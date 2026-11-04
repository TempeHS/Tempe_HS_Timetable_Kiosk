// Runs the real index.html script in a VM with a stubbed DOM and fetch, against the repo's data files.
const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { parseDocument, DomUtils } = require('htmlparser2');
const { buildBellTimes, buildCalendar, buildLessons, key } = require('./fixtures');

const ROOT = path.join(__dirname, '..', '..');
const HTML = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const INLINE_SCRIPT = extractInlineScript(HTML);
const CORE_SCRIPT = fs.readFileSync(path.join(ROOT, 'timetable-core.js'), 'utf8');

function extractInlineScript(html) {
    const scripts = DomUtils.getElementsByTagName('script', parseDocument(html));
    const script = scripts.find(element => !Object.hasOwn(element.attribs, 'src'));
    assert.ok(script, 'Expected an inline script in the HTML');
    return DomUtils.textContent(script);
}

it('extracts inline scripts using HTML parsing', () => {
    const source = '\nconsole.log("test");\n';
    for (const [opening, closing] of [
        ['script', 'script'],
        ['SCRIPT', 'SCRIPT'],
        ['ScRiPt', 'sCrIpT'],
        ['script type="text/javascript"', 'script'],
        ['script data-label="a > b"', 'script'],
        ['script', 'script \t']
    ]) {
        const html = `<${opening}>${source}</${closing}>`;
        assert.equal(extractInlineScript(html), source);
    }
    assert.equal(extractInlineScript(
        `<!-- <script>ignored();</script> --><script SRC="core.js"></script><script>${source}</script>`
    ), source);
    assert.throws(() => extractInlineScript('<script src="core.js"></script>'), /Expected an inline script/);
});

function fakeDateClass(fixedIso) {
    const fixed = new Date(fixedIso).getTime();
    return class FakeDate extends Date {
        constructor(...args) {
            super(...(args.length ? args : [fixed]));
        }
        static now() {
            return fixed;
        }
    };
}

function makeElement() {
    const classes = new Set();
    let html = '';
    return {
        innerHTMLWrites: 0,
        get innerHTML() { return html; },
        set innerHTML(value) {
            html = value;
            this.innerHTMLWrites++;
        },
        textContent: '',
        className: '',
        style: {},
        classList: { add: c => classes.add(c), remove: c => classes.delete(c) }
    };
}

// files: map of filename -> string content, or null to return 404. Unlisted files are read from disk.
async function runKiosk({ now, files = {} }) {
    const elements = {};
    const errors = [];
    const context = {
        console: { log() {}, warn() {}, error: (...a) => errors.push(a) },
        document: { getElementById: id => (elements[id] = elements[id] || makeElement()) },
        location: { href: 'http://kiosk/', replace() {} },
        setInterval: () => 0,
        setTimeout: () => 0,
        clearTimeout() {},
        AbortController,
        addEventListener() {},
        Date: fakeDateClass(now),
        fetch: async url => {
            const name = String(url).split('?')[0];
            let body = Object.prototype.hasOwnProperty.call(files, name) ? files[name] : undefined;
            if (body === undefined) {
                const p = path.join(ROOT, name);
                body = fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
            }
            if (body === null) return { ok: false, status: 404, json: async () => ({}), text: async () => '' };
            return { ok: true, status: 200, json: async () => JSON.parse(body), text: async () => body };
        }
        // No DOMParser: XML sources fail, exercising the fallback paths.
    };
    context.window = context;
    vm.createContext(context);
    vm.runInContext(CORE_SCRIPT, context);
    vm.runInContext(INLINE_SCRIPT, context);

    for (let i = 0; i < 50 && (!elements.header || /Loading/.test(elements.header.innerHTML || 'Loading')); i++) {
        await new Promise(r => setImmediate(r));
    }
    return {
        header: elements.header ? elements.header.innerHTML : '',
        timetable: elements.timetable ? elements.timetable.innerHTML : '',
        notices: elements['data-notices'] ? elements['data-notices'].innerHTML : '',
        errors,
        context,
        elements
    };
}

