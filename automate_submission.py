import sys
import time
import argparse
import pandas as pd
import re
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PORTAL_LOGIN_URL = "https://tandv.doae.go.th/index/login_tv_system.php"
PORTAL_WORKFLOW_26_URL = "https://tandv.doae.go.th/workflow/workflow_start.php?W=26"
PLAYWRIGHT_NAVIGATION_TIMEOUT_MS = 30_000
PLAYWRIGHT_ACTION_TIMEOUT_MS = 15_000
PLAYWRIGHT_RESULT_TIMEOUT_MS = 25_000


def _page_diagnostics(page):
    try:
        return page.evaluate("""() => {
            const selectors = ['#PL_YAER', '#PL_MOUNT', '#PL_TAMBONN', '#USR_APPROVERS'];
            const workflowControls = {};
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (!el) {
                    workflowControls[selector] = {present: false};
                    continue;
                }
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                workflowControls[selector] = {
                    present: true,
                    optionCount: el.options ? el.options.length : 0,
                    value: el.value || '',
                    ariaHidden: el.getAttribute('aria-hidden'),
                    display: style.display,
                    visibility: style.visibility,
                    visible: Boolean(rect.width && rect.height && style.display !== 'none' && style.visibility !== 'hidden')
                };
            }
            return {
                url: window.location.href,
                title: document.title,
                bodyText: (document.body?.innerText || '').slice(-2000),
                loginVisible: Boolean(document.querySelector('input[name=USER_PASSWORD]')),
                workflowReady: workflowControls['#PL_YAER']?.present && workflowControls['#PL_YAER'].optionCount > 1 &&
                    workflowControls['#PL_MOUNT']?.present && workflowControls['#PL_MOUNT'].optionCount >= 1 &&
                    workflowControls['#PL_TAMBONN']?.present && workflowControls['#PL_TAMBONN'].optionCount > 1,
                workflowControls
            };
        }""")
    except Exception as exc:
        return {"diagnostics_error": str(exc)}


def _assert_authenticated(page):
    state = _page_diagnostics(page)
    if state.get("loginVisible") or "login" in str(state.get("url", "")).lower():
        raise RuntimeError(f"AUTHENTICATION_ERROR: {state}")


def is_tv_logged_in(page):
    """Check T&V login state from page content, not from the URL alone.

    Mirrors app.py: logged in requires no visible login form, a non-login URL
    path, and an authenticated-chrome marker. Never touches credentials.
    """
    try:
        state = page.evaluate("""() => ({
            urlPath: window.location.pathname || '',
            loginVisible: Boolean(document.querySelector('input[name="USER_PASSWORD"]')),
            authMarkers: Boolean(
                document.querySelector('a[href*="logout"]')
                || document.querySelector('a[href*="workflow"]')
                || document.querySelector('#PL_YAER')
                || document.querySelector('a[href*="main_tv_system"]')
            ),
        })""")
    except Exception:
        return False
    if not isinstance(state, dict) or state.get('loginVisible'):
        return False
    path = str(state.get('urlPath') or '').lower()
    if not path or 'login' in path:
        return False
    return bool(state.get('authMarkers'))


def _wait_for_portal_ready(page, stage):
    """Wait for initial Select2 controls without requiring month options yet."""
    try:
        page.wait_for_function("""() => {
            const minimums = {
                '#PL_YAER': 2,
                '#PL_MOUNT': 1,
                '#PL_TAMBONN': 2
            };
            return Object.entries(minimums).every(([selector, minimum]) => {
                const el = document.querySelector(selector);
                return el && el.options && el.options.length >= minimum;
            });
        }""", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)
    except Exception as exc:
        raise RuntimeError(f"WORKFLOW_SELECTOR_ERROR at {stage}: {_page_diagnostics(page)}") from exc


def _wait_for_select_options(page, selector, minimum, stage):
    """Wait for a dynamic Select2 backing select to receive enough options."""
    try:
        selector_js = json.dumps(str(selector), ensure_ascii=False)
        minimum_js = int(minimum)
        page.wait_for_function(
            f"""() => {{
                const el = document.querySelector({selector_js});
                return Boolean(el && el.options && el.options.length >= {minimum_js});
            }}""",
            timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS,
        )
    except Exception as exc:
        raise RuntimeError(f"WORKFLOW_DYNAMIC_OPTION_ERROR at {stage}: {_page_diagnostics(page)}") from exc


