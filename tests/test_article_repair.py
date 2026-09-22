import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import app
import catalog
import dossier
from test_catalog import article


class Response(io.BytesIO):
    headers=Message()
    def geturl(self):return 'https://news.google.com/rss/articles/example'


class ArticleRepairTests(unittest.TestCase):
    def test_ordinal_cannot_seed_unrelated_headlines(self):
        rows=[article('1','Nieuwe Nederlandse serie Tweede seizoen aangekondigd'),
              article('2','Nieuwe trailer: populaire actieserie met Chris Pratt keert terug voor tweede seizoen')]
        self.assertEqual(catalog.extract_name(rows[0]),'')
        self.assertEqual(catalog.catalog(rows)['series'],[])

    def test_google_link_resolves_and_rejects_private_destination(self):
        page=b'<div data-n-a-id="example" data-n-a-ts="1234" data-n-a-sg="signature"></div>'
        for target in ['https://publisher.example/news','https://127.0.0.1/private']:
            body=")]}'\n\n"+json.dumps([['wrb.fr','Fbv4je',json.dumps(['garturlres',target,1])]])
            def validate(url):
                if '127.0.0.1' in url:raise ValueError('private')
                return url
            with patch.object(app,'public_url',side_effect=validate),patch.object(app,'build_opener') as opener:
                opener.return_value.open.side_effect=[Response(page),Response(body.encode())]
                if '127.0.0.1' in target:
                    with self.assertRaises(ValueError):app.resolve_article_url('https://news.google.com/rss/articles/example')
                else:self.assertEqual(app.resolve_article_url('https://news.google.com/rss/articles/example'),target)

    def test_article_body_excludes_other_programme_cards(self):
        p=dossier.ArticleParser()
        p.feed('<h1>Nieuw programma Wedding in a Week?</h1><div class="detailpage__detailtext"><p>Het nieuwe programma Wedding in a Week? is een liefdesexperiment waarin singles samenleven.</p><p>Wedding in a Week? is vanaf maandag 22 februari dagelijks bij NET5 te zien.</p></div><p>Andere Serie is nu te zien op Videoland. Cast: Wrong Person.</p>')
        text=p.text_for('Wedding in a Week')
        facts=dossier.extract(text,'Wedding in a Week','https://example.org/news')
        self.assertEqual(facts['release_date']['value'],'22 februari')
        self.assertEqual(facts['networks']['value'],'NET5')
        self.assertIn('synopsis',facts)
        self.assertNotIn('release_year',facts)
        self.assertNotIn('cast',facts)
        self.assertEqual(catalog.phase_of(text)[0],'Release gepland')

    def test_roundup_metadata_stays_in_its_named_section(self):
        p=dossier.ArticleParser()
        p.feed('<h1>Programmas in oktober</h1><h2>Eerste Show</h2><p>Vanaf 3 oktober te zien bij NPO 1.</p><h2>Nederlands Domste</h2><p>Nederlands Domste is vanaf 24 oktober te zien bij RTL 4.</p><h2>Laatste Show</h2><p>Vanaf 30 oktober te zien bij NET5.</p>')
        facts=dossier.extract(p.text_for('Nederlands Domste'),'Nederlands Domste','https://example.org')
        self.assertEqual(facts['release_date']['value'],'24 oktober')
        self.assertEqual(facts['networks']['value'],'RTL 4')
        with self.assertRaises(ValueError):p.text_for('Niet genoemd')

    def test_broadcast_evidence_updates_only_the_matching_production(self):
        rows=[article('1','Het nieuwe datingprogramma Wil Je met Me Bouwen?',summary='Bij NET5 vanaf 14 september 2026 te zien.'),
              article('2','Wil je met me bouwen?',summary='Deze uitzending van het programma Wil je met me bouwen? werd uitgezonden op maandag 14 september door NET5.')]
        group=catalog.catalog(rows)['series'][0]
        self.assertEqual(group['productions'][0]['status'],'Beschikbaar')
        rows.append(article('3','Het tweede seizoen van Wil Je met Me Bouwen? aangekondigd',summary='NET5 presenteert een nieuw seizoen.'))
        group=catalog.catalog(rows)['series'][0]
        self.assertEqual(next(p for p in group['productions'] if p['season']==2)['status'],'Aangekondigd')

    def test_presenters_and_partial_episode_count(self):
        text='Edson da Graça en Monica Geuze presenteren nieuwe spelshow Nederlands Domste.\nNederlands Domste is vanaf 24 oktober te zien bij RTL 4. Na zeven afleveringen zijn er drie kandidaten over voor de finale.'
        facts=dossier.extract(text,'Nederlands Domste','https://example.org')
        self.assertEqual(facts['presenters']['value'],'Edson da Graça\nMonica Geuze')
        self.assertNotIn('episodes',facts)

    def test_recurring_feed_does_not_replace_full_article_facts(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'DB',Path(folder)/'test.sqlite3'):
            app.init()
            item=article('unused','Nieuwe Nederlandse serie Teststad',summary='Teststad is vanaf 24 oktober te zien bij RTL 4.')
            with app.connect() as c:
                app.ingest(c,{'id':'test','name':'Test'},[item])
                item['summary']='Een kort feedfragment zonder datum.'
                app.ingest(c,{'id':'test','name':'Test'},[item])
                facts=json.loads(c.execute('SELECT facts FROM article_facts').fetchone()[0])
            self.assertEqual(facts['release_date']['value'],'24 oktober')
