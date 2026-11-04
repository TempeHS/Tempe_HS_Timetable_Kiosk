# Timetable Kiosk Configuration Guide

Complete reference for configuring the timetable kiosk for your school.

## 🎯 Quick Configuration

### Essential Settings

The minimum configuration requires updating just a few settings in `config.json`:

```json
{
  "school": {
    "name": "Your School Name",
    "term": "Term 1 2025"
  },
  "api": {
    "sync_days": 7
  }
}
```

### For GitHub Pages Deployment

1. **Fork this repository** to your GitHub account
2. **Edit `config.json`** with your school's settings (see below)
3. **Enable GitHub Pages**: Settings → Pages → Deploy from branch `main`
4. **Access your kiosk**: `https://yourusername.github.io/repository-name`

### For School Website Deployment

1. **Download all files** from this repository
2. **Customize `config.json`** with your school settings
3. **Upload to web server** (any directory accessible via web browser)
4. **Link to `index.html`** from your school website

## 📝 Configuration Reference

### School Information

```json
{
  "school": {
    "name": "Your School Name",
    "logo": {
      "url": "https://your-school.edu/logo.png",
      "opacity": 0.15,
      "size": "auto 100vh"
    }
  }
}
```

- **name**: The school name that appears in the browser title
- **logo.url**: Direct URL to your school's logo image
- **logo.opacity**: Logo transparency (0.0 to 1.0)
- **logo.size**: CSS background-size property for the logo

### Colors and Styling

```json
{
  "colors": {
    "primary": "#AC0000",
    "background": "#f7f8fc",
    "overlay": "rgba(247, 248, 252, 0.3)",
    "tile": {
      "background": "#EDEDEE",
      "border": "#555",
      "shadow": "#b5b7b9",
      "hover": "#EDEDEE"
    },
    "text": {
      "primary": "#1a2325",
      "secondary": "#b5b7b9",
      "classCode": "#AC0000"
    }
  }
}
```

- **primary**: Main school color (used for year labels and class codes)
- **background**: Page background color
- **overlay**: Semi-transparent overlay color
- **tile**: Colors for class tiles (background, border, shadow, hover effect)
- **text**: Text colors for different elements

### Schedule Configuration

```json
{
  "schedule": {
    "ignoredDays": [0, 6],
    "schoolDays": [1, 2, 3, 4, 5],
    "defaultShowMinutesBefore": 10,
    "periods": {
      "P0": {
        "showFromDay": 5,
        "showFromTime": "15:05",
        "showUntilStart": true,
        "description": "Period 0"
      },
      "P1": {
        "showFromTime": "08:20",
        "description": "Period 1"
      }
    }
  }
}
```

- **ignoredDays**: Array of days to skip (0=Sunday, 1=Monday, ..., 6=Saturday)
- **schoolDays**: Array of school days
- **defaultShowMinutesBefore**: How many minutes before a period starts to show it
- **periods**: Special configurations for specific periods
  - **showFromDay**: Day of week to start showing this period (for cross-day periods)
  - **showFromTime**: Time to start showing the period (HH:MM format)
  - **showUntilStart**: Whether to show until the period actually starts
  - **description**: Display name for the period

### Sport Periods

```json
{
  "sportPeriods": {
    "tuesday": {
      "periods": ["P5", "P6"],
      "yearGroups": {
        "7": {
          "label": "Year 7 & 8 Sport",
          "includesYears": [7, 8],
          "excludeYears": [8]
        },
        "9": {
          "label": "Year 9 & 10 Sport",
          "includesYears": [9, 10],
          "excludeYears": [10]
        }
      }
    }
  }
}
```

Configure special periods like sport where year groups are combined:

- **periods**: Array of period codes that are sport periods
- **yearGroups**: Configuration for each year group
  - **label**: Display name for the combined years
  - **includesYears**: Years that should show under this label
  - **excludeYears**: Years to exclude from showing individual classes

### Year Groups

```json
{
  "yearGroups": {
    "multiRowYears": [7, 9],
    "displayYears": [7, 8, 9, 10, 11, 12],
    "classCodePattern": "^(\\d+)"
  }
}
```

- **multiRowYears**: Year groups that should display in multiple rows instead of single row
- **displayYears**: Which year levels to display
- **classCodePattern**: Regex pattern to extract year from class codes

### User Interface

```json
{
  "ui": {
    "refreshInterval": 60000,
    "autoRefresh": true,
    "hourlyReload": true,
    "cacheBusting": true,
    "responsive": {
      "breakpoints": {
        "large": 1700,
        "medium": 1280,
        "small": 700,
        "compactHeight": 800
      }
    }
  }
}
```

#### Refresh & Reload Settings

- **refreshInterval**: How often to refresh data (milliseconds, default: 60000 = 1 minute)
- **autoRefresh**: Enable/disable automatic data refresh (default: true)
- **hourlyReload**: Enable/disable full page reload every hour to prevent memory leaks (default: true)

On low-memory devices, refreshes never overlap: a timer tick is skipped if the
previous refresh is still running. Each network request has a 15-second timeout,
including downloading its response body. Failed sources retain their last good
data, and unchanged header, timetable, and notice HTML is not replaced in the DOM.
These safeguards also apply to the initial data load; configuration and reload
connectivity checks use the same request timeout.

#### Automatic Reload Schedule

The kiosk has multiple reload strategies for optimal performance:

