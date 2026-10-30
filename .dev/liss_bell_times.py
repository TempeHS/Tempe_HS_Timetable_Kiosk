#!/usr/bin/env python3
"""
LISS Bell Times Fetcher - Simplified
A script to fetch bell times from LISS API using only the getBellTimes method

Usage:
    python3 liss_bell_times.py [--config config_file.json]

Author: Tempe High School IT
Date: August 2025
"""

import json
import sys
import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests module is required. Install with: sudo apt install python3-requests")
    sys.exit(1)


class LissBellTimesFetcher:
    """Fetches bell times from LISS API using configuration file"""

    def __init__(self, config_file="liss_config.json"):
        """Initialize with configuration file"""
        self.config = self.load_config(config_file)
        self.setup_logging()

    def load_config(self, config_file):
        """Load configuration from JSON file"""
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                raise FileNotFoundError(
                    f"Configuration file not found: {config_file}")

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Validate required configuration
            required_fields = ['liss.endpoint', 'liss.school']
            for field in required_fields:
                keys = field.split('.')
                value = config
                for key in keys:
                    if key not in value:
                        raise KeyError(
                            f"Missing required configuration: {field}")
                    value = value[key]

            # Validate environment variable configurations
            liss_config = config['liss']
            if 'username_env' in liss_config:
                username_env = liss_config['username_env']
                if not os.getenv(username_env):
                    raise KeyError(
                        f"Environment variable {username_env} is not set")
            elif 'username' not in liss_config:
                raise KeyError(
                    "Either 'username' or 'username_env' must be specified in config")

            if 'password_env' in liss_config:
                password_env = liss_config['password_env']
                if not os.getenv(password_env):
                    raise KeyError(
                        f"Environment variable {password_env} is not set")
            elif 'password' not in liss_config:
                raise KeyError(
                    "Either 'password' or 'password_env' must be specified in config")

            return config

        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            print(f"Error loading configuration: {e}")
            sys.exit(1)

    def setup_logging(self):
        """Setup logging based on configuration"""
        if self.config.get('logging', {}).get('enabled', True):
            level = getattr(logging, self.config.get(
                'logging', {}).get('level', 'INFO'))
            logging.basicConfig(
                level=level,
                format='%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self.logger = logging.getLogger(__name__)
        else:
            # Create a null logger
            self.logger = logging.getLogger(__name__)
            self.logger.addHandler(logging.NullHandler())

    def create_auth_object(self):
        """Create authentication object for LISS API"""
        liss_config = self.config['liss']

        # Get username from environment or config
        if 'username_env' in liss_config:
            username = os.getenv(liss_config['username_env'])
            if not username:
                raise ValueError(
                    f"Environment variable {liss_config['username_env']} is not set")
        else:
            username = liss_config['username']

        # Get password from environment or config
        if 'password_env' in liss_config:
            password = os.getenv(liss_config['password_env'])
            if not password:
                raise ValueError(
                    f"Environment variable {liss_config['password_env']} is not set")
        else:
            password = liss_config['password']

        auth_object = {
            "School": liss_config['school'],
            "UserName": username,
            "Password": password,
            "LissVersion": liss_config.get('liss_version', 10002),
            "UserAgent": liss_config.get('user_agent', 'TimetableKiosk')
        }

        return auth_object

    def get_bell_times(self):
        """Fetch bell times from LISS API using getBellTimes method"""
        self.logger.info("Fetching bell times from LISS API...")

        url = self.config['liss']['endpoint']
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        auth_object = self.create_auth_object()

        # According to LISS documentation, getBellTimes can accept:
        # - Just the auth object (returns all bell times)
        # - Auth object + timetable structure name
        tt_structure = self.config['liss'].get('tt_structure', '')

        # Create the LISS request according to documentation
        if tt_structure:
            params = [auth_object, tt_structure]
        else:
            params = [auth_object]

        request = {
            "jsonrpc": "2.0",
            "method": "liss.getBellTimes",
            "params": params,
            "id": 1
        }

        self.logger.debug("LISS request: liss.getBellTimes")

        try:
            response = requests.post(
                url, headers=headers, json=request, timeout=30)

            if response.status_code == 200:
                data = response.json()

                if "result" in data:
                    bell_times = data["result"]
                    self.logger.info(
                        "Successfully fetched %d bell time entries", len(bell_times))
                    return bell_times

                elif "error" in data:
                    error = data["error"]
                    fault_string = error.get("faultString", "Unknown error")
                    self.logger.error("LISS API error: %s", fault_string)

                    # Provide helpful error analysis
                    if "does not exist" in fault_string and "academic year" in fault_string:
                        self.logger.info(
                            "💡 This suggests the school/year combination is not available")
                        self.logger.info(
                            "💡 Check if 2025 academic year data has been loaded")
                    elif "Username or password" in fault_string and "academic year" in fault_string:
                        self.logger.info(
                            "💡 Credentials may be valid for a different academic year")
                        self.logger.info(
                            "💡 Contact IT for current year credentials")
                    elif "TtStructure" in fault_string:
                        self.logger.info(
                            "💡 TimetableStructure '%s' may not be valid", tt_structure)
                        self.logger.info(
                            "💡 Try removing tt_structure from config or use an empty string")

                    return None
                else:
                    self.logger.error(
                        "Unexpected response format from LISS API")
                    return None

            else:
                self.logger.error("HTTP error %d: %s",
                                  response.status_code, response.text)
                return None

        except requests.RequestException as e:
            self.logger.error("Network error fetching bell times: %s", e)
            return None
        except json.JSONDecodeError as e:
            self.logger.error("JSON decode error: %s", e)
            return None

    def save_bell_times(self, bell_times):
        """Save bell times to file"""
        if not bell_times:
            self.logger.warning("No bell times to save")
            return False

        output_config = self.config.get('output', {})
        output_file = output_config.get('file', 'current_bell_times.json')
        pretty_print = output_config.get('pretty_print', True)

        try:
            # Add metadata
            output_data = {
                "metadata": {
                    "fetched_at": datetime.now().isoformat(),
                    "source": "LISS API",
                    "school": self.config['liss']['school'],
                    "tt_structure": self.config['liss'].get('tt_structure', ''),
                    "total_entries": len(bell_times)
                },
                "bell_times": bell_times
            }

            with open(output_file, 'w', encoding='utf-8') as f:
                if pretty_print:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(output_data, f, ensure_ascii=False)

            self.logger.info("Bell times saved to: %s", output_file)

            # Print summary
            self.print_summary(bell_times)

            return True

        except (IOError, json.JSONEncodeError) as e:
            self.logger.error("Error saving bell times: %s", e)
            return False

    def print_summary(self, bell_times):
        """Print a summary of the bell times"""
        print("\n📊 Bell Times Summary")
        print("=" * 40)
        print(f"Total entries: {len(bell_times)}")

        # Group by day
        days = {}
        for entry in bell_times:
            day_name = entry.get('DayName', 'Unknown')
            if day_name not in days:
                days[day_name] = []
            days[day_name].append(entry.get('Period', 'Unknown'))

        print("\nPeriods by day:")
        for day, periods in days.items():
            print(f"  {day}: {', '.join(periods)}")

        # Show sample entry
        if bell_times:
            print("\nSample entry:")
            sample = bell_times[0]
            for key, value in sample.items():
                print(f"  {key}: {value}")

    def run(self):
        """Main execution method"""
        print("🔔 LISS Bell Times Fetcher")
        print(f"School: {self.config['liss']['school']}")
        print(f"Endpoint: {self.config['liss']['endpoint']}")
        print("=" * 50)

        # Fetch bell times directly
        bell_times = self.get_bell_times()

        if bell_times:
            print("✅ Successfully fetched bell times!")
            self.save_bell_times(bell_times)
            return True
        else:
            print("❌ Failed to fetch bell times. Check logs for details.")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Fetch bell times from LISS API')
    parser.add_argument('--config', '-c', default='liss_config.json',
                        help='Configuration file path (default: liss_config.json)')

    args = parser.parse_args()

    try:
        fetcher = LissBellTimesFetcher(args.config)
        success = fetcher.run()
        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        return 1
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
