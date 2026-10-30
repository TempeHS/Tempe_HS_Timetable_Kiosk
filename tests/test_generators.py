"""Tests for the Sentral data generators, using a fake API client (no network)."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import generate_bell_times  # noqa: E402
import generate_calendar  # noqa: E402
import generate_liss_info  # noqa: E402


def _paged(items):
    """Return a _make_request-style responder that serves one page then stops."""
    def respond(params):
        return {'data': items if (params or {}).get('offset', 0) == 0 else []}
    return respond


class FakeClient:
    def __init__(self, endpoints, calendar_dates=None):
        self.endpoints = endpoints
        self.calendar_dates = calendar_dates or []

    def _make_request(self, method, endpoint, params=None):
        handler = self.endpoints.get(endpoint)
        if handler is None:
            return None
        return handler(params) if callable(handler) else handler

    def get_timetable_calendar_dates(self, **filters):
        return self.calendar_dates

    def print_request_stats(self):
        pass


DAYS = [
    {'id': 'd1', 'attributes': {'name': 'MonA'}},
    {'id': 'd6', 'attributes': {'name': 'MonB'}},
    {'id': 'dx', 'attributes': {'name': 'Staff Day'}},
]
PERIODS = [{'id': 'p1', 'attributes': {'name': 'P1'}}]


def _pid(pid_id, day_id, start='08:45:00', end='09:40:00'):
    return {
        'id': pid_id,
        'attributes': {'startTime': start, 'endTime': end, 'order': 1},
        'relationships': {'day': {'data': {'id': day_id}}, 'period': {'data': {'id': 'p1'}}},
    }


PERIOD_IN_DAYS = [_pid('pid1', 'd1'), _pid('pid6', 'd6'), _pid('pidx', 'dx')]


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def write_json(self, name, data):
        with open(name, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def read_json(self, name):
        with open(name, encoding='utf-8') as f:
            return json.load(f)


class BellTimesGeneratorTests(TempDirTestCase):
    def run_generator(self, endpoints):
        client = FakeClient(endpoints)
        with mock.patch.object(generate_bell_times.SentralAPIClient, 'from_config', return_value=client):
            return generate_bell_times.generate_bell_times_json(output_file='bell_times.json')

    def full_endpoints(self):
        return {
            'timetables/timetable-day': _paged(DAYS),
            'timetables/timetable-period': _paged(PERIODS),
            'timetables/timetable-period-in-day': _paged(PERIOD_IN_DAYS),
        }

    def test_generated_at_is_the_real_current_time(self):
        success, _, _ = self.run_generator(self.full_endpoints())
        self.assertTrue(success)
        generated = datetime.fromisoformat(self.read_json('bell_times.json')[
                                           'metadata']['generated_at'].replace('Z', '+00:00'))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        self.assertLess(
            abs((datetime.now(timezone.utc) - generated).total_seconds()), 300)

    def test_unknown_day_names_are_skipped_not_mapped_to_monday(self):
        self.run_generator(self.full_endpoints())
        entries = self.read_json('bell_times.json')['bell_times']
        self.assertEqual(sorted((e['DayName'], e['DayNumber'])
                         for e in entries), [('MonA', 1), ('MonB', 6)])

    def test_empty_api_response_fails_and_keeps_existing_file(self):
        self.write_json('bell_times.json', {
                        'metadata': {}, 'bell_times': [{'keep': True}]})
        success, _, _ = self.run_generator({})
        self.assertFalse(success)
        self.assertEqual(self.read_json('bell_times.json')
                         ['bell_times'], [{'keep': True}])


class LissGeneratorTests(TempDirTestCase):
    def endpoints(self, lessons):
        classes = [{'id': f'c{i}', 'attributes': {
            'name': f'7EN{i}', 'externalId': f'7EN {i}'}} for i in range(3)]
        teachers = [{'type': 'timetableTeacher', 'id': 't1',
                     'attributes': {'lastName': 'Smith'}}]
        return {
            'enrolments/staff': _paged([]),
            'timetables/timetable-class': _paged(classes),
            'timetables/timetable-room': _paged([{'id': 'r1', 'attributes': {'name': 'C8'}}]),
            'timetables/timetable-period-in-day': {'data': PERIOD_IN_DAYS},
            'timetables/timetable-day': {'data': DAYS},
            'timetables/timetable-period': {'data': PERIODS},
            'timetables/timetable-class-lesson': lambda p: {
                'data': lessons if p.get('offset', 0) == 0 else [],
                'included': teachers,
            },
        }

    @staticmethod
    def lesson(lesson_id, class_id, pid_id):
        return {
            'id': lesson_id,
            'relationships': {
                'class': {'data': {'id': class_id}},
                'room': {'data': {'id': 'r1'}},
                'periodInDay': {'data': {'id': pid_id}},
                'timetableTeachers': {'data': [{'id': 't1'}]},
            },
        }

    def run_generator(self, lessons):
        # calendar.json only covers week A, like the real 7-day file.
        self.write_json('calendar.json', {'calendar': [
            {'date': '2026-10-26', 'day_name': 'MonA',
                'day_number': 1, 'is_school_day': True},
        ]})
        client = FakeClient(self.endpoints(lessons),
                            calendar_dates=[{'attributes': {}}])
        with mock.patch.object(generate_liss_info.SentralAPIClient, 'from_config', return_value=client):
            return generate_liss_info.generate_liss_info_json(days_limit=7, output_file='liss_info.json')

    def test_includes_every_cycle_day_not_just_days_in_calendar_json(self):
        success, _, _ = self.run_generator(
            [self.lesson('l1', 'c0', 'pid1'), self.lesson('l6', 'c1', 'pid6')])
        self.assertTrue(success)
        days = sorted(e['DayNumber'] for e in self.read_json(
            'liss_info.json')['timetable_data'])
        self.assertEqual(days, [1, 6])

    def test_unknown_day_names_are_skipped_not_mapped_to_monday(self):
        self.run_generator([self.lesson('l1', 'c0', 'pid1'),
                           self.lesson('lx', 'c2', 'pidx')])
        codes = [e['ClassCode']
                 for e in self.read_json('liss_info.json')['timetable_data']]
        self.assertEqual(codes, ['7EN0'])

    def test_lesson_without_teacher_does_not_abort_generation(self):
        no_teacher = self.lesson('l1', 'c0', 'pid1')
        no_teacher['relationships']['timetableTeachers'] = {'data': []}
        success, _, _ = self.run_generator(
            [no_teacher, self.lesson('l6', 'c1', 'pid6')])
        self.assertTrue(success)
        entries = self.read_json('liss_info.json')['timetable_data']
        self.assertEqual(entries[0]['TeacherCode'], 'UNKN')
        self.assertIsNone(entries[0]['TeacherId'])

    def test_no_lessons_fails_and_keeps_existing_file(self):
        self.write_json('liss_info.json', {
                        'metadata': {}, 'timetable_data': [{'keep': True}]})
        success, _, _ = self.run_generator([])
        self.assertFalse(success)
        self.assertEqual(self.read_json('liss_info.json')[
                         'timetable_data'], [{'keep': True}])


class CalendarGeneratorConfigTests(TempDirTestCase):
    def days_ahead_used(self, config):
        with mock.patch.object(generate_calendar, 'load_config', return_value=config), \
                mock.patch.object(generate_calendar, 'generate_calendar_json', return_value=([], 204)) as gen, \
                mock.patch.object(generate_calendar, 'log_generation_run'):
            with self.assertRaises(SystemExit):
                generate_calendar.main()
        return gen.call_args[0][0] if gen.call_args[0] else gen.call_args[1]['days_ahead']

    def test_reads_days_ahead_from_data_sources(self):
        config = {'api': {'calendar_source': {'days_ahead': 7}},
                  'dataSources': {'calendar': {'days_ahead': 30}}}
        self.assertEqual(self.days_ahead_used(config), 30)

    def test_falls_back_to_api_calendar_source(self):
        self.assertEqual(self.days_ahead_used(
            {'api': {'calendar_source': {'days_ahead': 14}}}), 14)

    def test_defaults_to_at_least_14_days_so_next_week_is_covered(self):
        self.assertGreaterEqual(self.days_ahead_used({'api': {}}), 14)

    def test_real_config_covers_more_than_two_weeks(self):
        with open(os.path.join(ROOT, 'config.json'), encoding='utf-8') as f:
            self.assertGreaterEqual(self.days_ahead_used(json.load(f)), 14)


if __name__ == '__main__':
    unittest.main()
