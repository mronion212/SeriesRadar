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


class TitleIdentityTests(unittest.TestCase):
    def test_publisher_cannot_become_title_from_repeated_feed_headline(self):
        for publisher in ['NU','TVgids.nl','Spreekbuis.nl','Ditjes en Datjes','EO','PowNed']:
            with self.subTest(publisher=publisher):
                a=article('1','NPO maakt een nieuwe jeugdserie - '+publisher,
                          summary='NPO maakt een nieuwe jeugdserie '+publisher,publisher=publisher)
                self.assertEqual(catalog.extract_name(a),'')
                self.assertEqual(catalog.catalog([a])['series'],[])

    def test_false_nu_seed_cannot_collect_unrelated_headlines(self):
        rows=[article('1','NPO waarschuwt voor neppe mails met verzoek om auditievideo voor jeugdserie - NU',
                      summary='NPO waarschuwt voor neppe mails met verzoek om auditievideo voor jeugdserie NU',publisher='NU'),
              article('2',"Disney+ komt met documentaire over killer clowns: trailer van 'Clown Panic' nu te zien - FilmVandaag",publisher='FilmVandaag'),
              article('3','Netflix verlengt geprezen hitserie nú al met een derde seizoen - FilmVandaag',publisher='FilmVandaag')]
        self.assertEqual(catalog.catalog(rows)['series'],[])
        self.assertEqual(catalog.tidy_name('Nu te zien'),'')

    def test_descriptions_and_networks_do_not_extend_programme_titles(self):
        cases={
            'Nieuwe dramaserie Pro Deo over een klein en strijdbaar advocatenkantoor':'Pro Deo',
            'Nieuwe dramaserie Pro Deo met Tjitske Reidinga':'Pro Deo',
            'Lucas De Man trapt het nieuwe seizoen van Man en Kunst af op NPO 2':'Man en Kunst',
            'Netflix kondigt nieuwe Nederlandse serie De Stilte aan':'De Stilte',
            'Nieuw seizoen Vier Handen Op Eén Buik bij BNNVARA':'Vier Handen Op Eén Buik',
            'IDTV maakt nieuw seizoen Je Huis Op Orde voor SBS6':'Je Huis Op Orde',
            'Hoofdrol in nieuwe dramaserie Dochters van Videoland':'Dochters',
            'Videoland zoekt prinsesjes voor derde seizoen Máxima-serie':'Máxima',
            'Datingserie Love Is Blind: Nederland bij Netflix':'Love Is Blind: Nederland',
            'Prime Video maakt realityserie Seks, Zweet en Tranen over sekswerk in Nederland':'Seks, Zweet en Tranen',
            'Ondanks kritiek komt er tweede seizoen van De Hanslers: opnames al in volle gang':'De Hanslers',
            "Nieuwe documentaire: 'Knokke in Cadzand'":'Knokke in Cadzand',
        }
        for title,expected in cases.items():
            with self.subTest(title=title):
                a=article('1',title+' - Pers',summary=title+' Pers')
                self.assertEqual(catalog.extract_name(a),expected)

    def test_editorial_labels_and_pull_quotes_are_not_titles(self):
        for title in ['In productie: Nieuwe Nederlandse Netflix-serie met bekende acteurs',
                      "Netflix 'overtreft bestseller' met nieuwe Nederlandse thrillerserie: 'Een ode'",
                      "Nieuwe documentaire: 'Freek is weer zichzelf'",
                      'Daten met humor in nieuwe PowNed-serie']:
            self.assertEqual(catalog.extract_name(article('1',title)),'')

    def test_explicit_title_wins_over_incidental_known_word(self):
        a=article('1',"Nieuwe Nederlandse serie 'Oog op Morgen' aangekondigd")
        self.assertEqual(catalog.assess(a,{'morgen':'Morgen'})['name'],'Oog op Morgen')
        a=article('2','Meer mensen kijken morgen naar deze nieuwe Nederlandse serie')
        self.assertEqual(catalog.assess(a,{'morgen':'Morgen'})['name'],'')
        a=article('3','Volledige Cast van De Eetclub (serie, 2026)')
        self.assertEqual(catalog.assess(a,{'cast':'Cast','de eetclub':'De Eetclub'})['name'],'De Eetclub')

    def test_title_in_body_of_teaser_headline_is_read(self):
        title='Netflix verlengt geprezen hitserie nú al met een derde seizoen'
        body='Een actrice zou een rol krijgen in het derde seizoen van The Gentlemen (2024– ). Er is nu groen licht voor dat seizoen.'
        p=dossier.ArticleParser();p.feed('<h1>'+title+'</h1><p>'+body+"</p><p>De trailer van het tweede seizoen van Guy Ritchie's The Gentlemen is verschenen.</p>")
        text=p.text_for('The Gentlemen')
        self.assertEqual(catalog.extract_name(article('1',title,summary=text)),'The Gentlemen')
        with self.assertRaises(ValueError):p.text_for('Andere Serie')
        # Reading a Dutch article about Netflix does not establish Dutch production.
        out=catalog.catalog([article('1',title,summary=text)])
        self.assertEqual(out['series'],[])
        self.assertEqual(out['ignored'][0]['name'],'The Gentlemen')

    def test_prior_credits_in_body_do_not_replace_headline_subject(self):
        a=article('1','Presentator maakt The Golden Elevators',summary=(
            'In de nieuwe spelshow The Golden Elevators starten tien kandidaten in een wolkenkrabber.\n'
            'Eerder presenteerde hij het programma De Wereld Draait Door. De omroep reageerde.'))
        self.assertEqual(catalog.extract_name(a),'The Golden Elevators')

    def test_manual_names_and_multiword_title_punctuation_remain_intact(self):
        a=article('1',"Nieuwe Nederlandse serie 'Signed, Sealed, Delivered' aangekondigd")
        self.assertEqual(catalog.extract_name(a),'Signed, Sealed, Delivered')
        a=article('2','Een onduidelijke kop',series_title='Nu',classification_reviewed=1,
                  production_kind='Nieuwe serie',season_number=1,phase='Aangekondigd')
        self.assertEqual(catalog.catalog([a])['series'][0]['name'],'Nu')

    def test_enrichment_reads_unnamed_season_news_without_domestic_assumption(self):
        class Response(io.BytesIO):
            headers=Message()
        title='Netflix verlengt geprezen hitserie nú al met een derde seizoen'
        page=('<h1>'+title+'</h1><p>Er komt een derde seizoen van The Gentlemen (2024– ).</p>').encode()
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'DB',Path(folder)/'test.sqlite3'):
            app.init()
            with app.connect() as c:app.ingest(c,{'id':'test','name':'Test'},[article('1',title)])
            with patch.object(app,'public_url'),patch.object(app,'resolve_article_url',return_value='https://example.org/news'),patch.object(app,'build_opener') as opener:
                opener.return_value.open.return_value=Response(page)
                app.enrich_articles(limit=1)
            with app.connect() as c:
                stored=dict(c.execute('SELECT * FROM articles').fetchone())
                check=c.execute("SELECT * FROM enrichment_checks WHERE key LIKE 'article:%'").fetchone()
            self.assertEqual(catalog.extract_name(stored),'The Gentlemen')
            self.assertIsNotNone(check['last_success'])
            self.assertIsNone(check['error'])
