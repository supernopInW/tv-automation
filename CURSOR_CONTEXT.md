# CURSOR CONTEXT — DOAE T&V AUTOMATION / WORKFLOW 26

> ไฟล์นี้เป็น **บริบทหลักแบบรวมทุกเรื่องไว้ในไฟล์เดียว** สำหรับใช้เปิดใน Cursor IDE และให้ AI ใน Cursor อ่านก่อนแก้ไข repository. เนื้อหาครอบคลุม architecture, business logic, Workflow 26, API, security hardening, Render production, WCAG, keyboard/screen reader, automated accessibility tests, modal patch proposal และขั้นตอนทำงานต่อ

**Repository:** `https://github.com/supernopInW/tv-automation`  
**Live service:** `https://tv-automation.onrender.com`  
**Production source:** source tree ที่ root ของ repository  
**Current merged commit:** `e818d5f`  
**Service ID:** `srv-d9o5jvlaeets73d4tfp0`  
**สถานะเอกสาร:** รวมจากงานตรวจสอบล่าสุด; ไม่มี password, hash, session secret, T&V credential, Redis URL จริง หรือ token ใด ๆ

---

## 0. กฎสำคัญสำหรับ Cursor Agent

ก่อนแก้ไฟล์ใด ๆ ให้ตรวจ `AGENTS.md` และไฟล์นี้ก่อนเสมอ. Production source อยู่ที่ root; `Ready_For_GitHub/`, `Upload_To_GitHub/` และ archive อื่น ๆ ไม่ใช่ source ที่ deploy โดยอัตโนมัติ ต้องตรวจ diff และ scope ให้ชัดก่อนแก้

ห้ามเปิดเผยหรือบันทึก secret ทุกชนิด ได้แก่ password, password hash, session secret, T&V credential, Redis URL จริง, API token, cookie หรือข้อมูลส่วนบุคคลจาก Excel/portal. ห้ามส่ง credential ผ่าน chat, test fixture, screenshot, trace, log, GitHub issue หรือ commit

ห้ามกดหรือเรียกการทำงานที่ทำให้เกิด Draft/Submit T&V ระหว่างการทดสอบ. ใช้ `dry_run`, local fixture, mocked API หรือ staging synthetic data เท่านั้น. คง `APP_AUTH_CAN_SUBMIT=0` จนกว่าจะได้รับอนุมัติสิทธิ์อย่างชัดเจน

ห้ามลด `APP_AUTH_REQUIRED`, ห้าม bypass server-side ACL, ห้ามใช้ `memory://` ใน production, ห้ามปิด security gate เพื่อให้ pipeline ผ่าน, ห้ามปิด axe rules กว้าง ๆ เพื่อให้ accessibility test เขียว และห้ามชี้ CI accessibility test ไป production

เมื่อแก้เสร็จให้รันอย่างน้อย:

```bash
node --check static/auth.js
node --check static/app.js
node --check static/csp-bindings.js
python test_security_headers.py
python test_security_check.py
python test_workflow26_hardening.py
python scripts/security_check.py
git diff --check
```

หากมีการแก้ modal/accessibility ให้เพิ่มหรือปรับ regression test, รัน local/staging เท่านั้น และตรวจว่าไม่มี portal navigation, `/api/run`, Draft หรือ Submit เกิดขึ้น

---

## 1. ภาพรวมระบบ

ระบบนี้เป็น Flask web application สำหรับจัดทำและกรอกแผนปฏิบัติงานเยี่ยมเยียนรายเดือนของระบบส่งเสริมการเกษตร DOAE T&V. ผู้ใช้สามารถนำเข้าแผนจาก Excel หรือสร้างแผนจากหน้าเว็บ ตรวจทานตาราง และสั่งให้ Playwright ทำงาน Workflow 26 บน T&V Portal

ลำดับใช้งานหลักคือ:

1. ผู้ใช้เข้าสู่ application authentication ของ `tv-automation`
2. กำหนด role, จังหวัด, อำเภอ, สำนักงาน และตำบลที่รับผิดชอบ
3. อัปโหลด `.xls`/`.xlsx` หรือเลือกสร้างแผนอัตโนมัติบนเว็บ
4. เลือกเดือน วันหยุด กิจกรรม และการสุ่มหมู่บ้าน/หมู่
5. ตรวจทานและแก้ไขตารางแผนงาน
6. กรอกบัญชี T&V ใน memory ระหว่างการทำงานตาม policy
7. เลือก `dry_run`, `draft` หรือ `submit`
8. ส่งคำสั่งผ่าน `/api/run` และติดตามผลผ่าน SSE stream

การทดสอบทั้งหมดต้องเริ่มที่ `dry_run` หรือ fixture. `draft` และ `submit` เป็น operations ที่มีผลต่อข้อมูลปลายทาง ไม่ใช้ระหว่าง security/accessibility regression

---

## 2. Tech Stack และ Deployment

| ส่วน | เทคโนโลยี/หน้าที่ |
|---|---|
| Backend | Python 3, Flask, Gunicorn 26.0.0 |
| Browser automation | Playwright sync API, Chromium headless |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Frontend modules | `static/auth.js`, `static/csp-bindings.js`, `static/app.js` |
| Spreadsheet | pandas 2.3.3, numpy 2.2.6, openpyxl, xlrd |
| Security | CSRF, server-side ACL, CSP, upload ownership/TTL, rate limiting |
| Rate limiter | Flask-Limiter 4.1.1 พร้อม Redis storage ใน production |
| Container | Docker, Playwright Python base image, non-root `appuser` |
| Deployment | Render.com web service |
| Live URL | `https://tv-automation.onrender.com` |
| AI integration | ตัด Gemini/AI API ออกจากระบบแล้ว |

