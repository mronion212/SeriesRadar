import io
import json
import unittest
from unittest.mock import patch
import ai_research
import catalog
import dossier
from test_catalog import article


class ResearchTests(unittest.TestCase):
    def test_pasted_response_accepts_fences_and_explanation_but_rejects_ambiguity(self):
        result={'series_id':'a','scope':'new:1','title':'Teststad','facts':[]}
        raw='Dit heb ik gevonden:\n```json\n'+json.dumps(result)+'\n```\nKlaar.'
        self.assertEqual(ai_research.parse_result(raw),result)
        for invalid in (json.dumps(result)+json.dumps(result),'{"facts": [', 'Geen JSON'):
            with self.assertRaises(ValueError):ai_research.parse_result(invalid)

    def test_one_invalid_fact_does_not_block_valid_facts(self):
        report=[]
        proposals=[None,{'field':'notes','value':'Privé','source_url':'https://example.org','evidence':'Test'},
                   {'field':'episodes','value':8,'source_url':'https://example.org','evidence':'Teststad telt acht afleveringen.'}]
        facts,rejected=ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':1},lambda *_:'Teststad telt acht afleveringen.',diagnostics=report)
        self.assertEqual(facts['episodes']['value'],'8')
        self.assertEqual(rejected,2)
        self.assertEqual([r['code'] for r in report],['invalid','invalid','confirmed'])

    def test_people_from_multiple_verified_sources_are_merged(self):
        proposals=[{'field':'cast','value':['Anna | Noor'],'source_url':'https://example.org/a','evidence':'Anna speelt Noor.'},
                   {'field':'cast','value':'Bas | Jan','source_url':'https://example.org/b','evidence':'Bas speelt Jan.'}]
        facts,rejected=ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':1},lambda *_:'Teststad\nAnna speelt Noor. Bas speelt Jan.')
        self.assertEqual(facts['cast']['value'],'Anna | Noor\nBas | Jan')
        self.assertEqual(len(facts['cast']['sources']),2)
        self.assertEqual(rejected,0)

    def test_other_season_elsewhere_on_page_does_not_reject_matching_claim(self):
        proposals=[{'field':'episodes','value':'8','source_url':'https://example.org','evidence':'Seizoen 2 van Teststad telt acht afleveringen.'}]
        facts,rejected=ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':2},lambda *_:'Teststad\nSeizoen 1 was vorig jaar te zien.\nSeizoen 2 van Teststad telt acht afleveringen.')
        self.assertEqual(facts['episodes']['value'],'8')
        self.assertEqual(rejected,0)

    def test_conflicting_episode_counts_are_reported(self):
        report=[]
        proposals=[{'field':'episodes','value':str(n),'source_url':'https://example.org','evidence':f'Teststad telt {n} afleveringen.'} for n in (8,10)]
        facts,rejected=ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':1},lambda *_:'Teststad telt 8 afleveringen. Teststad telt 10 afleveringen.',diagnostics=report)
        self.assertNotIn('episodes',facts)
        self.assertEqual(rejected,2)
        self.assertTrue(all(r['code']=='conflict' and r['status']=='unconfirmed' for r in report))

    def test_a_real_quote_does_not_confirm_an_invented_value(self):
        cases=[('episodes','99','Teststad telt acht afleveringen.'),
               ('runtime','90 minuten','Elke aflevering van Teststad duurt 50 minuten.'),
               ('cast','Anna | Jan','Anna speelt Noor in Teststad.'),
               ('directors','Anna','Anna speelt Noor in Teststad.'),
               ('release_date','2026-10-15','Teststad is vanaf 14 oktober 2026 te zien.')]
        for field,value,quote in cases:
            with self.subTest(field=field):
                report=[]
                facts,rejected=ai_research.verify_proposals([{'field':field,'value':value,
                    'source_url':'https://example.org','evidence':quote}],{'name':'Teststad'},
                    {'season':1},lambda *_:quote,diagnostics=report)
                self.assertEqual((facts,rejected),({},1))
                self.assertEqual(report[0]['code'],'value_unconfirmed')

    def test_explicit_values_and_roles_are_supported(self):
        for field,value,quote in [('episodes','8','De achtdelige serie Teststad.'),
                ('runtime','50 minuten','Elke aflevering duurt 50 minuten.'),
                ('cast','Anna | Noor','Anna speelt Noor.'),('directors','Anna Vos','De regie is van Anna Vos.'),
                ('release_date','2026-10-14','Vanaf 14 oktober 2026 te zien.')]:
            with self.subTest(field=field):self.assertTrue(ai_research.value_supported(field,value,quote))

    def test_crossed_cast_roles_are_not_inferred(self):
        self.assertFalse(ai_research.value_supported('cast','Anna | Jan','Anna speelt Noor en Bas speelt Jan.'))
        self.assertFalse(ai_research.value_supported('cast','Anna | Noor','Anna en Bas spelen Noor en Jan.'))
        self.assertFalse(ai_research.value_supported('directors','Bas Bos','Anna Vos doet de regie. Bas Bos is acteur.'))

    def test_episode_rows_need_a_matching_number_title_and_date(self):
        quote='Seizoen 2 van Teststad, aflevering 1 De vondst, vanaf 14 oktober 2026.'
        self.assertTrue(ai_research.value_supported('episode_guide','1 | De vondst | 2026-10-14',quote))
        self.assertFalse(ai_research.value_supported('episode_guide','2 | De vondst | 2026-10-14',quote))
        self.assertFalse(ai_research.value_supported('episode_guide','1 | De vondst | 2026-10-15',quote))

    def test_partial_episode_count_is_not_an_order(self):
        quote='De eerste acht afleveringen van Teststad zijn te zien.'
        report=[]
        result=ai_research.verify_proposals([{'field':'episodes','value':'8','source_url':'https://example.org',
            'evidence':quote}],{'name':'Teststad'},{'season':1},lambda *_:quote,diagnostics=report)
        self.assertEqual(result,({},1))
        self.assertEqual(report[0]['code'],'partial_count')

    def test_uncertain_negative_and_paraphrased_claims_need_review(self):
        for field,value,quote in [('episodes','8','Teststad krijgt mogelijk acht afleveringen.'),
                ('episodes','8','Teststad krijgt geen acht afleveringen.'),
                ('synopsis','Een eigen beschrijving.','Teststad gaat over een familie.')]:
            report=[]
            facts,rejected=ai_research.verify_proposals([{'field':field,'value':value,
                'source_url':'https://example.org','evidence':quote}],{'name':'Teststad'},
                {'season':1},lambda *_:quote,diagnostics=report)
            self.assertEqual((facts,rejected),({},1))
            self.assertEqual(report[0]['status'],'unconfirmed')

    def test_second_season_needs_explicit_season_context(self):
        quote='Teststad telt acht afleveringen.'
        report=[]
        facts,rejected=ai_research.verify_proposals([{'field':'episodes','value':'8',
            'source_url':'https://example.org','evidence':quote}],{'name':'Teststad'},
            {'season':2},lambda *_:quote,diagnostics=report)
        self.assertEqual((facts,rejected),({},1))
        self.assertEqual(report[0]['code'],'season_unconfirmed')

    def test_source_must_name_the_series(self):
        quote='Dit programma telt acht afleveringen.'
        report=[]
        facts,rejected=ai_research.verify_proposals([{'field':'episodes','value':'8',
            'source_url':'https://example.org','evidence':quote}],{'name':'Teststad'},
            {'season':1},lambda *_:quote,diagnostics=report)
        self.assertEqual((facts,rejected),({},1))
        self.assertEqual(report[0]['code'],'identity_unconfirmed')

    def test_existing_values_are_preserved_and_people_keep_their_sources(self):
        claim=lambda value:{'value':value,'origin':'external_ai','source_url':'https://example.org/new',
                            'sources':[{'source_url':'https://example.org/new','evidence':'New'}]}
        profile={'fields':{'episodes':{'value':'8','origin':'automatic'},
                           'runtime':{'value':'40','origin':'manual'},
                           'cast':{'value':'Anna | Noor','origin':'tvmaze','source_url':'https://tvmaze.com',
                                   'evidence':'Cast','license_url':'https://creativecommons.org/licenses/by-sa/4.0/'}}}
        report=[{'field':f,'status':'confirmed'} for f in ('episodes','runtime','cast')]
        facts=ai_research.reconcile_facts({'episodes':claim('10'),'runtime':claim('50'),
                                         'cast':claim('Bas | Jan')},profile,report)
        self.assertEqual(set(facts),{'cast'})
        self.assertEqual(facts['cast']['value'],'Anna | Noor\nBas | Jan')
        self.assertEqual(len(facts['cast']['sources']),2)
        self.assertIn('license_url',facts['cast'])
        self.assertEqual([r.get('code') for r in report[:2]],['existing_conflict','manual_preserved'])

    def test_chat_package_selects_fields_and_carries_identity_and_instructions(self):
        group={'id':'series-1','name':'Teststad','articles':[],
               'productions':[{'kind':'Nieuwe serie','season':1,'articles':[]}]}
        profile={'scope':'new:1','kind':'Nieuwe serie','season':1,'revision':3,
                 'fields':{'episodes':{'value':'8'},'notes':{'value':'Private note'}}}
        packet=ai_research.research_package(group,profile,{'mode':'verify','target':'imdb','brief':'Controleer ook de regie.'})
        self.assertEqual(packet['dossier_revision'],3)
        self.assertEqual(packet['schema_version'],2)
        self.assertIn('Controleer ook de regie.',packet['prompt'])
        self.assertIn('IMDb',packet['prompt'])
        context=json.loads(packet['prompt'].split('DOSSIERCONTEXT:\n',1)[1])
        self.assertEqual(context['requested_fields'],[['episodes','Aantal afleveringen']])
        self.assertNotIn('Private note',packet['prompt'])
        missing=ai_research.research_package(group,profile)
        context=json.loads(missing['prompt'].split('DOSSIERCONTEXT:\n',1)[1])
        self.assertNotIn('episodes',[f[0] for f in context['requested_fields']])
        for invalid in ([],{'mode':'invalid'},{'brief':'a'*2001}):
            with self.assertRaises(ValueError):ai_research.research_options(invalid)

    def test_empty_research_changes_no_facts(self):
        self.assertEqual(ai_research.verify_proposals([],{'name':'Teststad'},{'season':1},lambda *_:self.fail('No source needed')),({},0))

    def test_report_preserves_blocked_source_for_every_field(self):
        from urllib.error import HTTPError
        proposals=[{'field':field,'value':'Voorstel','source_url':'https://example.org','evidence':'Een letterlijk citaat'} for field in ('cast','directors')]
        report=[]
        with patch.object(ai_research,'urlopen'):
            def blocked(*_):raise HTTPError('https://example.org',403,'Forbidden',{},None)
            facts,rejected=ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':1},blocked,diagnostics=report)
        self.assertEqual((facts,rejected),({},2))
        self.assertEqual([r['code'] for r in report],['source_blocked','source_blocked'])
        self.assertTrue(all('403' in r['reason'] for r in report))

    def test_report_distinguishes_quote_and_season_failures(self):
        report=[]
        proposals=[{'field':'episodes','value':'8','source_url':'https://example.org','evidence':'Teststad telt acht afleveringen.'}]
        ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':1},lambda *_:'Andere inhoud',diagnostics=report)
        self.assertEqual(report[0]['code'],'quote_not_found')
        report=[]
        ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':1},lambda *_:'Seizoen 2. Teststad telt acht afleveringen.',diagnostics=report)
        self.assertEqual(report[0]['code'],'season_mismatch')

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

    def test_external_rejects_wrong_season_and_unreadable_source(self):
        proposals=[{'field':'episodes','value':'8','source_url':'https://example.org','evidence':'Teststad telt acht afleveringen.'}]
        result,rejected=ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':1},lambda *_:'Seizoen 2. Teststad telt acht afleveringen.')
        self.assertEqual((result,rejected),({},1))
        def unavailable(*_):raise OSError('Unavailable')
        self.assertEqual(ai_research.verify_proposals(proposals,{'name':'Teststad'},{'season':1},unavailable),({},1))

    def test_external_rejects_internal_fields_and_bad_links(self):
        for field,url in [('notes','https://example.org'),('cast','javascript:alert(1)')]:
            with self.assertRaises(ValueError):
                ai_research.validate_proposals([{'field':field,'value':'Test','source_url':url,'evidence':'Test'}])

    def test_chatgpt_markdown_links_normalized_before_validation(self):
        proposal={'field':'official_url','value':'[Website](https://example.org/show)','source_url':'[https://example.org/show](https://example.org/show)','evidence':'Teststad'}
        normalized=ai_research.validate_proposals([proposal])[0]
        self.assertEqual(normalized['source_url'],'https://example.org/show')
        self.assertEqual(normalized['value'],'https://example.org/show')
        self.assertTrue(proposal['value'].startswith('[Website]'))
        with self.assertRaises(ValueError):
            ai_research.validate_proposals([{**proposal,'source_url':'[Website](javascript:alert(1))'}])
