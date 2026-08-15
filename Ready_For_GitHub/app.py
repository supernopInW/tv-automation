import sys
import io
import time
import re
import hashlib
import hmac
import queue
import secrets
import threading
import zipfile
import tempfile
from pathlib import Path

import pandas as pd
from flask import Flask, render_template, jsonify, request, Response, send_from_directory, session, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import json
import os
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash
import geo_data

APP_SESSION_SECRET = os.environ.get('APP_SESSION_SECRET', '').strip()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SECRET_KEY'] = APP_SESSION_SECRET or secrets.token_urlsafe(32)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_BYTES', str(10 * 1024 * 1024)))

APP_AUTH_REQUIRED = os.environ.get('APP_AUTH_REQUIRED', '1').strip().lower() in {'1', 'true', 'yes'}
APP_AUTH_USERNAME = os.environ.get('APP_AUTH_USERNAME', '').strip()
APP_AUTH_PASSWORD_HASH = os.environ.get('APP_AUTH_PASSWORD_HASH', '').strip()
APP_AUTH_ROLE = os.environ.get('APP_AUTH_ROLE', 'officer').strip()
APP_AUTH_OFFICE_NAME = os.environ.get('APP_AUTH_OFFICE_NAME', '').strip()
APP_AUTH_ALLOWED_TAMBONS = frozenset(
    item.strip() for item in os.environ.get('APP_AUTH_ALLOWED_TAMBONS', '').split(',') if item.strip()
)
APP_AUTH_ALLOWED_APPROVERS = frozenset(
    item.strip() for item in os.environ.get('APP_AUTH_ALLOWED_APPROVERS', '').split(',') if item.strip()
)
APP_AUTH_CAN_SUBMIT = os.environ.get('APP_AUTH_CAN_SUBMIT', '0').strip().lower() in {'1', 'true', 'yes'}
APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()
RATE_LIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://').strip()
if APP_ENV in {'production', 'prod'} and RATE_LIMIT_STORAGE_URI.startswith('memory://'):
    raise RuntimeError('RATELIMIT_STORAGE_URI must be a shared Redis URI in production')
if APP_ENV in {'production', 'prod'} and APP_AUTH_REQUIRED:
    if not (APP_AUTH_USERNAME and APP_AUTH_PASSWORD_HASH and APP_SESSION_SECRET):
        raise RuntimeError('Production application authentication secrets are not configured')
    if not (APP_AUTH_ROLE and APP_AUTH_OFFICE_NAME and APP_AUTH_ALLOWED_TAMBONS and APP_AUTH_ALLOWED_APPROVERS):
        raise RuntimeError('Production authorization profile is not configured')
if APP_AUTH_REQUIRED and not (APP_AUTH_USERNAME and APP_AUTH_PASSWORD_HASH and APP_SESSION_SECRET):
    # Fail closed for protected requests; never use a source-code default.
    print('APP_AUTH_REQUIRED=1 but authentication secrets are not configured')
if RATE_LIMIT_STORAGE_URI == 'memory://':
    print('WARNING: RATELIMIT_STORAGE_URI=memory:// is for development only')

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=RATE_LIMIT_STORAGE_URI,
    strategy='moving-window',
    headers_enabled=True,
)

PROTECTED_API_PATHS = {
    '/api/add-row', '/api/upload', '/api/sheets', '/api/records',
    '/api/historical-activities', '/api/run',
}
PUBLIC_API_PATHS = {'/api/health', '/api/access/status', '/api/auth/login', '/api/auth/logout', '/api/csp-report'}

UPLOAD_TTL_SECONDS = int(os.environ.get('UPLOAD_TTL_SECONDS', '1800'))
UPLOAD_REGISTRY = {}
UPLOAD_REGISTRY_LOCK = threading.Lock()
ALLOWED_UPLOAD_EXTENSIONS = {'.xls', '.xlsx'}
OLE_COMPOUND_FILE_HEADER = bytes.fromhex('D0CF11E0A1B11AE1')


def _rate_limit_key():
    """Use the platform-derived remote address after proxy configuration is verified."""
    return get_remote_address() or 'unknown'


def _ensure_csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return token


def _csrf_valid():
    expected = session.get('csrf_token', '')
    supplied = request.headers.get('X-CSRF-Token', '')
    return bool(expected and supplied) and hmac.compare_digest(supplied, expected)


def _auth_configured():
    return bool(APP_AUTH_USERNAME and APP_AUTH_PASSWORD_HASH and APP_SESSION_SECRET)


def _app_authenticated():
    return bool(session.get('app_user'))


def _normalize_tambon_name(value):
    return str(value or '').replace('ตำบล', '').replace('แขวง', '').strip()


def _server_auth_profile():
    return {
        'username': APP_AUTH_USERNAME,
        'role': APP_AUTH_ROLE or 'officer',
        'office_name': APP_AUTH_OFFICE_NAME,
        'allowed_tambons': APP_AUTH_ALLOWED_TAMBONS,
        'allowed_approvers': APP_AUTH_ALLOWED_APPROVERS,
        'can_submit': APP_AUTH_CAN_SUBMIT,
    }


