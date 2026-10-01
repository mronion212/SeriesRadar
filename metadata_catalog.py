"""Conservative TVmaze catalogue matching and season-scoped metadata."""
import re
from html import unescape
from catalog import normalize
import dossier

LICENSE='https://creativecommons.org/licenses/by-sa/4.0/'


def match(results,name,known_ids=None):
    candidates=[]
    for result in results:
        show=result.get('show',{})
        if normalize(show.get('name',''))!=normalize(name) or show.get('language')!='Dutch':continue
        if type(show.get('id')) is not int or show['id']<=0:continue
        external=show.get('externals') or {}
        if any(str(external.get(k) or '')!=str(v) for k,v in (known_ids or {}).items() if v):continue
        candidates.append(show)
    if len(candidates)!=1:raise ValueError('Geen unieke TVmaze-serie met dezelfde titel en originele taal Nederlands bevestigd.')
    return candidates[0]


def facts_for(show,name,scope):
    if normalize(show.get('name',''))!=normalize(name) or show.get('language')!='Dutch':
        raise ValueError('TVmaze-titel of originele taal komt niet overeen.')
    source=show.get('url','')
    facts={}
    def add(key,value,evidence):
        if value is None or value=='':return
        try:validated=dossier.validate_fields({key:{'value':str(value),'source_url':source,'evidence':'TVmaze: '+evidence[:550]}})[key]
        except ValueError:return
        facts[key]={**validated,'origin':'tvmaze','license_url':LICENSE}
    add('languages',show.get('language'),'original language')
    add('format',show.get('type'),'show type')
    add('genres','\n'.join(show.get('genres') or []),'genres')
    # A channel's country does not establish the production country.
    network=show.get('network') or {};platform=show.get('webChannel') or {}
    add('networks',network.get('name'),'network')
    add('platforms',platform.get('name'),'web channel')
    add('official_url',show.get('officialSite'),'official site')
    external=show.get('externals') or {}
    add('imdb_id',external.get('imdb'),'external IMDb ID')
    add('tvdb_id',external.get('thetvdb'),'external TheTVDB ID')
    embedded=show.get('_embedded') or {}
    seasons=embedded.get('seasons') or []
    number=scope.split(':')[-1]
    number=int(number) if number.isdigit() else None
    season=next((s for s in seasons if s.get('number')==number),None) if number is not None else None
    if season:
        start=season.get('premiereDate')
        if start and re.fullmatch(r'\d{4}-\d{2}-\d{2}',start):
            add('release_date',start,f'season {number} premiere date')
            add('release_year',start[:4],f'season {number} premiere year')
        order=season.get('episodeOrder')
        if type(order) is int and order>0:add('episodes',order,f'season {number} explicit episode order')
        episodes=[e for e in embedded.get('episodes',[]) if e.get('season')==number and type(e.get('number')) is int]
        runtime=sorted({e['runtime'] for e in episodes if type(e.get('runtime')) is int and e['runtime']>0})
        if runtime:add('runtime',str(runtime[0])+('–'+str(runtime[-1]) if len(runtime)>1 else '')+' minuten',f'season {number} listed episode runtimes')
        lines=[]
        for episode in episodes:
            line=f"{episode['number']} | {episode.get('name') or 'Titel onbekend'} | {episode.get('airdate') or 'Datum onbekend'}"
            if sum(len(v)+1 for v in lines)+len(line)>5900:
                lines.append('Meer afleveringen: zie TVmaze-bron.');break
            lines.append(line)
        add('episode_guide','\n'.join(lines),f'season {number} listed episodes; listing does not prove a final total')
    # TVmaze main cast and synopsis describe the entire show, not a specific
    # season. Only use them when exactly one known season matches this dossier.
    if season and len(seasons)==1:
        synopsis=re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',show.get('summary') or ''))).strip()
        add('synopsis',synopsis,'show synopsis (source text; rewrite before submission)')
        cast=[]
        for credit in embedded.get('cast',[]):
            person=(credit.get('person') or {}).get('name')
            character=(credit.get('character') or {}).get('name')
            if person:cast.append(person+(' | '+character if character else ''))
        add('cast','\n'.join(dict.fromkeys(cast)),f'main cast; only known season is {number}')
    return facts
