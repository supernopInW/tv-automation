import sys
import time
import re
import queue
import threading
import uuid
import pandas as pd
from flask import Flask, render_template, jsonify, request, Response, send_from_directory
import json
import os
from werkzeug.utils import secure_filename
from google import genai
import geo_data

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# Ensure directories exist
os.makedirs('static', exist_ok=True)
os.makedirs('templates', exist_ok=True)
os.makedirs('docs', exist_ok=True)

# Global variables and paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_XLS_PATH = os.path.join(BASE_DIR, "แผนเดือนพค69.xls")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Single automation lock for shared Playwright resources (HF Space friendly)
_run_lock = threading.Lock()
_run_active = False

# Helper functions for T&V Portal mapping
def map_activity(activity_name, tool_name):
    act = activity_name.strip()
    tool = tool_name.strip()
    
    # 1. Training / Meetings (สำนักงาน = WM/MM ตามวันจันทร์ — ปรับละเอียดใน apply_sida_office_meeting_rules)
    if (
        "ประชุมสำนักงาน" in act
        or "ประชุมสำนักงานเกษตรอำเภอ" in act
        or ("ประชุม" in act and ("กษอ" in act or "สำนักงาน" in act))
        or "ประชุม" in tool
    ):
        if "DM" in act or ("ประจำเดือน" in act and "สำนักงาน" in act):
            return "1", "13", ""  # District / monthly office meeting (ตามแผนสีดา)
        if "MM" in act or "ประจำเดือน" in act:
            return "1", "12", ""  # Monthly Meeting
        if "WM" in act or "สัปดาห์" in act:
            return "1", "14", ""  # Weekly Meeting
        return "1", "14", ""  # default office meeting → WM (date rules may set DM)
            
    # 2. Visiting / Projects
    if "วิสาหกิจชุมชน" in act:
        return "2", "19", ""      # วิสาหกิจชุมชน
    elif "ทะเบียนเกษตรกร" in act:
        return "5", "4", ""       # ด้านข้อมูลสารสนเทศ
    elif "Smart Farmer" in act:
        return "2", "16", ""      # Smart Farmer / Young Smart Farmer
    elif "Zoning" in act or "Agri-Map" in act:
        return "2", "17", ""      # Zoning by Agri-Map
    elif "แปลงใหญ่" in act:
        return "2", "15", ""      # เกษตรแปลงใหญ่
    elif "เกษตรอินทรีย์" in act or "5 ดี" in act:
        return "2", "22", ""      # เกษตรอินทรีย์
    elif "ศูนย์เรียนรู้" in act or "ศพก" in act:
        return "2", "2", ""       # ศพก.
    elif "ยกระดับคุณภาพ" in act or "มาตรฐานสินค้าเกษตร" in act:
        return "2", "24", ""      # พัฒนาคุณภาพสินค้าเกษตร
    elif "สุขภาพพืช" in act or "จัดการสุขภาพพืช" in act:
        return "2", "24", ""      # พัฒนาคุณภาพสินค้าเกษตร
    elif "องค์กรเกษตรกร" in act or "พัฒนาเกษตรกร" in act or "3ก" in act:
        return "2", "20", ""      # กลุ่มเกษตรกร / กลุ่มแม่บ้านเกษตรกร
    elif "สิ่งแวดล้อม" in act or "เป็นมิตรกับสิ่งแวดล้อม" in act:
        return "2", "999", act    # อื่นๆ
    else:
        return "2", "999", act    # อื่นๆ (Fallback)

def parse_date_to_be(date_str, month_num, year_num):
    date_str = thai_to_arabic(date_str).replace(" ", "")
    match = re.match(r"^(\d+)", date_str)
    if not match:
        return ""
    day = int(match.group(1))
    return f"{day:02d}/{month_num:02d}/{year_num}"


def be_date_to_gregorian(be_date):
    """Parse DD/MM/YYYY (Buddhist Era) → datetime.date or None."""
    from datetime import date
    text = str(be_date or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
    if not m:
        return None
    day, month, be_year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    year = be_year - 543 if be_year >= 2400 else be_year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def classify_office_meeting_by_date(be_date):
    """
    สนง.กษอ.สีดา = ประชุมสำนักงานเท่านั้น (ตามแผนเยี่ยมเยียนที่หัวหน้าส่ง)
    - ทุกวันจันทร์ → ประชุมประจำสัปดาห์ (WM = 14)
    - จันทร์แรกของเดือน → ประชุมประจำเดือน (DM = 13) ตามไฟล์ Excel ของ สนง.กษอ.สีดา
    Returns dict or None if not Monday.
    """
    d = be_date_to_gregorian(be_date)
    if not d or d.weekday() != 0:  # Monday
        return None
    is_first_monday = d.day <= 7
    if is_first_monday:
        return {
            "issue_val": "1",
            "activity_val": "13",
            "kind": "DM",
            "label": "ประชุมสำนักงานเกษตรอำเภอประจำเดือน (DM)",
        }
    return {
        "issue_val": "1",
        "activity_val": "14",
        "kind": "WM",
        "label": "ประชุมสำนักงานเกษตรอำเภอประจำสัปดาห์ (WM)",
    }


def apply_sida_office_meeting_rules(records, office_name=None):
    """Force Monday rows to office meeting at สำนักงานเกษตรอำเภอ…"""
    office = _normalize_office_place(office_name)
    for rec in records or []:
        meeting = classify_office_meeting_by_date(rec.get("date"))
        if not meeting:
            # สำนักงานใช้ได้แค่ประชุม — ถ้าไม่ใช่วันจันทร์แต่ชี้สำนักงานจาก Excel ว่างไว้ให้ frontend จัด
            loc = str(rec.get("location") or "")
            if office and loc and (loc == office or "สำนักงานเกษตร" in loc):
                rec["location"] = ""
                rec["officeOnly"] = False
            continue
        rec["issue_val"] = meeting["issue_val"]
        rec["activity_val"] = meeting["activity_val"]
        rec["location"] = office
        rec["officeOnly"] = True
        # Clarify activity text if it looks like an office meeting or is empty
        act = str(rec.get("activity") or "")
        if not act or "ประชุม" in act or "WM" in act.upper() or "MM" in act.upper() or "DM" in act.upper() or "สำนักงาน" in act:
            rec["activity"] = meeting["label"]
        if not rec.get("target_num"):
            rec["target_num"] = 7
    return records

def is_thai_month_sheet(sheet_name):
    sh = sheet_name.replace(" ", "").replace(".", "")
    months = ["มค", "กพ", "มีค", "เมย", "พค", "มิย", "กค", "สค", "กย", "ตค", "พย", "ธค",
              "มกรา", "กุมภา", "มีนา", "เมษา", "พฤษภา", "มิถุนา", "กรกฎา", "สิงหา", "กันยา", "ตุลา", "พฤศจิกา", "ธันวา"]
    return any(m in sh for m in months)

def get_sheet_sort_key(sheet_name, xls_path):
    try:
        y, _, m = parse_sheet_name(sheet_name, xls_path)
        return (int(y), m)
    except Exception:
        return (0, 0)

def parse_sheet_name(sheet_name, xls_path=None, records=None):
    normalized = sheet_name.replace(" ", "").replace(".", "")
    match = re.match(r"^([ก-๙]+)(\d+)$", normalized)
    month_part = ""
    if match:
        month_part = match.group(1)
        year_part = int(match.group(2))
        full_year = 2500 + year_part
        year_num = str(full_year)
    else:
        month_match = re.search(r"([ก-๙]+)", normalized)
        if month_match:
            month_part = month_match.group(1)
        else:
            month_part = normalized
        year_num = "2569"
        if xls_path and os.path.exists(xls_path):
            try:
                xl = pd.ExcelFile(xls_path)
                df = xl.parse(sheet_name, nrows=1)
                if not df.empty:
                    header_text = str(df.columns[0])
                    year_match = re.search(r"25\d{2}", header_text)
                    if year_match:
                        year_num = year_match.group(0)
            except Exception:
                pass
        elif records:
            for rec in records:
                date_str = rec.get("date", "")
                if date_str and "/" in date_str:
                    parts = date_str.split("/")
                    if len(parts) == 3 and parts[2].isdigit():
                        year_num = parts[2]
                        break

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
    
    month_num = 6
    portal_month_val = "69"
    matched = False
    for k, (m_num, p_val) in month_map.items():
        if k in month_part:
            month_num = m_num
            portal_month_val = p_val
            matched = True
            break
            
    if not matched:
        full_names = {
            "มกรา": 1, "กุมภา": 2, "มีนา": 3, "เมษา": 4, "พฤษภา": 5, "มิถุนา": 6,
            "กรกฎา": 7, "สิงหา": 8, "กันยา": 9, "ตุลา": 10, "พฤศจิกา": 11, "ธันวา": 12
        }
        for k, m_num in full_names.items():
            if k in month_part:
                month_num = m_num
                fiscal_order = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]
                if m_num in fiscal_order:
                    idx = fiscal_order.index(m_num)
                    portal_month_val = str(61 + idx)
                matched = True
                break
                
    return year_num, portal_month_val, month_num

