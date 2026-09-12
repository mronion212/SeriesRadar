import io
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
import app
import catalog
import dossier
from test_catalog import article


class RealityTests(unittest.TestCase):
    def test_wolven_heading_and_named_body_establish_new_programme(self):
        a=article('wolven','Wolven',url='https://npo.nl/start/serie/wolven/afleveringen/seizoen-22',
                  summary='In het gloednieuwe, psychologische spelprogramma Wolven spelen Nederlanders. Wolven kijk je sinds zaterdag 29 augustus op NPO 1. Streamen via NPO Start en Disney+.')
        self.assertTrue(app.relevant(a,'test'))
        g=catalog.catalog([a])['series'][0]
        self.assertEqual((g['name'],g['productions'][0]['season'],g['productions'][0]['status']),('Wolven',1,'Beschikbaar'))
        facts=dossier.extract(a['summary'],'Wolven',a['url'])
        self.assertEqual(facts['platforms']['value'],'NPO Start\nDisney+')

    def test_acronym_alias_and_unknown_season_stay_visible(self):
        rows=[article('1','A.S.S. Anti Survival Show',summary='In het programma A.S.S. Anti Survival Show spelen bekende Nederlanders. Het programma is te zien bij NET5.'),
              article('2','Dit zijn de kandidaten van het nieuwe realityprogramma de Anti Survival Show',summary='NET5 presenteert een nieuw programma.')]
        g=catalog.catalog(rows)['series'][0]
        self.assertEqual(len(g['articles']),2)
        self.assertEqual(catalog.normalize(g['name']),'anti survival show')
        self.assertTrue(any(p['status']=='Beschikbaar' for p in g['productions']))
        alone=catalog.catalog(rows[:1])['series'][0]
        self.assertIsNone(alone['productions'][0]['season'])

    def test_reality_spacing_and_page_description_are_read(self):
        parser=dossier.ArticleParser()
        parser.feed('<meta name="description" content="Undercover Lover is een realityprogramma voor Nederland."><h1>Undercover Lover</h1><p>Undercover Lover is te streamen op (o.a.) Prime Video.</p>')
        rows=[article('1','Prime Video toont trailer van reality programma Undercover Lover',summary='Undercover Lover is vanaf 17 juli exclusief te zien op Prime Video.'),
              article('2','Undercover Lover',summary=parser.text_for('Undercover Lover'))]
        g=catalog.catalog(rows)['series'][0]
        self.assertEqual(g['name'],'Undercover Lover')
        self.assertEqual(len(g['articles']),2)
        self.assertEqual(g['productions'][0]['status'],'Beschikbaar')

    def test_failed_direct_page_does_not_discard_other_articles(self):
        class Response(io.BytesIO):
            headers=Message()
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'DB',Path(folder)/'test.sqlite3'):
            app.init()
            source={'id':'test','name':'Test','url':'https://example.org/feed','initial_urls':['https://example.org/blocked','https://example.org/wolven']}
            with patch.object(app,'public_url'),patch.object(app,'build_opener') as opener:
                opener.return_value.open.side_effect=[Response(b'<rss><channel/></rss>'),OSError('blocked'),Response(b'<h1>Wolven</h1><p>Het nieuwe spelprogramma Wolven bij NPO.</p>')]
                result=app.fetch_source(source)
            self.assertEqual([a['title'] for a in result],['Wolven'])
            self.assertIn('blocked',source['_warnings'][0])
            self.assertFalse(app.due_check('initial:https://example.org/blocked'))