def _auth_profile_configured():
    return bool(
        APP_AUTH_ROLE
        and APP_AUTH_OFFICE_NAME
        and APP_AUTH_ALLOWED_TAMBONS
        and APP_AUTH_ALLOWED_APPROVERS
    )


def _validate_run_authorization(data):
    """Derive automation scope from the server profile when app auth is enabled."""
    requested_mode = str(data.get('mode', 'dry_run') or 'dry_run').strip()
    if 'dry_run' in data and requested_mode == 'dry_run' and data.get('dry_run') is False:
        requested_mode = 'submit'
    if requested_mode not in {'dry_run', 'draft', 'submit'}:
        return None, ({'success': False, 'error': 'โหมดการทำงานไม่ถูกต้อง'}, 400)

    if not APP_AUTH_REQUIRED:
        return {
            'tambon': data.get('tambon', ''),
            'role': data.get('role', 'officer'),
            'office_name': data.get('office_name', ''),
            'approver': data.get('approver', ''),
            'mode': requested_mode,
        }, None

    if not _auth_profile_configured():
        return None, ({'success': False, 'error': 'ยังไม่ได้ตั้งค่า server-side authorization profile'}, 503)

    profile = _server_auth_profile()
    requested_tambons = list(data.get('selected_tambons') or [])
    if not requested_tambons and data.get('tambon'):
        requested_tambons = [data.get('tambon')]
    normalized_requested = {_normalize_tambon_name(item) for item in requested_tambons if str(item).strip()}
    unauthorized_tambons = normalized_requested - {_normalize_tambon_name(item) for item in profile['allowed_tambons']}
    if not normalized_requested or unauthorized_tambons:
        return None, ({'success': False, 'error': 'ไม่มีสิทธิ์ใช้พื้นที่ที่ร้องขอ'}, 403)

    requested_approver = str(data.get('approver') or '').strip()
    if requested_approver not in profile['allowed_approvers']:
        return None, ({'success': False, 'error': 'ไม่มีสิทธิ์ใช้ผู้อนุมัติที่ร้องขอ'}, 403)
    if requested_mode == 'submit' and not profile['can_submit']:
        return None, ({'success': False, 'error': 'บัญชีนี้ไม่มีสิทธิ์ส่งข้อมูลจริง'}, 403)

    for record in data.get('records') or []:
        record_tambon = _normalize_tambon_name(record.get('tambon') or data.get('tambon'))
        if record_tambon and record_tambon not in {
            _normalize_tambon_name(item) for item in profile['allowed_tambons']
        }:
            return None, ({'success': False, 'error': 'ข้อมูลแถวมีตำบลนอกสิทธิ์'}, 403)

    return {
        'tambon': next(iter(normalized_requested)),
        'role': profile['role'],
        'office_name': profile['office_name'],
        'approver': requested_approver,
        'mode': requested_mode,
    }, None


@app.before_request
def set_csp_nonce():
    # A fresh nonce per response authorizes only the JSON-LD script rendered by
    # the server; all executable JavaScript remains external and same-origin.
    g.csp_nonce = secrets.token_urlsafe(16)


@app.context_processor
def inject_csp_nonce():
    return {'csp_nonce': getattr(g, 'csp_nonce', '')}


@app.before_request
def enforce_api_access_boundary():
    if not request.path.startswith('/api/'):
        return None
    if request.path in {'/api/health', '/api/csp-report'}:
        return None
    _ensure_csrf_token()
    if request.path in {'/api/access/status', '/api/auth/login', '/api/auth/logout'}:
        if request.path != '/api/access/status' and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and not _csrf_valid():
            return jsonify({'success': False, 'error': 'คำขอไม่ผ่านการตรวจสอบความปลอดภัย'}), 403
        return None
    if APP_AUTH_REQUIRED and not _auth_configured():
        return jsonify({'success': False, 'error': 'ระบบยืนยันตัวตนยังไม่ได้ตั้งค่า'}), 503
    if APP_AUTH_REQUIRED and not _app_authenticated():
        return jsonify({'success': False, 'error': 'กรุณาเข้าสู่ระบบแอปก่อนใช้งาน'}), 401
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and not _csrf_valid():
        return jsonify({'success': False, 'error': 'คำขอไม่ผ่านการตรวจสอบความปลอดภัย'}), 403
    return None


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(_error):
    return jsonify({'success': False, 'error': 'ไฟล์หรือคำขอมีขนาดใหญ่เกินกำหนด'}), 413

# CSP is enforced by default in production after the inline-handler/style
# migration. Development and test remain Report-Only unless explicitly enabled.
_csp_default = '1' if APP_ENV in {'production', 'prod'} else ''
CSP_ENFORCE = os.getenv('CSP_ENFORCE', _csp_default).strip().lower() in {'1', 'true', 'yes'}
CSP_POLICY = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "frame-src 'none'; "
    "form-action 'self'; "
    "script-src 'self'; "
    "script-src-attr 'none'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "style-src-attr 'none'; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "manifest-src 'self'; "
    "media-src 'none'"
)
CSP_HEADER_NAME = 'Content-Security-Policy' if CSP_ENFORCE else 'Content-Security-Policy-Report-Only'


