const issueOptions = {
    "1": "การถ่ายทอดความรู้ (TRAINING)",
    "2": "การเยี่ยมเยียน (VISITING)",
    "3": "การสนับสนุน (SUPPORTING)",
    "4": "การนิเทศงาน (SUPERVISION)",
    "5": "การจัดการข้อมูล (DATA MANAGEMENT)"
};

const activityOptions = {
    "1": [
        { value: "14", label: "Weekly Meeting : WM" },
        { value: "13", label: "District Meeting : DM" },
        { value: "12", label: "Monthly Meeting : MM" },
        { value: "11", label: "Provincial Meeting : PM" },
        { value: "1", label: "National Workshop : NW" },
        { value: "6", label: "Regional Workshop : RW" },
        { value: "7", label: "Provincial Workshop : PW" },
        { value: "8", label: "District Workshop : DW" },
        { value: "9", label: "ประชุมผู้บริหารระดับกรม" },
        { value: "10", label: "ประชุมหัวหน้าส่วนราชการระดับเขต" },
        { value: "999", label: "อื่นๆ" }
    ],
    "2": [
        { value: "2", label: "ศพก." },
        { value: "15", label: "เกษตรแปลงใหญ่" },
        { value: "16", label: "Smart Farmer / Young Smart Farmer" },
        { value: "17", label: "Zoning by Agri-Map" },
        { value: "18", label: "โครงการอันเนื่องมาจากพระราชดำริ" },
        { value: "19", label: "วิสาหกิจชุมชน" },
        { value: "20", label: "กลุ่มเกษตรกร / กลุ่มแม่บ้านเกษตรกร" },
        { value: "21", label: "เกษตรทฤษฎีใหม่" },
        { value: "22", label: "เกษตรอินทรีย์" },
        { value: "23", label: "ตลาดสินค้าเกษตร" },
        { value: "24", label: "พัฒนาคุณภาพสินค้าเกษตร" },
        { value: "25", label: "บริหารจัดการทรัพยากรน้ำ" },
        { value: "26", label: "พัฒนาสถาบันเกษตรกรรูปแบบประชารัฐ" },
        { value: "27", label: "ธนาคารสินค้าเกษตร" },
        { value: "28", label: "จัดระเบียบการประมงให้เป็นมาตรฐาน" },
        { value: "29", label: "ส่งเสริมการใช้เครื่องจักรกลการเกษตร" },
        { value: "30", label: "การช่วยเหลือด้านหนี้สิน" },
        { value: "31", label: "แผนผลิตข้าวข้าวครบวงจร" },
        { value: "999", label: "อื่นๆ" }
    ],
    "3": [
        { value: "3", label: "ด้านโครงสร้างและอุปกรณ์" },
        { value: "33", label: "เพิ่มสมรรถนะและสร้างขวัญกำลังใจ" },
        { value: "34", label: "ด้านวิชาการ" },
        { value: "999", label: "อื่นๆ" }
    ],
    "4": [
        { value: "999", label: "อื่นๆ" }
    ],
    "5": [
        { value: "4", label: "ด้านข้อมูลสารสนเทศ" },
        { value: "36", label: "ด้านแผนพัฒนาการเกษตร" },
        { value: "999", label: "อื่นๆ" }
    ]
};

let allRecords = [];
let historicalActivityPool = [];
let historicalActivityPoolLoaded = false;
let selectedFile = null;
let tempFilename = '';
// Tracks the month selected by the web-based plan generator.
// This must take precedence over the Excel sheet selector when submitting.
let currentPlanMonth = '';

const thaiPlanMonthAbbr = [
    'มค', 'กพ', 'มีค', 'เมย', 'พค', 'มิย',
    'กค', 'สค', 'กย', 'ตค', 'พย', 'ธค'
];

function planMonthToSheetName(planMonth) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(planMonth || ''));
    if (!match) return '';
    const month = parseInt(match[2], 10);
    if (month < 1 || month > 12) return '';
    const yearBeShort = String(parseInt(match[1], 10) + 543).slice(-2);
    return `${thaiPlanMonthAbbr[month - 1]}${yearBeShort}`;
}

function inferPlanMonthFromRecords() {
    const rec = allRecords.find(item => /^\d{1,2}\/\d{1,2}\/\d{4}$/.test(String(item.date || '')));
    if (!rec) return '';
    const [day, month, yearBeText] = String(rec.date).split('/').map(Number);
    const year = yearBeText >= 2400 ? yearBeText - 543 : yearBeText;
    if (!day || month < 1 || month > 12 || !year) return '';
    return `${year}-${String(month).padStart(2, '0')}`;
}
let locationPresets = [{ value: "_custom", label: "กำหนดเอง..." }];
/** Cache villages by tambon_code for per-row linking */
const rowVillageCache = {};

const geoState = {
    provinces: [],
    amphoes: [],
    tambons: [],
    villages: [],
    provinceCode: '',
    amphoeCode: '',
    tambonCode: '',
    provinceName: '',
    amphoeName: '',
    tambonName: '',
    villageName: '',
    selectedVillages: [],
    selectedTambons: [],
    moo: '',
    moos: [],
    officeName: '',
    officeStaffCount: 7,
    role: 'officer',
    presets: [],
    setupConfirmed: false,
    officerName: ''
};

function getOfficeStaffCount() {
    const el = document.getElementById('office-staff-count');
    if (el && el.value) {
        const val = parseInt(el.value, 10);
        if (!isNaN(val) && val > 0) return val;
    }
    return geoState.officeStaffCount || 7;
}

function onOfficeStaffCountChange() {
    const count = getOfficeStaffCount();
    geoState.officeStaffCount = count;
    localStorage.setItem('tv_office_staff_count', String(count));
    
    let updated = 0;
    if (allRecords && allRecords.length) {
        allRecords.forEach((rec, idx) => {
            if (isOfficeWorkRecord(rec) || rec.officeOnly || rec.issue_val === '1') {
                rec.target_num = count;
                rec.target_raw = `${count} ราย`;
                const targetInput = document.getElementById(`target-${idx}`);
                if (targetInput) targetInput.value = count;
                updated++;
            }
        });
        if (updated > 0) {
            addLog('info', `อัปเดตจำนวนบุคคลเป้าหมายวันประชุมสำนักงานเป็น ${count} คน (${updated} แถว)`);
        }
    }
}

/** สุ่มจำนวนบุคคลเป้าหมายงานภาคสนาม (20, 30, 50, 60 คน) */
function getRandomFieldTargetCount() {
    const pool = [20, 30, 50, 60];
    const randIdx = Math.floor(Math.random() * pool.length);
    return pool[randIdx];
}

// T&V credentials are needed only for the current run. The username has
// historically been stored in localStorage, while the password is in
// sessionStorage; clear both locations and the visible fields after the run.
function clearTandVCredentials() {
    try {
        localStorage.removeItem('tv_username');
        sessionStorage.removeItem('tv_username');
        sessionStorage.removeItem('tv_password');
    } catch (storageError) {
        // Do not expose credential values if browser storage is unavailable.
        console.warn('ไม่สามารถล้างข้อมูลรับรอง T&V จาก browser storage ได้', storageError);
    }

    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    if (usernameInput) usernameInput.value = '';
    if (passwordInput) passwordInput.value = '';
}

// Return a one-shot cleanup callback for the end of one Playwright run.
// The guard prevents duplicate cleanup when both stream completion and an
// error handler observe the same run ending.
function createRunCredentialCleanup() {
    let credentialsCleared = false;
    return () => {
        if (credentialsCleared) return;
        credentialsCleared = true;
        clearTandVCredentials();
    };
}

document.addEventListener("DOMContentLoaded", () => {
    initMooMultiSelect();
    initVillageMultiSelect();
    initTambonMultiSelect();
    initGeoCascade();
    fetchSheets();
    document.getElementById('start-btn').addEventListener('click', startAutomation);
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.multi-select') && !e.target.closest('.row-moo-picker')) {
            closeAllMultiPanels();
        }
    });

    // Gemini API keys are memory-only; never persist them in Web Storage.
    const apiKeyInput = document.getElementById('gemini-api-key');
    if (apiKeyInput) apiKeyInput.value = '';
    try {
        localStorage.removeItem('gemini_api_key');
    } catch (_storageError) {
        // Ignore storage access failures; the key remains memory-only.
    }

    const savedApprover = localStorage.getItem('tv_approver') || '';
    if (savedApprover) document.getElementById('approver').value = savedApprover;
    document.getElementById('approver').addEventListener('input', (e) => {
        localStorage.setItem('tv_approver', e.target.value.trim());
    });

    // T&V credentials are memory-only and are never persisted in Web Storage.
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    if (usernameInput) usernameInput.value = '';
    if (passwordInput) passwordInput.value = '';

    const savedRole = localStorage.getItem('tv_role') || 'officer';
    document.getElementById('role-select').value = savedRole;
    geoState.role = savedRole;
    onRoleChange();

    const savedOffice = localStorage.getItem('tv_office_name') || '';
    const officeInput = document.getElementById('office-name');
    if (officeInput) {
        const val = (savedOffice && savedOffice !== 'สำนักงานเกษตรอำเภอสีดา') ? savedOffice : '';
        officeInput.value = val;
        geoState.officeName = val;
        officeInput.addEventListener('input', (e) => {
            geoState.officeName = e.target.value.trim();
            localStorage.setItem('tv_office_name', geoState.officeName);
            refreshLocationPresets();
        });
    }

    const randomOpt = document.getElementById('opt-random-moo-on-load');
    if (randomOpt) {
        const saved = localStorage.getItem('tv_random_moo_on_load');
        if (saved !== null) randomOpt.checked = saved === '1';
        randomOpt.addEventListener('change', () => {
            localStorage.setItem('tv_random_moo_on_load', randomOpt.checked ? '1' : '0');
        });
    }

    const officerInput = document.getElementById('officer-name');
    if (officerInput) {
        officerInput.value = localStorage.getItem('tv_officer_name') || '';
        geoState.officerName = officerInput.value;
        officerInput.addEventListener('input', () => {
            geoState.officerName = officerInput.value.trim();
            localStorage.setItem('tv_officer_name', geoState.officerName);
            geoState.setupConfirmed = false;
            updateSetupSummary();
        });
    }
    geoState.setupConfirmed = localStorage.getItem('tv_setup_confirmed') === '1';
    updateSetupSummary();
});

function normalizeMoos(list) {
    const seen = new Set();
    const out = [];
    (list || []).forEach(m => {
        const v = String(m || '').trim();
        if (!v || v === '_custom' || seen.has(v)) return;
        seen.add(v);
        out.push(v);
    });
    out.sort((a, b) => {
        const na = parseInt(a, 10);
        const nb = parseInt(b, 10);
        if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
        return String(a).localeCompare(String(b), 'th');
    });
    return out;
}

function normalizeVillages(list) {
    const seen = new Set();
    const out = [];
    (list || []).forEach(name => {
        const v = String(name || '').replace(/\s*\(ม\.\d+\)\s*$/, '').trim();
        if (!v || seen.has(v)) return;
        seen.add(v);
        out.push(v);
    });
    return out;
}

function bareTambonName(name) {
    return String(name || '').replace(/^ตำบล/, '').replace(/^แขวง/, '').trim();
}

function normalizeTambons(list) {
    const seen = new Set();
    const out = [];
    (list || []).forEach(name => {
        const v = bareTambonName(name);
        if (!v || seen.has(v)) return;
        seen.add(v);
        out.push(v);
    });
    out.sort((a, b) => a.localeCompare(b, 'th'));
    return out;
}

function isAllAmphoeResponsibility() {
    const all = getAmphoeTambonNames();
    const sel = [...getResponsibleTambonSet()];
    if (!all.length || !sel.length) return false;
    return all.every(t => sel.includes(t));
}

function updateSetupSummary() {
    const el = document.getElementById('setup-summary');
    const lockHint = document.getElementById('upload-lock-hint');
    const uploadBtn = document.getElementById('upload-btn');
    const name = (document.getElementById('officer-name')?.value || '').trim();
    const role = document.getElementById('role-select')?.value || geoState.role;
    const roleLabel = {
        officer: 'เจ้าหน้าที่',
        district_chief: 'เกษตรอำเภอ/หัวหน้า',
        admin_clerk: 'ธุรการ (ไปกับหัวหน้า)'
    }[role] || role;
    const tbs = [...getResponsibleTambonSet()];
    const amphoe = geoState.amphoeName || document.getElementById('amphoe-select')?.value || '';
    let text = '';
    if (!amphoe) {
        text = 'พื้นที่รับผิดชอบ: ยังไม่ได้เลือกอำเภอ';
    } else if (!tbs.length) {
        text = `พื้นที่รับผิดชอบ: อำเภอ${amphoe} · ยังไม่ได้เลือกตำบล`;
    } else if (isAllAmphoeResponsibility()) {
        text = `พื้นที่รับผิดชอบ: ${name ? name + ' · ' : ''}${roleLabel} · อำเภอ${amphoe} · ทุกตำบล (${tbs.length}) — ไม่สุ่มหมู่`;
    } else if (tbs.length === 1) {
        text = `พื้นที่รับผิดชอบ: ${name ? name + ' · ' : ''}${roleLabel} · ตำบล${tbs[0]} — สุ่มหมู่ในตำบลนี้`;
    } else {
        text = `พื้นที่รับผิดชอบ: ${name ? name + ' · ' : ''}${roleLabel} · ${tbs.length} ตำบล (${tbs.join(', ')}) — สุ่มหมู่ทุกตำบลที่รับผิดชอบ`;
    }
    const hasTambons = (geoState.amphoeCode || amphoe) && tbs.length > 0;
    if (geoState.setupConfirmed && tbs.length) {
        text = '✓ ' + text;
    }
    if (el) el.textContent = text;
    const ready = hasTambons;
    if (uploadBtn) uploadBtn.disabled = !ready;
    const createWebBtn = document.getElementById('create-plan-web-btn');
    if (createWebBtn) createWebBtn.disabled = !ready;
    const autoGenBtn = document.getElementById('btn-generate-auto-plan');
    if (autoGenBtn) autoGenBtn.disabled = !ready;
    if (lockHint) {
        lockHint.style.display = ready ? 'none' : 'block';
        lockHint.textContent = ready ? '' : 'กรุณาเลือกจังหวัด/อำเภอ/ตำบล ในพื้นที่รับผิดชอบด้านบนก่อน';
    }
}

function confirmResponsibilitySetup() {
    const tbs = [...getResponsibleTambonSet()];
    if (!geoState.amphoeCode && !document.getElementById('amphoe-select')?.value) {
        addLog('error', 'กรุณาเลือกอำเภอก่อน');
        return;
    }
    if (!tbs.length) {
        addLog('error', 'กรุณาเลือกตำบลในพื้นที่รับผิดชอบอย่างน้อย 1 ตำบล');
        return;
    }
    geoState.setupConfirmed = true;
    geoState.officerName = (document.getElementById('officer-name')?.value || '').trim();
    localStorage.setItem('tv_setup_confirmed', '1');
    localStorage.setItem('tv_officer_name', geoState.officerName);
    // sync primary tambon field for backend default
    const primary = tbs[0];
    const tambonInput = document.getElementById('tambon');
    if (tambonInput) tambonInput.value = primary;
    geoState.tambonName = primary;
    updateSetupSummary();
    addLog('success', `ยืนยันพื้นที่รับผิดชอบแล้ว: ${tbs.map(t => 'ตำบล' + t).join(', ')}`);
    document.getElementById('upload-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function isMultiTambonRole(role = geoState.role) {
    return role === 'district_chief' || role === 'admin_clerk';
}

function getSelectedTambonsForExpand() {
    // Source of truth = chip list from geo panel / «เลือกทุกตำบลในอำเภอ»
    return normalizeTambons(geoState.selectedTambons);
}

function formatTambonPart(tambon) {
    const t = (tambon || '').trim();
    if (!t) return '';
    return t.startsWith('ตำบล') ? t : `ตำบล${t}`;
}

function formatMooTambonSegment(moos, tambon) {
    const tpart = formatTambonPart(tambon);
    const mooNums = normalizeMoos(moos);
    if (!tpart && !mooNums.length) return '';
    if (!mooNums.length) return tpart;
    // Target T&V PD_PLACE style: หมู่ 1, 3, 5 ตำบลหนองตาดใหญ่
    return `หมู่ ${mooNums.join(', ')} ${tpart}`.trim();
}

/** ชื่อสถานที่งานสำนักงาน — ไม่ต้องใส่หมู่/ตำบลเพิ่ม */
function getOfficePlaceName() {
    const office = (document.getElementById('office-name')?.value || geoState.officeName || '').trim();
    if (!office) {
        return geoState.amphoeName ? `สำนักงานเกษตรอำเภอ${geoState.amphoeName}` : 'สำนักงานเกษตรอำเภอเมือง';
    }
    if (/สำนักงานเกษตรอำเภอ/.test(office)) return office;
    const short = office
        .replace(/^สนง\.?\s*กษอ\.?\s*/i, '')
        .replace(/^สนง\.?\s*เกษตรอำเภอ\s*/i, '')
        .replace(/^สำนักงาน\s*เกษตรอำเภอ\s*/i, '')
        .trim();
    return short ? `สำนักงานเกษตรอำเภอ${short}` : office;
}

/** Parse พ.ศ. date DD/MM/YYYY → Date (local) or null */
function parseBeDate(dateStr) {
    const m = String(dateStr || '').trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!m) return null;
    const day = parseInt(m[1], 10);
    const month = parseInt(m[2], 10) - 1;
    let year = parseInt(m[3], 10);
    if (year >= 2400) year -= 543;
    const dt = new Date(year, month, day);
    if (dt.getFullYear() !== year || dt.getMonth() !== month || dt.getDate() !== day) return null;
    return dt;
}

/**
 * สำนักงานเกษตรอำเภอสีดา = ประชุมสำนักงานเท่านั้น
 * - ทุกวันจันทร์ → WM (14) ประชุมประจำสัปดาห์
 * - จันทร์แรกของเดือน → MM (12) ประชุมประจำเดือน
 */
function classifyOfficeMeetingByDate(dateStr) {
    const dt = parseBeDate(dateStr);
    if (!dt || dt.getDay() !== 1) return null; // Monday
    const isFirstMonday = dt.getDate() <= 7;
    if (isFirstMonday) {
        return {
            issue_val: '1',
            activity_val: '13',
            kind: 'DM',
            label: 'ประชุมสำนักงานเกษตรอำเภอประจำเดือน (DM)'
        };
    }
    return {
        issue_val: '1',
        activity_val: '14',
        kind: 'WM',
        label: 'ประชุมสำนักงานเกษตรอำเภอประจำสัปดาห์ (WM)'
    };
}

