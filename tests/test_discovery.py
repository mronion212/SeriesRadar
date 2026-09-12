import unittest
from pathlib import Path
import json
import app
import catalog
import dossier
from test_catalog import article


class DiscoveryTests(unittest.TestCase):
    def test_hitster_passes_ingestion_and_catalog_with_release_facts(self):
        a=article('hitster','Partygame Hitster binnenkort te zien bij RTL',
                  summary='In deze muzikale gameshow spelen bekende Nederlanders. Hitster is vanaf zaterdag 24 oktober om 20.00 uur te zien bij RTL 4 en te streamen bij Videoland.')
        self.assertTrue(app.relevant(a,'broadcast-direct'))
        groups=catalog.catalog([a])['series']
        self.assertEqual(groups[0]['name'],'Hitster')
        self.assertEqual(groups[0]['productions'][0]['status'],'Release gepland')
        f=dossier.extract(a['title']+'\n'+a['summary'],'Hitster',a['url'])
        self.assertEqual(f['release_date']['value'],'24 oktober')
        self.assertEqual(f['networks']['value'],'RTL 4')
        self.assertEqual(f['format']['value'],'Spelshow')

    def test_tvdb_requires_verified_title_id_and_domestic_country(self):
        page='<h1>Sex en de Vinex</h1><ul><li><strong>TheTVDB.com Series ID</strong><span>482393</span></li><li><strong>Original Country</strong><span>The Netherlands</span></li><li><strong>Original Language</strong><span>Dutch</span></li><li><strong>Network</strong><span>Videoland (NL)</span></li></ul>'
        f=dossier.tvdb_facts(page,'Sex en de Vinex','https://thetvdb.com/series/sex-en-de-vinex')
        self.assertEqual(f['tvdb_id']['value'],'482393')
        self.assertEqual(f['languages']['value'],'Dutch')
        for changed in (page.replace('The Netherlands','United States'),page.replace('Sex en de Vinex','Something Else'),page.replace('482393','unknown')):
            with self.assertRaises(ValueError):dossier.tvdb_facts(changed,'Sex en de Vinex','https://thetvdb.com/series/test')

    def test_extended_metadata_keeps_people_out_of_company_field(self):
        text='Sex en de Vinex is een achtdelige dramaserie. Geproduceerd door Pupkin, Vanessa Henneman en Janey van Ierland. Regie ligt in handen van Annemarie van de Mond.\nSynopsis\nEen wijk vol geheimen.'
        f=dossier.extract(text,'Sex en de Vinex','https://example.org')
        self.assertEqual(f['production_companies']['value'],'Pupkin')
        self.assertEqual(f['episodes']['value'],'8')
        self.assertEqual(f['directors']['value'],'Annemarie van de Mond')
        self.assertEqual(f['synopsis']['value'],'Een wijk vol geheimen')
        self.assertNotIn('languages',f)

    def test_requested_sources_and_formats_remain_configured(self):
        sources=json.loads((app.ROOT/'sources.json').read_text(encoding='utf-8'))
        self.assertEqual(len(sources),len({s['id'] for s in sources}))
        for sid in ('filmvandaag','broadcastmagazine','tvgids'):
            self.assertIn('partygame',next(s for s in sources if s['id']==sid)['query'])
        self.assertFalse(app.relevant({'title':'Nieuwe podcastserie over voetbal','summary':''},'broadcast-direct'))

    def test_availability_updates_first_season_but_never_another_season(self):
        rows=[article('1','Nieuwe Videoland-serie BASTA aangekondigd'),
              article('2','De serie BASTA',summary='BASTA is sinds vrijdag 4 september te zien op Videoland.')]
        group=catalog.catalog(rows)['series'][0]
        self.assertEqual(group['productions'][0]['status'],'Beschikbaar')
        rows.append(article('3','Videoland-serie BASTA krijgt tweede seizoen'))
        group=catalog.catalog(rows)['series'][0]
        self.assertEqual(next(p for p in group['productions'] if p['season']==2)['status'],'Aangekondigd')
        self.assertEqual(next(p for p in group['productions'] if p['kind']=='Nieuwe serie')['status'],'Aangekondigd')

    def test_future_release_is_not_streaming_or_completed_filming(self):
        self.assertEqual(catalog.phase_of('BASTA is vanaf vrijdag 4 september in zijn geheel te streamen bij Videoland.')[0],'Release gepland')
        self.assertEqual(catalog.phase_of('BASTA is nu te streamen bij Videoland.')[0],'Beschikbaar')
        self.assertEqual(catalog.phase_of('BASTA is nog niet nu te streamen bij Videoland.')[0],'Onbekend')
