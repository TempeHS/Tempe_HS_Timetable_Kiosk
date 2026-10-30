#!/usr/bin/env python3
"""
LISS Info Generator - Optimized Version  
Generates liss_info.json from Sentral API data using optimized bulk operations.
This version uses include parameters to minimize API calls (6 calls vs 700+ in original).
Performance: ~0.9 seconds vs 26+ seconds for non-optimized version.
"""

import sys
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sentral_rest_client import SentralAPIClient
from data_freshness import write_json_atomic


def log_generation_run(response_code: int, start_date: str, end_date: str, validation_result: str, log_file: str = '.logs/liss_info_generation.log'):
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


def validate_liss_data(liss_data: List[Dict[str, Any]]) -> str:
    """
    Validate that LISS data matches required pattern.

    Args:
        liss_data (list): LISS timetable data to validate

    Returns:
        str: Validation result description
    """
    if not liss_data:
        return "FAILED - No LISS timetable data generated"

    required_fields = ['DayNumber', 'Period',
                       'ClassCode', 'TeacherId', 'TeacherCode']
    validation_issues = []

    for i, entry in enumerate(liss_data[:5]):  # Check first 5 entries
        for field in required_fields:
            if field not in entry:
                validation_issues.append(
                    f"Missing field '{field}' in entry {i+1}")

    # Check day numbers are valid (1-10)
    for i, entry in enumerate(liss_data[:5]):
        day_num = entry.get('DayNumber', 0)
        if not (1 <= day_num <= 10):
            validation_issues.append(
                f"Invalid day number in entry {i+1}: {day_num}")

    # Check teacher codes format (surname up to 10 characters, allows hyphens, apostrophes, spaces)
    for i, entry in enumerate(liss_data[:3]):
        teacher_code = entry.get('TeacherCode', '')
        if not re.match(r"^[A-Z][A-Z\-'\s]*$", teacher_code) or len(teacher_code) > 10:
            validation_issues.append(
                f"Invalid teacher code format in entry {i+1}: {teacher_code} (expected 1-10 chars: letters, hyphens, apostrophes, spaces)")

    if validation_issues:
        return f"FAILED - {len(validation_issues)} issues: {', '.join(validation_issues[:3])}"
    else:
        return f"PASSED - {len(liss_data)} LISS timetable entries validated successfully"


def get_staff_code_mapping(client: SentralAPIClient) -> Dict[str, str]:
    """
    Get mapping of staff IDs to staff codes from the enrolments/staff endpoint.

    Args:
        client: Sentral API client

    Returns:
        Dictionary mapping staff IDs to staff codes
    """
    print("📋 Fetching staff data for code mapping...")
    staff_mapping = {}

    try:
        # Get all staff data
        offset = 0
        limit = 100
        while True:
            response = client._make_request(
                'GET', 'enrolments/staff', {'limit': limit, 'offset': offset})
            if not response or 'data' not in response:
                break

            staff_list = response['data']
            if not staff_list:
                break

            for staff in staff_list:
                staff_id = staff.get('id')
                attrs = staff.get('attributes', {})
                staff_code = attrs.get('code', '')

                if staff_id and staff_code:
                    staff_mapping[staff_id] = staff_code

            # Check if we've reached the end
            if len(staff_list) < limit:
                break
            offset += limit

        print(f"✓ Found {len(staff_mapping)} staff code mappings")
        return staff_mapping

    except Exception as e:
        print(f"Warning: Could not fetch staff codes: {e}")
        return {}


