import json
import socket
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import app

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.previous=app.DB
        app.DB=Path(self.temp.name)/'test.sqlite3'
        app.init()

    def tearDown(self):
        app.DB=self.previous
        self.temp.cleanup()

    def test_source_override_survives_database_reopen(self):
        source=app.validate_source({'id':'rtl','name':'Eigen RTL zoekopdracht','mode':'search','value':'site:rtl.nl "nieuwe serie"','enabled':False})
        with app.connect() as c:
            c.execute('INSERT INTO source_config VALUES (?,?)',(source['id'],json.dumps(source)))
        app.init()
        found=next(s for s in app.sources() if s['id']=='rtl')
        self.assertEqual(found['name'],'Eigen RTL zoekopdracht')
        self.assertFalse(found['enabled'])
        self.assertEqual(sum(s['id']=='rtl' for s in app.sources()),1)

    def test_private_url_rejected_including_redirect(self):
        for url in ['http://example.org/feed','https://user:pass@example.org/feed','https://example.org:8080/feed']:
            with self.assertRaises(ValueError): app.public_url(url)
        with patch.object(socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError): app.public_url('https://example.org/feed')
            with self.assertRaises(ValueError): app.PublicRedirect().redirect_request(None,None,302,'',{},'https://example.org/feed')

    def test_source_form_validation(self):
        with self.assertRaises(ValueError): app.validate_source({'name':'','mode':'search','value':'series'})
        with self.assertRaises(ValueError): app.validate_source({'id':'../oops','name':'Test','mode':'search','value':'series'})
        s=app.validate_source({'name':'Test','mode':'search','value':'site:test.nl serie'})
        self.assertTrue(s['id'].startswith('custom-'))

if __name__=='__main__': unittest.main()