def clean_excel_val(val):
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    return val_str

# Keywords that are tool/method names, NOT physical locations
_TOOL_KEYWORDS = [
    "ประชาสัมพันธ์", "ชี้แจง", "แผ่นพับ", "สาธิต",
    "อบรม", "บรรยาย", "สัมมนา", "ฝึกอบรม",
    "เอกสาร", "สื่อ", "วิทยุ", "โทรทัศน์",
    "ออนไลน์", "Line", "Facebook"
]

def _normalize_office_place(office_name):
    """PD_PLACE for office work: สำนักงานเกษตรอำเภอ… only (no moo/tambon)."""
    office = (office_name or "").strip() or "สำนักงานเกษตรอำเภอเมือง"
    if "สำนักงานเกษตรอำเภอ" in office:
        return office
    short = re.sub(r"^สนง\.?\s*กษอ\.?\s*", "", office, flags=re.I)
    short = re.sub(r"^สนง\.?\s*เกษตรอำเภอ\s*", "", short, flags=re.I)
    short = re.sub(r"^สำนักงาน\s*เกษตรอำเภอ\s*", "", short, flags=re.I).strip()
    return f"สำนักงานเกษตรอำเภอ{short}" if short else office


def sanitize_location(location, tool_name, tambon, issue_val, office_name=None, default_tambon=None):
    """Ensure location is a real physical place, not a tool/method name."""
    office = _normalize_office_place(office_name)
    default_tb = (default_tambon or "").strip()
    if default_tb and not default_tb.startswith("ตำบล") and not default_tb.startswith("แขวง"):
        default_tb = f"ตำบล{default_tb}"

    if str(issue_val) == "1":
        return office

    is_invalid = False

    if not location or location == "nan":
        is_invalid = True
    elif any(kw in location for kw in _TOOL_KEYWORDS):
        is_invalid = True
    elif "ตำบล" in location and ("…" in location or "..." in location or ".." in location):
        is_invalid = True
    elif tool_name and tool_name != "nan" and (location.strip() == tool_name.strip() or location.strip() in tool_name):
        is_invalid = True

    if is_invalid:
        fallback = tambon if tambon and tambon != "nan" else ""
        if fallback and not str(fallback).startswith("ตำบล") and not str(fallback).startswith("แขวง"):
            fallback = f"ตำบล{fallback}"
        return fallback if fallback else (default_tb or office)

    return location

def select_by_value_js(page, selector, value):
    page.evaluate(f"""() => {{
        const select = document.querySelector('{selector}');
        if (select) {{
            select.value = '{value}';
            select.dispatchEvent(new Event('change'));
        }}
    }}""")

def select_by_label_js(page, selector, label):
    page.evaluate(f"""() => {{
        const select = document.querySelector('{selector}');
        if (select) {{
            const option = Array.from(select.options).find(o => o.text.trim() === '{label}');
            if (option) {{
                select.value = option.value;
                select.dispatchEvent(new Event('change'));
            }}
        }}
    }}""")

_THAI_DIGIT_MAP = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

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


def thai_to_arabic(text):
    return str(text or "").translate(_THAI_DIGIT_MAP)


def parse_target_num(target_raw):
    text = thai_to_arabic(target_raw).strip()
    if not text or text.lower() == "nan":
        return 0
    if "ทุกท่าน" in text or "ทุกคน" in text or "จนท" in text:
        return 7
    digits = re.findall(r"\d+", text)
    if digits:
        try:
            return int("".join(digits) if len(digits) == 1 else digits[0])
        except ValueError:
            return 0
    return 0


_PLAN_MONTH_ALIASES = [
    ("ม.ค", 1), ("มค", 1), ("มกรา", 1),
    ("ก.พ", 2), ("กพ", 2), ("กุมภา", 2),
    ("มี.ค", 3), ("มีค", 3), ("มีนา", 3),
    ("เม.ย", 4), ("เมย", 4), ("เมษา", 4),
    ("พ.ค", 5), ("พค", 5), ("พฤษภา", 5),
    ("มิ.ย", 6), ("มิย", 6), ("มิถุนา", 6),
    ("ก.ค", 7), ("กค", 7), ("กรกฎา", 7),
    ("ส.ค", 8), ("สค", 8), ("สิงหา", 8),
    ("ก.ย", 9), ("กย", 9), ("กันยา", 9),
    ("ต.ค", 10), ("ตค", 10), ("ตุลา", 10),
    ("พ.ย", 11), ("พย", 11), ("พฤศจิกา", 11),
    ("ธ.ค", 12), ("ธค", 12), ("ธันวา", 12),
]


def parse_visit_plan_dates(date_raw, default_month, default_year_be):
    """Parse '๓ ส.ค. ๖๙' or '๕-๗ ส.ค. ๖๙' → list of BE dates DD/MM/YYYY."""
    text = thai_to_arabic(date_raw).strip()
    if not text or text.lower() == "nan":
        return []
    compact = text.replace(" ", "").replace(".", "")
    month = default_month
    for alias, mnum in _PLAN_MONTH_ALIASES:
        a = alias.replace(".", "")
        if a in compact:
            month = mnum
            break
    year = int(default_year_be)
    years = re.findall(r"(\d{2,4})", text)
    if years:
        y = int(years[-1])
        year = 2500 + y if y < 100 else y
    # day range or single day
    range_m = re.search(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})", text)
    if range_m:
        d1, d2 = int(range_m.group(1)), int(range_m.group(2))
        if d2 < d1:
            d1, d2 = d2, d1
        return [f"{d:02d}/{month:02d}/{year}" for d in range(d1, d2 + 1)]
    day_m = re.search(r"(\d{1,2})", text)
    if not day_m:
        return []
    day = int(day_m.group(1))
    return [f"{day:02d}/{month:02d}/{year}"]


def detect_excel_table_format(df):
    """Return ('visit_plan'|'legacy', header_row_index)."""
    for i in range(min(12, len(df))):
        cells = [str(c).strip() for c in df.iloc[i].tolist()]
        joined = " ".join(cells)
        # Two-row headers: join with next row for keyword detection
        if i + 1 < len(df):
            next_cells = [str(c).strip() for c in df.iloc[i + 1].tolist()]
            joined_2 = joined + " " + " ".join(next_cells)
        else:
            joined_2 = joined
        # Legacy visit sheet from สนง. (มีคอลัมน์เครื่องมือ/สถานที่)
        if "เครื่องมือ" in joined or ("สถานที่" in joined and ("วัน" in joined or "วันที่" in joined)):
            return "legacy", i
        if "กิจกรรม" in joined_2 and ("บุคคลเป้าหมาย" in joined_2 or "เป้าหมาย" in joined_2):
            # Prefer visit_plan only when ไม่มีคอลัมน์เครื่องมือแบบแผนเยี่ยมเยียนเต็ม
            if "เครื่องมือ" not in joined_2:
                return "visit_plan", i
    return "legacy", None


def _find_col(headers, *keywords):
    for idx, h in enumerate(headers):
        hs = str(h)
        if any(k in hs for k in keywords):
            return idx
    return None


