"""Security regression tests for the development LISS bell times client."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest import mock


CLIENT_PATH = Path(__file__).resolve(
).parents[1] / '.dev' / 'liss_bell_times.py'
SPEC = importlib.util.spec_from_file_location(
    'dev_liss_bell_times', CLIENT_PATH)
liss_bell_times = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(liss_bell_times)


class LissBellTimesLoggingTests(unittest.TestCase):
    def test_debug_logs_exclude_credentials_without_changing_request(self):
        username = 'sensitive-test-user'
        password = 'sensitive-test-password'
        for use_environment in (False, True):
            for structure in ('', 'Main'):
                with self.subTest(environment=use_environment, structure=structure):
                    config = {'liss': {
                        'endpoint': 'https://example.invalid/liss',
                        'school': 'Test School',
                        'tt_structure': structure,
                    }}
                    if use_environment:
                        config['liss'].update({
                            'username_env': 'TEST_LISS_USERNAME',
                            'password_env': 'TEST_LISS_PASSWORD',
                        })
                    else:
                        config['liss'].update({
                            'username': username, 'password': password,
                        })

                    with mock.patch.object(
                        liss_bell_times.LissBellTimesFetcher,
                        'load_config', return_value=config,
                    ), mock.patch.dict(os.environ, {
                        'TEST_LISS_USERNAME': username,
                        'TEST_LISS_PASSWORD': password,
                    }), mock.patch.object(liss_bell_times.requests, 'post') as post:
                        post.return_value.status_code = 200
                        post.return_value.json.return_value = {'result': []}
                        fetcher = liss_bell_times.LissBellTimesFetcher()

                        with self.assertLogs(fetcher.logger, level='DEBUG') as logs:
                            self.assertEqual(fetcher.get_bell_times(), [])

                        post.assert_called_once()
                        request = post.call_args.kwargs['json']
                        self.assertEqual(
                            request['method'], 'liss.getBellTimes')
                        self.assertEqual(
                            request['params'][0]['UserName'], username)
                        self.assertEqual(
                            request['params'][0]['Password'], password)
                        self.assertEqual(request['params'][1:], [
                                         structure] if structure else [])
                        output = '\n'.join(logs.output)
                        self.assertIn('liss.getBellTimes', output)
                        self.assertNotIn(username, output)
                        self.assertNotIn(password, output)


if __name__ == '__main__':
    unittest.main()