Docker ปัจจุบันใช้ Gunicorn แบบ worker เดียวและ threads 4:

```text
gunicorn -b 0.0.0.0:7860 --workers 1 --threads 4 --timeout 600 app:app
```

`_run_lock` จึงเป็น process-local และสอดคล้องกับ deployment ปัจจุบัน. หากเพิ่ม worker หรือ scale หลาย instance ต้องออกแบบ distributed lock ใหม่ ไม่ควรถือว่า in-process lock ป้องกัน concurrent run ได้ทุกกรณี

---

## 3. โครงสร้างไฟล์สำคัญ

| ไฟล์ | หน้าที่ |
|---|---|
| `app.py` | Flask app, config, auth boundary, CSRF, ACL, upload registry, rate limiting, API และ Workflow 26 runner |
| `templates/index.html` | HTML หลัก, form, table shell, manual modal, confirmation modal, script order |
| `static/app.js` | frontend state, geo controls, table rendering, auto plan, modal handlers, SSE/log UI |
| `static/auth.js` | application auth overlay, CSRF token state และ fetch wrapper |
| `static/csp-bindings.js` | delegated event binding ผ่าน `data-csp-*` เพื่อรองรับ CSP Enforce |
| `static/style.css` | layout, form, table, modal, responsive และ visual states |
| `static/auth.css` | app-auth overlay/card styles |
| `scripts/security_check.py` | static security hard gate 14 assertions |
| `test_security_headers.py` | security headers, auth, CSRF, upload owner, ACL, diagnostics, nonce tests |
| `test_security_check.py` | checker invocation และ Docker/security contract tests |
| `test_workflow26_hardening.py` | Workflow 26 hardening และ CSRF contract tests |
| `test_selector2_readiness.py` | readiness/selector timeout contract |
| `test_clear_credentials.js` | credential memory-clearing regression test |
| `Dockerfile` | production image, non-root user, upload directory และ Gunicorn command |
| `docker-compose.yml` | local container, bind `127.0.0.1:7860`, appuser และ auth defaults |
| `requirements.txt` | exact-pinned Python dependencies |
| `requirements.lock` | reproducible Python lock file |
| `.github/workflows/security.yml` | Security Gate, tests, syntax, audit, Semgrep, CodeQL, Docker validation |
| `.github/codeql/codeql-config.yml` | CodeQL scope; ตัด archive ที่ทำให้เกิด duplicate findings |
| `AGENTS.md` | repository rules, history และ audit records |
| `docs/DEPLOY.md` | production environment contract และ Render guide |
| `docs/WORKFLOW.md` | Excel → Workflow 26 และ business rules |
| `docs/USER_GUIDE.md` | คู่มือผู้ใช้ภาษาไทย |
| `docs/WCAG_REVIEW.md` | WCAG review และ remediation priorities |
| `docs/ACCESSIBILITY_TESTING_WORKFLOW26.md` | manual keyboard/NVDA/VoiceOver checklist |
| `docs/AUTOMATED_ACCESSIBILITY_TESTING_WORKFLOW26.md` | Playwright + axe-core/Jest + CI strategy |
| `docs/MODAL_ACCESSIBILITY_PATCH_PROPOSAL.md` | modal/focus-trap patch proposal; ยังไม่ apply |
| `a11y-tests/` | ตัวอย่าง Playwright accessibility workspace; ยังไม่ติดตั้ง dependency |

---

## 4. Workflow 26 และ Business Logic

### 4.1 โหมดทำงาน

| Mode | ความหมาย | ใช้ระหว่าง test หรือไม่ |
|---|---|---|
| `dry_run` | ตรวจ flow/ข้อมูลโดยไม่ finalize | ใช้เป็นค่าเริ่มต้นและใช้ทดสอบ |
| `draft` | บันทึกชั่วคราวบน portal | ห้ามใช้ระหว่าง test เว้นแต่ได้รับอนุมัติ |
| `submit` | บันทึกและส่งให้ผู้อนุมัติ | ห้ามใช้ระหว่าง test และถูกคุมด้วย `APP_AUTH_CAN_SUBMIT=0` |

### 4.2 กฎวันจันทร์

วันจันทร์ใช้กฎประชุมสำนักงาน DM/WM. วันอื่นใช้กิจกรรมภาคสนาม. เมื่อ issue/activity เปลี่ยนต้อง re-apply office meeting rule, target, location และ description ให้สอดคล้องกัน ห้ามแก้ field ใด field หนึ่งโดยไม่ตรวจ state ของทั้ง row

### 4.3 การสุ่มพื้นที่

ระบบเลือกจังหวัด/อำเภอ/ตำบลตามพื้นที่ที่ผู้ใช้รับผิดชอบ. การสุ่มหมู่บ้าน/หมู่ต้องอยู่ใน authorized tambon และต้องตรวจ server-side scope อีกครั้งใน `/api/run` ไม่เชื่อ hidden input หรือ value จาก client เพียงอย่างเดียว

### 4.4 Activity และ modal ของ portal

ลำดับที่ต้องรักษาใน Workflow 26 ได้แก่:

1. dynamic issue/activity selection
2. `PD_OTHER` สำหรับ activity `999`
3. generic events ตามหน้า portal
4. final activity re-apply หลัง dependent controls เปลี่ยน
5. ตั้ง `PD_SDATE` และ `PD_EDATE` เป็นขั้นตอนท้าย
6. validate DOM/state ก่อน finalize
7. ตรวจว่า portal modal ถูกซ่อนหรือสถานะยืนยันเสร็จจริง
8. บันทึกผลตาม mode ที่อนุญาต