def load_visit_plan_records(df, header_row, sheet_name, office_name=None, default_tambon=None):
    """
    แผนเยี่ยมเยียนระดับบุคคลที่หัวหน้าส่งรายเดือน
    คอลัมน์: สัปดาห์ที่ | วันเดือนปี | กิจกรรม | บุคคลเป้าหมาย | ผู้ร่วม | หมายเหตุ
    """
    try:
        year_num, portal_month_val, month_num = parse_sheet_name(sheet_name)
    except Exception:
        year_num, portal_month_val, month_num = "2569", "71", 8

    headers = [str(c).strip() for c in df.iloc[header_row].tolist()]
    col_date = _find_col(headers, "วัน", "วันที่")
    col_act = _find_col(headers, "กิจกรรม")
    col_target = _find_col(headers, "บุคคลเป้าหมาย", "เป้าหมาย")
    col_join = _find_col(headers, "ร่วมปฏิบัติ", "เจ้าหน้าที่")
    if col_date is None:
        col_date = 1
    if col_act is None:
        col_act = 2
    if col_target is None:
        col_target = 3

    records = []
    row_no = 0
    for idx in range(header_row + 1, len(df)):
        row = df.iloc[idx]
        date_raw = row.iloc[col_date] if col_date < len(row) else ""
        activity_raw = row.iloc[col_act] if col_act < len(row) else ""
        target_raw = row.iloc[col_target] if col_target < len(row) else ""
        join_raw = row.iloc[col_join] if col_join is not None and col_join < len(row) else ""

        if pd.isna(date_raw) and pd.isna(activity_raw):
            continue
        date_str = str(date_raw).strip() if not pd.isna(date_raw) else ""
        activity = str(activity_raw).strip() if not pd.isna(activity_raw) else ""
        if (not date_str or date_str.lower() == "nan") and (not activity or activity.lower() == "nan"):
            continue
        # Skip repeated header / week-only rows without activity
        if "กิจกรรม" in activity or activity in ("nan",):
            continue
        if not activity:
            continue

        dates = parse_visit_plan_dates(date_str, month_num, int(year_num))
        if not dates:
            # fallback: first number as day in sheet month
            be = parse_date_to_be(thai_to_arabic(date_str), month_num, int(year_num))
            dates = [be] if be else []
        if not dates:
            continue

        target_num = parse_target_num(target_raw)
        co_workers = str(join_raw).strip() if not pd.isna(join_raw) else ""
        if co_workers.lower() == "nan":
            co_workers = ""

        issue_val, activity_val, other_text = map_activity(activity, "")
        for be_date in dates:
            row_no += 1
            records.append({
                "id": row_no,
                "excel_date": date_str,
                "date": be_date,
                "activity": activity,
                "tool": "",
                "location": "",
                "tambon": default_tambon or "",
                "target_raw": str(target_raw).strip() if not pd.isna(target_raw) else "",
                "target_num": target_num,
                "co_workers": co_workers,
                "issue_val": issue_val,
                "activity_val": activity_val,
                "other_text": other_text,
                "source_format": "visit_plan",
            })

    return apply_sida_office_meeting_rules(records, office_name=office_name)


def load_excel_records(xls_path, sheet_name="มิ.ย.69", office_name=None, default_tambon=None):
    if not os.path.exists(xls_path):
        return []

    try:
        year_num, portal_month_val, month_num = parse_sheet_name(sheet_name, xls_path=xls_path)
    except Exception as ex:
        year_num, portal_month_val, month_num = "2569", "69", 6

    xl = pd.ExcelFile(xls_path)
    df = xl.parse(sheet_name)
    fmt, header_row = detect_excel_table_format(df)
    if fmt == "visit_plan":
        return load_visit_plan_records(
            df, header_row, sheet_name,
            office_name=office_name, default_tambon=default_tambon
        )

    records = []
    row_no = 0
    # Skip sub-header row ("ที่" / "เป้าหมาย") when present under main header
    start_idx = (header_row + 1) if header_row is not None else 4
    if header_row is not None and header_row + 1 < len(df):
        sub = " ".join(str(c) for c in df.iloc[header_row + 1].tolist())
        if "เป้าหมาย" in sub or str(df.iloc[header_row + 1].iloc[0]).strip() in ("ที่", "nan", ""):
            start_idx = header_row + 2

    for idx in range(start_idx, len(df)):
        row = df.iloc[idx]
        date_raw = row.iloc[1] if len(row) > 1 else ""
        activity_raw = row.iloc[2] if len(row) > 2 else ""
        tool_raw = row.iloc[3] if len(row) > 3 else ""
        location_raw = row.iloc[4] if len(row) > 4 else ""
        target_raw = row.iloc[5] if len(row) > 5 else ""
        co_workers_raw = row.iloc[6] if len(row) > 6 else ""
        tambon_raw = row.iloc[7] if len(row) > 7 else ""

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
        if "กิจกรรม" in activity or activity in ("nan",):
            continue
        if not activity:
            continue

        # Expand Thai day ranges (เช่น ๕-๗ ส.ค. ๖๙) into multiple rows
        dates = parse_visit_plan_dates(date_str, month_num, int(year_num))
        if not dates:
            be_one = parse_date_to_be(date_str, month_num, int(year_num))
            dates = [be_one] if be_one else []
        if not dates:
            continue

        override_issue = clean_excel_val(row.iloc[8]) if len(row) > 8 and not pd.isna(row.iloc[8]) else ""
        override_activity = clean_excel_val(row.iloc[9]) if len(row) > 9 and not pd.isna(row.iloc[9]) else ""
        override_other = clean_excel_val(row.iloc[10]) if len(row) > 10 and not pd.isna(row.iloc[10]) else ""
        override_location = clean_excel_val(row.iloc[11]) if len(row) > 11 and not pd.isna(row.iloc[11]) else ""
        override_target = clean_excel_val(row.iloc[12]) if len(row) > 12 and not pd.isna(row.iloc[12]) else ""

        issue_val, activity_val, other_text = map_activity(activity, tool)

        if override_issue:
            issue_val = override_issue
        if override_activity:
            activity_val = override_activity
        if override_other:
            other_text = override_other

        resolved_location = sanitize_location(
            location, tool, tambon, issue_val,
            office_name=office_name, default_tambon=default_tambon or tambon
        )

        if override_location:
            resolved_location = override_location

        target_num = parse_target_num(target)
        if override_target and str(override_target).isdigit():
            target_num = int(override_target)

        for be_date in dates:
            row_no += 1
            records.append({
                "id": row_no,
                "excel_date": date_str,
                "date": be_date,
                "activity": activity,
                "tool": tool,
                "location": resolved_location,
                "tambon": tambon or (default_tambon or ""),
                "target_raw": target,
                "target_num": target_num,
                "co_workers": co_workers,
                "issue_val": issue_val,
                "activity_val": activity_val,
                "other_text": other_text,
                "source_format": "legacy",
            })
    return apply_sida_office_meeting_rules(records, office_name=office_name)