/** Apply office-meeting rules to one record. Returns true if applied. */
function applyOfficeMeetingRulesToRecord(rec) {
    if (!rec) return false;
    const meeting = classifyOfficeMeetingByDate(rec.date);
    if (!meeting) return false;
    const officePlace = getOfficePlaceName();
    rec.officeOnly = true;
    rec.issue_val = meeting.issue_val;
    rec.activity_val = meeting.activity_val;
    rec.placeParts = [];
    rec.moos = [];
    rec.location = officePlace;
    const act = String(rec.activity || '');
    if (!act || /ประชุม|WM|MM|สำนักงาน/i.test(act)) {
        rec.activity = meeting.label;
    }
    const staffCount = getOfficeStaffCount();
    rec.target_num = staffCount;
    rec.target_raw = `${staffCount} ราย`;
    return true;
}

function isOfficeOnlyLocation(location) {
    const loc = String(location || '').trim();
    if (!loc) return false;
    if (/หมู่\s*\d|ตำบล/.test(loc)) return false;
    return /สำนักงาน|สนง\.?\s*กษอ|สนง\.?เกษตร/.test(loc);
}

function isOfficeWorkRecord(rec) {
    if (!rec) return false;
    if (rec.officeOnly) return true;
    if (String(rec.issue_val) === '1') return true;
    return isOfficeOnlyLocation(rec.location);
}

/** Final PD_PLACE: หมู่ 1, 3, 5 ตำบลหนองตาดใหญ่, หมู่ 1, 2 ตำบลสามเมือง */
function formatCombinedPlace(parts, office = '') {
    const segs = (parts || [])
        .map(p => formatMooTambonSegment(p.moos || [], p.tambon || ''))
        .filter(Boolean);
    if (segs.length) return segs.join(', ');
    return (office || getOfficePlaceName() || '').trim();
}

function parseCombinedPlace(location) {
    const text = String(location || '').trim();
    if (!text) return [];
    // Split on comma that precedes หมู่ or ตำบล
    const chunks = text.split(/,\s*(?=หมู่\s|ตำบล)/).map(s => s.trim()).filter(Boolean);
    const parts = [];
    chunks.forEach(chunk => {
        const moos = parseMoosFromLocation(chunk);
        const tm = chunk.match(/ตำบล([^\s,]+)/);
        const tambon = tm ? bareTambonName(tm[1]) : '';
        if (tambon || moos.length) {
            parts.push({ tambon, moos });
        }
    });
    return parts;
}

function ensurePlaceParts(rec) {
    if (!rec) return [];
    if (isOfficeWorkRecord(rec)) {
        rec.placeParts = [];
        return rec.placeParts;
    }
    if (Array.isArray(rec.placeParts) && rec.placeParts.length) {
        rec.placeParts = rec.placeParts.map(p => ({
            tambon: bareTambonName(p.tambon || ''),
            moos: normalizeMoos(p.moos || [])
        })).filter(p => p.tambon || p.moos.length);
        return rec.placeParts;
    }
    // Migrate from old single-tambon fields
    const fromLoc = parseCombinedPlace(rec.location || '');
    if (fromLoc.length) {
        rec.placeParts = fromLoc;
        return rec.placeParts;
    }
    const tambon = bareTambonName(rec.tambon || geoState.tambonName || '');
    const moos = normalizeMoos(rec.moos || parseMoosFromLocation(rec.location));
    rec.placeParts = tambon || moos.length ? [{ tambon, moos }] : [];
    return rec.placeParts;
}

function syncRecordPlaceFromParts(rec) {
    if (isOfficeWorkRecord(rec)) {
        rec.officeOnly = true;
        rec.placeParts = [];
        rec.moos = [];
        rec.location = getOfficePlaceName();
        return rec.location;
    }
    const parts = ensurePlaceParts(rec);
    const office = getOfficePlaceName();
    rec.location = formatCombinedPlace(parts, office);
    rec.tambon = parts[0]?.tambon || bareTambonName(geoState.tambonName || '');
    rec.moos = parts[0]?.moos ? [...parts[0].moos] : [];
    return rec.location;
}

/**
 * หลังโหลด Excel: เลือกว่าจะสุ่มหมู่ 2–4 หรือไม่
 * สุ่มจากหมู่บ้านจริงของตำบลนั้นเท่านั้น
 * งานสำนักงาน → สำนักงานเกษตรอำเภอสีดา อย่างเดียว
 */
async function applyPlaceAfterExcelLoad(records) {
    const wantRandom = !!document.getElementById('opt-random-moo-on-load')?.checked;
    const officePlace = getOfficePlaceName();
    const responsible = [...getResponsibleTambonSet()];
    const coverAll = isAllAmphoeResponsibility() || isMultiTambonRole();
    let randomized = 0;
    let officeRows = 0;
    let missingVillageData = 0;
    let wmCount = 0;
    let dmCount = 0;

    for (const rec of records || []) {
        // วันจันทร์ = ประชุมสำนักงาน (จันทร์แรกของเดือน = DM, จันทร์อื่น = WM)
        if (applyOfficeMeetingRulesToRecord(rec)) {
            officeRows += 1;
            if (rec.activity_val === '13') dmCount += 1;
            else wmCount += 1;
            continue;
        }

        rec.officeOnly = false;
        rec.coverAllTambons = false;

        // ธุรการ/หัวหน้า หรือเลือกครบทุกตำบล → ใส่ทุกตำบล ไม่สุ่มหมู่
        if (coverAll) {
            const all = getAmphoeTambonNames();
            const list = all.length ? all : responsible;
            rec.coverAllTambons = true;
            rec.placeParts = list.map(t => ({ tambon: t, moos: [] }));
            syncRecordPlaceFromParts(rec);
            continue;
        }

        if (!responsible.length) {
            rec.placeParts = [];
            syncRecordPlaceFromParts(rec);
            continue;
        }

        if (wantRandom) {
            // 1 ตำบล = สุ่มหมู่ในตำบลนั้น · หลายตำบล = สุ่มหมู่ทุกตำบลที่รับผิดชอบใส่สถานที่
            const parts = [];
            for (const tb of responsible) {
                const pool = await getMoosForTambonName(tb);
                if (!pool.length) {
                    parts.push({ tambon: tb, moos: [] });
                    missingVillageData += 1;
                } else {
                    parts.push({ tambon: tb, moos: pickRandomMoosFromPool(pool, 2, 4) });
                }
            }
            rec.placeParts = parts;
            rec.tambon = responsible[0];
            randomized += 1;
        } else {
            rec.placeParts = responsible.map(tb => ({ tambon: tb, moos: [] }));
            rec.tambon = responsible[0];
        }
        syncRecordPlaceFromParts(rec);
    }

    if (coverAll) {
        addLog('info', 'โหมดทุกตำบล (หัวหน้า/ธุรการ) — งานภาคสนามใส่ทุกตำบล ไม่สุ่มหมู่');
    } else if (wantRandom && randomized) {
        addLog(
            'success',
            responsible.length === 1
                ? `สุ่มหมู่ในตำบล${responsible[0]} แล้ว ${randomized} แถวงานภาคสนาม`
                : `สุ่มหมู่ครบ ${responsible.length} ตำบลที่รับผิดชอบ แล้ว ${randomized} แถว (ใส่รวมในสถานที่)`
        );
    } else if (!wantRandom) {
        addLog('info', 'โหลดจาก Excel โดยไม่สุ่มหมู่ (ตามที่เลือก)');
    }
    if (missingVillageData) {
        addLog('warning', `บางตำบลยังไม่มีข้อมูลหมู่บ้าน — ข้ามการสุ่มหมู่ตำบลนั้น`);
    }
    if (officeRows) {
        addLog('info', `${officeRows} แถวประชุมสำนักงาน → «${officePlace}» (WM ${wmCount} / DM ${dmCount})`);
    }
}

function formatLocationString({ villages = [], moos = [], tambon = '', office = '' } = {}) {
    // Prefer combined moo+tambon segment (PD_PLACE). Villages optional prefix.
    const segment = formatMooTambonSegment(moos, tambon);
    const villageNames = normalizeVillages(villages);
    if (villageNames.length) {
        const v = villageNames.join(', ');
        if (segment) return `${v} ${segment}`;
        return office ? `${v} ${office}` : v;
    }
    if (segment) return segment;
    return office || '';
}

function closeAllMultiPanels() {
    document.querySelectorAll('.multi-select-panel').forEach(p => { p.hidden = true; });
    document.querySelectorAll('.multi-select-toggle').forEach(b => b.setAttribute('aria-expanded', 'false'));
}

function renderChipRow(container, items, labelFn, onRemove) {
    if (!container) return;
    container.innerHTML = '';
    items.forEach(item => {
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.innerHTML = `<span>${labelFn(item)}</span>`;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'chip-remove';
        btn.setAttribute('aria-label', 'ลบ');
        btn.textContent = '×';
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            onRemove(item);
        });
        chip.appendChild(btn);
        container.appendChild(chip);
    });
}

function persistGeoSelections() {
    geoState.moos = normalizeMoos(geoState.moos);
    geoState.moo = geoState.moos[0] || '';
    geoState.selectedVillages = normalizeVillages(geoState.selectedVillages);
    geoState.villageName = geoState.selectedVillages[0] || '';
    geoState.selectedTambons = normalizeTambons(geoState.selectedTambons);
    localStorage.setItem('tv_moos', JSON.stringify(geoState.moos));
    localStorage.setItem('tv_moo', geoState.moo);
    localStorage.setItem('tv_villages', JSON.stringify(geoState.selectedVillages));
    localStorage.setItem('tv_village', geoState.villageName);
    localStorage.setItem('tv_selected_tambons', JSON.stringify(geoState.selectedTambons));
}

function updateMooToggleLabel() {
    const btn = document.getElementById('moo-multi-toggle');
    if (!btn) return;
    const n = geoState.moos.length;
    btn.textContent = n ? `เลือกแล้ว ${n} หมู่` : 'เลือกหมู่...';
}

function updateVillageToggleLabel() {
    const btn = document.getElementById('village-multi-toggle');
    if (!btn) return;
    const n = geoState.selectedVillages.length;
    btn.textContent = n ? `เลือกแล้ว ${n} หมู่บ้าน` : 'เลือกหมู่บ้าน...';
}

function updateTambonToggleLabel() {
    const btn = document.getElementById('tambon-multi-toggle');
    if (!btn) return;
    const n = geoState.selectedTambons.length;
    const total = (geoState.tambons || []).length;
    if (!n) {
        btn.textContent = 'เลือกตำบล...';
    } else if (total && n >= total) {
        btn.textContent = `เลือกแล้วทุกตำบล (${n})`;
    } else {
        btn.textContent = `เลือกแล้ว ${n} ตำบล`;
    }
}

function renderGeoTambonChips() {
    renderChipRow(
        document.getElementById('tambon-chips'),
        geoState.selectedTambons,
        t => formatTambonPart(t),
        t => {
            geoState.selectedTambons = geoState.selectedTambons.filter(x => bareTambonName(x) !== bareTambonName(t));
            persistGeoSelections();
            rebuildTambonPanel();
            renderGeoTambonChips();
        }
    );
    updateTambonToggleLabel();
}

function rebuildTambonPanel() {
    const panel = document.getElementById('tambon-multi-panel');
    if (!panel) return;
    const list = geoState.tambons || [];
    const selected = new Set(normalizeTambons(geoState.selectedTambons).map(bareTambonName));
    if (!list.length) {
        panel.innerHTML = '<div class="resp-tambon-empty">เลือกอำเภอก่อน — ระบบจะแสดงรายการตำบลให้ติ๊กเลือก (เลือกได้หลายตำบล)</div>';
        return;
    }
    // Always-visible checkbox grid — หน่วยเล็กสุดคือตำบล
    panel.innerHTML = list.map(t => {
        const name = bareTambonName(t.name_th);
        return `<label class="resp-tambon-item"><input type="checkbox" value="${escapeAttr(name)}" ${selected.has(name) ? 'checked' : ''}> <span>${escapeAttr(formatTambonPart(name))}</span></label>`;
    }).join('');
    panel.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', () => {
            if (cb.checked) {
                if (!geoState.selectedTambons.map(bareTambonName).includes(cb.value)) {
                    geoState.selectedTambons.push(cb.value);
                }
            } else {
                geoState.selectedTambons = geoState.selectedTambons.filter(x => bareTambonName(x) !== cb.value);
            }
            geoState.selectedTambons = normalizeTambons(geoState.selectedTambons);
            geoState.setupConfirmed = false;
            localStorage.setItem('tv_setup_confirmed', '0');
            persistGeoSelections();
            renderGeoTambonChips();
            const primary = geoState.selectedTambons[0] || '';
            const tambonInput = document.getElementById('tambon');
            if (tambonInput) tambonInput.value = primary;
            geoState.tambonName = primary;
            updateSetupSummary();
        });
    });
}

async function selectAllTambonsInAmphoe() {
    if (!geoState.amphoeCode) {
        addLog('warning', 'กรุณาเลือกอำเภอก่อน');
        return;
    }
    if (!geoState.tambons.length) {
        const res = await fetch(`/api/geo/tambons?amphoe_code=${encodeURIComponent(geoState.amphoeCode)}`).then(r => r.json());
        geoState.tambons = res.tambons || [];
        fillDatalist('tambon-list', geoState.tambons.map(t => t.name_th));
    }
    if (!geoState.tambons.length) {
        addLog('warning', 'ไม่พบรายการตำบลในอำเภอนี้');
        return;
    }
    geoState.selectedTambons = normalizeTambons(geoState.tambons.map(t => t.name_th));
    persistGeoSelections();
    rebuildTambonPanel();
    renderGeoTambonChips();
    const first = geoState.selectedTambons[0] || '';
    if (first && !document.getElementById('tambon').value.trim()) {
        document.getElementById('tambon').value = first;
        await onTambonPicked();
    }
    addLog('info', `เลือกทุกตำบลในอำเภอแล้ว (${geoState.selectedTambons.length} ตำบล)`);
}

function initTambonMultiSelect() {
    const panel = document.getElementById('tambon-multi-panel');
    const allBtn = document.getElementById('select-all-tambons-btn');
    const clearBtn = document.getElementById('clear-tambons-btn');
    if (!panel) return;
    let saved = [];
    try { saved = JSON.parse(localStorage.getItem('tv_selected_tambons') || '[]'); } catch (_) {}
    geoState.selectedTambons = normalizeTambons(saved);
    rebuildTambonPanel();
    renderGeoTambonChips();
    if (allBtn) {
        allBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            await selectAllTambonsInAmphoe();
            geoState.setupConfirmed = false;
            updateSetupSummary();
        });
    }
    if (clearBtn) {
        clearBtn.addEventListener('click', (e) => {
            e.preventDefault();
            geoState.selectedTambons = [];
            geoState.setupConfirmed = false;
            localStorage.setItem('tv_setup_confirmed', '0');
            persistGeoSelections();
            rebuildTambonPanel();
            renderGeoTambonChips();
            updateSetupSummary();
        });
    }
}

function renderGeoMooChips() {
    renderChipRow(
        document.getElementById('moo-chips'),
        geoState.moos,
        m => `ม.${m}`,
        m => {
            geoState.moos = geoState.moos.filter(x => x !== m);
            persistGeoSelections();
            rebuildMooPanel();
            renderGeoMooChips();
            updateMooToggleLabel();
            refreshLocationPresets();
        }
    );
    updateMooToggleLabel();
}

function renderGeoVillageChips() {
    renderChipRow(
        document.getElementById('village-chips'),
        geoState.selectedVillages,
        name => name,
        name => {
            geoState.selectedVillages = geoState.selectedVillages.filter(x => x !== name);
            persistGeoSelections();
            rebuildVillagePanel();
            renderGeoVillageChips();
            updateVillageToggleLabel();
            refreshLocationPresets();
        }
    );
    updateVillageToggleLabel();
}

function rebuildMooPanel() {
    const panel = document.getElementById('moo-multi-panel');
    if (!panel) return;
    const selected = new Set(geoState.moos);
    // Only real moos of the selected tambon (from village data)
    const pool = moosFromVillages(geoState.villages);
    const extras = geoState.moos.filter(m => !pool.includes(m));
    let html = pool.length
        ? `<div style="padding:0.25rem 0.45rem;font-size:0.72rem;color:var(--text-muted);">หมู่ในตำบล${geoState.tambonName || ''} (${pool.length} หมู่)</div>`
        : `<div style="padding:0.25rem 0.45rem;font-size:0.72rem;color:var(--text-muted);">เลือกตำบลก่อน — จะแสดงเฉพาะหมู่ที่มีจริง</div>`;
    pool.forEach(v => {
        html += `<label class="multi-select-option"><input type="checkbox" value="${escapeAttr(v)}" ${selected.has(v) ? 'checked' : ''}> หมู่ ${escapeAttr(v)}</label>`;
    });
    extras.forEach(v => {
        html += `<label class="multi-select-option"><input type="checkbox" value="${escapeAttr(v)}" checked> หมู่ ${escapeAttr(v)} (นอกรายการ)</label>`;
    });
    html += `<div class="multi-select-actions">
        <button type="button" data-act="all" ${pool.length ? '' : 'disabled'}>ทุกหมู่ในตำบล</button>
        <button type="button" data-act="clear">ล้าง</button>
    </div>`;
    panel.innerHTML = html;
    panel.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', () => {
            if (cb.checked) {
                if (!geoState.moos.includes(cb.value)) geoState.moos.push(cb.value);
            } else {
                geoState.moos = geoState.moos.filter(x => x !== cb.value);
            }
            persistGeoSelections();
            renderGeoMooChips();
            refreshLocationPresets();
        });
    });
    panel.querySelector('[data-act="all"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        geoState.moos = normalizeMoos(pool);
        persistGeoSelections();
        rebuildMooPanel();
        renderGeoMooChips();
        refreshLocationPresets();
    });
    panel.querySelector('[data-act="clear"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        geoState.moos = [];
        persistGeoSelections();
        rebuildMooPanel();
        renderGeoMooChips();
        refreshLocationPresets();
    });
}