Portal อาจล้าง `PD_EDATE` เมื่อ `PD_SDATE` เกิด `change`; จึงต้องตั้งทั้งสอง field ในขั้นตอนท้ายและตรวจค่าหลัง event

หากผลลัพธ์เป็น `FINALIZE_UNKNOWN_RESULT` ต้องหยุดและตรวจ portal ด้วยคน ห้าม retry อัตโนมัติ เพราะอาจทำให้เกิดรายการซ้ำหรือส่งข้อมูลซ้ำ

---

## 5. API Contract

| Method | Route | ขอบเขต/หน้าที่ |
|---|---|---|
| `GET` | `/api/health` | public health check; ไม่เปิดเผย secret |
| `GET` | `/api/access/status` | auth status และ CSRF token ตาม contract |
| `POST` | `/api/auth/login` | login ของแอป; ไม่ใช่ login T&V; มี brute-force limit |
| `POST` | `/api/auth/logout` | ล้าง application session |
| `GET` | `/api/geo` | รายการจังหวัด/อำเภอ/ตำบล |
| `GET` | `/api/sheets` | sheet จาก workbook upload |
| `POST` | `/api/upload` | รับ Excel, validate และคืน opaque `upload_id` |
| `GET` | `/api/records` | อ่าน records ตาม upload/session owner |
| `POST` | `/api/add-row` | เพิ่ม blank row; มี rate limit |
| `GET` | `/api/historical-activities` | กิจกรรมเก่าสำหรับสร้างแผน |
| `POST` | `/api/run` | ตรวจ auth/ACL/mode แล้วเริ่ม Workflow 26 |
| `GET` | `/api/stream/<run_id>` | SSE progress/status |

API boundary จริงอยู่ที่ `enforce_api_access_boundary()` ใน `before_request`; อย่าถือว่า `PROTECTED_API_PATHS` หรือ `PUBLIC_API_PATHS` เป็น enforcement เพียงอย่างเดียว ต้องตรวจ flow จริงร่วมด้วย

Root source ยังไม่มี route `/api/csp-report` ที่ลงทะเบียน แม้ middleware จะมี path exception. อย่าถือว่า CSP reporting ใช้งานได้ จนกว่าจะเพิ่ม endpoint, validation และ test อย่างตั้งใจ

GET read-only routes ไม่ต้องใช้ CSRF header แต่ POST/PUT/PATCH/DELETE ต้องมี `X-CSRF-Token` ที่สัมพันธ์กับ session

---

## 6. Security Architecture

### 6.1 Application authentication

`APP_AUTH_REQUIRED=1` เป็น fail-closed default. เมื่อเปิด production ระบบต้องมี username, Werkzeug password hash และ random session secret. หากค่าขาด startup ต้องหยุด ไม่ควร fallback เป็น unauthenticated mode

Application login แยกจาก T&V login. `static/auth.js` สร้าง overlay สำหรับ login ของแอปและ inject CSRF header ให้ same-origin mutation requests. T&V username/password ไม่ควรเก็บถาวรบน server หรือ browser storage ที่ไม่จำเป็น

### 6.2 Server-side authorization profile

สิทธิ์ต้อง derive จาก environment/server profile ได้แก่:

- `role`
- `office_name`
- `allowed_tambons`
- `allowed_approvers`
- `can_submit`

ข้อมูลที่ client ส่งมา เช่น role/tambon/approver/submit mode ต้องถือเป็นคำขอที่ต้อง validate ไม่ใช่ authority. `APP_AUTH_CAN_SUBMIT=0` ต้องคงไว้จนได้รับอนุมัติ

### 6.3 CSRF

Mutation requests ใช้ `X-CSRF-Token`. `static/auth.js` รักษา token ใน application state และ fetch wrapper เติม header ให้ same-origin mutation. ห้ามยกเว้น CSRF ให้ route ที่เปลี่ยนข้อมูลเพียงเพราะเรียกว่า “test”

### 6.4 Upload security

Upload ใช้ opaque upload ID แทนชื่อไฟล์จริง, ตรวจ owner/session, ขนาด, extension, workbook structure และ TTL. ไฟล์อยู่ใน `/tmp/tv-automation-uploads` และไม่ควรเขียนลง `/static/` หรือเปิดเป็น public download โดยตรง

### 6.5 CSP และ DOM safety

Production policy ตั้งใจใช้ enforce:

```text
default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none';
frame-src 'none'; form-action 'self'; script-src 'self' 'nonce-{nonce}';
script-src-attr 'none'; style-src 'self' https://fonts.googleapis.com;
style-src-attr 'none'; font-src 'self' https://fonts.gstatic.com;
img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:;
manifest-src 'self'; media-src 'none'
```

`index.html` โหลด `auth.js`, `csp-bindings.js`, `app.js` ตามลำดับ. Inline handlers/styles ถูกย้ายไป `data-csp-*` และ external files. JSON-LD ใช้ per-request nonce

เมื่อ renderข้อมูลจาก Excel/user input ให้ใช้ `createElement`, `textContent`, DOM properties หรือ safe attribute setters. Legacy `innerHTML` ที่ยังอยู่ต้องมี reviewed annotation และต้องไม่รับข้อมูล untrusted โดยตรง

### 6.6 Docker

Docker ใช้ non-root `appuser`, `COPY --chown`, upload directory mode จำกัด และไม่ใช้ `chmod 777`. Compose bind ที่ `127.0.0.1:7860:7860` และใช้ user ที่ไม่ใช่ root

---

## 7. Rate Limiting

