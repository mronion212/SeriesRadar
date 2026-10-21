"""Run separately: opens a temporary local HTTP server, uses a disposable DB."""
import base64
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'ADMIN_USER':'test','ADMIN_PASSWORD':'integration-only'}):
    app.DB=Path(directory)/'test.sqlite3'
    app.init()
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    address='http://127.0.0.1:'+str(server.server_port)
    authorization='Basic '+base64.b64encode(b'test:integration-only').decode()
    def call(path,data=None,auth=True,csrf=True):
        headers={'Authorization':authorization} if auth else {}
        if data is not None:
            headers['Content-Type']='application/json'
            if csrf: headers['X-Radar-Request']='1'
        req=Request(address+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urlopen(req) as response:
                return response.status,json.loads(response.read())
        except HTTPError as exc:
            return exc.code,None
    try:
        assert call('/api/dashboard',auth=False)[0]==200
        initial_status=call('/api/status',auth=False)[1]
        assert isinstance(initial_status['revision'],int)
        assert call('/api/admin/dashboard',auth=False)[0]==401
        for endpoint in ('/api/admin/dashboard?summary=1','/api/admin/status','/api/admin/review','/api/admin/series/missing'):
            assert call(endpoint,auth=False)[0]==401
        assert call('/api/series/missing',auth=False)[0]==404
        assert call('/admin',auth=False)[0]==401
        for endpoint in ('/api/dossier/enrich','/api/dossier/research-package','/api/dossier/research-import','/api/ai/settings','/api/dossier/research','/api/scan','/api/article','/api/dossier','/api/dossier/import','/api/dossier/check-tvdb','/api/source','/api/source/test'):
            assert call(endpoint,{},auth=False)[0]==401
        assert call('/health',auth=False)[0]==200
        assert call('/api/scan',{},csrf=False)[0]==403
        assert call('/api/ai/settings',{'api_key':'sk-test-key-not-a-real-secret'},csrf=False)[0]==403
        assert call('/api/ai/settings',{'api_key':'sk-test-key-not-a-real-secret'})[0]==200
        assert call('/api/admin/dashboard')[1]['ai']['configured'] is True
        assert 'sk-test-key-not-a-real-secret' not in json.dumps(call('/api/admin/dashboard')[1])
        assert 'sk-test-key-not-a-real-secret' not in json.dumps(call('/api/dashboard',auth=False)[1])
        assert call('/api/article',{})[0]==400
        source={'name':'Integration feed','mode':'search','value':'"Nederlandse serie" when:90d','enabled':False}
        status,result=call('/api/source',source)
        assert status==200
        saved=next(s for s in call('/api/admin/dashboard')[1]['sources'] if s['id']==result['id'])
        assert saved['enabled'] is False
        with app.connect() as c:
            app.ingest(c,{'id':'test','name':'Test'},[{'title':"Nieuwe Nederlandse serie 'Teststad' aangekondigd",'url':'https://example.org/test','summary':'','published':None,'publisher':'Test'}])
        assert call('/api/status',auth=False)[1]['revision']>initial_status['revision']
        with urlopen(Request(address+'/api/dashboard',headers={'Accept-Encoding':'gzip'})) as response:
            assert response.headers['Content-Encoding']=='gzip'
            assert 'series' in json.loads(gzip.decompress(response.read()))
        group=call('/api/admin/dashboard')[1]['series'][0]
        compact=call('/api/admin/dashboard?summary=1')[1]
        assert 'articles' not in compact['series'][0]
        assert compact['series'][0]['article_count']==len(group['articles'])
        assert compact['inbox']==compact['ignored']==[] and 'counts' in compact
        detail_path='/api/series/'+group['id']
        admin_detail_path='/api/admin/series/'+group['id']
        assert call(admin_detail_path,auth=False)[0]==401
        assert call(admin_detail_path)[1]==group
        row=group['articles'][0]
        profile=group['dossiers'][0]
        update={'series_id':group['id'],'scope':profile['scope'],'revision':profile['revision'],'fields':{'notes':{'value':'Private dossier note'},'cast':{'value':'Anna de Vries | Noor','source_url':'https://example.org/test','evidence':'Cast credits'}}}
        assert call('/api/dossier',update)[0]==200
        assert call('/api/dossier',update)[0]==409
        public=call('/api/dashboard',auth=False)[1]
        assert public['inbox']==[] and public['ignored']==[] and public['sources']==[]
        assert 'notes' not in public['series'][0]['articles'][0]
        assert 'Private dossier note' not in json.dumps(public)
        compact=call('/api/dashboard?summary=1',auth=False)[1]
        assert 'articles' not in compact['series'][0]
        assert 'Private dossier note' not in json.dumps(compact)
        assert 'notes' not in [f['key'] for f in compact['dossier_fields']]
        public_detail=call(detail_path,auth=False)[1]
        assert public_detail==public['series'][0]
        assert 'Private dossier note' not in json.dumps(public_detail)
        assert call(admin_detail_path)[1]['dossiers'][0]['fields']['notes']['value']=='Private dossier note'
        content_revision=call('/api/status',auth=False)[1]['revision']
        detail_revision=call('/api/status',auth=False)[1]['detail_revision']
        app.record_check('article:'+row['id'])
        assert call('/api/status',auth=False)[1]['revision']==content_revision
        assert call('/api/status',auth=False)[1]['detail_revision']>detail_revision
        first=call('/api/dashboard',auth=False)[1]['series'][0]['articles'][0]['retrieval']['last_success']
        app.record_check('article:'+row['id'],'temporary failure')
        retrieval=call('/api/dashboard',auth=False)[1]['series'][0]['articles'][0]['retrieval']
        assert retrieval['last_success']==first and retrieval['status']=='failed'
        with patch.object(app.ai_research,'research',return_value=({'cast':{'value':'AI cast','source_url':'https://example.org/test','evidence':'Cast','origin':'ai'},'episodes':{'value':'8','source_url':'https://example.org/test','evidence':'Acht afleveringen','origin':'ai'}},0)):
            assert call('/api/dossier/research',{'series_id':group['id'],'scope':profile['scope']})[0]==202
            for _ in range(100):
                if not app.AI_LOCK.locked():break
                time.sleep(.02)
            assert not app.AI_LOCK.locked()
        researched=call('/api/dashboard',auth=False)[1]['series'][0]['dossiers'][0]['fields']
        assert researched['cast']['value']=='Anna de Vries | Noor'
        assert researched['episodes']['value']=='8' and researched['episodes']['origin']=='ai'
        target={'series_id':group['id'],'scope':profile['scope']}
        assert call('/api/dossier/enrich',target,csrf=False)[0]==403
        with patch.object(app,'enrich_tvmaze'),patch.object(app,'discover_metadata') as discover,patch.object(app,'enrich_articles') as enrich:
            assert call('/api/dossier/enrich',target)[0]==202
            for _ in range(100):
                if not app.LOCK.locked():break
                time.sleep(.02)
            assert not app.LOCK.locked()
            discover.assert_called_once()
            enrich.assert_called_once()
        assert 'metadata_discovery' not in call('/api/dashboard',auth=False)[1]['series'][0]
        packet=call('/api/dossier/research-package',target)[1]
        assert packet['title']=='Teststad' and 'Private dossier note' not in packet['prompt']
        assert packet['schema_version']==2 and packet['dossier_revision']==1
        configured=call('/api/dossier/research-package',{**target,'options':{'mode':'all','target':'imdb','brief':'Controleer de rollen.'}})[1]
        assert configured['target']=='imdb' and 'Controleer de rollen.' in configured['prompt']
        assert call('/api/dossier/research-package',{**target,'options':{'mode':'wrong'}})[0]==400
        assert call('/api/dossier/research-import',{**target,'title':'Teststad','schema_version':2,'dossier_revision':0,'facts':[]})[0]==409
        assert call('/api/dossier/research-package',target,csrf=False)[0]==403
        external={**target,'title':'Teststad','schema_version':2,'dossier_revision':1,'facts':[{'field':'episodes','value':'8','source_url':'https://example.org/test','evidence':'Teststad heeft acht afleveringen.'}]}
        assert call('/api/dossier/research-import',{**external,'title':'Andere serie'})[0]==400
        assert call('/api/dossier/research-import',{**external,'scope':'season:99'})[0]==400
        assert call('/api/dossier/research-import',{**external,'facts':{}})[0]==400
        assert call('/api/dossier/research-import',external,csrf=False)[0]==403
        with patch.object(app,'ai_key',return_value=''),patch.object(app.ai_research,'research') as paid,patch.object(app,'read_article_page',return_value='Teststad heeft acht afleveringen.'):
            assert call('/api/dossier/research-import',external)[0]==202
            for _ in range(100):
                if not app.AI_LOCK.locked():break
                time.sleep(.02)
            assert not app.AI_LOCK.locked()
            paid.assert_not_called()
        fields=call('/api/dashboard',auth=False)[1]['series'][0]['dossiers'][0]['fields']
        assert fields['episodes']['value']=='8' and fields['episodes']['origin']=='external_ai'
        report=call('/api/dossier/research-package',target)[1]['research_status']['report']
        assert report[0]['code']=='confirmed' and report[0]['field']=='episodes'
        mixed={**external,'facts':[{'field':'unknown','value':'bad'},external['facts'][0]]}
        raw='Hier is het resultaat:\n```json\n'+json.dumps(mixed)+'\n```'
        assert call('/api/dossier/research-import',{**target,'raw':json.dumps({**external,'scope':'season:2'})})[0]==400
        with patch.object(app,'read_article_page',return_value='Teststad heeft acht afleveringen.'):
            assert call('/api/dossier/research-import',{**target,'raw':raw})[0]==202
            for _ in range(100):
                if not app.AI_LOCK.locked():break
                time.sleep(.02)
            assert not app.AI_LOCK.locked()
        report=call('/api/dossier/research-package',target)[1]['research_status']['report']
        assert [r['code'] for r in report]==['invalid','confirmed']
        conflicting={**external,'facts':[{'field':'episodes','value':'10','source_url':'https://example.org/test','evidence':'Teststad heeft tien afleveringen.'}],
                     'unanswered':[{'field':'runtime','reason':'Geen bron gevonden.'}]}
        with patch.object(app,'read_article_page',return_value='Teststad heeft tien afleveringen.'):
            assert call('/api/dossier/research-import',conflicting)[0]==202
            for _ in range(100):
                if not app.AI_LOCK.locked():break
                time.sleep(.02)
        report=call('/api/dossier/research-package',target)[1]['research_status']['report']
        assert [r['code'] for r in report]==['existing_conflict','not_found']
        assert call(detail_path,auth=False)[1]['dossiers'][0]['fields']['episodes']['value']=='8'
        assert 'ai_runs' not in call('/api/dashboard',auth=False)[1]['series'][0]
        assert fields['cast']['value']=='Anna de Vries | Noor'
        with patch.dict(os.environ,{'ADMIN_PASSWORD':''}):
            assert call('/api/dashboard',auth=False)[0]==200
            assert call('/api/admin/dashboard',auth=False)[0]==503
            assert call('/api/scan',{},auth=False)[0]==503
        app.init()
        dossier=call('/api/admin/dashboard')[1]['series'][0]['dossiers'][0]
        assert dossier['fields']['cast']['value']=='Anna de Vries | Noor'
        assert dossier['fields']['cast']['origin']=='manual'
        data={'id':row['id'],'series_title':'Teststad','production_kind':'Nieuw seizoen','season_number':2,'phase':'In productie','notes':'Persisted note','tvdb':0,'excluded':0}
        assert call('/api/article',data)[0]==200
        updated=call('/api/admin/dashboard')[1]['series'][0]
        assert updated['productions'][0]['season']==2
        assert updated['productions'][0]['status']=='In productie'
        data['excluded']=1
        assert call('/api/article',data)[0]==200
        assert not call('/api/admin/dashboard')[1]['series']
        assert call('/api/admin/dashboard')[1]['ignored'][0]['notes']=='Persisted note'
        review=call('/api/admin/review')[1]
        assert review['ignored'][0]['notes']=='Persisted note'
        compact=call('/api/admin/dashboard?summary=1')[1]
        assert compact['counts']['ignored']==len(review['ignored']) and compact['ignored']==[]
        assert call(detail_path,auth=False)[0]==404
        print('HTTP integration OK: login, CSRF, sources, grouping, review, ignore, persistence')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
