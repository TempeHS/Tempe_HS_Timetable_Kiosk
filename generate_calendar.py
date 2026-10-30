#!/usr/bin/env python3
"""
Tempe High School Timetable Kiosk - Calendar Generator
Copyright (C) 2025 TempeHS

This script generates calendar.json from Sentral API data in a format
similar to calendar.xml structure for the timetable kiosk.

Usage:
    python generate_calendar.py
"""

import sys
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sentral_rest_client import SentralAPIClient, load_config
from data_freshness import write_json_atomic

DEFAULT_DAYS_AHEAD = 30


def get_days_ahead(config: Dict[str, Any]) -> int:
    """dataSources.calendar.days_ahead, then api.calendar_source.days_ahead, then 30."""
    candidates = [
        ((config.get('dataSources') or {}).get(
            'calendar') or {}).get('days_ahead'),
        ((config.get('api') or {}).get('calendar_source') or {}).get('days_ahead'),
    ]
    for value in candidates:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return DEFAULT_DAYS_AHEAD


def log_generation_run(response_code: int, start_date: str, end_date: str, validation_result: str, log_file: str = '.logs/calendar_generation.log'):
    """
    Log generation run details to a log file.

    Args:
        response_code (int): HTTP response code from API
        start_date (str): Start date of data range
        end_date (str): End date of data range  
        validation_result (str): Result of data validation
        log_file (str): Log file path
    """
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} | Response: {response_code} | Range: {start_date} to {end_date} | Validation: {validation_result}\n"

        # Ensure logs directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}")


def validate_calendar_data(calendar_data: List[Dict[str, Any]]) -> str:
    """
    Validate that calendar data matches required pattern.

    Args:
        calendar_data (list): Calendar data to validate

    Returns:
        str: Validation result description
    """
    if not calendar_data:
        return "FAILED - No data generated"

    required_fields = ['date', 'day_name',
                       'day_number', 'day_type', 'is_school_day']
    validation_issues = []

    for i, entry in enumerate(calendar_data[:5]):  # Check first 5 entries
        for field in required_fields:
            if field not in entry:
                validation_issues.append(
                    f"Missing field '{field}' in entry {i+1}")

    # Check date format
    for i, entry in enumerate(calendar_data[:3]):  # Check first 3 entries
        date_str = entry.get('date', '')
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            validation_issues.append(
                f"Invalid date format in entry {i+1}: {date_str}")

    if validation_issues:
        return f"FAILED - {len(validation_issues)} issues: {', '.join(validation_issues[:3])}"
    else:
        return f"PASSED - {len(calendar_data)} entries validated successfully"


def load_day_type_mapping() -> Dict[int, str]:
    """
    Load day type ID to name mapping from Sentral API.

    Returns:
        Dictionary mapping day type IDs to day names
    """
    client = SentralAPIClient.from_config()
    if not client:
        return {}

    try:
        # Get day type mapping with pagination
        day_types = []
        offset = 0
        limit = 50

        while True:
            response = client._make_request(
                'GET', 'timetables/timetable-day', params={'limit': limit, 'offset': offset})
            if not response or 'data' not in response:
                break

            batch = response.get('data', [])
            if not batch:
                break

            day_types.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        if day_types:
            mapping = {}
            for day_type in day_types:
                day_id = day_type.get('id')
                name = day_type.get('attributes', {}).get('name')
                if day_id and name:
                    mapping[day_id] = name
            return mapping
    except Exception as e:
        print(f"Error loading day type mapping: {e}")

    return {}


def load_xml_calendar_fallback() -> Dict[str, Dict[str, Any]]:
    """
    Load calendar.xml as fallback data for day names and numbers.

    Returns:
        Dictionary mapping dates to calendar information
    """
    xml_map = {}

    try:
        with open('calendar.xml', 'r', encoding='utf-8') as f:
            xml_content = f.read()

        # Extract calendar data using regex
        date_pattern = r'<dateTime\.iso8601>(\d{8}T\d{2}:\d{2}:\d{2})</dateTime\.iso8601>'
        day_name_pattern = r'<name>DayName</name>\s*<value>([^<]+)</value>'
        day_number_pattern = r'<name>DayNumber</name>\s*<value>\s*<i4>(\d+)</i4>'

        dates = re.findall(date_pattern, xml_content)
        day_names = re.findall(day_name_pattern, xml_content)
        day_numbers = re.findall(day_number_pattern, xml_content)

        for i, date_str in enumerate(dates):
            if i < len(day_names) and i < len(day_numbers):
                date = date_str[:8]  # YYYYMMDD
                formatted_date = f'{date[:4]}-{date[4:6]}-{date[6:8]}'
                xml_map[formatted_date] = {
                    'day_name': day_names[i],
                    'day_number': int(day_numbers[i]),
                    'original_date': date_str
                }

    except Exception as e:
        print(f"Warning: Could not load calendar.xml fallback: {e}")

    return xml_map