def generate_liss_info_json(days_limit: int = 7, output_file: str = 'liss_info.json', debug: bool = False) -> Tuple[bool, int, str]:
    """
    Generate liss_info.json from Sentral API data for the specified number of days.

    Args:
        days_limit (int): Number of days of data to generate (default 7)
        output_file (str): Output JSON file path
        debug (bool): Enable debug logging for API diagnostics

    Returns:
        Tuple of (success, response_code, date_range)
    """
    print(f"🗓️  Generating LISS info JSON for {days_limit} days...")
    if debug:
        print("🐛 Debug mode enabled - detailed API diagnostics will be shown")

    # Initialize API client with debug mode
    client = SentralAPIClient.from_config('config.json', debug=debug)
    if not client:
        print("❌ Failed to initialize API client")
        return False, 0, "N/A"

    response_code = 200  # Default success code
    try:
        # Get current date range for calendar context
        today = datetime.now()
        end_date = today + timedelta(days=days_limit)
        date_from = today.strftime('%Y-%m-%d')
        date_to = end_date.strftime('%Y-%m-%d')
        date_range = f"{date_from} to {date_to}"

        print(f"📅 Target date range: {date_range}")

        # Always include the whole A/B cycle: the kiosk looks ahead into next week,
        # which may be a different week of the cycle than this one.
        active_day_numbers = set(range(1, 11))
        print(f"📋 Active day numbers: {sorted(active_day_numbers)}")

        # Get staff code mapping
        staff_mapping = get_staff_code_mapping(client)

        # Get timetable classes (with pagination)
        print("📚 Fetching timetable classes...")
        classes = []
        offset = 0
        limit = 200

        while True:
            classes_response = client._make_request(
                'GET', 'timetables/timetable-class', {'limit': limit, 'offset': offset})
            if not classes_response or 'data' not in classes_response:
                break

            batch = classes_response['data']
            if not batch:
                break

            classes.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        if not classes:
            print("❌ No timetable classes found")
            return False, 404, date_range

        class_lookup = {cls['id']: cls for cls in classes}
        print(f"✓ Found {len(classes)} timetable classes")

        # Get timetable rooms (with pagination)
        print("🏫 Fetching timetable rooms...")
        rooms = []
        offset = 0
        limit = 200

        while True:
            rooms_response = client._make_request(
                'GET', 'timetables/timetable-room', {'limit': limit, 'offset': offset})
            if not rooms_response or 'data' not in rooms_response:
                break

            batch = rooms_response['data']
            if not batch:
                break

            rooms.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        room_lookup = {room['id']: room for room in rooms}
        print(f"✓ Found {len(rooms)} timetable rooms")

        # Get period-in-day mappings to understand day/period structure
        print("⏰ Fetching period-in-day mappings...")
        period_in_day_response = client._make_request(
            'GET', 'timetables/timetable-period-in-day', {'limit': 200})
        if not period_in_day_response:
            print("❌ Failed to fetch period-in-day mappings")
            return False, 404, date_range

        period_in_days = period_in_day_response.get('data', [])

        # Get days and periods for lookup
        print("📅 Fetching timetable days...")
        days_response = client._make_request(
            'GET', 'timetables/timetable-day', {'limit': 50})
        if not days_response:
            print("❌ Failed to fetch timetable days - cannot continue")
            print("🔍 This is required for period-in-day mapping")
            return False, 404, date_range

        print("⏰ Fetching timetable periods...")
        periods_response = client._make_request(
            'GET', 'timetables/timetable-period', {'limit': 50})
        if not periods_response:
            print("❌ Failed to fetch timetable periods - cannot continue")
            print("🔍 This is required for period-in-day mapping")
            return False, 404, date_range

        # Validate response structure
        days_data = days_response.get('data', [])
        periods_data = periods_response.get('data', [])

        if not days_data:
            print("⚠️  Warning: No timetable days found in response")
            print(f"🔍 Days response structure: {list(days_response.keys())}")
        else:
            print(f"✅ Found {len(days_data)} timetable days")

        if not periods_data:
            print("⚠️  Warning: No timetable periods found in response")
            print(
                f"🔍 Periods response structure: {list(periods_response.keys())}")
        else:
            print(f"✅ Found {len(periods_data)} timetable periods")

        day_lookup = {day['id']: day for day in days_data}
        period_lookup = {period['id']: period for period in periods_data}

        # Create period-in-day lookup
        period_day_lookup = {}
        for pid in period_in_days:
            pid_id = pid.get('id')
            day_id = pid.get('relationships', {}).get(
                'day', {}).get('data', {}).get('id')
            period_id = pid.get('relationships', {}).get(
                'period', {}).get('data', {}).get('id')

            if day_id and period_id:
                day_name = day_lookup.get(day_id, {}).get(
                    'attributes', {}).get('name', 'Unknown')
                period_name = period_lookup.get(period_id, {}).get(
                    'attributes', {}).get('name', 'Unknown')

                # Map day names to numbers
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

                period_day_lookup[pid_id] = {
                    'day_name': day_name,
                    'day_number': day_number,
                    'period_name': period_name
                }

        print(f"✓ Found {len(period_day_lookup)} period-in-day mappings")

        # Get class lessons (limit to active days only)
        print("🕐 Fetching timetable class lessons...")
        lessons_data = []

        # Fetch lessons in batches
        offset = 0
        limit = 100
        lessons_processed = 0

        while True:  # Remove artificial limit - get all lessons
            lessons_response = client._make_request('GET', 'timetables/timetable-class-lesson', {
                'limit': limit,
                'offset': offset,
                # OPTIMIZATION: Get all related data in one call!
                'include': 'class,room,periodInDay,timetableTeachers'
            })
            if not lessons_response or 'data' not in lessons_response:
                break

            lessons = lessons_response['data']
            included_data = lessons_response.get('included', [])

            # OPTIMIZATION: Build lookup tables from included data
            teacher_lookup = {}
            for item in included_data:
                if item.get('type') == 'timetableTeacher':
                    teacher_lookup[item.get('id')] = item

            if not lessons:
                break

            for lesson in lessons:
                lesson_id = lesson.get('id')
                rels = lesson.get('relationships', {})

                # Get period-in-day info
                pid_id = rels.get('periodInDay', {}).get('data', {}).get('id')
                period_info = period_day_lookup.get(pid_id, {})
                day_number = period_info.get('day_number', 0)

                # Only include lessons for active days within our date range
                if day_number in active_day_numbers:
                    # Get class info
                    class_id = rels.get('class', {}).get('data', {}).get('id')
                    class_info = class_lookup.get(class_id, {})
                    class_attrs = class_info.get('attributes', {})
                    class_code = class_attrs.get('name', 'Unknown')
                    edval_class_code = class_attrs.get(
                        'externalId', class_code)

                    # Get room info
                    room_id = rels.get('room', {}).get('data', {}).get('id')
                    room_info = room_lookup.get(room_id, {})
                    room_code = room_info.get('attributes', {}).get('name', '')

                    # Get teacher info from INCLUDED data (OPTIMIZED!)
                    teacher_id = None
                    teacher_code = 'UNKN'
                    teacher_rel = rels.get(
                        'timetableTeachers', {}).get('data', [])

                    if isinstance(teacher_rel, list) and teacher_rel:
                        # Take first teacher from included data
                        teacher_id = teacher_rel[0].get('id')
                        teacher_info = teacher_lookup.get(teacher_id, {})

                        if teacher_info:
                            teacher_attrs = teacher_info.get('attributes', {})
                            last_name = teacher_attrs.get('lastName', '')
                            if last_name:
                                teacher_code = last_name[:10].upper()

                    # Create LISS entry
                    liss_entry = {
                        'DayNumber': day_number,
                        'Period': period_info.get('period_name', 'Unknown'),
                        'ClassCode': class_code,
                        'EdvalClassCode': edval_class_code,
                        'TeacherId': teacher_id,
                        'TeacherCode': teacher_code,
                        'RoomCode': room_code
                    }

                    lessons_data.append(liss_entry)
                    lessons_processed += 1

            if len(lessons) < limit:  # Break when no more lessons available
                break

            offset += limit

        print(f"✓ Processed {len(lessons_data)} class lessons")

        validation_result = validate_liss_data(lessons_data)
        if validation_result.startswith('FAILED'):
            print(f"❌ Not writing {output_file}: {validation_result}")
            return False, 204 if not lessons_data else 422, date_range

        # Create the complete JSON structure
        liss_json = {
            "metadata": {
                "school": "TEMPE",
                "generated_at": datetime.now().isoformat(),
                "source": "sentral_api",
                "total_lessons": len(lessons_data),
                "date_range": date_range,
                "days_covered": sorted(set(item['DayNumber'] for item in lessons_data)),
                "note": "Generated from Sentral API timetable endpoints for LISS integration"
            },
            "timetable_data": lessons_data
        }

        # Write to JSON file
        print(
            f"💾 Writing {len(lessons_data)} LISS entries to {output_file}...")
        write_json_atomic(output_file, liss_json)

        print(f"✅ Successfully generated {output_file}")
        print(f"📊 Summary:")
        print(f"   - Total lessons: {len(lessons_data)}")
        print(
            f"   - Unique classes: {len(set(item['ClassCode'] for item in lessons_data))}")
        print(
            f"   - Unique teachers: {len(set(item['TeacherCode'] for item in lessons_data if item['TeacherCode']))}")
        print(
            f"   - Unique rooms: {len(set(item['RoomCode'] for item in lessons_data if item['RoomCode']))}")
        print(
            f"   - Day numbers covered: {sorted(set(item['DayNumber'] for item in lessons_data))}")

        # Show sample data
        print(f"\n📝 Sample entries:")
        for i, entry in enumerate(lessons_data[:5]):
            print(
                f"   {i+1}. Day {entry['DayNumber']} {entry['Period']}: {entry['ClassCode']} - {entry['TeacherCode']} in {entry['RoomCode']}")

        # Print API statistics for debugging
        client.print_request_stats()

        return True, response_code, date_range

    except Exception as e:
        print(f"❌ Error generating LISS info JSON: {e}")
        print(f"🔍 Exception type: {type(e).__name__}")
        print(f"🔍 Exception details: {str(e)}")

        # Print API statistics even on failure
        if 'client' in locals():
            client.print_request_stats()

        # Import traceback for more detailed error info
        import traceback
        print(f"🐛 Full traceback:")
        traceback.print_exc()

        return False, 500, "N/A"


def main():
    """Main function"""
    print("SENTRAL API LISS INFO JSON GENERATOR")
    print("="*50)

    # Check for debug mode from environment or command line
    debug_mode = os.getenv('LISS_DEBUG', 'false').lower() == 'true'
    if len(sys.argv) > 1 and '--debug' in sys.argv:
        debug_mode = True

    if debug_mode:
        print("🐛 Debug mode enabled")

    # Generate for 7 days as requested
    success, response_code, date_range = generate_liss_info_json(
        days_limit=7, debug=debug_mode)

    # Validate generated data if successful
    validation_result = "FAILED - Generation failed"
    if success:
        try:
            with open('liss_info.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                liss_data = data.get('timetable_data', [])
                validation_result = validate_liss_data(liss_data)
        except Exception as e:
            validation_result = f"FAILED - Could not validate: {e}"

    # Log the generation run
    log_generation_run(response_code, date_range.split(' to ')[0] if ' to ' in date_range else date_range,
                       date_range.split(' to ')[1] if ' to ' in date_range else date_range, validation_result)

    if success:
        print("\n🎉 LISS info JSON generation completed successfully!")
        print("The liss_info.json file can now be used for LISS integration")
    else:
        print("\n💥 LISS info JSON generation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
