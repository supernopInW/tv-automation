import io
import os
import re
import tempfile
import time

from werkzeug.security import generate_password_hash

# Offline tests intentionally use in-memory limiter storage; production guard
# remains fail-closed in the application runtime.
os.environ['APP_ENV'] = 'test'
os.environ['RATELIMIT_STORAGE_URI'] = 'memory://'
os.environ['APP_USER_REDIS_URI'] = 'memory://'
os.environ['APP_SESSION_SECRET'] = 'test-only-session-secret'


import app as app_module
import user_auth
from app import app


def _bootstrap_test_user(username, password):
    user_auth.reset_for_tests()
    user_auth.configure('memory://')
    app_module.app._user_store_ready = False
    password_hash = generate_password_hash(password)
    app_module.APP_AUTH_USERNAME = username
    app_module.APP_AUTH_PASSWORD_HASH = password_hash
    user_auth.bootstrap_admin(username, password_hash)
    return password_hash


def _csrf_token(client):
    response = client.get('/api/access/status')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['csrf_token']
    return payload['csrf_token']


def test_security_headers_and_csp_report_only():
    client = app.test_client()
    response = client.get('/api/health')
    headers = response.headers
    assert response.status_code == 200
    assert 'Content-Security-Policy-Report-Only' in headers
    assert "default-src 'self'" in headers['Content-Security-Policy-Report-Only']
    assert "script-src 'self'" in headers['Content-Security-Policy-Report-Only']
    assert "script-src-attr 'none'" in headers['Content-Security-Policy-Report-Only']
    assert "style-src-attr 'none'" in headers['Content-Security-Policy-Report-Only']
    assert "frame-ancestors 'none'" in headers['Content-Security-Policy-Report-Only']
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['X-Frame-Options'] == 'DENY'
    assert headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert 'geolocation=()' in headers['Permissions-Policy']
    assert headers['Cache-Control'] == 'no-store'
    assert 'TANDV_PASSWORD' not in headers


def test_index_json_ld_nonce_matches_csp_header():
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    csp = response.headers['Content-Security-Policy-Report-Only']
    nonce_match = re.search(r"'nonce-([^']+)'", csp)
    assert nonce_match is not None
    html = response.get_data(as_text=True)
    assert f'nonce="{nonce_match.group(1)}"' in html



def test_access_status_exposes_csrf_token_without_authentication():
    old_required = app_module.APP_AUTH_REQUIRED
    try:
        app_module.APP_AUTH_REQUIRED = False
        client = app.test_client()
        response = client.get('/api/access/status')
        payload = response.get_json()
        assert response.status_code == 200
        assert payload['success'] is True
        assert payload['auth_required'] is False
        assert payload['authenticated'] is False
        assert len(payload['csrf_token']) >= 20
    finally:
        app_module.APP_AUTH_REQUIRED = old_required


def test_protected_endpoint_requires_app_session_when_auth_enabled():
    old_required = app_module.APP_AUTH_REQUIRED
    old_username = app_module.APP_AUTH_USERNAME
    old_hash = app_module.APP_AUTH_PASSWORD_HASH
    try:
        app_module.APP_AUTH_REQUIRED = True
        _bootstrap_test_user('security-test-user', 'security-test-password')
        client = app.test_client()
        response = client.get('/api/records')
        assert response.status_code == 401
        assert response.get_json()['success'] is False
    finally:
        app_module.APP_AUTH_REQUIRED = old_required
        app_module.APP_AUTH_USERNAME = old_username
        app_module.APP_AUTH_PASSWORD_HASH = old_hash