function rebuildVillagePanel() {
    const panel = document.getElementById('village-multi-panel');
    if (!panel) return;
    const selected = new Set(geoState.selectedVillages);
    const list = geoState.villages || [];
    if (!list.length) {
        panel.innerHTML = '<div class="multi-select-option" style="cursor:default;opacity:0.7;">ยังไม่มีรายการ — พิมพ์เพิ่มด้านล่าง</div>';
        return;
    }
    let html = list.map(v => {
        const name = v.name_th || '';
        const label = v.moo ? `${name} (ม.${v.moo})` : name;
        return `<label class="multi-select-option"><input type="checkbox" value="${escapeAttr(name)}" data-moo="${escapeAttr(v.moo || '')}" ${selected.has(name) ? 'checked' : ''}> ${escapeAttr(label)}</label>`;
    }).join('');
    html += `<div class="multi-select-actions"><button type="button" data-act="clear">ล้าง</button></div>`;
    panel.innerHTML = html;
    panel.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', () => {
            const name = cb.value;
            const moo = cb.dataset.moo || '';
            if (cb.checked) {
                if (!geoState.selectedVillages.includes(name)) geoState.selectedVillages.push(name);
                if (moo && !geoState.moos.includes(moo)) {
                    geoState.moos.push(moo);
                    rebuildMooPanel();
                    renderGeoMooChips();
                }
            } else {
                geoState.selectedVillages = geoState.selectedVillages.filter(x => x !== name);
            }
            persistGeoSelections();
            renderGeoVillageChips();
            refreshLocationPresets();
        });
    });
    panel.querySelector('[data-act="clear"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        geoState.selectedVillages = [];
        persistGeoSelections();
        rebuildVillagePanel();
        renderGeoVillageChips();
        refreshLocationPresets();
    });
}

function initMooMultiSelect() {
    const toggle = document.getElementById('moo-multi-toggle');
    const panel = document.getElementById('moo-multi-panel');
    if (!toggle || !panel) return;
    let saved = [];
    try { saved = JSON.parse(localStorage.getItem('tv_moos') || '[]'); } catch (_) {}
    if (!Array.isArray(saved) || !saved.length) {
        const legacy = localStorage.getItem('tv_moo') || '';
        if (legacy && legacy !== '_custom') saved = [legacy];
    }
    geoState.moos = normalizeMoos(saved);
    rebuildMooPanel();
    renderGeoMooChips();
    toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = panel.hidden;
        closeAllMultiPanels();
        if (open) {
            panel.hidden = false;
            toggle.setAttribute('aria-expanded', 'true');
        }
    });
}

function initVillageMultiSelect() {
    const toggle = document.getElementById('village-multi-toggle');
    const panel = document.getElementById('village-multi-panel');
    const addInput = document.getElementById('village-select');
    if (!toggle || !panel) return;
    let saved = [];
    try { saved = JSON.parse(localStorage.getItem('tv_villages') || '[]'); } catch (_) {}
    if (!Array.isArray(saved) || !saved.length) {
        const legacy = localStorage.getItem('tv_village') || '';
        if (legacy) saved = [legacy];
    }
    geoState.selectedVillages = normalizeVillages(saved);
    rebuildVillagePanel();
    renderGeoVillageChips();
    toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = panel.hidden;
        closeAllMultiPanels();
        if (open) {
            panel.hidden = false;
            toggle.setAttribute('aria-expanded', 'true');
        }
    });
    if (addInput) {
        addInput.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            onVillagePicked(true);
        });
    }
}

async function initGeoCascade() {
    try {
        const [provRes, distRes] = await Promise.all([
            fetch('/api/geo/provinces').then(r => r.json()),
            fetch('/api/districts').then(r => r.json())
        ]);
        geoState.provinces = provRes.provinces || [];
        geoState.presets = distRes.presets || [];
        fillSelect('province-select', geoState.provinces, '— เลือกจังหวัด —');
        fillDatalist('province-list', geoState.provinces.map(p => p.name_th));

        const pInput = document.getElementById('province-select');
        const aInput = document.getElementById('amphoe-select');
        const tInput = document.getElementById('tambon');
        const vInput = document.getElementById('village-select');

        if (pInput) {
            pInput.addEventListener('change', onProvincePicked);
            pInput.addEventListener('blur', onProvincePicked);
        }
        if (aInput) {
            aInput.addEventListener('change', onAmphoePicked);
            aInput.addEventListener('blur', onAmphoePicked);
        }
        if (tInput) {
            tInput.addEventListener('change', onTambonPicked);
            tInput.addEventListener('blur', onTambonPicked);
        }
        if (vInput) {
            vInput.addEventListener('change', onVillagePicked);
            vInput.addEventListener('blur', onVillagePicked);
        }

        // Clear old legacy Sida values from localStorage so fresh users start with empty selection
        if (localStorage.getItem('tv_amphoe_name') === 'สีดา' || localStorage.getItem('tv_office_name') === 'สำนักงานเกษตรอำเภอสีดา') {
            localStorage.removeItem('tv_province_name');
            localStorage.removeItem('tv_province_code');
            localStorage.removeItem('tv_amphoe_name');
            localStorage.removeItem('tv_amphoe_code');
            localStorage.removeItem('tv_tambon');
            localStorage.removeItem('tv_tambon_code');
            localStorage.removeItem('tv_office_name');
            localStorage.removeItem('tv_selected_tambons');
            localStorage.removeItem('tv_setup_confirmed');
        }

        // Restore saved geo if available
        const savedP = localStorage.getItem('tv_province_name') || '';
        const savedA = localStorage.getItem('tv_amphoe_name') || '';
        const savedT = localStorage.getItem('tv_tambon') || '';
        if (savedP && pInput) {
            pInput.value = savedP;
            await onProvincePicked();
            if (savedA && aInput) {
                aInput.value = savedA;
                await onAmphoePicked();
                if (savedT && tInput) {
                    tInput.value = savedT;
                    await onTambonPicked();
                    rebuildVillagePanel();
                    renderGeoVillageChips();
                    rebuildMooPanel();
                    renderGeoMooChips();
                }
                rebuildTambonPanel();
                renderGeoTambonChips();
            }
        }
        await ensureAmphoeTambonsLoaded();
        if (isMultiTambonRole() && geoState.amphoeCode) {
            await selectAllTambonsInAmphoe();
        } else if (!normalizeTambons(geoState.selectedTambons).length) {
            // Migrate single tambon from old UI → พื้นที่รับผิดชอบ
            const one = bareTambonName(
                document.getElementById('tambon')?.value || geoState.tambonName || ''
            );
            if (one) {
                geoState.selectedTambons = [one];
                persistGeoSelections();
                rebuildTambonPanel();
                renderGeoTambonChips();
            }
        }
        const savedStaffCount = localStorage.getItem('tv_office_staff_count');
        if (savedStaffCount) {
            const countInput = document.getElementById('office-staff-count');
            if (countInput) countInput.value = savedStaffCount;
            geoState.officeStaffCount = parseInt(savedStaffCount, 10) || 7;
        }
        updateSetupSummary();
    } catch (err) {
        addLog('error', `โหลดข้อมูลภูมิศาสตร์ล้มเหลว: ${err}`);
    }
}

/** Load all tambons for current amphoe (used by place builder). */
async function ensureAmphoeTambonsLoaded() {
    // Resolve amphoe from UI / localStorage / sida preset if needed
    if (!geoState.amphoeCode) {
        const aName = (document.getElementById('amphoe-select')?.value || geoState.amphoeName || '').trim();
        if (aName && geoState.amphoes.length) {
            const a = findByName(geoState.amphoes, aName);
            if (a) geoState.amphoeCode = a.code;
        }
    }
    if (!geoState.amphoeCode) return geoState.tambons || [];
    if (geoState.tambons && geoState.tambons.length) return geoState.tambons;

    try {
        const res = await fetch(`/api/geo/tambons?amphoe_code=${encodeURIComponent(geoState.amphoeCode)}`).then(r => r.json());
        geoState.tambons = res.tambons || [];
        fillDatalist('tambon-list', geoState.tambons.map(t => t.name_th));
        if (geoState.tambons.length) {
            addLog('info', `โหลดตำบลในอำเภอ${geoState.amphoeName || ''} แล้ว ${geoState.tambons.length} ตำบล`);
        }
    } catch (e) {
        addLog('error', `โหลดรายการตำบลล้มเหลว: ${e}`);
    }
    return geoState.tambons || [];
}

function fillSelect(id, items, placeholder = '') {
    const sel = document.getElementById(id);
    if (!sel) return;
    let html = placeholder ? `<option value="">${escapeAttr(placeholder)}</option>` : '';
    (items || []).forEach(item => {
        const val = typeof item === 'string' ? item : (item.name_th || item.value || '');
        const label = typeof item === 'string' ? item : (item.name_th || item.label || val);
        html += `<option value="${escapeAttr(val)}">${escapeAttr(label)}</option>`;
    });
    sel.innerHTML = html;
}

function fillDatalist(id, names) {
    const dl = document.getElementById(id);
    if (!dl) return;
    dl.innerHTML = names.map(n => `<option value="${escapeAttr(n)}"></option>`).join('');
}

function fillPresetSelect() {
    const sel = document.getElementById('preset-select');
    if (!sel) return;
    sel.innerHTML = '<option value="">— เลือกเอง —</option>';
    geoState.presets.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.label || p.id;
        sel.appendChild(opt);
    });
}

