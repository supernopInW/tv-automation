import io
import os
import tempfile
import time

from werkzeug.security import generate_password_hash

import app as app_module
from app import app


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
        app_module.APP_AUTH_USERNAME = 'security-test-user'
        app_module.APP_AUTH_PASSWORD_HASH = generate_password_hash('security-test-password')
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
        app_module.APP_AUTH_USERNAME = 'security-test-user'
        app_module.APP_AUTH_PASSWORD_HASH = generate_password_hash('security-test-password')
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


def test_frontend_does_not_persist_credentials_or_public_screenshot_url():
    with open('static/app.js', encoding='utf-8') as handle:
        source = handle.read()
    with open('app.py', encoding='utf-8') as handle:
        backend_source = handle.read()
    with open('automate_submission.py', encoding='utf-8') as handle:
        cli_source = handle.read()
    assert "localStorage.setItem('tv_username'" not in source
    assert "localStorage.getItem('tv_username'" not in source
    assert "sessionStorage.setItem('tv_password'" not in source
    assert "sessionStorage.getItem('tv_password'" not in source
    assert "localStorage.setItem('gemini_api_key'" not in source
    assert "localStorage.getItem('gemini_api_key'" not in source
    assert '/static/${shot_name}' not in backend_source
    assert 'screenshot(path=' not in backend_source
    assert 'screenshot(path=' not in cli_source
    assert 'modal_error.html' not in cli_source


if __name__ == '__main__':
    tests = [
        test_security_headers_and_csp_report_only,
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
