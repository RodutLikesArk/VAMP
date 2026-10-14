import os
import tempfile
import unittest
from unittest.mock import patch

from pc.settings import load_settings, save_settings, validate_url, data_dir


class SettingsTests(unittest.TestCase):
    def test_accept_robot_and_simulator_addresses(self):
        self.assertEqual(validate_url(' http://127.0.0.1:8765/ '), 'http://127.0.0.1:8765')
        self.assertEqual(validate_url('http://192.168.10.2:8765'), 'http://192.168.10.2:8765')

    def test_reject_malformed_addresses(self):
        for address in ['file:///tmp/test', '192.168.10.2', 'http://u:p@host', 'http://host/api', 'http://host:bad', 'http://host?token=abc']:
            with self.subTest(address=address), self.assertRaises(ValueError):
                validate_url(address)

    def test_roundtrip_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'APPDATA': folder}):
            save_settings('http://127.0.0.1:8765', 'test-token', '')
            saved = load_settings()
            self.assertEqual(saved['url'], 'http://127.0.0.1:8765')
            self.assertEqual(saved['token'], 'test-token')
            (data_dir() / 'operator.json').write_text('{broken')
            self.assertEqual(load_settings()['url'], 'http://192.168.10.2:8765')
            (data_dir() / 'operator.json').write_text('{"url": "invalid"}')
            self.assertEqual(load_settings()['url'], 'http://192.168.10.2:8765')

    def test_empty_token_rejected(self):
        with self.assertRaises(ValueError):
            save_settings('http://host', '')