| Endpoint | Limit |
|---|---:|
| `POST /api/auth/login` | 5 ต่อนาที และ 20 ต่อชั่วโมง |
| `POST /api/upload` | 5 ต่อ 10 นาที |
| `POST /api/add-row` | 30 ต่อนาที |
| `GET /api/records` | 30 ต่อนาที |
| `POST /api/run` | 2 ต่อ 10 นาที |

Production ต้องใช้ `RATELIMIT_STORAGE_URI` เป็น Redis/Valkey Internal URL. ห้ามใช้ `memory://` เพราะ state ไม่แชร์ระหว่าง process/instance และหายเมื่อ restart

Current key ใช้ client address. หลัง reverse proxy ต้องตรวจว่า IP ถูกอ่านถูกต้อง; หากผู้ใช้จำนวนมากอยู่หลัง NAT/proxy อาจถูกรวม rate-limit key. Routes geo, sheets, historical activities และ logout ยังไม่มี decorator แยก ต้องทบทวนหาก traffic เพิ่ม

---

## 8. Render Production Contract

ตัวแปรที่ต้องมีบน Render service:

```text
APP_ENV=production
APP_AUTH_REQUIRED=1
APP_AUTH_USERNAME=<app username>
APP_AUTH_PASSWORD_HASH=<Werkzeug hash; ห้ามใส่ค่าจริงในเอกสาร>
APP_SESSION_SECRET=<random secret; ห้ามใส่ค่าจริงในเอกสาร>
APP_AUTH_ROLE=<authorized role>
APP_AUTH_OFFICE_NAME=<authorized office>
APP_AUTH_ALLOWED_TAMBONS=<comma-separated authorized tambons>
APP_AUTH_ALLOWED_APPROVERS=<comma-separated authorized approvers>
APP_AUTH_CAN_SUBMIT=0
RATELIMIT_STORAGE_URI=<Render Internal Redis/Valkey URL from Connect>
```

ปัญหาที่เคยค้าง:

1. `APP_AUTH_ROLE` อาจยังไม่ได้ตั้ง
2. `APP_AUTH_OFFICE_NAME` อาจยังไม่ได้ตั้ง
3. `APP_AUTH_ALLOWED_TAMBONS` อาจยังไม่ได้ตั้ง
4. `APP_AUTH_ALLOWED_APPROVERS` อาจยังไม่ได้ตั้ง
5. `APP_AUTH_CAN_SUBMIT` ควรเป็น `0`
6. `APP_SESSION_SECRET` ต้องไม่ใช่ placeholder
7. `RATELIMIT_STORAGE_URI` ห้ามใช้ `https://tv-automation.onrender.com/`; ต้องใช้ Internal URL จาก Render Key Value เมนู Connect

Production guards:

1. production + `memory://` → RuntimeError
2. production + auth secrets ไม่ครบ → RuntimeError
3. production + authorization profile ไม่ครบ → RuntimeError

อย่าลด guards เพื่อให้ deployment ผ่าน. ให้แก้ Environment Variables ที่ Render, Save/Deploy, ตรวจ logs, health และ access status แทน

---

## 9. สถานะ Security และ Git

PR #4 ถูก squash merge เข้า `main` ด้วย `e818d5f`. Security Gate ที่ผ่านประกอบด้วย Docker build, CodeQL, Semgrep, dependency audit, secret scan และ regression tests. CodeQL scope ตัด archive ออกจาก production root เพื่อหลีกเลี่ยง duplicate findings. Docker แก้ UID conflict ด้วย `groupadd --system appuser`. Dependencies สำคัญถูก pin เพื่อ production image

Working tree ณ งานเอกสารล่าสุดมีไฟล์เอกสาร/ตัวอย่าง accessibility ที่ยังไม่ได้ commit โดยไม่ควร stage ไฟล์ที่ไม่ได้ตั้งใจ. ตรวจด้วย:

```bash
git status --short
git diff --check
git diff --stat
```

คำสั่ง commit ที่ปลอดภัยสำหรับ documentation bundle:

```bash
git add -- AGENTS.md CURSOR_CONTEXT.md \
  docs/WCAG_REVIEW.md \
  docs/ACCESSIBILITY_TESTING_WORKFLOW26.md \
  docs/AUTOMATED_ACCESSIBILITY_TESTING_WORKFLOW26.md \
  docs/MODAL_ACCESSIBILITY_PATCH_PROPOSAL.md \
  a11y-tests/

git diff --cached --check
git diff --cached --name-only
git diff --cached

git commit -m "docs: consolidate Cursor and accessibility guidance"
```

ก่อน commit ต้องเห็นเฉพาะไฟล์ที่ตั้งใจและตรวจว่าไม่มี `.env`, credential, hash, session secret, Redis URL จริง, screenshot, trace หรือ test artifact ที่มีข้อมูลส่วนบุคคล. คำสั่งข้างต้นไม่มี `git push`

---

## 10. WCAG Status

เว็บไซต์มีพื้นฐานที่ดี เช่น `lang="th"`, skip link, semantic header/nav/main/footer, headings, visible labels ของ form หลัก และ native HTML controls หลายส่วน. อย่างไรก็ตามยังไม่ควรประกาศ WCAG 2.2 AA conformance

| ประเด็น | หลักฐาน/ความเสี่ยง |
|---|---|
| Contrast | `--text-muted #64748b` บน `#0b0f19` คำนวณแบบ solid ได้ประมาณ `4.02:1`, ต่ำกว่า 4.5:1 สำหรับ normal text |
| Focus | พบ `outline: none` ใน `.form-input`, `.cell-input`, `.btn-glow`; ยังไม่มี global `:focus-visible` ครอบคลุม |
| Table | static table ไม่มี `<caption>`/explicit `scope`; dynamic controls มี accessible name/context ไม่ครบ |
| Modal | manual/confirmation ขาด dialog semantics/focus lifecycle; app-auth ยังขาด labels/trap/Escape ที่ครบ |
| Upload | drop zone เป็น `div` click/drag และ file input ซ่อนด้วย `display:none`; ต้องมี keyboard fallback |
| Dynamic status | progress/log/error ต้องตรวจ `aria-live`/`role=status`/`role=alert` ให้เหมาะสม |
| Motion | ยังไม่พบ `prefers-reduced-motion` |
| Error screenshot | ควรซ่อน empty container/image จนกว่าจะมีภาพจริง |

