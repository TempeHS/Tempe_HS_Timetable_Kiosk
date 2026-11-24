#!/usr/bin/env python3
"""
Weekly health check for the Sentral endpoints the kiosk depends on.

Runs the real generators into a temporary folder (nothing in the repo is changed) and checks
that the data they produce, plus the raw daily-lesson feed, still look the way the kiosk expects.
Exits 1 and writes a Markdown report if anything looks wrong.

Usage: python check_sentral_api.py [report.md]
"""

import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import generate_bell_times
import generate_calendar
import generate_liss_info
from sentral_rest_client import SentralAPIClient

# Documented values for timetableDailyLesson.type in .dev/openapi.json.
KNOWN_DAILY_TYPES = {'Class', 'Duty', 'Study', 'RollClass', 'RTO', 'StaffMeeting', 'ExtraCurricular',
                     'Excursion', 'Exam', 'Cancellation', 'Incursion', 'Event', 'Cover', 'OnCall'}
CYCLE_DAYS = set(range(1, 11))
MIN_LESSON_RATIO = 0.8
MAX_UNKNOWN_TEACHER_RATIO = 0.25


def check_bell_times(doc: Optional[Dict[str, Any]]) -> List[str]:
    entries = (doc or {}).get('bell_times') or []
    if not entries:
        return ['Bell times: no entries generated']
    problems = []
    missing_days = CYCLE_DAYS - {e.get('DayNumber') for e in entries}
    if missing_days:
        problems.append(f'Bell times: no periods for cycle days {sorted(missing_days)}')
    incomplete = [e for e in entries if not (e.get('Period') and e.get('StartTime') and e.get('EndTime'))]
    if incomplete:
        problems.append(f'Bell times: {len(incomplete)} entries missing Period/StartTime/EndTime')
    return problems


def check_calendar(entries: List[Dict[str, Any]], days_ahead: int) -> List[str]:
    if not entries:
        return ['Calendar: no entries generated']
    problems = []
    if len(entries) < days_ahead:
        problems.append(f'Calendar: only {len(entries)} days returned for a {days_ahead}-day range')
    bad_school_days = [e['date'] for e in entries if e.get('is_school_day') and e.get('day_number') not in CYCLE_DAYS]
    if bad_school_days:
        problems.append(f'Calendar: school days without a cycle day 1-10: {bad_school_days}')
    return problems


def check_liss(doc: Optional[Dict[str, Any]], previous_count: int, school_dates: List[str]) -> List[str]:
    lessons = (doc or {}).get('timetable_data') or []
    if not lessons:
        return ['Timetable: no cycle lessons generated']
    problems = []
    if previous_count and len(lessons) < previous_count * MIN_LESSON_RATIO:
        problems.append(f'Timetable: {len(lessons)} cycle lessons, down from {previous_count} in the committed file')
    missing_days = CYCLE_DAYS - {l.get('DayNumber') for l in lessons}
    if missing_days:
        problems.append(f'Timetable: no lessons for cycle days {sorted(missing_days)}')
    unknown_teachers = sum(1 for l in lessons if l.get('TeacherCode') in (None, '', 'UNKN'))
    if unknown_teachers > len(lessons) * MAX_UNKNOWN_TEACHER_RATIO:
        problems.append(f'Timetable: {unknown_teachers} of {len(lessons)} cycle lessons have no teacher')

    changes = (doc or {}).get('daily_changes')
    if not isinstance(changes, list):
        problems.append('Daily changes: missing from generated file')
    elif school_dates:
        dates_with_classes = {c.get('Date') for c in changes if c.get('Type') == 'Class'}
        missing = [d for d in school_dates if d not in dates_with_classes]
        if missing:
            problems.append(f'Daily changes: no class records for school days {missing} - the daily-lesson feed may have changed')
    return problems