function escapeAttr(s) {
    return String(s).replace(/"/g, '&quot;');
}

function findByName(list, name) {
    const n = (name || '').trim();
    const bare = bareTambonName(n);
    return list.find(x => x.name_th === n)
        || list.find(x => bareTambonName(x.name_th) === bare)
        || list.find(x => x.name_th === bare)
        || null;
}

function resolveTambonMeta(tambonName) {
    const bare = bareTambonName(tambonName);
    if (!bare) return { code: '', name_th: '' };
    const hit = findByName(geoState.tambons || [], bare)
        || findByName(geoState.tambons || [], tambonName);
    return {
        code: hit ? hit.code : '',
        name_th: hit ? hit.name_th : bare
    };
}

async function loadVillagesForTambonName(tambonName) {
    const meta = resolveTambonMeta(tambonName);
    if (!meta.code) return [];
    if (rowVillageCache[meta.code]) return rowVillageCache[meta.code];
    try {
        const res = await fetch(`/api/geo/villages?tambon_code=${encodeURIComponent(meta.code)}`).then(r => r.json());
        const list = res.villages || [];
        rowVillageCache[meta.code] = list;
        return list;
    } catch (e) {
        return [];
    }
}

/** Unique moo numbers from village list (sorted numerically) */
function moosFromVillages(villages) {
    const seen = new Set();
    const out = [];
    (villages || []).forEach(v => {
        const m = String(v?.moo ?? '').trim();
        if (!m || seen.has(m)) return;
        seen.add(m);
        out.push(m);
    });
    return out.sort((a, b) => {
        const na = parseInt(a, 10);
        const nb = parseInt(b, 10);
        if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
        return String(a).localeCompare(String(b), 'th');
    });
}

async function getMoosForTambonName(tambonName) {
    const villages = await loadVillagesForTambonName(tambonName);
    return moosFromVillages(villages);
}

function buildLocationPresetsForTambon(tambonName, villages = []) {
    const office = document.getElementById('office-name')?.value.trim() || geoState.officeName || '';
    const tpart = formatTambonPart(tambonName || geoState.tambonName || '');
    const presets = [];
    if (office) {
        presets.push({ value: office, label: office });
    }
    if (tpart) {
        presets.push({ value: tpart, label: tpart });
    }
    (villages || []).slice(0, 40).forEach(v => {
        const name = v.name_th || '';
        if (!name) return;
        const moo = v.moo || '';
        let value = name;
        if (moo && !name.includes('หมู่')) value = `${name} หมู่ ${moo}`;
        if (tpart && !value.includes(tpart)) value = `${value} ${tpart}`;
        const label = moo ? `${name} (ม.${moo})` : name;
        presets.push({ value, label });
    });
    presets.push({ value: '_custom', label: 'กำหนดเอง...' });
    const seen = new Set();
    return presets.filter(p => {
        if (!p.value && p.value !== '_custom') return false;
        if (seen.has(p.value)) return false;
        seen.add(p.value);
        return true;
    });
}

function locationMatchesTambon(location, tambonName) {
    const loc = String(location || '');
    const bare = bareTambonName(tambonName);
    if (!bare) return true;
    if (!loc) return false;
    // If location mentions another explicit ตำบล..., require match
    const m = loc.match(/ตำบล([^\s,]+)/);
    if (m) return bareTambonName(m[1]) === bare;
    return true;
}

async function onPresetChange() {
    const id = document.getElementById('preset-select').value;
    if (!id) return;
    const preset = geoState.presets.find(p => p.id === id);
    if (!preset) return;
    document.getElementById('province-select').value = preset.province_name || '';
    await onProvincePicked();
    document.getElementById('amphoe-select').value = preset.amphoe_name || '';
    await onAmphoePicked();
    const tb = preset.default_tambon_name || '';
    if (tb) {
        document.getElementById('tambon').value = tb;
        await onTambonPicked();
    }
    if (preset.office_name) {
        document.getElementById('office-name').value = preset.office_name;
        geoState.officeName = preset.office_name;
        localStorage.setItem('tv_office_name', preset.office_name);
    } else if (preset.amphoe_name) {
        const office = `สำนักงานเกษตรอำเภอ${preset.amphoe_name}`;
        document.getElementById('office-name').value = office;
        geoState.officeName = office;
        localStorage.setItem('tv_office_name', office);
    }
    if (preset.office_staff_count) {
        const staffInput = document.getElementById('office-staff-count');
        if (staffInput) staffInput.value = preset.office_staff_count;
        geoState.officeStaffCount = preset.office_staff_count;
        localStorage.setItem('tv_office_staff_count', String(preset.office_staff_count));
    }
    addLog('info', `ใช้พรีเซ็ต: ${preset.label}`);
}

async function onRoleChange() {
    const role = document.getElementById('role-select').value;
    geoState.role = role;
    localStorage.setItem('tv_role', role);
    geoState.setupConfirmed = false;
    localStorage.setItem('tv_setup_confirmed', '0');
    const hint = document.getElementById('role-hint');
    if (hint) {
        if (role === 'officer') {
            hint.textContent = 'เลือก 1 หรือหลายตำบลที่รับผิดชอบ (เช่น หนองตาดใหญ่ หรือ 2 ตำบล)';
        } else {
            hint.textContent = 'ธุรการ/หัวหน้า = ทุกตำบลเหมือนกัน (ไม่สุ่มหมู่) — ระบบเลือกทุกตำบลให้อัตโนมัติ';
        }
    }
    document.body.classList.toggle('role-multi-tambon', isMultiTambonRole(role));
    if (isMultiTambonRole(role) && geoState.amphoeCode) {
        await selectAllTambonsInAmphoe();
    }
    rebuildTambonPanel();
    renderGeoTambonChips();
    updateSetupSummary();
    if (allRecords.length) renderTable(allRecords);
}

async function onProvincePicked() {
    const name = document.getElementById('province-select').value.trim();
    const p = findByName(geoState.provinces, name);
    geoState.provinceName = name;
    geoState.provinceCode = p ? p.code : '';
    localStorage.setItem('tv_province_name', name);
    localStorage.setItem('tv_province_code', geoState.provinceCode);
    document.getElementById('amphoe-select').value = '';
    document.getElementById('tambon').value = '';
    if (document.getElementById('village-select')) document.getElementById('village-select').value = '';
    const officeInput = document.getElementById('office-name');
    if (officeInput) officeInput.value = '';
    geoState.officeName = '';
    localStorage.removeItem('tv_office_name');
    geoState.amphoes = [];
    geoState.tambons = [];
    geoState.villages = [];
    geoState.selectedTambons = [];
    fillSelect('amphoe-select', [], '— เลือกอำเภอก่อน —');
    fillDatalist('amphoe-list', []);
    fillDatalist('tambon-list', []);
    fillDatalist('village-list', []);
    persistGeoSelections();
    rebuildTambonPanel();
    renderGeoTambonChips();
    updateSetupSummary();
    if (!geoState.provinceCode) return;
    const res = await fetch(`/api/geo/amphoes?province_code=${encodeURIComponent(geoState.provinceCode)}`).then(r => r.json());
    geoState.amphoes = res.amphoes || [];
    fillSelect('amphoe-select', geoState.amphoes, '— เลือกอำเภอ —');
    fillDatalist('amphoe-list', geoState.amphoes.map(a => a.name_th));
}

async function onAmphoePicked() {
    const name = document.getElementById('amphoe-select').value.trim();
    const a = findByName(geoState.amphoes, name);
    const prevAmphoe = geoState.amphoeCode;
    geoState.amphoeName = name;
    geoState.amphoeCode = a ? a.code : '';
    localStorage.setItem('tv_amphoe_name', name);
    localStorage.setItem('tv_amphoe_code', geoState.amphoeCode);
    document.getElementById('tambon').value = '';
    document.getElementById('village-select').value = '';
    geoState.tambons = [];
    geoState.villages = [];
    fillDatalist('tambon-list', []);
    fillDatalist('village-list', []);
    if (prevAmphoe && prevAmphoe !== geoState.amphoeCode) {
        geoState.selectedTambons = [];
        persistGeoSelections();
    }
    const officeInput = document.getElementById('office-name');
    if (name) {
        const office = `สำนักงานเกษตรอำเภอ${name}`;
        if (officeInput) officeInput.value = office;
        geoState.officeName = office;
        localStorage.setItem('tv_office_name', office);
    } else {
        if (officeInput) officeInput.value = '';
        geoState.officeName = '';
        localStorage.removeItem('tv_office_name');
    }
    if (!geoState.amphoeCode) {
        rebuildTambonPanel();
        renderGeoTambonChips();
        return;
    }
    const res = await fetch(`/api/geo/tambons?amphoe_code=${encodeURIComponent(geoState.amphoeCode)}`).then(r => r.json());
    geoState.tambons = res.tambons || [];
    fillDatalist('tambon-list', geoState.tambons.map(t => t.name_th));
    // Keep only selected tambons that still exist in this amphoe
    const valid = new Set(geoState.tambons.map(t => bareTambonName(t.name_th)));
    geoState.selectedTambons = normalizeTambons(geoState.selectedTambons).filter(t => valid.has(bareTambonName(t)));
    persistGeoSelections();
    rebuildTambonPanel();
    renderGeoTambonChips();
    updateSetupSummary();
    // Place builder can pick any tambon in this amphoe
    allRecords.forEach((_, idx) => {
        if (document.getElementById(`place-builder-${idx}`)) renderPlaceBuilder(idx);
    });
}

async function onTambonPicked() {
    const name = document.getElementById('tambon').value.trim();
    const t = findByName(geoState.tambons, name);
    geoState.tambonName = name;
    geoState.tambonCode = t ? t.code : '';
    localStorage.setItem('tv_tambon', name);
    localStorage.setItem('tv_tambon_code', geoState.tambonCode);
    if (isMultiTambonRole() && name) {
        const tbBare = bareTambonName(name);
        if (tbBare && !geoState.selectedTambons.map(bareTambonName).includes(tbBare)) {
            geoState.selectedTambons.push(tbBare);
            geoState.selectedTambons = normalizeTambons(geoState.selectedTambons);
            persistGeoSelections();
            rebuildTambonPanel();
            renderGeoTambonChips();
        }
    }
    document.getElementById('village-select').value = '';
    geoState.villages = [];
    fillDatalist('village-list', []);
    if (!geoState.tambonCode) {
        refreshLocationPresets();
        return;
    }
    const res = await fetch(`/api/geo/villages?tambon_code=${encodeURIComponent(geoState.tambonCode)}`).then(r => r.json());
    geoState.villages = res.villages || [];
    if (geoState.tambonCode) rowVillageCache[geoState.tambonCode] = geoState.villages;
    // Keep only moos that exist in this tambon
    const validMoos = new Set(moosFromVillages(geoState.villages));
    if (validMoos.size) {
        geoState.moos = normalizeMoos(geoState.moos.filter(m => validMoos.has(String(m))));
        persistGeoSelections();
    }
    rebuildMooPanel();
    renderGeoMooChips();
    // Officer role: keep every row tambon/location in sync with the panel tambon
    if (!isMultiTambonRole() && allRecords.length) {
        const bare = bareTambonName(geoState.tambonName);
        allRecords.forEach((rec, idx) => {
            rec.tambon = bare;
            const input = document.getElementById(`tambon-${idx}`);
            if (input) {
                input.value = bare;
                input.title = formatTambonPart(bare);
            }
            syncRowTambonLocation(idx, { force: true });
        });
    }
    const villageBare = geoState.villages.map(v => v.name_th);
    const withMoo = geoState.villages.map(v => v.moo ? `${v.name_th} (ม.${v.moo})` : v.name_th);
    fillDatalist('village-list', [...new Set([...withMoo, ...villageBare])]);
    rebuildVillagePanel();
    renderGeoVillageChips();
    refreshLocationPresets();
}

function onVillagePicked(fromEnter = false) {
    const input = document.getElementById('village-select');
    const raw = (input?.value || '').trim();
    if (!raw) {
        persistGeoSelections();
        refreshLocationPresets();
        return;
    }
    const name = raw.replace(/\s*\(ม\.\d+\)\s*$/, '').trim();
    const matched = geoState.villages.find(v =>
        v.name_th === name || `${v.name_th} (ม.${v.moo})` === raw
    );
    if (!geoState.selectedVillages.includes(name)) {
        geoState.selectedVillages.push(name);
    }
    if (matched && matched.moo && !geoState.moos.includes(matched.moo)) {
        geoState.moos.push(matched.moo);
        rebuildMooPanel();
        renderGeoMooChips();
    }
    if (input) input.value = '';
    persistGeoSelections();
    rebuildVillagePanel();
    renderGeoVillageChips();
    refreshLocationPresets();
    if (fromEnter) closeAllMultiPanels();
}

async function refreshLocationPresets() {
    const office = document.getElementById('office-name').value.trim();
    const tambon = document.getElementById('tambon').value.trim();
    const params = new URLSearchParams({
        office_name: office,
        tambon_name: tambon,
        tambon_code: geoState.tambonCode || ''
    });
    try {
        const res = await fetch(`/api/location-presets?${params}`).then(r => r.json());
        locationPresets = res.presets || [{ value: '_custom', label: 'กำหนดเอง...' }];
        if (allRecords.length) {
            // re-init location selects without full re-render
        }
    } catch (e) {
        locationPresets = [
            { value: office || '', label: office || 'สำนักงาน' },
            { value: tambon ? (tambon.startsWith('ตำบล') ? tambon : `ตำบล${tambon}`) : '', label: tambon },
            { value: '_custom', label: 'กำหนดเอง...' }
        ].filter(x => x.value || x.value === '_custom');
    }
}

function buildDefaultLocation() {
    const office = document.getElementById('office-name').value.trim();
    const tambon = document.getElementById('tambon').value.trim();
    return formatLocationString({
        villages: geoState.selectedVillages,
        moos: geoState.moos,
        tambon,
        office
    });
}

function parseMoosFromLocation(location) {
    const text = String(location || '');
    const m = text.match(/หมู่\s*([\d,\s]+)/);
    if (!m) return [];
    return normalizeMoos(m[1].split(/[,\s]+/).filter(Boolean));
}

function ensureRowGeoFields(rec) {
    if (!Array.isArray(rec.villages)) {
        rec.villages = [];
    } else {
        rec.villages = normalizeVillages(rec.villages);
    }
    if (isOfficeWorkRecord(rec)) {
        rec.officeOnly = true;
        rec.placeParts = [];
        rec.moos = [];
        rec.location = getOfficePlaceName();
        return rec;
    }
    ensurePlaceParts(rec);
    if (!Array.isArray(rec.moos) || !rec.moos.length) {
        rec.moos = normalizeMoos(rec.placeParts[0]?.moos || parseMoosFromLocation(rec.location));
    } else {
        rec.moos = normalizeMoos(rec.moos);
    }
    syncRecordPlaceFromParts(rec);
    return rec;
}

function getAmphoeTambonNames() {
    const fromGeo = (geoState.tambons || []).map(t => bareTambonName(t.name_th)).filter(Boolean);
    if (fromGeo.length) {
        return [...new Set(fromGeo)].sort((a, b) => a.localeCompare(b, 'th'));
    }
    return [];
}

function nextUnusedAmphoeTambon(placeParts) {
    const used = new Set((placeParts || []).map(p => bareTambonName(p.tambon)));
    const all = getAmphoeTambonNames();
    return all.find(t => !used.has(t)) || '';
}

/** ตำบลที่รับผิดชอบจาก Step 0 (ชิปที่เลือก) */
function getResponsibleTambonSet() {
    const selected = normalizeTambons(geoState.selectedTambons || []);
    if (selected.length) return new Set(selected);
    const one = bareTambonName(document.getElementById('tambon')?.value || geoState.tambonName || '');
    return one ? new Set([one]) : new Set();
}

function isCoveringAllAmphoeTambons(rec) {
    if (rec?.coverAllTambons) return true;
    const all = getAmphoeTambonNames();
    if (!all.length) return false;
    const parts = ensurePlaceParts(rec || {});
    const inPlace = new Set(parts.map(p => bareTambonName(p.tambon)).filter(Boolean));
    return all.length > 0 && all.every(t => inPlace.has(t));
}

/**
 * สุ่มหมู่ 2–4 จาก pool จริงของตำบลเท่านั้น
 * ถ้าตำบลมีหมู่บ้านน้อยกว่า 2 → สุ่มเท่าที่มีจริง
 */
function pickRandomMoosFromPool(pool, minCount = 2, maxCount = 4) {
    const unique = normalizeMoos(pool || []);
    if (!unique.length) return [];
    const lo = Math.max(1, Math.min(unique.length, minCount));
    const hi = Math.max(lo, Math.min(unique.length, maxCount));
    const count = lo + Math.floor(Math.random() * (hi - lo + 1));
    const shuffled = [...unique];
    for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return normalizeMoos(shuffled.slice(0, count));
}

/**
 * สุ่มหมู่ 2–4 เฉพาะตำบลที่รับผิดชอบ จากหมู่บ้านจริงของตำบลนั้น
 * ถ้าแถวเป็นโหมดไปทุกตำบลในอำเภอ → ไม่สุ่ม
 */
async function randomizeMoosForResponsibleTambons(rowIdx) {
    const rec = allRecords[rowIdx];
    if (!rec) return { ok: false, reason: 'ไม่พบแถว' };
    ensurePlaceParts(rec);

    if (isCoveringAllAmphoeTambons(rec)) {
        return {
            ok: false,
            reason: 'โหมดไปทุกตำบลในอำเภอ — ไม่สุ่มหมู่ (ใส่เฉพาะชื่อตำบล)'
        };
    }

    const responsible = getResponsibleTambonSet();
    if (!responsible.size) {
        return { ok: false, reason: 'ยังไม่ระบุตำบลที่รับผิดชอบด้านบน' };
    }

    let changed = 0;
    const details = [];
    const skipped = [];
    for (const part of rec.placeParts) {
        const tb = bareTambonName(part.tambon);
        if (!tb || !responsible.has(tb)) continue;
        const pool = await getMoosForTambonName(tb);
        if (!pool.length) {
            skipped.push(`ตำบล${tb}: ไม่พบข้อมูลหมู่บ้าน`);
            continue;
        }
        part.moos = pickRandomMoosFromPool(pool, 2, 4);
        changed += 1;
        details.push(`ตำบล${tb}: หมู่ ${part.moos.join(', ')} (จาก ${pool.length} หมู่ในตำบล)`);
    }

    if (!changed) {
        return {
            ok: false,
            reason: skipped.length
                ? skipped.join(' · ')
                : 'ไม่มีตำบลที่รับผิดชอบในสถานที่นี้ — เพิ่มตำบลที่รับผิดชอบก่อน แล้วค่อยสุ่ม'
        };
    }

    syncRecordPlaceFromParts(rec);
    return { ok: true, changed, details, skipped };
}

function buildTambonSelectOptions(selectedTambon, placeParts, partIdx) {
    const all = getAmphoeTambonNames();
    const selected = bareTambonName(selectedTambon);
    const usedElsewhere = new Set(
        (placeParts || [])
            .map((p, i) => (i === partIdx ? '' : bareTambonName(p.tambon)))
            .filter(Boolean)
    );
    let opts = `<option value="">— เลือกตำบลในอำเภอ${geoState.amphoeName ? ' ' + geoState.amphoeName : ''} —</option>`;
    if (selected && !all.includes(selected)) {
        opts += `<option value="${escapeAttr(selected)}" selected>${escapeAttr(selected)} (นอกบัญชี)</option>`;
    }
    all.forEach(name => {
        const taken = usedElsewhere.has(name);
        const sel = name === selected ? 'selected' : '';
        const mark = taken ? ' (ใช้อยู่แล้วในแถวนี้)' : '';
        opts += `<option value="${escapeAttr(name)}" ${sel}>${escapeAttr(name)}${mark}</option>`;
    });
    return opts;
}

async function renderPlaceBuilder(rowIdx) {
    const wrap = document.getElementById(`place-builder-${rowIdx}`);
    const preview = document.getElementById(`location-preview-${rowIdx}`);
    const rec = allRecords[rowIdx];
    if (!wrap || !rec) return;

    // Critical: load full amphoe tambon list before building dropdown
    await ensureAmphoeTambonsLoaded();

    if (isOfficeWorkRecord(rec)) {
        const officePlace = getOfficePlaceName();
        rec.officeOnly = true;
        rec.placeParts = [];
        rec.moos = [];
        rec.location = officePlace;
        wrap.innerHTML = `<div class="place-amphoe-hint">งานสำนักงาน — ใช้สถานที่อย่างเดียว ไม่ต้องใส่หมู่/ตำบล</div>
            <div class="place-seg-preview" title="${escapeAttr(officePlace)}">${escapeAttr(officePlace)}</div>
            <div class="place-builder-actions">
                <button type="button" class="btn-place-add" id="place-use-field-${rowIdx}">เปลี่ยนเป็นงานภาคสนาม (เลือกตำบล/หมู่)</button>
            </div>`;
        if (preview) {
            preview.textContent = officePlace;
            preview.title = officePlace;
        }
        document.getElementById(`place-use-field-${rowIdx}`)?.addEventListener('click', () => {
            rec.officeOnly = false;
            rec.issue_val = rec.issue_val === '1' ? '2' : rec.issue_val;
            const issueEl = document.getElementById(`issue-${rowIdx}`);
            if (issueEl && issueEl.value === '1') {
                issueEl.value = '2';
                onIssueChange(rowIdx);
            }
            const tambon = bareTambonName(rec.tambon || document.getElementById('tambon')?.value || geoState.tambonName || '');
            rec.placeParts = tambon ? [{ tambon, moos: [] }] : [];
            syncRecordPlaceFromParts(rec);
            renderPlaceBuilder(rowIdx);
        });
        return;
    }

    const parts = ensurePlaceParts(rec);
    if (!parts.length) {
        parts.push({
            tambon: bareTambonName(geoState.tambonName || document.getElementById('tambon')?.value || ''),
            moos: normalizeMoos(geoState.moos || [])
        });
        rec.placeParts = parts;
    }

    const amphoeLabel = geoState.amphoeName
        ? `อำเภอ${geoState.amphoeName}`
        : 'อำเภอที่เลือกด้านบน';
    const tambonNames = getAmphoeTambonNames();
    const tambonCount = tambonNames.length;

    let html = `<div class="place-amphoe-hint" title="${escapeAttr(tambonNames.join(', '))}">${amphoeLabel}${tambonCount ? ` · ${tambonCount} ตำบล` : ''}</div>`;
    if (!tambonCount) {
        html += `<div class="place-amphoe-warn">ยังไม่มีรายการตำบล — เลือกอำเภอด้านบนหรือพรีเซ็ตสีดา</div>`;
    }

    parts.forEach((part, pIdx) => {
        const mooChips = (part.moos || []).map(m =>
            `<span class="chip"><span>ม.${m}</span><button type="button" class="chip-remove" data-part="${pIdx}" data-moo="${escapeAttr(m)}" aria-label="ลบ">×</button></span>`
        ).join('');
        const segText = formatMooTambonSegment(part.moos, part.tambon) || '—';
        html += `<div class="place-segment" data-part="${pIdx}">
            <div class="place-segment-row">
                <label class="place-seg-label">ตำบล</label>
                <select class="cell-input cell-select place-tambon-select" data-part="${pIdx}" title="ตำบลใน${amphoeLabel}">
                    ${buildTambonSelectOptions(part.tambon, parts, pIdx)}
                </select>
                <button type="button" class="btn-place-moo" data-part="${pIdx}">เลือกหมู่…</button>
                ${parts.length > 1 ? `<button type="button" class="btn-place-remove" data-part="${pIdx}" title="ลบตำบลนี้">ลบ</button>` : ''}
            </div>
            <div class="chip-row place-moo-chips" data-part="${pIdx}">${mooChips || '<span class="field-hint-inline">ยังไม่เลือกหมู่</span>'}</div>
            <div class="multi-select place-moo-picker" data-part="${pIdx}">
                <div class="multi-select-panel place-moo-panel" data-part="${pIdx}" hidden></div>
            </div>
            <div class="place-seg-preview" title="${escapeAttr(segText)}">${escapeAttr(segText)}</div>
        </div>`;
    });
    const coverAll = isCoveringAllAmphoeTambons(rec);
    html += `<div class="place-builder-actions">
        <button type="button" class="btn-place-add" id="place-add-${rowIdx}" ${tambonCount ? '' : 'disabled'} title="เพิ่มตำบลอื่นในอำเภอ">+ ตำบล</button>
        <button type="button" class="btn-place-add-all" id="place-add-all-${rowIdx}" ${tambonCount ? '' : 'disabled'} title="ใส่ทุกตำบลในอำเภอ (ไม่สุ่มหมู่)">+ ทุกตำบล</button>
        <button type="button" class="btn-place-random-moo" id="place-random-moo-${rowIdx}" ${coverAll || !tambonCount ? 'disabled' : ''} title="สุ่ม 2–4 หมู่ จากหมู่บ้านจริงของตำบลที่รับผิดชอบ">สุ่มหมู่ 2–4</button>
        ${isMultiTambonRole() ? `<label class="row-use-all-tambons multi-tambon-only" title="ขยายส่งทีละตำบลในหัวแผน T&V">
            <input type="checkbox" id="use-all-tambons-${rowIdx}" ${rec.useAllTambons ? 'checked' : ''} onchange="syncRowUseAllTambonsUi(${rowIdx})">
            ขยายทีละตำบล
        </label>` : ''}
    </div>`;
    if (coverAll) {
        html += `<div class="place-amphoe-hint">ทุกตำบล — ไม่สุ่มหมู่</div>`;
    }
    wrap.innerHTML = html;

    const finalLoc = syncRecordPlaceFromParts(rec);
    if (preview) {
        preview.textContent = finalLoc || '(ยังไม่มีสถานที่)';
        preview.title = finalLoc || '';
    }

    wrap.querySelectorAll('.place-tambon-select').forEach(sel => {
        sel.addEventListener('change', async () => {
            const pIdx = parseInt(sel.dataset.part, 10);
            const tb = bareTambonName(sel.value);
            rec.placeParts[pIdx].tambon = tb;
            rec.coverAllTambons = false;
            // Keep only moos that exist in the newly selected tambon
            const pool = new Set(await getMoosForTambonName(tb));
            if (pool.size) {
                rec.placeParts[pIdx].moos = normalizeMoos(
                    (rec.placeParts[pIdx].moos || []).filter(m => pool.has(String(m)))
                );
            } else {
                rec.placeParts[pIdx].moos = [];
            }
            syncRecordPlaceFromParts(rec);
            const hidden = document.getElementById(`tambon-${rowIdx}`);
            if (hidden) hidden.value = rec.placeParts[0]?.tambon || '';
            renderPlaceBuilder(rowIdx);
        });
    });
    wrap.querySelectorAll('.chip-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            const pIdx = parseInt(btn.dataset.part, 10);
            const moo = btn.dataset.moo;
            rec.placeParts[pIdx].moos = normalizeMoos((rec.placeParts[pIdx].moos || []).filter(m => m !== moo));
            syncRecordPlaceFromParts(rec);
            renderPlaceBuilder(rowIdx);
        });
    });
        wrap.querySelectorAll('.btn-place-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            const pIdx = parseInt(btn.dataset.part, 10);
            rec.placeParts.splice(pIdx, 1);
            rec.coverAllTambons = false;
            syncRecordPlaceFromParts(rec);
            renderPlaceBuilder(rowIdx);
        });
    });
    wrap.querySelectorAll('.btn-place-moo').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const pIdx = parseInt(btn.dataset.part, 10);
            togglePlaceMooPanel(rowIdx, pIdx);
        });
    });
    document.getElementById(`place-add-${rowIdx}`)?.addEventListener('click', () => {
        const next = nextUnusedAmphoeTambon(rec.placeParts);
        if (!next) {
            addLog('warning', 'เลือกครบทุกตำบลในอำเภอแล้ว หรือยังไม่ได้เลือกอำเภอด้านบน');
            return;
        }
        rec.coverAllTambons = false;
        rec.placeParts.push({ tambon: next, moos: [] });
        syncRecordPlaceFromParts(rec);
        renderPlaceBuilder(rowIdx);
        addLog('info', `เพิ่มตำบล${next} ในสถานที่แล้ว`);
    });
    document.getElementById(`place-add-all-${rowIdx}`)?.addEventListener('click', () => {
        const all = getAmphoeTambonNames();
        if (!all.length) {
            addLog('warning', 'กรุณาเลือกอำเภอด้านบนก่อน');
            return;
        }
        // ไปทุกตำบล: ใส่ชื่อตำบลอย่างเดียว ไม่สุ่ม/ไม่คัดลอกหมู่
        rec.coverAllTambons = true;
        rec.placeParts = all.map(t => ({ tambon: t, moos: [] }));
        syncRecordPlaceFromParts(rec);
        renderPlaceBuilder(rowIdx);
        addLog('info', `ใส่ทุกตำบลในอำเภอแล้ว (${all.length} ตำบล) — ไม่สุ่มหมู่`);
    });
    document.getElementById(`place-random-moo-${rowIdx}`)?.addEventListener('click', async () => {
        const result = await randomizeMoosForResponsibleTambons(rowIdx);
        if (!result.ok) {
            addLog('warning', result.reason);
            return;
        }
        addLog('success', `สุ่มหมู่จากข้อมูลจริงแล้ว — ${result.details.join(' | ')}`);
        if (result.skipped?.length) addLog('warning', result.skipped.join(' · '));
        renderPlaceBuilder(rowIdx);
    });
}

