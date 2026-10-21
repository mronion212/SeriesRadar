import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('release',Path(__file__).resolve().parents[1]/'.github'/'release.py')
release=importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_first_release_and_successive_versions(self):
        release.check_sequence('0.1.0')
        for previous,current in [('0.1.0','0.1.1'),('0.1.9','0.2.0'),('0.9.4','1.0.0')]:
            release.check_sequence(current,previous)

    def test_duplicate_skipped_and_invalid_versions_are_rejected(self):
        for version in ('v0.1.0','01.1.0','0.1.01','1.0','0.1.0-dev'):
            with self.assertRaises(ValueError):release.parse_version(version)
        for version in ('0.1.0','0.1.2','0.3.0','2.0.0','0.0.9'):
            with self.assertRaises(ValueError):release.check_sequence(version,'0.1.0')

    def test_notes_match_only_the_selected_version(self):
        notes='# Wijzigingen\n\n## [0.1.1] - 2026-10-22\n\n- Nieuw.\n\n## [0.1.0] - 2026-10-21\n\n- Eerste.\n'
        self.assertEqual(release.release_notes(notes,'0.1.1'),'- Nieuw.\n')
        self.assertEqual(release.release_notes(notes,'0.1.0'),'- Eerste.\n')
        with self.assertRaises(ValueError):release.release_notes(notes,'0.1.2')

    def test_empty_notes_are_rejected(self):
        with self.assertRaises(ValueError):release.release_notes('## [0.1.0] - 2026-10-21\n\n','0.1.0')
