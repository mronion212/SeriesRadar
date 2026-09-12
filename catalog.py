"""Conservative, explainable series extraction. Unknowns go to an inbox."""
import hashlib
import re
import unicodedata

PHASES = ['Onbekend', 'Aangekondigd', 'Release gepland', 'In productie', 'Geproduceerd', 'Beschikbaar']
KINDS = ['Onbekend', 'Nieuwe serie', 'Nieuw seizoen']
MONTHS = 'januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december'
SERIES_WORD = r'(?:[a-zà-ÿ]*serie|sitcom|gameshow|spelshow|quiz|partygame|realityprogramma|datingprogramma|talentenjacht|documentaire|tv-programma|televisieprogramma)\b'
ORDINALS = {'eerste':1,'tweede':2,'derde':3,'vierde':4,'vijfde':5,'zesde':6,'zevende':7,'achtste':8,'negende':9,'tiende':10,'elfde':11,'twaalfde':12}
ALIASES_PHASE = {'Te beoordelen':'Onbekend','Gereleased':'Beschikbaar'}

def normalize(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()

def headline(a):
    text = a['title']
    if a.get('publisher'):
        text = text.removesuffix(' - ' + a['publisher'])
    return text.strip()

def phase_of(text):
    rules = [
        ('Onbekend', r'gaat niet door|geannuleerd|stopgezet|opnames?\b.{0,50}uitgesteld'),
        ('Beschikbaar', r'vanaf vandaag (?:te zien|te streamen|beschikbaar)|(?:nu|inmiddels|al) (?:volledig )?te (?:zien|streamen)|nu beschikbaar|is (?:nu )?(?:verschenen|uitgebracht)|vandaag (?:te zien|te streamen)|sinds\b.{0,80}?(?:op|bij) (?:Videoland|Netflix|NPO|Prime Video)|in zijn geheel te streamen'),
        ('Geproduceerd', r'opnames?\b.{0,90}?(?:afgerond|achter de rug|voltooid)|laatste draaidag|productie (?:is )?(?:afgerond|voltooid)|klaar met (?:de )?opnames'),
        ('In productie', r'opnames?\b.{0,160}?(?:gestart|begonnen|van start)|start(?:en)? (?:met |de )?opnames|in productie|wordt (?:momenteel )?opgenomen'),
        ('Release gepland', r'(?:vanaf|op)\s+(?:(?:maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)\s+)?\d{1,2}\s+(?:'+MONTHS+r')[^\n]{0,100}?(?:te zien|te streamen|beschikbaar)|in 20\d\d te (?:zien|streamen)'),
        ('Aangekondigd', r'aangekondigd|kondigt .{0,100}?aan|in ontwikkeling|in de maak|nieuwe .{0,50}?serie\b|nieuw(?:e)? seizoen|krijgt .{0,35}?seizoen|releasedatum|startdatum|vanaf \d|binnenkort te|in 20\d\d te zien|verschijnt|komt met'),
    ]
    for phase, pattern in rules:
        if phase=='Beschikbaar':
            for sentence in re.split(r'(?<=[.!?])\s+|\n',text):
                if re.search(r'\b(?:binnenkort|vanaf (?!vandaag)|nog niet|niet meer|zal|volgende maand)\b',sentence,re.I):continue
                m=re.search(pattern,sentence,re.I)
                if m:return phase,m.group(0)
            continue
        m = re.search(pattern, text, re.I)
        if m:
            return phase, m.group(0)
    return 'Onbekend', 'Geen expliciete productiestatus in het feedbericht'

def season_of(text):
    m = re.search(r'\bseizoen\s+(\d{1,2})\b', text, re.I)
    if m: return int(m.group(1))
    m = re.search(r'\b(' + '|'.join(ORDINALS) + r')(?: en laatste)? seizoen\b', text, re.I)
    return ORDINALS[m.group(1).lower()] if m else None

def kind_of(text, season):
    if season and season > 1:
        return 'Nieuw seizoen'
    if re.search(r'\bnieuw(?:e)? seizoen|vervolgseizoen|verlengd|krijgt .{0,25}seizoen', text, re.I):
        return 'Nieuw seizoen' if season != 1 else 'Nieuwe serie'
    if re.search(r'\bnieuwe?\b.{0,55}' + SERIES_WORD, text, re.I) or season == 1:
        return 'Nieuwe serie'
    if re.search(SERIES_WORD, text, re.I) and re.search(r'binnenkort te zien|komt naar televisie|maakt .{0,20}debuut', text, re.I):
        return 'Nieuwe serie'
    return 'Onbekend'

def tidy_name(value):
    value = value.strip(' \"\'‘’“”.,:;!?')
    value = re.split(r'\s+(?:aangekondigd|gestart|afgerond|binnenkort|van start|in de maak|in duistere|naar het boek|en nóg|en nog|over|met|bij|op|vanaf|in 20\d\d|seizoen|komt|krijgt|keert|toont|vertelt|overtreft|draait|duikt|speelt|laat|wordt|is|te zien|te streamen|bekend|onthuld)\b|[,!?]|\s+-\s+', value, maxsplit=1, flags=re.I)[0]
    value = value.strip(' \"\'‘’“”.,:;!?')
    if not 2 <= len(value) <= 85 or len(value.split()) > 12:
        return ''
    if not value[0].isupper() or re.match(r'^(?:De|Het|Een)?\s*(?:nieuwe|Nederlandse|Netflix|Videoland|NPO|SBS6|MAX|KIJK|VPRO|RTL|Original|over|aan|met|van|dit|deze)\b', value, re.I):
        return ''
    return value.title() if value.isupper() else value

def extract_name(a):
    """Require a title-shaped phrase immediately after a series noun."""
    text = headline(a)
    patterns = [
        r'\b' + SERIES_WORD + r'\s+[‘’\'“\"]([^‘’\'“\"]{2,85})[‘’\'“\"]',
        r'\b' + SERIES_WORD + r'\s+([^:]+)$',
        r'^([^:]{2,85}):\s*(?:een |de |nieuwe |indringende ).*' + SERIES_WORD,
        r'\bnieuwe?\s+([A-ZÀ-Ý][\wÀ-ÿ]*(?:\s+(?:[A-ZÀ-Ý][\wÀ-ÿ]*|de|het|van|en)){0,6})-serie\b',
        r'\bseizoen\s+(?:\d{1,2}\s+)?(?:van\s+)?[‘’\'“\"]([^‘’\'“\"]+)[‘’\'“\"]',
        r'[‘’\'“\"]([^‘’\'“\"]+)[‘’\'“\"]\s+seizoen\s+\d',
        r'\b(?:nieuw(?:e)?|eerste|tweede|derde|vierde|vijfde) seizoen\s+(?:van\s+)?([^:]+)$',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I if 'A-Z' not in pattern else 0)
        if m:
            candidate = tidy_name(m.group(1))
            # A quoted adjective or a creator's other series is not a title.
            if candidate and not re.search(r'makers|producent|regisseur', text[m.end():m.end()+15], re.I):
                return candidate
    return ''

def noise_reason(a):
    text = headline(a)
    if re.search(r'recensie|kijktips|top\s*\d|best(?:e| bekeken)|meest bekeken|films en series|premièredatums|(?:deze|zes) misdaadseries|internationale topseries|archief|kijkcijfer|schiet .{0,30}door het dak|podcast|theaterseizoen|concert|culturele seizoen|wereldtitel|eredivisie|\bserie [ab]\b|voetballer|\bPSV\b|\bAjax\b', text, re.I):
        return 'Kijktip, recensie, algemeen overzicht of ander nieuws'
    return ''

def assess(a, known):
    title = headline(a)
    # Search snippets frequently just repeat the headline. Limit context to stored fragment.
    text = title + ' ' + a.get('summary','')
    season = season_of(title)
    kind = kind_of(title, season)
    phase, evidence = phase_of(text)
    name = extract_name(a)
    normalized = ' ' + normalize(title) + ' '
    matches = [v for k,v in known.items() if ' ' + k + ' ' in normalized]
    # Prefer longest match; retain ambiguity for two distinct series.
    matches = [n for n in matches if not any(normalize(n) != normalize(other) and normalize(n) in normalize(other) for other in matches)]
    if len(matches) == 1:
        n = matches[0]
        # Don't label a new unnamed show as its creators' previous show.
        if not (re.search(r'makers|team achter', title, re.I) and re.search(r'nieuwe .{0,40}serie', title, re.I)):
            name = n
    if len(matches) > 1:
        name = ''
    rejected = noise_reason(a)
    if re.search(r'\b(?:Britse|Amerikaanse|Duitse|Deense|Zweedse|Spaanse|buitenlandse)\b.{0,30}serie', title, re.I):
        rejected = 'Buitenlandse serie; geen Nederlandse productie vastgesteld'
    nl = bool(re.search(r'\b(?:Nederlandse?|Nederlanders|Nederlandstalige|Videoland|AVROTROS|NPO|Talpa|SBS6|BNNVARA|KRO.NCRV|PowNed|VPRO|EO)\b', text, re.I))
    nl = nl or a['source'] in ('avrotros-direct','avrotros','npo')
    if not nl and not rejected:
        rejected = 'Nederlandse productie nog niet vastgesteld'
    # A reviewed row explicitly overrides extraction; older reviews preserve name/notes.
    if a.get('classification_reviewed'):
        name = a.get('series_title','').strip()
        kind = a.get('production_kind','Onbekend')
        season = a.get('season_number')
        phase = ALIASES_PHASE.get(a['phase'], a['phase'])
        rejected = ''
        evidence = 'Handmatig beoordeeld'
    elif a.get('reviewed') and a.get('series_title'):
        name = a['series_title']
        phase = ALIASES_PHASE.get(a['phase'], a['phase'])
        evidence = 'Eerder handmatig beoordeeld'
    if name:
        name = known.get(normalize(name), name)
    if a.get('excluded'):
        rejected = 'Handmatig genegeerd'
    update = phase != 'Onbekend' or bool(re.search(r'nieuw(?:e)?|eerste beelden|trailer|teaser|cast|figuranten|opnames|reboot|verlengd', title, re.I))
    release_hint = ''
    m = re.search(r'(?:vanaf|verschijnt|release(?:datum)?|start(?:datum)?|première|zaterdag|zondag|maandag|dinsdag|woensdag|donderdag|vrijdag)\b.{0,50}(?:\d{1,2}\s+(?:' + MONTHS + r')|20\d\d)', text, re.I)
    if m: release_hint = m.group(0)
    return {**a,'name':name,'kind':kind,'season':season,'status':phase,'evidence':evidence,'release_hint':release_hint,'rejection':rejected,'is_update':update,'issue': 'Meerdere series genoemd' if len(matches)>1 else 'Serietitel ontbreekt' if not name else 'Nieuwe serie of seizoen nog niet vastgesteld' if kind=='Onbekend' else 'Geen duidelijk nieuws over een nieuwe productie' if not update else ''}

def catalog(rows):
    known = {}
    for a in rows:
        name = a.get('series_title') or extract_name(a)
        if name: known.setdefault(normalize(name), name)
    for a in rows:
        if a.get('classification_reviewed') and a.get('series_title'):
            known[normalize(a['series_title'])] = a['series_title']
    assessed = [assess(a, known) for a in rows]
    # An unnumbered availability update can describe the sole first-season dossier.
    # Never carry it across several seasons or override a manual classification.
    for a in assessed:
        if a['status']!='Beschikbaar' or a['kind']!='Onbekend' or a.get('classification_reviewed') or season_of(a.get('summary','')):continue
        siblings=[b for b in assessed if b['name']==a['name'] and b['kind']!='Onbekend' and not b['rejection']]
        if siblings and all(b['kind']=='Nieuwe serie' for b in siblings):
            a['kind']='Nieuwe serie';a['season']=1
    # Domestic context established in one article also applies to the same exact title.
    domestic = {normalize(a['name']) for a in assessed if a['name'] and not a['rejection']}
    for a in assessed:
        if a['rejection']=='Nederlandse productie nog niet vastgesteld' and normalize(a['name']) in domestic:
            a['rejection']=''
    groups, inbox, ignored = {}, [], []
    # A series only enters the main catalog with a specific new-series/season signal.
    eligible_names = {normalize(a['name']) for a in assessed if a['name'] and a['kind']!='Onbekend' and not a['rejection'] and a['is_update']}
    eligible_names.update(normalize(a['name']) for a in assessed if a.get('classification_reviewed') and a['name'] and a['kind']!='Onbekend' and not a['rejection'])
    for a in assessed:
        if a['rejection']:
            ignored.append(a)
            continue
        key = normalize(a['name'])
        if key not in eligible_names:
            inbox.append(a)
            continue
        group = groups.setdefault(key, {'id':hashlib.sha256(key.encode()).hexdigest()[:20], 'name':known.get(key,a['name']), 'articles':[], 'productions':[]})
        group['articles'].append(a)
    for group in groups.values():
        # Compare publication dates, never crawler arrival order. Unknown date is oldest.
        group['articles'].sort(key=lambda a:(a.get('published') or '',a['discovered']), reverse=True)
        buckets = {}
        for a in group['articles']:
            bucket = (a['kind'], 1 if a['kind']=='Nieuwe serie' else a['season'])
            buckets.setdefault(bucket, []).append(a)
        for (kind,season), articles in buckets.items():
            explicit = [a for a in articles if a['status']!='Onbekend']
            # Announcing the same season again cannot undo completed filming.
            # A manual assessment or explicit cancellation takes precedence when newer.
            latest = max(explicit, key=lambda a:(PHASES.index(a['status']), a.get('published') or '')) if explicit else articles[0]
            overrides = [a for a in articles if a.get('classification_reviewed') or re.search(r'gaat niet door|geannuleerd|stopgezet|uitgesteld', a['evidence'], re.I)]
            if overrides and (overrides[0].get('published') or '') >= (latest.get('published') or ''):
                latest = overrides[0]
            group['productions'].append({'kind':kind,'season':season,'status':latest['status'],'status_article':latest['id'],'evidence':latest['evidence'],'reviewed':bool(latest.get('classification_reviewed')), 'release_hint':next((a['release_hint'] for a in articles if a['release_hint']),''),'articles': [a['id'] for a in articles], 'tvdb':all(a['tvdb'] for a in articles), 'updated':articles[0].get('published') or articles[0]['discovered']})
        group['updated'] = max(a.get('published') or a['discovered'] for a in group['articles'])
        group['productions'].sort(key=lambda p:(p['kind']=='Onbekend', -(p['season'] or 0)))
    return {'series':sorted(groups.values(),key=lambda g:g['updated'],reverse=True), 'inbox':inbox, 'ignored':ignored}
