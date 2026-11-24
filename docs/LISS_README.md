# LISS-Compatible Timetable Data

Advanced timetable integration using Sentral REST API with LISS-compatible output format.

## 🎯 What This Provides

This implementation uses the **Sentral REST API** (documented at https://development.sentral.com.au/) to generate LISS-compatible JSON data including:

- Individual student timetables
- Teacher assignments
- Room allocations
- Subject codes and periods
- Year group organization

## 🔄 LISS Compatibility

While the current implementation uses Sentral's REST API, it generates data in **LISS-compatible JSON format** for:

- **Cross-compatibility** with Learning Information Systems Standard (LISS)
- **Future integration** with Edval when LISS support is added
- **Standardized format** that works across different timetabling systems
- **Easy migration** to native LISS when available

## ⚡ Quick Setup

### Generate LISS-Compatible Data

Run the optimized timetable generator:

```bash
python generate_liss_info.py
```

This creates `liss_info.json` with complete timetable data using Sentral REST API in LISS format.

### Performance Features (v2.0+)

- **⚡ 20x faster**: ~1.3 seconds vs 26+ seconds
- **📉 95% fewer API calls**: ~10 calls vs 700+ calls
- **🔧 Bulk operations**: Uses Sentral REST API include parameters
- **📊 Complete logging**: Generation and validation logs
- **🎯 LISS format**: Compatible with LISS standard for future migration
- **🤖 Automated updates**: GitHub Actions run every 15 minutes during school hours

### GitHub Actions Integration (v2.1)

The LISS data generation is now fully automated:

- **Smart scheduling**: Updates every 15 minutes during school hours only (7:30 AM - 3:30 PM weekdays)
- **Time zone aware**: Handles Sydney AEST/AEDT automatically
- **Conflict resolution**: Fixed git merge issues in v2.1
- **Error recovery**: Robust handling of network and API issues

## 🔧 Configuration

### Sentral REST API Setup

Add your Sentral configuration to the `api.sentral` section in `config.json`:

```json
{
  "api": {
    "sentral": {
      "base_url": "https://<your-school-sentral>/",
      "api_key": "${REST_API_KEY}",
      "tenant": "your-tenant-id",
      "api_path": "/api/v1"
    }
  }
}
```

**API Documentation**: Full Sentral REST API documentation available at https://development.sentral.com.au/

### Advanced Options

Edit `generate_liss_info.py` for customization:

- **Days ahead**: How many days to fetch (default: 7)
- **Year groups**: Which years to include (default: all)
- **Data filtering**: Exclude specific periods or subjects

### Output Format

Creates `liss_info.json` with LISS-compatible structure using Sentral REST API data:

```json
{
  "metadata": {
    "school": "TEMPE",
    "generated_at": "2025-08-22T04:43:26.856133",
    "source": "sentral_rest_api",
    "format": "liss_compatible",
    "total_lessons": 350,
    "date_range": "2025-08-22 to 2025-08-29",
    "optimization": "Bulk REST API operations",
    "api_calls_reduced": "From 700+ to 6 calls total"
  },
  "timetable_data": [
    {
      "DayNumber": 1,
      "Period": "P1",
      "ClassCode": "9MU1",
      "EdvalClassCode": "9MU1",
      "TeacherCode": "LADO",
      "TeacherId": "12345",
      "RoomCode": "P5"
    }
  ]
}
```

### Technical Implementation

- **Data Source**: Sentral REST API (https://development.sentral.com.au/)
- **Format**: LISS-compatible JSON structure
- **Performance**: Bulk API operations with include parameters
- **Validation**: Automatic data integrity checks
- **Future-Ready**: Compatible with LISS when Edval integration is added

## 📊 Edval LISS Bell Times Integration

### Basic Usage

````bash
# Fetch bell times using default config
python3 liss_bell_times.py

# Test connection only
## 🚀 Usage

### Automated Generation (Recommended)

Use GitHub Actions for automatic updates:

1. **Repository Secrets**: Add `REST_API_KEY` to your repository
2. **Enable Workflows**: LISS data updates during school hours (7:30 AM - 3:30 PM)
3. **Manual Trigger**: Use "Run workflow" button for immediate updates

### Manual Generation

Run the script locally for testing or one-off generation:

```bash
# Generate 7 days of timetable data
python3 generate_liss_info.py

# Check output
ls -la liss_info.json .logs/liss_info_generation.log
````

## 🔍 Output Format

The generated `liss_info.json` follows LISS standard format:

```json
{
  "metadata": {
    "school": "TEMPE",
    "generated_at": "2025-08-22T04:43:26.856133",
    "source": "sentral_rest_api",
    "format": "liss_compatible",
    "total_lessons": 350,
    "date_range": "2025-08-22 to 2025-08-29"
  },
  "timetable_data": [
    {
      "DayNumber": 1,
      "Period": "P1",
      "ClassCode": "9MU1",
      "EdvalClassCode": "9MU1",
      "TeacherCode": "LADO",
      "TeacherId": "12345",
      "RoomCode": "P5"
    }
  ],
  "daily_changes": [
    {
      "Date": "2025-08-22",
      "Type": "Class",
      "Period": "P1",
      "ClassCode": "9MU1",
      "TeacherCode": "JONES",
      "RoomCode": "C6"
    },
    { "Date": "2025-08-22", "Type": "Cancellation", "Period": "P2", "Year": "12" },
    { "Date": "2025-08-22", "Type": "Cancellation", "Period": "P3", "Year": "11", "Subject": "EMAT" }
  ]
}
```

### Daily changes

`timetable_data` is the normal Day 1–10 cycle. `daily_changes` comes from Sentral's
`timetable-daily-lesson` endpoint (today to +7 days, Sydney time) and overrides the cycle for a
specific date and period:

- **`Class`** (Sentral `Class` or `Cover`): replaces that class's cycle lesson, e.g. a cover teacher or room change.
- **`Cancellation`**: hides lessons. It targets one `ClassCode`, or a cohort taken from Sentral's
  name such as "Year 12 Cancellation" (`Year: "12"`) or "Year 11 EMAT Cancellation"
  (`Year: "11"`, `Subject: "EMAT"`, matching `11EMAT1` but not `11EMAX1`).
- Events, duties, staff meetings and other daily lesson types are ignored. Records with no period are skipped.

If the daily changes can't be fetched, the generator fails and the previous `liss_info.json` is kept.
The XML backup has no daily changes, so it only shows the normal cycle.

## 🔧 Troubleshooting

### No Data Generated

1. **Check API credentials** in repository secrets
2. **Verify Sentral API access** - test at `https://your-school-sentral.com.au/restapi/v1/ping`
3. **Check logs** in `.logs/liss_info_generation.log`

### Performance Issues

1. **Reduce data range** - edit `generate_liss_info.py` to fetch fewer days
2. **Check API rate limits** - Sentral may throttle high-frequency requests
3. **Monitor API calls** - logs show optimization metrics

### Integration with Kiosk

The generated `liss_info.json` automatically integrates with the timetable kiosk:

- **Automatic detection**: Kiosk loads LISS data when available
- **Fallback support**: Falls back to standard data if LISS unavailable
- **Real-time updates**: GitHub Actions keep data fresh during school hours

## 🎯 Future LISS Integration

When Edval adds native LISS support:

- **Easy migration**: Data format already LISS-compatible
- **Minimal changes**: Same JSON structure will work
- **Cross-compatibility**: Supports both Sentral API and native LISS
- **Standardized**: Follows LISS specification for maximum compatibility

## 📚 References

- **Sentral REST API**: https://development.sentral.com.au/
- **LISS Standard**: Learning Information Systems Standard
- **GitHub Actions**: Automated updates during school hours
- **Edval Integration**: Future native LISS support planned

The bell times JSON can be used by your main timetable kiosk application to display current bell times and determine which period is currently active.

## Technical Notes

- Uses JSON-RPC 2.0 protocol as specified by LISS
- Implements proper error handling and logging
- Handles Edval-specific authentication requirements
- Compatible with LISS specification version 0.9.3