def _csp_policy_for_request():
    nonce = getattr(g, 'csp_nonce', '')
    if not nonce:
        return CSP_POLICY
    return CSP_POLICY.replace(
        "script-src 'self';",
        f"script-src 'self' 'nonce-{nonce}';",
        1,
    )


@app.after_request
def add_security_headers(response):
    """Attach browser hardening headers without logging request credentials."""
    response.headers[CSP_HEADER_NAME] = _csp_policy_for_request()
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=(), usb=()'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

# Ensure directories exist
os.makedirs('static', exist_ok=True)
os.makedirs('templates', exist_ok=True)
os.makedirs('docs', exist_ok=True)

# Global variables and paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_XLS_PATH = os.path.join(BASE_DIR, "แผนเดือนพค69.xls")
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "tv-automation-uploads")
os.makedirs(UPLOAD_DIR, mode=0o700, exist_ok=True)


def _cleanup_expired_uploads():
    now = time.time()
    with UPLOAD_REGISTRY_LOCK:
        expired = [upload_id for upload_id, meta in UPLOAD_REGISTRY.items()
                   if now - meta.get('created_at', now) > UPLOAD_TTL_SECONDS]
        for upload_id in expired:
            meta = UPLOAD_REGISTRY.pop(upload_id, {})
            path = meta.get('path')
            if path:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass


def _upload_owner_key():
    app_user = session.get('app_user')
    if app_user:
        return f"app:{app_user}"
    # Anonymous uploads are bound to the signed browser session, not only to
    # the remote IP, because multiple officers may share a proxy/NAT address.
    owner_token = session.get('upload_owner_token')
    if not owner_token:
        owner_token = secrets.token_urlsafe(32)
        session['upload_owner_token'] = owner_token
    return f"session:{owner_token}"


def _get_owned_upload_path(upload_id):
    _cleanup_expired_uploads()
    with UPLOAD_REGISTRY_LOCK:
        meta = UPLOAD_REGISTRY.get(upload_id)
        if not meta or meta.get('owner') != _upload_owner_key():
            return None
        path = meta.get('path')
        if not path or not os.path.isfile(path):
            UPLOAD_REGISTRY.pop(upload_id, None)
            return None
        return path


def _validate_excel_payload(file_storage):
    original = (file_storage.filename or '').strip()
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError('รูปแบบไฟล์ไม่ถูกต้อง กรุณาอัปโหลดเฉพาะไฟล์ .xls หรือ .xlsx')
    payload = file_storage.stream.read(app.config['MAX_CONTENT_LENGTH'] + 1)
    file_storage.stream.seek(0)
    if len(payload) > app.config['MAX_CONTENT_LENGTH']:
        raise RequestEntityTooLarge()
    if suffix == '.xls':
        if not payload.startswith(OLE_COMPOUND_FILE_HEADER):
            raise ValueError('โครงสร้างไฟล์ XLS ไม่ถูกต้อง')
    else:
        if not payload.startswith(b'PK\\x03\\x04'):
            raise ValueError('โครงสร้างไฟล์ XLSX ไม่ถูกต้อง')
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = archive.namelist()
                if len(names) > 1000 or any(name.startswith('/') or '..' in Path(name).parts for name in names):
                    raise ValueError('โครงสร้างไฟล์ XLSX ไม่ปลอดภัย')
                if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
                    raise ValueError('ข้อมูลภายในไฟล์ XLSX มีขนาดเกินกำหนด')
                if not {'[Content_Types].xml', 'xl/workbook.xml'}.issubset(names):
                    raise ValueError('ไม่ใช่ไฟล์ XLSX ที่สมบูรณ์')
        except zipfile.BadZipFile as exc:
            raise ValueError('ไฟล์ XLSX เสียหายหรือไม่ใช่ ZIP package') from exc
    return suffix

# Single automation lock for shared Playwright resources (HF Space friendly)
_run_lock = threading.Lock()
_run_active = False

# Historical Excel activity pool used by the client-side auto-plan generator.
# The current upload is intentionally excluded; only workbook files committed
# at the project root are considered historical reference data.
_historical_activity_pool_cache = None
_historical_activity_sources_cache = []
_historical_activity_errors_cache = []
_historical_activity_lock = threading.Lock()
_valid_visiting_activity_values = {
    "2", "15", "16", "17", "18", "19", "20", "21", "22",
    "23", "24", "25", "26", "27", "28", "29", "30", "31", "999",
}

PORTAL_LOGIN_URL = "https://tandv.doae.go.th/index/login_tv_system.php"
PORTAL_WORKFLOW_26_URL = "https://tandv.doae.go.th/workflow/workflow_start.php?W=26"
PLAYWRIGHT_NAVIGATION_TIMEOUT_MS = 30_000
PLAYWRIGHT_ACTION_TIMEOUT_MS = 15_000
PLAYWRIGHT_RESULT_TIMEOUT_MS = 25_000