def load_excel_records_with_gemini(xls_path, sheet_name, api_key, office_name=None, default_tambon=None):
    if not os.path.exists(xls_path):
        return []

    office = _normalize_office_place(office_name)
    default_tb = (default_tambon or "").strip() or "ตำบล"
    if default_tb and not default_tb.startswith("ตำบล") and not default_tb.startswith("แขวง"):
        default_tb_display = f"ตำบล{default_tb}"
    else:
        default_tb_display = default_tb

    try:
        year_num, portal_month_val, month_num = parse_sheet_name(sheet_name, xls_path=xls_path)
    except Exception as ex:
        year_num, portal_month_val, month_num = "2569", "69", 6
        
    xl = pd.ExcelFile(xls_path)
    df = xl.parse(sheet_name)
    
    raw_rows = []
    row_no = 0
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
            
        be_date = parse_date_to_be(date_str, month_num, int(year_num))
        
        row_no += 1
        raw_rows.append({
            "id": row_no,
            "excel_date": date_str,
            "date": be_date,
            "activity_raw": activity,
            "tool_raw": tool,
            "location_raw": location,
            "target_raw": target,
            "co_workers": co_workers,
            "tambon_raw": tambon
        })
        
    if not raw_rows:
        return []

    client = genai.Client(api_key=api_key)
    
    prompt = """คุณเป็นผู้เชี่ยวชาญด้านระบบ T&V (Training and Visit) ของกรมส่งเสริมการเกษตร (DOAE)
หน้าที่ของคุณคือวิเคราะห์แต่ละแถวจากแผนปฏิบัติงานรายเดือน (Excel) แล้วจำแนกข้อมูลให้ตรงกับรหัสที่ใช้ในระบบ T&V Portal (Workflow 26) อย่างแม่นยำ

═══════════════════════════════════════════════════════════════
ส่วนที่ 1: ตารางรหัสประเด็นงาน (issue_val) และกิจกรรมหลัก (activity_val)
═══════════════════════════════════════════════════════════════

┌──────────────────────────────────────────────────────────────
│ ประเด็น 1: การถ่ายทอดความรู้ (TRAINING/MEETING) │ issue_val = "1"
│
│ activity_val │ ชื่อกิจกรรม                          │ คำสำคัญในข้อมูลดิบ (Keywords)
│ ────────────┼──────────────────────────────────────┼──────────────────────────────
│ "14"        │ ประชุมสัปดาห์ (Weekly Meeting: WM)   │ WM, ประชุมสัปดาห์, ประชุมประจำสัปดาห์, Weekly
│ "13"        │ ประชุมอำเภอ (District Meeting: DM)   │ DM, ประชุมอำเภอ, ประชุมสำนักงานเกษตรอำเภอ, District Meeting
│ "12"        │ ประชุมเดือน (Monthly Meeting: MM)    │ MM, ประชุมเดือน, ประชุมประจำเดือน, Monthly Meeting
│ "11"        │ ประชุมจังหวัด (Provincial Meeting: PM)│ PM, ประชุมจังหวัด, ประชุมสำนักงานเกษตรจังหวัด
│ "1"         │ สัมมนาระดับชาติ (National Workshop: NW)│ NW, สัมมนาระดับชาติ, ประชุมกรม
│ "6"         │ สัมมนาระดับเขต (Regional Workshop: RW)│ RW, สัมมนาเขต, ประชุมเขต
│ "7"         │ สัมมนาระดับจังหวัด (Provincial Workshop: PW)│ PW, อบรมจังหวัด, สัมมนาจังหวัด
│ "8"         │ สัมมนาระดับอำเภอ (District Workshop: DW)│ DW, อบรมอำเภอ, สัมมนาอำเภอ
│ "9"         │ ประชุมผู้บริหารระดับกรม               │ ผู้บริหารกรม, ประชุมกรม
│ "10"        │ ประชุมหัวหน้าส่วนราชการระดับเขต       │ หัวหน้าส่วนเขต, ประชุมเขต
│ "999"       │ อื่นๆ (Other training/meetings)      │ ประชุมที่ไม่ตรงกับรหัสข้างต้น, ประชุมชี้แจง, ประชุมนอกรอบ
│
│ ⚠️ เงื่อนไขสำคัญ: ถ้ากิจกรรมเป็น "ประชุม" แต่ในชื่อกิจกรรมมีคำเกี่ยวกับโครงการเฉพาะ
│    (เช่น "ประชุมแปลงใหญ่", "ประชุมวิสาหกิจชุมชน") → จัดเป็นประเด็น 2 (VISITING) ตามโครงการนั้น
│    ไม่ใช่ประเด็น 1 เพราะ "ประชุม" เป็นแค่วิธีการ แต่เนื้อหาคือเยี่ยมเยียน
└──────────────────────────────────────────────────────────────

┌──────────────────────────────────────────────────────────────
│ ประเด็น 2: การเยี่ยมเยียน (VISITING/FIELDWORK) │ issue_val = "2"
│
│ activity_val │ ชื่อกิจกรรม                          │ คำสำคัญ / ตัวอย่างข้อมูลดิบ
│ ────────────┼──────────────────────────────────────┼──────────────────────────────
│ "2"         │ ศพก. (ศูนย์เรียนรู้ฯ)               │ ศพก, ศพก., ศูนย์เรียนรู้, ศูนย์เรียนรู้เพิ่มประสิทธิภาพ
│ "15"        │ เกษตรแปลงใหญ่                        │ แปลงใหญ่, เกษตรแปลงใหญ่, นาแปลงใหญ่
│ "16"        │ Smart Farmer / Young Smart Farmer    │ Smart Farmer, SF, YSF, สมาร์ทฟาร์มเมอร์, เกษตรกรปราดเปรื่อง
│ "17"        │ Zoning by Agri-Map                   │ Zoning, Agri-Map, โซนนิ่ง
│ "18"        │ โครงการอันเนื่องมาจากพระราชดำริ       │ พระราชดำริ, โครงการหลวง, เศรษฐกิจพอเพียง
│ "19"        │ วิสาหกิจชุมชน                        │ วิสาหกิจชุมชน, วสช, กลุ่มวิสาหกิจ
│ "20"        │ กลุ่มเกษตรกร / กลุ่มแม่บ้าน          │ กลุ่มเกษตรกร, กลุ่มแม่บ้าน, องค์กรเกษตรกร, พัฒนาเกษตรกร, 3ก, สมาชิกกลุ่ม, กลุ่มส่งเสริม
│ "21"        │ เกษตรทฤษฎีใหม่                       │ ทฤษฎีใหม่, เกษตรทฤษฎีใหม่
│ "22"        │ เกษตรอินทรีย์                        │ เกษตรอินทรีย์, อินทรีย์, GAP, 5 ดี, 5ดี, เกษตรปลอดภัย
│ "23"        │ ตลาดสินค้าเกษตร                      │ ตลาดเกษตร, ตลาดสินค้า, ตลาด, จำหน่ายสินค้า
│ "24"        │ พัฒนาคุณภาพสินค้าเกษตร / สุขภาพพืช   │ คุณภาพสินค้า, มาตรฐานสินค้า, ยกระดับคุณภาพ, สุขภาพพืช, จัดการศัตรูพืช, IPM
│ "25"        │ บริหารจัดการทรัพยากรน้ำ               │ ทรัพยากรน้ำ, จัดการน้ำ, ชลประทาน, แหล่งน้ำ
│ "26"        │ พัฒนาสถาบันเกษตรกรรูปแบบประชารัฐ      │ ประชารัฐ, สถาบันเกษตรกร
│ "27"        │ ธนาคารสินค้าเกษตร                    │ ธนาคารสินค้า, ธนาคารเกษตร
│ "28"        │ จัดระเบียบการประมง                    │ ประมง, IUU
│ "29"        │ ส่งเสริมเครื่องจักรกล                │ เครื่องจักร, เครื่องจักรกล, จักรกลเกษตร
│ "30"        │ ช่วยเหลือด้านหนี้สิน                 │ หนี้สิน, ปัญหาหนี้, สินเชื่อ
│ "31"        │ แผนผลิตข้าวครบวงจร                   │ ข้าวครบวงจร, แผนข้าว
│ "999"       │ อื่นๆ                                │ เยี่ยมเยียนทั่วไป, ลงพื้นที่, สำรวจ, ติดตามงาน, เยี่ยมเกษตรกร,
│             │                                      │ ส่งเสริมการปลูก, ถ่ายทอดเทคโนโลยี, สิ่งแวดล้อม, งานรณรงค์, งานวันถ่ายทอด
│
│ ℹ️ ประเด็น 2 เป็นประเด็นเริ่มต้น (default) — ถ้ากิจกรรมเป็นงานภาคสนาม/เยี่ยมเยียน
│    แต่ไม่ตรงกับรหัสเฉพาะใดเลย → ใช้ activity_val = "999" พร้อมสรุป other_text
└──────────────────────────────────────────────────────────────

┌──────────────────────────────────────────────────────────────
│ ประเด็น 3: การสนับสนุน (SUPPORTING) │ issue_val = "3"
│
│ activity_val │ ชื่อกิจกรรม                          │ คำสำคัญ
│ ────────────┼──────────────────────────────────────┼──────────────────────────────
│ "3"         │ ด้านโครงสร้างและอุปกรณ์               │ อุปกรณ์, สนับสนุนวัสดุ, โครงสร้างพื้นฐาน, ซ่อมบำรุง
│ "33"        │ เพิ่มสมรรถนะและสร้างขวัญกำลังใจ       │ สร้างขวัญ, เพิ่มสมรรถนะ, กำลังใจ, สวัสดิการ
│ "34"        │ ด้านวิชาการ                          │ สนับสนุนวิชาการ, เอกสารวิชาการ
│ "999"       │ อื่นๆ                                │ สนับสนุนอื่นๆ
└──────────────────────────────────────────────────────────────

┌──────────────────────────────────────────────────────────────
│ ประเด็น 4: การนิเทศงาน (SUPERVISION) │ issue_val = "4"
│
│ activity_val │ ชื่อกิจกรรม                          │ คำสำคัญ
│ ────────────┼──────────────────────────────────────┼──────────────────────────────
│ "999"       │ อื่นๆ                                │ นิเทศ, นิเทศงาน, ตรวจเยี่ยมราชการ, ตรวจติดตาม (จากผู้บังคับบัญชา)
│
│ ⚠️ "นิเทศ" = ผู้บังคับบัญชามาตรวจงาน ≠ "เยี่ยมเยียน" = เจ้าหน้าที่ลงพื้นที่เยี่ยมเกษตรกร
└──────────────────────────────────────────────────────────────

┌──────────────────────────────────────────────────────────────
│ ประเด็น 5: การจัดการข้อมูล (DATA MANAGEMENT) │ issue_val = "5"
│
│ activity_val │ ชื่อกิจกรรม                          │ คำสำคัญ
│ ────────────┼──────────────────────────────────────┼──────────────────────────────
│ "4"         │ ด้านข้อมูลสารสนเทศ                   │ ทะเบียนเกษตรกร, ทบก, ปรับปรุงทะเบียน, ขึ้นทะเบียน, ระบบสารสนเทศ,
│             │                                      │ บันทึกข้อมูล, คีย์ข้อมูล, จัดทำข้อมูล, ฐานข้อมูล, รายงานข้อมูล
│ "36"        │ ด้านแผนพัฒนาการเกษตร                 │ แผนพัฒนา, แผนการเกษตร, จัดทำแผน
│ "999"       │ อื่นๆ                                │ งานจัดการข้อมูลอื่นๆ, งานสารบรรณ, งานธุรการ
└──────────────────────────────────────────────────────────────


═══════════════════════════════════════════════════════════════
ส่วนที่ 2: กฎการจำแนกประเภทและลำดับการตัดสิน (Classification Rules & Priority)
═══════════════════════════════════════════════════════════════

ขั้นตอน A: ตรวจสอบว่าแถวเป็นกิจกรรมจริงหรือไม่ → กำหนด should_include

  ✅ should_include = true เมื่อ:
    - มีวันที่ (date) + มีชื่อกิจกรรม (activity_raw) อธิบายการทำงานจริง
    - เป็นกิจกรรมประจำวัน เช่น ลงพื้นที่, ประชุม, อบรม, เยี่ยมเยียน, ทำทะเบียน
    - แม้ activity_raw จะมีแค่คำสั้นๆ เช่น "ลงพื้นที่" ก็ถือว่าเป็นกิจกรรมจริง

  ❌ should_include = false เมื่อ:
    - เป็นวันหยุดราชการ, วันหยุดนักขัตฤกษ์ (เช่น "วันวิสาขบูชา", "วันจักรี", "วันแรงงาน")
    - เป็นวันหยุดเสาร์-อาทิตย์ ที่ activity_raw ว่างเปล่าหรือเขียนว่า "หยุด", "หยุดราชการ", "วันหยุด"
    - เป็นวันลา (เช่น "ลาพักผ่อน", "ลาป่วย", "ลากิจ")
    - activity_raw ว่างเปล่า, เป็น nan, เป็น "-" หรือเป็นแค่หมายเหตุ/หัวข้อ
    - มีเฉพาะวันที่แต่ไม่มีกิจกรรม (ไม่มีเนื้องาน)

ขั้นตอน B: จำแนกประเด็นงานและกิจกรรม → issue_val + activity_val

  ลำดับการพิจารณา (Priority - ตรวจตามลำดับ หยุดที่ข้อแรกที่ตรง):

  1. ตรวจคำสำคัญเฉพาะทาง (Specific Keywords First):
     - ถ้ามีคำว่า "ทะเบียนเกษตรกร" หรือ "ทบก" → issue "5", activity "4"
     - ถ้ามีคำว่า "ศพก" → issue "2", activity "2"
     - ถ้ามีคำว่า "แปลงใหญ่" → issue "2", activity "15"
     - ถ้ามีคำว่า "วิสาหกิจชุมชน" → issue "2", activity "19"
     - ถ้ามีคำว่า "Smart Farmer" หรือ "สมาร์ทฟาร์ม" → issue "2", activity "16"
     - ถ้ามีคำว่า "อินทรีย์" หรือ "GAP" หรือ "5 ดี" → issue "2", activity "22"
     - ถ้ามีคำว่า "นิเทศ" → issue "4", activity "999"
     (... ตรวจคำสำคัญอื่นๆ ตามตารางด้านบนให้ครบทุก activity_val)

  2. ถ้ามีคำว่า "ประชุม" + ไม่มีคำเฉพาะโครงการ → issue "1":
     - แยกประเภทย่อยตามคำต่อท้าย: WM/สัปดาห์ → "14", DM/อำเภอ → "13", MM/ประจำเดือน → "12" ฯลฯ
     - ถ้าไม่ตรงกับรหัสย่อยใด → issue "1", activity "999"

  3. ถ้าไม่ตรงกับรหัสเฉพาะใดเลย → ใช้ issue "2", activity "999":
     - กรณีนี้ต้องกำหนด other_text เป็นคำสรุปภาษาไทยสั้นๆ ไม่เกิน 30 ตัวอักษร
     - เช่น: "ลงพื้นที่ติดตามงาน" → other_text = "ติดตามงานในพื้นที่"
     - เช่น: "รณรงค์ไม่เผาตอซัง" → other_text = "รณรงค์สิ่งแวดล้อม"

ขั้นตอน C: กำหนด other_text

  - ถ้า activity_val ไม่ใช่ "999" → other_text = "" (เว้นว่าง)
  - ถ้า activity_val = "999" → other_text = คำอธิบายสั้นๆ ภาษาไทย (ไม่เกิน 30 ตัวอักษร)
    - ห้ามใช้ชื่อกิจกรรมดิบทั้งข้อความ ให้สรุปใจความหลักเท่านั้น
    - ตัวอย่าง:
      * "ติดตามสถานการณ์น้ำท่วมพื้นที่การเกษตร" → "ติดตามน้ำท่วม"
      * "จัดงานวันถ่ายทอดเทคโนโลยี (Field Day)" → "งาน Field Day"
      * "ลงพื้นที่ส่งเสริมการปลูกข้าวโพดเลี้ยงสัตว์หลังฤดูทำนา" → "ส่งเสริมข้าวโพดหลังนา"
      * "ร่วมพิธีเปิดงานเกษตรแห่งชาติ" → "พิธีเปิดงานเกษตร"


═══════════════════════════════════════════════════════════════
ส่วนที่ 3: กฎสถานที่ (Location Rules)
═══════════════════════════════════════════════════════════════

กฎหลัก: สถานที่ (location) ต้องเป็นสถานที่ทางกายภาพจริงเท่านั้น

  ชื่อสำนักงานเกษตรอำเภอของพื้นที่นี้: """ + office + """
  ตำบลเริ่มต้นของพื้นที่นี้: """ + default_tb_display + """

  1. ถ้า issue_val = "1" (ประชุม/อบรม):
     → location = ชื่อสำนักงานเกษตรอำเภอข้างต้น เสมอ

  2. ถ้า issue_val ≠ "1":
     → ใช้ location_raw ที่เป็นชื่อสถานที่จริง เช่น ชื่อหมู่บ้าน, หมู่, ตำบล, ศพก.
     → แต่ถ้า location_raw เป็นสิ่งต่อไปนี้ ให้ถือว่าไม่ถูกต้อง:
       ❌ คำที่เป็นวิธีการ/เครื่องมือ: "ชี้แจง/ประชาสัมพันธ์", "แผ่นพับ", "ประชุม",
          "สาธิต", "อบรม", "เอกสาร", "Line", "Facebook", "ออนไลน์"
       ❌ คำที่มีจุดไข่ปลา: "ตำบล…...", "ตำบล...", "....."
       ❌ ค่าว่างเปล่า, "nan", "-"
     → เมื่อ location_raw ไม่ถูกต้อง:
       • ใช้ค่า tambon_raw แทน (เติมคำว่า ตำบล ถ้าจำเป็น)
       • ถ้า tambon_raw ก็ว่าง → ใช้ตำบลเริ่มต้นของพื้นที่นี้

  3. ถ้า location_raw เป็นชื่อตำบลเปล่าๆ:
     → เติมคำนำหน้า "ตำบล"


═══════════════════════════════════════════════════════════════
ส่วนที่ 4: กฎการแปลงเป้าหมาย (target_num Rules)
═══════════════════════════════════════════════════════════════

แปลง target_raw → target_num (integer) ตามลำดับ:

  1. ถ้ามีตัวเลขชัดเจน → ดึงตัวเลขออกมา
     - "15 ราย" → 15
     - "เกษตรกร 20 คน" → 20
     - "30" → 30
     - "3-5 ราย" → ใช้จำนวนสูงสุด → 5
     - "จนท 4 คน + เกษตรกร 10 ราย" → รวมเป็น 14

  2. ถ้าเป็นคำไม่ระบุจำนวนชัดเจน → default = 7
     - "จนท" หรือ "จนท." → 7
     - "ทุกคน", "ทุกท่าน" → 7
     - "เจ้าหน้าที่" → 7
     - "คณะทำงาน" → 7

  3. ถ้าไม่มีข้อมูลหรือเป็นค่าว่าง → default = 0
     - "", "nan", "-" → 0


═══════════════════════════════════════════════════════════════
ส่วนที่ 5: กรณีพิเศษและข้อยกเว้น (Edge Cases)
═══════════════════════════════════════════════════════════════

  1. กิจกรรมซ้ำหลายวัน: แต่ละแถวมี id เป็นเอกลักษณ์ → วิเคราะห์แยกทีละแถว อย่ารวม
  2. วันที่มีหลายกิจกรรม: แต่ละแถวคือหนึ่งกิจกรรม → ให้ issue_val/activity_val ตามกิจกรรมของแถวนั้น
  3. กิจกรรมกำกวม: ถ้าตัดสินใจไม่ได้ → ใช้ issue_val = "2", activity_val = "999"
  4. ข้อมูลซ้ำใน activity_raw กับ tool_raw: พิจารณาจาก activity_raw เป็นหลัก tool_raw เป็นข้อมูลเสริม
  5. ตัวอักษรย่อ: WM = Weekly, DM = District, MM = Monthly, PM = Provincial, NW/RW/PW/DW = Workshop ระดับต่างๆ
  6. คำว่า "ประชุม" + ชื่อโครงการ: จัดตามโครงการ (issue 2) ไม่ใช่ตามประชุม (issue 1)
     - "ประชุมแปลงใหญ่" → issue "2", activity "15"
     - "ประชุมกลุ่มวิสาหกิจชุมชน" → issue "2", activity "19"
     - "ประชุมประจำเดือน" → issue "1", activity "12"

═══════════════════════════════════════════════════════════════
ส่วนที่ 6: ข้อมูลดิบจาก Excel (Input Data)
═══════════════════════════════════════════════════════════════

""" + json.dumps(raw_rows, ensure_ascii=False, indent=2) + """

═══════════════════════════════════════════════════════════════
ส่วนที่ 7: รูปแบบ JSON ที่ต้องการ (Required Output Format)
═══════════════════════════════════════════════════════════════

ตอบเป็น JSON Array เท่านั้น ห้ามมีข้อความอื่นนอก JSON
แต่ละ object ต้องมี key ครบทุกตัวตามนี้:

{
  "id":              (integer - ตรงกับ id ของ input row),
  "should_include":  (boolean - true = กิจกรรมจริง, false = หยุด/ลา/ว่าง),
  "issue_val":       (string - "1"|"2"|"3"|"4"|"5"),
  "activity_val":    (string - รหัสกิจกรรมย่อย เช่น "14", "2", "999"),
  "other_text":      (string - คำอธิบายถ้า activity_val="999", มิฉะนั้น ""),
  "location":        (string - สถานที่ทางกายภาพจริง),
  "target_num":      (integer - จำนวนเป้าหมาย/คน)
}

ตัวอย่าง Output:
[
  {"id": 1, "should_include": true, "issue_val": "1", "activity_val": "12", "other_text": "", "location": """ + office + """, "target_num": 7},
  {"id": 2, "should_include": false, "issue_val": "2", "activity_val": "999", "other_text": "", "location": "", "target_num": 0},
  {"id": 3, "should_include": true, "issue_val": "2", "activity_val": "19", "other_text": "", "location": """ + default_tb_display + """, "target_num": 15}
]
"""

    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt,
        config={'response_mime_type': 'application/json'}
    )
    
    gemini_data = json.loads(response.text)
    
    records = []
    gemini_map = {item["id"]: item for item in gemini_data}
    
    for row in raw_rows:
        row_id = row["id"]
        g_item = gemini_map.get(row_id)
        if not g_item or not g_item.get("should_include", True):
            continue
        
        # Post-process: validate location is a real place, not a tool name
        raw_location = g_item.get("location", row["location_raw"])
        issue_val = g_item.get("issue_val", "2")
        validated_location = sanitize_location(
            raw_location, row["tool_raw"], row.get("tambon_raw", ""), issue_val,
            office_name=office, default_tambon=default_tb
        )

        records.append({
            "id": row_id,
            "excel_date": row["excel_date"],
            "date": row["date"],
            "activity": row["activity_raw"],
            "tool": row["tool_raw"],
            "location": validated_location,
            "tambon": row.get("tambon_raw", "") or default_tb,
            "target_raw": row["target_raw"],
            "target_num": g_item.get("target_num", 0),
            "co_workers": row["co_workers"],
            "issue_val": issue_val,
            "activity_val": g_item.get("activity_val", "999"),
            "other_text": g_item.get("other_text", "")
        })

    for i, rec in enumerate(records, start=1):
        rec["id"] = i
    return apply_sida_office_meeting_rules(records, office_name=office)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/docs/<path:filename>')
