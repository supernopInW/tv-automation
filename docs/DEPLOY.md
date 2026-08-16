# คู่มือการ Deploy ระบบ — DOAE T&V Automation

เอกสารนี้อธิบายวิธีนำระบบ **DOAE T&V Automation** ไปเปิดใช้งาน (Deploy) บนช่องทางต่างๆ ทั้งแบบ Container (Docker / Hugging Face Spaces), Cloud VPS หรือเครื่องสำนักงานเกษตรอำเภอ

---

## 1. วิธี Deploy ด้วย Docker Compose (แนะนำสำหรับ VPS / Server)

โปรเจกต์มีไฟล์ `docker-compose.yml` และ `Dockerfile` พร้อมใช้อัตโนมัติ

```bash
# 1. Clone หรือคัดลอกโฟลเดอร์โปรเจกต์มาที่เครื่อง VPS/Server
git clone <your-repo-url> tv_automation
cd tv_automation

# 2. สั่งรัน Docker Compose ในแบบ background (Headless Mode)
docker compose up -d --build
```

Compose จะ bind application ไว้ที่ **`127.0.0.1:7860`** เท่านั้น ไม่ควรเปิด port 7860 ออก Internet โดยตรง ให้ใช้ reverse proxy ที่บังคับ HTTPS และ authentication/network policy แทน

### Environment ที่ต้องตั้งก่อน production

ตั้งค่าผ่าน secret manager ของผู้ให้บริการหรือไฟล์ environment ที่อยู่นอก Git repository โดยห้ามใส่ password, password hash, session secret หรือ Redis credential ลงใน source code

```bash
APP_ENV=production
APP_AUTH_REQUIRED=1
APP_AUTH_USERNAME=<app-username>
APP_AUTH_PASSWORD_HASH=<werkzeug-password-hash>
APP_SESSION_SECRET=<random-secret-32-bytes-or-more>
APP_AUTH_ROLE=officer
APP_AUTH_OFFICE_NAME=<authorized-office>
APP_AUTH_ALLOWED_TAMBONS=<comma-separated-authorized-tambons>
APP_AUTH_ALLOWED_APPROVERS=<comma-separated-authorized-approvers>
APP_AUTH_CAN_SUBMIT=0
RATELIMIT_STORAGE_URI=redis://<redis-host>:<port>/<db>
```

เมื่อ `APP_AUTH_REQUIRED=1` ระบบจะ derive role, office, allowed tambons, approvers และสิทธิ์ submit จาก server-side profile แทนค่าที่ client ส่งมา หาก profile ไม่ครบหรือใช้ `memory://` ใน production ระบบต้อง fail closed และไม่ควรเริ่มให้บริการสาธารณะ

### Render.com (production ปัจจุบัน)

- Live URL: `https://tv-automation.onrender.com`
- Checklist ตั้งค่า env / redeploy: [`docs/RENDER_PHASE1_CHECKLIST.md`](RENDER_PHASE1_CHECKLIST.md)
- สถานะ deploy ล่าสุดจาก handoff: [`docs/render_handoff_findings.md`](render_handoff_findings.md)
- บริบทรวมสำหรับ Cursor: [`CURSOR_CONTEXT.md`](../CURSOR_CONTEXT.md)

อย่าลด production guards เพื่อให้ deploy ผ่าน — แก้ Environment Variables ให้ครบแล้ว Save/Deploy

---

## 2. วิธี Deploy บน Hugging Face Spaces (ฟรี Cloud Hosting)

โปรเจกต์รองรับการรันบน **Hugging Face Spaces** ด้วย Docker:

1. สมัคร/เข้าสู่ระบบ [Hugging Face](https://huggingface.co)
2. กด **Create New Space**
3. ตั้งชื่อ Space และเลือก **Space SDK = Docker** (Blank Container)
4. อัปโหลดไฟล์ทั้งหมดในโปรเจกต์นี้ไปยัง Repository ของ Space (รวมโฟลเดอร์ `data/`, `static/`, `templates/`, `Dockerfile` และ `README.md`)
5. Hugging Face จะอ่าน YAML frontmatter ใน `README.md` และสร้าง Container อัตโนมัติบนพอร์ต `7860`
6. เมื่อ Build เสร็จ จะได้ลิงก์ HTTPS ใช้งานออนไลน์ฟรีได้ 24 ชม.

---

## 3. วิธีรันบนเครื่อง Local พร้อมเปิด Public Link (Tunneling)

หากต้องการรันบนเครื่องคอมพิวเตอร์ในสำนักงานเกษตรอำเภอ (Windows) แล้วสร้างลิงก์ให้เครื่องอื่นหรือมือถือเข้าใช้ได้:

### ใช้ไฟล์ Batch Helpers:
- **`T&V_Automation_App.bat`**: สตาร์ทรันระบบ Local ธรรมดาที่ `http://127.0.0.1:5000`
- **`Start_App_With_Tunnel.bat`**: สตาร์ทรันระบบ Flask พร้อมสร้าง Ngrok Tunnel / Cloudflare Tunnel ออนไลน์อัตโนมัติ

---

## 4. แหล่งข้อมูลภูมิศาสตร์ (bundled)

ระบบไม่เรียก API กรมตอนรัน แต่ใช้ไฟล์ใน `data/` ที่ build ล่วงหน้า

| ชั้นข้อมูล | ไฟล์ | แหล่ง |
|-----------|------|--------|
| จังหวัด / อำเภอ / ตำบล | `data/provinces.json`, `amphoes.json`, `tambons.json` | [open-admin-data/thailand-administrative-divisions](https://github.com/open-admin-data/thailand-administrative-divisions) (CC-BY-4.0) |
| หมู่บ้าน | `data/villages/{tambon_code}.json` | โฟลเดอร์ `data/villages-by-province` ใน repo เดียวกัน |

### สร้าง/อัปเดตข้อมูลภูมิศาสตร์ใหม่
```bash
python -u scripts/build_geo_data.py
```

---

## 5. Checklist ก่อนเปิดใช้งานจริง (Production Checklist)

- [x] Docker runtime ใช้ non-root user และไม่มี `chmod -R 777`
- [x] Compose bind port เฉพาะ `127.0.0.1:7860` และใช้ reverse proxy สำหรับ HTTPS
- [x] `APP_AUTH_REQUIRED=1` และ authentication profile ครบถ้วน
- [x] ตั้ง `RATELIMIT_STORAGE_URI` เป็น shared Redis URI ที่ไม่ใช่ `memory://`
- [x] ตรวจ server-side authorization ของ role/office/tambon/approver และ `can_submit`
- [x] ใช้ `requirements.txt` และ `requirements.lock` แบบ exact pins
- [x] มีโฟลเดอร์ `data/` และฐานข้อมูลภูมิศาสตร์ไทยครบถ้วน
- [x] ตรวจสอบระบบสุ่มสร้างแผนบนเว็บ / อัปโหลด Excel
- [x] ตรวจสอบกฎวันจันทร์ (DM/WM) และการใช้จำนวนสมาชิกสำนักงาน
- [x] ตรวจสอบการสุ่มเป้าหมายภาคสนาม `[20, 30, 50, 60]` คน
- [x] ยืนยันความปลอดภัย: ไม่มีรหัสผ่าน T&V ของผู้ใช้ถูกเก็บบันทึกบนเซิร์ฟเวอร์
