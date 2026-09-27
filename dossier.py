"""Source-backed metadata candidates and editable IMDb/TVDB preparation dossiers."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse
from catalog import normalize, extract_name

FIELDS = [
    ('original_title','Oorspronkelijke titel','Basis'),('alternative_titles','Alternatieve titels','Basis'),
    ('format','Type / formaat','Basis'),('synopsis','Synopsis (bronvoorstel; herschrijven voor inzending)','Basis'),
    ('countries','Productieland(en)','Basis'),('languages','Originele taal/talen','Basis'),('genres','Genres','Basis'),
    ('networks','Netwerk / omroep','Uitgave'),('platforms','Streamingplatform','Uitgave'),
    ('production_companies','Productiebedrijf','Uitgave'),('distributors','Distributeur / coproductiepartners','Uitgave'),
    ('release_date','Premièredatum / releaseplanning','Uitgave'),('release_year','Releasejaar','Uitgave'),
    ('episodes','Aantal afleveringen','Uitgave'),('runtime','Speelduur per aflevering','Uitgave'),
    ('cast','Cast — acteur | personage','Makers'),('directors','Regie','Makers'),('writers','Scenario','Makers'),
    ('creators','Bedenkers / ontwikkelaars','Makers'),('producers','Producenten (personen)','Makers'),
    ('presenters','Presentatoren','Makers'),('participants','Deelnemers','Makers'),
    ('official_url','Officiële seriepagina','Links'),('trailer_url','Trailer','Links'),('artwork_url','Poster / beeldmateriaal (rechten controleren)','Links'),
    ('imdb_id','Bestaand IMDb-ID','Links'),('tvdb_id','Bestaand TVDB-ID','Links'),
    ('episode_guide','Afleveringen — nummer | titel | datum','Aanvullend'),('notes','Bijzonderheden / invoernotities','Aanvullend'),
]
KEYS = {key for key,_,_ in FIELDS}
CHECK_FIELDS = ['original_title','synopsis','countries','languages','genres','production_companies','cast','directors','release_date','episodes','runtime']

def valid_link(value):
    p = urlparse(value)
    return p.scheme in ('http','https') and bool(p.hostname) and not p.username and not p.password

def validate_fields(fields):
    if not isinstance(fields,dict) or set(fields)-KEYS:
        raise ValueError('Ongeldige dossiervelden')
    result={}
    for key, field in fields.items():
        if not isinstance(field,dict) or set(field)-{'value','source_url','evidence'}:
            raise ValueError('Ongeldig gegeven')
        if any(not isinstance(field.get(k,''),str) for k in ('value','source_url','evidence')):
            raise ValueError('Gebruik tekst in de dossiervelden')
        value=field.get('value','').strip(); source=field.get('source_url','').strip(); evidence=field.get('evidence','').strip()
        if len(value)>6000 or len(source)>2000 or len(evidence)>600:
            raise ValueError('Een dossierveld is te lang')
        if source and not valid_link(source): raise ValueError('Gebruik een volledige http(s)-bronlink')
        if key.endswith('_url') and value and not valid_link(value): raise ValueError('Gebruik een volledige http(s)-link')
        if key=='imdb_id' and value and not re.fullmatch(r'tt\d{7,12}',value): raise ValueError('Een IMDb-ID begint met tt, gevolgd door cijfers')
        if key=='tvdb_id' and value and not value.isdigit(): raise ValueError('Een TVDB-ID bevat alleen cijfers')
        result[key]={'value':value,'source_url':source,'evidence':evidence,'origin':'manual'}
    return result

def scope_of(p):
    return ('new' if p['kind']=='Nieuwe serie' else 'season' if p['kind']=='Nieuw seizoen' else 'unknown')+':'+str(p['season'] or '?')

def extract(text, name, url):
    """Only explicit relationships; publisher names are never network/producer proof."""
    facts={}
    if normalize(name) not in normalize(text): return facts
    text=re.split(r'Nederlands drama bij|Nederlandse series bij|Lees ook|Gerelateerde berichten',text,flags=re.I)[0]
    def add(key,value,evidence):
        value=value.strip(' \n.,;:')
        if not value: return
        facts.setdefault(key,{'value':value,'source_url':url,'evidence':evidence[:350],'origin':'automatic'})
    patterns = {
        'production_companies': [r'\bproducent\s+(?!van\b|voor\b|is\b)([A-Z][\w &-]{1,70})(?=[.,;\n]|\s+(?:en|voor|van|meldt|zegt|laat)\b)',r'(?:geproduceerd|gemaakt) door ([^.\n]+)',r'(?:een productie van|productie(?:bedrijf)?\s*:)\s*([^\n.]+)',r'(?:^|[.\n]\s*)([A-Z][\w &-]{1,70}?) is de producent van (?:de serie|het programma)'],
        'directors':[r'(?:geregisseerd door|regie (?:(?:is|ligt) )?in handen van|regie\s*:)\s*([^\n.]+)'],
        'writers':[r'(?:scenario is geschreven door|geschreven door|scenario\s*:)\s*([^\n.]+)'],
        'creators':[r'(?:ontwikkeld door|bedacht door|(?:naar |is )?een idee van)\s*([^\n.]+)'],
        'producers':[r'(?:producenten zijn|uitvoerend producent(?:en)?\s*:)\s*([^\n.]+)'],
        'distributors':[r'(?:een coproductie van|distributie door)\s*([^\n.]+)'],
        'cast':[r'(?:hoofdrollen worden gespeeld door|(?:hoofd)?rollen (?:worden )?vertolkt door|cast bestaat uit|hoofdrollen voor|met in de hoofdrollen|cast\s*:)\s*([^\n.]+)',r'([A-ZÀ-Ý][^.\n]{3,230}?) spelen de hoofdrollen'],
        'episodes':[r'\b(\d{1,3}) (?:afleveringen|delen)\b'],
        'presenters':[r'(?:gepresenteerd door|presentatie (?:is )?in handen van|presentator(?:en)?\s*:)\s*([^\n.]+)'],
        'runtime':[r'(?:afleveringen van|speelduur(?: per aflevering)?(?: van|:)?)\s*(\d{1,3}\s*minuten)'],
        'countries':[r'(?:productieland(?:en)?|land van productie)\s*:\s*([^\n.]+)'],
        'languages':[r'(?:originele taal|gesproken taal)\s*:\s*([^\n.]+)',r'\b(Nederlandstalig)e?\b'],
    }
    for key, patterns_for_key in patterns.items():
        for pattern in patterns_for_key:
            m=re.search(pattern,text,re.I if key!='cast' or pattern.startswith('(?:') else 0)
            if not m: continue
            if key=='episodes' and re.search(r'\b(?:na|eerste|laatste)\s*$',text[:m.start()],re.I):continue
            value=re.split(r',?\s+(?:bekend van|de makers van|en geregisseerd|en geschreven|in deze|waarin|waarbij|naast|voor deze)\b',m.group(1),maxsplit=1,flags=re.I)[0]
            if key=='production_companies' and re.match(r'(?:de\s+)?(?:presentator(?:en)?|acteur(?:s)?|cast)\b',value,re.I):continue
            if key=='cast':value=re.sub(r'^(?:onder anderen|onder meer|o\.a\.)\s+','',value,flags=re.I)
            if key=='presenters':value=re.sub(r'\s+en\s+','\n',value,flags=re.I)
            if key in ('cast','directors','writers','creators','producers','production_companies','distributors'):
                value=re.sub(r'\([^)]*\)','',value)
                value=re.split(r'\s+(?:in co-?productie met|in opdracht van|en wordt|wordt gemaakt|voor (?:de|het))\b',value,maxsplit=1,flags=re.I)[0]
                names=re.split(r',\s*|\s+en\s+',value)
                names=[n.strip() for n in names if n.strip()]
                if any(len(n)>90 or len(n.split())>8 for n in names): continue
                if key=='production_companies' and len(names)>1:
                    # Production credits can mix companies and individual producers.
                    companies=[n for n in names if re.search(r'\b(?:Pupkin|NewBe|Fremantle|EndemolShine|Talpa|Film|Films|Productions|Media|Studios|Valley|Lemming|Millstreet)\b',n,re.I)]
                    if companies:names=companies
                value='\n'.join(names)
            add(key,value,m.group(0))
            break
    network=re.findall(r'(?:bij|op)\s+(AVROTROS|BNNVARA|KRO-NCRV|NPO\s*(?:Zapp|Start|Plus|[123])|SBS\s*6|Net\s*5|RTL\s*[4578]|VRT|Proximus)\b',text,re.I)
    platform_name=r'(?:Videoland|Netflix|Prime Video|Disney\+|HBO Max|SkyShowtime|NPO Start|NPO Plus|NLZIET|Streamz|KIJK)'
    platform_groups=re.findall(r'(?:bij|op|via)\s+(?:\(?o\.a\.\)?\s+)?('+platform_name+r'(?:\s+en\s+'+platform_name+r')*)(?!\w)',text,re.I)
    platform=[v for group in platform_groups for v in re.split(r'\s+en\s+',group,flags=re.I)]
    if network:add('networks','\n'.join(dict.fromkeys(network)),'Expliciete verwijzing: bij/op '+', '.join(dict.fromkeys(network)))
    if platform:add('platforms','\n'.join(dict.fromkeys(platform)),'Expliciete verwijzing: bij/op '+', '.join(dict.fromkeys(platform)))
    m=re.search(r'(?:vanaf|op)\s+(?:(?:maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)\s+)?(\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)(?:\s+20\d{2})?)[^\n]{0,90}?(?:te zien|te streamen|beschikbaar|première)',text,re.I)
    if m:
        add('release_date',m.group(1),m.group(0))
        year=re.search(r'\b20\d{2}\b',m.group(1))
        if year:add('release_year',year.group(0),m.group(0))
    m=re.search(r'in\s+(20\d{2})\s+te (?:streamen|zien)',text,re.I)
    if m:add('release_year',m.group(1),m.group(0))
    numbers={'een':1,'twee':2,'drie':3,'vier':4,'vijf':5,'zes':6,'zeven':7,'acht':8,'negen':9,'tien':10,'elf':11,'twaalf':12}
    m=re.search(r'\b('+ '|'.join(numbers)+r')(?:delige| afleveringen)\b',text,re.I)
    if m and not re.search(r'\b(?:na|eerste|laatste)\s*$',text[:m.start()],re.I):add('episodes',str(numbers[m.group(1).lower()]),m.group(0))
    m=re.search(r'(?:^|\n)Synopsis\s*:?\s+([^\n]+)',text,re.I)
    if m:add('synopsis',m.group(1)[:6000], 'Synopsis uit de bron; herschrijven voor inzending')
    genres={'drama':r'dramaserie|drama-serie','Comedy':r'comedy|komedie|sitcom','Thriller':r'thrillerserie','Misdaad':r'misdaadserie','Documentaire':r'documentaireserie|docuserie','Reality':r'reality[- ]?(?:serie|programma|show|hit|competitie)|survivalprogramma|datingexperiment|datingprogramma','Spelshow':r'gameshow|spelshow|spelprogramma|quiz','Animatie':r'animatieserie'}
    found=[k for k,p in genres.items() if re.search(r'\b(?:'+p+r')\b',text,re.I)]
    if found:add('genres','\n'.join(found),'Expliciete genrevermelding in artikel')
    if re.search(r'\b(?:gameshow|spelshow|spelprogramma|quiz)\b',text,re.I):add('format','Spelshow','Spelprogramma genoemd in artikel')
    # Common prose credits, in addition to labelled press-kit fields.
    person=r'[A-ZÀ-Ý][\wÀ-ÿ]+(?: (?:[A-ZÀ-Ý][\wÀ-ÿ]+|da|de|van|der|den)){1,5}'
    m=re.search(r'('+person+r'(?: en '+person+r')?) (?:presenteren|presenteert)\b',text)
    if m:add('presenters',m.group(1).replace(' en ','\n'),m.group(0))
    m=re.search(r'\bpresentatoren\s+('+person+r'(?: en '+person+r')?)\b',text)
    if m:add('presenters',m.group(1).replace(' en ','\n'),m.group(0))
    m=re.search(r'\b(Nederlandse|Belgische|Vlaamse) (?:[\w-]+ ){0,2}(?:serie|spelshow|quiz|realityprogramma|datingprogramma)\b',text,re.I)
    if m:add('countries','Nederland' if m.group(1).lower()=='nederlandse' else 'België',m.group(0))
    m=re.search(r'\b(reality[- ]?(?:programma|show|serie|experiment|competitie)|datingprogramma|liefdesexperiment|documentaireserie|dramaserie)\b',text,re.I)
    if m:
        add('format',m.group(1),m.group(0))
        if re.search('reality|dating|liefdes',m.group(1),re.I):add('genres','Reality',m.group(0))
    if 'synopsis' not in facts:
        candidates=[]
        for paragraph in text.splitlines():
            if (60<=len(paragraph)<=1800 and normalize(name) in normalize(paragraph)
                    and re.search(r'\bis een\b|\b(?:volgen|volgt|draait|reizen|ontdekken|strijden|nemen|spelen)\b|\bdoen zich\b',paragraph,re.I)
                    and not re.search(r'\b(?:deelnemers gezocht|aanmelden|meld je aan|oproep|voor het tweede seizoen zoeken|wanneer het tweede seizoen)\b',paragraph,re.I)):
                candidates.append(paragraph)
        if candidates:
            paragraph=max(candidates,key=lambda p:(not bool(re.search(r'\b(?:vanaf|releasedatum|première|te zien|te streamen)\b',p,re.I)),bool(re.search(r'\bIn\s+'+re.escape(name)+r'\b',p,re.I)),bool(re.search(r'\b(?:volgt|volgen|draait|reizen|strijden|doen zich)\b',p,re.I)),-len(p)))
            add('synopsis',paragraph,'Beschrijving uit de bron; herschrijven voor inzending')
    return facts


def tvdb_facts(markup, name, url):
    """Read the public series page; never infer existence from a guessed URL."""
    from html import unescape
    def plain(s):return re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',s))).strip()
    heading=re.search(r'<h1\b[^>]*>(.*?)</h1>',markup,re.S|re.I)
    if not heading or normalize(plain(heading.group(1)))!=normalize(name):
        raise ValueError('TVDB-pagina heeft geen exact overeenkomende titel; controleer handmatig.')
    fields={}
    mapping={'TheTVDB.com Series ID':'tvdb_id','Original Language':'languages','Original Country':'countries','Genres':'genres','Network':'networks','Production Company':'production_companies'}
    for label,body in re.findall(r'<strong[^>]*>(.*?)</strong>(.*?)</li>',markup,re.S|re.I):
        key=mapping.get(plain(label))
        if key:
            values=[plain(v) for v in re.findall(r'<span[^>]*>(.*?)</span>',body,re.S)]
            value='\n'.join(v for v in values if v)
            if value:fields[key]={'value':value,'source_url':url,'evidence':'TVDB: '+plain(label),'origin':'automatic'}
    if not fields.get('tvdb_id',{}).get('value','').isdigit():raise ValueError('Geen geldig TVDB-serie-ID gevonden')
    # Same-name foreign shows must not become automatic domestic matches.
    if normalize(fields.get('countries',{}).get('value','')) not in ('the netherlands','netherlands','nederland'):
        raise ValueError('TVDB-titel gevonden, maar Nederlandse herkomst niet bevestigd; controleer handmatig.')
    overview=re.search(r'<div\b[^>]*class="change_translation_text"[^>]*data-language="nld"[^>]*>(.*?)</div>',markup,re.S)
    if overview:
        fields['synopsis']={'value':plain(overview.group(1))[:6000],'source_url':url,'evidence':'Nederlandse TVDB-synopsis; herschrijven voor inzending','origin':'automatic'}
    imdb=re.search(r'https://www.imdb.com/title/(tt\d+)/',markup)
    if imdb:fields['imdb_id']={'value':imdb.group(1),'source_url':url,'evidence':'TVDB externe IMDb-link','origin':'automatic'}
    return fields

class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__();self.paragraphs=[];self.headings=[];self.descriptions=[];self.title='';self.capture=None;self.buffer=[];self.skip=0;self.is_script=False;self.script=[];self.schemas=[]
        self.divs=[];self.main_paragraphs=[];self.section_headings=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='div':
            self.divs.append(bool(self.divs and self.divs[-1]) or attrs.get('itemprop')=='articleBody' or bool(re.search(r'\b(?:detailpage__detailtext|article-body|article__body|article-content)\b',attrs.get('class',''))))
        if tag=='meta' and (attrs.get('name')=='description' or attrs.get('property')=='og:description') and attrs.get('content'):
            self.descriptions.append(attrs['content'])
        if tag=='script':
            self.is_script=attrs.get('type')=='application/ld+json';self.script=[]
        if tag in ('script','style','nav','footer'): self.skip+=1
        if not self.skip and tag in ('p','h1','h2','title'):
            self.capture=tag;self.buffer=[]
    def handle_endtag(self,tag):
        if tag=='div' and self.divs:self.divs.pop()
        if tag=='script' and self.is_script:
            try:self.schemas.append(json.loads(''.join(self.script)))
            except ValueError:pass
            self.is_script=False
        if tag in ('script','style','nav','footer') and self.skip:self.skip-=1
        if self.capture==tag:
            value=re.sub(r'\s+',' ',''.join(self.buffer)).strip()
            if tag=='h1':self.headings.append(value)
            if tag=='h2':self.section_headings.append(value)
            if tag=='title':self.title=value
            if tag in ('p','h2'):
                self.paragraphs.append(value)
                if self.divs and self.divs[-1]:self.main_paragraphs.append(value)
            self.capture=None
    def handle_data(self,data):
        if self.is_script:self.script.append(data)
        if not self.skip and self.capture:self.buffer.append(data)
    def text_for(self,name):
        if normalize(name) not in normalize(' '.join(self.headings) or self.title):
            heading=self.headings[0] if self.headings else self.title
            if heading:
                text=self.text_for(heading)
                # A teaser headline can omit the title, but the article itself
                # must explicitly identify it before metadata can be imported.
                if normalize(extract_name({'title':heading,'summary':text}))==normalize(name):return text
            # A roundup can supply a clearly delimited programme section.
            for i,paragraph in enumerate(self.paragraphs):
                if (normalize(paragraph)==normalize(name) or re.match(re.escape(name)+r'\s*[,–—:]\s*(?:vanaf|op)\b',paragraph,re.I)):
                    section=[paragraph]
                    for following in self.paragraphs[i+1:]:
                        if following in self.section_headings or re.match(r'.{2,85}?,\s*(?:vanaf|op)\b',following,re.I):break
                        section.append(following)
                    if len(section)>1:return '\n'.join(section)[:60000]
            raise ValueError('De pagina bevat geen afgebakend artikel of onderdeel over deze serie.')
        text='\n'.join(self.headings[:1]+list(dict.fromkeys(self.descriptions))+(self.main_paragraphs or self.paragraphs))
        for schema in self.schemas:
            nodes=schema if isinstance(schema,list) else schema.get('@graph',[schema]) if isinstance(schema,dict) else []
            for node in nodes:
                if isinstance(node,dict) and normalize(name) in normalize(node.get('headline','') or node.get('name','')) and isinstance(node.get('description'),str):
                    text+='\n'+node['description']
                if isinstance(node,dict) and isinstance(node.get('articleBody'),str) and normalize(name) in normalize(node.get('headline','')):
                    return ('\n'.join(self.headings)+'\n'+node['articleBody'])[:60000]
        text=re.split(r'\n(?:TVvisie Extra|Onze apps|Meest recente|Gerelateerde berichten|Lees ook|Vacatures|Aanbiedingen|Reacties Netflix Nieuws|Meer populaire artikelen|Meer film- en serienieuws|Elke week het meest gelezen)\b',text,flags=re.I)[0]
        return text[:60000]

def prepare(group, saved, imported, article_facts=None):
    result=[]
    for production in group['productions']:
        scope=scope_of(production); candidates={}
        articles=[a for a in group['articles'] if a['id'] in production['articles']]
        for a in reversed(articles):
            fresh={**(article_facts or {}).get(a['id'],{}),**extract(a['title']+'\n'+a['summary'],group['name'],a['url'])}
            if ('release_date' in fresh and 'release_year' not in fresh
                    and fresh['release_date']['value']!=candidates.get('release_date',{}).get('value')):
                # Do not combine a revised date with an old announcement's year.
                candidates.pop('release_year',None)
            candidates.update(fresh)
        candidates.update(imported.get(scope,{}))
        candidates.setdefault('original_title',{'value':group['name'],'source_url':articles[0]['url'] if articles else '', 'evidence':'Gekoppelde serietitel; controleer de spelling','origin':'automatic'})
        stored=saved.get(scope,{'revision':0,'fields':{}})
        values={**candidates,**stored['fields']}
        filled=[k for k in CHECK_FIELDS if values.get(k,{}).get('value')]
        result.append({'scope':scope,'kind':production['kind'],'season':production['season'],'status':production['status'],'revision':stored['revision'],'fields':values,'filled':len(filled),'total':len(CHECK_FIELDS),'missing':[k for k in CHECK_FIELDS if k not in filled]})
    return result
