// Pure timetable logic shared by index.html (browser) and tests (Node).
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    } else {
        root.TimetableCore = api;
    }
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const MS_PER_DAY = 24 * 60 * 60 * 1000;
    const DEFAULT_CLASS_CODE_PATTERN = /^(\d+)/;
    const MAX_PERIOD_STEPS = 40;
    const UNSAFE_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

    const DEFAULT_CONFIG = {
        school: {
            name: 'Tempe High School',
            logo: {
                url: 'https://tempe-h.schools.nsw.gov.au/content/dam/doe/sws/schools/t/tempe-h/logo.png',
                opacity: 0.15,
                size: 'auto 100vh'
            }
        },
        api: { sync_days: 7, use_json: true, fallback_to_xml: true },
        colors: {
            primary: '#AC0000',
            background: '#f7f8fc',
            overlay: 'rgba(247, 248, 252, 0.3)',
            tile: { background: '#EDEDEE', border: '#555', shadow: '#b5b7b9', hover: '#EDEDEE' },
            text: { primary: '#1a2325', secondary: '#b5b7b9', classCode: '#AC0000' }
        },
        schedule: {
            ignoredDays: [0, 6],
            schoolDays: [1, 2, 3, 4, 5],
            defaultShowMinutesBefore: 10,
            periods: {
                P0: { showFromDay: 5, showFromTime: '15:05', showUntilStart: true, description: 'Period 0' },
                P1: { showFromTime: '08:20', description: 'Period 1' }
            }
        },
        sportPeriods: {
            tuesday: {
                periods: ['P5', 'P6'],
                yearGroups: {
                    7: { label: 'Year 7 & 8 Sport', includesYears: [7, 8], excludeYears: [8] },
                    9: { label: 'Year 9 & 10 Sport', includesYears: [9, 10], excludeYears: [10] }
                }
            }
        },
        yearGroups: {
            multiRowYears: [7, 9],
            displayYears: [7, 8, 9, 10, 11, 12],
            classCodePattern: '^(\\d+)'
        },
        ui: {
            refreshInterval: 60000,
            cacheBusting: true,
            debug: false,
            responsive: { breakpoints: { large: 1700, medium: 1280, small: 700, compactHeight: 800 } }
        },
        dataSources: {
            calendar: { json_file: 'calendar.json', xml_file: 'calendar.xml' },
            bell_times: { json_file: 'bell_times.json', xml_file: 'bell_times.xml', stale_days: 30 },
            liss_info: { json_file: 'liss_info.json', xml_file: 'liss_info.xml' }
        }
    };

    // --- generic helpers ---

    const isPlainObject = v => v !== null && typeof v === 'object' && !Array.isArray(v);
    const clone = v => JSON.parse(JSON.stringify(v));

    function mergeConfig(defaults, loaded) {
        const result = clone(defaults);
        if (!isPlainObject(loaded)) return result;
        for (const [k, v] of Object.entries(loaded)) {
            if (UNSAFE_KEYS.has(k)) continue;
            if (isPlainObject(v) && isPlainObject(result[k])) {
                result[k] = mergeConfig(result[k], v);
            } else {
                result[k] = v !== null && typeof v === 'object' ? clone(v) : v;
            }
        }
        return result;
    }

    function getStaleDays(config, source) {
        const sourceDays = config && config.dataSources && config.dataSources[source] && config.dataSources[source].stale_days;
        if (Number.isFinite(sourceDays) && sourceDays > 0) return sourceDays;
        const syncDays = config && config.api && config.api.sync_days;
        if (Number.isFinite(syncDays) && syncDays > 0) return syncDays;
        return 7;
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function parseTime(timeStr) {
        if (typeof timeStr !== 'string') return null;
        const match = timeStr.trim().match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
        if (!match) return null;
        const hours = Number(match[1]);
        const minutes = Number(match[2]);
        if (hours > 23 || minutes > 59) return null;
        return hours * 60 + minutes;
    }

    function isDataStale(metadata, maxAgeDays = 7, now = new Date()) {
        if (!metadata) return true;
        const timestamp = metadata.generated_at || metadata.generated || metadata.timestamp;
        if (!timestamp) return true;
        const generated = new Date(timestamp);
        if (Number.isNaN(generated.getTime())) return true;
        return (now - generated) / MS_PER_DAY > maxAgeDays;
    }

    // --- dates and calendar ---

    const pad2 = n => (n < 10 ? '0' + n : String(n));

    function toDate(value) {
        const d = value instanceof Date ? value : new Date(value);
        return Number.isNaN(d.getTime()) ? null : d;
    }

    function toDateKey(value) {
        const d = toDate(value);
        return d ? `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}` : null;
    }

    const startOfDay = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const formatAuDate = d => `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
    const formatLongDay = d => d.toLocaleDateString('en-AU', { weekday: 'long' });

    function findCalendarEntry(calendarData, targetDate) {
        const targetKey = toDateKey(targetDate);
        if (!targetKey || !Array.isArray(calendarData)) return undefined;
        return calendarData.find(e => e && toDateKey(e.date) === targetKey);
    }

    function getDayNumber(calendarData, targetDate) {
        const entry = findCalendarEntry(calendarData, targetDate);
        if (!entry) return null;
        const n = Number(entry.dayNumber);
        return Number.isInteger(n) && n > 0 ? n : null;
    }

    function mergeCalendars(primary, secondary) {
        const byKey = new Map();
        for (const list of [secondary, primary]) {
            for (const entry of Array.isArray(list) ? list : []) {
                const k = entry && toDateKey(entry.date);
                if (k) byKey.set(k, entry);
            }
        }
        return [...byKey.values()].sort((a, b) => toDate(a.date) - toDate(b.date));
    }

    function isSchoolDay(calendarData, date, config) {
        const entry = findCalendarEntry(calendarData, date);
        if (entry) {
            return typeof entry.isSchoolDay === 'boolean' ? entry.isSchoolDay : Number(entry.dayNumber) > 0;
        }
        const dow = date.getDay();
        const schedule = (config && config.schedule) || DEFAULT_CONFIG.schedule;
        return schedule.schoolDays.includes(dow) && !schedule.ignoredDays.includes(dow);
    }

    function getNextSchoolDay(date, calendarData, config, maxDays = 60) {
        const base = startOfDay(date);
        for (let i = 1; i <= maxDays; i++) {
            const candidate = new Date(base.getFullYear(), base.getMonth(), base.getDate() + i);
            if (isSchoolDay(calendarData, candidate, config)) return candidate;
        }
        return null;
    }

    // --- bell times and periods ---

    function getBellTimesForDay(bellTimes, dayNumber) {
        const valid = (Array.isArray(bellTimes) ? bellTimes : []).filter(b =>
            b && b.period && Number.isFinite(b.start) && Number.isFinite(b.end) && b.end > b.start);
        const hasDayNumbers = valid.some(b => b.dayNumber !== null && b.dayNumber !== undefined && b.dayNumber !== '');
        let selected;
        if (hasDayNumbers) {
            const n = Number(dayNumber);
            if (dayNumber === null || dayNumber === undefined || !Number.isInteger(n) || n <= 0) return [];
            selected = valid.filter(b => Number(b.dayNumber) === n);
        } else {
            const seen = new Set();
            selected = valid.filter(b => !seen.has(b.period) && seen.add(b.period));
        }
        return selected.slice().sort((a, b) => a.start - b.start);
    }

    const isBreakPeriod = bell => !!bell && (bell.type === 'R' || /^(recess|lunch|break)/i.test(bell.period));

    function bellTimesForDate(bellTimes, calendarData, date) {
        return getBellTimesForDay(bellTimes, getDayNumber(calendarData, date));
    }

    function firstPeriodOfNextSchoolDay(bellTimes, calendarData, date, config) {
        const next = getNextSchoolDay(date, calendarData, config);
        if (!next) return { period: null, date, forceNextDay: true, reason: 'no-school-day' };
        const dayNumber = getDayNumber(calendarData, next);
        if (!dayNumber) return { period: null, date: next, forceNextDay: true, reason: 'no-calendar' };
        const bells = getBellTimesForDay(bellTimes, dayNumber);
        if (!bells.length) return { period: null, date: next, forceNextDay: true, reason: 'no-bell-times' };
        return { period: bells[0].period, date: next, forceNextDay: true };
    }

    function getCurrentPeriodOrNext(bellTimes, calendarData, now, config) {
        const schedule = (config && config.schedule) || DEFAULT_CONFIG.schedule;
        const periodConfigs = schedule.periods || {};
        const today = startOfDay(now);

        if (!isSchoolDay(calendarData, today, config)) {
            return firstPeriodOfNextSchoolDay(bellTimes, calendarData, today, config);
        }

        const dayNumber = getDayNumber(calendarData, today);
        const dayBells = getBellTimesForDay(bellTimes, dayNumber);
        if (!dayBells.length) {
            return { period: null, date: now, forceNextDay: false, reason: dayNumber ? 'no-bell-times' : 'no-calendar' };
        }

        const minutes = now.getHours() * 60 + now.getMinutes();
        const defaultLead = Number.isFinite(schedule.defaultShowMinutesBefore) ? schedule.defaultShowMinutesBefore : 10;

        // Cross-day periods (e.g. P0 shown from Friday 15:05 for the next school day).
        for (const bell of dayBells) {
            const pc = periodConfigs[bell.period];
            if (pc && pc.showFromDay !== undefined && now.getDay() === pc.showFromDay) {
                const showFrom = parseTime(pc.showFromTime);
                if (showFrom !== null && minutes >= showFrom) {
                    const next = getNextSchoolDay(today, calendarData, config);
                    if (!next) return { period: null, date: now, forceNextDay: true, reason: 'no-school-day' };
                    return { period: bell.period, date: next, forceNextDay: true };
                }
            }
        }

        const showFromOf = bell => {
            const pc = periodConfigs[bell.period];
            const configuredFrom = pc ? parseTime(pc.showFromTime) : null;
            return configuredFrom !== null ? configuredFrom : bell.start - defaultLead;
        };

        for (let i = 0; i < dayBells.length; i++) {
            const bell = dayBells[i];
            const pc = periodConfigs[bell.period];
            if (pc && pc.showFromDay !== undefined) {
                if (pc.showUntilStart && minutes < bell.start) {
                    return { period: bell.period, date: now, forceNextDay: false };
                }
                continue;
            }
            if (minutes >= showFromOf(bell) && minutes < bell.end) {
                // A break gives way to the next period once that period's lead time starts.
                const next = dayBells[i + 1];
                const chosen = isBreakPeriod(bell) && next && minutes >= showFromOf(next) ? next : bell;
                return { period: chosen.period, date: now, forceNextDay: false };
            }
        }

        if (minutes >= dayBells[dayBells.length - 1].end) {
            return firstPeriodOfNextSchoolDay(bellTimes, calendarData, today, config);
        }
        return { period: dayBells[0].period, date: now, forceNextDay: false };
    }

    function getNextPeriod(bellTimes, calendarData, currentPeriod, currentDate, config) {
        const dayBells = bellTimesForDate(bellTimes, calendarData, currentDate);
        const index = dayBells.findIndex(b => b.period === currentPeriod);
        if (index !== -1) {
            for (let i = index + 1; i < dayBells.length; i++) {
                if (dayBells[i].period !== currentPeriod) {
                    return { period: dayBells[i].period, date: currentDate, forceNextDay: false };
                }
            }
        }
        return firstPeriodOfNextSchoolDay(bellTimes, calendarData, currentDate, config);
    }

    // --- sport periods and lessons ---

    function getSportConfig(calendarData, targetDate, period, config) {
        if (!config || !isPlainObject(config.sportPeriods)) return null;
        const entry = findCalendarEntry(calendarData, targetDate);
        const dayName = entry && typeof entry.dayName === 'string' ? entry.dayName.toLowerCase() : '';
        if (!dayName) return null;
        for (const [dayKey, sportConfig] of Object.entries(config.sportPeriods)) {
            if (sportConfig && Array.isArray(sportConfig.periods) &&
                dayName.startsWith(dayKey.toLowerCase().substring(0, 3)) &&
                sportConfig.periods.includes(period)) {
                return sportConfig;
            }
        }
        return null;
    }

    function isConfiguredSportPeriod(calendarData, targetDate, period, config) {
        return getSportConfig(calendarData, targetDate, period, config) !== null;
    }

    function shouldExcludeYearFromSport(year, calendarData, targetDate, period, config) {
        const sportConfig = getSportConfig(calendarData, targetDate, period, config);
        if (!sportConfig || !isPlainObject(sportConfig.yearGroups)) return false;
        const y = parseInt(year, 10);
        return Object.values(sportConfig.yearGroups).some(g => g && Array.isArray(g.excludeYears) && g.excludeYears.includes(y));
    }

    function getYearLabel(year, calendarData, targetDate, period, config) {
        const sportConfig = getSportConfig(calendarData, targetDate, period, config);
        const group = sportConfig && sportConfig.yearGroups && sportConfig.yearGroups[year];
        return group && group.label ? group.label : `Year ${year}`;
    }

    const patternCache = new Map();
    function getClassCodeRegex(config) {
        const pattern = config && config.yearGroups && config.yearGroups.classCodePattern;
        if (!pattern) return DEFAULT_CLASS_CODE_PATTERN;
        if (!patternCache.has(pattern)) {
            let regex;
            try {
                regex = new RegExp(pattern);
            } catch (e) {
                regex = DEFAULT_CLASS_CODE_PATTERN;
            }
            patternCache.set(pattern, regex);
        }
        return patternCache.get(pattern);
    }

    function groupLessonsByYear(lessons, period, dayNumber, calendarData, targetDate, config) {
        const byYear = {};
        const n = Number(dayNumber);
        if (!Number.isInteger(n) || n <= 0 || !Array.isArray(lessons)) return byYear;
        const regex = getClassCodeRegex(config);
        const sportConfig = getSportConfig(calendarData, targetDate, period, config);

        for (const lesson of lessons) {
            if (!lesson || !lesson.ClassCode || lesson.Period !== period || Number(lesson.DayNumber) !== n) continue;
            const match = String(lesson.ClassCode).match(regex);
            if (!match || !match[1]) continue;
            const year = match[1];
            if (sportConfig && shouldExcludeYearFromSport(year, calendarData, targetDate, period, config)) continue;
            (byYear[year] = byYear[year] || []).push({
                ClassCode: lesson.ClassCode,
                TeacherCode: lesson.TeacherCode,
                RoomCode: lesson.RoomCode
            });
        }
        return byYear;
    }

    function hasClassesForDisplayYears(lessonsByYear, config) {
        const years = (config && config.yearGroups && config.yearGroups.displayYears) || DEFAULT_CONFIG.yearGroups.displayYears;
        return years.some(y => lessonsByYear[String(y)] && lessonsByYear[String(y)].length > 0);
    }

    function describeMissing(candidate, now) {
        const date = (candidate && candidate.date) || now;
        const label = `${formatLongDay(date)} ${formatAuDate(date)}`;
        switch (candidate && candidate.reason) {
            case 'no-calendar': return `No timetable data for ${label}`;
            case 'no-bell-times': return `No bell times for ${label}`;
            case 'no-school-day': return 'No upcoming school days found';
            default: return 'No classes scheduled';
        }
    }

    // Finds the current/next period that actually has classes to show.
    function selectDisplay({ bellTimes, lessons, calendar, now, config }) {
        const nowKey = toDateKey(now);
        let candidate = getCurrentPeriodOrNext(bellTimes, calendar, now, config);

        for (let step = 0; step < MAX_PERIOD_STEPS && candidate && candidate.period; step++) {
            const dayNumber = getDayNumber(calendar, candidate.date);
            if (!dayNumber) {
                candidate = { ...candidate, period: null, reason: 'no-calendar' };
                break;
            }
            const bell = getBellTimesForDay(bellTimes, dayNumber).find(b => b.period === candidate.period);
            if (!isBreakPeriod(bell)) {
                const lessonsByYear = groupLessonsByYear(lessons, candidate.period, dayNumber, calendar, candidate.date, config);
                if (hasClassesForDisplayYears(lessonsByYear, config)) {
                    return {
                        period: candidate.period,
                        date: candidate.date,
                        forceNextDay: toDateKey(candidate.date) !== nowKey,
                        dayNumber,
                        lessonsByYear
                    };
                }
            }
            candidate = getNextPeriod(bellTimes, calendar, candidate.period, candidate.date, config);
        }

        return {
            period: null,
            date: (candidate && candidate.date) || now,
            forceNextDay: false,
            dayNumber: null,
            lessonsByYear: {},
            message: describeMissing(candidate, now)
        };
    }

    // --- data source selection ---

    const hasData = d => (Array.isArray(d) ? d.length > 0 : d !== null && d !== undefined);
    const errorMessage = e => (e && e.message ? e.message : String(e));

    // Order: fresh JSON -> XML -> stale JSON (better than a blank screen).
    // jsonStatus/generatedAt/jsonError/xmlError explain the choice so the UI can warn about it.
    async function loadWithFallback({ loadJson, loadXml, maxAgeDays = 7, now = new Date(), useJson = true, fallbackToXml = true }) {
        const errors = [];
        const status = { jsonStatus: useJson ? 'failed' : 'disabled', generatedAt: null, jsonError: null, xmlError: null };
        let staleData = null;

        if (useJson) {
            try {
                const result = await loadJson();
                if (!result || !hasData(result.data)) throw new Error('JSON contained no data');
                const metadata = result.metadata || {};
                status.generatedAt = metadata.generated_at || metadata.generated || metadata.timestamp || null;
                if (!isDataStale(result.metadata, maxAgeDays, now)) {
                    return { data: result.data, source: 'json', ...status, jsonStatus: 'fresh' };
                }
                status.jsonStatus = 'stale';
                staleData = result.data;
                errors.push(`JSON: stale (older than ${maxAgeDays} days)`);
            } catch (e) {
                status.jsonError = errorMessage(e);
                errors.push(`JSON: ${status.jsonError}`);
            }
        }

        if (fallbackToXml || !useJson) {
            try {
                const data = await loadXml();
                if (!hasData(data)) throw new Error('XML contained no data');
                return { data, source: 'xml', ...status };
            } catch (e) {
                status.xmlError = errorMessage(e);
                errors.push(`XML: ${status.xmlError}`);
            }
        }

        if (staleData !== null) return { data: staleData, source: 'json-stale', ...status };
        throw new Error(`All data sources failed - ${errors.join('; ')}`);
    }

    const NOTICE_SOURCES = [
        ['bell_times', 'Bell times', 'Weekly Data Update'],
        ['calendar', 'Calendar', 'Weekly Data Update'],
        ['liss_info', 'Timetable', 'LISS Timetable Updates']
    ];

    function describeAge(generatedAt, now) {
        const generated = generatedAt ? toDate(generatedAt) : null;
        if (!generated) return 'last updated: unknown';
        const days = Math.max(0, Math.floor((now - generated) / MS_PER_DAY));
        return `last updated ${formatAuDate(generated)}, ${days} day${days === 1 ? '' : 's'} ago`;
    }

    // Plain-English warnings for the kiosk screen; empty when all data is fresh.
    function getDataNotices(statuses, now = new Date()) {
        if (!isPlainObject(statuses)) return [];
        const notices = [];
        for (const [key, label, workflow] of NOTICE_SOURCES) {
            const s = statuses[key];
            if (!s) continue;
            const action = `Run the "${workflow}" GitHub workflow.`;
            if (s.failed) {
                notices.push(s.hasPreviousData
                    ? `${label} could not be refreshed - showing previously loaded data. ${action}`
                    : `${label} could not be loaded. ${action}`);
            } else if (s.source === 'json-stale') {
                notices.push(`${label} data is stale (${describeAge(s.generatedAt, now)}) and the XML backup is unavailable - times shown may be out of date. ${action}`);
            } else if (s.source === 'xml' && s.jsonStatus === 'stale') {
                notices.push(`${label} data is stale (${describeAge(s.generatedAt, now)}) - showing XML backup. ${action}`);
            } else if (s.source === 'xml' && s.jsonStatus === 'failed') {
                notices.push(`${label} JSON is unavailable - showing XML backup. ${action}`);
            }
        }
        return notices;
    }

    return {
        DEFAULT_CONFIG,
        mergeConfig,
        getStaleDays,
        escapeHtml,
        parseTime,
        isDataStale,
        toDateKey,
        formatAuDate,
        formatLongDay,
        findCalendarEntry,
        getDayNumber,
        mergeCalendars,
        isSchoolDay,
        getNextSchoolDay,
        getBellTimesForDay,
        isBreakPeriod,
        getCurrentPeriodOrNext,
        getNextPeriod,
        isConfiguredSportPeriod,
        shouldExcludeYearFromSport,
        getYearLabel,
        groupLessonsByYear,
        hasClassesForDisplayYears,
        selectDisplay,
        loadWithFallback,
        getDataNotices
    };
});