def _page_diagnostics(page):
    """Return safe, non-sensitive diagnostics for the current portal page."""
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
                    ariaHidden: el.getAttribute('aria-hidden'),
                    display: style.display,
                    visibility: style.visibility,
                    visible: Boolean(rect.width && rect.height && style.display !== 'none' && style.visibility !== 'hidden')
                };
            }
            return {
                urlPath: window.location.pathname,
                readyState: document.readyState,
                loginVisible: Boolean(document.querySelector('input[name=USER_PASSWORD]')),
                workflowReady: workflowControls['#PL_YAER']?.present && workflowControls['#PL_YAER'].optionCount > 1 &&
                    workflowControls['#PL_MOUNT']?.present && workflowControls['#PL_MOUNT'].optionCount >= 1 &&
                    workflowControls['#PL_TAMBONN']?.present && workflowControls['#PL_TAMBONN'].optionCount > 1,
                workflowControls,
                modalVisible: Boolean(document.querySelector('#bizModal_402')) &&
                    getComputedStyle(document.querySelector('#bizModal_402')).display !== 'none'
            };
        }""")
    except Exception as exc:
        return {"diagnostics_error": str(exc)}


def _wait_for_portal_ready(page, stage):
    """Wait for Workflow 26 controls, including hidden Select2 backing selects."""
    try:
        # The portal wraps these native selects with Select2 and intentionally
        # hides the backing elements. Wait for attachment and populated options,
        # not CSS visibility of the raw <select>.
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
        state = _page_diagnostics(page)
        if state.get("loginVisible") or "login" in str(state.get("url", "")).lower():
            code = "AUTH_OR_SESSION_ERROR"
        else:
            code = "WORKFLOW_SELECTOR_ERROR"
        raise RuntimeError(f"{code} at {stage}: {state}") from exc


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
        state = _page_diagnostics(page)
        raise RuntimeError(f"WORKFLOW_DYNAMIC_OPTION_ERROR at {stage}: {state}") from exc


def _assert_authenticated(page):
    state = _page_diagnostics(page)
    if state.get("loginVisible") or "login" in str(state.get("url", "")).lower():
        raise RuntimeError(f"AUTHENTICATION_ERROR after login: {state}")


def _modal_validation_state(page):
    """Read the relevant modal values and browser validation errors."""
    return page.evaluate("""() => {
        const modal = document.querySelector('#bizModal_402');
        if (!modal) return {modal: 'missing'};
        return {
            invalid: Array.from(modal.querySelectorAll(':invalid')).map((el) => ({
                id: el.id,
                name: el.name,
                value: el.value,
                message: el.validationMessage
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


def _verify_finalize_result(page, mode, before_url):
    """Classify finalization as confirmed or unknown; never claim success on timeout alone."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=PLAYWRIGHT_RESULT_TIMEOUT_MS)
    except Exception:
        # Some portal submissions do not navigate; body inspection below is still useful.
        pass
    page.wait_for_timeout(1_000)
    state = _page_diagnostics(page)
    text = str(state.get("bodyText", "")).lower()
    success_markers = (
        "บันทึกข้อมูลเรียบร้อย", "บันทึกเรียบร้อย", "ส่งข้อมูลเรียบร้อย",
        "ดำเนินการเรียบร้อย", "success", "saved", "completed"
    )
    url_changed = bool(state.get("url") and state.get("url") != before_url)
    has_success_marker = any(marker in text for marker in success_markers)
    if has_success_marker or (url_changed and not state.get("loginVisible")):
        return {"confirmed": True, "state": state}
    return {"confirmed": False, "state": state}

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
    """Select a native portal option and verify the resulting value."""
    result = page.evaluate(
        """({selector, value}) => {
            const select = document.querySelector(selector);
            if (!select) return {found: false, reason: 'select-not-found'};
            const option = Array.from(select.options).find((item) => item.value === value);
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
        {"selector": selector, "value": str(value or "").strip()},
    )
    if not result.get("found"):
        raise RuntimeError(f"PORTAL_OPTION_ERROR for {selector}: {result}")
    page.wait_for_timeout(300)
    selected = page.locator(selector).input_value()
    if selected != result.get("value"):
        raise RuntimeError(
            f"PORTAL_OPTION_NOT_PERSISTED for {selector}: expected={result.get('value')!r}, got={selected!r}"
        )


def select_by_label_js(page, selector, label):
    """Select an option by visible label without interpolating user text into JS."""
    result = page.evaluate(
        """({selector, label}) => {
            const select = document.querySelector(selector);
            if (!select) return {found: false, reason: 'select-not-found'};
            const wanted = String(label || '').trim();
            const option = Array.from(select.options).find((item) => item.text.trim() === wanted);
            if (!option) return {
                found: false,
                reason: 'option-not-found',
                label: wanted,
                options: Array.from(select.options).map((item) => ({value: item.value, text: item.text.trim()}))
            };
            select.value = option.value;
            select.dispatchEvent(new Event('input', {bubbles: true}));
            select.dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) window.jQuery(select).val(option.value).trigger('change');
            return {found: true, value: select.value, text: option.text.trim()};
        }""",
        {"selector": selector, "label": str(label or "").strip()},
    )
    if not result.get("found"):
        raise RuntimeError(f"PORTAL_OPTION_ERROR for {selector}: {result}")
    page.wait_for_timeout(300)
    selected = page.locator(selector).input_value()
    if selected != result.get("value"):
        raise RuntimeError(
            f"PORTAL_OPTION_NOT_PERSISTED for {selector}: expected={result.get('value')!r}, got={selected!r}"
        )


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


def load_historical_activity_pool():
    """Build weighted VISITING activities from committed historical workbooks."""
    global _historical_activity_pool_cache
    global _historical_activity_sources_cache
    global _historical_activity_errors_cache

    if _historical_activity_pool_cache is not None:
        return (
            _historical_activity_pool_cache,
            _historical_activity_sources_cache,
            _historical_activity_errors_cache,
        )

    with _historical_activity_lock:
        if _historical_activity_pool_cache is not None:
            return (
                _historical_activity_pool_cache,
                _historical_activity_sources_cache,
                _historical_activity_errors_cache,
            )

        weighted = {}
        sources = []
        errors = []
        workbook_names = sorted(
            name for name in os.listdir(BASE_DIR)
            if os.path.isfile(os.path.join(BASE_DIR, name))
            and os.path.splitext(name)[1].lower() in {".xls", ".xlsx"}
            and not name.startswith("~$")
        )

        seen_workbook_hashes = set()
        for workbook_name in workbook_names:
            workbook_path = os.path.join(BASE_DIR, workbook_name)
            workbook_loaded = False
            try:
                with open(workbook_path, "rb") as workbook_file:
                    workbook_hash = hashlib.sha1(workbook_file.read()).hexdigest()
                if workbook_hash in seen_workbook_hashes:
                    continue
                seen_workbook_hashes.add(workbook_hash)

                workbook = pd.ExcelFile(workbook_path)
                for sheet_name in workbook.sheet_names:
                    if not is_thai_month_sheet(sheet_name):
                        continue
                    records = load_excel_records(workbook_path, sheet_name)
                    workbook_loaded = True
                    for record in records:
                        if record.get("officeOnly"):
                            continue
                        if str(record.get("issue_val") or "").strip() != "2":
                            continue

                        activity_val = str(record.get("activity_val") or "").strip()
                        activity_text = str(record.get("activity") or "").strip()
                        other_text = str(record.get("other_text") or "").strip()
                        if activity_val not in _valid_visiting_activity_values or not activity_text:
                            continue

                        key = (activity_val, activity_text, other_text)
                        item = weighted.setdefault(
                            key,
                            {
                                "issue_val": "2",
                                "activity_val": activity_val,
                                "activity": activity_text,
                                "other_text": other_text,
                                "weight": 0,
                            },
                        )
                        item["weight"] += 1

                if workbook_loaded:
                    sources.append(workbook_name)
            except Exception as exc:
                errors.append(f"{workbook_name}: {exc}")

        _historical_activity_pool_cache = sorted(
            weighted.values(),
            key=lambda item: (-item["weight"], item["activity_val"], item["activity"]),
        )
        _historical_activity_sources_cache = sources
        _historical_activity_errors_cache = errors
        return (
            _historical_activity_pool_cache,
            _historical_activity_sources_cache,
            _historical_activity_errors_cache,
        )



@app.route('/api/access/status')
def access_status():
    return jsonify({
        'success': True,
        'auth_required': APP_AUTH_REQUIRED,
        'authenticated': _app_authenticated(),
        'csrf_token': _ensure_csrf_token(),
    })


@app.route('/api/auth/login', methods=['POST'])
@limiter.limit('5 per minute; 20 per hour', key_func=_rate_limit_key)
def app_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()
    password = str(data.get('password') or '')
    if len(username) > 256 or len(password) > 1024:
        return jsonify({'success': False, 'error': 'เข้าสู่ระบบไม่สำเร็จ'}), 401
    if not _auth_configured():
        return jsonify({'success': False, 'error': 'ระบบยืนยันตัวตนยังไม่ได้ตั้งค่า'}), 503
    valid = hmac.compare_digest(username, APP_AUTH_USERNAME) and check_password_hash(APP_AUTH_PASSWORD_HASH, password)
    if not valid:
        return jsonify({'success': False, 'error': 'เข้าสู่ระบบไม่สำเร็จ'}), 401
    session.clear()
    session['app_user'] = APP_AUTH_USERNAME
    session['csrf_token'] = secrets.token_urlsafe(32)
    session.permanent = True
    return jsonify({'success': True, 'csrf_token': session['csrf_token']})


@app.route('/api/auth/logout', methods=['POST'])
def app_logout():
    session.clear()
    return ('', 204)


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
@limiter.limit('30 per minute', key_func=_rate_limit_key)
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
@limiter.limit('5 per 10 minutes', key_func=_rate_limit_key)
def upload_file():
    _cleanup_expired_uploads()
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "ไม่พบไฟล์ที่อัปโหลด"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"success": False, "error": "กรุณาเลือกไฟล์ Excel"}), 400

    save_path = None
    try:
        suffix = _validate_excel_payload(file)
        upload_id = secrets.token_urlsafe(24)
        # The server chooses the suffix from a strict allowlist. The temporary
        # filename itself is generated by tempfile, never by the client.
        temp_suffix = '.xls' if suffix == '.xls' else '.xlsx'
        with tempfile.NamedTemporaryFile(
            mode='wb', prefix='tv-upload-', suffix=temp_suffix,
            dir=UPLOAD_DIR, delete=False
        ) as temp_upload:
            save_path = temp_upload.name
            file.save(temp_upload)
        xl = pd.ExcelFile(save_path)
        sheets = [sh for sh in xl.sheet_names if is_thai_month_sheet(sh)]
        sheets.sort(key=lambda sh: get_sheet_sort_key(sh, save_path), reverse=True)
        with UPLOAD_REGISTRY_LOCK:
            UPLOAD_REGISTRY[upload_id] = {
                'path': save_path,
                'owner': _upload_owner_key(),
                'created_at': time.time(),
            }
        return jsonify({
            "success": True,
            "message": "อัปโหลดไฟล์สำเร็จ!",
            "sheets": sheets,
            "filename": "ไฟล์ Excel ที่อัปโหลด",
            "temp_filename": upload_id,
        })
    except RequestEntityTooLarge:
        raise
    except Exception:
        if save_path:
            try:
                os.remove(save_path)
            except FileNotFoundError:
                pass
        return jsonify({"success": False, "error": "ไม่สามารถตรวจสอบหรืออ่านไฟล์ Excel ได้"}), 400

def _resolve_workbook_path(temp_filename=''):
    if temp_filename:
        return _get_owned_upload_path(temp_filename)
    return DEFAULT_XLS_PATH


@app.route('/api/sheets', methods=['GET'])
def get_sheets():
    try:
        xls_path = _resolve_workbook_path(request.args.get('temp_filename', '').strip())
        if not xls_path or not os.path.isfile(xls_path):
            return jsonify({"success": False, "error": "ไม่พบไฟล์หรือไม่มีสิทธิ์เข้าถึงไฟล์"}), 404
        xl = pd.ExcelFile(xls_path)
        sheets = [sh for sh in xl.sheet_names if is_thai_month_sheet(sh)]
        sheets.sort(key=lambda sh: get_sheet_sort_key(sh, xls_path), reverse=True)
        return jsonify({"success": True, "sheets": sheets, "current_file": os.path.basename(xls_path)})
    except Exception:
        return jsonify({"success": False, "error": "ไม่สามารถอ่านรายการแผ่นงานได้"}), 400

@app.route('/api/records', methods=['GET'])
@limiter.limit('30 per minute', key_func=_rate_limit_key)
def get_records():
    sheet = request.args.get('sheet', 'มิ.ย.69')
    temp_filename = request.args.get('temp_filename', '').strip()
    xls_path = _resolve_workbook_path(temp_filename)
    office_name = request.args.get('office_name', '').strip() or request.headers.get('X-Office-Name', '').strip()
    default_tambon = request.args.get('tambon', '').strip() or request.headers.get('X-Tambon', '').strip()
    try:
        if not xls_path or not os.path.isfile(xls_path):
            return jsonify({"success": False, "error": "ไม่พบไฟล์หรือไม่มีสิทธิ์เข้าถึงไฟล์"}), 404
        # Excel is processed locally with the deterministic rules-based parser.
        # No workbook data or external AI API key is sent to a third party.
        records = load_excel_records(
            xls_path, sheet, office_name=office_name, default_tambon=default_tambon
        )

        return jsonify({"success": True, "records": records})
    except Exception:
        return jsonify({"success": False, "error": "ไม่สามารถอ่านข้อมูลแผนงานได้"}), 400

@app.route('/api/historical-activities', methods=['GET'])
def get_historical_activities():
    """Return weighted field activities from historical root-level Excel files."""
    activities, source_files, errors = load_historical_activity_pool()
    return jsonify({
        "success": True,
        "activities": activities,
        "source_files": source_files,
        "errors": errors,
        "count": len(activities),
    })


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


def _fill_record_row(page, rec, idx, q):
    activity_preview = (rec.get('activity') or '')[:30]
    msg_prefix = f"รายการที่แถว {rec.get('id', idx)}: {activity_preview}..."
    q.put({"type": "row_status", "index": idx, "status": "processing", "message": f"กำลังกรอก: {msg_prefix}"})

    page.locator('a:has-text("เพิ่มข้อมูล")').click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
    page.wait_for_selector('#bizModal_402', state='visible', timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
    page.wait_for_timeout(500)

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
        other_val = (rec.get('other_text') or rec.get('activity') or 'ปฏิบัติงานในพื้นที่')[:30].strip()
        other_input = modal.locator('input#PD_OTHER')
        if other_input.count() != 1:
            raise RuntimeError("MODAL_VALIDATION_ERROR: PD_OTHER is required for activity 999")
        other_input.fill(other_val)
        if not other_input.input_value().strip():
            raise RuntimeError("MODAL_VALIDATION_ERROR: PD_OTHER remained empty for activity 999")

    be_date = rec['date']
    # The portal's PD_SDATE change handler clears PD_EDATE. Set both date
    # fields after all generic modal events so the date pair is the final state.

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

    # Generic change events can asynchronously rebuild PD_ACTIVITY and clear its value.
    # Let that handler settle, then set dynamic selects without firing their destructive
    # change handlers. Re-fill PD_OTHER after the final activity selection when needed.
    page.wait_for_timeout(1_000)
    _set_modal_select_value(page, '#bizModal_402 select#PD_ISSUES', rec['issue_val'])
    _set_modal_select_value(
        page,
        '#bizModal_402 select#PD_ACTIVITY',
        rec['activity_val'],
        rec.get('activity', ''),
    )
    if str(rec['activity_val']) == "999" or (str(rec['issue_val']) == "2" and str(rec['activity_val']) == "999"):
        other_val = (rec.get('other_text') or rec.get('activity') or 'ปฏิบัติงานในพื้นที่')[:30].strip()
        modal.locator('input#PD_OTHER').fill(other_val)

    # Set dates last because the portal clears PD_EDATE when PD_SDATE changes.
    _set_modal_dates(page, be_date)
    validation_state = _modal_validation_state(page)
    required_fields = {
        "issue": str(rec.get("issue_val") or ""),
        "activity": str(rec.get("activity_val") or ""),
        "startDate": str(be_date),
        "endDate": str(be_date),
        "detail": str(rec.get("activity") or ""),
        "place": place,
        "target": str(rec.get("target_num") or 0),
    }
    for field, expected in required_fields.items():
        actual = str(validation_state.get(field) or "")
        if field in ("detail", "place"):
            if expected and actual != expected:
                raise RuntimeError(f"MODAL_FIELD_MISMATCH: {field} expected={expected!r}, actual={actual!r}")
        elif actual != expected:
            raise RuntimeError(f"MODAL_FIELD_MISMATCH: {field} expected={expected!r}, actual={actual!r}")
    if validation_state.get("invalid"):
        raise RuntimeError(f"MODAL_VALIDATION_ERROR before save: {validation_state}")

    # Click the modal's save control. Do not submit the form natively because that
    # bypasses the portal validation and makes the final result ambiguous.
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
        validation_state = _modal_validation_state(page)
        raise RuntimeError(
            f"MODAL_SAVE_UNCONFIRMED: portal modal stayed open: {validation_state}"
        ) from exc
    page.wait_for_timeout(500)
    q.put({"type": "row_status", "index": idx, "status": "success", "message": f"กรอกสำเร็จ: {msg_prefix}"})


def _select_approver(page, approver):
    """Select and verify an approver; never continue with a silent no-op."""
    requested = str(approver or "").strip()
    if not requested:
        raise RuntimeError("APPROVER_ERROR: approver name is empty")
    result = page.evaluate(
        """(requested) => {
            const select = document.querySelector('select#USR_APPROVERS');
            if (!select) return {found: false, reason: 'select-not-found'};
            let option = Array.from(select.options).find((item) => item.text.trim() === requested);
            if (!option) option = Array.from(select.options).find((item) => item.text.includes(requested));
            if (!option) option = Array.from(select.options).find((item) => requested.includes(item.text.trim()));
            if (!option) return {
                found: false,
                reason: 'approver-not-found',
                requested,
                options: Array.from(select.options).map((item) => item.text.trim())
            };
            select.value = option.value;
            select.dispatchEvent(new Event('input', {bubbles: true}));
            select.dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) window.jQuery(select).val(option.value).trigger('change');
            return {found: true, value: select.value, text: option.text.trim()};
        }""",
        requested,
    )
    if not result.get("found"):
        raise RuntimeError(f"APPROVER_ERROR: {result}")
    page.wait_for_timeout(300)
    selected = page.locator('select#USR_APPROVERS').input_value()
    if selected != result.get("value"):
        raise RuntimeError(
            f"APPROVER_NOT_PERSISTED: expected={result.get('value')!r}, got={selected!r}"
        )


def _finish_plan(page, mode, q):
    if mode == 'dry_run':
        q.put({"type": "info", "message": "กรอกข้อมูลเสร็จสิ้นในโหมด Dry-run สำหรับตำบลนี้แล้ว"})
        return

    if mode == 'draft':
        button_selector = '#wf-btn-temp-save'
        label = 'บันทึกข้อมูลแบบชั่วคราว (ร่าง)'
        q.put({"type": "info", "message": "กำลังกดปุ่มบันทึกชั่วคราว (Save Draft)..."})
    else:
        button_selector = '#wf-btn-save'
        label = 'บันทึกและส่งข้อมูล'
        q.put({"type": "info", "message": "กำลังกดปุ่มบันทึกและส่งแผน..."})

    before_url = page.url
    page.locator(button_selector).click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
    try:
        page.wait_for_selector('button.confirm', state='visible', timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
        q.put({"type": "info", "message": f"กำลังกดยืนยัน{label}..."})
        page.locator('button.confirm').click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
    except Exception as exc:
        # Do not call native form.submit() here: it bypasses portal validation and
        # would make it impossible to distinguish a rejected save from a success.
        result = _verify_finalize_result(page, mode, before_url)
        if not result.get("confirmed"):
            raise RuntimeError(
                f"FINALIZE_CONFIRMATION_ERROR: {label} was not confirmed: {result.get('state')}"
            ) from exc

    result = _verify_finalize_result(page, mode, before_url)
    if not result.get("confirmed"):
        raise RuntimeError(
            f"FINALIZE_UNKNOWN_RESULT: {label} may or may not have been processed; "
            f"do not retry without checking the portal: {result.get('state')}"
        )
    q.put({"type": "info", "message": f"ยืนยันผลแล้ว: {label}"})


@app.route('/api/run', methods=['POST'])
@limiter.limit('2 per 10 minutes', key_func=_rate_limit_key)
def run_automation():
    global _run_active
    data = request.json or {}
    records = data.get('records', [])
    run_context, authorization_error = _validate_run_authorization(data)
    if authorization_error:
        error_body, error_status = authorization_error
        return jsonify(error_body), error_status

    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    sheet_name = data.get('sheet', 'มิ.ย.69')
    tambon = run_context['tambon']
    role = run_context['role']
    office_name = run_context['office_name']
    approver = run_context['approver']
    headless = data.get('headless', False)
    if sys.platform != 'win32' or os.environ.get('HEADLESS', '0') == '1':
        headless = True
    mode = run_context['mode']

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
    def event_stream():
        global _run_active
        q = queue.Queue()

        def run_playwright():
            from playwright.sync_api import sync_playwright
            browser = None
            try:
                q.put({"type": "info", "message": f"พื้นที่: {office_name or '-'} | บทบาท: {role} | ตำบลที่จะกรอก: {len(groups)} กลุ่ม"})
                q.put({"type": "info", "message": "กำลังเปิดเบราว์เซอร์..."})
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=headless)
                    context = browser.new_context()
                    page = context.new_page()
                    page.set_default_timeout(PLAYWRIGHT_ACTION_TIMEOUT_MS)
                    page.set_default_navigation_timeout(PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)

                    q.put({"type": "info", "message": "กำลังเข้าสู่ระบบเว็บ T&V..."})
                    page.goto(PORTAL_LOGIN_URL, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)
                    page.wait_for_selector('input[name="USER_NAME"]', state='visible', timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
                    page.wait_for_selector('input[name="USER_PASSWORD"]', state='visible', timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
                    page.fill('input[name="USER_NAME"]', username)
                    page.fill('input[name="USER_PASSWORD"]', password)
                    page.locator('#login_submit').click(timeout=PLAYWRIGHT_ACTION_TIMEOUT_MS)
                    page.wait_for_timeout(2_000)
                    _assert_authenticated(page)

                    for g_idx, (tambon_name, indexed_recs) in enumerate(groups, 1):
                        q.put({"type": "info", "message": f"[{g_idx}/{len(groups)}] เปิด Workflow 26 สำหรับตำบล: {tambon_name}"})
                        page.goto(PORTAL_WORKFLOW_26_URL, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)
                        _assert_authenticated(page)
                        _wait_for_portal_ready(page, f"workflow_26 group {g_idx}")

                        q.put({"type": "info", "message": f"เลือก ปี {year_num}, เดือน {month_name_thai}, ตำบล {tambon_name}"})
                        select_by_value_js(page, 'select#PL_YAER', year_num)
                        _wait_for_select_options(page, 'select#PL_MOUNT', 2, 'after selecting fiscal year')
                        select_by_label_js(page, 'select#PL_MOUNT', month_name_thai)
                        page.wait_for_timeout(700)
                        select_by_label_js(page, 'select#PL_TAMBONN', tambon_name)
                        page.wait_for_timeout(700)

                        for idx, rec in indexed_recs:
                            try:
                                _fill_record_row(page, rec, idx, q)
                            except Exception as e_row:
                                q.put({"type": "row_status", "index": idx, "status": "error",
                                       "message": f"เกิดข้อผิดพลาดแถว {rec.get('id')}: {e_row}"})
                                try:
                                    # Keep diagnostic screenshots transient and server-side only.
                                    # Never publish portal screenshots under /static.
                                    page.screenshot()
                                    q.put({"type": "screenshot", "available": False,
                                           "message": "ซ่อนภาพหน้าจอเพื่อป้องกันข้อมูลจากพอร์ทัลรั่วไหล"})
                                    q.put({"type": "diagnostics", "index": idx, "details": _page_diagnostics(page)})
                                except Exception as screenshot_exc:
                                    q.put({"type": "info", "message": f"แนบ diagnostics/screenshot ไม่สำเร็จ: {type(screenshot_exc).__name__}"})
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

                    q.put({"type": "done", "message": "เสร็จสิ้นภารกิจ!"})
                    # Close while the sync_playwright context is still alive.
                    # The context manager owns teardown after this block; calling
                    # browser.close() later would produce "Event loop is closed".
                    if browser is not None:
                        try:
                            if browser.is_connected():
                                browser.close()
                        except Exception as close_exc:
                            q.put({"type": "info", "message": f"ปิดเบราว์เซอร์ไม่สมบูรณ์: {close_exc}"})
                        finally:
                            browser = None
            except Exception as ex:
                q.put({"type": "error", "message": f"การกรอกข้อมูลหยุดชะงัก: {str(ex)}"})
            finally:
                # sync_playwright() has already handled teardown on error.
                # Do not call browser.close() after its event loop is stopped.
                browser = None
                _run_active = False
                try:
                    _run_lock.release()
                except RuntimeError:
                    pass
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
            # The worker owns the lock and releases it only after Playwright has
            # actually stopped. Do not overwrite the worker's lifecycle state if
            # the SSE client disconnects before the worker finishes.
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
