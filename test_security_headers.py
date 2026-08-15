from app import app


def main():
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
    print('PASS CSP report-only and security headers')


if __name__ == '__main__':
    main()