def check_daily_feed(records: List[Dict[str, Any]]) -> List[str]:
    problems = []
    no_date = sum(1 for r in records if not (r.get('attributes') or {}).get('date'))
    if no_date:
        problems.append(f'Daily feed: {no_date} records have no date')
    types = Counter((r.get('attributes') or {}).get('type') for r in records)
    unknown = {t: n for t, n in types.items() if t not in KNOWN_DAILY_TYPES}
    if unknown:
        problems.append(f'Daily feed: unknown change types {unknown} - the generator ignores these')

    unrecognised = Counter()
    for r in records:
        attrs = r.get('attributes') or {}
        rels = r.get('relationships') or {}
        has = lambda k: bool((rels.get(k) or {}).get('data'))
        if attrs.get('type') == 'Cancellation' and has('period') and not has('class'):
            name = attrs.get('name') or ''
            if not generate_liss_info.CANCELLATION_GROUP_PATTERN.match(name):
                unrecognised[name] += 1
    if unrecognised:
        problems.append(f'Daily feed: cancellations the kiosk cannot apply (no class, unrecognised name): {dict(unrecognised)}')
    return problems


def fetch_daily_feed(client: SentralAPIClient, date_from: str, date_to: str) -> Optional[List[Dict[str, Any]]]:
    records, offset, limit = [], 0, 200
    while True:
        response = client._make_request('GET', 'timetables/timetable-daily-lesson',
                                        {'from': date_from, 'to': date_to, 'limit': limit, 'offset': offset})
        if not response or 'data' not in response:
            return None
        records.extend(response['data'])
        if len(response['data']) < limit:
            return records
        offset += limit


def read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def run_checks(tmp: str) -> Dict[str, List[str]]:
    results: Dict[str, List[str]] = {}

    ok, _, _ = generate_bell_times.generate_bell_times_json(output_file=os.path.join(tmp, 'bell_times.json'))
    results['Bell times'] = check_bell_times(read_json(os.path.join(tmp, 'bell_times.json'))) if ok else ['Bell times: generator failed']

    days_ahead = generate_calendar.get_days_ahead(generate_calendar.load_config() or {})
    calendar, _ = generate_calendar.generate_calendar_json(days_ahead)
    results['Calendar'] = check_calendar(calendar, days_ahead)

    today = datetime.now(ZoneInfo('Australia/Sydney')).date()
    date_from, date_to = today.isoformat(), (today + timedelta(days=7)).isoformat()
    school_dates = [e['date'] for e in calendar if e.get('is_school_day') and date_from <= e.get('date', '') <= date_to]

    previous = read_json('liss_info.json') or {}
    ok, _, _ = generate_liss_info.generate_liss_info_json(days_limit=7, output_file=os.path.join(tmp, 'liss_info.json'))
    results['Timetable'] = (check_liss(read_json(os.path.join(tmp, 'liss_info.json')),
                                       len(previous.get('timetable_data') or []), school_dates)
                            if ok else ['Timetable: generator failed (see log above)'])

    client = SentralAPIClient.from_config('config.json')
    feed = fetch_daily_feed(client, date_from, date_to) if client else None
    results['Daily feed'] = check_daily_feed(feed) if feed is not None else ['Daily feed: request failed']
    return results


def format_report(results: Dict[str, List[str]]) -> str:
    lines = ['## Sentral API health check', '']
    for area, problems in results.items():
        lines.append(f"- {'❌' if problems else '✅'} **{area}**")
        lines.extend(f'  - {p}' for p in problems)
    return '\n'.join(lines) + '\n'


def main() -> int:
    report_path = sys.argv[1] if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory() as tmp:
        results = run_checks(tmp)
    report = format_report(results)
    print('\n' + report)
    for path in filter(None, (report_path, os.getenv('GITHUB_STEP_SUMMARY'))):
        with open(path, 'a', encoding='utf-8') as f:
            f.write(report)
    return 1 if any(results.values()) else 0


if __name__ == '__main__':
    sys.exit(main())
