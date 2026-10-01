import json
import unittest
from unittest.mock import patch
import metadata_catalog
import app
import test_app


def show():
    return {'id':42,'name':'Teststad','url':'https://www.tvmaze.com/shows/42/teststad','language':'Dutch',
            'genres':['Drama'],'type':'Scripted','network':{'name':'NPO 1','country':{'code':'NL'}},
            'externals':{'imdb':'tt1234567','thetvdb':123},'summary':'<p>Een korte synopsis.</p>',
            '_embedded':{'seasons':[{'number':1,'premiereDate':'2026-09-01','episodeOrder':8}],
                         'episodes':[{'season':1,'number':1,'name':'Begin','airdate':'2026-09-01','runtime':45}],
                         'cast':[{'person':{'name':'Anna Vos'},'character':{'name':'Noor'}}]}}


class MetadataTests(unittest.TestCase):
    def test_exact_identity_dutch_language_and_existing_ids_required(self):
        data=show()
        self.assertEqual(metadata_catalog.match([{'show':data}],'Teststad',{'imdb':'tt1234567'})['id'],42)
        for candidates,ids in [([{'show':{**data,'language':'English'}}],{}),
                               ([{'show':{**data,'name':'Teststad UK'}}],{}),
                               ([{'show':data},{'show':{**data,'id':43}}],{}),
                               ([{'show':data}],{'imdb':'tt9999999'})]:
            with self.assertRaises(ValueError):metadata_catalog.match(candidates,'Teststad',ids)

    def test_single_season_data_and_license(self):
        facts=metadata_catalog.facts_for(show(),'Teststad','new:1')
        self.assertEqual(facts['cast']['value'],'Anna Vos | Noor')
        self.assertEqual(facts['episodes']['value'],'8')
        self.assertEqual(facts['runtime']['value'],'45 minuten')
        self.assertEqual(facts['release_date']['value'],'2026-09-01')
        self.assertEqual(facts['languages']['origin'],'tvmaze')
        self.assertEqual(facts['languages']['license_url'],metadata_catalog.LICENSE)
        self.assertNotIn('countries',facts)

    def test_multiple_seasons_do_not_share_cast_synopsis_dates_or_counts(self):
        data=show()
        data['_embedded']['seasons'].append({'number':2,'premiereDate':'2027-01-01','episodeOrder':6})
        facts=metadata_catalog.facts_for(data,'Teststad','season:2')
        self.assertEqual(facts['episodes']['value'],'6')
        self.assertEqual(facts['release_date']['value'],'2027-01-01')
        for key in ('cast','synopsis','runtime','episode_guide'):self.assertNotIn(key,facts)

    def test_unknown_season_cannot_inherit_release_or_cast(self):
        facts=metadata_catalog.facts_for(show(),'Teststad','unknown:?')
        self.assertIn('languages',facts)
        for key in ('cast','synopsis','runtime','release_date','episodes'):self.assertNotIn(key,facts)

    def test_listing_count_is_not_a_confirmed_episode_order(self):
        data=show();data['_embedded']['seasons'][0]['episodeOrder']=None
        self.assertNotIn('episodes',metadata_catalog.facts_for(data,'Teststad','new:1'))


class CatalogueStorageTests(unittest.TestCase):
    # Reuse only the disposable database fixture.
    setUp=test_app.RadarTests.setUp
    tearDown=test_app.RadarTests.tearDown
    def test_catalogue_enrichment_fills_missing_fields_and_caches(self):
        with app.connect() as c:
            app.ingest(c,{'id':'test','name':'Test'},[{'title':'Nieuwe Nederlandse serie Teststad','url':'https://example.org/test','summary':'','published':None,'publisher':''}])
        with patch.object(app,'read_json_page',side_effect=[[{'show':show()}],show()]) as read:
            app.enrich_tvmaze()
            app.enrich_tvmaze()
        self.assertEqual(read.call_count,2)
        group=app.get_catalog()['series'][0]
        self.assertEqual(group['dossiers'][0]['fields']['cast']['value'],'Anna Vos | Noor')
        with app.connect() as c:source=dict(c.execute('SELECT * FROM dossier_sources').fetchone())
        with patch.object(app,'read_json_page',return_value=show()):
            app.import_metadata(group['id'],source['scope'],'Teststad',source['url'],json.loads(source['field_filter']))
        self.assertEqual(app.get_catalog()['series'][0]['dossiers'][0]['fields']['episodes']['value'],'8')


if __name__=='__main__':unittest.main()
