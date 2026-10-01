import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

class RadarTests(unittest.TestCase):
    def test_targeted_discovery_fills_missing_fields_and_keeps_existing_values(self):
        with app.connect() as c:
            app.ingest(c,{'id':'test','name':'Test'},[{'title':'Nieuwe Nederlandse serie Teststad','url':'https://example.org/news','summary':'Teststad is vanaf 12 oktober 2026 te zien bij NPO 1.','published':None,'publisher':''}])
        group=app.get_catalog()['series'][0]
        fact=lambda value:{'value':value,'source_url':'https://example.org/press','evidence':'Credits','origin':'automatic'}
        items=[{'title':'Teststad cast en makers','summary':'','url':'https://example.org/press'}]
        with patch.object(app,'fetch_source',return_value=items) as feed,patch.object(app,'read_metadata',return_value=({'cast':fact('Anna | Noor'),'release_date':fact('Oude datum')},1,'https://example.org/press')) as read:
            app.discover_metadata()
            app.discover_metadata()
        self.assertEqual(feed.call_count,1)
        self.assertEqual(read.call_count,1)
        profile=app.get_catalog()['series'][0]['dossiers'][0]
        self.assertEqual(profile['fields']['cast']['value'],'Anna | Noor')
        self.assertEqual(profile['fields']['release_date']['value'],'12 oktober 2026')

    def test_unnumbered_discovery_cannot_copy_cast_across_seasons_or_on_refresh(self):
        with app.connect() as c:
            app.ingest(c,{'id':'test','name':'Test'},[
                {'title':'Nieuwe Nederlandse serie Teststad','url':'https://example.org/1','summary':'','published':None,'publisher':''},
                {'title':'Nederlandse serie Teststad krijgt tweede seizoen','url':'https://example.org/2','summary':'','published':None,'publisher':''}])
        facts={k:{'value':v,'source_url':'https://example.org/press','evidence':'Credits','origin':'automatic'} for k,v in [('cast','Anna'),('languages','Nederlands')]}
        items=[{'title':'Teststad cast','summary':'','url':'https://example.org/press'}]
        with patch.object(app,'fetch_source',return_value=items),patch.object(app,'read_metadata',return_value=(facts,None,'https://example.org/press')):
            app.discover_metadata()
            with app.connect() as c:linked=[dict(r) for r in c.execute('SELECT * FROM dossier_sources')]
            for s in linked:app.import_metadata(s['series_id'],s['scope'],s['name'],s['url'],json.loads(s['field_filter']))
        for p in app.get_catalog()['series'][0]['dossiers']:
            self.assertNotIn('cast',p['fields'])
            self.assertEqual(p['fields']['languages']['value'],'Nederlands')

    def test_article_enrichment_persists_full_page_facts_and_success(self):
        import io
        from email.message import Message
        with app.connect() as c:
            app.ingest(c,{'id':'test','name':'Test'},[{'title':'Nieuwe Nederlandse serie Teststad','url':'https://example.org/press','summary':'','published':None,'publisher':''}])
        response=io.BytesIO(b'<h1>Nieuwe Nederlandse serie Teststad</h1><p>Cast: Anna Vos</p>');response.headers=Message()
        with patch.object(app,'resolve_article_url',side_effect=lambda url:url),patch.object(app,'build_opener') as opener:
            opener.return_value.open.return_value=response
            app.enrich_articles(limit=1)
        with app.connect() as c:
            self.assertEqual(json.loads(c.execute('SELECT facts FROM article_facts').fetchone()[0])['cast']['value'],'Anna Vos')
            self.assertIsNotNone(c.execute('SELECT last_success FROM enrichment_checks').fetchone()[0])

    def test_atom_uses_full_content(self):
        feed=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Test</title><summary>Kort</summary><content>Volledige inhoud</content><link href="https://example.org/test"/></entry></feed>'
        self.assertEqual(list(app.parse_feed(feed))[0]['summary'],'Volledige inhoud')

    def test_unread_articles_precede_recently_checked_articles(self):
        items=[{'title':'Nieuwe Nederlandse serie Test'+str(n),'url':'https://example.org/'+str(n),'summary':'','published':f'2026-09-0{n+1}T12:00:00Z','publisher':''} for n in range(2)]
        with app.connect() as c:
            app.ingest(c,{'id':'test','name':'Test'},items)
            recent=c.execute('SELECT id FROM articles ORDER BY published DESC LIMIT 1').fetchone()['id']
            c.execute('INSERT INTO enrichment_checks (key,checked) VALUES (?,?)',('article:'+recent,'2020-01-01'))
        with patch.object(app,'public_url',side_effect=ValueError('test stop')) as fetch:
            app.enrich_articles(limit=1)
        fetch.assert_called_once_with('https://example.org/0')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = app.DB
        app.DB = Path(self.temp.name) / 'test.sqlite3'
        app.init()

    def tearDown(self):
        app.DB = self.previous
        self.temp.cleanup()

    def test_feed_dedup_preserves_review(self):
        feed = b'<rss><channel><item><title>Nieuwe serie Test</title><link>https://example.org/test</link><description>Opnames zijn gestart</description><pubDate>Fri, 11 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        items = list(app.parse_feed(feed))
        source = {'id':'test','name':'Test'}
        with app.connect() as c:
            self.assertEqual(app.ingest(c, source, items), 1)
            c.execute("UPDATE articles SET notes='bewaard',tvdb=1,reviewed=1,phase='Release gepland'")
            self.assertEqual(app.ingest(c, {'id':'other','name':'Other'}, items), 0)
        with app.connect() as c:
            row = c.execute('SELECT * FROM articles').fetchone()
            self.assertEqual(row['notes'], 'bewaard')
            self.assertEqual(row['phase'], 'Release gepland')
            self.assertEqual(row['tvdb'], 1)

    def test_catalog_cache_reuses_reads_and_refreshes_after_write(self):
        with patch.object(app, '_build_catalog', wraps=app._build_catalog) as build:
            first = app.get_catalog()
            first['series'].append({'name': 'Local mutation'})
            self.assertEqual(app.get_catalog()['series'], [])
            self.assertEqual(build.call_count, 1)
            revision = app.catalog_revision()
            with app.connect() as c:
                app.ingest(c, {'id': 'test', 'name': 'Test'}, [{'title': 'Nieuwe Nederlandse serie Teststad aangekondigd', 'url': 'https://example.org/test', 'summary': '', 'published': None, 'publisher': 'Test'}])
            self.assertGreater(app.catalog_revision(), revision)
            self.assertEqual(len(app.get_catalog()['series']), 1)
            self.assertEqual(build.call_count, 2)

    def test_classification_and_unknown(self):
        for title, phase in [('Opnames zijn gestart voor nieuwe serie', 'In productie'), ('Nieuwe serie vanaf vandaag te zien', 'Gereleased'), ('Serie vanaf 12 december', 'Release gepland'), ('Interview over een serie','Te beoordelen')]:
            self.assertEqual(app.classify(title)[0],phase)

    def test_bad_feed_and_date(self):
        with self.assertRaises(ValueError):
            list(app.parse_feed(b'<html>oops</html>'))
        self.assertIsNone(app.publication_date('onbekend'))
        self.assertEqual(app.publication_date('2026-09-11T12:00:00Z'), '2026-09-11T12:00:00+00:00')

    def test_relevance_ignores_publisher_and_sport(self):
        self.assertFalse(app.relevant({'title':'Nieuwe film op Netflix - serietotaal.nl','summary':'Nieuwe film op Netflix serietotaal.nl','publisher':'serietotaal.nl'}, 'rtl'))
        self.assertFalse(app.relevant({'title':'PSV wint eerste topper van het seizoen','summary':'','publisher':'RTL'}, 'rtl'))
        self.assertTrue(app.relevant({'title':'Nieuwe Nederlandse dramaserie aangekondigd','summary':'','publisher':''}, 'streamers'))

    def test_failed_source_does_not_block_others(self):
        sources = [{'id':'bad','name':'Bad'},{'id':'good','name':'Good'}]
        def fetch(s):
            if s['id']=='bad': raise ValueError('offline')
            return [{'title':'Nieuwe serie Test','url':'https://example.org/test','summary':'','published':None,'publisher':''}]
        with patch.object(app,'sources',return_value=sources), patch.object(app,'fetch_source',side_effect=fetch):
            app.scan()
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM articles').fetchone()[0],1)
            self.assertEqual(c.execute("SELECT error FROM sources WHERE id='bad'").fetchone()[0],'offline')
            self.assertIsNotNone(c.execute("SELECT value FROM meta WHERE key='last_finished'").fetchone())
        self.assertFalse(app.LOCK.locked())

if __name__ == '__main__': unittest.main()
