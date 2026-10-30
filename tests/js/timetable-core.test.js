const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const core = require('../../timetable-core.js');
const { CONFIG, buildBellTimes, buildCalendar, buildLessons, day, at, key } = require('./fixtures');

const bells = buildBellTimes();
const calendar = buildCalendar();
const lessons = buildLessons();

describe('parseTime', () => {
    it('parses HH:MM, H:MM and HH:MM:SS', () => {
        assert.equal(core.parseTime('08:45'), 525);
        assert.equal(core.parseTime('8:05'), 485);
        assert.equal(core.parseTime('08:45:00'), 525);
        assert.equal(core.parseTime('00:00'), 0);
    });

    it('returns null for missing or malformed times instead of 0/NaN', () => {
        for (const bad of ['', null, undefined, 'abc', '25:00', '12:60', '12', 'aa:bb']) {
            assert.equal(core.parseTime(bad), null, `input ${JSON.stringify(bad)}`);
        }
    });
});

describe('escapeHtml', () => {
    it('escapes HTML special characters', () => {
        assert.equal(core.escapeHtml(`<img src=x onerror="a('b')">&`), '&lt;img src=x onerror=&quot;a(&#39;b&#39;)&quot;&gt;&amp;');
    });

    it('handles null, undefined and numbers', () => {
        assert.equal(core.escapeHtml(null), '');
        assert.equal(core.escapeHtml(undefined), '');
        assert.equal(core.escapeHtml(12), '12');
    });
});

describe('isDataStale', () => {
    const now = new Date('2026-10-30T12:00:00Z');

    it('treats recent data as fresh', () => {
        assert.equal(core.isDataStale({ generated_at: '2026-10-29T12:00:00Z' }, 7, now), false);
    });

    it('treats data older than the threshold as stale', () => {
        assert.equal(core.isDataStale({ generated_at: '2026-10-20T12:00:00Z' }, 7, now), true);
    });

    it('supports the calendar "generated" key', () => {
        assert.equal(core.isDataStale({ generated: '2026-10-29T12:00:00' }, 7, now), false);
    });

    it('treats missing metadata or timestamp as stale', () => {
        assert.equal(core.isDataStale(null, 7, now), true);
        assert.equal(core.isDataStale({}, 7, now), true);
    });

    it('treats an unparseable timestamp as stale', () => {
        assert.equal(core.isDataStale({ generated_at: 'not-a-date' }, 7, now), true);
    });

    it('accepts a 20-day-old file when the threshold is 30 days (bell times)', () => {
        assert.equal(core.isDataStale({ generated_at: '2026-10-10T12:00:00Z' }, 30, now), false);
    });
});

describe('config defaults', () => {
    it('DEFAULT_CONFIG contains every key the renderer reads', () => {
        assert.equal(typeof core.DEFAULT_CONFIG.ui.responsive.breakpoints.compactHeight, 'number');
        assert.ok(Array.isArray(core.DEFAULT_CONFIG.yearGroups.displayYears));
        assert.ok(core.DEFAULT_CONFIG.schedule.periods);
    });

    it('mergeConfig fills missing nested keys from defaults', () => {
        const merged = core.mergeConfig(core.DEFAULT_CONFIG, { school: { name: 'Other HS' }, ui: { debug: true } });
        assert.equal(merged.school.name, 'Other HS');
        assert.equal(merged.ui.debug, true);
        assert.equal(merged.ui.responsive.breakpoints.compactHeight, core.DEFAULT_CONFIG.ui.responsive.breakpoints.compactHeight);
        assert.equal(merged.school.logo.url, core.DEFAULT_CONFIG.school.logo.url);
    });

    it('mergeConfig replaces arrays rather than merging them', () => {
        const merged = core.mergeConfig(core.DEFAULT_CONFIG, { yearGroups: { displayYears: [11, 12] } });
        assert.deepEqual(merged.yearGroups.displayYears, [11, 12]);
    });

    it('mergeConfig tolerates null/invalid input and never mutates defaults', () => {
        const before = JSON.stringify(core.DEFAULT_CONFIG);
        const merged = core.mergeConfig(core.DEFAULT_CONFIG, null);
        merged.school.name = 'changed';
        core.mergeConfig(core.DEFAULT_CONFIG, 'garbage');
        assert.equal(JSON.stringify(core.DEFAULT_CONFIG), before);
    });

    it('getStaleDays uses 30 days for bell times and sync_days for the rest', () => {
        assert.equal(core.getStaleDays(CONFIG, 'bell_times'), 30);
        assert.equal(core.getStaleDays(CONFIG, 'calendar'), 7);
        assert.equal(core.getStaleDays(CONFIG, 'liss_info'), 7);
        assert.equal(core.getStaleDays({}, 'bell_times'), 7);
    });
});

