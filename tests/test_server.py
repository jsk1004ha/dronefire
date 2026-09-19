import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from firelab.server import make_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / 'web').mkdir()
        (cls.root / 'web' / 'index.html').write_text('workbench', encoding='utf-8')
        cls.server = make_server(cls.root, 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def call(self, path, body=None, headers=None):
        hdr = {'Content-Type': 'application/json'}
        hdr.update(headers or {})
        req = Request(self.url + path, data=body.encode() if body is not None else None, headers=hdr)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read().decode()

    def test_loopback_health_and_static(self):
        self.assertEqual(self.call('/api/health')[0], 200)
        self.assertEqual(self.call('/')[1], 'workbench')
        self.assertEqual(self.call('/../CONTRACT.md')[0], 404)

    def test_foreign_host_and_origin_rejected(self):
        self.assertEqual(self.call('/api/health', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.call('/api/run', '{}', {'Origin': 'https://evil.example'})[0], 403)

    def test_invalid_configuration_never_queues(self):
        for payload in ['{"scenario":{"duration_s":-1}}', '{"unknown":1}', '{"scenario":{"dt_s":NaN}}', '[]']:
            self.assertEqual(self.call('/api/run', payload)[0], 400)
        self.assertEqual(self.call('/api/validate', '{}')[0], 200)

    def test_missing_data_and_synergy_cannot_fabricate_score(self):
        self.assertEqual(self.call('/api/analyze', '{}')[0], 400)
        code, raw = self.call('/api/synergy', json.dumps({'records': [], 'synergy': {
            'control_id': 'C0', 'combination_id': 'M1_M2', 'partial_single_ids': {'M1': 'M1', 'M2': 'M2'}}}))
        self.assertEqual(code, 200)
        result = json.loads(raw)
        self.assertFalse(result['eligible'])
        self.assertIsNone(result['additive_synergy_J_m2']['value'])

    def test_mime_required(self):
        self.assertEqual(self.call('/api/run', '{}', {'Content-Type': 'text/plain'})[0], 415)

    def test_campaign_validation_and_native_analysis_fail_closed(self):
        self.assertEqual(self.call('/api/campaign/defaults')[0], 200)
        self.assertEqual(self.call('/api/campaign/run', '{"omp_threads":true}')[0], 400)
        self.assertEqual(self.call('/api/study/analyze', '{"records":[]}')[0], 400)
        self.assertEqual(self.call('/api/fieldsets/../../secret.json')[0], 404)
