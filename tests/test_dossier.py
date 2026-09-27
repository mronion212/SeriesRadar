import unittest
import dossier
from test_catalog import article
import catalog

class DossierTests(unittest.TestCase):
    def test_renewal_article_credits_and_premise_not_casting_call(self):
        text=("Realityshow Undercover Lover krijgt een tweede seizoen. Het nieuws werd bekendgemaakt door "
              "presentatoren Robbert Rodenburg en Kelly Mexy.\nIn Undercover Lover reizen vijf koppels af "
              "naar een tropisch paradijs, waar ze bij aankomst van elkaar worden gescheiden.\n"
              "De makers zoeken deelnemers voor het tweede seizoen. Meld je aan, luidt de oproep van producent SimpelZodiak.")
        facts=dossier.extract(text,'Undercover Lover','https://example.org/renewal')
        self.assertEqual(facts['production_companies']['value'],'SimpelZodiak')
        self.assertEqual(facts['presenters']['value'],'Robbert Rodenburg\nKelly Mexy')
        self.assertTrue(facts['synopsis']['value'].startswith('In Undercover Lover reizen'))

    def test_current_extraction_corrects_old_automatic_article_facts(self):
        body=('Realityshow Undercover Lover krijgt een tweede seizoen.\n'
              'In Undercover Lover reizen vijf koppels af naar een tropisch paradijs.\n'
              'De oproep komt van producent SimpelZodiak.')
        group={'name':'Undercover Lover','productions':[{'kind':'Nieuw seizoen','season':2,'status':'Aangekondigd','articles':['renewal']}],
               'articles':[{'id':'renewal','title':'Undercover Lover krijgt een tweede seizoen','summary':body,'url':'https://example.org/renewal'}]}
        old={'renewal':{'production_companies':{'value':'presentatoren Robbert Rodenburg','source_url':'https://example.org/renewal'},
                        'synopsis':{'value':'Meld je aan voor seizoen 2','source_url':'https://example.org/renewal'}}}
        fields=dossier.prepare(group,{}, {},old)[0]['fields']
        self.assertEqual(fields['production_companies']['value'],'SimpelZodiak')
        self.assertTrue(fields['synopsis']['value'].startswith('In Undercover Lover reizen'))

    def test_previous_credits_and_coproduction_prose_are_not_names(self):
        f=dossier.extract('Teststad is geproduceerd door NewBe in co-productie met AVROTROS en wordt gemaakt door het team achter films. Geregisseerd door Jonathan Elbers (Film Een, Film Twee) en Dennis Bots (Andere Film).','Teststad','https://example.org')
        self.assertEqual(f['production_companies']['value'],'NewBe')
        self.assertEqual(f['directors']['value'],'Jonathan Elbers\nDennis Bots')

    def test_extract_explicit_credits_without_inventing_roles(self):
        text="Nieuwe serie Teststad. De hoofdrollen worden gespeeld door Anna de Vries en Bas Jansen. De serie is geproduceerd door Test Film en geregisseerd door Eva Vos. Het scenario is geschreven door Jan Smit en Piet de Boer. Teststad is in 2027 te streamen bij Videoland."
        f=dossier.extract(text,'Teststad','https://example.org/news')
        self.assertEqual(f['cast']['value'],'Anna de Vries\nBas Jansen')
        self.assertEqual(f['production_companies']['value'],'Test Film')
        self.assertEqual(f['directors']['value'],'Eva Vos')
        self.assertEqual(f['writers']['value'],'Jan Smit\nPiet de Boer')
        self.assertEqual(f['platforms']['value'],'Videoland')
        self.assertEqual(f['release_year']['value'],'2027')
        self.assertNotIn('languages',f)
        self.assertNotIn('countries',f)
        self.assertEqual(f['cast']['origin'],'automatic')

    def test_publisher_and_creator_not_mistaken_for_network_or_cast(self):
        f=dossier.extract('Teststad van Barry Atsma - RTL.nl','Teststad','https://example.org')
        self.assertNotIn('cast',f)
        self.assertNotIn('networks',f)

    def test_parser_ignores_script_navigation_and_wrong_titles(self):
        parser=dossier.ArticleParser()
        parser.feed('<h1>Teststad aangekondigd</h1><nav><p>Cast: Fake Person</p></nav><p>Teststad is geproduceerd door Test Film.</p><script>Cast: Wrong Name</script>')
        text=parser.text_for('Teststad')
        self.assertNotIn('Fake',text);self.assertNotIn('Wrong',text)
        with self.assertRaises(ValueError):parser.text_for('Andere serie')

    def test_manual_data_survives_new_automatic_data_and_seasons_isolated(self):
        g=catalog.catalog([article('1',"Nieuwe Nederlandse serie 'Teststad' aangekondigd"),article('2',"Nederlandse serie 'Teststad' krijgt tweede seizoen")])['series'][0]
        saved={'new:1':{'revision':1,'fields':{'cast':{'value':'Anna de Vries | Noor','origin':'manual','source_url':'https://example.org','evidence':'credits'}}}}
        imported={'new:1':{'cast':{'value':'Wrong Replacement','origin':'automatic'}}}
        profiles={p['scope']:p for p in dossier.prepare(g,saved,imported)}
        self.assertEqual(profiles['new:1']['fields']['cast']['value'],'Anna de Vries | Noor')
        self.assertNotIn('cast',profiles['season:2']['fields'])

    def test_validation_blocks_script_urls_and_bad_ids(self):
        for fields in [{'official_url':{'value':'javascript:alert(1)'}},{'cast':{'value':'Test','source_url':'javascript:alert(1)'}},{'imdb_id':{'value':'wrong'}},{'unknown':{'value':'x'}}]:
            with self.assertRaises(ValueError):dossier.validate_fields(fields)
        self.assertEqual(dossier.validate_fields({'imdb_id':{'value':'tt1234567'}})['imdb_id']['origin'],'manual')

    def test_blanking_a_field_suppresses_automatic_value(self):
        g=catalog.catalog([article('1',"Nieuwe Nederlandse serie 'Teststad' aangekondigd")])['series'][0]
        profiles=dossier.prepare(g,{'new:1':{'revision':1,'fields':dossier.validate_fields({'cast':{'value':''}})}},{'new:1':{'cast':{'value':'Somebody','origin':'automatic'}}})
        self.assertEqual(profiles[0]['fields']['cast']['value'],'')

if __name__=='__main__':unittest.main()
