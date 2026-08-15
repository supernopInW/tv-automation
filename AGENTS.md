# 🤖 Project Knowledge & AI Model Development Guidelines (AGENTS.md)
> **DOAE T&V Automation System (ระบบกรอกแผนเยี่ยมเยียนอัตโนมัติ T&V)**  
> **Last Updated:** 2026-08-16
> **Version:** 1.0.0

---

## 🚨 MANDATORY DIRECTIVE FOR ALL AI MODELS / AGENTS (กฎเหล็กบังคับอัปเดตไฟล์นี้)

> [!IMPORTANT]
> **คำสั่งบังคับสำหรับ AI/LLM ทุกตัวที่เข้ามาทำงานในโปรเจกต์นี้:**
> 1. **อ่านไฟล์นี้ก่อนเริ่มงานเสมอ:** AI ทุกตัวต้องอ่านและทำความเข้าใจบริบท สถาปัตยกรรม กฎธุรกิจ (Business Logic) และโครงสร้างไฟล์จากเอกสารนี้ก่อนดำเนินการ
> 2. **ต้องอัปเดตไฟล์นี้ทุกครั้งหลังทำภารกิจเสร็จ (ALWAYS UPDATE THIS FILE):** ไม่ว่าคุณจะแก้ไขโค้ด เพิ่มฟีเจอร์ แก้ไขบั๊ก ปรับโครงสร้างไฟล์ หรือค้นพบข้อจำกัด/ข้อควรระวังใหม่ๆ **คุณต้องอัปเดตไฟล์ `AGENTS.md` นี้เสมอ** เพื่อส่งต่อบริบทและพัฒนาความสมบูรณ์ของเอกสารให้ดีขึ้นเรื่อยๆ สำหรับ AI ตัวถัดไป
> 3. **ห้ามลบประวัติหรือบริบทสำคัญ:** เมื่ออัปเดต ให้เพิ่มเติมรายละเอียด ปรับปรุงสถานะโปรเจกต์ หรืออัปเดตวันที่ล่าสุด โดยคงโครงสร้างที่เป็นระบบไว้

---

## 📌 1. ภาพรวมโปรเจกต์ (Project Overview)

