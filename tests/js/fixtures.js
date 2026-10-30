// Test fixtures modelled on the real Tempe HS data (10-day A/B cycle, Tuesday has early lunch).
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const CONFIG = JSON.parse(fs.readFileSync(path.join(ROOT, 'config.json'), 'utf8'));

const STANDARD_DAY = [
    ['P0', '07:50', '08:45', 'O'],
    ['P1', '08:45', '09:40', 'T'],
    ['P2', '09:40', '10:35', 'T'],
    ['Recess', '10:35', '11:00', 'R'],
    ['P3', '11:00', '11:55', 'T'],
    ['P4', '11:55', '12:50', 'T'],
    ['Lunch', '12:50', '13:20', 'R'],
    ['P5', '13:20', '14:15', 'T'],
    ['P6', '14:15', '15:05', 'T'],
    ['P7', '15:05', '16:00', 'O']
];

const TUESDAY = [
    ['P0', '07:50', '08:45', 'O'],
    ['P1', '08:45', '09:40', 'T'],
    ['P2', '09:40', '10:35', 'T'],
    ['Recess', '10:35', '11:00', 'R'],
    ['P3', '11:00', '11:55', 'T'],
    ['Lunch', '11:55', '12:25', 'R'],
    ['P4', '12:25', '13:20', 'T'],
    ['P5', '13:20', '14:15', 'T'],
    ['P6', '14:15', '15:05', 'T'],
    ['P7', '15:05', '16:00', 'O']
];

const DAY_NAMES = { 1: 'MonA', 2: 'TueA', 3: 'WedA', 4: 'ThuA', 5: 'FriA', 6: 'MonB', 7: 'TueB', 8: 'WedB', 9: 'ThuB', 10: 'FriB' };

const toMinutes = s => {
    const [h, m] = s.split(':').map(Number);
    return h * 60 + m;
};

function buildBellTimes() {
    const bells = [];
    for (let dn = 1; dn <= 10; dn++) {
        const schedule = dn === 2 || dn === 7 ? TUESDAY : STANDARD_DAY;
        for (const [period, start, end, type] of schedule) {
            bells.push({ period, start: toMinutes(start), end: toMinutes(end), dayName: DAY_NAMES[dn], dayNumber: dn, type, source: 'test' });
        }
    }
    return bells;
}

// Local-time date helpers so tests behave the same in any timezone.
function day(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
}

function at(iso, hhmm) {
    const date = day(iso);
    const [h, m] = hhmm.split(':').map(Number);
    date.setHours(h, m, 0, 0);
    return date;
}

function key(date) {
    const pad = n => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// Week of Monday 2026-10-26 is week A.
function buildCalendar({ from = '2026-10-24', to = '2026-11-15', holidays = [] } = {}) {
    const weekAStart = day('2026-10-26');
    const calendar = [];
    for (let d = day(from); d <= day(to); d.setDate(d.getDate() + 1)) {
        const dow = d.getDay();
        const iso = key(d);
        const weekIndex = Math.floor(Math.round((d - weekAStart) / 86400000) / 7);
        const isWeekend = dow === 0 || dow === 6;
        const isHoliday = holidays.includes(iso);
        const dayNumber = isWeekend || isHoliday ? 0 : (((weekIndex % 2) + 2) % 2) * 5 + dow;
        calendar.push({
            date: new Date(d),
            dayName: isWeekend ? 'weekend' : isHoliday ? 'holiday' : DAY_NAMES[dayNumber],
            dayNumber,
            isSchoolDay: !isWeekend && !isHoliday,
            dayType: isWeekend ? 'weekend' : 'school',
            source: 'test'
        });
    }
    return calendar;
}

// Every teaching period has one class per year; P0 only has seniors; P7 has nothing.
function buildLessons() {
    const lessons = [];
    for (let dn = 1; dn <= 10; dn++) {
        for (const period of ['P0', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6']) {
            const years = period === 'P0' ? [11, 12] : [7, 8, 9, 10, 11, 12];
            for (const year of years) {
                lessons.push({ DayNumber: dn, Period: period, ClassCode: `${year}${period}D${dn}`, TeacherCode: 'SMITH', RoomCode: `R${dn}` });
            }
        }
    }
    return lessons;
}

module.exports = { CONFIG, DAY_NAMES, buildBellTimes, buildCalendar, buildLessons, day, at, key };