def test_auth_login_and_mutation_require_csrf_token():
    old_required = app_module.APP_AUTH_REQUIRED
    old_username = app_module.APP_AUTH_USERNAME
    old_hash = app_module.APP_AUTH_PASSWORD_HASH
    try:
        app_module.APP_AUTH_REQUIRED = True
        _bootstrap_test_user('security-test-user', 'security-test-password')
        client = app.test_client()
        csrf = _csrf_token(client)

        missing_csrf = client.post(
            '/api/auth/login',
            json={'username': 'security-test-user', 'password': 'security-test-password'},
        )
        assert missing_csrf.status_code == 403

        login = client.post(
            '/api/auth/login',
            json={'username': 'security-test-user', 'password': 'security-test-password'},
            headers={'X-CSRF-Token': csrf},
        )
        assert login.status_code == 200
        new_csrf = login.get_json()['csrf_token']
        assert new_csrf and new_csrf != csrf

        missing_mutation_csrf = client.post('/api/add-row', json={})
        assert missing_mutation_csrf.status_code == 403
    finally:
        app_module.APP_AUTH_REQUIRED = old_required
        app_module.APP_AUTH_USERNAME = old_username
        app_module.APP_AUTH_PASSWORD_HASH = old_hash


def test_upload_rejects_disallowed_extension_and_invalid_magic_bytes():
    old_required = app_module.APP_AUTH_REQUIRED
    try:
        app_module.APP_AUTH_REQUIRED = False
        client = app.test_client()
        csrf = _csrf_token(client)

        bad_extension = client.post(
            '/api/upload',
            headers={'X-CSRF-Token': csrf},
            data={'file': (io.BytesIO(b'not-an-excel-file'), 'payload.txt')},
            content_type='multipart/form-data',
        )
        assert bad_extension.status_code == 400
        assert 'ไม่สามารถตรวจสอบ' in bad_extension.get_json()['error'] or 'รูปแบบไฟล์' in bad_extension.get_json()['error']

        bad_magic = client.post(
            '/api/upload',
            headers={'X-CSRF-Token': csrf},
            data={'file': (io.BytesIO(b'not-a-zip-package'), 'payload.xlsx')},
            content_type='multipart/form-data',
        )
        assert bad_magic.status_code == 400
        assert 'ไม่สามารถตรวจสอบ' in bad_magic.get_json()['error']
    finally:
        app_module.APP_AUTH_REQUIRED = old_required


def test_upload_registry_binds_path_to_owner():
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(b'test upload placeholder')
        path = handle.name
    upload_id = 'opaque-security-test-id'
    try:
        with app.test_request_context('/', environ_base={'REMOTE_ADDR': '127.0.0.1'}):
            owner = app_module._upload_owner_key()
            app_module.UPLOAD_REGISTRY[upload_id] = {
                'path': path,
                'owner': owner,
                'created_at': time.time(),
            }
            assert app_module._get_owned_upload_path(upload_id) == path
            app_module.UPLOAD_REGISTRY[upload_id]['owner'] = 'different-owner'
            assert app_module._get_owned_upload_path(upload_id) is None
    finally:
        app_module.UPLOAD_REGISTRY.pop(upload_id, None)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass



def test_server_side_profile_rejects_client_supplied_scope_and_submit():
    old_required = app_module.APP_AUTH_REQUIRED
    old_username = app_module.APP_AUTH_USERNAME
    old_hash = app_module.APP_AUTH_PASSWORD_HASH
    old_role = app_module.APP_AUTH_ROLE
    old_office = app_module.APP_AUTH_OFFICE_NAME
    old_tambons = app_module.APP_AUTH_ALLOWED_TAMBONS
    old_approvers = app_module.APP_AUTH_ALLOWED_APPROVERS
    old_can_submit = app_module.APP_AUTH_CAN_SUBMIT
    try:
        app_module.APP_AUTH_REQUIRED = True
        app_module.APP_AUTH_USERNAME = 'security-test-user'
        app_module.APP_AUTH_PASSWORD_HASH = generate_password_hash('security-test-password')
        app_module.APP_AUTH_ROLE = 'officer'
        app_module.APP_AUTH_OFFICE_NAME = 'สำนักงานทดสอบ'
        app_module.APP_AUTH_ALLOWED_TAMBONS = frozenset({'ตำบลหนองตาดใหญ่'})
        app_module.APP_AUTH_ALLOWED_APPROVERS = frozenset({'ผู้อนุมัติทดสอบ'})
        app_module.APP_AUTH_CAN_SUBMIT = False

        context, error = app_module._validate_run_authorization({
            'selected_tambons': ['ตำบลอื่น'],
            'tambon': 'ตำบลอื่น',
            'role': 'admin_clerk',
            'office_name': 'สำนักงานอื่น',
            'approver': 'ผู้อนุมัติอื่น',
            'mode': 'submit',
            'records': [],
        })
        assert context is None
        assert error[1] == 403

        context, error = app_module._validate_run_authorization({
            'selected_tambons': ['ตำบลหนองตาดใหญ่'],
            'tambon': 'ตำบลหนองตาดใหญ่',
            'role': 'admin_clerk',
            'office_name': 'สำนักงานอื่น',
            'approver': 'ผู้อนุมัติทดสอบ',
            'mode': 'submit',
            'records': [{'tambon': 'ตำบลหนองตาดใหญ่'}],
        })
        assert context is None
        assert error[1] == 403
    finally:
        app_module.APP_AUTH_REQUIRED = old_required
        app_module.APP_AUTH_USERNAME = old_username
        app_module.APP_AUTH_PASSWORD_HASH = old_hash
        app_module.APP_AUTH_ROLE = old_role
        app_module.APP_AUTH_OFFICE_NAME = old_office
        app_module.APP_AUTH_ALLOWED_TAMBONS = old_tambons
        app_module.APP_AUTH_ALLOWED_APPROVERS = old_approvers
        app_module.APP_AUTH_CAN_SUBMIT = old_can_submit


