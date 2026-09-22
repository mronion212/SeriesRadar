"""Conservative, explainable series extraction. Unknowns go to an inbox."""
import hashlib
import re
import unicodedata

PHASES = ['Onbekend', 'Aangekondigd', 'Release gepland', 'In productie', 'Geproduceerd', 'Beschikbaar']
KINDS = ['Onbekend', 'Nieuwe serie', 'Nieuw seizoen']
MONTHS = 'januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december'
SERIES_WORD = r'(?:[a-zà-ÿ]*serie|sitcom|[a-zà-ÿ-]*show|quiz|partygame|[a-zà-ÿ-]*programma|reality[- ]?(?:programma|show|hit|serie)|dating[- ]?experiment|talentenjacht|documentaire)\b'
ORDINALS = {'eerste':1,'tweede':2,'derde':3,'vierde':4,'vijfde':5,'zesde':6,'zevende':7,'achtste':8,'negende':9,'tiende':10,'elfde':11,'twaalfde':12}
ALIASES_PHASE = {'Te beoordelen':'Onbekend','Gereleased':'Beschikbaar'}
NON_TITLES = set(ORDINALS) | {'nu','nieuw','nieuwe','seizoen','serie','in productie','aangekondigd',
    'npo','rtl','sbs6','net5','videoland','netflix','max','kijk','vpro','eo','powned','kro ncrv','bnnvara','avrotros'}

def normalize(value):
    # A.S.S. – Anti Survival Show and Anti Survival Show denote the same title.
    # Only discard initials when the remaining words spell out those initials.
    prefix=re.match(r'^((?:[A-Z]\.\s*){2,})\s*[–—-]?\s*(.+)$',value)
    if prefix and ''.join(re.findall(r'[A-Z]',prefix.group(1))).casefold()==''.join(w[0] for w in prefix.group(2).split()).casefold():
        value=prefix.group(2)
    value = unicodedata.normalize('NFKD', value.casefold())
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()

def headline(a):
    text = a['title']
    if a.get('publisher'):
        text = text.removesuffix(' - ' + a['publisher'])
    return text.strip()


def story_body(a):
    """Publisher attribution and a repeated feed headline are not title evidence."""
    title=normalize(headline(a));publisher=a.get('publisher','').strip()
    lines=[]
    for line in a.get('summary','').splitlines():
        if publisher:
            line=re.sub(r'(?:\s+-)?\s+'+re.escape(publisher)+r'\s*$', '',line,flags=re.I)
        if normalize(line)!=title:lines.append(line)
    return '\n'.join(lines)


def valid_name(value, publisher=''):
    key=normalize(value)
    return (bool(key) and key not in NON_TITLES and key!=normalize(publisher)
            and not re.search(r'\b\w+\.(?:nl|be|com|org)\b',value,re.I))


