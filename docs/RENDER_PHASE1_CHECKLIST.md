# Render Phase 1 Checklist — tv-automation

> ใช้เอกสารนี้ตั้งค่า Environment Variables บน Render ให้ครบก่อน redeploy  
> **ห้าม** ใส่ password, hash, session secret หรือ Redis URL จริงลงใน Git / chat / screenshot  
> **ห้าม** ลด security guards เพื่อให้ deploy ผ่าน

**Service:** `tv-automation`  
**Service ID:** `srv-d9o5jvlaeets73d4tfp0`  
**Live URL:** `https://tv-automation.onrender.com`  
**Target commit (Phase 1 auth profile):** `313a3f8` — **Deploy live** แล้วหลังเติม authorization profile
**ถัดไป:** deploy โค้ด multi-user + invite (ยังอยู่ local / ยังไม่ขึ้น `main` จนกว่าจะ commit+merge)

---

## 1. สิ่งที่ต้องมีบน Render (Environment)

| ตัวแปร | ค่าที่ต้องตั้ง | หมายเหตุ |
|---|---|---|
| `APP_ENV` | `production` | บังคับ |
| `APP_AUTH_REQUIRED` | `1` | fail-closed; ห้ามเป็น `0` |
| `APP_AUTH_USERNAME` | username ของแอป (ไม่ใช่ T&V) | bootstrap admin |
| `APP_AUTH_PASSWORD_HASH` | Werkzeug password hash | ห้ามใส่รหัสผ่าน plain text |
| `APP_SESSION_SECRET` | random secret ≥ 32 bytes | ห้ามใช้ placeholder |
| `APP_AUTH_ROLE` | เช่น `officer` | ตั้งแล้วบน live |
| `APP_AUTH_OFFICE_NAME` | เช่น `สำนักงานเกษตรอำเภอสีดา` | ตั้งแล้วบน live |
| `APP_AUTH_ALLOWED_TAMBONS` | รายชื่อตำบลคั่นด้วย comma | ตั้งแล้วบน live |
| `APP_AUTH_ALLOWED_APPROVERS` | รายชื่อผู้อนุมัติคั่นด้วย comma | ตั้งแล้วบน live |
| `APP_AUTH_CAN_SUBMIT` | `0` | คงไว้จนกว่าจะอนุมัติสิทธิ์ Submit |
| `RATELIMIT_STORAGE_URI` | Redis/Valkey **Internal** URL จากเมนู Connect | ห้าม `memory://` และห้ามเว็บ URL ของแอป |
| `APP_USER_REDIS_URI` | (ทางเลือก) Redis เดียวกันหรือ DB แยก | ถ้าไม่ตั้ง ใช้ `RATELIMIT_STORAGE_URI`; เก็บ users/invites (hashed) |

### สร้าง password hash (บนเครื่อง local)

```powershell
venv\Scripts\python.exe -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('ใส่รหัสผ่านแอปที่นี่'))"
```

คัดลอกเฉพาะ hash ไปใส่ Render — อย่า commit และอย่าส่งรหัสผ่านใน chat

### สร้าง session secret

```powershell
venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Redis / Valkey (rate limit + app users)

ใช้ Internal URL เดียวกันได้สำหรับ:
- `RATELIMIT_STORAGE_URI` — rate limiting
- `APP_USER_REDIS_URI` — (optional) ถ้าไม่ตั้ง จะใช้ค่าเดียวกับ `RATELIMIT_STORAGE_URI`

ผู้ใช้แอป/invite ถูกเก็บใน Redis; admin bootstrap จาก `APP_AUTH_USERNAME` + `APP_AUTH_PASSWORD_HASH`
---

## 2. ขั้นตอนบน Render Dashboard

1. เปิด service `tv-automation` → **Environment**
2. ตั้งค่าตัวแปรในตารางด้านบนให้ครบ (อย่าลด guards)
3. **Save Changes**
4. **Manual Deploy** ของ latest `main` (หลัง merge multi-user) หรือ commit ที่ต้องการ
5. เปิด **Logs** ตรวจว่าไม่มี:
   - `Production authorization profile is not configured`
   - `Production application authentication secrets are not configured`
   - `RATELIMIT_STORAGE_URI must be a shared Redis URI`
6. ตรวจ endpoints (read-only):
   - `GET https://tv-automation.onrender.com/api/health` → `status: ok`
   - `GET https://tv-automation.onrender.com/api/access/status` → auth contract ตอบได้
7. Login ด้วย **บัญชีแอป** ที่ตั้งเอง (ไม่ใช่บัญชี T&V)
8. (หลัง deploy invite) Admin กด **สร้างลิงก์เชิญ** → ส่ง URL ให้ผู้ใช้ใหม่ → ผู้ใช้เปิด `/?invite=...` ตั้งรหัสแอป
9. ห้ามกด Draft / Submit / `/api/run` ไปพอร์ทัลจริงจนกว่าจะพร้อมทดสอบ dry_run โดยตั้งใจ

---

## 3. ค่าตัวอย่างสำหรับอำเภอสีดา (ใส่ค่าจริงเองบน Render เท่านั้น)

ตัวอย่างโครงสร้าง — **อย่าคัดลอกเป็นค่า production โดยไม่ตรวจสิทธิ์จริง:**

```text
APP_AUTH_ROLE=officer
APP_AUTH_OFFICE_NAME=สำนักงานเกษตรอำเภอสีดา
APP_AUTH_ALLOWED_TAMBONS=หนองตาดใหญ่,...
APP_AUTH_ALLOWED_APPROVERS=นางอรอนงค์ สูญกลาง,...
APP_AUTH_CAN_SUBMIT=0
```

เติมตำบล/ผู้อนุมัติให้ครบตามที่อนุญาตจริง แล้วบันทึกเฉพาะบน Render

---

## 4. Pass / Fail

| ผล | เงื่อนไข |
|---|---|
| **PASS** | Deploy สำเร็จ, logs ไม่มี profile/secret/redis error, `/api/health` ok, login แอปได้, `APP_AUTH_CAN_SUBMIT=0` |
| **FAIL** | Deploy exited / worker boot error / health ของ instance เก่าเท่านั้น / login ไม่ได้ |
| **BLOCKED** | ยังไม่มี Redis instance หรือยังไม่มีค่า username/hash/secret จากเจ้าของระบบ |

---

## 5. หลัง Phase 1 ผ่านแล้ว

- บันทึกวันที่/เวลา deploy สำเร็จใน `docs/render_handoff_findings.md` (ไม่ใส่ secret)
- ค่อยพิจารณา smoke test `dry_run` บน production โดยไม่ Draft/Submit
- งาน a11y / modal patch ทำใน branch แยก ตาม `CURSOR_CONTEXT.md` Phase 3+