def test_frontend_does_not_persist_credentials_or_public_screenshot_url():
    with open('static/app.js', encoding='utf-8') as handle:
        source = handle.read()
    with open('app.py', encoding='utf-8') as handle:
        backend_source = handle.read()
    with open('automate_submission.py', encoding='utf-8') as handle:
        cli_source = handle.read()
    assert "localStorage.setItem('tv_username'" not in source
    assert "localStorage.getItem('tv_username'" not in source
    assert "localStorage.setItem('tv_password'" not in source
    # Tab session (sessionStorage) is the allowed place to hold T&V credentials.
    assert "sessionStorage.setItem('tv_username'" in source
    assert "sessionStorage.setItem('tv_password'" in source
    assert "getElementById('username')" in source
    assert "getElementById('password')" in source
    assert "page.fill('input[name=\"USER_PASSWORD\"]'" in backend_source
    assert 'TV_PASSWORD' not in cli_source
    assert 'getpass' not in cli_source
    with open('templates/index.html', encoding='utf-8') as handle:
        template_source = handle.read()
    with open('requirements.txt', encoding='utf-8') as handle:
        requirements_source = handle.read()
    assert 'gemini' not in source.lower()
    assert 'X-Gemini-API-Key' not in source
    assert 'gemini' not in backend_source.lower()
    assert 'google-genai' not in requirements_source.lower()
    assert 'gemini' not in template_source.lower()
    assert 'id="username"' in template_source
    assert 'id="password"' in template_source
    assert 'id="tv-status-chip"' in template_source
    assert "localStorage.setItem('gemini_api_key'" not in source
    assert "localStorage.getItem('gemini_api_key'" not in source
    assert '/static/${shot_name}' not in backend_source
    assert 'screenshot(path=' not in backend_source
    assert 'screenshot(path=' not in cli_source
    assert 'modal_error.html' not in cli_source
    diagnostics_start = backend_source.index('def _page_diagnostics')
    diagnostics_end = backend_source.index('def _wait_for_portal_ready', diagnostics_start)
    diagnostics_source = backend_source[diagnostics_start:diagnostics_end]
    assert 'bodyText:' not in diagnostics_source
    assert 'document.title' not in diagnostics_source
    assert 'value: el.value' not in diagnostics_source


if __name__ == '__main__':
    tests = [
        test_security_headers_and_csp_report_only,
        test_index_json_ld_nonce_matches_csp_header,
        test_access_status_exposes_csrf_token_without_authentication,
        test_protected_endpoint_requires_app_session_when_auth_enabled,
        test_auth_login_and_mutation_require_csrf_token,
        test_upload_rejects_disallowed_extension_and_invalid_magic_bytes,
        test_upload_registry_binds_path_to_owner,
        test_frontend_does_not_persist_credentials_or_public_screenshot_url,
    ]
    for test in tests:
        test()
        print(f'PASS {test.__name__}')
