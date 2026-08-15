/* Application access boundary. Loaded before app.js. */
(() => {
    const nativeFetch = window.fetch.bind(window);
    const state = {
        authRequired: false,
        authenticated: false,
        csrfToken: '',
        ready: null,
    };

    const sameOriginApi = (input) => {
        const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
        return url.origin === window.location.origin && url.pathname.startsWith('/api/');
    };

    const apiPath = (input) => new URL(
        typeof input === 'string' ? input : input.url,
        window.location.href
    ).pathname;

    const isMutation = (input, init) => {
        const method = String((init && init.method) || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
        return ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);
    };

    const showAuthOverlay = () => {
        if (document.getElementById('app-auth-overlay')) return;
        const overlay = document.createElement('div');
        overlay.id = 'app-auth-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.className = 'app-auth-overlay';

        const card = document.createElement('div');
        card.className = 'app-auth-card';
        const title = document.createElement('h1');
        title.textContent = 'เข้าสู่ระบบแอปพลิเคชัน';
        const hint = document.createElement('p');
        hint.textContent = 'กรุณาใช้บัญชีของแอป ไม่ใช่รหัสผ่าน T&V';
        const username = document.createElement('input');
        username.id = 'app-auth-username';
        username.name = 'username';
        username.autocomplete = 'username';
        username.placeholder = 'ชื่อผู้ใช้แอป';
        username.required = true;
        const password = document.createElement('input');
        password.id = 'app-auth-password';
        password.name = 'password';
        password.type = 'password';
        password.autocomplete = 'current-password';
        password.placeholder = 'รหัสผ่านแอป';
        password.required = true;
        const submit = document.createElement('button');
        submit.type = 'button';
        submit.textContent = 'เข้าสู่ระบบ';
        const status = document.createElement('p');
        status.id = 'app-auth-status';
        status.setAttribute('role', 'status');

        submit.addEventListener('click', async () => {
            submit.disabled = true;
            status.textContent = 'กำลังตรวจสอบ...';
            try {
                const response = await nativeFetch('/api/auth/login', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': state.csrfToken,
                    },
                    body: JSON.stringify({ username: username.value, password: password.value }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) throw new Error('เข้าสู่ระบบไม่สำเร็จ');
                state.authenticated = true;
                state.csrfToken = data.csrf_token || state.csrfToken;
                password.value = '';
                overlay.remove();
                window.dispatchEvent(new CustomEvent('app-authenticated'));
            } catch (_error) {
                status.textContent = 'เข้าสู่ระบบไม่สำเร็จ กรุณาตรวจสอบข้อมูลหรือรอสักครู่';
                password.value = '';
            } finally {
                submit.disabled = false;
            }
        });
        password.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') submit.click();
        });

        card.append(title, hint, username, password, submit, status);
        overlay.append(card);
        document.body.append(overlay);
        username.focus();
    };

    state.ready = nativeFetch('/api/access/status', { credentials: 'same-origin' })
        .then(async (response) => {
            const data = await response.json();
            state.authRequired = data.auth_required === true;
            state.authenticated = data.authenticated === true;
            state.csrfToken = data.csrf_token || '';
            if (state.authRequired && !state.authenticated) {
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', showAuthOverlay, { once: true });
                } else {
                    showAuthOverlay();
                }
            }
            return state;
        })
        .catch(() => state);

    window.fetch = async (input, init = {}) => {
        if (!sameOriginApi(input)) return nativeFetch(input, init);
        const path = apiPath(input);
        if (path === '/api/access/status' || path === '/api/auth/login' || path === '/api/health' || path === '/api/csp-report') {
            return nativeFetch(input, init);
        }
        await state.ready;
        if (state.authRequired && !state.authenticated) {
            showAuthOverlay();
            throw new Error('APP_AUTH_REQUIRED');
        }
        const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined));
        if (isMutation(input, init) && state.csrfToken) headers.set('X-CSRF-Token', state.csrfToken);
        return nativeFetch(input, { ...init, credentials: 'same-origin', headers });
    };

    window.appAuth = state;
})();