def phase_of(text):
    aired = re.search(r'\bwerd uitgezonden (?:op|door)\b[^\n.]{0,100}',text,re.I)
    if aired and not re.search(r'gaat niet door|geannuleerd|stopgezet',text,re.I):
        return 'Beschikbaar', aired.group(0)
    rules = [
        ('Onbekend', r'gaat niet door|geannuleerd|stopgezet|opnames?\b.{0,50}uitgesteld'),
        ('Beschikbaar', r'vanaf vandaag (?:te zien|te streamen|beschikbaar)|(?:nu|inmiddels|al) (?:volledig )?te (?:zien|streamen)|nu beschikbaar|is (?:nu )?(?:verschenen|uitgebracht)|vandaag (?:te zien|te streamen)|sinds\b.{0,100}?(?:op|bij) (?:Videoland|Netflix|NPO|Prime Video)|in zijn geheel te streamen|is te (?:zien|streamen) (?:op|bij|via) (?:\(o\.a\.\) )?(?:Prime Video|Videoland|Netflix|NPO|Net5|SBS6|NLZIET|Streamz)|kijk .{0,80} terug (?:op|bij|via) NLZIET'),
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

def season_numbers(text):
    numbers = {int(n) for n in re.findall(r'\bseizoen\s+(\d{1,2})\b', text, re.I)}
    numbers.update(int(n) for n in re.findall(r'\b(\d{1,2})(?:e|de|ste)\s+seizoen\b', text, re.I))
    numbers.update(ORDINALS[n.lower()] for n in re.findall(r'\b(' + '|'.join(ORDINALS) + r')(?: en laatste)? seizoen\b', text, re.I))
    return numbers


def season_of(text):
    numbers = season_numbers(text)
    return next(iter(numbers)) if len(numbers)==1 and 0 not in numbers else None


def production_context(title, summary, season):
    """Keep explicit references to other seasons out of this production's status."""
    parts = [title]
    for sentence in re.split(r'(?<=[.!?])\s+|\n|;\s*|\s+(?:maar|terwijl)\s+', summary):
        mentioned = season_of(sentence)
        if mentioned is not None and mentioned != season:
            continue
        # With several seasons in one clause there is no safe status attribution.
        if len(season_numbers(sentence)) > 1:
            continue
        parts.append(sentence)
    return '\n'.join(parts)

def kind_of(text, season):
    if season and season > 1:
        return 'Nieuw seizoen'
    if re.search(r'\bnieuw(?:e)? seizoen|vervolgseizoen|verlengd|krijgt .{0,25}seizoen', text, re.I):
        return 'Nieuw seizoen' if season != 1 else 'Nieuwe serie'
    if re.search(r'\b(?:gloed)?nieuwe?\b.{0,55}' + SERIES_WORD, text, re.I) or season == 1:
        return 'Nieuwe serie'
    if re.search(SERIES_WORD, text, re.I) and re.search(r'binnenkort te zien|komt naar televisie|maakt .{0,20}debuut', text, re.I):
        return 'Nieuwe serie'
    return 'Onbekend'

def tidy_name(value):
    # Question-shaped programme titles may contain lowercase prepositions.
    question = re.match(r'^((?:Wil|Kan|Kun|Wie|Wat|Waar|Hoe)\b[^?]{2,80}\?)', value.strip(), re.I)
    if question:
        return question.group(1).strip()
    value = value.strip(' \"\'‘’“”.,:;!?')
    value = re.sub(r'^(?:de|het)\s+(?=[A-ZÀ-Ý])','',value)
    value=re.split(r':\s*(?=[a-zà-ÿ‘’\'“\"])|\s+(?:uitgesteld|wagen|verruilen)\b',value,maxsplit=1)[0]
    value = re.split(r'\s+(?:aangekondigd|gestart|afgerond|binnenkort|van start|in de maak|in duistere|naar het boek|en nóg|en nog|over|met|bij|op|vanaf|in 20\d\d|seizoen|komt|krijgt|keert|toont|vertelt|overtreft|draait|duikt|speelt|spelen|start|starten|staat|staan|gaat|gaan|volgt|volgen|laat|wordt|is|te zien|te streamen|bekend|onthuld)\b|\s+(?:voor|van)\s+(?:Videoland|Netflix|RTL|SBS6|NPO|NET5)\b|,(?!\s+[A-ZÀ-Ý])|[!?]|(?<![A-Z])\.\s+(?=[A-Z])|\s+-\s+|\s*\(\d{4}', value, maxsplit=1)[0]
    value=re.sub(r'-serie$','',value,flags=re.I)
    value = value.strip(' \"\'‘’“”.,:;!?')
    if not 2 <= len(value) <= 85 or len(value.split()) > 12:
        return ''
    if not valid_name(value) or re.fullmatch(r'\d+(?:e|de|ste)?',value,re.I):
        return ''
    if not value[0].isupper() or re.match(r'^(?:De|Het|Een)?\s*(?:nieuwe|Nederlandse|Netflix|Videoland|NPO|SBS6|NET5|MAX|KIJK|VPRO|RTL|Original|over|aan|met|van|dit|deze)\b', value, re.I):
        return ''
    return value.title() if value.isupper() else value

def extract_name(a, include_body=True):
    """Require a title-shaped phrase immediately after a series noun."""
    text = headline(a)
    body=story_body(a)
    publisher=a.get('publisher','')
    quoted = re.search(r'\b' + SERIES_WORD + r'\s*:?\s+[‘’\'“\"]([^‘’\'“\"]{2,85})[‘’\'“\"]', text, re.I)
    review_quote=bool(quoted and ':' in quoted.group(0) and (
        re.search(r'overtreft|reacties|recensie|fans|kijkers',text[:quoted.start()],re.I)
        or re.search(r'\b(?:is|zijn|was|heeft|hebben|ben|bent)\b',quoted.group(1),re.I)))
    if quoted and quoted.group(1)[0].isupper() and valid_name(quoted.group(1),publisher) and not review_quote:
        return quoted.group(1).strip()
    patterns = [
        r'\b' + SERIES_WORD + r'\s+[‘’\'“\"]([^‘’\'“\"]{2,85})[‘’\'“\"]',
        r'\b' + SERIES_WORD + r'\s+(.+)$',
        r'^([^:]{2,85}):\s*(?:een |de |nieuwe |indringende ).*' + SERIES_WORD,
        r'\bnieuwe?\s+([A-ZÀ-Ý][\wÀ-ÿ]*(?:\s+(?:[A-ZÀ-Ý][\wÀ-ÿ]*|de|het|van|en)){0,6})-serie\b',
        r'\bseizoen\s+(?:\d{1,2}\s+)?(?:van\s+)?[‘’\'“\"]([^‘’\'“\"]+)[‘’\'“\"]',
        r'[‘’\'“\"]([^‘’\'“\"]+)[‘’\'“\"]\s+seizoen\s+\d',
        r'\b(?:nieuw(?:e)?|eerste|tweede|derde|vierde|vijfde) seizoen\s+(?:van\s+)?([^:]+)$',
        r'\b(?:'+ '|'.join(ORDINALS)+r'|\d+) seizoen van (.+)$',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I if 'A-Z' not in pattern else 0)
        if m:
            # Preserve a longer name containing e.g. "op" or "met" only when
            # the body repeats it. A headline alone is insufficient evidence.
            full = re.split(r'\s+(?:aangekondigd|krijgt|keert|wordt|is|vanaf|binnenkort)\b', m.group(1), maxsplit=1, flags=re.I)[0].strip(' \"\'‘’“”.,:;!?')
            if (2 <= len(full) <= 85 and full[0].isupper()
                    and re.search(r'\s+(?:op|met|over)\s+', full, re.I)
                    and not re.search(r'\b(?:op|bij|met)\s+(?:Videoland|Netflix|NPO|RTL|SBS6|Net5|Prime Video|Disney|HBO|de hoofdrol|bekende acteurs)\b', full, re.I)
                    and ' '+normalize(full)+' ' in ' '+normalize(body)+' '
                    and not re.search(r'\b(?:bij|voor|van)\s+(?:BNNVARA|RTL|SBS6|Videoland|Netflix|NPO)\b',full,re.I)
                    and tidy_name(full)):
                return full
            candidate = tidy_name(m.group(1))
            if re.search(r'\bkondigt\b',text,re.I):candidate=re.sub(r' aan$','',candidate)
            if re.search(r'\btrapt\b',text,re.I):candidate=re.sub(r' af$','',candidate)
            # A quoted adjective or a creator's other series is not a title.
            if candidate and valid_name(candidate,publisher) and not re.search(r'makers|producent|regisseur', text[m.end():m.end()+15], re.I):
                return candidate
    # Programme pages often have only the title as their h1. Require that the
    # article itself explicitly calls this exact heading a programme or series.
    candidate=tidy_name(text)
    if candidate and normalize(candidate)==normalize(text):
        if re.search(SERIES_WORD+r'\s+[‘’\'“\"]?'+re.escape(candidate)+r'(?!\w)',a.get('summary',''),re.I):return candidate
    if include_body:
        candidates={}
        for line in body.splitlines()[:40]:
            if line.strip()==text:continue
            # Only explicit programme naming in prose, not arbitrary capitalized words.
            if not re.search(SERIES_WORD+r'\s+[‘’\'“\"]?[A-ZÀ-Ý]|seizoen van [A-ZÀ-Ý]',line):continue
            found=extract_name({'title':line,'summary':'','publisher':publisher},include_body=False)
            if found:candidates[normalize(found)]=found
        # "Guy Ritchie's The Gentlemen" is an attribution when another sentence
        # independently names "The Gentlemen". Never strip possessives blindly
        # (e.g. Grey's Anatomy is itself a title).
        candidates={k:n for k,n in candidates.items() if not any(
            other!=k and k.endswith(' '+other) and re.search(r"[’']s\s+",n)
            for other in candidates)}
        named_in_headline=[n for k,n in candidates.items() if ' '+k+' ' in ' '+normalize(text)+' ']
        if len(named_in_headline)==1:return named_in_headline[0]
        if len(candidates)==1:return next(iter(candidates.values()))
    return ''

def noise_reason(a):
    text = headline(a)
    if re.search(r'recensie|kijktips|top\s*\d|best(?:e| bekeken)|meest bekeken|films en series|premièredatums|(?:deze|zes) misdaadseries|internationale topseries|archief|kijkcijfer|schiet .{0,30}door het dak|podcast|theaterseizoen|concert|culturele seizoen|wereldtitel|eredivisie|\bserie [ab]\b|voetballer|\bPSV\b|\bAjax\b', text, re.I):
        return 'Kijktip, recensie, algemeen overzicht of ander nieuws'
    return ''

def assess(a, known):
    title = headline(a)
    # Search snippets frequently just repeat the headline. Limit context to stored fragment.
    text = title + '\n' + a.get('summary','')
    season = season_of(title)
    kind = kind_of(title, season)
    name = extract_name(a)
    normalized=' '+normalize(title)+' '
    # A one-word title is not evidence when it appears as an ordinary lowercase
    # word elsewhere in a headline (e.g. Nu, Love, Harmony).
    capitals={normalize(t) for t in re.findall(r'\w+',title) if t[0].isupper()}
    matches = [v for k,v in known.items() if (k in capitals if ' ' not in k else ' '+k+' ' in normalized)]
    matches = [v for v in matches if not re.match(r'^(?:Volledige\s+)?'+re.escape(v)+r'\s+van\b',title,re.I)]
    # Prefer longest match; retain ambiguity for two distinct series.
    matches = [n for n in matches if not any(normalize(n) != normalize(other) and normalize(n) in normalize(other) for other in matches)]
    if len(matches) == 1 and (not name or normalize(name)==normalize(matches[0]) or normalize(matches[0]).startswith(normalize(name)+' ')):
        n = matches[0]
        # Don't label a new unnamed show as its creators' previous show.
        if not (re.search(r'makers|team achter', title, re.I) and re.search(r'nieuwe .{0,40}serie', title, re.I)):
            name = n
    if len(matches) > 1 and not name:
        name = ''
    if name and (kind=='Onbekend' or season is None) and not re.search(r'makers|team achter',title,re.I):
        # Use only a sentence naming this title, never a sidebar's other show.
        for sentence in re.split(r'(?<=[!?])\s+|(?<=[.])\s+(?=[A-ZÀ-Ý])|\n',a.get('summary','')):
            if ' '+normalize(name)+' ' not in ' '+normalize(sentence)+' ':continue
            candidate_season=season_of(sentence)
            candidate_kind=kind_of(sentence,candidate_season)
            if candidate_kind!='Onbekend':
                if kind!='Onbekend' and candidate_kind!=kind:continue
                kind=candidate_kind;season=candidate_season;break
    phase, evidence = phase_of(production_context(title, a.get('summary',''), season or (1 if kind=='Nieuwe serie' else None)))
    rejected = noise_reason(a)
    if re.search(r'\b(?:Britse|Amerikaanse|Duitse|Deense|Zweedse|Spaanse|buitenlandse)\b.{0,30}serie', title, re.I):
        rejected = 'Buitenlandse serie; geen Nederlandse productie vastgesteld'
    nl = bool(re.search(r'\b(?:Nederland(?:s|se|ers)?|Nederlandstalige|Videoland|AVROTROS|NPO|Talpa|SBS6|Net5|BNNVARA|KRO.NCRV|PowNed|VPRO|EO)\b', text, re.I))
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
    publishers={normalize(a.get('publisher','')) for a in rows}
    for a in rows:
        manual=a.get('series_title') if a.get('classification_reviewed') or a.get('reviewed') else ''
        name = manual or extract_name(a)
        if name and (manual or (valid_name(name) and normalize(name) not in publishers)):
            known.setdefault(normalize(name), name)
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
    eligible_names = {normalize(a['name']) for a in assessed if a['name'] and (a['kind']!='Onbekend' or a['status'] in ('Beschikbaar','Release gepland')) and not a['rejection'] and a['is_update']}
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