def serve_docs(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'docs'), filename)

@app.route('/README.md')
def serve_readme():
    return send_from_directory(BASE_DIR, 'README.md', mimetype='text/markdown')

@app.route('/robots.txt')
def serve_robots():
    """Serve robots.txt for SEO crawlers."""
    return send_from_directory(os.path.join(BASE_DIR, 'static'), 'robots.txt', mimetype='text/plain')

@app.route('/sitemap.xml')
def serve_sitemap():
    """Serve XML sitemap for SEO indexing."""
    return send_from_directory(os.path.join(BASE_DIR, 'static'), 'sitemap.xml', mimetype='application/xml')

@app.route('/api/health')
def health_check():
    meta = geo_data.load_meta()
    return jsonify({
        "status": "ok",
        "message": "T&V Automation Server is running",
        "geo": meta.get("counts", {}),
        "online": True
    })

@app.route('/api/geo/provinces')
def api_geo_provinces():
    return jsonify({"success": True, "provinces": geo_data.load_provinces()})

@app.route('/api/geo/amphoes')
def api_geo_amphoes():
    province_code = request.args.get('province_code', '').strip()
    if not province_code:
        return jsonify({"success": False, "error": "ต้องระบุ province_code"}), 400
    return jsonify({"success": True, "amphoes": geo_data.get_amphoes(province_code)})