describe('getBellTimesForDay', () => {
    it('returns only the requested day, sorted by start time', () => {
        const tue = core.getBellTimesForDay(bells, 2);
        assert.equal(tue.length, 10);
        assert.ok(tue.every(b => b.dayNumber === 2));
        assert.deepEqual(tue.map(b => b.period), ['P0', 'P1', 'P2', 'Recess', 'P3', 'Lunch', 'P4', 'P5', 'P6', 'P7']);
    });

    it('accepts a string day number', () => {
        assert.equal(core.getBellTimesForDay(bells, '7').length, 10);
    });

    it('returns an empty list for an unknown day', () => {
        assert.deepEqual(core.getBellTimesForDay(bells, 11), []);
        assert.deepEqual(core.getBellTimesForDay(bells, null), []);
        assert.deepEqual(core.getBellTimesForDay([], 1), []);
    });

    it('uses every entry (deduplicated by period) when bell times have no day numbers', () => {
        const dayless = [
            { period: 'P2', start: 580, end: 635, dayNumber: null },
            { period: 'P1', start: 525, end: 580, dayNumber: null },
            { period: 'P1', start: 525, end: 580, dayNumber: null }
        ];
        assert.deepEqual(core.getBellTimesForDay(dayless, 3).map(b => b.period), ['P1', 'P2']);
    });

    it('drops entries with invalid times', () => {
        const withBad = [...core.getBellTimesForDay(bells, 1), { period: 'PX', start: null, end: 10, dayNumber: 1 }];
        assert.ok(!core.getBellTimesForDay(withBad, 1).some(b => b.period === 'PX'));
    });
});

describe('mergeCalendars', () => {
    it('fills dates missing from the JSON calendar with XML entries, JSON wins on overlap', () => {
        const json = buildCalendar({ from: '2026-10-25', to: '2026-11-01' }).map(e => ({ ...e, source: 'api' }));
        const xml = buildCalendar({ from: '2026-10-01', to: '2026-12-31' }).map(e => ({ ...e, source: 'xml' }));
        const merged = core.mergeCalendars(json, xml);
        const find = iso => merged.find(e => key(e.date) === iso);
        assert.equal(find('2026-10-27').source, 'api');
        assert.equal(find('2026-11-02').source, 'xml');
        assert.equal(merged.filter(e => key(e.date) === '2026-10-27').length, 1);
        assert.ok(merged.every((e, i) => i === 0 || merged[i - 1].date <= e.date));
    });

    it('handles empty or missing inputs', () => {
        assert.deepEqual(core.mergeCalendars([], []), []);
        assert.equal(core.mergeCalendars(null, calendar).length, calendar.length);
        assert.equal(core.mergeCalendars(calendar, undefined).length, calendar.length);
    });
});

describe('getNextSchoolDay', () => {
    it('Friday -> Monday', () => {
        assert.equal(key(core.getNextSchoolDay(day('2026-10-30'), calendar, CONFIG)), '2026-11-02');
    });

    it('Saturday -> Monday', () => {
        assert.equal(key(core.getNextSchoolDay(day('2026-10-31'), calendar, CONFIG)), '2026-11-02');
    });

    it('skips a public holiday from the calendar', () => {
        const cal = buildCalendar({ holidays: ['2026-11-02'] });
        assert.equal(key(core.getNextSchoolDay(day('2026-10-30'), cal, CONFIG)), '2026-11-03');
    });

    it('falls back to configured weekdays beyond the calendar range', () => {
        assert.equal(key(core.getNextSchoolDay(day('2026-11-20'), calendar, CONFIG)), '2026-11-23');
    });

    it('returns null when no school day exists within the search window', () => {
        const allHolidays = buildCalendar({ from: '2026-12-01', to: '2027-03-31' }).map(e => ({ ...e, isSchoolDay: false, dayNumber: 0 }));
        assert.equal(core.getNextSchoolDay(day('2026-12-01'), allHolidays, CONFIG), null);
    });
});