async function rebuildPlaceMooPanel(rowIdx, partIdx) {
    const panel = document.querySelector(`#place-builder-${rowIdx} .place-moo-panel[data-part="${partIdx}"]`);
    const rec = allRecords[rowIdx];
    if (!panel || !rec) return;
    const part = ensurePlaceParts(rec)[partIdx];
    if (!part) return;
    const tb = bareTambonName(part.tambon);
    const pool = tb ? await getMoosForTambonName(tb) : [];
    const selected = new Set(part.moos || []);
    // Drop invalid moos that are not in this tambon
    if (pool.length) {
        const valid = normalizeMoos((part.moos || []).filter(m => pool.includes(String(m))));
        if (valid.length !== (part.moos || []).length) {
            part.moos = valid;
            syncRecordPlaceFromParts(rec);
        }
    }
    let html = pool.length
        ? `<div style="padding:0.25rem 0.45rem;font-size:0.72rem;color:var(--text-muted);">หมู่ในตำบล${tb} (${pool.length} หมู่)</div>`
        : `<div style="padding:0.25rem 0.45rem;font-size:0.72rem;color:#fbbf24;">ยังไม่มีข้อมูลหมู่บ้านของตำบลนี้</div>`;
    pool.forEach(v => {
        html += `<label class="multi-select-option"><input type="checkbox" value="${escapeAttr(v)}" ${selected.has(v) ? 'checked' : ''}> ม.${escapeAttr(v)}</label>`;
    });
    html += `<div class="multi-select-actions">
        <button type="button" data-act="all" ${pool.length ? '' : 'disabled'}>ทุกหมู่ในตำบล</button>
        <button type="button" data-act="clear">ล้าง</button>
    </div>`;
    panel.innerHTML = html;
    panel.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', () => {
            if (cb.checked) {
                if (!part.moos.includes(cb.value)) part.moos.push(cb.value);
            } else {
                part.moos = part.moos.filter(x => x !== cb.value);
            }
            part.moos = normalizeMoos(part.moos);
            syncRecordPlaceFromParts(rec);
            renderPlaceBuilder(rowIdx).then(() => {
                const p2 = document.querySelector(`#place-builder-${rowIdx} .place-moo-panel[data-part="${partIdx}"]`);
                if (p2) {
                    rebuildPlaceMooPanel(rowIdx, partIdx).then(() => { p2.hidden = false; });
                }
            });
        });
    });
    panel.querySelector('[data-act="all"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        part.moos = normalizeMoos(pool);
        syncRecordPlaceFromParts(rec);
        renderPlaceBuilder(rowIdx);
    });
    panel.querySelector('[data-act="clear"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        part.moos = [];
        syncRecordPlaceFromParts(rec);
        renderPlaceBuilder(rowIdx);
    });
}

async function togglePlaceMooPanel(rowIdx, partIdx) {
    closeAllMultiPanels();
    const panel = document.querySelector(`#place-builder-${rowIdx} .place-moo-panel[data-part="${partIdx}"]`);
    if (!panel) return;
    panel.hidden = false;
    panel.innerHTML = '<div style="padding:0.35rem;font-size:0.75rem;color:var(--text-muted);">กำลังโหลดหมู่บ้าน...</div>';
    await rebuildPlaceMooPanel(rowIdx, partIdx);
    panel.hidden = false;
}

function applyRowLocationFromGeo(rowIdx) {
    const rec = allRecords[rowIdx];
    if (!rec) return;
    const tambon = bareTambonName(
        document.getElementById(`tambon-${rowIdx}`)?.value || rec.tambon || geoState.tambonName || ''
    );
    rec.tambon = tambon;
    const office = document.getElementById('office-name')?.value.trim() || '';
    const derived = formatLocationString({
        villages: rec.villages,
        moos: rec.moos,
        tambon,
        office
    }) || formatTambonPart(tambon) || office;
    if (!derived) return;
    rec.location = derived;
    const sel = document.getElementById(`location-select-${rowIdx}`);
    const customInput = document.getElementById(`location-custom-${rowIdx}`);
    if (sel && customInput) {
        const exact = Array.from(sel.options).find(o => o.value === derived);
        if (exact) {
            sel.value = derived;
            customInput.style.display = 'none';
            customInput.value = derived;
        } else {
            sel.value = '_custom';
            customInput.value = derived;
            customInput.style.display = 'block';
        }
    }
    const preview = document.getElementById(`location-preview-${rowIdx}`);
    if (preview) preview.textContent = derived;
    syncSelectFulltext(`location-select-${rowIdx}`);
}

async function syncRowTambonLocation(rowIdx, opts = {}) {
    const rec = allRecords[rowIdx];
    if (!rec) return;
    const input = document.getElementById(`tambon-${rowIdx}`);
    const raw = (input?.value || rec.tambon || geoState.tambonName || '').trim();
    const meta = resolveTambonMeta(raw);
    const tambon = meta.name_th || bareTambonName(raw);
    const oldTambon = bareTambonName(rec.tambon || '');
    rec.tambon = tambon;
    if (input && meta.name_th && bareTambonName(input.value) !== bareTambonName(meta.name_th)) {
        // keep display as bare or with prefix consistently — use bare for T&V portal
        input.value = tambon;
        input.title = formatTambonPart(tambon);
    }
    rec.tambonCode = meta.code || '';
    const villages = await loadVillagesForTambonName(tambon);
    rec._villagesList = villages;

    // Drop villages that are not in this tambon
    const villageNames = new Set(villages.map(v => v.name_th));
    if (rec.villages?.length) {
        rec.villages = rec.villages.filter(v => villageNames.has(v));
    }

    const force = !!opts.force;
    const mismatched = !locationMatchesTambon(rec.location, tambon);
    if (force || mismatched || oldTambon !== bareTambonName(tambon) || !(rec.moos || []).length && !(rec.villages || []).length) {
        if (oldTambon && oldTambon !== bareTambonName(tambon) && rec.location) {
            rec.location = relocateForTambon(rec.location, oldTambon, tambon, rec.moos, rec.villages);
        }
        await initLocationSelect(rowIdx, rec.location, villages);
        applyRowLocationFromGeo(rowIdx);
    } else {
        await initLocationSelect(rowIdx, rec.location, villages);
    }
    renderRowMooChips(rowIdx);
    const panel = document.getElementById(`moo-panel-${rowIdx}`);
    if (panel && !panel.hidden) rebuildRowMooPanel(rowIdx);
}

const _rowTambonTimers = {};
function onRowTambonChanged(rowIdx) {
    clearTimeout(_rowTambonTimers[rowIdx]);
    _rowTambonTimers[rowIdx] = setTimeout(() => {
        syncRowTambonLocation(rowIdx, { force: true });
    }, 180);
}

function rebuildRowMooPanel(rowIdx) {
    const panel = document.getElementById(`moo-panel-${rowIdx}`);
    if (!panel) return;
    const rec = ensureRowGeoFields(allRecords[rowIdx] || {});
    const selected = new Set(rec.moos || []);
    const villages = rec._villagesList || geoState.villages || [];
    const pool = moosFromVillages(villages);
    if (pool.length) {
        rec.moos = normalizeMoos((rec.moos || []).filter(m => pool.includes(String(m))));
    }
    const villageOpts = villages.map(v => {
        const name = v.name_th || '';
        const checked = (rec.villages || []).includes(name) ? 'checked' : '';
        const label = v.moo ? `${name} (ม.${v.moo})` : name;
        return `<label class="multi-select-option"><input type="checkbox" data-kind="village" value="${escapeAttr(name)}" data-moo="${escapeAttr(v.moo || '')}" ${checked}> ${escapeAttr(label)}</label>`;
    }).join('');
    let html = pool.length
        ? `<div style="padding:0.25rem 0.45rem;font-size:0.72rem;color:var(--text-muted);">หมู่ในตำบล (${pool.length} หมู่)</div>`
        : `<div style="padding:0.25rem 0.45rem;font-size:0.72rem;color:var(--text-muted);">ยังไม่มีข้อมูลหมู่บ้าน</div>`;
    pool.forEach(v => {
        html += `<label class="multi-select-option"><input type="checkbox" data-kind="moo" value="${escapeAttr(v)}" ${selected.has(v) ? 'checked' : ''}> ม.${escapeAttr(v)}</label>`;
    });
    if (villageOpts) {
        html += '<div style="padding:0.35rem 0.45rem 0.15rem;font-size:0.72rem;color:var(--text-muted);border-top:1px solid rgba(148,163,184,0.2);margin-top:0.2rem;">หมู่บ้าน</div>';
        html += villageOpts;
    }
    html += `<div class="multi-select-actions">
        <button type="button" data-act="all" ${pool.length ? '' : 'disabled'}>ทุกหมู่ในตำบล</button>
        <button type="button" data-act="clear">ล้าง</button>
    </div>`;
    panel.innerHTML = html;

    panel.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', () => {
            const kind = cb.dataset.kind;
            if (kind === 'moo') {
                if (cb.checked) {
                    if (!rec.moos.includes(cb.value)) rec.moos.push(cb.value);
                } else {
                    rec.moos = rec.moos.filter(x => x !== cb.value);
                }
                rec.moos = normalizeMoos(rec.moos);
            } else {
                if (cb.checked) {
                    if (!rec.villages.includes(cb.value)) rec.villages.push(cb.value);
                    const moo = cb.dataset.moo || '';
                    if (moo && !rec.moos.includes(moo)) rec.moos.push(moo);
                    rec.moos = normalizeMoos(rec.moos);
                } else {
                    rec.villages = rec.villages.filter(x => x !== cb.value);
                }
                rec.villages = normalizeVillages(rec.villages);
            }
            renderRowMooChips(rowIdx);
            applyRowLocationFromGeo(rowIdx);
            rebuildRowMooPanel(rowIdx);
        });
    });
    panel.querySelector('[data-act="all"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        rec.moos = normalizeMoos(pool);
        renderRowMooChips(rowIdx);
        applyRowLocationFromGeo(rowIdx);
        rebuildRowMooPanel(rowIdx);
    });
    panel.querySelector('[data-act="clear"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        rec.moos = [];
        rec.villages = [];
        renderRowMooChips(rowIdx);
        applyRowLocationFromGeo(rowIdx);
        rebuildRowMooPanel(rowIdx);
    });
}

function renderRowMooChips(rowIdx) {
    const rec = ensureRowGeoFields(allRecords[rowIdx] || {});
    const chips = [];
    (rec.moos || []).forEach(m => chips.push({ kind: 'moo', value: m, label: `ม.${m}` }));
    (rec.villages || []).forEach(v => chips.push({ kind: 'village', value: v, label: v }));
    renderChipRow(
        document.getElementById(`moo-chips-${rowIdx}`),
        chips,
        item => item.label,
        item => {
            if (item.kind === 'moo') {
                rec.moos = rec.moos.filter(x => x !== item.value);
            } else {
                rec.villages = rec.villages.filter(x => x !== item.value);
            }
            renderRowMooChips(rowIdx);
            applyRowLocationFromGeo(rowIdx);
            rebuildRowMooPanel(rowIdx);
        }
    );
    const toggle = document.getElementById(`moo-toggle-${rowIdx}`);
    if (toggle) {
        const n = (rec.moos || []).length + (rec.villages || []).length;
        toggle.textContent = n ? `หมู่/หมู่บ้าน (${n})` : 'เลือกหมู่...';
    }
}

async function toggleRowMooPanel(rowIdx) {
    const panel = document.getElementById(`moo-panel-${rowIdx}`);
    const toggle = document.getElementById(`moo-toggle-${rowIdx}`);
    if (!panel || !toggle) return;
    const willOpen = panel.hidden;
    closeAllMultiPanels();
    if (willOpen) {
        const rec = allRecords[rowIdx];
        const tambon = rec?.tambon || document.getElementById(`tambon-${rowIdx}`)?.value || geoState.tambonName;
        rec._villagesList = await loadVillagesForTambonName(tambon);
        rebuildRowMooPanel(rowIdx);
        panel.hidden = false;
        toggle.setAttribute('aria-expanded', 'true');
    }
}

function handleDrop(e) {
    e.preventDefault();
    const dropZone = document.getElementById('drop-zone');
    dropZone.classList.remove('file-selected');
    if (e.dataTransfer.files.length > 0) {
        selectedFile = e.dataTransfer.files[0];
        showFileName(selectedFile.name);
    }
}

function handleFileSelect(e) {
    if (e.target.files.length > 0) {
        selectedFile = e.target.files[0];
        showFileName(selectedFile.name);
    }
}

function showFileName(name) {
    const display = document.getElementById('file-name-display');
    const placeholder = document.getElementById('upload-placeholder');
    const dropZone = document.getElementById('drop-zone');
    display.textContent = `✓ เลือกไฟล์แล้ว: ${name}`;
    display.style.display = 'block';
    placeholder.style.display = 'none';
    dropZone.classList.add('file-selected');
    addLog("info", `ไฟล์พร้อมอัปโหลด: ${name}`);
}

function uploadExcelFile() {
    const tbs = [...getResponsibleTambonSet()];
    if (!geoState.setupConfirmed) {
        if ((geoState.amphoeCode || geoState.amphoeName) && tbs.length > 0) {
            confirmResponsibilitySetup();
        } else {
            alert('กรุณาเลือกตำบลที่รับผิดชอบในส่วน "พื้นที่รับผิดชอบ" ด้านบนก่อนอัปโหลด Excel');
            document.getElementById('setup-section')?.scrollIntoView({ behavior: 'smooth' });
            return;
        }
    }
    if (!selectedFile) {
        alert("กรุณาเลือกหรือวางไฟล์ Excel แผนงานก่อนครับ");
        return;
    }
    const formData = new FormData();
    formData.append('file', selectedFile);
    const uploadBtn = document.getElementById('upload-btn');
    uploadBtn.disabled = true;
    uploadBtn.textContent = 'กำลังส่งไปเซิร์ฟเวอร์...';

    fetch('/api/upload', { method: 'POST', body: formData })
    .then(res => res.json())
    .then(data => {
        uploadBtn.disabled = false;
        uploadBtn.textContent = '🚀 วิเคราะห์และโหลดตาราง';
        if (data.success) {
            tempFilename = data.temp_filename;
            addLog("success", `วิเคราะห์สำเร็จ! พบแผ่นงานทั้งหมด: ${data.sheets.join(', ')}`);
            const sheetSelect = document.getElementById('sheet-select');
            sheetSelect.innerHTML = '';
            data.sheets.forEach(sh => {
                const opt = document.createElement('option');
                opt.value = sh;
                opt.textContent = sh;
                sheetSelect.appendChild(opt);
            });
            if (data.sheets.length > 0) loadRecords(data.sheets[0]);
        } else {
            addLog("error", `การวิเคราะห์ไฟล์ล้มเหลว: ${data.error}`);
            alert(`วิเคราะห์ล้มเหลว: ${data.error}`);
        }
    })
    .catch(err => {
        uploadBtn.disabled = false;
        uploadBtn.textContent = '🚀 วิเคราะห์และโหลดตาราง';
        addLog("error", `เกิดข้อผิดพลาดในการอัปโหลด: ${err}`);
    });
}

function fetchSheets() {
    const sheetSelect = document.getElementById('sheet-select');
    fetch(`/api/sheets?temp_filename=${encodeURIComponent(tempFilename)}`)
        .then(res => res.json())
        .then(data => {
            if (data.success && data.sheets && data.sheets.length > 0) {
                sheetSelect.innerHTML = '';
                data.sheets.forEach(sh => {
                    const opt = document.createElement('option');
                    opt.value = sh;
                    opt.textContent = sh;
                    sheetSelect.appendChild(opt);
                });
                loadRecords(data.sheets[0]);
            } else {
                addLog("info", "รอผู้ใช้อัปโหลดไฟล์ Excel เริ่มต้น...");
            }
        })
        .catch(err => addLog("error", `โหลดข้อมูลชีตล้มเหลว: ${err}`));
}

function onSheetChange() {
    loadRecords(document.getElementById('sheet-select').value);
}

function loadRecords(sheetName) {
    // Loading an Excel sheet switches month authority back to the sheet selector.
    currentPlanMonth = '';
    const rowCountEl = document.getElementById('row-count');
    rowCountEl.textContent = 'กำลังโหลดตาราง...';
    const apiKey = (document.getElementById('gemini-api-key')?.value || '').trim();
    const office = document.getElementById('office-name').value.trim();
    const tambon = document.getElementById('tambon').value.trim();
    const qs = new URLSearchParams({
        sheet: sheetName,
        temp_filename: tempFilename,
        office_name: office,
        tambon: tambon
    });
    fetch(`/api/records?${qs}`, { headers: { 'X-Gemini-API-Key': apiKey } })
        .then(res => res.json())
        .then(async data => {
            if (data.success) {
                allRecords = data.records;
                const defaultTb = tambon;
                allRecords.forEach(r => {
                    if (!r.tambon) r.tambon = defaultTb;
                });
                await applyPlaceAfterExcelLoad(allRecords);
                allRecords.forEach((r, i) => {
                    r.id = i + 1;
                    ensureRowGeoFields(r);
                });
                renderTable(allRecords);
                updateQuickStats();
                rowCountEl.textContent = `โหลดเสร็จสิ้น: ${allRecords.length} แถว (แผ่นงาน: ${sheetName})`;
                addLog("success", `โหลดข้อมูลแผ่นงาน '${sheetName}' เรียบร้อยแล้ว`);
            } else {
                rowCountEl.textContent = 'โหลดล้มเหลว';
                addLog("error", `ดึงข้อมูลล้มเหลว: ${data.error}`);
            }
        })
        .catch(err => {
            rowCountEl.textContent = 'ข้อผิดพลาดการเชื่อมต่อ';
            addLog("error", `การเชื่อมต่อพอร์ตผิดพลาด: ${err}`);
        });
}