@app.route('/api/geo/tambons')
def api_geo_tambons():
    amphoe_code = request.args.get('amphoe_code', '').strip()
    if not amphoe_code:
        return jsonify({"success": False, "error": "ต้องระบุ amphoe_code"}), 400
    return jsonify({"success": True, "tambons": geo_data.get_tambons(amphoe_code)})

@app.route('/api/geo/villages')
def api_geo_villages():
    tambon_code = request.args.get('tambon_code', '').strip()
    if not tambon_code:
        return jsonify({"success": False, "error": "ต้องระบุ tambon_code"}), 400
    villages = geo_data.get_villages(tambon_code)
    return jsonify({"success": True, "villages": villages})

@app.route('/api/districts')
def api_districts():
    """Thin wrapper: presets + resolved สีดา quick-select."""
    sida = geo_data.resolve_sida_codes()
    presets = geo_data.load_presets()
    # refresh sida preset with live codes
    out = []
    for p in presets:
        if p.get("id") == "sida":
            out.append(sida)
        else:
            out.append(p)
    if not any(p.get("id") == "sida" for p in out):
        out.insert(0, sida)
    return jsonify({"success": True, "presets": out, "sida": sida})

@app.route('/api/location-presets')
def api_location_presets():
    office_name = request.args.get('office_name', '').strip()
    tambon_name = request.args.get('tambon_name', '').strip()
    tambon_code = request.args.get('tambon_code', '').strip()
    villages = geo_data.get_villages(tambon_code) if tambon_code else []
    presets = geo_data.build_location_presets(office_name, tambon_name, villages)
    return jsonify({"success": True, "presets": presets})