describe('getCurrentPeriodOrNext (uses only the current day\'s bell times)', () => {
    it('Monday 12:55 is Lunch (Tuesday\'s P4 must not leak into Monday)', () => {
        const r = core.getCurrentPeriodOrNext(bells, calendar, at('2026-10-26', '12:55'), CONFIG);
        assert.equal(r.period, 'Lunch');
        assert.equal(key(r.date), '2026-10-26');
    });

    it('Tuesday 11:58 is Lunch (Tuesday has early lunch)', () => {
        const r = core.getCurrentPeriodOrNext(bells, calendar, at('2026-10-27', '11:58'), CONFIG);
        assert.equal(r.period, 'Lunch');
    });

    it('Tuesday 12:20 shows P4 (10 minutes before 12:25)', () => {
        const r = core.getCurrentPeriodOrNext(bells, calendar, at('2026-10-27', '12:20'), CONFIG);
        assert.equal(r.period, 'P4');
    });

    it('Friday 15:10 shows next Monday P0', () => {
        const r = core.getCurrentPeriodOrNext(bells, calendar, at('2026-10-30', '15:10'), CONFIG);
        assert.equal(r.period, 'P0');
        assert.equal(key(r.date), '2026-11-02');
        assert.equal(r.forceNextDay, true);
    });

    it('Friday 15:10 before a Monday holiday shows Tuesday P0', () => {
        const cal = buildCalendar({ holidays: ['2026-11-02'] });
        const r = core.getCurrentPeriodOrNext(bells, cal, at('2026-10-30', '15:10'), CONFIG);
        assert.equal(key(r.date), '2026-11-03');
    });

    it('after the last period moves to the next school day', () => {
        const r = core.getCurrentPeriodOrNext(bells, calendar, at('2026-10-28', '16:30'), CONFIG);
        assert.equal(r.period, 'P0');
        assert.equal(key(r.date), '2026-10-29');
        assert.equal(r.forceNextDay, true);
    });

    it('a weekday public holiday shows the next school day', () => {
        const cal = buildCalendar({ holidays: ['2026-11-02'] });
        const r = core.getCurrentPeriodOrNext(bells, cal, at('2026-11-02', '10:00'), CONFIG);
        assert.equal(key(r.date), '2026-11-03');
        assert.equal(r.forceNextDay, true);
    });

    it('returns no period (not a guess) when the date is missing from the calendar', () => {
        const shortCal = buildCalendar({ from: '2026-10-25', to: '2026-11-01' });
        const r = core.getCurrentPeriodOrNext(bells, shortCal, at('2026-11-03', '10:00'), CONFIG);
        assert.equal(r.period, null);
    });

    it('does not throw and returns no period with empty bell times', () => {
        const r = core.getCurrentPeriodOrNext([], calendar, at('2026-10-27', '10:00'), CONFIG);
        assert.equal(r.period, null);
    });
});

describe('getNextPeriod', () => {
    it('Tuesday after P3 is Lunch, not Monday\'s P4', () => {
        const r = core.getNextPeriod(bells, calendar, 'P3', day('2026-10-27'), CONFIG);
        assert.equal(r.period, 'Lunch');
    });

    it('Monday after Lunch is P5', () => {
        const r = core.getNextPeriod(bells, calendar, 'Lunch', day('2026-10-26'), CONFIG);
        assert.equal(r.period, 'P5');
    });

    it('after the last period goes to the next school day\'s first period', () => {
        const r = core.getNextPeriod(bells, calendar, 'P7', day('2026-10-30'), CONFIG);
        assert.equal(r.period, 'P0');
        assert.equal(key(r.date), '2026-11-02');
        assert.equal(r.forceNextDay, true);
    });

    it('does not throw with empty bell times', () => {
        const r = core.getNextPeriod([], calendar, 'P1', day('2026-10-27'), CONFIG);
        assert.equal(r.period, null);
    });
});