1. **Data Refresh**: Every minute (configurable via `refreshInterval`)
   - Smooth data updates without page flash
   - Updates timetable content seamlessly
   - Controlled by `autoRefresh` setting

2. **Hourly Reload**: Every hour (configurable via `hourlyReload`)
   - Full page reload to clear memory leaks
   - Can be disabled by setting `hourlyReload: false`
   - Helps maintain long-term stability

3. **Daily Fresh Start**: Every morning at 7:30am (automatic)
   - Full page reload before school hours
   - Ensures optimal performance each school day
   - Cannot be disabled (essential for kiosk reliability)

#### Other UI Settings

- **cacheBusting**: Whether to add timestamps to prevent caching
- **responsive.breakpoints**: Screen size breakpoints for responsive design
  - **large**, **medium**, **small**: Width breakpoints for general responsive design
  - **compactHeight**: Height breakpoint for compact layout mode (pixels)

#### Responsive Layout Behavior

The timetable automatically adapts to different screen heights using the `compactHeight` breakpoint:

**Tall Screens (above compactHeight):**

- Traditional layout with year labels positioned above the class tiles
- More spacious margins and padding
- Suitable for desktop displays and large screens

**Short Screens (at or below compactHeight):**

- Compact layout with year labels positioned to the left of class tiles
- Reduced margins and tighter spacing
- Optimized for tablets, laptops, and shorter displays
- Year labels become right-aligned next to the tiles

**Configuration Example:**

```json
{
  "ui": {
    "responsive": {
      "breakpoints": {
        "compactHeight": 800
      }
    }
  }
}
```

With `compactHeight: 800`:

- Screens with height > 800px: Traditional layout (labels above)
- Screens with height ≤ 800px: Compact layout (labels left)

This ensures optimal viewing experience across different display types commonly used in schools.

### Data Files

```json
{
  "files": {
    "bellTimes": "bell_times.xml",
    "lessons": "liss_info.xml",
    "calendar": "calendar.xml"
  }
}
```

- **bellTimes**: Filename for bell times XML
- **lessons**: Filename for lessons XML
- **calendar**: Filename for calendar XML

## Example Configurations

### Different School Example

```json
{
  "school": {
    "name": "Riverside Secondary College",
    "logo": {
      "url": "https://riverside-sc.edu.au/assets/logo.png",
      "opacity": 0.2,
      "size": "contain"
    }
  },
  "colors": {
    "primary": "#003366",
    "background": "#f0f4f8",
    "text": {
      "classCode": "#003366"
    }
  },
  "schedule": {
    "ignoredDays": [0, 6],
    "defaultShowMinutesBefore": 15,
    "periods": {
      "HR": {
        "showFromTime": "08:30",
        "description": "Home Room"
      }
    }
  },
  "yearGroups": {
    "displayYears": [8, 9, 10, 11, 12],
    "multiRowYears": [8, 10]
  },
  "ui": {
    "responsive": {
      "breakpoints": {
        "compactHeight": 750
      }
    }
  }
}
```

### Primary School Example

```json
{
  "school": {
    "name": "Sunshine Primary School",
    "logo": {
      "url": "https://sunshine-ps.edu.au/logo.svg",
      "opacity": 0.1
    }
  },
  "colors": {
    "primary": "#FF6B35",
    "background": "#FFF8E1"
  },
  "yearGroups": {
    "displayYears": [1, 2, 3, 4, 5, 6],
    "multiRowYears": [1, 3, 5],
    "classCodePattern": "^(\\d+)"
  },
  "ui": {
    "responsive": {
      "breakpoints": {
        "compactHeight": 700
      }
    }
  }
}
```

## Setup Instructions

1. **Copy the base files**: `index.html`, `config.json`, and your XML data files
2. **Customize config.json**: Update all settings for your school
3. **Update XML files**: Ensure your bell times, lessons, and calendar data are in the correct format
4. **Test locally**: Use a local web server to test the configuration
5. **Deploy**: Upload all files to your web server

## Testing

The app includes a manual override feature for testing different times and dates. Set `USE_MANUAL_OVERRIDE = true` in the JavaScript section and configure the test date/time.

**For GitHub Pages testing:**

- Make changes to your repository
- Commit and push changes
- GitHub Pages will automatically update (may take a few minutes)
- Use browser developer tools (F12) to check console for errors

## Fallback Behavior

If `config.json` cannot be loaded, the app will fall back to the default Tempe High School configuration to ensure it still functions.

## File Structure

```
school-timetable/
├── index.html
├── config.json
├── bell_times.xml
├── liss_info.xml
├── calendar.xml
└── docs/
    ├── README.md
    ├── CONFIGURATION.md
    └── GITHUB_PAGES_DEPLOYMENT.md
```

## GitHub Pages Considerations

**File Access:**

- All files must be in the repository
- File names are case-sensitive
- No special server configuration needed
- Automatic HTTPS and global CDN

**Updates:**

- Changes take effect after Git commit/push
- Usually updates within 1-5 minutes
- Check GitHub Pages deployment status in repository Actions tab

**Security:**

- All files are publicly accessible
- Don't include sensitive information in configuration files
- Consider using environment variables for sensitive data if needed

## Support

The configuration system is designed to be flexible and support various school structures. If you need additional configuration options, you can extend the `config.json` file and modify the JavaScript code accordingly.

**Common Customizations:**

- Additional sport periods for different days
- More complex year group arrangements
- Custom period naming schemes
- Different timing rules for various periods
- School-specific color schemes and branding