ระบบ **DOAE T&V Automation** เป็น Web Application (Flask + Playwright + JavaScript) ออกแบบและพัฒนาโดย **นายนพฤทธิ์ น้อยเล็น (นักวิชาการส่งเสริมการเกษตรปฏิบัติการ)** ถูกพัฒนาขึ้นเพื่อช่วยเจ้าหน้าที่สำนักงานเกษตรอำเภอ (เริ่มต้นจาก **สำนักงานเกษตรอำเภอสีดา จ.นครราชสีมา** และรองรับทุกอำเภอทั่วประเทศ) นำข้อมูล **"แผนการเยี่ยมเยียนรายเดือน" จากไฟล์ Excel** เข้าสู่ระบบพอร์ทัล **DOAE T&V (https://tandv.doae.go.th)** (Workflow 26) โดยอัตโนมัติ

### ปัญหาที่ระบบนี้แก้ (Problem Solved)
- เดิมทีเจ้าหน้าที่ต้องนั่งคีย์ข้อมูลแผนเยี่ยมเยียนรายวันลงพอร์ทัลทีละรายการ ซึ่งใช้เวลานานและเสี่ยงต่อการผิดพลาด
- ระบบนี้เปิดให้เจ้าหน้าที่:
  1. เลือกบทบาทและตำบลที่รับผิดชอบ
  2. อัปโหลดไฟล์ Excel แผนเยี่ยมเยียน (เช่น ชีต `สค69`)
  3. ระบบจะกระจายวัน/สุ่มหมู่บ้านภาคสนามตามกฎธุรกิจ (เช่น กฎวันจันทร์ประจำสำนักงาน)
  4. แสดงตารางให้ตรวจสอบ/แก้ไข
  5. สั่งบอท Playwright ล็อกอินด้วยบัญชี T&V ของตนเองเพื่อกรอกข้อมูลลงระบบ T&V แบบอัตโนมัติ (เลือกโหมด Dry-run / บันทึกชั่วคราว / บันทึก & ส่ง)

---

## 🛠️ 2. สถาปัตยกรรมระบบ & Tech Stack (Architecture & Tech Stack)

- **Backend:** Python 3.10+, Flask, Pandas, openpyxl, xlrd
- **Automation Engine:** Playwright (Chromium Async/Sync API) สำหรับควบคุม Headless/Headed Browser ไปยังระบบ T&V
- **Data Processing:** Local rules-based parser สำหรับอ่านและจำแนกข้อมูล Excel โดยไม่มีการเชื่อมต่อ external AI API
- **Frontend:** Vanilla HTML5, CSS3 (Modern Responsive Dashboard, CSS Variables, Glassmorphism design), Vanilla JavaScript (`static/app.js`)
- **Data Persistence & Cache:** 
  - ข้อมูลภูมิศาสตร์ (จังหวัด/อำเภอ/ตำบล/หมู่บ้าน) เก็บเป็น JSON ใน `data/` และ `config/districts.json`
  - T&V username/password ของผู้ใช้ **ไม่เก็บในฐานข้อมูล ไฟล์ หรือ Web Storage**; อยู่ในหน่วยความจำของแท็บ/การรันและล้างหลังจบงาน
- **Tunneling & Deployment:** รองรับ Cloudflare Tunnel (`cloudflared.exe`) และ Ngrok (`ngrok.exe`) เพื่อรันเปิดให้เครื่องอื่นใช้งานผ่านลิงก์ได้

---

## 📁 3. แผนผังโครงสร้างไฟล์สำคัญ (Key Directory & File Structure)

```text
tv_automation/
├── AGENTS.md                  # 👈 [ไฟล์นี้] คู่มือและบริบทสำหรับ AI Agents (ต้องอัปเดตเสมอ)
├── README.md                  # คู่มือโปรเจกต์ระดับผู้ใช้/ผู้พัฒนาทั่วไป
├── app.py                     # 🧠 โค้ดหลัก Flask API, Playwright Automation Engine (Workflow 26), Map Activity logic
├── automate_submission.py     # สคริปต์ย่อยจัดการการกรอกข้อมูลอัตโนมัติด้วย Playwright
├── geo_data.py                # ตัวจัดการข้อมูลภูมิศาสตร์ (จังหวัด, อำเภอ, ตำบล, หมู่บ้าน)
├── requirements.txt           # Python Dependencies ของ Flask, Playwright, Pandas และ parser แบบ local
├── Dockerfile & .dockerignore # การ containerize สำหรับการ deploy (HF Spaces / VPS)
├── docker-compose.yml         # 🚀 การสั่งรันด้วย Docker Compose แบบ 1-Command
├── Upload_To_GitHub.bat       # 🐙 สคริปต์ทางลัดสำหรับ Push โค้ดลง GitHub (supernopInW/tv-automation)
│
├── config/
│   └── districts.json         # พรีเซ็ตข้อมูลอำเภอ (เช่น อำเภอสีดา จ.นครราชสีมา)
│
├── data/
│   ├── geo_thailand.json      # ข้อมูลภูมิศาสตร์ประเทศไทย
│   └── villages/              # ไฟล์ JSON รายชื่อหมู่บ้านแยกตามตำบล
│
├── scripts/
│   ├── build_geo_data.py      # สคริปต์แปลง/สร้างฐานข้อมูลภูมิศาสตร์
│   ├── merge_villages.py      # สคริปต์รวมรายชื่อหมู่บ้าน
│   ├── create_sample_excel.py # สคริปต์สร้างไฟล์ Excel แผนงานตัวอย่างสำหรับทดสอบ
│   ├── inspect_form.py        # สคริปต์ส่อง DOM Element ของหน้าเว็บ T&V
│   └── inspect_buttons.py     # สคริปต์ส่องปุ่มและฟอร์มบนเว็บ T&V
│
├── static/
│   ├── app.js                 # 💻 Logic ฝั่ง Client: Event Handling, สุ่มหมู่บ้าน, กฎวันจันทร์, SSE Live Log
│   └── style.css              # 🎨 UI Design System & Theme Styles
│
├── templates/
│   └── index.html             # 🖼️ หน้าจอ Dashboard หลักสำหรับผู้ใช้งาน
│
└── docs/
    ├── CHANGELOG.md           # บันทึกการแก้ไขและการ deploy
    ├── USER_GUIDE.md          # คู่มือใช้งานอย่างละเอียดสำหรับเจ้าหน้าที่
    ├── WORKFLOW.md            # รายละเอียดกระบวนการแปลง Excel -> T&V Portal
    └── DEPLOY.md              # คู่มือการติดตั้งและ Deploy ระบบ
```

---

## ⚙️ 4. กฎธุรกิจและตรรกะสำคัญ (Core Business Logic)

หาก AI ตัวใดต้องแก้ไขโค้ดใน `app.py` หรือ `static/app.js` **ต้องรักษาและปฏิบัติตามกฎต่อไปนี้อย่างเคร่งครัด:**

1. **กฎวันจันทร์ (Monday Rule - ประชุมสำนักงาน):**
   - ทุกวันจันทร์ของเดือน กำหนดให้เป็นวันประชุมสำนักงานเกษตรอำเภอ
   - **จันทร์แรกของเดือน (1st Monday):** กำหนดเป็น **DM (District Meeting / รหัส 13)**
   - **จันทร์อื่นๆ ของเดือน:** กำหนดเป็น **WM (Weekly Meeting / รหัส 14)**
   - สถานที่: `สำนักงานเกษตรอำเภอ...`
   - **จำนวนบุคคลเป้าหมาย (Target Count):** อ้างอิงจากช่อง "จำนวนสมาชิกสำนักงาน (คน)" ในหน้าตั้งค่า (ปรับได้ตามสำนักงานแต่ละแห่ง เช่น 5, 7, 10, 12 คน)

2. **งานภาคสนามและการสุ่มหมู่บ้าน (Fieldwork & Village Sampling):**
   - วันที่ไม่ใช่วันจันทร์ (อังคาร-ศุกร์) ที่มีงานลงพื้นที่ ให้สุ่มหมู่บ้าน 2-4 หมู่บ้านจากตำบลที่เจ้าหน้าที่รับผิดชอบ
   - รูปแบบข้อความสถานที่ที่เกิด: `หมู่ X, Y ตำบล [ชื่อตำบล]` หรือกรณีหลายตำบล `หมู่ 1, 3 ตำบล A, หมู่ 2, 4 ตำบล B`
   - **จำนวนบุคคลเป้าหมายงานภาคสนาม (Fieldwork Target Count):** ระบบสุ่มตัวเลขจำนวนคนจากกลุ่ม **`[20, 30, 50, 60]`** ราย/คน สำหรับแต่ละกิจกรรมภาคสนาม

3. **การขยายช่วงวันใน Excel (Date Range Expansion):**
   - หากใน Excel ระบุวันเป็นช่วง เช่น `๕-๗ ส.ค. ๖๙` ระบบต้องขยายเป็น 3 แถวแยกตามวันจริง (05/08/2569, 06/08/2569, 07/08/2569)

4. **โหมดการรัน Playwright Automation:**
   - **Dry-run Mode:** เปิดเบราว์เซอร์ไปทดลองกรอก ตรวจสอบฟอร์ม แต่ **ไม่กดปุ่มบันทึก/ส่งจริง** (ใช้สำหรับทดสอบ)
   - **Save Draft Mode:** กรอกและกด **บันทึกชั่วคราว** ในระบบ T&V
   - **Submit Mode:** กรอกและกด **บันทึก & ส่งอนุมัติ**

5. **ความปลอดภัยรหัสผ่าน (Security Protocol):**
   - **ห้าม** บันทึก Username/Password ของ T&V ลงไฟล์, DB หรือ Log เด็ดขาด
   - Password ส่งผ่าน HTTPS request Payload และถือครองในเซสชันเบราว์เซอร์เท่านั้น

---

## 🚀 5. คำสั่งการติดตั้งและการใช้งาน (Development Setup & Execution)

### การตั้งค่า Environment
```bash
# 1. สร้างและเปิดใช้งาน Virtual Environment
python -m venv venv
# Windows PowerShell / CMD:
venv\Scripts\activate

# 2. ติดตั้ง Dependencies
pip install -r requirements.txt

# 3. ติดตั้ง Chromium สำหรับ Playwright
playwright install chromium

# 4. รันระบบ Flask App
python app.py
```
แอปพลิเคชันจะทำงานที่ URL: `http://127.0.0.1:5000`

### ไฟล์ Batch Helpers (สำหรับ Windows)
- `Start_App_With_Tunnel.bat`: สตาร์ท Flask พร้อมเปิด Cloudflare Tunnel / Ngrok
- `Install_Dependencies.bat`: สคริปต์ติดตั้ง pip และ playwright อัตโนมัติ
- `T&V_Automation_App.bat`: สคริปต์ทางลัดสำหรับเปิดใช้งานแอปพลิเคชัน

---

## 📝 6. แนวทางปฏิบัติตนและข้อตกลงสำหรับ AI Models (AI Workflow Protocol)

เมื่อ AI (รวมถึงตัวคุณ) เข้ามาพัฒนาต่อ ให้ปฏิบัติตามขั้นตอนต่อไปนี้:

1. **ตรวจสอบความถูกต้องก่อนแก้โค้ด (Inspect Before Edit):**
   - ใช้ `view_file` หรือ `grep_search` ตรวจสอบฟังก์ชันเดิม ห้ามเดาสัญญาณ (Function Signature) หรือ Element ID บนเว็บ T&V
2. **รักษา Code Style & Refactoring Rules:**
   - ภาษา Python: ใช้ PEP8, จัดการ Exception ชัดเจน, อย่ากลืน Error (`try...except: pass` ห้ามใช้เด็ดขาด)
   - ภาษา JavaScript: Vanilla ES6+, ใช้ Async/Await, มี JSDoc อธิบายฟังก์ชันสำคัญ
3. **การทดสอบหลังแก้ไข (Verification):**
   - ทุกครั้งที่แก้ `app.py` หรือ `static/app.js` ต้องรัน `python app.py` หรือสคริปต์ทดสอบ เพื่อยืนยันว่าไม่มี Syntax Error / Import Error
4. **กระบวนการอัปเดตไฟล์ `AGENTS.md` (Self-Updating Protocol):**
   - เมื่อเพิ่ม API Route ใหม่ -> มาเพิ่มรายการในส่วน **3. แผนผังโครงสร้าง** หรือสร้างหัวข้อ API
   - เมื่อแก้/เพิ่มกฎธุรกิจ -> มาอัปเดตหัวข้อ **4. กฎธุรกิจและตรรกะสำคัญ**
   - เมื่อค้นพบวิธีแก้ปัญหาหรือบั๊ก -> มาอัปเดตในหัวข้อ **7. ปัญหารู้จักและแนวทางแก้ไข**
   - **เปลี่ยนวันที่ Last Updated ที่หัวเอกสารเสมอ!**

---

## 🐛 7. ปัญหารู้จักและข้อควรระวัง (Known Issues & Troubleshooting)

- **DOM Elements ของพอร์ทัล T&V เปลี่ยนแปลง:**
  - หาก Playwright หาปุ่มหรือ Dropdown ไม่เจอ ให้ใช้ `scripts/inspect_form.py` หรือ `scripts/inspect_buttons.py` เพื่อส่อง Selector ล่าสุดจากระบบ T&V
- **การใช้ Playwright Thread / Async Lock:**
  - `app.py` ใช้ `threading.Lock()` ชื่อ `_run_lock` เพื่อป้องกันการเปิด Playwright Browser หลาย Instance พร้อมกันจน Memory เต็ม (ออกแบบให้เหมาะกับการ Deploy บน Cloud/HuggingFace Spaces)
- **ปุ่มสร้างแผนอัตโนมัติถูกล็อก (Disabled Button Behavior):**
  - ระบบเดิมล็อกปุ่มไว้จนกว่าจะกดปุ่ม "ยืนยันพื้นที่รับผิดชอบ"
  - ปรับปรุงล่าสุด: หากเลือกอำเภอและตำบลเรียบร้อยแล้ว ปุ่มสุ่มสร้างแผนจะเปิดให้กดทันที และจะทำ Auto-confirm พื้นที่ให้อัตโนมัติเมื่อกดใช้งาน
- **ปุ่มบันทึกใน Modal `#bizModal_402` ค้าง (Timeout Exceeded / Element is not enabled):**
  - เกิดขึ้นเมื่อกิจกรรมเป็นรหัส "999" (กิจกรรมอื่นๆ) แต่ช่อง `input#PD_OTHER` ไม่ได้ถูกกรอก หรือ T&V Form Validation script ค้าง attribute `disabled` บนปุ่มบันทึก
  - **การแก้ไข:** ใน `_fill_record_row` (ของทั้ง `app.py` และ `automate_submission.py`) ได้เพิ่มการเติม fallback text ให้ `input#PD_OTHER` อัตโนมัติเมื่อเลือก 999, เพิ่มการ dispatch `input/change/blur/keyup` events ให้ครบทุก field, ปลดล็อก `disabled` บนปุ่มบันทึกด้วย JavaScript และเพิ่ม fallback JS click/submit กรณี Playwright standard click ติดขัด actionability check

---

## 📋 8. สถานะปัจจุบันและงานที่ต้องทำต่อ (Status & Roadmap)

- [x] ระบบวิเคราะห์และอ่าน Excel แผนงานรายเดือน (ชีต สค69 / พค69)
- [x] ระบบคำนวณและสุ่มหมู่บ้านตามตำบลที่รับผิดชอบ
- [x] กฎวันจันทร์ประจำสำนักงาน (DM/WM)
- [x] Playwright Automation สำหรับ Workflow 26 (รองรับ Dry-run / Draft / Submit)
- [x] UI Dashboard ภาษาไทย สำหรับเจ้าหน้าที่
- [ ] *(งานในอนาคต)* รองรับ Workflow อื่นๆ ของระบบ T&V เพิ่มเติม
- [ ] *(งานในอนาคต)* เพิ่มระบบ Export Log รายงานการกรอกย้อนหลังเป็น PDF/Excel

---

## 🔎 9. บันทึกการสำรวจและการแก้ไข (2026-08-07)

- Source ที่ deploy คือไฟล์ในโฟลเดอร์รากและชุด Ready_For_GitHub/ ตรงกับไฟล์สำคัญที่ตรวจสอบแล้ว
- app.py มี Flask routes 18 รายการ; ข้อมูลภูมิศาสตร์ bundled มี 77 จังหวัด, 928 อำเภอ, 7,364 ตำบล และ 79,818 หมู่บ้าน
- Smoke check ล่าสุดผ่านการ import app, py_compile, /api/health, /api/districts และ parser ตัวอย่าง Excel
- แก้ไขการสร้างแผนบนเว็บให้เดือนที่เลือกใน #auto-plan-month เป็นแหล่งเดือนหลักตอนส่ง Workflow 26; หากเป็นแถวที่เพิ่มเอง ระบบจะอนุมานเดือนจากวันที่แถวแรก และยังคงใช้เดือนจาก Excel เมื่อโหลดแผนจากไฟล์
- ข้อจำกัดเครื่องพัฒนา: คำสั่ง python ไม่อยู่ใน PATH และ venv\Scripts\python.exe ชี้ไปยัง Python ที่ไม่มีอยู่แล้ว จึงใช้ bundled Python runtime ร่วมกับ venv\Lib\site-packages ในการตรวจสอบ

*โปรดจำไว้: ทุกครั้งที่คุณทำการแก้ไขโปรเจกต์นี้ อย่าลืมกลับมารายงานการเปลี่ยนแปลงและปรับปรุงไฟล์ `AGENTS.md` นี้ให้สมบูรณ์ขึ้น!*

---

## 11. บันทึกสภาพแวดล้อมการพัฒนา (2026-08-07)

- ตรวจพบไดรฟ์ระบบ C: พื้นที่เต็มจากการสะสมของไฟล์ชั่วคราว/แคชหลายส่วน รวมถึง Windows Installer ประมาณ 2 GB, Playwright browsers ประมาณ 1.46 GB และแคชเบราว์เซอร์/แอปอื่น ๆ
- ล้างเฉพาะ Temp diagnostics/ตัวติดตั้ง VS Code เก่า, cursor sandbox cache, npm cache, pip cache และ crash dumps แล้ว ได้พื้นที่กลับคืนประมาณ 1.38 GB
- ห้ามลบ `hiberfil.sys`, Windows Installer หรือโฟลเดอร์ Playwright โดยอัตโนมัติ เพราะอาจกระทบระบบหรือการทดสอบอัตโนมัติ ควรตรวจสอบและยืนยันก่อนทุกครั้ง
- ล้าง Playwright browser runtimes รุ่นเก่า (Firefox, WebKit, Chromium รุ่นเก่า และ Chromium headless shell) แล้วเมื่อ 2026-08-07 โดยเก็บ Chromium รุ่นปัจจุบันไว้สำหรับระบบอัตโนมัติ
- เพิ่ม API `/api/historical-activities` เพื่ออ่านกิจกรรมประเด็นเยี่ยมเยียนจาก Excel เก่าระดับ root และส่งค่า `weight` ตามจำนวนครั้งที่พบให้ frontend สุ่มแบบถ่วงน้ำหนัก โดยไม่ใช้ไฟล์อัปโหลดปัจจุบันเป็นแหล่งหลัก
- ปรับ `.dockerignore` ให้ Docker/Render รวมเฉพาะ Excel เก่าที่ใช้สร้างคลังกิจกรรม เพื่อไม่ให้ API ตอบคลังว่างหลัง deploy
- หน้าสร้างแผนอัตโนมัติแสดงว่ากิจกรรมภาคสนามสุ่มจากประวัติ Excel เสมอ และตัดโค้ดเดิมที่อ่าน allRecords ของไฟล์อัปโหลดปัจจุบันออก เพื่อป้องกันการนำข้อมูลรอบปัจจุบันมาเป็นแหล่งสุ่มโดยไม่ตั้งใจ
## 10. Modal Validation Fix (2026-08-07)

- Updated `app.py` and `automate_submission.py` so Workflow 26 waits for dynamic activity options, verifies the selected activity, re-applies both start/end dates until they persist, and reports invalid portal fields when `#bizModal_402` remains visible after save.
- Business rule: each plan record is a single-day activity, so `PD_EDATE` must always equal `PD_SDATE`; both automation paths enforce and verify this.
- Clarified auto-plan requirement: the current uploaded Excel must not be the primary activity source. Random fieldwork activities should be sampled from historical Excel activity records (using the historical pool as a reference), with the built-in pool only as fallback when no historical records are available.

## 12. บันทึกการ Hardening Playwright Workflow 26 (2026-08-15)
- ปรับ pp.py และ utomate_submission.py ให้ตรวจ login/session, Workflow 26 selectors, dynamic dropdown และค่าที่เลือกคงอยู่จริงก่อนกรอกข้อมูล
- เพิ่มการตรวจ modal fields, PD_OTHER สำหรับกิจกรรม 999, validation state และป้องกันการใช้ native form.submit ที่ทำให้ผลลัพธ์ไม่ชัดเจน
- ปรับ Draft/Submit ให้ตรวจผลลัพธ์จาก URL/ข้อความของพอร์ทัล และรายงาน FINALIZE_UNKNOWN_RESULT เมื่อยังยืนยันไม่ได้ ห้าม retry โดยไม่ตรวจพอร์ทัลก่อน
- เพิ่ม diagnostics และ absolute screenshot path เมื่อแถวผิด รวมถึงปรับ worker ให้เป็นผู้ถือครองและปล่อย _run_lock หลัง Playwright จบจริง
- เพิ่ม 	est_workflow26_hardening.py สำหรับทดสอบ offline; ผ่าน 4 กรณี และผ่าน py_compile/
ode --check โดยยังไม่ส่งข้อมูลไปพอร์ทัลจริง


## 13. บันทึกการแก้ Select2 Readiness และ Browser Lifecycle (2026-08-15)

- พบว่า `select#PL_YAER` และ `select#PL_MOUNT` ถูกห่อด้วย Select2 และ raw select ถูกซ่อนตามปกติ ส่วน `select#PL_TAMBONN` มีขนาด 0x0 แม้ตัวควบคุมบนหน้าจอพร้อมใช้งาน การรอด้วย `state="visible"` จึงทำให้ Dry Run หยุดด้วย `WORKFLOW_SELECTOR_ERROR` ก่อนเปิด modal.
- ปรับ `app.py` และ `automate_submission.py` ให้รอ raw select ที่ attach และมี options มากกว่า 1 แทนการบังคับ visibility รวมถึงเพิ่ม diagnostics ของ option count, value, display, visibility และ aria-hidden.
- ปรับการปิด browser ให้เกิดขณะ `sync_playwright()` context ยังทำงานอยู่ และไม่เรียก `browser.close()` ซ้ำหลัง context หยุดแล้ว เพื่อตัดข้อความ `Event loop is closed! Is Playwright already stopped?`.
- ปรับ SSE lifecycle ไม่เขียนทับ `_run_active` จาก generator ที่ disconnect; worker ยังคงเป็นเจ้าของการปล่อย lock.
- เพิ่ม `test_selector2_readiness.py`; targeted tests 3 กรณี, hardening tests 4 กรณี, `py_compile` และ `git diff --check` ผ่านทั้งหมดแบบ offline โดยไม่เปิด browser และไม่ส่งข้อมูลไป T&V.


## 14. แก้ Dynamic Month Readiness รอบสอง (2026-08-15)

- จาก retry จริงพบว่า `#PL_MOUNT` เริ่มต้นด้วย option เดียวคือ `เลือกเดือน` ก่อนปีงบประมาณถูกเลือก ดังนั้นการกำหนดให้ทุก control ต้องมี options มากกว่า 1 ทำให้ readiness เข้มเกินไปและหยุดก่อนเลือกปี.
- ปรับ readiness initial ให้ยอมรับ `#PL_MOUNT` ที่มีอย่างน้อย 1 option แต่ยังตรวจ `#PL_YAER` และ `#PL_TAMBONN` ตามจำนวนขั้นต่ำที่ใช้งานได้จริง.
- เพิ่ม `_wait_for_select_options()` ใน `app.py` และ `automate_submission.py` เพื่อรอ `#PL_MOUNT` เติม options อย่างน้อย 2 รายการหลังเลือกปี ก่อนเลือกเดือนตามชื่อ.
- เพิ่ม assertions สำหรับ initial placeholder และ dynamic month wait ใน `test_selector2_readiness.py`; targeted tests 5 กรณี, hardening tests 4 กรณี, `py_compile` และ `git diff --check` ผ่านแบบ offline.


## 15. แก้ Dynamic Month Wait รอบสาม (2026-08-15)

- Retry บน Render ยืนยันว่า หลังเลือกปี 2569 ตัวเลือกใน `#PL_MOUNT` ถูกโหลดครบแล้ว แต่ `_wait_for_select_options()` ยังรายงาน `WORKFLOW_DYNAMIC_OPTION_ERROR` เนื่องจากการส่ง object argument ให้ `page.wait_for_function()` และการ destructuring argument ใน JavaScript predicate ไม่ทำงานตามที่คาดกับ Playwright sync runtime จริง.
- ปรับ helper ใน `app.py` และ `automate_submission.py` ให้ serialize selector ด้วย `json.dumps()` แล้วฝัง selector และจำนวนขั้นต่ำลงใน predicate โดยตรง พร้อมตัดการส่ง argument object ออกทั้งหมด. วิธีนี้ยังคงป้องกัน selector injection จากค่าที่ไม่คาดคิดและทำให้ predicate ใช้ได้กับ runtime จริง.
- ปรับ `test_selector2_readiness.py` ให้ตรวจ predicate แบบใหม่ว่า selector/minimum ถูกฝังถูกต้องและไม่มี positional arguments.
- ผลตรวจสอบรอบ patch: targeted Select2 tests 4 กรณี, hardening tests 5 กรณี, `py_compile` และ `git diff --check` ผ่านทั้งหมดแบบ offline. ยังไม่ได้ Draft/Submit และยังไม่มีการส่งข้อมูลจริงไปพอร์ทัล.

## 16. แก้ Modal Date Event Ordering (2026-08-15)

- Dry-run บน Render ผ่าน login, Workflow 26 readiness และ dynamic month wait แล้ว แต่ modal validation พบ `MODAL_FIELD_MISMATCH` ครบ 20 แถว เพราะ `#PD_EDATE` กลายเป็นค่าว่าง.
- ตรวจ DOM จริงในพอร์ทัลพบว่า `#PD_SDATE` และ `#PD_EDATE` เป็น input `type="text"` ที่เริ่มต้น disabled และมี datepicker/inputmask. Event handler `change` ของ `#PD_SDATE` จะเปิดใช้งานและล้างค่า `#PD_EDATE` เพื่อรอช่วงวันที่.
- สาเหตุคือโค้ดตั้งวันที่ทั้งคู่ก่อน generic event dispatch แต่ generic dispatch ส่ง `change` ซ้ำให้ `#PD_SDATE` หลังจากนั้น จึงล้าง `#PD_EDATE` อีกครั้ง. แก้ทั้ง `app.py` และ `automate_submission.py` ให้ `_set_modal_dates()` ทำงานหลัง generic events เป็นขั้นตอนสุดท้ายก่อน validation.
- เพิ่ม regression assertion ใน `test_workflow26_hardening.py` ตรวจลำดับดังกล่าวทั้ง backend และ CLI. ผลทดสอบรอบนี้ผ่าน Select2 tests 4 กรณี, hardening tests 5 กรณี, `py_compile` และ `git diff --check` แบบ offline. ยังไม่ได้ Draft/Submit.


## 17. แก้ Modal Dynamic Activity Event Ordering รอบถัดไป (2026-08-15)

- Retry บน Render หลัง date fix ยืนยันว่า `PD_EDATE` ผ่านแล้ว แต่ validation พบ `MODAL_FIELD_MISMATCH` ที่ `activity` ครบหลายแถว โดย `#PD_ACTIVITY` กลับเป็นค่าว่าง.
- Controlled test บน modal จริงของพอร์ทัลพบว่า `#PD_ACTIVITY` มี inline handler `bsf_change_objF_398(this.value);` และเมื่อเลือกกิจกรรมแล้วระบบจะ rebuild option list แบบ asynchronous. การ dispatch `input/change/keyup/blur` ให้ทุก field ภายหลังจึงทำให้ dynamic activity ถูกล้างกลับเป็น placeholder.
- ทดสอบซ้ำบน modal จริงโดยไม่บันทึกข้อมูล: หลัง generic events ค่า `#PD_ACTIVITY` ว่าง แต่การกำหนด `select.value` และส่งเฉพาะ `input` event หลัง handler settle แล้ว คงค่า `19` (วิสาหกิจชุมชน) ได้อย่างน้อย 1 วินาที.
- แก้ทั้ง `app.py` และ `automate_submission.py` เพิ่ม `_set_modal_select_value()` ซึ่งตั้งค่า dynamic select ครั้งสุดท้ายโดยไม่ยิง destructive `change` event. หลัง generic events ให้รอ handler 1 วินาที แล้ว re-apply `#PD_ISSUES` และ `#PD_ACTIVITY`; สำหรับกิจกรรม `999` ให้เติม `#PD_OTHER` ซ้ำก่อนตั้งวันที่และ validation.
- เพิ่ม regression test ตรวจว่า final select setter อยู่หลัง generic event block และก่อน `_set_modal_dates()` พร้อมยืนยัน helper ไม่ dispatch `change`. Offline hardening tests ผ่าน 6 กรณี, Select2 tests ผ่าน 4 กรณี, `py_compile` และ `git diff --check` ผ่านแล้ว. ยังไม่ได้ commit/deploy patch และยังไม่มี Draft/Submit.

## 18. สถานะ retry รอบ Dynamic Activity Fix

- Retry ที่กำลังตรวจบน Render เป็น deployment date fix เดิม (`3736c22`) และพบ `activity` ว่างหลังผ่าน dynamic month; ห้ามนำผลรอบนี้ไปสรุปว่า patch section 17 ใช้งานแล้วจนกว่าจะ commit, deploy และ retry ใหม่.
- ยังคงห้ามกด `บันทึกชั่วคราว` หรือ `บันทึกและส่งข้อมูล` ระหว่างการทดสอบทุกกรณี.

---


## 19. Final Dry-run ผ่านครบ 20 แถว (2026-08-15)

- หลัง deployment `6bdee8b` ขึ้น live เวลา 08:14:15 น. ตั้งค่า retry เป็นนครราชสีมา → สีดา → หนองตาดใหญ่, แผน `มิ.ย.69` จำนวน 20 แถว, ผู้อนุมัตินางอรอนงค์ สูญกลาง และ `run_mode=dry_run`.
- Dry-run รอบ final เริ่มเวลา 08:16:54 น. ผ่าน login, Workflow 26, dynamic month readiness และเริ่มกรอก modal เวลา 08:17:20 น. ผลการกรอกแถว 1–20 สำเร็จทั้งหมด โดยไม่พบ `MODAL_FIELD_MISMATCH`, `WORKFLOW_SELECTOR_ERROR`, `WORKFLOW_DYNAMIC_OPTION_ERROR` หรือ error อื่น. แถวสุดท้ายสำเร็จเวลา 08:20:07 น. และระบบสรุป `กรอกข้อมูลเสร็จสิ้นในโหมด Dry-run` เวลา 08:20:08 น.
- ผลนี้ยืนยันว่า date ordering fix และ final dynamic select reapply สามารถทำงานร่วมกับ portal จริงได้ครบทุกแถว. ระหว่างรอบนี้ไม่ได้กด `บันทึกชั่วคราว`, `บันทึกและส่งข้อมูล`, Draft หรือ Submit; จึงไม่มีข้อมูลจริงถูกบันทึกหรือส่งให้ผู้อนุมัติ.
- สถานะปัจจุบัน: production `origin/main` และ Render live อยู่ที่ `6bdee8b`; พร้อมพิจารณาใช้งานจริงในขั้น Draft เท่านั้นหลังผู้ใช้ตรวจข้อมูลอีกครั้ง. ห้ามข้ามการตรวจทานและห้ามเปลี่ยนเป็น Submit โดยอัตโนมัติ.

---


## 20. Security Hardening CI/CD และ Frontend Secret Controls (2026-08-15)

- เตรียม branch แยก `security/hardening` สำหรับยกระดับ security pipeline โดยยังไม่แก้ branch `main` หรือ Render production.
- เพิ่ม `.github/workflows/security.yml` สำหรับ Python/JavaScript syntax และ offline regression tests, `pip-audit`, Semgrep DOM sink regression, CodeQL สำหรับ JavaScript/Python, Gitleaks และ `Security Gate` ที่ต้องผ่านทุก job ก่อนจบ workflow.
- GitHub Actions ใน workflow ถูก pin ด้วย commit SHA ที่ตรวจสอบแล้ว; ห้ามย้ายกลับไปใช้ tag ลอยโดยไม่ review ใหม่.
- เพิ่ม `.semgrep.yml` เพื่อป้องกันการเพิ่ม `innerHTML`, `outerHTML`, `insertAdjacentHTML` และ `document.write` ใหม่ โดยใช้ baseline scan เพื่อทยอยแก้ legacy sinks เดิม.
- ห้ามใส่ T&V username/password, Gemini API key, Render deploy hook หรือ token ใด ๆ ใน workflow, source, log หรือ commit.
- ก่อนเปิดใช้งานจริงต้องให้ workflow ทำงานใน Pull Request สำเร็จ, ตั้ง Branch Protection/Ruleset ของ `main` ให้ required check เป็น `Security Gate`, และตั้ง Render เป็น `After CI Checks Pass` หรือปิด auto-deploy แล้วใช้ deploy hook ที่เก็บใน GitHub Secret.
- ห้ามกด Draft/Submit T&V ระหว่าง security/CI test และห้ามใช้ production credential ใน job ทดสอบ.
- ผล pre-commit validation รอบแรก: security workflow structure, py_compile, node syntax, Select2 readiness tests, Workflow 26 hardening tests, credential cleanup unit test และ git diff check ผ่านแบบ offline; ยังไม่ได้ push หรือ deploy.


## 21. Content Security Policy และ Browser Hardening (2026-08-15)

- เพิ่ม CSP แบบ Report-Only ใน `app.py` ผ่าน `Content-Security-Policy-Report-Only` โดยนโยบายอนุญาตเฉพาะ same-origin scripts/connections, Google Fonts ที่จำเป็น, data/blob image ตามการใช้งาน และปิด object/embed, frame, inline script attributes และ inline style attributes.
- เพิ่ม `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` แบบปิดกล้อง/ไมโครโฟน/geolocation/payment/USB และ HSTS.
- API responses ตั้ง `Cache-Control: no-store` เพื่อลดการ cache ข้อมูลแผนงานและผลลัพธ์ที่อาจมีข้อมูลส่วนบุคคล.
- หลังย้าย inline event handlers/styles แล้ว ใช้ per-request nonce กับ JSON-LD ใน `app.py`; `CSP_ENFORCE=1` จะเป็นค่าเริ่มต้นเมื่อ `APP_ENV=production` และยังสามารถ override ได้ด้วย environment variable. ต้องตรวจ browser violations ก่อน deploy.
- เพิ่ม `test_security_headers.py` และผูกเข้า Security Gate; CSP unit test, existing Workflow 26 tests, credential cleanup test, py_compile, node syntax check และ git diff check ผ่านใน sandbox.


## 22. Access Boundary, Upload Hardening และ Private Artifacts (2026-08-15)

- เพิ่ม `Flask-Limiter[redis]==4.1.1` ใน `requirements.txt` เพื่อให้ rate limiting ใช้งานได้ทั้ง memory storage สำหรับ development และ Redis storage สำหรับ production.
- เพิ่ม application authentication boundary ผ่าน `APP_AUTH_REQUIRED=1`; เมื่อเปิดใช้งานต้อง login ผ่าน `/api/auth/login` และ protected API ที่ไม่มี session จะตอบกลับโดยไม่เปิดเผยรายละเอียดภายใน. ค่าเริ่มต้นปัจจุบัน `APP_AUTH_REQUIRED=1` แบบ fail-closed.
- เพิ่ม session cookie hardening, CSRF token สำหรับ mutation requests และ rate limits สำหรับ login, upload, records, add-row และ run automation. ห้ามบันทึก password, T&V username หรือ Gemini API key ลง Web Storage.
- Upload ใช้ opaque `upload_id`, ตรวจ extension และ magic bytes/ZIP structure, จำกัดขนาด, ผูก owner กับ session และล้างตาม TTL. ห้ามใช้ชื่อไฟล์จาก client เป็น path โดยตรง.
- Portal screenshots ห้ามเขียนลง `static/` หรือเผยแพร่ผ่าน URL สาธารณะ; diagnostics ที่ส่งผ่าน SSE ต้องเป็นข้อความที่จำเป็นเท่านั้น และ frontend ต้องไม่โหลด URL screenshot ที่ไม่ได้รับอนุญาต.
- ระหว่าง security validation ห้ามกด Draft/Submit T&V และห้ามใช้ credential จริงใน CI. ก่อน merge ต้องผ่าน syntax checks, offline regression tests, security tests, dependency audit, SAST และ secret scan.
- สถานะรอบนี้: แก้ source และ dependency แล้ว; ต้องเพิ่ม/ยืนยัน regression tests, รัน validation, ตรวจ diff และจึงค่อย commit/push/เปิด PR. ยังไม่เปลี่ยน `main` หรือ Render production.

---

*อัปเดตล่าสุด: security/access-upload-hardening; โปรดตรวจสถานะ branch และ test result ก่อน deploy ทุกครั้ง.*


## 23. Security Follow-up Validation (2026-08-15)

- ปิดเส้นทาง artifact ใน `automate_submission.py` เพิ่มเติม: error screenshot ถูกจับไว้ใน memory ชั่วคราวเท่านั้น และลบการเขียน modal HTML ลง path คงที่ของเครื่องผู้พัฒนา.
- ปรับ `_upload_owner_key()` ให้ผู้ใช้ anonymous ผูก upload กับ token แบบสุ่มใน signed session แทนการใช้ IP เพียงอย่างเดียว เพื่อไม่ให้ผู้ใช้หลายรายที่อยู่หลัง NAT/proxy เดียวกันเข้าถึง upload ของกันและกัน.
- ปรับ `static/app.js` ให้ Gemini API key ไม่ถูกอ่านจากหรือเขียนลง Web Storage รวมถึงล้าง legacy key ที่อาจค้างอยู่ และให้ใช้ค่าใน input memory-only ระหว่างการอ่าน Excel เท่านั้น.
- เพิ่ม regression assertions สำหรับการไม่อ่าน/เขียน T&V username/password และ Gemini key จาก Web Storage รวมถึงการไม่เขียน screenshot หรือ modal HTML ลงดิสก์.
- เพิ่ม `node --check static/auth.js` ใน Security Gate. Local CI-equivalent checks, Python/JavaScript syntax, dependency audit (`pip-audit`) และ offline regression tests ผ่านแล้ว; Semgrep แบบ baseline ของ `main` ไม่พบ finding ใหม่ ขณะที่ full scan ยังรายงาน legacy `innerHTML` sinks เดิมตามที่ baseline rule ออกแบบไว้.
- สถานะยังเป็น pre-PR: ต้อง stage ตรวจ diff/secret scan, commit, push branch, เปิด Pull Request และรอ Security Gate ก่อน merge หรือ deploy.


## อัปเดต Security/Data Governance — 2026-08-15

- ถอด Google GenAI/Gemini integration ออกจาก backend, frontend, requirements, template และ source tree สำรองทั้งหมด
- `/api/records` ใช้ local deterministic rules-based parser เท่านั้น; ไม่อ่าน `X-Gemini-API-Key` และไม่ส่งข้อมูล Excel ไป external AI service
- ลบ Gemini API key field และ Web Storage handling จาก frontend พร้อมปรับ USER_GUIDE/WORKFLOW ให้ระบุ local processing
- เพิ่ม regression assertions ว่า runtime source ไม่มี Gemini/API-key integration และ dependency `google-genai` ไม่อยู่ใน requirements
- ตรวจ syntax Python/JavaScript, regression 17 tests, credential cleanup และ `git diff --check` ผ่านหลังการเปลี่ยนแปลง
- ห้ามนำข้อมูล Excel ที่มีข้อมูลส่วนบุคคลหรือข้อมูลภายในไปยังบริการ AI ภายนอกผ่านระบบนี้ เพราะระบบถูกออกแบบให้ไม่เชื่อมต่อ external AI แล้ว
- หยุดการทำสไลด์ชั่วคราวตามคำขอ และให้การแก้โค้ด/validation เป็นงานหลักของรอบนี้


## Security Audit รอบที่ 3 — remediation status (2026-08-15)

รอบนี้แก้ประเด็น Critical/High และ deployment safeguards ที่ตรวจได้จาก source code แล้ว ได้แก่ เปลี่ยน `APP_AUTH_REQUIRED` default เป็น `1`, เพิ่ม server-side authorization profile สำหรับ role/office/allowed tambons/allowed approvers/สิทธิ์ submit, และ whitelist `mode` ก่อนเริ่ม Playwright โดยไม่เชื่อค่าขอบเขตจาก client เมื่อเปิด app auth

Dockerfile หลักและชุด `Ready_For_GitHub` ใช้ non-root `appuser`, `COPY --chown`, จำกัด writable directory ไว้ที่ `/tmp/tv-automation-uploads` และไม่มี `chmod -R 777` อีกต่อไป ส่วน Compose bind port เป็น `127.0.0.1:7860:7860` และใช้ UID 1000 เพื่อไม่เปิด application ตรงสู่ public interface โดย default

เพิ่ม exact-pinned `requirements.txt` และ `requirements.lock`; เพิ่ม production guard ให้ `APP_ENV=production` ปฏิเสธ `memory://` rate-limit storage และลด diagnostics จาก portal โดยไม่ส่ง body text, title, full URL หรือค่า select กลับ authenticated client

Security checker และ regression coverage รอบล่าสุดผ่าน 23 tests และ checker 13/13 checks; หากพบข้อมูลหรือสิทธิ์ไม่ครบใน production ให้ระบบ fail closed และต้องตั้ง environment/ACL ให้ครบก่อนเปิดใช้งานจริง


## 25. CI Compatibility Follow-up (2026-08-16)

- Security Gate run แรกบน commit CSP migration ตรวจพบว่า `pandas==3.0.5` และ `numpy==2.5.1` ยังติดตั้งไม่ได้ใน Python runtime ของ Playwright Jammy image/GitHub runner จึงปรับ manifest และ lock ให้ใช้ `pandas==2.3.3` กับ `numpy==2.2.6` ซึ่งรองรับ runtime เดิมและยัง pin แบบ reproducible.
- Semgrep baseline scan เดิมรายงาน legacy `innerHTML` sinks ที่ถูกย้ายบรรทัดระหว่าง CSP refactor; เพิ่ม `nosemgrep: tv-automation-no-dynamic-innerhtml` เฉพาะจุดที่ตรวจแล้ว เพื่อไม่บล็อก legacy sinks แต่ยังทำให้ sink ใหม่โดยไม่มี reviewed annotation ล้มเหลวใน CI.
- แก้ manual runner ของ `test_security_headers.py` ไม่ให้พึ่ง pytest `monkeypatch` fixture เพื่อให้คำสั่งที่ระบุใน Security Gate ทำงานได้จริงทั้งแบบ direct runner และ pytest.
- Local Semgrep baseline scan หลังแก้ผ่าน 0 findings; ต้อง rerun GitHub Security Gate หลัง push commit แก้ไข. หาก Docker build หรือ dependency audit ล้มอีก ให้แก้จาก log ของ runner ก่อนพิจารณา merge.