describe('sport periods', () => {
    const tue = day('2026-10-27');
    const tueB = day('2026-11-03');
    const mon = day('2026-10-26');

    it('relabels Year 7 on Tuesday (TueA and TueB) sport periods', () => {
        assert.equal(core.getYearLabel('7', calendar, tue, 'P5', CONFIG), 'Year 7 & 8 Sport');
        assert.equal(core.getYearLabel('9', calendar, tueB, 'P6', CONFIG), 'Year 9 & 10 Sport');
    });

    it('keeps normal labels outside sport periods', () => {
        assert.equal(core.getYearLabel('7', calendar, tue, 'P4', CONFIG), 'Year 7');
        assert.equal(core.getYearLabel('7', calendar, mon, 'P5', CONFIG), 'Year 7');
        assert.equal(core.getYearLabel('11', calendar, tue, 'P5', CONFIG), 'Year 11');
    });

    it('excludes Years 8 and 10 only during Tuesday sport', () => {
        assert.equal(core.shouldExcludeYearFromSport('8', calendar, tue, 'P5', CONFIG), true);
        assert.equal(core.shouldExcludeYearFromSport('10', calendar, tue, 'P6', CONFIG), true);
        assert.equal(core.shouldExcludeYearFromSport('8', calendar, tue, 'P4', CONFIG), false);
        assert.equal(core.shouldExcludeYearFromSport('8', calendar, mon, 'P5', CONFIG), false);
    });

    it('does not throw when the calendar entry has no day name', () => {
        const cal = [{ date: tue, dayNumber: 2, isSchoolDay: true }];
        assert.equal(core.getYearLabel('7', cal, tue, 'P5', CONFIG), 'Year 7');
        assert.equal(core.shouldExcludeYearFromSport('8', cal, tue, 'P5', CONFIG), false);
    });
});

describe('groupLessonsByYear', () => {
    it('only includes the given day number and period', () => {
        const byYear = core.groupLessonsByYear(lessons, 'P1', 6, calendar, day('2026-11-02'), CONFIG);
        assert.deepEqual(Object.keys(byYear).sort(), ['10', '11', '12', '7', '8', '9']);
        assert.ok(Object.values(byYear).flat().every(l => l.ClassCode.endsWith('P1D6')));
    });

    it('accepts string day numbers from XML', () => {
        const xmlLike = lessons.map(l => ({ ...l, DayNumber: String(l.DayNumber) }));
        assert.equal(core.groupLessonsByYear(xmlLike, 'P1', 6, calendar, day('2026-11-02'), CONFIG)['7'].length, 1);
    });

    it('hides Years 8 and 10 during Tuesday sport', () => {
        const byYear = core.groupLessonsByYear(lessons, 'P5', 2, calendar, day('2026-10-27'), CONFIG);
        assert.equal(byYear['8'], undefined);
        assert.equal(byYear['10'], undefined);
        assert.ok(byYear['7']);
    });

    it('skips lessons without a class code or year', () => {
        const odd = [{ DayNumber: 1, Period: 'P1', ClassCode: null }, { DayNumber: 1, Period: 'P1', ClassCode: 'ABC' }];
        assert.deepEqual(core.groupLessonsByYear(odd, 'P1', 1, calendar, day('2026-10-26'), CONFIG), {});
    });

    it('survives an invalid classCodePattern in config', () => {
        const badConfig = { ...CONFIG, yearGroups: { ...CONFIG.yearGroups, classCodePattern: '(' } };
        const byYear = core.groupLessonsByYear(lessons, 'P1', 1, calendar, day('2026-10-26'), badConfig);
        assert.equal(byYear['7'].length, 1);
    });
});