def _modal_validation_state(page):
    return page.evaluate("""() => {
        const modal = document.querySelector('#bizModal_402');
        if (!modal) return {modal: 'missing'};
        return {
            invalid: Array.from(modal.querySelectorAll(':invalid')).map((el) => ({
                id: el.id, name: el.name, value: el.value, message: el.validationMessage
            })),
            startDate: modal.querySelector('#PD_SDATE')?.value || '',
            endDate: modal.querySelector('#PD_EDATE')?.value || '',
            issue: modal.querySelector('#PD_ISSUES')?.value || '',
            activity: modal.querySelector('#PD_ACTIVITY')?.value || '',
            other: modal.querySelector('#PD_OTHER')?.value || '',
            detail: modal.querySelector('#PD_DETAIL')?.value || '',
            place: modal.querySelector('#PD_PLACE')?.value || '',
            target: modal.querySelector('#PD_TARGET')?.value || ''
        };
    }""")


def _verify_finalize_result(page, before_url):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=PLAYWRIGHT_RESULT_TIMEOUT_MS)
    except Exception:
        pass
    page.wait_for_timeout(1_000)
    state = _page_diagnostics(page)
    text = str(state.get("bodyText", "")).lower()
    markers = ("บันทึกข้อมูลเรียบร้อย", "บันทึกเรียบร้อย", "ส่งข้อมูลเรียบร้อย", "success", "saved", "completed")
    return {"confirmed": any(marker in text for marker in markers) or (
        state.get("url") != before_url and not state.get("loginVisible")
    ), "state": state}

# Normalized mapping function
def map_activity(activity_name, tool_name):
    act = activity_name.strip()
    tool = tool_name.strip()
    
    # 1. Training / Meetings
    if "ประชุมสำนักงานเกษตรอำเภอ" in act or "ประชุม" in tool:
        if "WM" in act or "สัปดาห์" in act:
            return "1", "14", ""  # TRAINING, Weekly Meeting
        elif "DM" in act or "อำเภอประจำเดือน" in act:
            return "1", "13", ""  # District Meeting
        elif "MM" in act or "ประจำเดือน" in act:
            return "1", "12", ""  # Monthly Meeting
        else:
            return "1", "999", act
            
    # 2. Visiting / Projects
    if "วิสาหกิจชุมชน" in act:
        return "2", "19", ""      # VISITING, วิสาหกิจชุมชน
    elif "ทะเบียนเกษตรกร" in act:
        return "5", "4", ""       # DATA MANAGEMENT, ด้านข้อมูลสารสนเทศ
    elif "Smart Farmer" in act:
        return "2", "16", ""      # VISITING, Smart Farmer / Young Smart Farmer
    elif "Zoning" in act or "Agri-Map" in act:
        return "2", "17", ""      # VISITING, Zoning by Agri-Map
    elif "แปลงใหญ่" in act:
        return "2", "15", ""      # VISITING, เกษตรแปลงใหญ่
    elif "เกษตรอินทรีย์" in act or "5 ดี" in act:
        return "2", "22", ""      # VISITING, เกษตรอินทรีย์
    elif "ศูนย์เรียนรู้" in act or "ศพก" in act:
        return "2", "2", ""       # VISITING, ศพก.
    elif "ยกระดับคุณภาพ" in act or "มาตรฐานสินค้าเกษตร" in act:
        return "2", "24", ""      # VISITING, พัฒนาคุณภาพสินค้าเกษตร
    elif "สุขภาพพืช" in act or "จัดการสุขภาพพืช" in act:
        return "2", "24", ""      # VISITING, พัฒนาคุณภาพสินค้าเกษตร
    elif "องค์กรเกษตรกร" in act or "พัฒนาเกษตรกร" in act or "3ก" in act:
        return "2", "20", ""      # VISITING, กลุ่มเกษตรกร / กลุ่มแม่บ้านเกษตรกร
    elif "สิ่งแวดล้อม" in act or "เป็นมิตรกับสิ่งแวดล้อม" in act:
        return "2", "999", act    # VISITING, อื่นๆ
    else:
        return "2", "999", act    # VISITING, อื่นๆ (Fallback)