function syncRowUseAllTambonsUi(rowIdx) {
    const cb = document.getElementById(`use-all-tambons-${rowIdx}`);
    const rec = allRecords[rowIdx];
    if (!cb || !rec) return;
    rec.useAllTambons = !!cb.checked;
}

function toggleAllRowsUseAllTambons(on) {
    if (!isMultiTambonRole()) return;
    if (on && !normalizeTambons(geoState.selectedTambons).length) {
        selectAllTambonsInAmphoe().then(() => {
            allRecords.forEach((rec, idx) => {
                rec.useAllTambons = true;
                const cb = document.getElementById(`use-all-tambons-${idx}`);
                if (cb) cb.checked = true;
                syncRowUseAllTambonsUi(idx);
            });
            addLog('info', `เปิด «ใช้ทุกตำบล» ทั้ง ${allRecords.length} แถว`);
        });
        return;
    }
    allRecords.forEach((rec, idx) => {
        rec.useAllTambons = !!on;
        const cb = document.getElementById(`use-all-tambons-${idx}`);
        if (cb) cb.checked = !!on;
        syncRowUseAllTambonsUi(idx);
    });
    addLog('info', on
        ? `เปิด «ใช้ทุกตำบล» ทั้ง ${allRecords.length} แถว`
        : `ยกเลิก «ใช้ทุกตำบล» ทั้งตาราง`);
}

function relocateForTambon(baseLocation, oldTambon, newTambon, moos, villages) {
    const office = document.getElementById('office-name')?.value.trim() || '';
    if ((moos && moos.length) || (villages && villages.length)) {
        return formatLocationString({ villages: villages || [], moos: moos || [], tambon: newTambon, office });
    }
    const newPart = formatTambonPart(newTambon);
    const oldPart = formatTambonPart(oldTambon);
    let loc = (baseLocation || '').trim();
    if (oldPart && loc.includes(oldPart)) {
        return loc.split(oldPart).join(newPart);
    }
    if (/ตำบล[^\s,]+/.test(loc) && newPart) {
        return loc.replace(/ตำบล[^\s,]+/g, newPart);
    }
    if (newPart) return loc ? `${loc} ${newPart}` : newPart;
    return loc;
}

function renderTable(records) {
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';
    buildDescPresets(records);
    const multi = isMultiTambonRole();

    records.forEach((rec, idx) => {
        const tr = document.createElement('tr');
        tr.id = `row-${idx}`;
        let issueOptionsHtml = '';
        for (const [val, label] of Object.entries(issueOptions)) {
            const selected = val === String(rec.issue_val) ? 'selected' : '';
            issueOptionsHtml += `<option value="${val}" ${selected}>${label}</option>`;
        }
        const tambonVal = rec.tambon || geoState.tambonName || '';
        const useAll = !!rec.useAllTambons;
        tr.innerHTML = `
            <td class="text-center" style="font-weight: 700; color: var(--text-muted);">${rec.id}</td>
            <td class="row-date-col">
                <input type="text" class="cell-input" id="date-${idx}" value="${rec.date || ''}" style="text-align: center;" title="${rec.date || ''}" onchange="onRowDateChanged(${idx})">
            </td>
            <td class="row-issue-col">
                <div class="cell-stack">
                    <select class="cell-input cell-select" id="issue-${idx}" onchange="onIssueChange(${idx}); syncSelectFulltext('issue-${idx}')">
                        ${issueOptionsHtml}
                    </select>
                    <div class="cell-fulltext" id="issue-${idx}-fulltext"></div>
                </div>
            </td>
            <td class="row-activity-col">
                <div class="cell-stack">
                    <select class="cell-input cell-select" id="activity-select-${idx}" onchange="syncSelectFulltext('activity-select-${idx}')"></select>
                    <div class="cell-fulltext" id="activity-select-${idx}-fulltext"></div>
                </div>
            </td>
            <td class="row-details-col">
                <div class="desc-combo">
                    <select class="cell-input cell-select" id="desc-select-${idx}" onchange="onDescChange(${idx}); syncSelectFulltext('desc-select-${idx}')"></select>
                    <div class="cell-fulltext" id="desc-select-${idx}-fulltext"></div>
                    <textarea class="cell-input" id="activity-${idx}" style="min-height: 64px; resize: vertical; display: none;" placeholder="พิมพ์รายละเอียด...">${rec.activity || ''}</textarea>
                </div>
            </td>
            <td class="row-location-col">
                <div class="place-builder" id="place-builder-${idx}"></div>
                <div class="location-preview place-final-preview" id="location-preview-${idx}" title="ข้อความที่จะกรอกใน PD_PLACE"></div>
                <input type="hidden" id="tambon-${idx}" value="${bareTambonName(tambonVal)}">
            </td>
            <td class="row-target-col text-center">
                <input type="number" class="cell-input text-center" id="target-${idx}" value="${rec.target_num || 0}">
            </td>
            <td class="row-status-col text-center" id="status-${idx}">
                <span class="status-badge badge-ready">พร้อมกรอก</span>
            </td>
            <td class="row-action-col text-center">
                <button class="btn-delete-row" onclick="deleteRow(${idx})" title="ลบแถวนี้">🗑️</button>
            </td>
        `;
        tbody.appendChild(tr);
        ensureRowGeoFields(rec);
        if (!isOfficeWorkRecord(rec) && !rec.placeParts?.length) {
            rec.placeParts = [{
                tambon: bareTambonName(tambonVal || geoState.tambonName || ''),
                moos: normalizeMoos(rec.moos || geoState.moos || [])
            }];
        }
        updateActivitySelect(idx, rec.issue_val, rec.activity_val);
        initDescSelect(idx, rec.activity);
        syncSelectFulltext(`issue-${idx}`);
        syncSelectFulltext(`activity-select-${idx}`);
        syncSelectFulltext(`desc-select-${idx}`);
        void renderPlaceBuilder(idx);
    });
}

function syncSelectFulltext(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const box = document.getElementById(`${selectId}-fulltext`);
    const opt = sel.options[sel.selectedIndex];
    let text = '';
    if (opt) {
        text = (opt.value && opt.value !== '_custom' && opt.value.length > (opt.textContent || '').length)
            ? opt.value
            : (opt.textContent || opt.label || opt.value || '');
        if (opt.value === '_custom') {
            const rowMatch = selectId.match(/(\d+)$/);
            if (rowMatch) {
                const idx = rowMatch[1];
                if (selectId.startsWith('desc-select-')) {
                    text = document.getElementById(`activity-${idx}`)?.value || 'กำหนดเอง';
                } else if (selectId.startsWith('location-select-')) {
                    text = document.getElementById(`location-custom-${idx}`)?.value || 'กำหนดเอง';
                } else {
                    text = 'กำหนดเอง';
                }
            }
        }
    }
    sel.title = text;
    if (box) {
        box.textContent = text;
        box.hidden = !text;
    }
}

function updateActivitySelect(rowIdx, issueVal, selectedActivityVal) {
    const actSelect = document.getElementById(`activity-select-${rowIdx}`);
    actSelect.innerHTML = '';
    const options = activityOptions[issueVal] || [];
    options.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.value;
        option.textContent = opt.label;
        if (String(opt.value) === String(selectedActivityVal)) option.selected = true;
        actSelect.appendChild(option);
    });
    syncSelectFulltext(`activity-select-${rowIdx}`);
    syncSelectFulltext(`issue-${rowIdx}`);
}

function onIssueChange(rowIdx) {
    const issueVal = document.getElementById(`issue-${rowIdx}`).value;
    const defaultActivity = activityOptions[issueVal]?.[0]?.value || "999";
    updateActivitySelect(rowIdx, issueVal, defaultActivity);
    syncSelectFulltext(`issue-${rowIdx}`);
    const rec = allRecords[rowIdx];
    if (!rec) return;
    rec.issue_val = issueVal;
    // วันจันทร์บังคับประชุมสำนักงานตามปฏิทิน
    if (applyOfficeMeetingRulesToRecord(rec)) {
        syncOfficeMeetingRowUi(rowIdx);
        return;
    }
    if (String(issueVal) === '1') {
        rec.officeOnly = true;
        rec.placeParts = [];
        rec.moos = [];
        rec.location = getOfficePlaceName();
        void renderPlaceBuilder(rowIdx);
        const preview = document.getElementById(`location-preview-${rowIdx}`);
        if (preview) {
            preview.textContent = rec.location;
            preview.title = rec.location;
        }
        addLog('info', `แถว ${rec.id}: ประเด็นงานสำนักงาน → สถานที่ «${rec.location}» อย่างเดียว`);
    } else if (rec.officeOnly) {
        rec.officeOnly = false;
        const tambon = bareTambonName(rec.tambon || document.getElementById('tambon')?.value || geoState.tambonName || '');
        rec.placeParts = tambon ? [{ tambon, moos: [] }] : [];
        syncRecordPlaceFromParts(rec);
        void renderPlaceBuilder(rowIdx);
    }
}

function syncOfficeMeetingRowUi(rowIdx) {
    const rec = allRecords[rowIdx];
    if (!rec) return;
    const issueEl = document.getElementById(`issue-${rowIdx}`);
    if (issueEl) issueEl.value = rec.issue_val;
    updateActivitySelect(rowIdx, rec.issue_val, rec.activity_val);
    syncSelectFulltext(`issue-${rowIdx}`);
    syncSelectFulltext(`activity-select-${rowIdx}`);
    const targetEl = document.getElementById(`target-${rowIdx}`);
    if (targetEl && rec.target_num) targetEl.value = rec.target_num;
    const descSel = document.getElementById(`desc-select-${rowIdx}`);
    const actTa = document.getElementById(`activity-${rowIdx}`);
    if (actTa) actTa.value = rec.activity || '';
    if (descSel && rec.activity) {
        const hit = Array.from(descSel.options).find(o => o.value === rec.activity);
        if (hit) {
            descSel.value = rec.activity;
        } else {
            // keep custom text in textarea path if used
            initDescSelect(rowIdx, rec.activity);
        }
        syncSelectFulltext(`desc-select-${rowIdx}`);
    }
    void renderPlaceBuilder(rowIdx);
    const preview = document.getElementById(`location-preview-${rowIdx}`);
    if (preview) {
        preview.textContent = rec.location;
        preview.title = rec.location;
    }
}

function onRowDateChanged(rowIdx) {
    const rec = allRecords[rowIdx];
    const dateEl = document.getElementById(`date-${rowIdx}`);
    if (!rec || !dateEl) return;
    rec.date = dateEl.value.trim();
    if (applyOfficeMeetingRulesToRecord(rec)) {
        syncOfficeMeetingRowUi(rowIdx);
        const kind = rec.activity_val === '13' ? 'ประชุมประจำเดือน (DM)' : 'ประชุมประจำสัปดาห์ (WM)';
        addLog('info', `แถว ${rec.id}: วันจันทร์ → ${kind} ที่ «${rec.location}»`);
        return;
    }
    // เปลี่ยนจากจันทร์เป็นวันอื่น — ออกจากโหมดสำนักงานอัตโนมัติถ้าเคยถูกบังคับ
    if (rec.officeOnly && isOfficeOnlyLocation(rec.location)) {
        rec.officeOnly = false;
        const tambon = bareTambonName(rec.tambon || document.getElementById('tambon')?.value || geoState.tambonName || '');
        rec.placeParts = tambon ? [{ tambon, moos: [] }] : [];
        syncRecordPlaceFromParts(rec);
        void renderPlaceBuilder(rowIdx);
    }
}

async function initLocationSelect(rowIdx, currentLocation, villagesOverride) {
    const sel = document.getElementById(`location-select-${rowIdx}`);
    const customInput = document.getElementById(`location-custom-${rowIdx}`);
    if (!sel || !customInput) return;
    const rec = allRecords[rowIdx] || {};
    const tambon = bareTambonName(
        document.getElementById(`tambon-${rowIdx}`)?.value || rec.tambon || geoState.tambonName || ''
    );
    let villages = villagesOverride;
    if (!villages) {
        villages = rec._villagesList || await loadVillagesForTambonName(tambon);
        rec._villagesList = villages;
    }
    const presets = buildLocationPresetsForTambon(tambon, villages);
    sel.innerHTML = '';
    let matched = false;
    presets.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.value;
        option.textContent = opt.label;
        option.title = opt.label;
        if (opt.value !== '_custom' && opt.value === currentLocation) {
            option.selected = true;
            matched = true;
        }
        sel.appendChild(option);
    });
    if (!matched && currentLocation) {
        sel.value = '_custom';
        customInput.value = currentLocation;
        customInput.style.display = 'block';
    } else if (matched) {
        customInput.style.display = 'none';
        customInput.value = currentLocation || '';
    } else if (!currentLocation && tambon) {
        const tpart = formatTambonPart(tambon);
        const hit = Array.from(sel.options).find(o => o.value === tpart);
        if (hit) {
            sel.value = tpart;
            customInput.style.display = 'none';
            customInput.value = tpart;
            if (rec) rec.location = tpart;
        }
    }
    syncSelectFulltext(`location-select-${rowIdx}`);
    const preview = document.getElementById(`location-preview-${rowIdx}`);
    if (preview) preview.textContent = getLocationValue(rowIdx) || formatTambonPart(tambon);
}

function onLocationChange(rowIdx) {
    const sel = document.getElementById(`location-select-${rowIdx}`);
    const customInput = document.getElementById(`location-custom-${rowIdx}`);
    const rec = allRecords[rowIdx];
    const tambon = bareTambonName(
        document.getElementById(`tambon-${rowIdx}`)?.value || rec?.tambon || ''
    );
    if (sel.value === '_custom') {
        customInput.style.display = 'block';
        customInput.focus();
    } else {
        customInput.style.display = 'none';
        let val = sel.value;
        // Keep location tied to this row's tambon
        if (tambon && !locationMatchesTambon(val, tambon) && !val.includes('สนง') && !val.includes('สำนักงาน')) {
            val = relocateForTambon(val, bareTambonName(val.match(/ตำบล([^\s,]+)/)?.[1] || ''), tambon, rec?.moos, rec?.villages);
        }
        customInput.value = val;
        if (rec) {
            rec.location = val;
            rec.tambon = tambon;
            const parsed = parseMoosFromLocation(val);
            if (parsed.length) rec.moos = parsed;
            renderRowMooChips(rowIdx);
        }
    }
    const preview = document.getElementById(`location-preview-${rowIdx}`);
    if (preview) preview.textContent = getLocationValue(rowIdx);
    syncSelectFulltext(`location-select-${rowIdx}`);
}

function getLocationValue(rowIdx) {
    const rec = allRecords[rowIdx];
    if (rec) {
        ensurePlaceParts(rec);
        return syncRecordPlaceFromParts(rec);
    }
    const preview = document.getElementById(`location-preview-${rowIdx}`);
    return (preview?.textContent || '').trim();
}

let descPresets = [];

function buildDescPresets(records) {
    const unique = [];
    const seen = new Set();
    records.forEach(rec => {
        const text = (rec.activity || '').trim();
        if (text && !seen.has(text)) {
            seen.add(text);
            unique.push({ value: text, label: text });
        }
    });
    unique.push({ value: '_custom', label: '✏️ กำหนดเอง...' });
    descPresets = unique;
}

function initDescSelect(rowIdx, currentDesc) {
    const sel = document.getElementById(`desc-select-${rowIdx}`);
    const customArea = document.getElementById(`activity-${rowIdx}`);
    sel.innerHTML = '';
    let matched = false;
    descPresets.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.value;
        option.textContent = opt.label;
        option.title = opt.label;
        if (opt.value !== '_custom' && opt.value === currentDesc) {
            option.selected = true;
            matched = true;
        }
        sel.appendChild(option);
    });
    if (!matched && currentDesc) {
        sel.value = '_custom';
        customArea.value = currentDesc;
        customArea.style.display = 'block';
    }
    syncSelectFulltext(`desc-select-${rowIdx}`);
}

function onDescChange(rowIdx) {
    const sel = document.getElementById(`desc-select-${rowIdx}`);
    const customArea = document.getElementById(`activity-${rowIdx}`);
    if (sel.value === '_custom') {
        customArea.style.display = 'block';
        customArea.focus();
    } else {
        customArea.style.display = 'none';
        customArea.value = sel.value;
    }
    syncSelectFulltext(`desc-select-${rowIdx}`);
}

function getDescValue(rowIdx) {
    const sel = document.getElementById(`desc-select-${rowIdx}`);
    const customArea = document.getElementById(`activity-${rowIdx}`);
    if (sel.value === '_custom') return customArea.value;
    return sel.value;
}

