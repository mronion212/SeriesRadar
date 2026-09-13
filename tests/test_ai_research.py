import io
import json
import unittest
from unittest.mock import patch
import ai_research
import catalog
import dossier
from test_catalog import article


class ResearchTests(unittest.TestCase):
    def test_question_and_quoted_prepositions_are_preserved(self):
        self.assertEqual(catalog.extract_name(article('1','Het nieuwe datingprogramma Wil Je met Me Bouwen? maakt zijn opwachting bij NET5')), 'Wil Je met Me Bouwen?')
        self.assertEqual(catalog.extract_name(article('2', 'Nieuwe Nederlandse serie "Met het mes op tafel" aangekondigd')), 'Met het mes op tafel')

    def test_only_consulted_sources_and_matching_quotes_accepted(self):
        url='https://example.org/press'
        facts=[{'field':'episodes','value':'8','source_url':url,'evidence':'Teststad telt acht afleveringen.'},
               {'field':'runtime','value':'50 minuten','source_url':url,'evidence':'Elke aflevering duurt 50 minuten.'},
               {'field':'cast','value':'Verzonnen acteur','source_url':'https://example.org/not-consulted','evidence':'Een acteur'}]
        response={'status':'completed','output':[{'type':'web_search_call','action':{'sources':[{'url':url}]}},
                  {'type':'message','content':[{'type':'output_text','text':json.dumps({'facts':facts})}]}]}
        with patch.object(ai_research,'urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as request:
            result,rejected=ai_research.research('sk-test',{'name':'Teststad','articles':[]}, {'kind':'Nieuwe serie','season':1},lambda url,name:'Teststad telt acht afleveringen.')
        self.assertEqual(list(result),['episodes'])
        self.assertEqual(rejected,2)
        payload=json.loads(request.call_args.args[0].data)
        self.assertEqual((payload['model'],payload['reasoning']['effort']),('gpt-5.6-luna','max'))
        self.assertFalse(payload['store'])

    def test_broadcast_date_and_spaced_network(self):
        text='Wil Je met Me Bouwen? is op maandag 14 september 2026 om 20:25 uur te zien bij NET 5.'
        facts=dossier.extract(text,'Wil Je met Me Bouwen?','https://example.org')
        self.assertEqual(facts['release_date']['value'],'14 september 2026')
        self.assertEqual(facts['networks']['value'],'NET 5')
        self.assertEqual(catalog.phase_of(text)[0],'Release gepland')