# Convert Excel Date string to dd/mm/yyyy BE
def parse_date_to_be(date_str, month_num, year_num):
    date_str = str(date_str).replace(" ", "")
    # Extract day digits from start of string
    match = re.match(r"^(\d+)", date_str)
    if not match:
        return None
    day = int(match.group(1))
    return f"{day:02d}/{month_num:02d}/{year_num}"


def thai_fiscal_year_be(calendar_year_be, month_num):
    year = int(calendar_year_be)
    month = int(month_num)
    if month >= 10:
        return year + 1
    return year


def calendar_year_be_for_fiscal_sheet(sheet_year_be, month_num):
    year = int(sheet_year_be)
    month = int(month_num)
    if month >= 10:
        return year - 1
    return year


def resolve_portal_fiscal_year(sheet_year_be, month_num, records=None):
    for rec in records or []:
        text = str(rec.get("date") or "").strip()
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
        if not match:
            continue
        cal_be = int(match.group(3))
        mon = int(match.group(2))
        if cal_be < 2400:
            continue
        return str(thai_fiscal_year_be(cal_be, mon))
    return str(int(sheet_year_be))


# Parse sheet name (e.g. "มิ.ย.69" -> Year 2569, Month value 69, Month number 6)
def parse_sheet_name(sheet_name):
    # Normalize sheet name
    normalized = sheet_name.replace(" ", "").replace(".", "")
    match = re.match(r"^([ก-๙]+)(\d+)$", normalized)
    if not match:
        raise ValueError(f"Invalid sheet name format: {sheet_name}. Expected format like 'มิ.ย.69'")
    
    month_part = match.group(1)
    year_part = int(match.group(2))
    
    full_year = 2500 + year_part
    
    month_map = {
        "มค": (1, "64"),
        "กพ": (2, "65"),
        "มีค": (3, "66"),
        "เมย": (4, "67"),
        "พค": (5, "68"),
        "มิย": (6, "69"),
        "กค": (7, "70"),
        "สค": (8, "71"),
        "กย": (9, "72"),
        "ตค": (10, "61"),
        "พย": (11, "62"),
        "ธค": (12, "63")
    }
    
    if month_part not in month_map:
        raise ValueError(f"Unknown month name abbreviation: '{month_part}' in sheet name '{sheet_name}'")
        
    month_num, portal_month_val = month_map[month_part]
    return str(full_year), portal_month_val, month_num

# Clean Excel values to prevent float formatting representation (e.g. 5.0 -> 5)
def clean_excel_val(val):
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    return val_str

# JS Dropdown helpers to bypass Select2 visibility issues
def _select_portal_option(page, selector, *, value=None, label=None):
    result = page.evaluate(
        """({selector, value, label}) => {
            const select = document.querySelector(selector);
            if (!select) return {found: false, reason: 'select-not-found'};
            const wantedValue = String(value || '').trim();
            const wantedLabel = String(label || '').trim();
            const option = Array.from(select.options).find((item) =>
                (wantedValue && item.value === wantedValue) ||
                (wantedLabel && item.text.trim() === wantedLabel)
            );
            if (!option) return {
                found: false,
                reason: 'option-not-found',
                options: Array.from(select.options).map((item) => ({value: item.value, text: item.text.trim()}))
            };
            select.value = option.value;
            select.dispatchEvent(new Event('input', {bubbles: true}));
            select.dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) window.jQuery(select).val(option.value).trigger('change');
            return {found: true, value: select.value, text: option.text.trim()};
        }""",
        {"selector": selector, "value": value, "label": label},
    )
    if not result.get("found"):
        raise RuntimeError(f"PORTAL_OPTION_ERROR for {selector}: {result}")
    page.wait_for_timeout(300)
    actual = page.locator(selector).input_value()
    if actual != result.get("value"):
        raise RuntimeError(f"PORTAL_OPTION_NOT_PERSISTED for {selector}: expected={result.get('value')!r}, got={actual!r}")


