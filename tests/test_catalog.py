import unittest
import catalog

def article(id, title, published='2026-09-01T12:00:00+00:00', **extra):
    return {'id':id,'title':title,'url':'https://example.org/'+id,'summary':'','publisher':'Pers','source':'test','published':published,'discovered':'2026-09-11T12:00:00+00:00','phase':'Te beoordelen','reviewed':0,'classification_reviewed':0,'series_title':'','tvdb':0,'notes':'','excluded':0,**extra}

class CatalogTests(unittest.TestCase):
    def test_same_series_groups_without_mixing_seasons(self):
        rows=[article('1',"Nieuwe Nederlandse serie 'Teststad' vanaf vandaag te streamen",'2026-01-01T12:00:00+00:00'),article('2',"Nederlandse serie 'Teststad' krijgt tweede seizoen",'2026-09-01T12:00:00+00:00')]
        groups=catalog.catalog(rows)['series']
        self.assertEqual(len(groups),1)
        by_season={p['season']:p for p in groups[0]['productions']}
        self.assertEqual(by_season[1]['status'],'Beschikbaar')
        self.assertEqual(by_season[2]['status'],'Aangekondigd')
        self.assertEqual(by_season[2]['kind'],'Nieuw seizoen')

    def test_no_title_never_becomes_a_fake_series(self):
        out=catalog.catalog([article('1','Nieuwe Nederlandse serie met bekende acteurs aangekondigd')])
        self.assertEqual(out['series'],[])
        self.assertEqual(len(out['inbox']),1)

    def test_network_is_not_a_series(self):
        self.assertEqual(catalog.extract_name(article('1','Nieuwe MAX-serie aangekondigd')),'')
        self.assertEqual(catalog.extract_name(article('2','Nieuwe dramaserie Fort Alpha bij AVROTROS')),'Fort Alpha')
        self.assertEqual(catalog.extract_name(article('3','Nieuwe serie De Bangaclub in duistere kant studentenleven')),'De Bangaclub')

    def test_domestic_context_shared_across_publishers(self):
        rows=[article('1',"Nederlandse serie 'Teststad' in ontwikkeling"),article('2',"Nieuwe serie 'Teststad' aangekondigd")]
        self.assertEqual(len(catalog.catalog(rows)['series'][0]['articles']),2)

    def test_roundups_reviews_and_multiple_titles_not_auto_grouped(self):
        rows=[article('1',"Nieuwe Nederlandse serie 'Teststad' aangekondigd"),article('2',"Nieuwe Nederlandse serie 'Haven' aangekondigd"),article('3','Nieuwe Nederlandse series Teststad en Haven aangekondigd'),article('4','Recensie: Nederlandse serie Teststad'),article('5','Beste Nederlandse series: Teststad')]
        out=catalog.catalog(rows)
        self.assertEqual(len(out['series']),2)
        self.assertEqual(len(out['inbox']),1)
        self.assertEqual(len(out['ignored']),2)

    def test_unknown_season_kept_separate(self):
        rows=[article('1',"Nieuwe Nederlandse serie 'Teststad' aangekondigd"),article('2',"Opnames Nederlandse serie 'Teststad' afgerond")]
        productions=catalog.catalog(rows)['series'][0]['productions']
        self.assertEqual({p['kind'] for p in productions},{'Nieuwe serie','Onbekend'})
        self.assertEqual(next(p['status'] for p in productions if p['kind']=='Nieuwe serie'),'Aangekondigd')

    def test_release_date_does_not_imply_produced_or_available(self):
        self.assertEqual(catalog.phase_of('Nieuwe Nederlandse serie vanaf 12 december te zien')[0],'Aangekondigd')
        self.assertEqual(catalog.phase_of('Opnames voor serie Teststad afgerond')[0],'Geproduceerd')
        self.assertEqual(catalog.phase_of('Nieuwe serie gaat niet door')[0],'Onbekend')

    def test_state_not_regressed_by_newer_generic_announcement(self):
        rows=[article('1',"Opnames nieuwe Nederlandse serie 'Teststad' afgerond",'2026-08-01T00:00:00+00:00'),article('2',"Nieuwe Nederlandse serie 'Teststad' aangekondigd",'2026-09-01T00:00:00+00:00')]
        self.assertEqual(catalog.catalog(rows)['series'][0]['productions'][0]['status'],'Geproduceerd')

    def test_manual_link_and_ignore(self):
        rows=[article('1','Onbenoemd persbericht',series_title='Teststad',production_kind='Nieuwe serie',season_number=1,phase='In productie',classification_reviewed=1)]
        self.assertEqual(catalog.catalog(rows)['series'][0]['name'],'Teststad')
        rows[0]['excluded']=1
        self.assertEqual(catalog.catalog(rows)['series'],[])
        self.assertEqual(len(catalog.catalog(rows)['ignored']),1)

    def test_creator_previous_show_not_used_for_new_unnamed_series(self):
        rows=[article('1',"Nieuwe Nederlandse serie 'Teststad' aangekondigd"),article('2',"Team achter Teststad werkt aan nieuwe Nederlandse serie")]
        out=catalog.catalog(rows)
        self.assertEqual(len(out['inbox']),1)
        self.assertEqual(len(out['series'][0]['articles']),1)

    def test_accent_case_and_punctuation_normalization(self):
        rows=[article('1',"Nieuwe Nederlandse serie 'Máxima' aangekondigd"),article('2',"Nieuwe Nederlandse serie 'MAXIMA' in productie")]
        self.assertEqual(len(catalog.catalog(rows)['series']),1)

if __name__=='__main__': unittest.main()