def generate_calendar_json(days_ahead: int = 7) -> tuple[List[Dict[str, Any]], int]:
    """
    Generate calendar JSON data from Sentral API for the specified number of days.

    Args:
        days_ahead (int): Number of days ahead to generate calendar for

    Returns:
        Tuple of (List of calendar entries in JSON format, HTTP response code)
    """
    print(f"🗓️  Generating calendar data for {days_ahead} days...")

    # Initialize client
    client = SentralAPIClient.from_config()
    if not client:
        print("❌ Failed to initialize Sentral API client")
        return [], 0

    # Get date range
    today = datetime.now()
    end_date = today + timedelta(days=days_ahead)

    date_from = today.strftime('%Y-%m-%d')
    date_to = end_date.strftime('%Y-%m-%d')

    print(f"📅 Date range: {date_from} to {date_to}")

    # Load day type mapping
    day_type_mapping = load_day_type_mapping()
    print(f"📋 Loaded {len(day_type_mapping)} day type mappings")

    # Load XML calendar as fallback
    xml_fallback = load_xml_calendar_fallback()
    print(f"📄 Loaded {len(xml_fallback)} XML fallback entries")

    # Get calendar data from API
    response_code = 200  # Default success code
    try:
        calendar_data = client.get_timetable_calendar_dates(
            **{'from': date_from, 'to': date_to}
        )

        if not calendar_data:
            print("❌ No calendar data received from API")
            response_code = 204  # No content
            return [], response_code

        print(f"✅ Retrieved {len(calendar_data)} calendar records from API")

    except Exception as e:
        print(f"❌ Error fetching calendar data: {e}")
        response_code = 500  # Server error
        return [], response_code

    # Process calendar data
    calendar_json = []

    for record in calendar_data:
        attrs = record.get('attributes', {})
        date = attrs.get('date')
        cycle = attrs.get('cycle')
        interval = attrs.get('interval', '1')
        is_daily_timetable = attrs.get('isDailyTimetable', False)

        # Get fallback data from XML
        xml_data = xml_fallback.get(date, {})
        xml_day_name = xml_data.get('day_name', 'unknown')
        xml_day_number = xml_data.get('day_number', 0)

        # Determine day type
        if cycle and is_daily_timetable:
            # School day with cycle
            day_name = xml_day_name if xml_day_name != 'unknown' else f'Cycle{cycle}'
            day_number = xml_day_number if xml_day_number > 0 else cycle
            day_type = 'school'
        elif is_daily_timetable and not cycle:
            # Special school day without cycle
            day_name = xml_day_name if xml_day_name != 'unknown' else 'special'
            day_number = xml_day_number if xml_day_number > 0 else 0
            day_type = 'school'
        else:
            # Non-school day
            day_name = xml_day_name if xml_day_name != 'unknown' else 'non-school'
            day_number = 0
            day_type = xml_day_name if xml_day_name in [
                'weekend', 'holiday'] else 'non-school'

        # Create calendar entry
        calendar_entry = {
            'date': date,
            'day_name': day_name,
            'day_number': day_number,
            'day_type': day_type,
            'cycle': cycle,
            'interval': interval,
            'is_daily_timetable': is_daily_timetable,
            'is_school_day': is_daily_timetable and cycle is not None,
            'source': 'sentral_api'
        }

        calendar_json.append(calendar_entry)

    return calendar_json, response_code


def save_calendar_json(calendar_data: List[Dict[str, Any]], filename: str = 'calendar.json'):
    """
    Save calendar data to JSON file.

    Args:
        calendar_data (list): Calendar data to save
        filename (str): Output filename
    """
    try:
        write_json_atomic(filename, {
            'metadata': {
                'generated': datetime.now().isoformat(),
                'source': 'sentral_api',
                'total_days': len(calendar_data),
                'date_range': {
                    'from': calendar_data[0]['date'] if calendar_data else None,
                    'to': calendar_data[-1]['date'] if calendar_data else None
                }
            },
            'calendar': calendar_data
        })

        print(f"💾 Calendar data saved to {filename}")
        return True

    except Exception as e:
        print(f"❌ Error saving calendar data: {e}")
        return False


def main():
    """Main function to generate calendar.json"""
    print("🗓️  Tempe HS Timetable Kiosk - Calendar Generator")
    print("=" * 55)

    # Load configuration
    config = load_config()
    if not config:
        print("❌ Failed to load configuration")
        sys.exit(1)

    # Get calendar source settings
    calendar_config = (config.get('api') or {}).get('calendar_source', {})
    days_ahead = get_days_ahead(config)

    print(f"⚙️  Configuration:")
    print(f"   Days ahead: {days_ahead}")
    print(f"   Use API: {calendar_config.get('use_api', True)}")
    print(
        f"   Fallback to XML: {calendar_config.get('fallback_to_xml', True)}")

    # Generate calendar data
    calendar_data, response_code = generate_calendar_json(days_ahead)

    # Get date range for logging
    start_date = calendar_data[0]['date'] if calendar_data else 'N/A'
    end_date = calendar_data[-1]['date'] if calendar_data else 'N/A'

    # Validate data
    validation_result = validate_calendar_data(calendar_data)

    if calendar_data:
        # Save to file
        if save_calendar_json(calendar_data):
            print(
                f"✅ Successfully generated calendar.json with {len(calendar_data)} entries")

            # Log the generation run
            log_generation_run(response_code, start_date,
                               end_date, validation_result)

            # Show summary
            school_days = sum(
                1 for entry in calendar_data if entry['is_school_day'])
            non_school_days = len(calendar_data) - school_days

            print(f"\n📊 Summary:")
            print(f"   📚 School days: {school_days}")
            print(f"   🏠 Non-school days: {non_school_days}")
            print(f"   📅 Total days: {len(calendar_data)}")

            # Show first few entries
            print(f"\n📋 First 5 entries:")
            for i, entry in enumerate(calendar_data[:5]):
                status = "📚" if entry['is_school_day'] else "🏠"
                print(
                    f"   {status} {entry['date']}: {entry['day_name']} (Day {entry['day_number']})")
        else:
            # Log failure case
            log_generation_run(response_code, start_date,
                               end_date, "FAILED - Could not save file")
            print("❌ Failed to save calendar.json")
            sys.exit(1)
    else:
        # Log no data case
        log_generation_run(response_code, 'N/A', 'N/A', validation_result)
        print("❌ No calendar data generated")
        sys.exit(1)


if __name__ == "__main__":
    main()