describe('selectDisplay (what the kiosk actually shows)', () => {
    const run = (now, overrides = {}) => core.selectDisplay({ bellTimes: bells, lessons, calendar, now, config: CONFIG, ...overrides });

    it('Monday 12:55 shows Monday P5', () => {
        const r = run(at('2026-10-26', '12:55'));
        assert.equal(r.period, 'P5');
        assert.equal(key(r.date), '2026-10-26');
        assert.ok(r.lessonsByYear['7'].every(l => l.ClassCode === '7P5D1'));
    });

    it('Tuesday 11:58 skips Lunch and shows Tuesday P4', () => {
        const r = run(at('2026-10-27', '11:58'));
        assert.equal(r.period, 'P4');
        assert.ok(r.lessonsByYear['7'].every(l => l.ClassCode === '7P4D2'));
    });

    it('Friday 15:10 shows Monday (week B, day 6) P0', () => {
        const r = run(at('2026-10-30', '15:10'));
        assert.equal(r.period, 'P0');
        assert.equal(key(r.date), '2026-11-02');
        assert.equal(r.forceNextDay, true);
        assert.ok(r.lessonsByYear['11'].every(l => l.ClassCode.endsWith('D6')));
    });

    it('Friday 15:10 before a Monday holiday shows Tuesday (day 7)', () => {
        const r = run(at('2026-10-30', '15:10'), { calendar: buildCalendar({ holidays: ['2026-11-02'] }) });
        assert.equal(key(r.date), '2026-11-03');
        assert.ok(r.lessonsByYear['11'].every(l => l.ClassCode.endsWith('D7')));
    });

    it('Thursday 15:10 (P7 has no classes) moves to Friday P0', () => {
        const r = run(at('2026-10-29', '15:10'));
        assert.equal(r.period, 'P0');
        assert.equal(key(r.date), '2026-10-30');
    });

    it('week B Monday 09:00 shows day 6 lessons, not day 1', () => {
        const r = run(at('2026-11-02', '09:00'));
        assert.equal(r.period, 'P1');
        assert.ok(Object.values(r.lessonsByYear).flat().every(l => l.ClassCode.endsWith('D6')));
    });

    it('shows a clear message when the next school day is not in the calendar', () => {
        const r = run(at('2026-10-30', '15:10'), { calendar: buildCalendar({ from: '2026-10-25', to: '2026-11-01' }) });
        assert.equal(r.period, null);
        assert.match(r.message, /02\/11\/2026/);
    });

    it('shows a message (no throw, bounded) when there are no lessons at all', () => {
        const r = run(at('2026-10-27', '10:00'), { lessons: [] });
        assert.equal(r.period, null);
        assert.ok(r.message);
    });

    it('shows a message (no throw) when there are no bell times', () => {
        const r = run(at('2026-10-27', '10:00'), { bellTimes: [] });
        assert.equal(r.period, null);
        assert.ok(r.message);
    });
});

describe('loadWithFallback (JSON -> XML -> stale JSON)', () => {
    const now = new Date('2026-10-30T12:00:00Z');
    const fresh = { metadata: { generated_at: '2026-10-29T12:00:00Z' }, data: ['json'] };
    const stale = { metadata: { generated_at: '2024-01-01T00:00:00Z' }, data: ['old-json'] };
    const fail = async () => { throw new Error('boom'); };
    const opts = o => ({ maxAgeDays: 7, now, useJson: true, fallbackToXml: true, ...o });

    it('uses fresh JSON', async () => {
        const r = await core.loadWithFallback(opts({ loadJson: async () => fresh, loadXml: async () => ['xml'] }));
        assert.deepEqual(r.data, ['json']);
        assert.equal(r.source, 'json');
        assert.equal(r.jsonStatus, 'fresh');
    });

    it('uses XML when JSON is stale and reports when the JSON was generated', async () => {
        const r = await core.loadWithFallback(opts({ loadJson: async () => stale, loadXml: async () => ['xml'] }));
        assert.deepEqual(r.data, ['xml']);
        assert.equal(r.source, 'xml');
        assert.equal(r.jsonStatus, 'stale');
        assert.equal(r.generatedAt, '2024-01-01T00:00:00Z');
    });

    it('uses stale JSON when XML also fails', async () => {
        const r = await core.loadWithFallback(opts({ loadJson: async () => stale, loadXml: fail }));
        assert.deepEqual(r.data, ['old-json']);
        assert.equal(r.source, 'json-stale');
        assert.equal(r.jsonStatus, 'stale');
        assert.match(r.xmlError, /boom/);
    });

    it('uses XML when JSON fails or is empty, and reports the JSON error', async () => {
        const failed = await core.loadWithFallback(opts({ loadJson: fail, loadXml: async () => ['xml'] }));
        assert.equal(failed.source, 'xml');
        assert.equal(failed.jsonStatus, 'failed');
        assert.match(failed.jsonError, /boom/);
        const empty = { metadata: fresh.metadata, data: [] };
        assert.equal((await core.loadWithFallback(opts({ loadJson: async () => empty, loadXml: async () => ['xml'] }))).source, 'xml');
    });

    it('rejects with a combined error when every source fails', async () => {
        await assert.rejects(core.loadWithFallback(opts({ loadJson: fail, loadXml: fail })), /JSON.*boom.*XML.*boom/s);
    });

    it('skips JSON when use_json is false', async () => {
        let called = false;
        const r = await core.loadWithFallback(opts({ useJson: false, loadJson: async () => { called = true; return fresh; }, loadXml: async () => ['xml'] }));
        assert.equal(called, false);
        assert.equal(r.source, 'xml');
        assert.equal(r.jsonStatus, 'disabled');
    });

    it('keeps stale JSON when XML fallback is disabled', async () => {
        const r = await core.loadWithFallback(opts({ fallbackToXml: false, loadJson: async () => stale, loadXml: async () => ['xml'] }));
        assert.equal(r.source, 'json-stale');
    });
});

