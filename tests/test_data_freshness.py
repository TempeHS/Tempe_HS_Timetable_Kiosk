"""Tests for the commit decision used by the GitHub Actions data workflows."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import data_freshness  # noqa: E402

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
BELLS = [{'DayNumber': 1, 'Period': 'P1',
          'StartTime': '08:45', 'EndTime': '09:40'}]


def bell_file(age_days=None, data=BELLS, timestamp=None, key='generated_at'):
    metadata = {'source': 'Sentral API'}
    if timestamp is None and age_days is not None:
        timestamp = (NOW - timedelta(days=age_days)).isoformat()
    if timestamp is not None:
        metadata[key] = timestamp
    return json.dumps({'metadata': metadata, 'bell_times': data})


def decide(old, new, stale_days=30, margin_days=7):
    return data_freshness.should_commit(old, new, stale_days=stale_days, margin_days=margin_days, now=NOW)[0]


class ShouldCommitTests(unittest.TestCase):
    def test_new_file_with_no_previous_version_is_committed(self):
        self.assertTrue(decide(None, bell_file(0)))

    def test_changed_bell_times_are_committed(self):
        changed = [dict(BELLS[0], StartTime='08:50')]
        self.assertTrue(decide(bell_file(1), bell_file(0, data=changed)))

    def test_unchanged_and_recent_is_skipped(self):
        self.assertFalse(decide(bell_file(10), bell_file(0)))

    def test_unchanged_but_would_go_stale_before_next_weekly_run_is_committed(self):
        self.assertFalse(decide(bell_file(22.9), bell_file(0)))
        self.assertTrue(decide(bell_file(23), bell_file(0)))

    def test_unchanged_and_already_stale_is_committed(self):
        self.assertTrue(decide(bell_file(31), bell_file(0)))

    def test_old_hardcoded_2024_timestamp_is_committed(self):
        self.assertTrue(
            decide(bell_file(timestamp='2024-01-01T00:00:00Z'), bell_file(0)))

    def test_missing_or_invalid_old_timestamp_is_committed(self):
        self.assertTrue(decide(bell_file(), bell_file(0)))
        self.assertTrue(decide(bell_file(timestamp='garbage'), bell_file(0)))

    def test_corrupt_old_file_is_committed(self):
        self.assertTrue(decide('{not json', bell_file(0)))
        self.assertTrue(decide('', bell_file(0)))

    def test_metadata_only_changes_do_not_count_as_data_changes(self):
        old = json.loads(bell_file(2))
        old['metadata']['date_range'] = '2026-10-28 to 2026-11-04'
        self.assertFalse(decide(json.dumps(old), bell_file(0)))

    def test_naive_timestamps_and_calendar_generated_key_are_supported(self):
        naive = (NOW - timedelta(days=2)).replace(tzinfo=None).isoformat()
        self.assertFalse(decide(bell_file(timestamp=naive), bell_file(0)))
        self.assertFalse(decide(bell_file(2, key='generated'),
                         bell_file(0, key='generated')))

    def test_liss_rule_uses_sync_days_with_one_day_margin(self):
        self.assertFalse(decide(bell_file(5.5), bell_file(0),
                         stale_days=7, margin_days=1))
        self.assertTrue(decide(bell_file(6), bell_file(0),
                        stale_days=7, margin_days=1))

    def test_invalid_or_empty_new_file_raises(self):
        with self.assertRaises(ValueError):
            decide(bell_file(1), '{bad json')
        with self.assertRaises(ValueError):
            decide(bell_file(1), bell_file(0, data=[]))
        with self.assertRaises(ValueError):
            decide(bell_file(1), json.dumps({'metadata': {}}))


class StaleDaysTests(unittest.TestCase):
    def test_bell_times_use_their_own_threshold(self):
        config = {'api': {'sync_days': 7}, 'dataSources': {
            'bell_times': {'stale_days': 30}}}
        self.assertEqual(data_freshness.get_stale_days(
            config, 'bell_times'), 30)
        self.assertEqual(data_freshness.get_stale_days(config, 'liss_info'), 7)
        self.assertEqual(data_freshness.get_stale_days({}, 'calendar'), 7)

    def test_real_config_sets_30_days_for_bell_times(self):
        with open(os.path.join(ROOT, 'config.json'), encoding='utf-8') as f:
            self.assertEqual(data_freshness.get_stale_days(
                json.load(f), 'bell_times'), 30)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    def run_cli(self, old, new):
        config = self.write('config.json', json.dumps(
            {'api': {'sync_days': 7}, 'dataSources': {'bell_times': {'stale_days': 30}}}))
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, 'data_freshness.py'), 'should-commit',
             '--old', old, '--new', new, '--source', 'bell_times', '--config', config, '--margin-days', '7'],
            capture_output=True, text=True)

    def test_prints_true_when_old_file_is_missing(self):
        result = self.run_cli(os.path.join(
            self.tmp.name, 'missing.json'), self.write('new.json', bell_file(0)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], 'true')

    def test_prints_false_for_unchanged_recent_file(self):
        recent = json.dumps({'metadata': {'generated_at': datetime.now(
            timezone.utc).isoformat()}, 'bell_times': BELLS})
        result = self.run_cli(self.write('old.json', recent),
                              self.write('new.json', recent))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], 'false')

    def test_exits_non_zero_for_invalid_new_file(self):
        result = self.run_cli(self.write(
            'old.json', bell_file(1)), self.write('new.json', '{bad'))
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
