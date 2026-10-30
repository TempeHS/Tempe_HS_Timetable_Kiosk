# Changelog

All notable changes to the Timetable Kiosk project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-10-30

### 🔧 Fixed

- **Wrong Period Times**: Fixed periods showing at the wrong times because bell times from all 10 cycle days were mixed together
  - Each day now uses only its own bell times (e.g. Tuesday's early lunch no longer affects other days)
  - Recess and Lunch are skipped, so the next teaching period is shown (e.g. Monday 12:55 shows Period 5, not Period 4)
  - Week B days (6-10) now show the correct timetable
- **Stale Bell Times**: Fixed `bell_times.json` always being treated as out of date
  - `generate_bell_times.py` now writes the real generation time instead of a hard-coded 2024 date
  - Weekly workflow commits unchanged bell times when the saved timestamp is 23+ days old, so they never reach the 30-day stale limit
- **LISS Data Going Stale**: LISS workflow now refreshes the timestamp of unchanged data before it goes stale
- **Missing Next-Week Data**: Fixed blank or random timetables on Friday afternoons
  - `generate_calendar.py` now reads `days_ahead` from the correct config setting (30 days)
  - `generate_liss_info.py` now includes all 10 cycle days, not just the current week
  - Dates missing from the JSON calendar are filled from `calendar.xml`
- **Public Holidays**: Holidays in the calendar are now skipped when finding the next school day
- **Sport Period Labels**: "Year 7 & 8 Sport" and "Year 9 & 10 Sport" labels now display on Tuesday sport periods
- **Unknown Timetable Days**: Days such as "Staff Day" are skipped instead of being treated as Monday
- **LISS Generation Crash**: Lessons with no teacher no longer stop the whole generation run

### 🆕 Added

- **Data Status Notices**: Red on-screen warnings (bottom right) when data is stale, missing or could not be refreshed
  - Shows the last update date, age and which GitHub workflow to run
  - Hidden automatically when all data is fresh
- **Clear No-Data Messages**: Shows "No timetable data for <date>" instead of guessing when a date is missing from the calendar
- **Automated Tests**: Node.js tests for the front end (`npm test`) and Python tests for data generators (`python3 -m unittest discover -s tests`)
- **Per-source Stale Limits**: New `dataSources.bell_times.stale_days` setting (default 30 days)

### 🚀 Improvements

- **Robust Error Handling**: The kiosk keeps working when things go wrong
  - Missing or invalid `config.json` falls back to built-in defaults
  - Each data file loads independently: fresh JSON → XML backup → stale JSON
  - Failed refreshes keep the last good screen instead of showing an error
  - Hourly and daily page reloads only happen when the server is reachable
- **Safer Data Generation**: Generators refuse to overwrite good files with empty or invalid data, and write files atomically
- **Security**: All data values are HTML-escaped before display
- **Code Structure**: Timetable logic moved to `timetable-core.js` so it can be tested
- **Debug Logging**: `ui.debug` now defaults to `false` in `config.json`

### 📋 Licensing

- **MIT License**: `LICENSE` file and source headers updated from GNU GPL v3 to MIT, matching the README

## [2.1.0] - 2025-08-26

### 🔧 Fixed

- **GitHub Actions Git Conflicts**: Fixed critical issue where workflows failed with "Your local changes would be overwritten by merge" errors
  - Workflows now automatically stash local changes before pulling updates
  - Intelligent recovery mechanism if stash pop fails
  - Applies to both `liss-timetable-updates.yml` and `weekly-data-update.yml`
- **Workflow Error Handling**: Enhanced error recovery and logging in GitHub Actions

### 📚 Documentation

- **Updated all documentation files** with current information and recent fixes
- **Enhanced Debugging Guide**: Added GitHub Actions troubleshooting section
- **Improved GitHub Actions Setup Guide**: Documented git conflict resolution
- **Updated README**: Added recent improvements and enhanced feature list
- **Enhanced Setup Guide**: Updated automation section with v2.1 improvements

### 🚀 Improvements

- **Better Error Messages**: More descriptive error handling in workflows
- **Enhanced Logging**: Improved debug information throughout the system
- **Time Zone Handling**: Better documentation of Sydney time zone handling in workflows

## [2.0.0] - 2025-01-15

### 🆕 Added

- **LISS Timetable Integration**: Real-time timetable updates during school hours
- **Optimized Data Generation**: 20x faster API processing with 95% fewer calls
- **Intelligent Scheduling**: LISS updates every 15 minutes during school hours only
- **Enhanced API Integration**: Complete Sentral REST API implementation
- **Automated GitHub Actions**: Weekly data updates and real-time LISS updates

### 🔧 Enhanced

- **Multi-source Data Loading**: JSON primary with XML fallback
- **Performance Optimizations**: Bulk API operations and reduced network calls
- **Debug System**: Comprehensive logging for troubleshooting
- **Error Handling**: Robust fallback mechanisms

### 📱 UI/UX

- **Responsive Design**: Works on all device sizes
- **Live Period Highlighting**: Current period visual indicators
- **Auto-refresh System**: Smart refresh with memory management
- **Clean Interface**: Modern, professional appearance

## [1.0.0] - 2024-12-01

### 🎉 Initial Release

- **Basic Timetable Display**: Shows daily schedules for all year groups
- **XML Data Support**: Loads data from Sentral XML exports
- **Configurable Display**: Customizable school branding and colors
- **Static File Deployment**: Works on any web server
- **Sample Data**: Includes demonstration data for testing

### 📋 Core Features

- **Bell Times Display**: Period start/end times
- **Teacher Information**: Staff assignments for classes
- **Room Allocations**: Classroom locations
- **Year Group Organization**: Separate views for different year levels

### 🛠️ Technical

- **Pure HTML/CSS/JavaScript**: No framework dependencies
- **Cross-browser Compatible**: Works on all modern browsers
- **Mobile Responsive**: Touch-friendly interface
- **Easy Configuration**: JSON-based settings

---

## Version Numbering

- **Major** (X.0.0): Breaking changes or major new features
- **Minor** (0.X.0): New features, enhancements, significant improvements
- **Patch** (0.0.X): Bug fixes, documentation updates, minor improvements

## Support

For issues related to specific versions:

- **v2.2+**: Check the red notices on screen for data problems and the workflow to run
- **v2.1+**: Check the [Debugging Guide](docs/DEBUGGING_GUIDE.md) for GitHub Actions troubleshooting
- **v2.0+**: See [GitHub Actions Setup](docs/GITHUB_ACTIONS_SETUP.md) for automation configuration
- **All versions**: Review [Configuration Guide](docs/CONFIGURATION.md) for setup help

## Migration Notes

### Upgrading to v2.2

- **Deploy `timetable-core.js`** alongside `index.html` (required)
- **Optional**: Add `"stale_days": 30` under `dataSources.bell_times` in `config.json` (30 is the default)
- **Run the "Weekly Data Update" workflow** once to refresh `bell_times.json` and clear the stale notice
- **Existing setups continue working** with XML fallback

### Upgrading to v2.1

- **No configuration changes required**
- **Workflows auto-update** when you pull latest changes
- **Existing setup continues working** with improved reliability

### Upgrading to v2.0

- **Add repository secrets** for API keys if using automation
- **Update config.json** with new API settings
- **Enable GitHub Actions** for automated updates
- **Previous XML-only setups continue working** as fallback