function buildKioskFiles() {
    const metadata = { generated_at: '2026-10-25T00:00:00Z' };
    const time = minutes => `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
    const bellTimes = buildBellTimes().map(entry => ({
        Period: entry.period,
        StartTime: time(entry.start),
        EndTime: time(entry.end),
        DayName: entry.dayName,
        DayNumber: entry.dayNumber,
        Type: entry.type
    }));
    const calendar = buildCalendar({ to: '2026-11-01' }).map(entry => ({
        date: key(entry.date),
        day_name: entry.dayName,
        day_number: entry.dayNumber,
        is_school_day: entry.isSchoolDay,
        day_type: entry.dayType
    }));
    return {
        'bell_times.json': JSON.stringify({ metadata, bell_times: bellTimes }),
        'calendar.json': JSON.stringify({ metadata, calendar }),
        'liss_info.json': JSON.stringify({ metadata, timetable_data: buildLessons() })
    };
}

function runFixtureKiosk({ now = '2026-10-26T12:55:00', files = {} } = {}) {
    return runKiosk({
        now,
        files: { ...buildKioskFiles(), ...files }
    });
}

describe('index.html smoke tests', () => {
    it('loads the supplied JSON data through the real page parsers', async () => {
        const calendar = JSON.parse(fs.readFileSync(path.join(ROOT, 'calendar.json'), 'utf8'));
        const bells = JSON.parse(fs.readFileSync(path.join(ROOT, 'bell_times.json'), 'utf8'));
        const liss = JSON.parse(fs.readFileSync(path.join(ROOT, 'liss_info.json'), 'utf8'));
        const schoolDay = calendar.calendar.find(entry => entry.is_school_day);
        assert.ok(schoolDay, 'Supplied calendar should contain a school day');
        const { context, header } = await runKiosk({ now: `${schoolDay.date}T10:00:00` });
        assert.equal(vm.runInContext('bellTimes.length', context), bells.bell_times.length);
        assert.equal(vm.runInContext('lessons.length', context), liss.timetable_data.length);
        assert.equal(vm.runInContext('calendarData.length', context), calendar.calendar.length);
        assert.equal(vm.runInContext('Object.values(dataStatus).every(status => !status.failed)', context), true);
        assert.ok(header);
        assert.doesNotMatch(header, /Error loading timetable data|Loading data/);
    });

    it('does not replace unchanged HTML, but renders changed lessons and dates', async () => {
        const { context, elements } = await runFixtureKiosk();
        const ids = ['header', 'timetable', 'data-notices'];
        const writes = ids.map(id => elements[id].innerHTMLWrites);
        await context.smoothDataRefresh();
        assert.deepEqual(ids.map(id => elements[id].innerHTMLWrites), writes);

        const originalFetch = context.fetch;
        context.fetch = async (...args) => {
            const response = await originalFetch(...args);
            if (String(args[0]).startsWith('liss_info.json')) {
                const data = await response.json();
                data.timetable_data.push({ DayNumber: 1, Period: 'P5', ClassCode: '7NEW', TeacherCode: 'NEWTEACH', RoomCode: 'NEWROOM' });
                return { ...response, json: async () => data };
            }
            return response;
        };
        await context.smoothDataRefresh();
        assert.match(elements.timetable.innerHTML, /NEWROOM/);
        assert.equal(elements.timetable.innerHTMLWrites, writes[1] + 1);
        assert.equal(elements.header.innerHTMLWrites, writes[0]);

        context.Date = fakeDateClass('2026-10-30T15:10:00');
        await context.smoothDataRefresh();
        assert.match(elements.header.innerHTML, /No timetable data for Monday/);
        assert.equal(elements.timetable.innerHTML, '');
        context.Date = fakeDateClass('2026-10-26T12:55:00');
        await context.smoothDataRefresh();
        assert.match(elements.header.innerHTML, /Period 5/);
        assert.match(elements.timetable.innerHTML, /NEWROOM/);
    });

    for (const stage of ['request', 'body']) {
        it(`aborts a stalled ${stage} after 15 seconds and clears its timeout`, async () => {
            const { context } = await runFixtureKiosk();
            const timers = new Map();
            context.setTimeout = (callback, delay) => {
                const timer = { callback, delay };
                timers.set(timer, timer);
                return timer;
            };
            context.clearTimeout = timer => timers.delete(timer);
            let signal;
            context.fetch = async (_url, options) => {
                signal = options.signal;
                const pending = new Promise((_resolve, reject) => {
                    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
                });
                return stage === 'request' ? pending : { ok: true, json: () => pending };
            };
            const request = context.fetchData('slow.json');
            await new Promise(resolve => setImmediate(resolve));
            assert.equal(timers.size, 1);
            const [timer] = timers.values();
            assert.equal(timer.delay, 15000);
            timer.callback();
            await assert.rejects(request, { name: 'AbortError' });
            assert.equal(signal.aborted, true);
            assert.equal(timers.size, 0);
        });
    }

    it('clears request timers on success and errors, including text responses', async () => {
        const { context } = await runFixtureKiosk();
        const timers = new Set();
        context.setTimeout = callback => { timers.add(callback); return callback; };
        context.clearTimeout = timer => timers.delete(timer);
        await context.fetchData('config.json');
        assert.equal(timers.size, 0);
        assert.equal(await context.fetchData('bell_times.xml', 'text'), fs.readFileSync(path.join(ROOT, 'bell_times.xml'), 'utf8'));
        assert.equal(timers.size, 0);
        await assert.rejects(context.fetchData('missing.json'), /HTTP 404/);
        assert.equal(timers.size, 0);
        context.fetch = async () => ({ ok: true, json: async () => { throw new Error('Invalid JSON'); } });
        await assert.rejects(context.fetchData('invalid.json'), /Invalid JSON/);
        assert.equal(timers.size, 0);
    });

    it('skips overlapping refreshes and allows the next refresh after completion', async () => {
        const { context } = await runFixtureKiosk();
        const originalFetch = context.fetch;
        let release;
        const pending = new Promise(resolve => { release = resolve; });
        let requests = 0;
        context.fetch = async (...args) => {
            requests++;
            await pending;
            return originalFetch(...args);
        };
        const firstRefresh = context.smoothDataRefresh();
        try {
            assert.equal(requests, 3);
            await context.smoothDataRefresh();
            assert.equal(requests, 3);
        } finally {
            release();
            await firstRefresh;
        }
        context.fetch = originalFetch;
        await context.smoothDataRefresh();
        assert.equal(vm.runInContext('refreshInProgress', context), false);
    });

    it('keeps the last good screen after timeouts and recovers on the next refresh', async () => {
        const { context, elements } = await runFixtureKiosk();
        assert.match(elements.header.innerHTML, /Period 5/);
        assert.match(elements.timetable.innerHTML, /class="tile"/);
        const header = elements.header.innerHTML;
        const timetable = elements.timetable.innerHTML;
        const originalFetch = context.fetch;
        const timers = new Set();
        context.setTimeout = callback => { timers.add(callback); return callback; };
        context.clearTimeout = timer => timers.delete(timer);
        context.fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
            signal.addEventListener('abort', () => reject(signal.reason), { once: true });
        });
        const refresh = context.smoothDataRefresh();
        for (let phase = 0; phase < 2; phase++) {
            await new Promise(resolve => setImmediate(resolve));
            assert.equal(timers.size, 3);
            for (const timeout of timers) timeout();
        }
        await refresh;
        assert.equal(timers.size, 0);
        assert.equal(elements.header.innerHTML, header);
        assert.equal(elements.timetable.innerHTML, timetable);
        assert.equal(elements['loading-indicator'].style.opacity, '0');
        assert.equal(vm.runInContext('refreshInProgress', context), false);

        context.fetch = originalFetch;
        await context.smoothDataRefresh();
        assert.equal(timers.size, 0);
        assert.equal(elements.timetable.innerHTML, timetable);
        assert.equal(vm.runInContext('Object.values(dataStatus).some(status => status.failed)', context), false);
    });

    it('Monday 26/10/2026 12:55 shows Period 5 for Monday, not a Tuesday period', async () => {
        const r = await runFixtureKiosk();
        assert.match(r.header, /Period 5 - Monday 26\/10\/2026/);
        assert.match(r.timetable, /class="tile"/);
    });

    it('Tuesday 27/10/2026 12:00 (early lunch) shows Period 4', async () => {
        const r = await runFixtureKiosk({ now: '2026-10-27T12:00:00' });
        assert.match(r.header, /Period 4 - Tuesday 27\/10\/2026/);
    });

    it('Friday 15:10 with a calendar ending Sunday shows a clear message instead of a random timetable', async () => {
        const r = await runFixtureKiosk({ now: '2026-10-30T15:10:00' });
        assert.match(r.header, /No timetable data for Monday 02\/11\/2026/);
        assert.equal(r.timetable, '');
    });

    it('still renders with built-in defaults when config.json is missing', async () => {
        const r = await runFixtureKiosk({ files: { 'config.json': null } });
        assert.match(r.header, /Period 5/);
    });

    it('still renders when config.json is invalid JSON', async () => {
        const r = await runFixtureKiosk({ files: { 'config.json': '{ not json' } });
        assert.match(r.header, /Period 5/);
    });

    it('shows an error (no crash) when every data file is missing', async () => {
        const missing = { 'bell_times.json': null, 'bell_times.xml': null, 'liss_info.json': null, 'liss_info.xml': null, 'calendar.json': null, 'calendar.xml': null };
        const r = await runFixtureKiosk({ files: missing });
        assert.match(r.header, /Error loading timetable data/);
    });

    it('shows an error (no crash) when a data file is corrupt', async () => {
        const r = await runFixtureKiosk({ files: { 'calendar.json': '{"calendar": [', 'calendar.xml': null } });
        assert.match(r.header, /Error loading timetable data/);
    });

    it('escapes HTML in data values', async () => {
        const liss = JSON.parse(buildKioskFiles()['liss_info.json']);
        liss.timetable_data.push({ DayNumber: 1, Period: 'P5', ClassCode: '7<img', TeacherCode: '<script>x</script>', RoomCode: '"><b>' });
        const r = await runFixtureKiosk({ files: { 'liss_info.json': JSON.stringify(liss) } });
        assert.ok(!r.timetable.includes('<script>'));
        assert.ok(!r.timetable.includes('<img'));
        assert.match(r.timetable, /7&lt;img/);
        assert.match(r.timetable, /&lt;script&gt;/);
        assert.match(r.timetable, /&quot;&gt;&lt;b&gt;/);
    });

    it('shows a notice when bell times are stale and XML is unavailable', async () => {
        const bells = JSON.parse(buildKioskFiles()['bell_times.json']);
        bells.metadata.generated_at = '2024-01-01T00:00:00Z';
        const r = await runFixtureKiosk({ files: { 'bell_times.json': JSON.stringify(bells), 'bell_times.xml': null } });
        assert.match(r.notices, /Bell times/);
        assert.match(r.notices, /stale/i);
        assert.match(r.notices, /Weekly Data Update/);
        assert.match(r.header, /Period 5/);
    });

    it('shows no notice when all data is fresh', async () => {
        const r = await runFixtureKiosk();
        assert.match(r.header, /Period 5/);
        assert.equal(r.notices, '');
    });

    it('shows a notice when a data file is missing', async () => {
        const r = await runFixtureKiosk({ files: { 'liss_info.json': null, 'liss_info.xml': null } });
        assert.match(r.notices, /Timetable/);
        assert.match(r.notices, /could not be loaded/i);
    });
});
