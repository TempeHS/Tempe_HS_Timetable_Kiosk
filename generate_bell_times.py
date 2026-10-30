#!/usr/bin/env python3
"""
Generate bell_times.json from Sentral API data
This recreates the bell_times.xml structure as JSON using API endpoints
"""

import sys
import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from sentral_rest_client import SentralAPIClient
from data_freshness import write_json_atomic


def log_generation_run(response_code: int, start_date: str, end_date: str, validation_result: str, log_file: str = '.logs/bell_times_generation.log'):
    """
    Log generation run details to a log file.

    Args:
        response_code (int): HTTP response code from API
        start_date (str): Start date of data range (or description)
        end_date (str): End date of data range (or description)
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


def validate_bell_times_data(bell_times_data: List[Dict[str, Any]]) -> str:
    """
    Validate that bell times data matches required pattern.

    Args:
        bell_times_data (list): Bell times data to validate

    Returns:
        str: Validation result description
    """
    if not bell_times_data:
        return "FAILED - No bell times data generated"

    required_fields = ['DayNumber', 'DayName',
                       'Period', 'StartTime', 'EndTime', 'Type']
    validation_issues = []

    for i, entry in enumerate(bell_times_data[:5]):  # Check first 5 entries
        for field in required_fields:
            if field not in entry:
                validation_issues.append(
                    f"Missing field '{field}' in entry {i+1}")

    # Check time format
    time_pattern = r'^\d{2}:\d{2}$'
    for i, entry in enumerate(bell_times_data[:3]):  # Check first 3 entries
        start_time = entry.get('StartTime', '')
        end_time = entry.get('EndTime', '')
        if not re.match(time_pattern, start_time):
            validation_issues.append(
                f"Invalid start time format in entry {i+1}: {start_time}")
        if not re.match(time_pattern, end_time):
            validation_issues.append(
                f"Invalid end time format in entry {i+1}: {end_time}")

    # Check day numbers are valid (1-10)
    for i, entry in enumerate(bell_times_data[:5]):
        day_num = entry.get('DayNumber', 0)
        if not (1 <= day_num <= 10):
            validation_issues.append(
                f"Invalid day number in entry {i+1}: {day_num}")

    if validation_issues:
        return f"FAILED - {len(validation_issues)} issues: {', '.join(validation_issues[:3])}"
    else:
        return f"PASSED - {len(bell_times_data)} bell time entries validated successfully"


def generate_bell_times_json(output_file: str = 'bell_times.json') -> Tuple[bool, int, str]:
    """
    Generate bell_times.json from Sentral API data

    Args:
        output_file (str): Output JSON file path

    Returns:
        Tuple of (success, response_code, date_range_description)
    """
    print("🔄 Generating bell_times.json from Sentral API...")

    # Initialize API client
    client = SentralAPIClient.from_config('config.json')
    if not client:
        print("❌ Failed to initialize API client")
        return False, 0, "N/A"

    response_code = 200  # Default success code
    try:
        # Get all timetable days with pagination
        print("📅 Fetching timetable days...")
        days = []
        offset = 0
        limit = 100

        while True:
            days_response = client._make_request(
                'GET', 'timetables/timetable-day', {'limit': limit, 'offset': offset})
            if not days_response or 'data' not in days_response:
                break

            batch = days_response.get('data', [])
            if not batch:
                break

            days.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        print(f"✓ Found {len(days)} timetable days")

        # Get all periods with pagination
        print("⏰ Fetching timetable periods...")
        periods = []
        offset = 0
        limit = 100

        while True:
            periods_response = client._make_request(
                'GET', 'timetables/timetable-period', {'limit': limit, 'offset': offset})
            if not periods_response or 'data' not in periods_response:
                break

            batch = periods_response.get('data', [])
            if not batch:
                break

            periods.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        print(f"✓ Found {len(periods)} timetable periods")

        # Get all period-in-day records with pagination
        print("🕐 Fetching period-in-day mappings...")
        period_in_days = []
        offset = 0
        limit = 200

        while True:
            period_in_day_response = client._make_request(
                'GET', 'timetables/timetable-period-in-day', {'limit': limit, 'offset': offset})
            if not period_in_day_response or 'data' not in period_in_day_response:
                break

            batch = period_in_day_response.get('data', [])
            if not batch:
                break

            period_in_days.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        print(f"✓ Found {len(period_in_days)} period-in-day mappings")

        # Create lookup dictionaries
        day_lookup = {day['id']: day for day in days}
        period_lookup = {period['id']: period for period in periods}

        # Generate bell times data
        bell_times_data = []

        # Sort period_in_days by day name and period order for consistent output
        def sort_key(item):
            day_id = item.get('relationships', {}).get(
                'day', {}).get('data', {}).get('id', '0')
            day_name = day_lookup.get(day_id, {}).get(
                'attributes', {}).get('name', 'ZZZ')
            order = item.get('attributes', {}).get('order', 999)
            return (day_name, order)

        sorted_period_in_days = sorted(period_in_days, key=sort_key)

        # Get unique day names for range description
        day_names = list(set(day_lookup.get(item.get('relationships', {}).get('day', {}).get('data', {}).get('id'), {}).get('attributes', {}).get('name', 'Unknown')
                             for item in period_in_days))
        day_names.sort()
        date_range = f"Timetable days: {', '.join(day_names[:5])}" + (
            "..." if len(day_names) > 5 else "")

        # Process each period-in-day mapping
        for item in sorted_period_in_days:
            attrs = item.get('attributes', {})
            rels = item.get('relationships', {})

            # Get day and period info
            day_id = rels.get('day', {}).get('data', {}).get('id')
            period_id = rels.get('period', {}).get('data', {}).get('id')

            day_info = day_lookup.get(day_id, {})
            period_info = period_lookup.get(period_id, {})

            day_name = day_info.get('attributes', {}).get('name', 'Unknown')
            period_name = period_info.get(
                'attributes', {}).get('name', 'Unknown')

            # Extract times (convert from HH:MM:SS to HH:MM format to match XML)
            start_time = attrs.get('startTime', '00:00:00')
            end_time = attrs.get('endTime', '00:00:00')

            # Convert from HH:MM:SS to HH:MM format
            if len(start_time) == 8:  # HH:MM:SS format
                start_time = start_time[:5]  # Take just HH:MM
            if len(end_time) == 8:  # HH:MM:SS format
                end_time = end_time[:5]  # Take just HH:MM

            # Determine day number based on day name (from XML analysis)
            day_number_map = {
                'MonA': 1, 'MonB': 6,
                'TueA': 2, 'TueB': 7,
                'WedA': 3, 'WedB': 8,
                'ThuA': 4, 'ThuB': 9,
                'FriA': 5, 'FriB': 10
            }

            day_number = day_number_map.get(day_name)
            if day_number is None:
                print(
                    f"⚠️  Skipping {period_name} on unknown timetable day '{day_name}'")
                continue

            # Determine period type based on period name and context
            period_type = 'T'  # Default to Teaching

            period_name_lower = period_name.lower()
            if period_name == 'P0':
                period_type = 'O'  # Orientation/Assembly
            elif 'recess' in period_name_lower or 'lunch' in period_name_lower:
                period_type = 'R'  # Recess/Break
            elif (period_name == 'P6' and day_name in ['TueA', 'TueB']) or \
                 (period_name == 'P7'):
                # P6 on Tuesday and P7 on all days are orientation periods
                period_type = 'O'
            # Otherwise keep 'T' for regular teaching periods

            # Create bell times entry
            bell_time_entry = {
                "DayNumber": day_number,
                "DayName": day_name,
                "Period": period_name,
                "StartTime": start_time,
                "EndTime": end_time,
                "Type": period_type
            }

            bell_times_data.append(bell_time_entry)

        validation_result = validate_bell_times_data(bell_times_data)
        if validation_result.startswith('FAILED'):
            print(f"❌ Not writing {output_file}: {validation_result}")
            return False, 204 if not bell_times_data else 422, date_range

        # Create the complete JSON structure
        bell_times_json = {
            "metadata": {
                "source": "Sentral API",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_periods": len(bell_times_data),
                "note": "Generated from Sentral API timetable endpoints"
            },
            "bell_times": bell_times_data
        }

        # Write to JSON file
        print(
            f"💾 Writing {len(bell_times_data)} bell time entries to {output_file}...")
        write_json_atomic(output_file, bell_times_json)

        print(f"✅ Successfully generated {output_file}")
        print(f"📊 Summary:")
        print(f"   - Total periods: {len(bell_times_data)}")
        print(
            f"   - Unique days: {len(set(item['DayName'] for item in bell_times_data))}")
        print(
            f"   - Unique periods: {len(set(item['Period'] for item in bell_times_data))}")

        # Show sample data
        print(f"\n📝 Sample entries:")
        for i, entry in enumerate(bell_times_data[:5]):
            print(
                f"   {i+1}. {entry['DayName']} {entry['Period']}: {entry['StartTime']}-{entry['EndTime']} ({entry['Type']})")

        return True, response_code, date_range

    except Exception as e:
        print(f"❌ Error generating bell times JSON: {e}")
        return False, 500, "N/A"


def main():
    """Main function"""
    print("SENTRAL API BELL TIMES JSON GENERATOR")
    print("="*50)

    success, response_code, date_range = generate_bell_times_json()

    # Validate generated data if successful
    validation_result = "FAILED - Generation failed"
    if success:
        try:
            with open('bell_times.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                bell_times_data = data.get('bell_times', [])
                validation_result = validate_bell_times_data(bell_times_data)
        except Exception as e:
            validation_result = f"FAILED - Could not validate: {e}"

    # Log the generation run
    log_generation_run(response_code, "Timetable structure",
                       date_range, validation_result)

    if success:
        print("\n🎉 Bell times JSON generation completed successfully!")
        print(
            "The bell_times.json file can now be used as an alternative to bell_times.xml")
    else:
        print("\n💥 Bell times JSON generation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