ข้อความที่ปลอดภัยในการสื่อสารคือ:

> เว็บไซต์มีการเตรียม accessibility ตามแนวทาง WCAG หลายส่วน และอยู่ระหว่างการปรับปรุง/ทดสอบเพื่อยืนยัน WCAG 2.2 AA; ยังไม่มีการรับรอง conformance อย่างเป็นทางการ

W3C ระบุว่า success criteria ต้องตรวจสอบได้ และการประเมินที่เชื่อถือได้ต้องใช้ทั้ง automated และ human evaluation [1] [2]

---

## 11. Keyboard Navigation Test

ทดสอบบน local/staging ด้วย synthetic fixture. ห้ามใช้ production credential และห้ามทำ portal mutation

### 11.1 Global

1. เปิดหน้าใหม่และกด `Tab`; focus แรกต้องเป็น skip link
2. กด `Enter`; focus ไป `#main-content`
3. กด `Tab` ต่อเนื่อง; focus order ต้องเป็นตรรกะและไม่เข้า hidden control
4. ใช้ `Shift+Tab` ย้อนกลับได้
5. ใช้ `Enter`/`Space` กับปุ่มได้
6. focus indicator ต้องมองเห็นและไม่ถูก overlay บัง
7. ทดสอบ viewport แคบและ zoom 200–400%

### 11.2 Form/พื้นที่

ตรวจ role, officer, province, amphoe, office, staff count, tambon controls, select-all/clear, chips และ confirm responsibility. Multi-select ต้องเปิด/ปิดด้วย keyboard, ประกาศ expanded state และเลือก/ลบรายการได้

### 11.3 Upload/auto-plan

ตรวจว่า upload มี keyboard entry point ไม่ต้องพึ่ง drag-and-drop. เลือกไฟล์ synthetic แล้วต้องประกาศชื่อ/สถานะ. สลับ Excel/auto-plan, เลือกเดือน, holiday buttons และ generate ด้วย keyboard ได้

**Known gap:** `#drop-zone` เป็น `div` ที่รับ click/drag และ `#file-input` ใช้ `display:none`; Playwright test ควร fail จนกว่าจะมี visible button/label ที่ focus ได้

### 11.4 Table

ตรวจการแก้ date/detail/place/target, select issue/activity, add/delete row, status และ validation. ทุก control ต้องมี accessible name ที่รวม row context เช่น “แถว 1 วันที่” และปุ่มลบต้องไม่ชื่อเพียง emoji หรือ “button”

### 11.5 Modal

เปิด manual/confirmation/auth modal แล้วตรวจ initial focus, Tab wrap, Shift+Tab wrap, Escape, close button และ focus return. ห้ามกด confirm ที่อาจเรียก `executeAutomation()`

---

## 12. Screen Reader Test

### 12.1 NVDA บน Windows

ใช้ Chrome/Firefox + NVDA Speech Viewer. ตรวจ document title, language, headings ด้วย `H`, landmarks ด้วย `D`, buttons ด้วย `B`, form fields ด้วย `F/E`, checkbox ด้วย `X`, combo box ด้วย `C`, table ด้วย `T` และ Elements List ด้วย `NVDA+F7`

ตรวจว่า:

- ชื่อหน้าและภาษาไทยถูกอ่านถูกต้อง
- headings `h1 → h2 → h3` เข้าใจได้
- labels ตรงกับ visible labels
- checkbox/radio/select อ่าน state ได้
- dynamic row บอก row/field context
- error/status ถูกประกาศเมื่อเกิดการเปลี่ยนแปลง
- modal อ่านชื่อและคำอธิบายได้
- focus ไม่หลุดไป background
- เมื่อปิด modal focus กลับ trigger เดิม

### 12.2 VoiceOver บน macOS

เปิด VoiceOver ด้วย `Command+F5`, ใช้ `Control+Option+Right Arrow` ไล่ controls และ Rotor ด้วย `Control+Option+U` เพื่อตรวจ headings, landmarks, links, forms และ tables

ตรวจ flow เดียวกับ NVDA: title/language, headings, labels, table row/column context, dynamic announcements, dialog name, focus trap, Escape และ focus return

### 12.3 Pass/Fail

`PASS` เมื่อทำ task ได้โดยไม่ใช้เมาส์, รู้ตำแหน่ง/ชื่อ/สถานะ control, แก้ error ได้ และ modal ไม่ทำให้ focus หลง

`FAIL` เมื่อ control ใช้ได้เฉพาะเมาส์, screen reader อ่านชื่อไม่ได้, dynamic update ไม่ประกาศ, table แยก row context ไม่ได้ หรือ modal focus หลุด

`BLOCKED` เมื่อ test ต้องใช้ credential/สิทธิ์ที่ไม่มี, portal ล่ม หรือ flow ต้อง Draft/Submit. Blocked ไม่ใช่ Pass

---

## 13. Automated Accessibility Test

ปัจจุบัน repository มีตัวอย่าง workspace แยก แต่ยังไม่ได้ติดตั้ง dependency หรือรัน browser test จริง:

