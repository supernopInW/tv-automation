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
    office_name = request.args.get('office_name', '').strip() or request.headers.get('X-Office-Name', '').strip()
    default_tambon = request.args.get('tambon', '').strip() or request.headers.get('X-Tambon', '').strip()
    try:
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
    modal.locator('select#PD_ISSUES').select_option(value=str(rec['issue_val']))
    page.wait_for_timeout(800)
    modal.locator('select#PD_ACTIVITY').select_option(value=str(rec['activity_val']))

    # If activity is "999" (อื่นๆ), input#PD_OTHER is mandatory for modal form validation
    if str(rec['activity_val']) == "999" or (str(rec['issue_val']) == "2" and str(rec['activity_val']) == "999"):
        other_val = (rec.get('other_text') or rec.get('activity') or 'ปฏิบัติงานในพื้นที่')[:30]
        try:
            modal.locator('input#PD_OTHER').fill(other_val)
        except Exception:
            pass

    be_date = rec['date']
    page.evaluate(f"""(dateVal) => {{
        const modalEl = document.querySelector('#bizModal_402');
        if (!modalEl) return;
        ['#PD_SDATE', '#PD_EDATE'].forEach(sel => {{
            const el = modalEl.querySelector(sel);
            if (el) {{
                el.removeAttribute('disabled');
                el.value = dateVal;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
            }}
        }});
    }}""", be_date)

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

    page.wait_for_selector('#bizModal_402', state='hidden', timeout=10000)
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