@app.route('/api/add-row', methods=['POST'])
def add_row():
    """Create a blank row template for the frontend."""
    data = request.json or {}
    row_id = data.get('id', 0)
    office_name = data.get('office_name', '')
    tambon_name = data.get('tambon_name', '') or data.get('tambon', '')
    village_name = data.get('village_name', '')
    moo = data.get('moo', '')
    villages = data.get('villages') or ([village_name] if village_name else [])
    moos = data.get('moos') or ([moo] if moo else [])
    location = geo_data.default_location(
        office_name, tambon_name, village_name, moo, villages=villages, moos=moos
    )
    return jsonify({
        "success": True,
        "record": {
            "id": row_id,
            "excel_date": "",
            "date": "",
            "activity": "",
            "tool": "",
            "location": location,
            "tambon": tambon_name,
            "moo": (moos[0] if moos else moo),
            "moos": moos,
            "village": (villages[0] if villages else village_name),
            "villages": villages,
            "target_raw": "",
            "target_num": 0,
            "co_workers": "",
            "issue_val": "2",
            "activity_val": "999",
            "other_text": ""
        }
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "ไม่พบไฟล์ที่อัปโหลด"})
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "กรุณาเลือกไฟล์ Excel"})
        
    if not (file.filename.endswith('.xls') or file.filename.endswith('.xlsx')):
        return jsonify({"success": False, "error": "รูปแบบไฟล์ไม่ถูกต้อง กรุณาอัปโหลดเฉพาะไฟล์ .xls หรือ .xlsx"})
        
    try:
        ext = os.path.splitext(file.filename)[1]
        unique_name = secure_filename(f"{int(time.time())}_{os.urandom(4).hex()}{ext}")
        save_path = os.path.join(UPLOAD_DIR, unique_name)
        file.save(save_path)
        
        # Load sheets
        xl = pd.ExcelFile(save_path)
        sheets = [sh for sh in xl.sheet_names if is_thai_month_sheet(sh)]
        sheets.sort(key=lambda sh: get_sheet_sort_key(sh, save_path), reverse=True)
        
        return jsonify({
            "success": True, 
            "message": "อัปโหลดไฟล์สำเร็จ!", 
            "sheets": sheets,
            "filename": file.filename,
            "temp_filename": unique_name
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/sheets', methods=['GET'])
def get_sheets():
    try:
        temp_filename = request.args.get('temp_filename', '')
        safe_filename = secure_filename(temp_filename) if temp_filename else ""
        xls_path = os.path.join(UPLOAD_DIR, safe_filename) if safe_filename else DEFAULT_XLS_PATH
        
        if not os.path.exists(xls_path):
            return jsonify({"success": True, "sheets": [], "current_file": ""})
            
        xl = pd.ExcelFile(xls_path)
        sheets = [sh for sh in xl.sheet_names if is_thai_month_sheet(sh)]
        sheets.sort(key=lambda sh: get_sheet_sort_key(sh, xls_path), reverse=True)
        return jsonify({"success": True, "sheets": sheets, "current_file": os.path.basename(xls_path)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/records', methods=['GET'])
def get_records():
    sheet = request.args.get('sheet', 'มิ.ย.69')
    temp_filename = request.args.get('temp_filename', '')
    safe_filename = secure_filename(temp_filename) if temp_filename else ""
    xls_path = os.path.join(UPLOAD_DIR, safe_filename) if safe_filename else DEFAULT_XLS_PATH
    api_key = request.headers.get('X-Gemini-API-Key', '').strip()
    office_name = request.args.get('office_name', '').strip() or request.headers.get('X-Office-Name', '').strip()
    default_tambon = request.args.get('tambon', '').strip() or request.headers.get('X-Tambon', '').strip()
    try:
        if api_key:
            print("Using Gemini API for parsing and classification...")
            try:
                records = load_excel_records_with_gemini(
                    xls_path, sheet, api_key,
                    office_name=office_name, default_tambon=default_tambon
                )
            except Exception as e_gemini:
                print(f"Gemini parsing failed ({e_gemini}), falling back to rules-based parser...")
                records = load_excel_records(
                    xls_path, sheet, office_name=office_name, default_tambon=default_tambon
                )
        else:
            print("Using rules-based parser (no Gemini API Key provided)...")
            records = load_excel_records(
                xls_path, sheet, office_name=office_name, default_tambon=default_tambon
            )

        return jsonify({"success": True, "records": records})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def _month_name_thai_from_sheet(sheet_name):
    month_name_thai = "มิถุนายน"
    normalized_sheet = sheet_name.replace(" ", "").replace(".", "")
    match_month = re.match(r"^([ก-๙]+)", normalized_sheet)
    if match_month:
        month_part = match_month.group(1)
        month_name_map = {
            "มค": "มกราคม", "กพ": "กุมภาพันธ์", "มีค": "มีนาคม", "เมย": "เมษายน",
            "พค": "พฤษภาคม", "มิย": "มิถุนายน", "กค": "กรกฎาคม", "สค": "สิงหาคม",
            "กย": "กันยายน", "ตค": "ตุลาคม", "พย": "พฤศจิกายน", "ธค": "ธันวาคม"
        }
        month_name_thai = month_name_map.get(month_part, "มิถุนายน")
    return month_name_thai


def _group_records_by_tambon(records, default_tambon, role):
    """Group records by tambon for multi-tambon roles; officer stays single-tambon."""
    multi = role in ("district_chief", "admin_clerk")
    if not multi:
        return [(default_tambon, list(enumerate(records)))]

    groups = {}
    order = []
    for idx, rec in enumerate(records):
        tb = (rec.get("tambon") or default_tambon or "").strip() or default_tambon
        # normalize bare names
        key = tb.replace("ตำบล", "").replace("แขวง", "").strip() or default_tambon
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((idx, rec))
    return [(k, groups[k]) for k in order]


def _fill_record_row(page, rec, idx, q, shot_prefix):
    activity_preview = (rec.get('activity') or '')[:30]
    msg_prefix = f"รายการที่แถว {rec.get('id', idx)}: {activity_preview}..."
    q.put({"type": "row_status", "index": idx, "status": "processing", "message": f"กำลังกรอก: {msg_prefix}"})

    page.click('a:has-text("เพิ่มข้อมูล")')
    page.wait_for_selector('#bizModal_402', state='visible')
    page.wait_for_timeout(800)

    modal = page.locator('#bizModal_402')
    _select_modal_option(page, '#bizModal_402 select#PD_ISSUES', rec['issue_val'])
    page.wait_for_timeout(800)
    _select_modal_option(
        page,
        '#bizModal_402 select#PD_ACTIVITY',
        rec['activity_val'],
        rec.get('activity', ''),
    )

    # If activity is "999" (อื่นๆ), input#PD_OTHER is mandatory for modal form validation
    if str(rec['activity_val']) == "999" or (str(rec['issue_val']) == "2" and str(rec['activity_val']) == "999"):
        other_val = (rec.get('other_text') or rec.get('activity') or 'ปฏิบัติงานในพื้นที่')[:30]
        try:
            modal.locator('input#PD_OTHER').fill(other_val)
        except Exception:
            pass

    be_date = rec['date']
    _set_modal_dates(page, be_date)

    place = rec.get('location') or ''
    modal.locator('textarea#PD_DETAIL').fill(rec.get('activity') or '')
    modal.locator('textarea#PD_PLACE').fill(place)
    modal.locator('input#PD_TARGET').fill(str(rec.get('target_num') or 0))

    # Trigger events on all inputs inside modal and remove disabled from submit button
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
    page.wait_for_timeout(300)

    # Click submit button with JS fallback if Playwright actionability fails
    try:
        modal.locator('button[type="submit"]:has-text("บันทึก")').click(timeout=5000)
    except Exception:
        page.evaluate("""() => {
            const modalEl = document.querySelector('#bizModal_402');
            if (!modalEl) return;
            const btn = Array.from(modalEl.querySelectorAll('button, input[type="submit"]'))
                .find(b => (b.textContent || '').includes('บันทึก') || (b.value || '').includes('บันทึก'))
                || modalEl.querySelector('button[type="submit"]')
                || modalEl.querySelector('button.btn-primary');
            if (btn) {
                btn.removeAttribute('disabled');
                btn.disabled = false;
                btn.click();
            } else {
                const form = modalEl.querySelector('form');
                if (form) form.submit();
            }
        }""")

    try:
        page.wait_for_selector('#bizModal_402', state='hidden', timeout=15000)
    except Exception as exc:
        validation_state = page.evaluate("""() => {
            const modal = document.querySelector('#bizModal_402');
            if (!modal) return {modal: 'missing'};
            const invalid = Array.from(modal.querySelectorAll(':invalid')).map((el) => ({
                id: el.id,
                name: el.name,
                value: el.value,
                message: el.validationMessage
            }));
            return {
                invalid,
                startDate: modal.querySelector('#PD_SDATE')?.value || '',
                endDate: modal.querySelector('#PD_EDATE')?.value || '',
                issue: modal.querySelector('#PD_ISSUES')?.value || '',
                activity: modal.querySelector('#PD_ACTIVITY')?.value || ''
            };
        }""")
        raise RuntimeError(
            f"Portal modal stayed open after save: {validation_state}"
        ) from exc
    page.wait_for_timeout(500)
    q.put({"type": "row_status", "index": idx, "status": "success", "message": f"กรอกสำเร็จ: {msg_prefix}"})


def _select_approver(page, approver):
    safe = (approver or "").replace("'", "\\'")
    page.evaluate(f"""() => {{
        const select = document.querySelector('select#USR_APPROVERS');
        if (select) {{
            const searchName = '{safe}'.trim();
            let option = Array.from(select.options).find(o => o.text.trim() === searchName);
            if (!option) {{
                option = Array.from(select.options).find(o => o.text.includes(searchName));
            }}
            if (!option) {{
                option = Array.from(select.options).find(o => searchName.includes(o.text.trim()));
            }}
            if (option) {{
                select.value = option.value;
                select.dispatchEvent(new Event('change'));
            }}
        }}
    }}""")


def _finish_plan(page, mode, q):
    if mode == 'dry_run':
        q.put({"type": "info", "message": "กรอกข้อมูลเสร็จสิ้นในโหมด Dry-run สำหรับตำบลนี้แล้ว"})
        return
    if mode == 'draft':
        q.put({"type": "info", "message": "กำลังกดปุ่มบันทึกชั่วคราว (Save Draft)..."})
        page.click('#wf-btn-temp-save')
        try:
            page.wait_for_selector('button.confirm', state='visible', timeout=5000)
            q.put({"type": "info", "message": "กำลังกดยืนยันการบันทึกชั่วคราว..."})
            page.click('button.confirm')
            page.wait_for_timeout(1000)
        except Exception:
            pass
        page.evaluate("""() => {
            const form = document.querySelector('#form_wf') || document.querySelector('form');
            if (form) form.submit();
        }""")
        page.wait_for_timeout(5000)
        q.put({"type": "info", "message": "บันทึกข้อมูลแบบชั่วคราว (ร่าง) เรียบร้อยแล้ว!"})
    else:
        q.put({"type": "info", "message": "กำลังกดปุ่มบันทึกและส่งแผน..."})
        page.click('#wf-btn-save')
        try:
            page.wait_for_selector('button.confirm', state='visible', timeout=5000)
            q.put({"type": "info", "message": "กำลังกดยืนยันการบันทึกและส่งแผน..."})
            page.click('button.confirm')
            page.wait_for_timeout(1000)
        except Exception:
            pass
        page.evaluate("""() => {
            const form = document.querySelector('#form_wf') || document.querySelector('form');
            if (form) form.submit();
        }""")
        page.wait_for_timeout(5000)
        q.put({"type": "info", "message": "บันทึกและส่งข้อมูลเรียบร้อยแล้ว!"})


@app.route('/api/run', methods=['POST'])
def run_automation():
    global _run_active
    data = request.json or {}
    records = data.get('records', [])
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    sheet_name = data.get('sheet', 'มิ.ย.69')
    tambon = data.get('tambon', '')
    role = data.get('role', 'officer')
    office_name = data.get('office_name', '')
    approver = data.get('approver', '')
    headless = data.get('headless', False)
    if sys.platform != 'win32' or os.environ.get('HEADLESS', '0') == '1':
        headless = True
    mode = data.get('mode', 'dry_run')
    if 'dry_run' in data and mode == 'dry_run':
        if not data['dry_run']:
            mode = 'submit'

    # Each officer must supply their own T&V account — never use shared defaults
    if not username or not password:
        return jsonify({
            "success": False,
            "error": "กรุณากรอกชื่อผู้ใช้และรหัสผ่านบัญชี T&V ของท่านเอง"
        }), 400

    if not _run_lock.acquire(blocking=False):
        return jsonify({
            "success": False,
            "error": "มีผู้ใช้อื่นกำลังรันระบบอยู่ กรุณารอสักครู่แล้วลองใหม่"
        }), 429
    _run_active = True

    try:
        year_num, portal_month_val, month_num = parse_sheet_name(sheet_name, records=records)
    except Exception as ex:
        year_num, portal_month_val, month_num = "2569", "69", 6

    month_name_thai = _month_name_thai_from_sheet(sheet_name)
    groups = _group_records_by_tambon(records, tambon, role)
    shot_prefix = f"err_{uuid.uuid4().hex[:10]}"

    def event_stream():
        global _run_active
        q = queue.Queue()

        def run_playwright():
            from playwright.sync_api import sync_playwright
            try:
                q.put({"type": "info", "message": f"พื้นที่: {office_name or '-'} | บทบาท: {role} | ตำบลที่จะกรอก: {len(groups)} กลุ่ม"})
                q.put({"type": "info", "message": "กำลังเปิดเบราว์เซอร์..."})
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=headless)
                    context = browser.new_context()
                    page = context.new_page()

                    q.put({"type": "info", "message": "กำลังเข้าสู่ระบบเว็บ T&V..."})
                    page.goto("https://tandv.doae.go.th/index/login_tv_system.php")
                    page.wait_for_load_state("networkidle")
                    page.fill('input[name="USER_NAME"]', username)
                    page.fill('input[name="USER_PASSWORD"]', password)
                    page.click('#login_submit')
                    page.wait_for_timeout(4000)

                    if "login" in page.url:
                        q.put({"type": "error", "message": "เข้าสู่ระบบไม่สำเร็จ! กรุณาตรวจสอบรหัสผ่านอีกครั้ง"})
                        browser.close()
                        return

                    for g_idx, (tambon_name, indexed_recs) in enumerate(groups, 1):
                        q.put({"type": "info", "message": f"[{g_idx}/{len(groups)}] เปิด Workflow 26 สำหรับตำบล: {tambon_name}"})
                        page.goto("https://tandv.doae.go.th/workflow/workflow_start.php?W=26")
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(2000)

                        q.put({"type": "info", "message": f"เลือก ปี {year_num}, เดือน {month_name_thai}, ตำบล {tambon_name}"})
                        select_by_value_js(page, 'select#PL_YAER', year_num)
                        page.wait_for_timeout(800)
                        select_by_label_js(page, 'select#PL_MOUNT', month_name_thai)
                        page.wait_for_timeout(800)
                        select_by_label_js(page, 'select#PL_TAMBONN', tambon_name)
                        page.wait_for_timeout(1200)

                        for idx, rec in indexed_recs:
                            try:
                                _fill_record_row(page, rec, idx, q, shot_prefix)
                            except Exception as e_row:
                                q.put({"type": "row_status", "index": idx, "status": "error",
                                       "message": f"เกิดข้อผิดพลาดแถว {rec.get('id')}: {e_row}"})
                                try:
                                    shot_path = os.path.join("static", f"{shot_prefix}_{idx}.png")
                                    page.screenshot(path=shot_path)
                                    q.put({"type": "screenshot", "url": f"/static/{shot_prefix}_{idx}.png"})
                                except Exception:
                                    pass
                                try:
                                    if page.locator('#bizModal_402').is_visible():
                                        page.keyboard.press('Escape')
                                        page.wait_for_timeout(500)
                                except Exception:
                                    pass

                        if approver:
                            q.put({"type": "info", "message": f"กำลังเลือกผู้อนุมัติ: {approver}..."})
                            _select_approver(page, approver)
                            page.wait_for_timeout(800)

                        _finish_plan(page, mode, q)

                        if mode == 'dry_run' and g_idx == len(groups):
                            q.put({"type": "info", "message": "Dry-run ครบทุกตำบล — เบราว์เซอร์จะเปิดค้างไว้ 3 นาทีเพื่อตรวจสอบ"})
                            page.wait_for_timeout(180000)

                    browser.close()
                    q.put({"type": "done", "message": "เสร็จสิ้นภารกิจ!"})
            except Exception as ex:
                q.put({"type": "error", "message": f"การกรอกข้อมูลหยุดชะงัก: {str(ex)}"})
            finally:
                q.put(None)

        t = threading.Thread(target=run_playwright)
        t.start()

        try:
            while True:
                item = q.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            _run_active = False
            try:
                _run_lock.release()
            except RuntimeError:
                pass

    return Response(event_stream(), mimetype='text/event-stream')

if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(errors='replace')
        sys.stderr.reconfigure(errors='replace')
    except AttributeError:
        pass

    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"Starting T&V Dashboard Server on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