```text
a11y-tests/
├── package.json
├── playwright.config.js
└── tests/
    └── workflow26_modal_table.a11y.spec.js
```

### 13.1 Install local

```bash
cd a11y-tests
npm install @playwright/test@<reviewed-version> @axe-core/playwright@<reviewed-version>
npx playwright install chromium
```

ให้ pin exact versions และ commit lock fileหลัง review. อย่าใช้ `@latest` ใน CI

### 13.2 Run local/staging

```bash
A11Y_BASE_URL=http://127.0.0.1:7860 \
  npm test -- tests/workflow26_modal_table.a11y.spec.js
```

PowerShell:

```powershell
$env:A11Y_BASE_URL="http://127.0.0.1:7860"
npm test -- tests/workflow26_modal_table.a11y.spec.js
```

`/?a11y_fixture=table` เป็น test-only fixture contract ที่ต้องสร้างใน local/staging. หากไม่มี synthetic rows table tests จะ skip; ห้ามสร้าง fixture นี้บน production โดยไม่มี access control. ตัวอย่างใช้ `@axe-core/playwright` ผ่าน `AxeBuilder({ page }).analyze()`; ส่วน Jest/`jest-axe` เหมาะกับ HTML fragments และไม่แทน browser test ที่ตรวจ focus, layout หรือ screen-reader behavior

### 13.3 axe policy

- confirmed `violations` → fail CI
- `incomplete` → แนบ report และ manual review
- third-party exclude → selector แคบ พร้อม issue/owner/expiry
- ห้าม exclude ทั้ง page/container
- ห้าม disable `color-contrast` เป็นทางลัด
- axe green ไม่ได้ยืนยัน keyboard/screen reader/modal focus

### 13.4 ตัวอย่าง modal assertion

```js
test('manual modal traps focus and restores opener focus', async ({ page }) => {
  await page.goto('/');
  const opener = page.getByRole('button', { name: /คู่มือการใช้งาน/ });
  await opener.focus();
  await opener.press('Enter');

  const modal = page.locator('#manual-modal');
  await expect(modal).toHaveAttribute('role', 'dialog');
  await expect(modal).toHaveAttribute('aria-modal', 'true');
  await expect(modal).toHaveAttribute('aria-labelledby', 'manual-modal-title');

  const title = page.locator('#manual-modal-title');
  await expect(title).toBeFocused();

  const close = page.getByRole('button', { name: /ปิดคู่มือการใช้งาน/ });
  await close.focus();
  await close.press('Tab');
  await expect(title).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(modal).toBeHidden();
  await expect(opener).toBeFocused();
});
```

### 13.5 ตัวอย่าง dynamic table assertions

```js
test('every table control has an accessible name', async ({ page }) => {
  await page.goto('/?a11y_fixture=table');
  const controls = page.locator(
    '#table-body input:not([type="hidden"]), #table-body select, ' +
    '#table-body textarea, #table-body button'
  );

  const count = await controls.count();
  expect(count).toBeGreaterThan(0);

  for (let index = 0; index < count; index += 1) {
    await expect(controls.nth(index)).toHaveAccessibleName();
  }
});
```

ตัวอย่างนี้ตั้งใจตรวจ gap ที่ source ปัจจุบันอาจยังไม่ผ่าน ได้แก่ table caption/scope, dynamic labels และ row context

---

## 14. Modal Accessibility Patch Proposal

### 14.1 Root cause

Manual modal ปัจจุบันเพิ่ม/ลบ class อย่างเดียว ไม่มี `role=dialog`, `aria-modal`, `aria-labelledby`, initial focus, focus trap, Escape หรือ focus return

Confirmation modal ปัจจุบัน `showConfirmModal()` ไม่เก็บ trigger และไม่คืน focus. มีข้อความ dynamic ที่ใช้ `innerHTML`; ต้องเปลี่ยนเป็น plain text/trusted DOM ก่อนเพิ่ม security/accessibility patch

App-auth overlay มี role/aria-modal และ focus username เบื้องต้น แต่ยังไม่มี accessible name association, focus trap, Escape หรือ focus lifecycle ครบ

### 14.2 Shared controller ตัวอย่าง

```js
const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])'
].join(',');

function createModalController({ overlay, dialog, initialFocus, onClose }) {
  let opener = null;
  let open = false;

  const visible = (element) => {
    if (!element || element.hidden) return false;
    const style = getComputedStyle(element);
    return style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      element.getClientRects().length > 0;
  };

  const focusables = () =>
    Array.from(dialog.querySelectorAll(FOCUSABLE)).filter(visible);

  const restoreFocus = () => {
    if (opener?.isConnected && !opener.disabled) {
      opener.focus({ preventScroll: true });
    }
  };

  const close = () => {
    if (!open) return;
    open = false;
    overlay.classList.remove('active');
    overlay.hidden = true;
    overlay.removeEventListener('keydown', onKeydown);
    onClose?.();
    restoreFocus();
  };

  function onKeydown(event) {
    if (!open) return;

    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }

    if (event.key !== 'Tab') return;
    const items = focusables();
    if (!items.length) {
      event.preventDefault();
      dialog.focus({ preventScroll: true });
      return;
    }

    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  const openModal = () => {
    opener = document.activeElement;
    open = true;
    overlay.hidden = false;
    overlay.classList.add('active');
    overlay.addEventListener('keydown', onKeydown);
    (initialFocus?.() || focusables()[0] || dialog).focus({ preventScroll: true });
  };

  return { open: openModal, close };
}
```

ห้ามใช้ `tabindex` ค่าบวก. `aria-modal=true` ต้องใช้เมื่อ implementation ป้องกัน interaction ภายนอกจริงทั้ง keyboard และ pointer. หาก overlay ยังไม่ inert จริง อย่าใส่ `aria-modal=true` จนกว่าจะทำ behavior ให้ตรง