def select_by_value_js(page, selector, value):
    _select_portal_option(page, selector, value=str(value or "").strip())


def select_by_label_js(page, selector, label):
    _select_portal_option(page, selector, label=str(label or "").strip())


def _select_modal_option(page, selector, value, label=""):
    """Select a dynamic portal option and verify that it remains selected."""
    target = str(value or "").strip()
    target_label = str(label or "").strip()
    last_state = {}

    for _ in range(12):
        last_state = page.evaluate(
            """({selector, target, label}) => {
                const select = document.querySelector(selector);
                if (!select) return {found: false, reason: 'select-not-found'};
                const option = Array.from(select.options).find((item) =>
                    item.value === target || (label && item.text.trim() === label)
                );
                if (!option) {
                    return {
                        found: false,
                        reason: 'option-not-found',
                        options: Array.from(select.options).map((item) => ({
                            value: item.value,
                            text: item.text.trim()
                        }))
                    };
                }
                select.value = option.value;
                select.dispatchEvent(new Event('input', {bubbles: true}));
                select.dispatchEvent(new Event('change', {bubbles: true}));
                if (window.jQuery) window.jQuery(select).val(option.value).trigger('change');
                return {found: true, value: option.value, text: option.text.trim()};
            }""",
            {"selector": selector, "target": target, "label": target_label},
        )
        if last_state.get("found"):
            page.wait_for_timeout(350)
            selected = page.evaluate(
                """(select) => {
                    const el = document.querySelector(select);
                    return el ? el.value : '';
                }""",
                selector,
            )
            if selected == last_state.get("value"):
                return
        page.wait_for_timeout(300)

    raise RuntimeError(
        f"Portal option was not selected for {selector}: "
        f"target={target!r}, state={last_state}"
    )


def _set_modal_select_value(page, selector, value, label=""):
    """Set a final modal select value without firing its destructive change handler."""
    target = str(value or "").strip()
    target_label = str(label or "").strip()
    state = page.evaluate(
        """({selector, target, label}) => {
            const select = document.querySelector(selector);
            if (!select) return {found: false, reason: 'select-not-found'};
            const option = Array.from(select.options).find((item) =>
                item.value === target || (label && item.text.trim() === label)
            );
            if (!option) return {
                found: false,
                reason: 'option-not-found',
                options: Array.from(select.options).map((item) => ({
                    value: item.value,
                    text: item.text.trim()
                }))
            };
            select.value = option.value;
            select.dispatchEvent(new Event('input', {bubbles: true}));
            return {found: true, value: option.value, text: option.text.trim()};
        }""",
        {"selector": selector, "target": target, "label": target_label},
    )
    if not state.get("found"):
        raise RuntimeError(
            f"Portal final option was not found for {selector}: "
            f"target={target!r}, state={state}"
        )
    page.wait_for_timeout(250)
    selected = page.locator(selector).input_value()
    if selected != state.get("value"):
        raise RuntimeError(
            f"Portal final option was not retained for {selector}: "
            f"expected={state.get('value')!r}, got={selected!r}"
        )


def _set_modal_dates(page, date_value):
    """Set identical start/end dates for a one-day plan record."""
    same_day = str(date_value or "").strip()
    if not same_day:
        raise ValueError("A plan record must contain a date")
    last_values = {}
    for _ in range(4):
        last_values = page.evaluate(
            """(dateValue) => {
                const modal = document.querySelector('#bizModal_402');
                if (!modal) return {};
                const values = {};
                ['#PD_SDATE', '#PD_EDATE'].forEach((selector) => {
                    const input = modal.querySelector(selector);
                    if (!input) return;
                    input.removeAttribute('disabled');
                    input.value = dateValue;
                    ['input', 'change', 'blur'].forEach((eventName) => {
                        input.dispatchEvent(new Event(eventName, {bubbles: true}));
                    });
                    values[selector] = input.value;
                });
                return values;
            }""",
            same_day,
        )
        if (
            last_values.get("#PD_SDATE") == same_day
            and last_values.get("#PD_EDATE") == same_day
        ):
            page.wait_for_timeout(500)
            stable_values = page.evaluate("""() => {
                const modal = document.querySelector('#bizModal_402');
                if (!modal) return {};
                return {
                    '#PD_SDATE': modal.querySelector('#PD_SDATE')?.value || '',
                    '#PD_EDATE': modal.querySelector('#PD_EDATE')?.value || ''
                };
            }""")
            if (
                stable_values.get("#PD_SDATE") == same_day
                and stable_values.get("#PD_EDATE") == same_day
            ):
                return
        page.wait_for_timeout(450)

    raise RuntimeError(f"Portal same-day date fields were not retained: {last_values}")


