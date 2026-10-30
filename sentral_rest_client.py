#!/usr/bin/env python3
"""
Tempe High School Timetable Kiosk
Copyright (C) 2025 TempeHS

Licensed under the MIT License. See the LICENSE file for details.

Sentral REST API Client
=======================

This script provides access to Sentral's REST API endpoints including:
- Activity Vehicle endpoints
- Timetable data
- Student information
- And other school management data

Based on Sentral API documentation: https://development.sentral.com.au/

Usage:
    python sentral_rest_client.py
"""

import requests
import json
import sys
import os
import re
import time
import logging
from typing import Optional, Dict, Any, List


def load_env_file(env_file_path: str = ".env") -> None:
    """
    Load environment variables from a .env file.

    Args:
        env_file_path (str): Path to the .env file
    """
    try:
        if os.path.exists(env_file_path):
            with open(env_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        # Only set if not already in environment
                        if key not in os.environ:
                            os.environ[key] = value
    except Exception as e:
        print(f"Warning: Could not load .env file: {e}")


def load_config(config_file: str = "config.json") -> Dict[str, Any]:
    """
    Load configuration from JSON file and resolve environment variables.
    Automatically loads .env file if it exists.

    Args:
        config_file (str): Path to configuration file

    Returns:
        dict: Configuration data with environment variables resolved
    """
    # Load .env file if it exists
    load_env_file()

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config_content = f.read()

        # Resolve environment variables in the format ${VAR_NAME}
        def replace_env_var(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            if env_value is None:
                print(f"❌ Environment variable '{var_name}' not found")
                return match.group(0)  # Return original if not found
            return env_value

        # Replace ${VAR_NAME} patterns with environment variable values
        resolved_content = re.sub(
            r'\$\{([^}]+)\}', replace_env_var, config_content)

        return json.loads(resolved_content)
    except FileNotFoundError:
        print(f"Configuration file '{config_file}' not found.")
        print("Please create the configuration file with your API credentials.")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing configuration file: {e}")
        return None
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return None


class SentralAPIClient:
    """Client for interacting with Sentral REST API"""

    def __init__(self, base_url: str, api_key: str, tenant: str, debug: bool = False):
        """
        Initialize the Sentral API client.

        Args:
            base_url (str): Base URL for the Sentral instance (e.g., "https://tempe-h.sentral.com.au")
            api_key (str): API key for authentication
            tenant (str): Tenant identifier
            debug (bool): Enable debug logging for detailed API diagnostics
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.tenant = tenant
        self.debug = debug
        self.session = requests.Session()
        self.request_count = 0
        self.total_request_time = 0

        # Set up logging for debug mode
        if self.debug:
            logging.basicConfig(
                level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.INFO)

        # Set default headers
        self.session.headers.update({
            'X-API-KEY': api_key,
            'X-API-TENANT': tenant,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Sentral-Python-Client/1.0'
        })

        if self.debug:
            self.logger.debug(
                f"Initialized SentralAPIClient with base_url: {base_url}, tenant: {tenant}")
            self.logger.debug(f"API Key length: {len(api_key)} characters")
            self.logger.debug(f"Session headers: {dict(self.session.headers)}")

    @classmethod
    def from_config(cls, config_file: str = "config.json", debug: bool = False):
        """
        Create SentralAPIClient from configuration file.

        Args:
            config_file (str): Path to configuration file
            debug (bool): Enable debug logging for detailed API diagnostics

        Returns:
            SentralAPIClient: Configured client instance
        """
        config = load_config(config_file)
        if not config:
            return None

        # Get sentral config from the merged config structure
        api_config = config.get('api', {}).get('sentral', {})
        base_url = api_config.get('base_url')
        api_key = api_config.get('api_key')
        tenant = api_config.get('tenant')

        if not all([base_url, api_key, tenant]):
            print("❌ Invalid configuration. Required: api.sentral.base_url, api.sentral.api_key, api.sentral.tenant")
            missing = []
            if not base_url:
                missing.append("api.sentral.base_url")
            if not api_key:
                missing.append(
                    "api.sentral.api_key (REST_API_KEY environment variable)")
            if not tenant:
                missing.append("api.sentral.tenant")
            print(f"❌ Missing configuration: {', '.join(missing)}")
            return None

        # Check if the API key still contains unresolved environment variable pattern
        if '${' in str(api_key):
            print("❌ API key environment variable was not resolved properly")
            print("❌ Please ensure 'REST_API_KEY' environment variable is set")
            return None

        if api_key == "your-sentral-rest-api-key-here":
            print("❌ Please update the API key in configuration file")
            return None

        return cls(base_url, api_key, tenant, debug=debug)

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                      data: Optional[Dict] = None, retries: int = 3, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """
        Make a request to the Sentral API with enhanced debugging and retry logic.

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE)
            endpoint (str): API endpoint (without base URL)
            params (dict): Query parameters
            data (dict): Request body data
            retries (int): Number of retry attempts for failed requests
            timeout (int): Request timeout in seconds

        Returns:
            dict or None: Response data if successful, None if failed
        """
        url = f"{self.base_url}/restapi/v1/{endpoint.lstrip('/')}"
        self.request_count += 1

        attempt = 0
        last_exception = None

        while attempt <= retries:
            request_start_time = time.time()

            try:
                if attempt > 0:
                    wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                    print(
                        f"🔄 Retry attempt {attempt}/{retries} after {wait_time}s wait...")
                    if self.debug:
                        self.logger.debug(
                            f"Waiting {wait_time} seconds before retry attempt {attempt}")
                    time.sleep(wait_time)

                print(
                    f"📡 [{self.request_count}] Making {method} request to: {url}")
                if self.debug:
                    self.logger.debug(
                        f"Request #{self.request_count} - {method} {url}")
                    self.logger.debug(
                        f"Timeout: {timeout}s, Attempt: {attempt + 1}/{retries + 1}")

                if params:
                    print(f"📋 Parameters: {params}")
                    if self.debug:
                        self.logger.debug(f"Query parameters: {params}")

                if data:
                    print(f"📄 Data: {json.dumps(data, indent=2)}")
                    if self.debug:
                        self.logger.debug(
                            f"Request body: {json.dumps(data, indent=2)}")

                # Make the actual request
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data,
                    timeout=timeout
                )

                request_end_time = time.time()
                request_duration = round(
                    request_end_time - request_start_time, 2)
                self.total_request_time += request_duration

                print(
                    f"📊 Response Status: {response.status_code} (took {request_duration}s)")

                if self.debug:
                    self.logger.debug(
                        f"Response headers: {dict(response.headers)}")
                    self.logger.debug(
                        f"Request completed in {request_duration}s")
                    self.logger.debug(
                        f"Total API time so far: {round(self.total_request_time, 2)}s across {self.request_count} requests")

                # Log response size for debugging
                content_length = response.headers.get(
                    'content-length', 'unknown')
                print(f"📦 Response size: {content_length} bytes")

                if response.status_code in [200, 201]:
                    try:
                        response_data = response.json()

                        # Log useful response metadata
                        if isinstance(response_data, dict):
                            if 'data' in response_data:
                                data_count = len(response_data['data']) if isinstance(
                                    response_data['data'], list) else 1
                                print(
                                    f"✅ Success: Retrieved {data_count} records")
                                if self.debug:
                                    self.logger.debug(
                                        f"Response contains {data_count} data records")

                            if 'meta' in response_data:
                                meta = response_data['meta']
                                if 'total' in meta:
                                    print(
                                        f"📈 Total available: {meta['total']} records")
                                if 'page' in meta:
                                    print(f"📄 Page info: {meta['page']}")

                        return response_data

                    except json.JSONDecodeError as e:
                        print(f"❌ Response is not valid JSON: {e}")
                        print(
                            f"🔍 Response content preview: {response.text[:500]}...")
                        if self.debug:
                            self.logger.error(f"JSON decode error: {e}")
                            self.logger.debug(f"Raw response: {response.text}")
                        return None

                elif response.status_code == 429:  # Rate limiting
                    retry_after = response.headers.get('Retry-After', '60')
                    print(f"⏰ Rate limited! Retry after {retry_after} seconds")
                    if self.debug:
                        self.logger.warning(
                            f"Rate limited - Retry-After: {retry_after}")

                    if attempt < retries:
                        time.sleep(int(retry_after))
                        attempt += 1
                        continue
                    else:
                        print(f"❌ Rate limit exceeded after {retries} retries")
                        return None

                # Server errors - retry
                elif response.status_code in [500, 502, 503, 504]:
                    print(
                        f"🔧 Server error {response.status_code} - will retry if attempts remaining")
                    if self.debug:
                        self.logger.warning(
                            f"Server error {response.status_code}: {response.text[:200]}")
                    last_exception = f"Server error: {response.status_code}"

                else:  # Client errors - don't retry
                    print(
                        f"❌ Client error {response.status_code} - not retrying")
                    print(f"🔍 Response: {response.text[:500]}...")
                    if self.debug:
                        self.logger.error(
                            f"Client error {response.status_code}: {response.text}")
                    return None

            except requests.exceptions.Timeout as e:
                request_end_time = time.time()
                request_duration = round(
                    request_end_time - request_start_time, 2)
                print(
                    f"⏰ Request timeout after {request_duration}s (limit: {timeout}s)")
                if self.debug:
                    self.logger.error(
                        f"Timeout error after {request_duration}s: {e}")
                last_exception = f"Timeout after {request_duration}s"

            except requests.exceptions.ConnectionError as e:
                request_end_time = time.time()
                request_duration = round(
                    request_end_time - request_start_time, 2)
                print(f"🔌 Connection error after {request_duration}s: {e}")
                if self.debug:
                    self.logger.error(f"Connection error: {e}")
                last_exception = f"Connection error: {e}"

            except requests.exceptions.RequestException as e:
                request_end_time = time.time()
                request_duration = round(
                    request_end_time - request_start_time, 2)
                print(f"🚨 Request exception after {request_duration}s: {e}")
                if self.debug:
                    self.logger.error(f"Request exception: {e}")
                last_exception = f"Request exception: {e}"

            except Exception as e:
                request_end_time = time.time()
                request_duration = round(
                    request_end_time - request_start_time, 2)
                print(f"💥 Unexpected error after {request_duration}s: {e}")
                if self.debug:
                    self.logger.error(f"Unexpected error: {e}")
                last_exception = f"Unexpected error: {e}"

            attempt += 1

        # All retries exhausted
        print(
            f"❌ Request failed after {retries + 1} attempts. Last error: {last_exception}")
        if self.debug:
            self.logger.error(
                f"All {retries + 1} attempts failed. Final error: {last_exception}")

        return None

    # Activity Vehicle Endpoints
    def get_activity_vehicles(self, **filters) -> Optional[List[Dict[str, Any]]]:
        """
        Get activity vehicles.

        Args:
            **filters: Optional filters like date_from, date_to, activity_id, etc.

        Returns:
            List of activity vehicle records
        """
        params = {k: v for k, v in filters.items() if v is not None}
        response = self._make_request('GET', 'activity-vehicle', params=params)
        return response.get('data', []) if response else None

    def create_activity_vehicle(self, vehicle_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new activity vehicle record.

        Args:
            vehicle_data (dict): Vehicle data to create

        Returns:
            Created vehicle record
        """
        return self._make_request('POST', 'activity-vehicle', data=vehicle_data)

    def update_activity_vehicle(self, vehicle_id: int, vehicle_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update an activity vehicle record.

        Args:
            vehicle_id (int): ID of the vehicle to update
            vehicle_data (dict): Updated vehicle data

        Returns:
            Updated vehicle record
        """
        return self._make_request('PUT', f'activity-vehicle/{vehicle_id}', data=vehicle_data)

    def delete_activity_vehicle(self, vehicle_id: int) -> bool:
        """
        Delete an activity vehicle record.

        Args:
            vehicle_id (int): ID of the vehicle to delete

        Returns:
            True if successful, False otherwise
        """
        response = self._make_request(
            'DELETE', f'activity-vehicle/{vehicle_id}')
        return response is not None

    # Timetable Endpoints
    def get_timetable(self, **filters) -> Optional[List[Dict[str, Any]]]:
        """
        Get timetable data.

        Args:
            **filters: Filters like date_from, date_to, student_id, teacher_id, etc.

        Returns:
            List of timetable records
        """
        params = {k: v for k, v in filters.items() if v is not None}
        response = self._make_request('GET', 'timetable', params=params)
        return response.get('data', []) if response else None

    def get_timetable_periods(self, **filters) -> Optional[List[Dict[str, Any]]]:
        """
        Get timetable periods.

        Args:
            **filters: Optional filters

        Returns:
            List of period records
        """
        params = {k: v for k, v in filters.items() if v is not None}
        response = self._make_request(
            'GET', 'timetable/periods', params=params)
        return response.get('data', []) if response else None

    def get_timetable_calendar_dates(self, **filters) -> Optional[List[Dict[str, Any]]]:
        """
        Get timetable calendar dates.

        This endpoint retrieves calendar information including dates, day types,
        and associated timetable structure information.

        Args:
            **filters: Optional filters such as:
                - date_from (str): Start date (YYYY-MM-DD format)
                - date_to (str): End date (YYYY-MM-DD format)
                - calendar_id (int): Specific calendar ID
                - day_type (str): Filter by day type
                - include_holidays (bool): Include holiday dates
                - academic_year (int): Filter by academic year

        Returns:
            List of calendar date records with timetable information
        """
        params = {k: v for k, v in filters.items() if v is not None}
        response = self._make_request(
            'GET', 'timetables/timetable-calendar-date', params=params)
        return response.get('data', []) if response else None

    # Student Endpoints
    def get_students(self, **filters) -> Optional[List[Dict[str, Any]]]:
        """
        Get student data.

        Args:
            **filters: Filters like active_only, year_level, etc.

        Returns:
            List of student records
        """
        params = {k: v for k, v in filters.items() if v is not None}
        response = self._make_request(
            'GET', 'enrolments/student', params=params)
        return response.get('data', []) if response else None

    # Teacher/Staff Endpoints
    def get_staff(self, **filters) -> Optional[List[Dict[str, Any]]]:
        """
        Get staff data.

        Args:
            **filters: Optional filters

        Returns:
            List of staff records
        """
        params = {k: v for k, v in filters.items() if v is not None}
        response = self._make_request('GET', 'staff', params=params)
        return response.get('data', []) if response else None

    # Activity Endpoints
    def get_activities(self, **filters) -> Optional[List[Dict[str, Any]]]:
        """
        Get activities.

        Args:
            **filters: Filters like date_from, date_to, activity_type, etc.

        Returns:
            List of activity records
        """
        params = {k: v for k, v in filters.items() if v is not None}
        response = self._make_request('GET', 'activities', params=params)
        return response.get('data', []) if response else None

    # Utility methods
    def get_request_stats(self) -> Dict[str, Any]:
        """
        Get statistics about API requests made by this client.

        Returns:
            Dictionary with request statistics
        """
        avg_time = round(self.total_request_time /
                         max(self.request_count, 1), 2)
        return {
            'total_requests': self.request_count,
            'total_time_seconds': round(self.total_request_time, 2),
            'average_request_time': avg_time,
            'base_url': self.base_url,
            'tenant': self.tenant,
            'debug_mode': self.debug
        }

    def print_request_stats(self):
        """Print formatted request statistics."""
        stats = self.get_request_stats()
        print(f"\n📊 API Request Statistics:")
        print(f"   Total requests: {stats['total_requests']}")
        print(f"   Total time: {stats['total_time_seconds']}s")
        print(f"   Average time: {stats['average_request_time']}s per request")
        print(f"   Base URL: {stats['base_url']}")
        print(f"   Tenant: {stats['tenant']}")
        print(f"   Debug mode: {stats['debug_mode']}")

    def test_connection(self) -> bool:
        """
        Test the API connection and authentication.

        Returns:
            True if connection successful, False otherwise
        """
        print("Testing Sentral API connection...")

        # Try different endpoints to test connectivity
        endpoints_to_try = [
            ('enrolments/student', 'students endpoint'),
            ('activities/activity', 'activities endpoint'),
            ('timetables/timetable-calendar-date', 'timetable calendar endpoint'),
            ('staff/staff', 'staff endpoint')
        ]

        for endpoint, description in endpoints_to_try:
            print(f"  Trying {description}...")
            response = self._make_request('GET', endpoint, params={'limit': 1})

            if response is not None:
                print(f"✅ API connection successful via {description}!")
                return True
            else:
                print(f"❌ Failed on {description}")

        print("❌ All endpoints failed - API connection unsuccessful!")
        return False

    def get_api_info(self) -> Optional[Dict[str, Any]]:
        """
        Get API information and available endpoints.

        Returns:
            API information
        """
        return self._make_request('GET', '')


def main():
    """Main function - load config and test API connection."""
    print("Sentral REST API Client")
    print("=" * 50)

    # Initialize client from configuration file
    client = SentralAPIClient.from_config()
    if not client:
        sys.exit(1)

    print(f"Base URL: {client.base_url}")
    print(f"Tenant: {client.tenant}")

    # Test connection
    if client.test_connection():
        print("✅ API connection successful!")
        print("Client is ready to use.")

        # Example usage:
        print("\nExample usage:")
        print("vehicles = client.get_activity_vehicles()")
        print("timetable = client.get_timetable()")
        print("calendar_dates = client.get_timetable_calendar_dates()")
        print("students = client.get_students()")

    else:
        print("❌ API connection failed!")
        print("Please check your API key and credentials in config.json under api.sentral section")


if __name__ == "__main__":
    main()
