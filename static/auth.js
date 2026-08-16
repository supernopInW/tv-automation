/* Application access boundary. Loaded before app.js. */
(() => {
    const nativeFetch = window.fetch.bind(window);
    const state = {
        authRequired: false,
        authenticated: false,
        csrfToken: '',
        username: '',
        isAdmin: false,
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

    const publicUnauthPaths = new Set([
        '/api/access/status',
        '/api/auth/login',
        '/api/health',
        '/api/csp-report',
        '/api/auth/invite-info',
        '/api/auth/accept-invite',
    ]);

    const inviteTokenFromUrl = () => {
        const params = new URLSearchParams(window.location.search);
        return (params.get('invite') || '').trim();
    };

    const clearInviteFromUrl = () => {
        const url = new URL(window.location.href);
        if (!url.searchParams.has('invite')) return;
        url.searchParams.delete('invite');
        window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
    };

    const removeOverlay = () => {
        const overlay = document.getElementById('app-auth-overlay');
        if (overlay) overlay.remove();
    };

    const ensureAdminBar = () => {
        if (!state.isAdmin) return;
        if (document.getElementById('app-admin-bar')) return;
        const bar = document.createElement('div');
        bar.id = 'app-admin-bar';
        bar.className = 'app-admin-bar';
        const label = document.createElement('span');
        label.textContent = `ผู้ดูแล: ${state.username || ''}`.trim();
        const inviteBtn = document.createElement('button');
        inviteBtn.type = 'button';
        inviteBtn.id = 'app-admin-invite-btn';
        inviteBtn.textContent = 'สร้างลิงก์เชิญ';
        const status = document.createElement('span');
        status.id = 'app-admin-status';
        status.setAttribute('role', 'status');
        inviteBtn.addEventListener('click', async () => {
            inviteBtn.disabled = true;
            status.textContent = 'กำลังสร้างลิงก์...';
            try {
                const response = await window.fetch('/api/auth/invites', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success || !data.invite_url) {
                    throw new Error(data.error || 'สร้างลิงก์ไม่สำเร็จ');
                }
                try {
                    await navigator.clipboard.writeText(data.invite_url);
                    status.textContent = 'คัดลอกลิงก์เชิญแล้ว ส่งให้ผู้ใช้ใหม่ได้เลย';
                } catch (_clipErr) {
                    status.textContent = data.invite_url;
                }
            } catch (error) {
                status.textContent = error.message || 'สร้างลิงก์ไม่สำเร็จ';
            } finally {
                inviteBtn.disabled = false;
            }
        });
        bar.append(label, inviteBtn, status);
        document.body.prepend(bar);
    };

    const showInviteOverlay = (token) => {
        removeOverlay();
        const overlay = document.createElement('div');
        overlay.id = 'app-auth-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-labelledby', 'app-auth-title');
        overlay.className = 'app-auth-overlay';

        const card = document.createElement('div');
        card.className = 'app-auth-card';
        const title = document.createElement('h1');
        title.id = 'app-auth-title';
        title.textContent = 'รับเชิญเข้าใช้งานแอป';
        const hint = document.createElement('p');
        hint.id = 'app-auth-hint';
        hint.textContent = 'ตั้งชื่อผู้ใช้และรหัสผ่านแอป (ไม่ใช่รหัส T&V) สิทธิ์ตำบลยังใช้บัญชี T&V ของคุณตอนรันงาน';
        overlay.setAttribute('aria-describedby', 'app-auth-hint');

        const usernameLabel = document.createElement('label');
        usernameLabel.htmlFor = 'app-auth-username';
        usernameLabel.textContent = 'ชื่อผู้ใช้แอป';
        const username = document.createElement('input');
        username.id = 'app-auth-username';
        username.name = 'username';
        username.autocomplete = 'username';
        username.required = true;

        const passwordLabel = document.createElement('label');
        passwordLabel.htmlFor = 'app-auth-password';
        passwordLabel.textContent = 'รหัสผ่านแอป (อย่างน้อย 10 ตัวอักษร)';
        const password = document.createElement('input');
        password.id = 'app-auth-password';
        password.name = 'password';
        password.type = 'password';
        password.autocomplete = 'new-password';
        password.required = true;

        const confirmLabel = document.createElement('label');
        confirmLabel.htmlFor = 'app-auth-password-confirm';
        confirmLabel.textContent = 'ยืนยันรหัสผ่าน';
        const confirm = document.createElement('input');
        confirm.id = 'app-auth-password-confirm';
        confirm.type = 'password';
        confirm.autocomplete = 'new-password';
        confirm.required = true;

        const submit = document.createElement('button');
        submit.type = 'button';
        submit.textContent = 'สร้างบัญชีและเข้าสู่ระบบ';
        const status = document.createElement('p');
        status.id = 'app-auth-status';
        status.setAttribute('role', 'status');

        submit.addEventListener('click', async () => {
            if (password.value !== confirm.value) {
                status.textContent = 'รหัสผ่านไม่ตรงกัน';
                return;
            }
            submit.disabled = true;
            status.textContent = 'กำลังสร้างบัญชี...';
            try {
                const response = await nativeFetch('/api/auth/accept-invite', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': state.csrfToken,
                    },
                    body: JSON.stringify({
                        token,
                        username: username.value,
                        password: password.value,
                    }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) {
                    throw new Error(data.error || 'รับเชิญไม่สำเร็จ');
                }
                state.authenticated = true;
                state.username = data.username || username.value;
                state.isAdmin = false;
                state.csrfToken = data.csrf_token || state.csrfToken;
                password.value = '';
                confirm.value = '';
                clearInviteFromUrl();
                overlay.remove();
                window.dispatchEvent(new CustomEvent('app-authenticated'));
            } catch (error) {
                status.textContent = error.message || 'รับเชิญไม่สำเร็จ';
                password.value = '';
                confirm.value = '';
            } finally {
                submit.disabled = false;
            }
        });

        card.append(
            title,
            hint,
            usernameLabel,
            username,
            passwordLabel,
            password,
            confirmLabel,
            confirm,
            submit,
            status,
        );
        overlay.append(card);
        document.body.append(overlay);
        username.focus();
    };

    const showAuthOverlay = () => {
        if (document.getElementById('app-auth-overlay')) return;
        const inviteToken = inviteTokenFromUrl();
        if (inviteToken) {
            showInviteOverlay(inviteToken);
            return;
        }

        const overlay = document.createElement('div');
        overlay.id = 'app-auth-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-labelledby', 'app-auth-title');
        overlay.className = 'app-auth-overlay';

        const card = document.createElement('div');
        card.className = 'app-auth-card';
        const title = document.createElement('h1');
        title.id = 'app-auth-title';
        title.textContent = 'เข้าสู่ระบบแอปพลิเคชัน';
        const hint = document.createElement('p');
        hint.id = 'app-auth-hint';
        hint.textContent = 'กรุณาใช้บัญชีของแอป ไม่ใช่รหัสผ่าน T&V — สิทธิ์ตำบลใช้บัญชี T&V ตอนรันงาน';
        overlay.setAttribute('aria-describedby', 'app-auth-hint');

        const usernameLabel = document.createElement('label');
        usernameLabel.htmlFor = 'app-auth-username';
        usernameLabel.textContent = 'ชื่อผู้ใช้แอป';
        const username = document.createElement('input');
        username.id = 'app-auth-username';
        username.name = 'username';
        username.autocomplete = 'username';
        username.required = true;

        const passwordLabel = document.createElement('label');
        passwordLabel.htmlFor = 'app-auth-password';
        passwordLabel.textContent = 'รหัสผ่านแอป';
        const password = document.createElement('input');
        password.id = 'app-auth-password';
        password.name = 'password';
        password.type = 'password';
        password.autocomplete = 'current-password';
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
                if (!response.ok || !data.success) throw new Error(data.error || 'เข้าสู่ระบบไม่สำเร็จ');
                state.authenticated = true;
                state.username = data.username || username.value;
                state.isAdmin = data.is_admin === true;
                state.csrfToken = data.csrf_token || state.csrfToken;
                password.value = '';
                overlay.remove();
                ensureAdminBar();
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

        card.append(title, hint, usernameLabel, username, passwordLabel, password, submit, status);
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
            state.username = data.username || '';
            state.isAdmin = data.is_admin === true;
            if (state.authRequired && !state.authenticated) {
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', showAuthOverlay, { once: true });
                } else {
                    showAuthOverlay();
                }
            } else if (state.authenticated) {
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', ensureAdminBar, { once: true });
                } else {
                    ensureAdminBar();
                }
            }
            return state;
        })
        .catch(() => state);

    window.fetch = async (input, init = {}) => {
        if (!sameOriginApi(input)) return nativeFetch(input, init);
        const path = apiPath(input);
        if (publicUnauthPaths.has(path)) {
            return nativeFetch(input, init);
        }
        await state.ready;
        if (state.authRequired && !state.authenticated) {
            showAuthOverlay();
            const authError = new Error('กรุณาเข้าสู่ระบบแอปก่อนใช้งาน');
            authError.code = 'APP_AUTH_REQUIRED';
            throw authError;
        }
        const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined));
        if (isMutation(input, init) && state.csrfToken) headers.set('X-CSRF-Token', state.csrfToken);
        return nativeFetch(input, { ...init, credentials: 'same-origin', headers });
    };

    window.appAuth = state;
})();