def main():
    # Configure stdout/stderr to replace unencodable characters instead of crashing
    try:
        sys.stdout.reconfigure(errors='replace')
        sys.stderr.reconfigure(errors='replace')
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description="T&V Automation Script")
    parser.add_argument("--submit", action="store_true", help="Perform actual submission (otherwise runs dry-run)")
    parser.add_argument("--draft", action="store_true", help="Save as draft (บันทึกชั่วคราว)")
    parser.add_argument("--sheet", default="มิ.ย.69", help="Excel sheet name to process")
    args = parser.parse_args()

    import os
    
    xls_path = r"c:\Users\Admin\Downloads\tv_automation\แผนเดือนพค69.xls"
    sheet_name = args.sheet
    
    try:
        year_num, portal_month_val, month_num = parse_sheet_name(sheet_name)
    except Exception as e_sheet:
        print(f"Error parsing sheet name: {e_sheet}")
        sys.exit(1)
    calendar_year = calendar_year_be_for_fiscal_sheet(year_num, month_num)
        
    print(f"Reading Excel sheet: {sheet_name} (Fiscal Year {year_num}, Month Number {month_num}, Portal Value {portal_month_val})...")
    xl = pd.ExcelFile(xls_path)
    df = xl.parse(sheet_name)
    
    # Parse rows starting from row 4 (index 4)
    records = []
    for idx in range(4, len(df)):
        row = df.iloc[idx]
        date_raw = row.iloc[1]
        activity_raw = row.iloc[2]
        tool_raw = row.iloc[3]
        location_raw = row.iloc[4]
        target_raw = row.iloc[5]
        co_workers_raw = row.iloc[6]
        tambon_raw = row.iloc[7]
        
        if pd.isna(date_raw) and pd.isna(activity_raw):
            continue
            
        date_str = str(date_raw).strip() if not pd.isna(date_raw) else ""
        activity = str(activity_raw).strip() if not pd.isna(activity_raw) else ""
        tool = str(tool_raw).strip() if not pd.isna(tool_raw) else ""
        location = str(location_raw).strip() if not pd.isna(location_raw) else ""
        target = str(target_raw).strip() if not pd.isna(target_raw) else ""
        co_workers = str(co_workers_raw).strip() if not pd.isna(co_workers_raw) else ""
        tambon = str(tambon_raw).strip() if not pd.isna(tambon_raw) else ""
        
        if not date_str and not activity:
            continue
            
        be_date = parse_date_to_be(date_str, month_num, calendar_year)
        if not be_date:
            print(f"Warning: Could not parse date '{date_str}' at row {idx+1}. Skipping.")
            continue
            
        # Check for optional overrides in columns 8 to 12 (Unnamed: 8 to Unnamed: 12)
        override_issue = clean_excel_val(row.iloc[8]) if len(row) > 8 and not pd.isna(row.iloc[8]) else ""
        override_activity = clean_excel_val(row.iloc[9]) if len(row) > 9 and not pd.isna(row.iloc[9]) else ""
        override_other = clean_excel_val(row.iloc[10]) if len(row) > 10 and not pd.isna(row.iloc[10]) else ""
        override_location = clean_excel_val(row.iloc[11]) if len(row) > 11 and not pd.isna(row.iloc[11]) else ""
        override_target = clean_excel_val(row.iloc[12]) if len(row) > 12 and not pd.isna(row.iloc[12]) else ""

        issue_val, activity_val, other_text = map_activity(activity, tool)
        
        # Apply overrides
        if override_issue:
            issue_val = override_issue
        if override_activity:
            activity_val = override_activity
        if override_other:
            other_text = override_other

        # Determine location: meetings go to "สนง.กษอ.สีดา", visits fall back to tambon
        resolved_location = location
        if issue_val == "1":
            resolved_location = "สนง.กษอ.สีดา"
        elif not location or "ตำบล" in location and ("…" in location or "." in location):
            resolved_location = tambon if tambon else "ตำบลหนองตาดใหญ่"
            
        if override_location:
            resolved_location = override_location
            
        # Extract numeric target
        numeric_target = "0"
        if "ทุกท่าน" in target or "ทุกคน" in target or "จนท" in target:
            numeric_target = "7"
        else:
            digits = re.findall(r'\d+', target)
            if digits:
                numeric_target = "".join(digits)
                
        if override_target:
            numeric_target = override_target

        records.append({
            "row_num": idx + 1,
            "date": be_date,
            "activity": activity,
            "tool": tool,
            "location": resolved_location,
            "target_raw": target,
            "target_num": numeric_target,
            "co_workers": co_workers,
            "issue_val": issue_val,
            "activity_val": activity_val,
            "other_text": other_text
        })
        
    print(f"Loaded {len(records)} records from Excel sheet.")
    portal_year = resolve_portal_fiscal_year(year_num, month_num, records)
    
    print("\nLaunching browser (Headed)...")
    # The user logs into T&V manually in the headed browser window; the script
    # never handles the T&V username/password. The persistent profile keeps
    # the session cookies on this machine only (gitignored, never uploaded).
    profile_dir = os.environ.get(
        "TV_BROWSER_PROFILE_DIR",
        str(Path(__file__).resolve().parent / "data" / "browser-profile"),
    )
    os.makedirs(profile_dir, exist_ok=True)

    with sync_playwright() as p:
        # Headed persistent context so the user can log in and verify visually
        context = p.chromium.launch_persistent_context(profile_dir, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(PLAYWRIGHT_ACTION_TIMEOUT_MS)
        page.set_default_navigation_timeout(PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)

        print("Opening T&V portal. Please log in manually in the browser window...")
        try:
            page.goto(PORTAL_LOGIN_URL, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)
        except Exception:
            # An already-authenticated profile may redirect away from login.
            pass

        login_deadline = time.time() + 300  # up to 5 minutes for manual login
        while not is_tv_logged_in(page):
            if time.time() > login_deadline:
                raise RuntimeError("TV_LOGIN_TIMEOUT: T&V login was not completed within 5 minutes")
            time.sleep(2)
        print("T&V login detected. Continuing with automation...")
        
        print("Navigating to Workflow 26 plan form...")
        page.goto(PORTAL_WORKFLOW_26_URL, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)
        _assert_authenticated(page)
        _wait_for_portal_ready(page, "workflow_26")
        
        # 1. Fill Main Page Header Fields using JS to bypass Select2 hiding
        print(f"Selecting Fiscal Year {portal_year}...")
        select_by_value_js(page, 'select#PL_YAER', str(portal_year))
        _wait_for_select_options(page, 'select#PL_MOUNT', 2, 'after selecting fiscal year')
        
        print(f"Selecting Month from sheet (value={portal_month_val})...")
        select_by_value_js(page, 'select#PL_MOUNT', str(portal_month_val))
        time.sleep(1.5)
        
        print("Selecting Tambon หนองตาดใหญ่...")
        select_by_label_js(page, 'select#PL_TAMBONN', 'หนองตาดใหญ่')
        time.sleep(1.5)
        
        # 2. Fill Table Rows via Modals
        for i, rec in enumerate(records):
            try:
                print(f"\n[{i+1}/{len(records)}] Adding Record (Row {rec['row_num']}): {rec['activity']}")
                
                # Click Add Data button to open modal
                page.locator('a:has-text("เพิ่มข้อมูล")').click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
                page.wait_for_selector('#bizModal_402', state='visible', timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
                page.wait_for_timeout(500)
                
                # Fill modal fields (these are standard selects and inputs, no Select2 wrapper)
                modal = page.locator('#bizModal_402')
                
                print(f"  Selecting Issue value: {rec['issue_val']}")
                _select_modal_option(page, '#bizModal_402 select#PD_ISSUES', rec['issue_val'])
                time.sleep(1.0) # Wait for dynamic activity options to load
                
                print(f"  Selecting Activity value: {rec['activity_val']}")
                _select_modal_option(
                    page,
                    '#bizModal_402 select#PD_ACTIVITY',
                    rec['activity_val'],
                    rec.get('activity', ''),
                )
                
                if str(rec['activity_val']) == "999" or (str(rec['issue_val']) == "2" and str(rec['activity_val']) == "999"):
                    other_val = (rec.get('other_text') or rec.get('activity') or 'ปฏิบัติงานในพื้นที่')[:30].strip()
                    print(f"  Filling Other Activity Text: {other_val}")
                    other_input = modal.locator('input#PD_OTHER')
                    if other_input.count() != 1:
                        raise RuntimeError("MODAL_VALIDATION_ERROR: PD_OTHER is required for activity 999")
                    other_input.fill(other_val)
                    if not other_input.input_value().strip():
                        raise RuntimeError("MODAL_VALIDATION_ERROR: PD_OTHER remained empty for activity 999")
                    
                print(f"  Filling Date: {rec['date']}")
                # The portal clears PD_EDATE when PD_SDATE changes; set both
                # date fields after generic modal events below.
                
                print(f"  Filling Detail: {rec['activity']}")
                modal.locator('textarea#PD_DETAIL').fill(rec['activity'])
                
                print(f"  Filling Location: {rec['location']}")
                modal.locator('textarea#PD_PLACE').fill(rec['location'])
                
                print(f"  Filling Target: {rec['target_num']} (raw: '{rec['target_raw']}')")
                modal.locator('input#PD_TARGET').fill(rec['target_num'])
                
                # Trigger input events and remove disabled attribute from submit button
                page.evaluate("""() => {
                    const modalEl = document.querySelector('#bizModal_402');
                    if (!modalEl) return;
                    const inputs = modalEl.querySelectorAll('input, select, textarea');
                    inputs.forEach(el => {
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('keyup', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    });
                    
                    const btn = modalEl.querySelector('button[type="submit"]') 
                             || modalEl.querySelector('button#btn-save') 
                             || modalEl.querySelector('.btn-primary');
                    if (btn) {
                        btn.removeAttribute('disabled');
                        btn.disabled = false;
                        btn.classList.remove('disabled');
                    }
                }""")

                # Generic change events can asynchronously rebuild PD_ACTIVITY and clear its value.
                # Let that handler settle, then set dynamic selects without firing their destructive
                # change handlers. Re-fill PD_OTHER after the final activity selection when needed.
                page.wait_for_timeout(1_000)
                _set_modal_select_value(page, 'select#PD_ISSUES', rec['issue_val'])
                _set_modal_select_value(
                    page,
                    'select#PD_ACTIVITY',
                    rec['activity_val'],
                    rec.get('activity', ''),
                )
                if str(rec['activity_val']) == "999" or (str(rec['issue_val']) == "2" and str(rec['activity_val']) == "999"):
                    other_val = (rec.get('other_text') or rec.get('activity') or 'ปฏิบัติงานในพื้นที่')[:30].strip()
                    modal.locator('input#PD_OTHER').fill(other_val)

                # Set dates last because the portal clears PD_EDATE when PD_SDATE changes.
                _set_modal_dates(page, rec['date'])
                validation_state = _modal_validation_state(page)
                expected_fields = {
                    "issue": str(rec["issue_val"]),
                    "activity": str(rec["activity_val"]),
                    "startDate": str(rec["date"]),
                    "endDate": str(rec["date"]),
                    "detail": str(rec["activity"]),
                    "place": str(rec["location"]),
                    "target": str(rec["target_num"]),
                }
                for field, expected in expected_fields.items():
                    actual = str(validation_state.get(field) or "")
                    if expected and actual != expected:
                        raise RuntimeError(f"MODAL_FIELD_MISMATCH: {field} expected={expected!r}, actual={actual!r}")
                if validation_state.get("invalid"):
                    raise RuntimeError(f"MODAL_VALIDATION_ERROR before save: {validation_state}")

                try:
                    modal.locator('button[type="submit"]:has-text("บันทึก")').click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
                except Exception as click_exc:
                    fallback_result = page.evaluate("""() => {
                        const modalEl = document.querySelector('#bizModal_402');
                        if (!modalEl) return {clicked: false, reason: 'modal-not-found'};
                        const btn = Array.from(modalEl.querySelectorAll('button, input[type="submit"]'))
                            .find(b => (b.textContent || '').includes('บันทึก') || (b.value || '').includes('บันทึก'))
                            || modalEl.querySelector('button[type="submit"]')
                            || modalEl.querySelector('button.btn-primary');
                        if (!btn) return {clicked: false, reason: 'save-button-not-found'};
                        btn.removeAttribute('disabled');
                        btn.disabled = false;
                        btn.classList.remove('disabled');
                        btn.click();
                        return {clicked: true};
                    }""")
                    if not fallback_result.get("clicked"):
                        raise RuntimeError(f"MODAL_SAVE_CONTROL_ERROR: {fallback_result}") from click_exc
                try:
                    page.wait_for_selector('#bizModal_402', state='hidden', timeout=PLAYWRIGHT_RESULT_TIMEOUT_MS)
                except Exception as exc:
                    raise RuntimeError(f"MODAL_SAVE_UNCONFIRMED: {_modal_validation_state(page)}") from exc
                page.wait_for_timeout(500)
            except Exception as e:
                print(f"Error occurred at row {rec['row_num']}: {e}")
                try:
                    # Keep portal diagnostics transient; never write screenshot or modal HTML to disk.
                    page.screenshot()
                    print("Transient error screenshot captured in memory only; no artifact was written.")
                except Exception as screenshot_exc:
                    print(f"Transient screenshot unavailable: {type(screenshot_exc).__name__}")
                raise e
            
        # 3. Select Approver and verify the value persisted
        approver_name = 'นางอรอนงค์ สูญกลาง'
        print(f"\nSelecting Approver {approver_name}...")
        select_by_label_js(page, 'select#USR_APPROVERS', approver_name)
        print("Approver selection verified.")
        
        # 4. Final Submission or Pause
        if args.submit or args.draft:
            is_submit = bool(args.submit)
            button_selector = '#wf-btn-save' if is_submit else '#wf-btn-temp-save'
            action_label = 'Submission' if is_submit else 'Draft save'
            print(f"\n*** {action_label.upper()} ***")
            before_url = page.url
            page.locator(button_selector).click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
            try:
                print("Waiting for confirmation dialog...")
                page.wait_for_selector('button.confirm', state='visible', timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
                page.locator('button.confirm').click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
            except Exception as exc:
                result = _verify_finalize_result(page, before_url)
                if not result.get("confirmed"):
                    raise RuntimeError(
                        f"FINALIZE_CONFIRMATION_ERROR: {action_label} not confirmed: {result.get('state')}"
                    ) from exc
            result = _verify_finalize_result(page, before_url)
            if not result.get("confirmed"):
                raise RuntimeError(
                    f"FINALIZE_UNKNOWN_RESULT: {action_label} may or may not have been processed; "
                    "do not retry without checking the portal"
                )
            print(f"{action_label} confirmed by portal.")
        else:
            print("\n================ DRY-RUN VERIFICATION ================")
            print("All fields have been filled out successfully.")
            print("The browser will remain open for your inspection.")
            print("PLEASE DO NOT CLOSE THE BROWSER MANUALLY YET.")
            print("Press Enter in the terminal to close the browser and exit.")
            print("======================================================")
            input()
            
        # Close while sync_playwright is still active. On an exception the
        # context manager handles teardown; do not close after its event loop.
        try:
            context.close()
        except Exception:
            print("Browser context was already closed.")

if __name__ == "__main__":
    main()
