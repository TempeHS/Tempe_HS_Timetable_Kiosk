#!/usr/bin/env python3
"""
Helpers for the generated data files (bell_times.json, calendar.json, liss_info.json).

- write_json_atomic: never leaves a half-written file if the process dies mid-write.
- should_commit: decides whether CI should commit a regenerated file. Unchanged data is
  still committed when its saved timestamp would go stale before the next scheduled run,
  so the kiosk never falls back to XML just because the data hasn't changed.

CLI (used by the GitHub Actions workflows):
    python3 data_freshness.py should-commit --old OLD.json --new NEW.json \
        --source bell_times --margin-days 7 [--config config.json]
Prints "true" or "false" on the last line of stdout; exits 2 if NEW is invalid or empty.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

TIMESTAMP_KEYS = ('generated_at', 'generated', 'timestamp')
DEFAULT_STALE_DAYS = 7


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def get_stale_days(config: Optional[Dict[str, Any]], source: str) -> float:
    """Per-source `dataSources.<source>.stale_days`, else `api.sync_days`, else 7."""
    config = config or {}
    source_days = ((config.get('dataSources') or {}).get(
        source) or {}).get('stale_days')
    if _positive_number(source_days):
        return source_days
    sync_days = (config.get('api') or {}).get('sync_days')
    if _positive_number(sync_days):
        return sync_days
    return DEFAULT_STALE_DAYS


def write_json_atomic(path: str, data: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix='.tmp-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    # Generators run on UTC CI runners, so naive timestamps are treated as UTC.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _payload(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in doc.items() if k != 'metadata'}


def _load_new(new_text: str) -> Dict[str, Any]:
    try:
        doc = json.loads(new_text)
    except (TypeError, ValueError) as e:
        raise ValueError(f'new file is not valid JSON: {e}') from e
    if not isinstance(doc, dict):
        raise ValueError('new file is not a JSON object')
    if not any(isinstance(v, list) and v for v in _payload(doc).values()):
        raise ValueError('new file contains no data')
    return doc


def should_commit(old_text: Optional[str], new_text: str, stale_days: float, margin_days: float,
                  now: Optional[datetime] = None) -> Tuple[bool, str]:
    """Return (commit?, reason). Raises ValueError if the new file is invalid or empty."""
    now = now or datetime.now(timezone.utc)
    new_doc = _load_new(new_text)

    if not old_text:
        return True, 'no previous version'
    try:
        old_doc = json.loads(old_text)
    except ValueError:
        return True, 'previous version is not valid JSON'
    if not isinstance(old_doc, dict):
        return True, 'previous version is not a JSON object'

    if _payload(old_doc) != _payload(new_doc):
        return True, 'data changed'

    metadata = old_doc.get('metadata') or {}
    timestamp = next((t for t in (_parse_timestamp(metadata.get(k))
                     for k in TIMESTAMP_KEYS) if t), None)
    if timestamp is None:
        return True, 'data unchanged but previous timestamp is missing or invalid'

    age_days = (now - timestamp).total_seconds() / 86400
    refresh_at = stale_days - margin_days
    if age_days >= refresh_at:
        return True, (f'data unchanged but timestamp is {age_days:.1f} days old '
                      f'(refresh at {refresh_at:g}, stale at {stale_days:g})')
    return False, f'data unchanged and timestamp is only {age_days:.1f} days old'


def _read_text(path: str) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return f.read()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    cmd = sub.add_parser('should-commit')
    cmd.add_argument('--old', required=True,
                     help='previously committed version (may not exist)')
    cmd.add_argument('--new', required=True, help='freshly generated file')
    cmd.add_argument('--source', required=True,
                     choices=['bell_times', 'calendar', 'liss_info'])
    cmd.add_argument('--config', default='config.json')
    cmd.add_argument('--margin-days', type=float, required=True,
                     help='days until the next scheduled run; refresh before the data would go stale')
    args = parser.parse_args(argv)

    try:
        config = json.loads(_read_text(args.config) or '{}')
    except ValueError as e:
        print(
            f'⚠️  Could not read {args.config}: {e}; using defaults', file=sys.stderr)
        config = {}
    stale_days = get_stale_days(config, args.source)

    try:
        commit, reason = should_commit(_read_text(args.old), _read_text(
            args.new) or '', stale_days, args.margin_days)
    except ValueError as e:
        print(f'❌ {args.new}: {e}', file=sys.stderr)
        return 2

    print(f'{args.source}: {reason}', file=sys.stderr)
    print('true' if commit else 'false')
    return 0


if __name__ == '__main__':
    sys.exit(main())
