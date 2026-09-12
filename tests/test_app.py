import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

class RadarTests(unittest.TestCase):
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