describe('getDataNotices (red on-screen warnings)', () => {
    const now = new Date('2026-10-30T12:00:00Z');
    const fresh = { source: 'json', jsonStatus: 'fresh', generatedAt: '2026-10-29T12:00:00Z' };
    const allFresh = { bell_times: fresh, calendar: fresh, liss_info: fresh };

    it('shows nothing when every source is fresh JSON', () => {
        assert.deepEqual(core.getDataNotices(allFresh, now), []);
    });

    it('shows nothing when JSON is deliberately disabled and XML is used', () => {
        const xmlOnly = { source: 'xml', jsonStatus: 'disabled', generatedAt: null };
        assert.deepEqual(core.getDataNotices({ ...allFresh, bell_times: xmlOnly }, now), []);
    });

    it('stale bell times (XML backup in use) say so, with the last update date, age and the workflow to run', () => {
        const notices = core.getDataNotices({ ...allFresh, bell_times: { source: 'xml', jsonStatus: 'stale', generatedAt: '2024-01-01T00:00:00Z' } }, now);
        assert.equal(notices.length, 1);
        const text = notices[0];
        assert.match(text, /Bell times/);
        assert.match(text, /stale/i);
        assert.match(text, /01\/01\/2024/);
        assert.match(text, /1033 days ago/);
        assert.match(text, /XML backup/);
        assert.match(text, /Weekly Data Update/);
    });

    it('stale JSON with no XML backup says the shown data may be out of date', () => {
        const [text] = core.getDataNotices({ ...allFresh, calendar: { source: 'json-stale', jsonStatus: 'stale', generatedAt: '2026-10-01T00:00:00Z' } }, now);
        assert.match(text, /Calendar/);
        assert.match(text, /may be out of date/i);
        assert.match(text, /XML backup.*unavailable/i);
    });

    it('missing JSON says it is unavailable and names the LISS workflow for timetable data', () => {
        const [text] = core.getDataNotices({ ...allFresh, liss_info: { source: 'xml', jsonStatus: 'failed', jsonError: 'liss_info.json: HTTP 404' } }, now);
        assert.match(text, /Timetable/);
        assert.match(text, /unavailable/i);
        assert.match(text, /LISS Timetable Updates/);
    });

    it('a failed refresh with earlier data says it is showing previously loaded data', () => {
        const [text] = core.getDataNotices({ ...allFresh, bell_times: { failed: true, hasPreviousData: true, error: 'network down' } }, now);
        assert.match(text, /could not be refreshed/i);
        assert.match(text, /previously loaded/i);
    });

    it('a failed first load says it could not be loaded', () => {
        const [text] = core.getDataNotices({ ...allFresh, bell_times: { failed: true, hasPreviousData: false, error: 'boom' } }, now);
        assert.match(text, /could not be loaded/i);
    });

    it('lists notices in a fixed order and tolerates missing or odd input', () => {
        const stale = { source: 'xml', jsonStatus: 'stale', generatedAt: 'garbage' };
        const notices = core.getDataNotices({ liss_info: stale, bell_times: stale }, now);
        assert.equal(notices.length, 2);
        assert.match(notices[0], /Bell times/);
        assert.match(notices[1], /Timetable/);
        assert.match(notices[0], /unknown/i);
        assert.deepEqual(core.getDataNotices(null, now), []);
        assert.deepEqual(core.getDataNotices({ bell_times: null }, now), []);
    });
});