### 14.3 Manual modal markup

```html
<div id="manual-modal" class="modal-overlay" hidden
     role="dialog" aria-modal="true"
     aria-labelledby="manual-modal-title">
  <div class="manual-modal-card">
    <div class="manual-modal-header">
      <h2 id="manual-modal-title" tabindex="-1">
        คู่มือการใช้งานระบบ DOAE T&amp;V Automation
      </h2>
      <button type="button" id="btn-close-manual-x"
              aria-label="ปิดคู่มือการใช้งาน">×</button>
    </div>
    <div class="manual-modal-body">
      <!-- structured headings/lists; avoid one giant aria-describedby -->
    </div>
    <div class="manual-modal-footer">
      <button type="button" id="btn-close-manual-ok">
        เข้าใจแล้ว / ปิดหน้าต่าง
      </button>
    </div>
  </div>
</div>
```

### 14.4 Confirmation modal markup

```html
<div id="confirm-overlay" class="modal-overlay" hidden
     role="alertdialog" aria-modal="true"
     aria-labelledby="confirm-title"
     aria-describedby="confirm-message">
  <div class="confirm-modal">
    <h2 id="confirm-title"></h2>
    <p id="confirm-message"></p>
    <div class="modal-actions">
      <button type="button" id="confirm-no-btn">ยกเลิก</button>
      <button type="button" id="confirm-yes-btn">ยืนยัน</button>
    </div>
  </div>
</div>
```

สำหรับ destructive confirmation ให้ initial focus เป็นปุ่ม “ยกเลิก” หรือ least destructive action. Test accessibility ห้าม activate ปุ่ม confirm ที่อาจเรียก `executeAutomation()`

### 14.5 Auth overlay labels

`auth.js` ต้องสร้าง visible labels หรือ `aria-labelledby`/`aria-describedby` ให้ครบ:

```js
overlay.setAttribute('aria-labelledby', 'app-auth-title');
overlay.setAttribute('aria-describedby', 'app-auth-hint');
title.id = 'app-auth-title';
hint.id = 'app-auth-hint';

const usernameLabel = document.createElement('label');
usernameLabel.htmlFor = 'app-auth-username';
usernameLabel.textContent = 'ชื่อผู้ใช้แอป';

const passwordLabel = document.createElement('label');
passwordLabel.htmlFor = 'app-auth-password';
passwordLabel.textContent = 'รหัสผ่านแอป';
```

ต้องคง CSRF, auth boundary, password clearing และ `APP_AUTH_REQUIRED=1` เหมือนเดิม

### 14.6 CSS proposal

```css
.modal-overlay[hidden] {
  display: none !important;
}

.modal-overlay :focus-visible,
.app-auth-overlay :focus-visible {
  outline: 3px solid #f0abfc;
  outline-offset: 3px;
}

@media (prefers-reduced-motion: reduce) {
  .confirm-modal,
  .manual-modal-card {
    animation: none;
  }

  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

### 14.7 Security note

Source ปัจจุบันใช้ `innerHTML` ใน confirmation message เพื่อแสดง `<strong>`/`<br>`. ก่อนเปลี่ยนเป็น `textContent` ต้องปรับ call sites ให้ส่ง plain text หรือสร้าง trusted DOM nodes แบบจำกัด. ห้ามเอาข้อมูลจาก Excel/user input ไปใส่ `innerHTML`

---

## 15. CI Accessibility Gate

เมื่อมี local/staging fixture ที่ deterministic ให้เพิ่ม job แยก `accessibility-gate`:

```yaml
accessibility-gate:
  name: Automated accessibility tests
  runs-on: ubuntu-latest
  timeout-minutes: 15
  permissions:
    contents: read
  defaults:
    run:
      working-directory: a11y-tests
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: 22
        cache: npm
        cache-dependency-path: a11y-tests/package-lock.json
    - run: npm ci
    - run: npx playwright install --with-deps chromium
    - name: Start local Flask app in test-only mode
      working-directory: .
      env:
        APP_ENV: development
        APP_AUTH_REQUIRED: '0'
        RATELIMIT_STORAGE_URI: memory://
        PORT: '7860'
        HEADLESS: '1'
      run: |
        python app.py > /tmp/tv-automation-a11y.log 2>&1 &
        for attempt in $(seq 1 30); do
          curl --fail --silent http://127.0.0.1:7860/api/health && exit 0
          sleep 1
        done
        cat /tmp/tv-automation-a11y.log
        exit 1
    - name: Run accessibility tests
      run: npm test
      env:
        A11Y_BASE_URL: http://127.0.0.1:7860
    - name: Upload report on failure
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: workflow26-a11y-playwright-report
        path: a11y-tests/playwright-report/
        if-no-files-found: ignore
```

`APP_AUTH_REQUIRED=0` และ `memory://` ในตัวอย่างใช้เฉพาะ isolated CI process ที่ไม่มี public exposure; ห้ามใช้ contract นี้กับ Render production. ใน CI ต้อง mock/disable outbound portal calls และไม่ใช้ T&V credential

---

## 16. สถานะงาน

### เสร็จแล้ว

- Security hardening หลายรอบ
- PR #4 merged เข้า `main` ด้วย `e818d5f`
- Security Gate และ static checker ผ่านตามผลล่าสุด
- CSP migration ใน source root
- server-side auth/ACL, CSRF, upload ownership/TTL, rate limiting และ non-root Docker
- ตัด Gemini/AI API
- สร้าง Cursor context และเอกสาร deploy/workflow
- สร้าง WCAG review
- สร้างคู่มือ keyboard/NVDA/VoiceOver
- สร้าง automated accessibility testing guide
- สร้าง Playwright modal/table example
- สร้าง modal accessibility patch proposal
- `node --check` ของไฟล์ JS ที่ตรวจและ `git diff --check` ผ่านตามผลล่าสุด

