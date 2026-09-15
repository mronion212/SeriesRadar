"""Run separately: opens a temporary local HTTP server, uses a disposable DB."""
import base64
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
        assert call('/api/admin/dashboard',auth=False)[0]==401
        assert call('/admin',auth=False)[0]==401
        for endpoint in ('/api/dossier/research-package','/api/dossier/research-import','/api/ai/settings','/api/dossier/research','/api/scan','/api/article','/api/dossier','/api/dossier/import','/api/dossier/check-tvdb','/api/source','/api/source/test'):
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
        group=call('/api/admin/dashboard')[1]['series'][0]
        row=group['articles'][0]
        profile=group['dossiers'][0]
        update={'series_id':group['id'],'scope':profile['scope'],'revision':profile['revision'],'fields':{'notes':{'value':'Private dossier note'},'cast':{'value':'Anna de Vries | Noor','source_url':'https://example.org/test','evidence':'Cast credits'}}}
        assert call('/api/dossier',update)[0]==200
        assert call('/api/dossier',update)[0]==409
        public=call('/api/dashboard',auth=False)[1]
        assert public['inbox']==[] and public['ignored']==[] and public['sources']==[]
        assert 'notes' not in public['series'][0]['articles'][0]
        assert 'Private dossier note' not in json.dumps(public)
        app.record_check('article:'+row['id'])
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
        packet=call('/api/dossier/research-package',target)[1]
        assert packet['title']=='Teststad' and 'Private dossier note' not in packet['prompt']
        assert call('/api/dossier/research-package',target,csrf=False)[0]==403
        external={**target,'title':'Teststad','facts':[{'field':'episodes','value':'10','source_url':'https://example.org/test','evidence':'Teststad heeft tien afleveringen.'}]}
        assert call('/api/dossier/research-import',{**external,'title':'Andere serie'})[0]==400
        assert call('/api/dossier/research-import',{**external,'scope':'season:99'})[0]==400
        assert call('/api/dossier/research-import',{**external,'facts':[]})[0]==400
        assert call('/api/dossier/research-import',external,csrf=False)[0]==403
        with patch.object(app,'ai_key',return_value=''),patch.object(app.ai_research,'research') as paid,patch.object(app,'read_article_page',return_value='Teststad heeft tien afleveringen.'):
            assert call('/api/dossier/research-import',external)[0]==202
            for _ in range(100):
                if not app.AI_LOCK.locked():break
                time.sleep(.02)
            assert not app.AI_LOCK.locked()
            paid.assert_not_called()
        fields=call('/api/dashboard',auth=False)[1]['series'][0]['dossiers'][0]['fields']
        assert fields['episodes']['value']=='10' and fields['episodes']['origin']=='external_ai'
        report=call('/api/dossier/research-package',target)[1]['research_status']['report']
        assert report[0]['code']=='confirmed' and report[0]['field']=='episodes'
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
        print('HTTP integration OK: login, CSRF, sources, grouping, review, ignore, persistence')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
