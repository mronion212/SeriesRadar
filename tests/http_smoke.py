"""Run separately: opens a temporary local HTTP server, uses a disposable DB."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
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
        assert call('/api/dashboard',auth=False)[0]==401
        assert call('/health',auth=False)[0]==200
        assert call('/api/scan',{},csrf=False)[0]==403
        assert call('/api/article',{})[0]==400
        source={'name':'Integration feed','mode':'search','value':'"Nederlandse serie" when:90d','enabled':False}
        status,result=call('/api/source',source)
        assert status==200
        saved=next(s for s in call('/api/dashboard')[1]['sources'] if s['id']==result['id'])
        assert saved['enabled'] is False
        with app.connect() as c:
            app.ingest(c,{'id':'test','name':'Test'},[{'title':"Nieuwe Nederlandse serie 'Teststad' aangekondigd",'url':'https://example.org/test','summary':'','published':None,'publisher':'Test'}])
        group=call('/api/dashboard')[1]['series'][0]
        row=group['articles'][0]
        profile=group['dossiers'][0]
        update={'series_id':group['id'],'scope':profile['scope'],'revision':profile['revision'],'fields':{'cast':{'value':'Anna de Vries | Noor','source_url':'https://example.org/test','evidence':'Cast credits'}}}
        assert call('/api/dossier',update)[0]==200
        assert call('/api/dossier',update)[0]==409
        app.init()
        dossier=call('/api/dashboard')[1]['series'][0]['dossiers'][0]
        assert dossier['fields']['cast']['value']=='Anna de Vries | Noor'
        assert dossier['fields']['cast']['origin']=='manual'
        data={'id':row['id'],'series_title':'Teststad','production_kind':'Nieuw seizoen','season_number':2,'phase':'In productie','notes':'Persisted note','tvdb':0,'excluded':0}
        assert call('/api/article',data)[0]==200
        updated=call('/api/dashboard')[1]['series'][0]
        assert updated['productions'][0]['season']==2
        assert updated['productions'][0]['status']=='In productie'
        data['excluded']=1
        assert call('/api/article',data)[0]==200
        assert not call('/api/dashboard')[1]['series']
        assert call('/api/dashboard')[1]['ignored'][0]['notes']=='Persisted note'
        print('HTTP integration OK: login, CSRF, sources, grouping, review, ignore, persistence')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