### ยังไม่เสร็จ

- ยืนยัน Render Environment Variables และ login production ให้สำเร็จ
- ยืนยัน Redis Internal URL และ authorization profile ครบ
- สร้าง synthetic fixture `?a11y_fixture=table` ใน local/staging
- pin/install npm dependencies และสร้าง lock file
- apply modal/focus-trap patch ใน branch แยกหลัง review
- เพิ่ม table caption/scope, dynamic accessible names, focus-visible, upload fallback, live regions และ reduced motion
- รัน Playwright/axe จริง
- ทำ keyboard-only, NVDA และ VoiceOver pass
- ตั้ง required accessibility CI gate
- ทดสอบ production หลัง deploy โดยไม่ทำ mutation จริง

---

## 17. ลำดับการทำงานต่อที่แนะนำ

### Phase 1: Render configuration

ตั้งค่าบน Render ให้ครบโดยไม่เปิดเผยค่า:

```text
APP_ENV=production
APP_AUTH_REQUIRED=1
APP_AUTH_USERNAME=<user-provided app username>
APP_AUTH_PASSWORD_HASH=<user-generated Werkzeug hash>
APP_SESSION_SECRET=<random secret>
APP_AUTH_ROLE=<authorized role>
APP_AUTH_OFFICE_NAME=<authorized office>
APP_AUTH_ALLOWED_TAMBONS=<authorized tambons>
APP_AUTH_ALLOWED_APPROVERS=<authorized approvers>
APP_AUTH_CAN_SUBMIT=0
RATELIMIT_STORAGE_URI=<Internal Redis/Valkey URL>
```

กด Save/Deploy, ดู logs, ตรวจ `/api/health`, `/api/access/status` และ login ด้วย app account ที่ผู้ใช้ตั้งเอง. ห้ามลด guards

### Phase 2: Documentation commit

ตรวจ staged file list ก่อน commit:

```bash
git status --short
git add -- AGENTS.md CURSOR_CONTEXT.md
# เพิ่ม docs/a11y-tests ที่ต้องการจริงเท่านั้น
git diff --cached --check
git diff --cached --name-only
git diff --cached
git commit -m "docs: consolidate Cursor and accessibility guidance"
```

ยังไม่ push จนกว่าผู้ใช้จะตรวจ staged diff และยืนยัน

### Phase 3: Accessibility remediation

แยก branch สำหรับ modal/table/focus changes. Apply shared controller, semantic markup, CSS focus/reduced-motion และ app-auth labels. รัน regression/security tests และ browser test local/staging

### Phase 4: Human and automated validation

รัน axe/Playwright, keyboard-only, NVDA, VoiceOver, contrast, reflow/zoom และตรวจว่าไม่มี `/api/run`, portal navigation, Draft หรือ Submit. แก้ confirmed issues และทบทวน `incomplete` results ด้วยคน

### Phase 5: CI/production

เมื่อผล deterministic ให้ตั้ง required accessibility check ใน PR, merge, deploy และตรวจ health/logs. Production smoke test ต้อง read-only และใช้ `APP_AUTH_CAN_SUBMIT=0`

---

## 18. Quick troubleshooting

| อาการ | ตรวจอะไร |
|---|---|
| Deploy ล้มด้วย production profile error | ตรวจ `APP_AUTH_ROLE`, office, tambons, approvers และ `APP_AUTH_CAN_SUBMIT` |
| Rate limit warning | ตรวจว่า `RATELIMIT_STORAGE_URI` เป็น Internal Redis/Valkey ไม่ใช่เว็บ URL และไม่ใช่ `memory://` |
| Login app ไม่ได้ | ตรวจ username, Werkzeug hash, session secret, auth status และ logs; ห้ามส่ง password ผ่าน chat |
| Workflow selector error | ตรวจ portal DOM/readiness และ selector contract; ห้ามเดา selector และห้าม retry หลัง unknown finalize |
| Modal test fail | ตรวจ role/name, initial focus, Tab loop, Escape, focus return และ hidden state |
| Table accessibility fail | เพิ่ม caption/scope, label/aria-describedby และ row/column context |
| Upload keyboard test fail | เพิ่ม visible keyboard-operable label/button; อย่าพึ่ง `setInputFiles()` เพียงอย่างเดียว |
| axe incomplete | แนบผลเพื่อ manual review; ห้ามแปลง incomplete เป็น pass โดยอัตโนมัติ |
| CSP report route 404 | root source ยังไม่มี `/api/csp-report` route ที่ลงทะเบียน; เพิ่มโดยตั้งใจพร้อม validation/test |

---

## 19. References

[1]: https://www.w3.org/TR/WCAG22/ "Web Content Accessibility Guidelines (WCAG) 2.2 — W3C"
[2]: https://www.w3.org/WAI/test-evaluate/preliminary/ "W3C Easy Checks — preliminary accessibility evaluation"
[3]: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ "WAI-ARIA APG Dialog (Modal) Pattern"
[4]: https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/ "WAI-ARIA APG Developing a Keyboard Interface"
[5]: https://playwright.dev/docs/test-intro "Playwright Test documentation"
[6]: https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright "@axe-core/playwright documentation"
[7]: https://github.com/dequelabs/axe-core "axe-core documentation"
[8]: https://github.com/supernopInW/tv-automation "tv-automation GitHub repository"
[9]: https://tv-automation.onrender.com "tv-automation live service"
