"""SeriesRadar: single-process HTTP server and durable half-hour RSS collector."""
import base64
import concurrent.futures
from contextlib import contextmanager
import hashlib
import hmac
import html
import json
import logging
import os
import ipaddress
import socket
from pathlib import Path
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
import xml.etree.ElementTree as ET
import catalog as series_catalog
import dossier

ROOT = Path(__file__).parent
DB = Path(os.environ.get('DATA_DIR', str(ROOT / 'data'))) / 'radar.sqlite3'
INTERVAL = max(60, int(os.environ.get('SCAN_INTERVAL_SECONDS', '1800')))
LOCK = threading.Lock()
WAKE = threading.Event()
PHASES = ['Te beoordelen', 'Aangekondigd', 'In productie', 'Release gepland', 'Gereleased']

def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()

def init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS articles (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
          summary TEXT NOT NULL, source TEXT NOT NULL, publisher TEXT NOT NULL,
          published TEXT, discovered TEXT NOT NULL, phase TEXT NOT NULL,
          reason TEXT NOT NULL, reviewed INTEGER DEFAULT 0,
          series_title TEXT DEFAULT '', notes TEXT DEFAULT '', tvdb INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS articles_discovered ON articles(discovered DESC);
        CREATE TABLE IF NOT EXISTS sources (
          id TEXT PRIMARY KEY, name TEXT, last_attempt TEXT, last_success TEXT,
          error TEXT, fetched INTEGER DEFAULT 0, added INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS source_config (id TEXT PRIMARY KEY, config TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dossier_data (series_id TEXT,scope TEXT,revision INTEGER NOT NULL,fields TEXT NOT NULL,PRIMARY KEY(series_id,scope));
        CREATE TABLE IF NOT EXISTS article_facts (article_id TEXT PRIMARY KEY,facts TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dossier_sources (series_id TEXT,scope TEXT,url TEXT,name TEXT,facts TEXT,checked TEXT,error TEXT,PRIMARY KEY(series_id,scope,url));
        CREATE TABLE IF NOT EXISTS enrichment_checks (key TEXT PRIMARY KEY,checked TEXT,error TEXT);
        ''')
        columns = {r['name'] for r in c.execute('PRAGMA table_info(articles)')}
        for name, definition in [('production_kind', "TEXT DEFAULT 'Onbekend'"), ('season_number','INTEGER'), ('classification_reviewed','INTEGER DEFAULT 0'), ('excluded','INTEGER DEFAULT 0')]:
            if name not in columns:
                c.execute(f'ALTER TABLE articles ADD COLUMN {name} {definition}')

def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]*>', ' ', value or ''))).strip()


def decode_page(raw, encoding=None):
    if not encoding:
        match=re.search(rb'charset\s*=\s*["\x27]?([a-zA-Z0-9_-]+)',raw[:4096],re.I)
        encoding=match.group(1).decode('ascii') if match else 'utf-8'
    if encoding.lower() in ('iso-8859-1','latin-1'):encoding='windows-1252'
    return raw.decode(encoding,errors='replace')

def classify(title, summary=''):
    text = (title + ' ' + summary).lower()
    # A phase is an article-level signal, never an assertion about a whole series.
    rules = [
        ('Gereleased', r'vanaf vandaag|nu te (?:zien|streamen)|nu beschikbaar|is verschenen'),
        ('In productie', r'opnames?\b.{0,160}(?:gestart|begonnen|van start)|start(?:en)? (?:met |de )?opnames|in productie|wordt (?:momenteel )?opgenomen'),
        ('Release gepland', r'vanaf \d|verschijnt op|releasedatum|startdatum|in 20\d\d te zien|gaat op .{0,35}première|binnenkort te|dit najaar|dit voorjaar'),
        ('Aangekondigd', r'nieuwe .{0,30}serie|nieuw seizoen|aangekondigd|in ontwikkeling|komt met|in de maak'),
    ]
    for phase, pattern in rules:
        match = re.search(pattern, text)
        if match:
            return phase, match.group(0)
    return 'Te beoordelen', 'Geen duidelijke fase gevonden'

def parse_feed(data):
    root = ET.fromstring(data)
    items = root.findall('.//item')
    if not items and root.tag not in ('rss', '{http://www.w3.org/2005/Atom}feed'):
        raise ValueError('De bron gaf geen RSS/Atom-feed terug')
    if root.tag == '{http://www.w3.org/2005/Atom}feed':
        ns = '{http://www.w3.org/2005/Atom}'
        for item in root.findall(ns + 'entry'):
            link = item.find(ns + 'link')
            yield {'title': clean(item.findtext(ns+'title')), 'url': link.get('href', '') if link is not None else '', 'summary': clean(item.findtext(ns+'summary')), 'published': item.findtext(ns+'published') or item.findtext(ns+'updated'), 'publisher': ''}
    else:
        for item in items:
            yield {'title': clean(item.findtext('title')), 'url': (item.findtext('link') or '').strip(), 'summary': clean(item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or item.findtext('description')), 'published': item.findtext('pubDate'), 'publisher': clean(item.findtext('source'))}

def publication_date(value):
    if not value:
        return None
    try:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None

def relevant(item, source_id):
    title = item['title']
    publisher = item.get('publisher', '')
    if publisher:
        title = title.removesuffix(' - ' + publisher)
    summary = item.get('summary', '').replace(publisher, '') if publisher else item.get('summary', '')
    text = title + ' ' + summary
    series = r'\b(?:[a-zà-ÿ]*series?|sitcom|drama|gameshow|spelshow|quiz|partygame|realityprogramma|datingprogramma|talentenjacht|documentaire|tv-programma|televisieprogramma)\b'
    if not re.search(series, text, re.I):
        if not (re.search(r'\bseizoen\b|binnenkort te zien|komt naar televisie', title, re.I) and re.search(r'\b(tv|televisie|videoland|netflix|npo|sbs6|rtl|opnames)\b', text, re.I)):
            return False
    if re.search(r'\b(podcastserie|concertserie|concertseizoen|theaterseizoen|culturele seizoen|eredivisie|wereldtitel|voetbal|ajax|psv)\b', title, re.I):
        return False
    if source_id in ('streamers', 'broad') and not re.search(r'\b(nederlandse?|nederlandstalige|videoland|npo|avrotros|talpa|sbs6|bnnvara|kro.ncrv)\b', title, re.I):
        return False
    return True

def sources():
    defaults = {s['id']: s for s in json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))}
    with connect() as c:
        for row in c.execute('SELECT id,config FROM source_config'):
            defaults[row['id']] = json.loads(row['config'])
    return list(defaults.values())

def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Gebruik een publieke HTTPS-feed zonder inloggegevens of afwijkende poort.')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise ValueError('Lokale en private netwerkadressen zijn niet toegestaan.')
    return url

class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def validate_source(data):
    if not isinstance(data, dict):
        raise ValueError('Ongeldige bron')
    name = data.get('name', '')
    mode = data.get('mode')
    value = data.get('value','')
    if not isinstance(name,str) or not 1 <= len(name.strip()) <= 100 or not isinstance(value,str) or not 1 <= len(value.strip()) <= 1000 or mode not in ('feed','search') or type(data.get('enabled',True)) is not bool:
        raise ValueError('Vul een naam en een geldige feed of zoekopdracht in.')
    source_id = data.get('id') or 'custom-' + __import__('uuid').uuid4().hex[:16]
    if not isinstance(source_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', source_id):
        raise ValueError('Ongeldige bron-ID')
    s = {'id':source_id,'name':name.strip(),'enabled':data.get('enabled',True),'kind':'Directe persfeed' if mode=='feed' else 'Google Nieuws'}
    if mode == 'feed':
        s['url'] = public_url(value.strip())
    else:
        s['query'] = value.strip()
    return s

def fetch_source(source):
    url = source.get('url') or 'https://news.google.com/rss/search?' + urlencode({'q': source['query'], 'hl': 'nl', 'gl': 'NL', 'ceid': 'NL:nl'})
    request = Request(url, headers={'User-Agent': 'SeriesRadar/1.0 (personal news monitor)', 'Accept': 'application/rss+xml, application/xml, text/xml'})
    public_url(url)
    with build_opener(PublicRedirect()).open(request, timeout=25) as response:
        data = response.read(3_000_001)
    if len(data) > 3_000_000:
        raise ValueError('Feed is groter dan 3 MB')
    items=list(parse_feed(data))
    # User-supplied older articles may have aged out of a feed. Import each once.
    for link in source.get('initial_urls',[]):
        with connect() as c:
            exists=c.execute('SELECT 1 FROM articles WHERE url=?',(link,)).fetchone()
        if exists:continue
        public_url(link)
        with build_opener(PublicRedirect()).open(Request(link,headers={'User-Agent':'SeriesRadar/1.0'}),timeout=20) as r:
            raw=r.read(3_000_001)
            if len(raw)>3_000_000:raise ValueError('Pagina groter dan 3 MB')
            parser=dossier.ArticleParser();parser.feed(decode_page(raw,r.headers.get_content_charset()))
        title=' '.join(parser.headings) or parser.title
        published=None
        for schema in parser.schemas:
            nodes=schema if isinstance(schema,list) else schema.get('@graph',[schema]) if isinstance(schema,dict) else []
            for node in nodes:
                if isinstance(node,dict) and node.get('datePublished'):published=node['datePublished']
        items.append({'title':title,'summary':'\n'.join(parser.paragraphs),'url':link,'published':published,'publisher':source['name']})
    return items

def ingest(c, source, items):
    added = 0
    for item in items:
        if not item['title'] or urlparse(item['url']).scheme not in ('http', 'https'):
            continue
        if not relevant(item, source['id']):
            continue
        # Same headline across search feeds is one signal; later news remains separate.
        key = hashlib.sha256(clean(item['title']).casefold().encode()).hexdigest()[:24]
        phase, reason = classify(item['title'], item['summary'])
        result = c.execute('''INSERT OR IGNORE INTO articles
          (id,title,url,summary,source,publisher,published,discovered,phase,reason)
          VALUES (?,?,?,?,?,?,?,?,?,?)''', (key, item['title'][:700], item['url'], item['summary'][:12000], source['id'], item['publisher'] or source['name'], publication_date(item['published']), now(), phase, reason))
        added += result.rowcount
        name=series_catalog.extract_name(item)
        if name:
            facts=dossier.extract(item['title']+'\n'+item['summary'],name,item['url'])
            if facts:
                c.execute('INSERT OR REPLACE INTO article_facts VALUES (?,?)',(key,json.dumps(facts)))
    return added

def get_catalog():
    with connect() as c:
        articles=[dict(r) for r in c.execute('SELECT * FROM articles ORDER BY published DESC,discovered DESC')]
        saved=[dict(r) for r in c.execute('SELECT * FROM dossier_data')]
        imported=[dict(r) for r in c.execute('SELECT * FROM dossier_sources ORDER BY checked')]
        facts={r['article_id']:json.loads(r['facts']) for r in c.execute('SELECT * FROM article_facts')}
        checks={r['key']:dict(r) for r in c.execute('SELECT * FROM enrichment_checks')}
    result=series_catalog.catalog(articles)
    for group in result['series']:
        values={r['scope']:{'revision':r['revision'],'fields':json.loads(r['fields'])} for r in saved if r['series_id']==group['id']}
        candidates={}
        group['metadata_sources']=[]
        for r in imported:
            if r['series_id']!=group['id']:continue
            candidates.setdefault(r['scope'],{}).update(json.loads(r['facts'] or '{}'))
            group['metadata_sources'].append({k:r[k] for k in ('scope','url','checked','error')})
        group['dossiers']=dossier.prepare(group,values,candidates,facts)
        group['tvdb_check']=checks.get('tvdb:'+group['id'])
    result['dossier_fields']=[{'key':k,'label':label,'section':section} for k,label,section in dossier.FIELDS]
    return result

def import_metadata(series_id,scope,name,url):
    public_url(url)
    req=Request(url,headers={'User-Agent':'SeriesRadar/1.0 (metadata from public press articles)'})
    try:
        with build_opener(PublicRedirect()).open(req,timeout=25) as response:
            data=response.read(3_000_001)
            if len(data)>3_000_000:raise ValueError('De pagina is te groot')
            if 'html' not in response.headers.get('Content-Type',''):raise ValueError('Gebruik een HTML-nieuwsbericht')
            encoding=response.headers.get_content_charset()
        markup=decode_page(data,encoding)
        parser=dossier.ArticleParser();parser.feed(markup)
        text=parser.text_for(name)
        # Prevent importing a different numbered season into this production.
        detected=series_catalog.season_of(' '.join(parser.headings))
        expected=scope.split(':')[-1]
        if detected and expected!='?' and int(expected)!=detected:
            raise ValueError('Deze bron noemt een ander seizoen. Kies het bijbehorende seizoen in het dossier.')
        facts=dossier.tvdb_facts(markup,name,url) if urlparse(url).hostname in ('thetvdb.com','www.thetvdb.com') else dossier.extract(text,name,url)
        with connect() as c:
            c.execute('INSERT OR REPLACE INTO dossier_sources VALUES (?,?,?,?,?,?,NULL)',(series_id,scope,url,name,json.dumps(facts),now()))
        return facts
    except Exception as exc:
        with connect() as c:
            c.execute('UPDATE dossier_sources SET checked=?,error=? WHERE series_id=? AND scope=? AND url=?',(now(),str(exc)[:250],series_id,scope,url))
        raise


def due_check(key, days=1):
    with connect() as c:
        row=c.execute('SELECT checked FROM enrichment_checks WHERE key=?',(key,)).fetchone()
    return not row or row['checked'] < datetime.fromtimestamp(time.time()-days*86400,timezone.utc).isoformat()


def record_check(key,error=None):
    with connect() as c:
        c.execute('INSERT OR REPLACE INTO enrichment_checks VALUES (?,?,?)',(key,now(),error))


def enrich_articles(limit=8):
    """Bounded direct-page reads, including older stored fragments; errors back off a day."""
    with connect() as c:
        rows=[dict(r) for r in c.execute('SELECT * FROM articles WHERE excluded=0 ORDER BY published DESC')]
    count=0
    for a in rows:
        if count>=limit:break
        if urlparse(a['url']).hostname=='news.google.com':continue
        name=a.get('series_title') or series_catalog.extract_name(a)
        if not name or not due_check('article:'+a['id']):continue
        count+=1
        try:
            public_url(a['url'])
            with build_opener(PublicRedirect()).open(Request(a['url'],headers={'User-Agent':'SeriesRadar/1.0'}),timeout=20) as r:
                raw=r.read(3_000_001)
                if len(raw)>3_000_000:raise ValueError('Pagina groter dan 3 MB')
                parser=dossier.ArticleParser();parser.feed(decode_page(raw,r.headers.get_content_charset()))
            text=parser.text_for(name)
            facts=dossier.extract(text,name,a['url'])
            with connect() as c:
                c.execute('UPDATE articles SET summary=? WHERE id=?',(text[:12000],a['id']))
                c.execute('INSERT OR REPLACE INTO article_facts VALUES (?,?)',(a['id'],json.dumps(facts)))
            record_check('article:'+a['id'])
        except Exception as exc:record_check('article:'+a['id'],str(exc)[:250])


def check_tvdb(group):
    # A slug is a cheap candidate lookup, not proof that other spellings do not exist.
    url='https://thetvdb.com/series/'+series_catalog.normalize(group['name']).replace(' ','-')
    try:
        profile=next((p for p in group['dossiers'] if p['scope']=='new:1'),group['dossiers'][0] if group['dossiers'] else None)
        if not profile:return
        import_metadata(group['id'],profile['scope'],group['name'],url)
        record_check('tvdb:'+group['id'])
    except Exception as exc:
        record_check('tvdb:'+group['id'],'Niet automatisch bevestigd; zoek ook handmatig. '+str(exc)[:180])


def enrich_catalog():
    enrich_articles()
    count=0
    for group in get_catalog()['series']:
        if count>=4:break
        if not due_check('tvdb:'+group['id'],7):continue
        check_tvdb(group);count+=1

def scan():
    if not LOCK.acquire(blocking=False):
        return
    try:
        configured = sources()
        with connect() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('last_started',?)", (now(),))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch_source, s): s for s in configured if s.get('enabled', True)}
            for future in concurrent.futures.as_completed(futures):
                s = futures[future]
                stamp = now()
                try:
                    items = future.result()
                    with connect() as c:
                        added = ingest(c, s, items)
                        c.execute('''INSERT INTO sources VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                          name=excluded.name,last_attempt=excluded.last_attempt,last_success=excluded.last_success,error=NULL,fetched=excluded.fetched,added=excluded.added''', (s['id'], s['name'], stamp, stamp, None, len(items), added))
                except Exception as exc:
                    logging.warning('Source %s: %s', s['id'], exc)
                    with connect() as c:
                        c.execute('''INSERT INTO sources (id,name,last_attempt,error) VALUES (?,?,?,?)
                          ON CONFLICT(id) DO UPDATE SET last_attempt=excluded.last_attempt,error=excluded.error''', (s['id'], s['name'], stamp, str(exc)[:250]))
        enrich_catalog()
        with connect() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('last_finished',?)", (now(),))
            c.execute("INSERT OR REPLACE INTO meta VALUES ('next_scan',?)", (str(time.time() + INTERVAL),))
        # Revisit linked metadata sources once per day, bounded per news round.
        with connect() as c:
            due=[dict(r) for r in c.execute("SELECT * FROM dossier_sources WHERE checked < ? ORDER BY checked LIMIT 4",(datetime.fromtimestamp(time.time()-86400,timezone.utc).isoformat(),))]
        for source in due:
            try:import_metadata(source['series_id'],source['scope'],source['name'],source['url'])
            except Exception:logging.warning('Metadata source unavailable: %s',source['url'])
    finally:
        LOCK.release()

def scheduler():
    while True:
        WAKE.clear()
        try:
            scan()
        except Exception:
            logging.exception('Scan failed')
        WAKE.wait(INTERVAL)

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload, content_type='application/json; charset=utf-8'):
        body = json.dumps(payload, ensure_ascii=False).encode() if content_type.startswith('application/json') else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        password = os.environ.get('ADMIN_PASSWORD', '')
        if not password:
            return True
        expected = 'Basic ' + base64.b64encode((os.environ.get('ADMIN_USER', 'admin') + ':' + password).encode()).decode()
        if hmac.compare_digest(self.headers.get('Authorization', ''), expected):
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="SeriesRadar", charset="UTF-8"')
        self.send_header('Content-Length', '0')
        self.end_headers()
        return False

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            with connect() as c:
                c.execute('SELECT 1').fetchone()
            return self.respond(200, {'status': 'ok'})
        if not self.authorized():
            return
        if path == '/api/dashboard':
            with connect() as c:
                statuses = {r['id']: dict(r) for r in c.execute('SELECT * FROM sources')}
                meta = dict(c.execute('SELECT key,value FROM meta').fetchall())
            return self.respond(200, {**get_catalog(), 'sources': [{**statuses.get(s['id'], {}), **s} for s in sources()], 'meta': meta, 'scanning': LOCK.locked(), 'interval': INTERVAL})
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8'), '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
        if path in files:
            name, kind = files[path]
            return self.respond(200, (ROOT / 'public' / name).read_bytes(), kind)
        self.respond(404, {'error': 'Niet gevonden'})

    def do_POST(self):
        if not self.authorized():
            return
        # Non-simple header plus JSON requirement blocks cross-site form/JS writes.
        if self.headers.get('X-Radar-Request') != '1' or self.headers.get('Content-Type') != 'application/json':
            return self.respond(403, {'error': 'Ongeldig verzoek'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 250000:
                raise ValueError('Ongeldige grootte')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Ongeldige invoer')
            if self.path == '/api/scan':
                WAKE.set()
                return self.respond(202, {'ok': True})
            if self.path in ('/api/dossier','/api/dossier/import','/api/dossier/check-tvdb'):
                group=next((g for g in get_catalog()['series'] if g['id']==data.get('series_id')),None)
                if not group: return self.respond(404,{'error':'Serie niet gevonden'})
                profile=next((p for p in group['dossiers'] if p['scope']==data.get('scope')),None)
                if not profile:raise ValueError('Selecteer een bestaande productie of seizoen')
                if self.path.endswith('/check-tvdb'):
                    if not LOCK.acquire(blocking=False):return self.respond(409,{'error':'Er loopt een scan. Probeer het na de scan opnieuw.'})
                    try:
                        if due_check('tvdb:'+group['id']):check_tvdb(group)
                    finally:LOCK.release()
                    return self.respond(200,{'ok':True})
                if self.path.endswith('/import'):
                    url=data.get('url','')
                    if not isinstance(url,str) or len(url)>2000:raise ValueError('Ongeldige bronlink')
                    try:
                        facts=import_metadata(group['id'],profile['scope'],group['name'],url)
                        return self.respond(200,{'ok':True,'found':len(facts)})
                    except Exception as exc:return self.respond(400,{'error':str(exc)[:250]})
                fields=dossier.validate_fields(data.get('fields'))
                with connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    row=c.execute('SELECT revision,fields FROM dossier_data WHERE series_id=? AND scope=?',(group['id'],profile['scope'])).fetchone()
                    revision=row['revision'] if row else 0
                    if type(data.get('revision')) is not int or data['revision']!=revision:
                        return self.respond(409,{'error':'Dit dossier is intussen gewijzigd. Sluit en open het formulier opnieuw.'})
                    merged={**(json.loads(row['fields']) if row else {}),**fields}
                    c.execute('INSERT OR REPLACE INTO dossier_data VALUES (?,?,?,?)',(group['id'],profile['scope'],revision+1,json.dumps(merged)))
                return self.respond(200,{'ok':True,'revision':revision+1})
            if self.path == '/api/article':
                if data.get('phase') not in series_catalog.PHASES or data.get('production_kind') not in series_catalog.KINDS or type(data.get('tvdb')) is not int or data['tvdb'] not in (0,1) or not isinstance(data.get('series_title'), str) or not isinstance(data.get('notes'), str) or type(data.get('excluded')) is not int or data['excluded'] not in (0,1):
                    raise ValueError('Ongeldige velden')
                season = data.get('season_number')
                if season is not None and (type(season) is not int or not 1 <= season <= 99):
                    raise ValueError('Gebruik een seizoennummer tussen 1 en 99 of laat het leeg.')
                if data['production_kind'] == 'Nieuwe serie' and season not in (None,1):
                    raise ValueError('Een nieuwe serie kan alleen seizoen 1 hebben; kies Nieuw seizoen.')
                if data['production_kind'] == 'Nieuw seizoen' and season == 1:
                    raise ValueError('Seizoen 1 hoort bij Nieuwe serie.')
                if not data['excluded'] and not data['series_title'].strip():
                    raise ValueError('Vul een serietitel in of negeer het bericht.')
                with connect() as c:
                    result = c.execute('''UPDATE articles SET phase=?,series_title=?,notes=?,tvdb=?,reviewed=1,
                      production_kind=?,season_number=?,classification_reviewed=1,excluded=? WHERE id=?''', (data['phase'], data['series_title'].strip()[:200], data['notes'][:5000], data['tvdb'],data['production_kind'],season,data['excluded'],data.get('id')))
                return self.respond(200 if result.rowcount else 404, {'ok': bool(result.rowcount)})
            if self.path in ('/api/source', '/api/source/test'):
                try:
                    s = validate_source(data)
                    if self.path.endswith('/test'):
                        items = fetch_source(s)
                        return self.respond(200, {'count':len(items), 'examples':[i['title'] for i in items[:5]]})
                    with connect() as c:
                        c.execute('INSERT OR REPLACE INTO source_config VALUES (?,?)',(s['id'],json.dumps(s)))
                    return self.respond(200, {'ok':True, 'id':s['id']})
                except Exception as exc:
                    return self.respond(400, {'error':str(exc)[:250]})
            self.respond(404, {'error': 'Niet gevonden'})
        except (ValueError, TypeError, AttributeError) as exc:
            self.respond(400, {'error': str(exc)[:250] or 'Ongeldige invoer'})

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    init()
    if '--scan-once' in __import__('sys').argv:
        scan()
    else:
        host = os.environ.get('HOST', '127.0.0.1')
        if host not in ('127.0.0.1', 'localhost') and not os.environ.get('ADMIN_PASSWORD'):
            raise SystemExit('Stel ADMIN_PASSWORD in voordat de app op het netwerk wordt gestart.')
        threading.Thread(target=scheduler, daemon=True).start()
        ThreadingHTTPServer((host, int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
