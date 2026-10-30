// Runs the real index.html script in a VM with a stubbed DOM and fetch, against the repo's data files.
const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { parseDocument, DomUtils } = require('htmlparser2');

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
    return {
        innerHTML: '',
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
        errors
    };
}

describe('index.html smoke tests (real data files)', () => {
    it('Monday 26/10/2026 12:55 shows Period 5 for Monday, not a Tuesday period', async () => {
        const r = await runKiosk({ now: '2026-10-26T12:55:00' });
        assert.match(r.header, /Period 5 - Monday 26\/10\/2026/);
        assert.match(r.timetable, /class="tile"/);
    });

    it('Tuesday 27/10/2026 12:00 (early lunch) shows Period 4', async () => {
        const r = await runKiosk({ now: '2026-10-27T12:00:00' });
        assert.match(r.header, /Period 4 - Tuesday 27\/10\/2026/);
    });

    it('Friday 15:10 with a calendar ending Sunday shows a clear message instead of a random timetable', async () => {
        const r = await runKiosk({ now: '2026-10-30T15:10:00' });
        assert.match(r.header, /No timetable data for Monday 02\/11\/2026/);
        assert.equal(r.timetable, '');
    });

    it('still renders with built-in defaults when config.json is missing', async () => {
        const r = await runKiosk({ now: '2026-10-26T12:55:00', files: { 'config.json': null } });
        assert.match(r.header, /Period 5/);
    });

    it('still renders when config.json is invalid JSON', async () => {
        const r = await runKiosk({ now: '2026-10-26T12:55:00', files: { 'config.json': '{ not json' } });
        assert.match(r.header, /Period 5/);
    });

    it('shows an error (no crash) when every data file is missing', async () => {
        const missing = { 'bell_times.json': null, 'bell_times.xml': null, 'liss_info.json': null, 'liss_info.xml': null, 'calendar.json': null, 'calendar.xml': null };
        const r = await runKiosk({ now: '2026-10-26T12:55:00', files: missing });
        assert.match(r.header, /Error loading timetable data/);
    });

    it('shows an error (no crash) when a data file is corrupt', async () => {
        const r = await runKiosk({ now: '2026-10-26T12:55:00', files: { 'calendar.json': '{"calendar": [', 'calendar.xml': null } });
        assert.match(r.header, /Error loading timetable data/);
    });

    it('escapes HTML in data values', async () => {
        const liss = JSON.parse(fs.readFileSync(path.join(ROOT, 'liss_info.json'), 'utf8'));
        liss.timetable_data.push({ DayNumber: 1, Period: 'P5', ClassCode: '7<img', TeacherCode: '<script>x</script>', RoomCode: '"><b>' });
        const r = await runKiosk({ now: '2026-10-26T12:55:00', files: { 'liss_info.json': JSON.stringify(liss) } });
        assert.ok(!r.timetable.includes('<script>'));
        assert.ok(!r.timetable.includes('<img'));
        assert.match(r.timetable, /&lt;script&gt;/);
    });

    it('shows a red notice when bell times are stale (committed bell_times.json is from 2024)', async () => {
        const r = await runKiosk({ now: '2026-10-26T12:55:00' });
        assert.match(r.notices, /Bell times/);
        assert.match(r.notices, /stale/i);
        assert.match(r.notices, /Weekly Data Update/);
        assert.match(r.header, /Period 5/);
    });

    it('shows no notice when all data is fresh', async () => {
        const bells = JSON.parse(fs.readFileSync(path.join(ROOT, 'bell_times.json'), 'utf8'));
        bells.metadata.generated_at = '2026-10-25T00:00:00Z';
        const r = await runKiosk({ now: '2026-10-26T12:55:00', files: { 'bell_times.json': JSON.stringify(bells) } });
        assert.equal(r.notices, '');
    });

    it('shows a notice when a data file is missing', async () => {
        const r = await runKiosk({ now: '2026-10-26T12:55:00', files: { 'liss_info.json': null, 'liss_info.xml': null } });
        assert.match(r.notices, /Timetable/);
        assert.match(r.notices, /could not be loaded/i);
    });
});