function addLog(type, message) {
    const consoleLogs = document.getElementById('console-logs');
    const now = new Date();
    const timeStr = `[${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}]`;
    const entry = document.createElement('div');
    entry.className = 'log-line';
    let typeClass = 'entry-info';
    if (type === 'success') typeClass = 'entry-success';
    if (type === 'error') typeClass = 'entry-error';
    if (type === 'warning') typeClass = 'entry-warning';
    entry.innerHTML = `
        <span class="log-timestamp">${timeStr}</span>
        <span class="${typeClass}">${message}</span>
    `;
    consoleLogs.appendChild(entry);
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

function addNewRow() {
    const maxId = allRecords.reduce((max, r) => Math.max(max, r.id || 0), 0);
    const moos = normalizeMoos(geoState.moos);
    const tambon = bareTambonName(document.getElementById('tambon').value.trim() || geoState.tambonName || '');
    const placeParts = [{ tambon, moos: [...moos] }];
    const newRecord = {
        id: maxId + 1,
        date: '',
        activity: '',
        tool: '',
        placeParts,
        location: formatCombinedPlace(placeParts, document.getElementById('office-name')?.value.trim() || ''),
        moos: [...moos],
        villages: [],
        tambon,
        target_raw: '',
        target_num: 0,
        co_workers: '',
        issue_val: '2',
        activity_val: '999',
        other_text: '',
        useAllTambons: false
    };
    allRecords.push(newRecord);
    renderTable(allRecords);
    updateQuickStats();
    addLog('info', `เพิ่มแถวใหม่: แถวที่ ${newRecord.id}`);
}

function deleteRow(idx) {
    if (allRecords.length <= 1) {
        addLog('warning', 'ไม่สามารถลบแถวสุดท้ายได้');
        return;
    }
    const removed = allRecords.splice(idx, 1);
    renderTable(allRecords);
    updateQuickStats();
    addLog('info', `ลบแถวที่ ${removed[0]?.id || idx + 1} แล้ว`);
}

async function createBlankPlanOnWeb() {
    if (!geoState.setupConfirmed && !geoState.amphoeCode) {
        addLog('warning', 'กรุณายืนยันพื้นที่รับผิดชอบด้านบนก่อน');
        return;
    }
    const today = new Date();
    const currentMonth = today.getMonth() + 1;
    const currentYearBe = today.getFullYear() + 543;
    currentPlanMonth = `${today.getFullYear()}-${String(currentMonth).padStart(2, '0')}`;
    const responsible = [...getResponsibleTambonSet()];
    const primaryTambon = responsible[0] || bareTambonName(geoState.tambonName || '');

    allRecords = [];
    const sampleDates = [5, 8, 12, 18, 22];
    for (let i = 0; i < sampleDates.length; i++) {
        const day = sampleDates[i];
        const dayStr = String(day).padStart(2, '0');
        const monthStr = String(currentMonth).padStart(2, '0');
        const dateStr = `${dayStr}/${monthStr}/${currentYearBe}`;
        
        const targetCount = getRandomFieldTargetCount();
        allRecords.push({
            id: i + 1,
            date: dateStr,
            activity: 'ติดตามงานและเยี่ยมเยียนเกษตรกรในพื้นที่',
            tool: 'เยี่ยมเยียน',
            placeParts: primaryTambon ? [{ tambon: primaryTambon, moos: [] }] : [],
            location: primaryTambon ? formatTambonPart(primaryTambon) : '',
            moos: [],
            villages: [],
            tambon: primaryTambon,
            target_raw: `${targetCount} ราย`,
            target_num: targetCount,
            co_workers: '',
            issue_val: '2',
            activity_val: '15',
            other_text: '',
            useAllTambons: false
        });
    }

    await applyPlaceAfterExcelLoad(allRecords);
    renderTable(allRecords);
    updateQuickStats();
    addLog('success', 'สร้างตารางแผนงานบนเว็บเรียบร้อยแล้ว ท่านสามารถแก้ไข วันที่/กิจกรรม/สถานที่ ได้ในตารางทันที');
    document.querySelector('.table-responsive')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function generateMonthScheduleOnWeb() {
    if (!geoState.setupConfirmed && !geoState.amphoeCode) {
        addLog('warning', 'กรุณายืนยันพื้นที่รับผิดชอบด้านบนก่อน');
        return;
    }
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const yearBe = year + 543;
    const monthStr = String(month + 1).padStart(2, '0');
    currentPlanMonth = `${year}-${monthStr}`;
    const responsible = [...getResponsibleTambonSet()];
    const primaryTambon = responsible[0] || bareTambonName(geoState.tambonName || '');

    const daysInMonth = new Date(year, month + 1, 0).getDate();
    allRecords = [];
    let rowId = 1;

    for (let d = 1; d <= daysInMonth; d++) {
        const dt = new Date(year, month, d);
        const dayOfWeek = dt.getDay();
        if (dayOfWeek === 0 || dayOfWeek === 6) continue;

        const dayStr = String(d).padStart(2, '0');
        const dateStr = `${dayStr}/${monthStr}/${yearBe}`;

        if (dayOfWeek === 1) {
            const isFirstMonday = d <= 7;
            const staffCount = getOfficeStaffCount();
            allRecords.push({
                id: rowId++,
                date: dateStr,
                activity: isFirstMonday ? 'ประชุมสำนักงานเกษตรอำเภอประจำเดือน (DM)' : 'ประชุมสำนักงานเกษตรอำเภอประจำสัปดาห์ (WM)',
                tool: 'ประชุม',
                placeParts: [],
                location: getOfficePlaceName(),
                officeOnly: true,
                moos: [],
                villages: [],
                tambon: primaryTambon,
                target_raw: `${staffCount} ราย`,
                target_num: staffCount,
                co_workers: '',
                issue_val: '1',
                activity_val: isFirstMonday ? '13' : '14',
                other_text: '',
                useAllTambons: false
            });
        } else {
            const fieldTarget = getRandomFieldTargetCount();
            allRecords.push({
                id: rowId++,
                date: dateStr,
                activity: 'เยี่ยมเยียนส่งเสริมการเกษตรและถ่ายทอดความรู้',
                tool: 'เยี่ยมเยียน',
                placeParts: primaryTambon ? [{ tambon: primaryTambon, moos: [] }] : [],
                location: primaryTambon ? formatTambonPart(primaryTambon) : '',
                moos: [],
                villages: [],
                tambon: primaryTambon,
                target_raw: `${fieldTarget} ราย`,
                target_num: fieldTarget,
                co_workers: '',
                issue_val: '2',
                activity_val: '15',
                other_text: '',
                useAllTambons: false
            });
        }
    }

    await applyPlaceAfterExcelLoad(allRecords);
    renderTable(allRecords);
    updateQuickStats();
    addLog('success', `สร้างตารางแผนงานทั้งเดือน (${allRecords.length} วันทำงาน) เรียบร้อยแล้ว`);
    document.querySelector('.table-responsive')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function exportPlanToExcel() {
    if (!allRecords.length) {
        addLog('warning', 'ไม่มีข้อมูลในตารางสำหรับส่งออก');
        return;
    }
    let csv = "\uFEFFลำดับ,วันที่,ประเด็นงาน,กิจกรรมหลัก,รายละเอียดคำอธิบาย,สถานที่,จำนวนคน\n";
    allRecords.forEach((rec, idx) => {
        const d = rec.date || '';
        const issue = (issueOptions[rec.issue_val] || '').replace(/"/g, '""');
        const act = (rec.activity || '').replace(/"/g, '""');
        const loc = (rec.location || '').replace(/"/g, '""');
        const target = rec.target_num || 0;
        const other = (rec.other_text || '').replace(/"/g, '""');
        const detail = (other || act).replace(/"/g, '""');
        csv += `"${idx + 1}","${d}","${issue}","${act}","${detail}","${loc}","${target}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `แผนปฏิบัติงาน_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    addLog('success', 'ส่งออกไฟล์แผนงาน CSV/Excel เรียบร้อยแล้ว');
}

function clearPlanTable() {
    if (!allRecords.length) return;
    showConfirmModal(
        'ยืนยันการล้างตาราง',
        'คุณต้องการล้างรายการแผนงานทั้งหมดในตารางใช่หรือไม่?',
        () => {
            allRecords = [];
            currentPlanMonth = '';
            renderTable(allRecords);
            updateQuickStats();
            addLog('info', 'ล้างข้อมูลตารางเรียบร้อยแล้ว');
        }
    );
}

function updateQuickStats() {
    const statsContainer = document.getElementById('quick-stats');
    if (!statsContainer) return;
    const issueCount = {};
    allRecords.forEach(rec => {
        const issueLabel = issueOptions[rec.issue_val] || 'ไม่ระบุ';
        const shortLabel = issueLabel.split('(')[0].trim();
        issueCount[shortLabel] = (issueCount[shortLabel] || 0) + 1;
    });
    let html = '';
    for (const [label, count] of Object.entries(issueCount)) {
        html += `<span class="stat-chip"><span class="stat-count">${count}</span> ${label}</span>`;
    }
    statsContainer.innerHTML = html;
}

function showConfirmModal(title, message, onConfirm) {
    const overlay = document.getElementById('confirm-overlay');
    document.getElementById('confirm-title').innerHTML = title;
    document.getElementById('confirm-message').innerHTML = message;
    overlay.classList.add('active');
    document.getElementById('confirm-yes-btn').onclick = () => {
        overlay.classList.remove('active');
        onConfirm();
    };
    document.getElementById('confirm-no-btn').onclick = () => {
        overlay.classList.remove('active');
    };
}

function collectBaseRunRecords() {
    const defaultTambon = document.getElementById('tambon').value.trim();
    const expandList = getSelectedTambonsForExpand();
    const records = [];
    const uiIndexMap = [];
    let needsExpandList = false;

    allRecords.forEach((rec, idx) => {
        const issueVal = document.getElementById(`issue-${idx}`).value;
        const activityVal = document.getElementById(`activity-select-${idx}`).value;
        ensureRowGeoFields(rec);
        const parts = ensurePlaceParts(rec);
        const combinedPlace = syncRecordPlaceFromParts(rec);
        const primaryTambon = parts[0]?.tambon || bareTambonName(defaultTambon);
        const hiddenTambon = document.getElementById(`tambon-${idx}`);
        if (hiddenTambon) hiddenTambon.value = primaryTambon;

        const useAll = isMultiTambonRole() && (
            document.getElementById(`use-all-tambons-${idx}`)?.checked || !!rec.useAllTambons
        );
        const base = {
            id: rec.id,
            date: document.getElementById(`date-${idx}`).value,
            issue_val: issueVal,
            activity_val: activityVal,
            activity: getDescValue(idx),
            location: combinedPlace,
            placeParts: parts.map(p => ({ tambon: p.tambon, moos: [...(p.moos || [])] })),
            moos: normalizeMoos(parts[0]?.moos || []),
            villages: normalizeVillages(rec.villages),
            tambon: primaryTambon,
            target_num: parseInt(document.getElementById(`target-${idx}`).value) || 0,
            co_workers: '',
            other_text: issueVal === "2" && activityVal === "999" ? document.getElementById(`activity-${idx}`).value : ""
        };

        if (useAll) {
            const amphoeAll = getAmphoeTambonNames();
            const expandingAllAmphoe = !!rec.coverAllTambons
                || (parts.length > 1 && isCoveringAllAmphoeTambons(rec))
                || (expandList.length > 0 && amphoeAll.length > 0
                    && amphoeAll.every(t => expandList.includes(t)));
            // Expand by placeParts if multiple; else by selected-tambons list
            // ไปทุกตำบลในอำเภอ → ไม่ใส่หมู่
            if (parts.length > 1) {
                parts.forEach(p => {
                    const tb = bareTambonName(p.tambon);
                    if (!tb) return;
                    const moos = expandingAllAmphoe ? [] : normalizeMoos(p.moos);
                    records.push({
                        ...base,
                        tambon: tb,
                        moos,
                        placeParts: [{ tambon: tb, moos: [...moos] }],
                        location: formatMooTambonSegment(moos, tb)
                    });
                    uiIndexMap.push(idx);
                });
            } else {
                if (!expandList.length) {
                    needsExpandList = true;
                    return;
                }
                const templateMoos = expandingAllAmphoe
                    ? []
                    : normalizeMoos(parts[0]?.moos || base.moos);
                expandList.forEach(tb => {
                    records.push({
                        ...base,
                        tambon: tb,
                        moos: templateMoos,
                        placeParts: [{ tambon: tb, moos: [...templateMoos] }],
                        location: formatMooTambonSegment(templateMoos, tb)
                    });
                    uiIndexMap.push(idx);
                });
            }
        } else {
            // One T&V row: PD_PLACE = combined multi-tambon string
            records.push(base);
            uiIndexMap.push(idx);
        }
    });

    return { records, uiIndexMap, needsExpandList, expandList };
}

function startAutomation() {
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;
    const approverVal = document.getElementById('approver').value.trim();
    const tambonVal = document.getElementById('tambon').value.trim();

    let hasError = false;
    document.querySelectorAll('.input-error').forEach(el => el.classList.remove('input-error'));
    document.querySelectorAll('.validation-msg').forEach(el => el.classList.remove('visible'));

    if (!username) {
        document.getElementById('username').classList.add('input-error');
        const msg = document.getElementById('username-error');
        if (msg) { msg.textContent = 'กรุณากรอกชื่อผู้ใช้งานบัญชี T&V ของท่าน'; msg.classList.add('visible'); }
        hasError = true;
    }
    if (!password) {
        document.getElementById('password').classList.add('input-error');
        const msg = document.getElementById('password-error');
        if (msg) { msg.textContent = 'กรุณากรอกรหัสผ่านบัญชี T&V ของท่าน'; msg.classList.add('visible'); }
        hasError = true;
    }
    if (!approverVal) {
        document.getElementById('approver').classList.add('input-error');
        const msg = document.getElementById('approver-error');
        if (msg) { msg.textContent = 'กรุณากรอกชื่อผู้อนุมัติ'; msg.classList.add('visible'); }
        hasError = true;
    }
    if (!tambonVal && geoState.role === 'officer') {
        document.getElementById('tambon').classList.add('input-error');
        addLog('error', 'กรุณาเลือกตำบลที่รับผิดชอบ');
        hasError = true;
    }
    if (allRecords.length === 0) {
        addLog('error', 'ไม่มีข้อมูลในตาราง กรุณาอัปโหลดไฟล์ Excel หรือกด «สร้างตารางแผนงานบนเว็บโดยตรง» ก่อน');
        hasError = true;
    }

    const preview = collectBaseRunRecords();
    if (preview.needsExpandList) {
        addLog('error', 'มีแถวติ๊ก «ใช้ทุกตำบล» แต่ยังไม่มีรายการตำบล — กด «เลือกทุกตำบลในอำเภอ» ก่อน');
        hasError = true;
    }
    if (hasError) {
        addLog('error', 'กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วนก่อนเริ่มรัน');
        return;
    }

    const expandNote = preview.records.length !== allRecords.length
        ? `<br>หลังขยายตามตำบล: <strong>${preview.records.length}</strong> รายการ (จาก ${allRecords.length} แถว × ตำบลที่เลือก)`
        : '';

    const mode = document.querySelector('input[name="run_mode"]:checked').value;
    if (mode === 'submit') {
        showConfirmModal(
            '⚠️ ยืนยันการส่งข้อมูล',
            `คุณกำลังจะ <strong>บันทึกและส่งแผนปฏิบัติงาน</strong> จำนวน ${preview.records.length} รายการ ด้วยบัญชี T&V ของท่านเอง${expandNote}<br><br>ข้อมูลที่ส่งแล้วจะไม่สามารถแก้ไขได้ง่าย กรุณาตรวจสอบก่อนดำเนินการ`,
            () => { executeAutomation(); }
        );
        return;
    }
    executeAutomation();
}

function executeAutomation() {
    const startBtn = document.getElementById('start-btn');
    const logStatus = document.getElementById('log-status');
    const errorContainer = document.getElementById('error-container');
    let completionConfirmed = false;

    errorContainer.style.display = 'none';
    startBtn.disabled = true;
    logStatus.textContent = 'RUNNING';
    logStatus.style.color = 'var(--warning)';

    const built = collectBaseRunRecords();
    if (built.needsExpandList || !built.records.length) {
        addLog('error', built.needsExpandList
            ? 'มีแถวติ๊ก «ใช้ทุกตำบล» แต่ยังไม่มีรายการตำบล — กด «เลือกทุกตำบลในอำเภอ» ก่อน'
            : 'ไม่มีรายการที่จะรัน');
        startBtn.disabled = false;
        logStatus.textContent = 'IDLE';
        return;
    }

    const autoPlanMonth = currentPlanMonth || inferPlanMonthFromRecords();
    const runSheet = autoPlanMonth
        ? planMonthToSheetName(autoPlanMonth)
        : document.getElementById('sheet-select').value;
    const payload = {
        username: document.getElementById('username').value.trim(),
        password: document.getElementById('password').value,
        sheet: runSheet,
        tambon: document.getElementById('tambon').value.trim() || (built.expandList[0] || ''),
        role: geoState.role,
        office_name: document.getElementById('office-name').value.trim(),
        province_name: geoState.provinceName,
        amphoe_name: geoState.amphoeName,
        village_name: geoState.villageName,
        villages: normalizeVillages(geoState.selectedVillages),
        moo: geoState.moo,
        moos: normalizeMoos(geoState.moos),
        selected_tambons: built.expandList,
        approver: document.getElementById('approver').value.trim(),
        headless: document.getElementById('headless').checked,
        mode: document.querySelector('input[name="run_mode"]:checked').value,
        records: built.records
    };

    const uiIndexMap = built.uiIndexMap;
    const clearRunCredentials = createRunCredentialCleanup();
    allRecords.forEach((_, idx) => updateRowStatus(idx, 'ready'));

    let modeLabel = 'Dry-run (ทดสอบ)';
    if (payload.mode === 'draft') modeLabel = 'บันทึกชั่วคราว';
    if (payload.mode === 'submit') modeLabel = 'บันทึก & ส่งข้อมูล';
    const expandInfo = payload.records.length !== allRecords.length
        ? ` | ขยายเป็น ${payload.records.length} รายการตามตำบล`
        : '';
    addLog("info", `เริ่มรันด้วยบัญชีของท่าน | แผ่นงาน '${payload.sheet}' | โหมด: ${modeLabel}${expandInfo}`);
    if (payload.records.length !== allRecords.length) {
        addLog('info', `ใช้รายการตำบล ${normalizeTambons(geoState.selectedTambons).length || built.expandList.length} แห่งเป็นแหล่งขยายแถว «ใช้ทุกตำบล»`);
    }

    fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(async response => {
        if (!response.ok) {
            let errMsg = `HTTP ${response.status}`;
            try {
                const j = await response.json();
                errMsg = j.error || errMsg;
            } catch (_) {}
            throw new Error(errMsg);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        function processStream() {
            reader.read().then(({ done, value }) => {
                if (done) {
                    clearRunCredentials();
                    startBtn.disabled = false;
                    if (completionConfirmed) {
                        logStatus.textContent = 'FINISHED';
                        logStatus.style.color = 'var(--success)';
                    } else {
                        logStatus.textContent = 'UNKNOWN';
                        logStatus.style.color = 'var(--warning)';
                        addLog('warning', 'การเชื่อมต่อจบลงโดยไม่มีสัญญาณยืนยันผลลัพธ์จากเซิร์ฟเวอร์ กรุณาตรวจสอบพอร์ทัลก่อนเริ่มใหม่');
                    }
                    return;
                }
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();
                lines.forEach(line => {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === 'done') completionConfirmed = true;
                            handleSSEMessage(data, payload.records.length, uiIndexMap);
                        } catch (e) {
                            console.error(e);
                        }
                    }
                });
                processStream();
            }).catch(err => {
                clearRunCredentials();
                addLog("error", `การอ่านผลการทำงานผิดพลาด: ${err.message || err}`);
                startBtn.disabled = false;
                logStatus.textContent = 'ERROR';
                logStatus.style.color = 'var(--error)';
            });
        }
        processStream();
    })
    .catch(err => {
        clearRunCredentials();
        addLog("error", `การรันผิดพลาด: ${err.message || err}`);
        startBtn.disabled = false;
        logStatus.textContent = 'ERROR';
        logStatus.style.color = 'var(--error)';
    });
}

function handleSSEMessage(data, totalCount, uiIndexMap = null) {
    if (data.type === 'info') {
        addLog('info', data.message);
    } else if (data.type === 'error') {
        addLog('error', data.message);
    } else if (data.type === 'done') {
        addLog('success', data.message);
    } else if (data.type === 'diagnostics') {
        const details = data.details || {};
        addLog('warning', `Diagnostics แถว ${data.index ?? '-'}: ${details.url || details.diagnostics_error || 'ไม่พบรายละเอียด'}`);
    } else if (data.type === 'row_status') {
        const payloadIdx = data.index;
        const idx = Array.isArray(uiIndexMap) && uiIndexMap[payloadIdx] != null
            ? uiIndexMap[payloadIdx]
            : payloadIdx;
        const status = data.status;
        const msg = data.message;
        updateRowStatus(idx, status);
        if (status === 'processing') {
            addLog('info', msg);
        } else if (status === 'success') {
            addLog('success', msg);
            const progressPercent = Math.round(((payloadIdx + 1) / totalCount) * 100);
            const progressBar = document.getElementById('progress-bar');
            progressBar.style.width = `${progressPercent}%`;
            progressBar.textContent = `${payloadIdx + 1}/${totalCount}`;
            progressBar.style.fontSize = '0.65rem';
            progressBar.style.color = 'white';
            progressBar.style.display = 'flex';
            progressBar.style.alignItems = 'center';
            progressBar.style.justifyContent = 'center';
        } else if (status === 'error') {
            addLog('error', msg);
        }
    } else if (data.type === 'screenshot') {
        const container = document.getElementById('error-container');
        const img = document.getElementById('error-img');
        let message = document.getElementById('error-screenshot-message');
        if (!message) {
            message = document.createElement('p');
            message.id = 'error-screenshot-message';
            message.className = 'error-screenshot-message';
            container.appendChild(message);
        }
        container.style.display = 'block';
        if (data.available && data.url) {
            img.src = `${data.url}?t=${new Date().getTime()}`;
            img.hidden = false;
            message.textContent = '';
        } else {
            img.removeAttribute('src');
            img.hidden = true;
            message.textContent = data.message || 'ภาพหน้าจอถูกซ่อนเพื่อป้องกันข้อมูลจากพอร์ทัลรั่วไหล';
        }
    }
}

function updateRowStatus(rowIdx, status) {
    const td = document.getElementById(`status-${rowIdx}`);
    if (!td) return;
    if (status === 'ready') {
        td.innerHTML = `<span class="status-badge badge-ready">พร้อมกรอก</span>`;
    } else if (status === 'processing') {
        td.innerHTML = `
            <span class="status-badge badge-processing">
                <span class="loading-spinner"></span>
                กำลังกรอก...
            </span>`;
    } else if (status === 'success') {
        td.innerHTML = `<span class="status-badge badge-success">✓ สำเร็จ</span>`;
    } else if (status === 'error') {
        td.innerHTML = `<span class="status-badge badge-error">✗ ผิดพลาด</span>`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const btnOpenManual = document.getElementById('btn-open-manual');
    const manualModal = document.getElementById('manual-modal');
    const btnCloseX = document.getElementById('btn-close-manual-x');
    const btnCloseOk = document.getElementById('btn-close-manual-ok');

    if (btnOpenManual && manualModal) {
        btnOpenManual.addEventListener('click', () => {
            manualModal.classList.add('active');
        });
    }

    const closeModal = () => {
        if (manualModal) manualModal.classList.remove('active');
    };

    if (btnCloseX) btnCloseX.addEventListener('click', closeModal);
    if (btnCloseOk) btnCloseOk.addEventListener('click', closeModal);
    if (manualModal) {
        manualModal.addEventListener('click', (e) => {
            if (e.target === manualModal) closeModal();
        });
    }

    populateAutoPlanMonthSelect();
    renderHolidayDaysGrid();
});

/* ========================================
   STEP 1: TAB SWITCHER & AUTO PLAN GENERATOR
   ======================================== */

function switchPlanCreationTab(tab) {
    const btnExcel = document.getElementById('tab-btn-excel');
    const btnAuto = document.getElementById('tab-btn-auto');
    const panelExcel = document.getElementById('plan-panel-excel');
    const panelAuto = document.getElementById('plan-panel-auto');

    if (tab === 'excel') {
        btnExcel?.classList.add('active');
        btnAuto?.classList.remove('active');
        if (panelExcel) panelExcel.style.display = 'block';
        if (panelAuto) panelAuto.style.display = 'none';
    } else {
        btnAuto?.classList.add('active');
        btnExcel?.classList.remove('active');
        if (panelAuto) panelAuto.style.display = 'block';
        if (panelExcel) panelExcel.style.display = 'none';
        populateAutoPlanMonthSelect();
        renderHolidayDaysGrid();
    }
}

let selectedHolidaysSet = new Set();

function populateAutoPlanMonthSelect() {
    const sel = document.getElementById('auto-plan-month');
    if (!sel || sel.children.length > 0) return;

    const monthNames = [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ];

    const today = new Date();
    const curYear = today.getFullYear();
    const curMonth = today.getMonth();

    let html = '';
    // Show current + next 5 months
    for (let i = 0; i < 6; i++) {
        const d = new Date(curYear, curMonth + i, 1);
        const mIdx = d.getMonth();
        const yBe = d.getFullYear() + 543;
        const val = `${d.getFullYear()}-${String(mIdx + 1).padStart(2, '0')}`;
        const label = `${monthNames[mIdx]} ${yBe}`;
        html += `<option value="${val}">${label}</option>`;
    }
    sel.innerHTML = html;
}

function renderHolidayDaysGrid() {
    const grid = document.getElementById('holiday-days-grid');
    if (!grid) return;

    const monthSel = document.getElementById('auto-plan-month')?.value;
    if (!monthSel) return;

    const [yearStr, monthStr] = monthSel.split('-');
    const year = parseInt(yearStr, 10);
    const month = parseInt(monthStr, 10) - 1;
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const dayShortNames = ["อา.", "จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส."];

    let html = '';
    for (let d = 1; d <= daysInMonth; d++) {
        const dt = new Date(year, month, d);
        const dayOfWeek = dt.getDay(); // 0 = Sun, 6 = Sat
        const isWeekend = (dayOfWeek === 0 || dayOfWeek === 6);
        const isHoliday = selectedHolidaysSet.has(d);

        let classes = 'day-chip-btn';
        if (isWeekend) classes += ' is-weekend';
        if (isHoliday) classes += ' is-holiday';

        const clickHandler = isWeekend ? '' : `onclick="toggleHolidayDay(${d})"`;

        html += `
            <button type="button" class="${classes}" ${clickHandler} title="${d} (วัน${dayShortNames[dayOfWeek]})">
                <span>${d}</span>
                <span class="day-name">${dayShortNames[dayOfWeek]}</span>
            </button>
        `;
    }

    grid.innerHTML = html;
    updateHolidayHintText();
}

function toggleHolidayDay(dayNum) {
    if (selectedHolidaysSet.has(dayNum)) {
        selectedHolidaysSet.delete(dayNum);
    } else {
        selectedHolidaysSet.add(dayNum);
    }
    renderHolidayDaysGrid();
}

function clearSelectedHolidays() {
    selectedHolidaysSet.clear();
    renderHolidayDaysGrid();
    addLog('info', 'ล้างรายการวันหยุดทั้งหมดแล้ว');
}

// Thai Standard Public Holidays mapping by Month (1..12)
const thaiHolidaysByMonth = {
    1: [1],             // วันขึ้นปีใหม่
    4: [6, 13, 14, 15], // วันจักรี + วันสงกรานต์
    5: [1, 4],          // วันแรงงาน + วันฉัตรมงคล
    6: [3],             // วันเฉลิมพระชนมพรรษาพระราชินี
    7: [28],            // วันเฉลิมพระชนมพรรษา ร.10
    8: [12],            // วันแม่แห่งชาติ
    10: [13, 23],       // วันนวมินทรมหาราช + วันปิยมหาราช
    12: [5, 10, 31]     // วันพ่อแห่งชาติ + วันรัฐธรรมนูญ + วันสิ้นปี
};

function autoSelectThaiHolidays() {
    const monthSel = document.getElementById('auto-plan-month')?.value;
    if (!monthSel) return;

    const [yearStr, monthStr] = monthSel.split('-');
    const month = parseInt(monthStr, 10);

    const holidays = thaiHolidaysByMonth[month] || [];
    if (holidays.length === 0) {
        addLog('info', 'เดือนนี้ไม่มีวันหยุดนักขัตฤกษ์หลัก คุณสามารถคลิกเลือกเลขวันที่ได้เอง');
    } else {
        holidays.forEach(d => selectedHolidaysSet.add(d));
        addLog('success', `โหลดวันหยุดนักขัตฤกษ์ไทยประจำเดือน (${holidays.map(d => `วันที่ ${d}`).join(', ')}) เรียบร้อยแล้ว`);
    }

    renderHolidayDaysGrid();
}

function updateHolidayHintText() {
    const hint = document.getElementById('holiday-selected-hint');
    if (!hint) return;
    const list = Array.from(selectedHolidaysSet).sort((a, b) => a - b);
    if (list.length > 0) {
        hint.innerHTML = `วันเสาร์-อาทิตย์เว้นให้อัตโนมัติ · <strong style="color:#fca5a5;">เลือกวันหยุดแล้ว (${list.length} วัน): วันที่ ${list.join(', ')}</strong>`;
    } else {
        hint.textContent = 'วันเสาร์-อาทิตย์เว้นให้อัตโนมัติ · คลิกที่ตัวเลขเพื่อเลือกวันหยุดนักขัตฤกษ์/วันหยุดพิเศษ/วันลาเพิ่มเติม';
    }
}

// Pool of diverse T&V Field Activities for Random Generator
const randomActivityPool = [
    { issue_val: "2", activity_val: "15", activity: "การเยี่ยมเยียนเกษตรกรกลุ่มส่งเสริมเกษตรแปลงใหญ่" },
    { issue_val: "2", activity_val: "16", activity: "การพัฒนาศักยภาพ Smart Farmer / Young Smart Farmer" },
    { issue_val: "2", activity_val: "2",  activity: "การติดตามถ่ายทอดความรู้ศูนย์เรียนรู้การเพิ่มประสิทธิภาพการผลิตสินค้าเกษตร (ศพก.)" },
    { issue_val: "2", activity_val: "19", activity: "การส่งเสริมและพัฒนาศักยภาพวิสาหกิจชุมชน" },
    { issue_val: "2", activity_val: "20", activity: "การส่งเสริมและพัฒนากลุ่มแม่บ้านเกษตรกร / กลุ่มเกษตรกร" },
    { issue_val: "2", activity_val: "22", activity: "การส่งเสริมและพัฒนาการผลิตตามมาตรฐานเกษตรอินทรีย์" },
    { issue_val: "2", activity_val: "24", activity: "การพัฒนาคุณภาพและยกระดับมาตรฐานสินค้าเกษตร" },
    { issue_val: "2", activity_val: "17", activity: "การบริหารจัดการพื้นที่เกษตรกรรมตามแผนที่ Agri-Map" },
    { issue_val: "2", activity_val: "21", activity: "การส่งเสริมการทำเกษตรตามแนวทางเกษตรทฤษฎีใหม่" }
];

async function loadHistoricalActivityPool() {
    if (historicalActivityPoolLoaded) return historicalActivityPool;

    try {
        const response = await fetch('/api/historical-activities');
        const payload = await response.json();
        historicalActivityPool = Array.isArray(payload.activities)
            ? payload.activities.filter(item =>
                item &&
                String(item.issue_val) === '2' &&
                String(item.activity_val || '').trim() &&
                String(item.activity || '').trim()
            )
            : [];
        historicalActivityPoolLoaded = true;
        return historicalActivityPool;
    } catch (error) {
        historicalActivityPoolLoaded = true;
        historicalActivityPool = [];
        addLog('warning', 'โหลดคลังกิจกรรมจาก Excel เก่าไม่สำเร็จ');
        return historicalActivityPool;
    }
}

function pickWeightedActivity(pool) {
    const candidates = Array.isArray(pool) && pool.length ? pool : randomActivityPool;
    const totalWeight = candidates.reduce((sum, item) => {
        const weight = Number(item?.weight);
        return sum + (Number.isFinite(weight) && weight > 0 ? weight : 1);
    }, 0);
    let cursor = Math.random() * totalWeight;

    for (const item of candidates) {
        const weight = Number(item?.weight);
        cursor -= Number.isFinite(weight) && weight > 0 ? weight : 1;
        if (cursor < 0) return item;
    }

    return candidates[candidates.length - 1];
}

async function generateAutoMonthPlanFromWebUI() {
    const tbs = [...getResponsibleTambonSet()];
    if (!geoState.setupConfirmed) {
        if ((geoState.amphoeCode || geoState.amphoeName) && tbs.length > 0) {
            confirmResponsibilitySetup();
        } else {
            addLog('warning', 'กรุณาเลือกจังหวัด อำเภอ และตำบลที่รับผิดชอบในส่วนด้านบนก่อน');
            alert('กรุณาเลือกจังหวัด อำเภอ และตำบลที่รับผิดชอบ ในส่วน "พื้นที่รับผิดชอบ" ด้านบนก่อนครับ');
            document.getElementById('setup-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            return;
        }
    }

    const monthSel = document.getElementById('auto-plan-month')?.value;
    if (!monthSel) return;

    const [yearStr, monthStr] = monthSel.split('-');
    const year = parseInt(yearStr, 10);
    const month = parseInt(monthStr, 10) - 1; // 0-indexed
    currentPlanMonth = monthSel;
    const yearBe = year + 543;
    const monthFormattedStr = String(month + 1).padStart(2, '0');

    const randomizeVillages = !!document.getElementById('opt-randomize-villages-auto')?.checked;
    const historicalPool = await loadHistoricalActivityPool();
    const activitySourcePool = historicalPool.length
        ? historicalPool
        : randomActivityPool;
    const shouldRandomizeActivities = activitySourcePool.length > 0;

    if (historicalPool.length > 0) {
        addLog(
            'info',
            `สุ่มกิจกรรมเยี่ยมเยียนจากคลัง Excel เก่า ${historicalPool.length} รูปแบบ โดยให้น้ำหนักตามจำนวนครั้งที่พบ`
        );
    } else {
        addLog('warning', 'ไม่พบกิจกรรมเยี่ยมเยียนจาก Excel เก่า จึงใช้รายการกิจกรรมสำรองของระบบ');
    }

    const responsible = [...getResponsibleTambonSet()];
    const primaryTambon = responsible[0] || bareTambonName(geoState.tambonName || '');

    const daysInMonth = new Date(year, month + 1, 0).getDate();
    allRecords = [];
    let rowId = 1;
    let skippedHolidays = 0;

    for (let d = 1; d <= daysInMonth; d++) {
        const dt = new Date(year, month, d);
        const dayOfWeek = dt.getDay(); // 0 = Sun, 6 = Sat

        // Skip Weekends (Sat/Sun)
        if (dayOfWeek === 0 || dayOfWeek === 6) continue;

        // Skip Specified Holidays
        if (selectedHolidaysSet.has(d)) {
            skippedHolidays++;
            continue;
        }

        const dayStr = String(d).padStart(2, '0');
        const dateStr = `${dayStr}/${monthFormattedStr}/${yearBe}`;

        if (dayOfWeek === 1) {
            // Monday = Office Meeting (DM on 1st Monday, WM on other Mondays)
            const isFirstMonday = d <= 7;
            const staffCount = getOfficeStaffCount();
            allRecords.push({
                id: rowId++,
                date: dateStr,
                activity: isFirstMonday ? 'ประชุมสำนักงานเกษตรอำเภอประจำเดือน (DM)' : 'ประชุมสำนักงานเกษตรอำเภอประจำสัปดาห์ (WM)',
                tool: 'ประชุม',
                placeParts: [],
                location: getOfficePlaceName(),
                officeOnly: true,
                moos: [],
                villages: [],
                tambon: primaryTambon,
                target_raw: `${staffCount} ราย`,
                target_num: staffCount,
                co_workers: '',
                issue_val: '1',
                activity_val: isFirstMonday ? '13' : '14',
                other_text: '',
                useAllTambons: false
            });
        } else {
            // Tue - Fri = Field Activities
            let chosenAct = {
                issue_val: '2',
                activity_val: '15',
                activity: 'การเยี่ยมเยียนส่งเสริมการเกษตรและถ่ายทอดความรู้'
            };

            if (shouldRandomizeActivities) {
                chosenAct = pickWeightedActivity(activitySourcePool);
            }

            const randTarget = getRandomFieldTargetCount(); // สุ่มจาก [20, 30, 50, 60] คน

            allRecords.push({
                id: rowId++,
                date: dateStr,
                activity: chosenAct.activity,
                tool: 'เยี่ยมเยียน',
                placeParts: primaryTambon ? [{ tambon: primaryTambon, moos: [] }] : [],
                location: primaryTambon ? formatTambonPart(primaryTambon) : '',
                moos: [],
                villages: [],
                tambon: primaryTambon,
                target_raw: `${randTarget} ราย`,
                target_num: randTarget,
                co_workers: '',
                issue_val: chosenAct.issue_val,
                activity_val: chosenAct.activity_val,
                other_text: chosenAct.other_text || '',
                useAllTambons: false
            });
        }
    }

    if (randomizeVillages) {
        await applyPlaceAfterExcelLoad(allRecords);
    } else {
        await applyPlaceAfterExcelLoad(allRecords);
    }

    renderTable(allRecords);
    updateQuickStats();

    let msg = `✨ สุ่มสร้างแผนประจำเดือน (${allRecords.length} วันทำงาน) เรียบร้อยแล้ว!`;
    if (skippedHolidays > 0) {
        const sortedList = Array.from(selectedHolidaysSet).sort((a, b) => a - b);
        msg += ` (เว้นวันหยุด ${skippedHolidays} วัน: วันที่ ${sortedList.join(', ')})`;
    }
    addLog('success', msg);
    document.querySelector('.table-responsive')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
