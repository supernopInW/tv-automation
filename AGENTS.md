# 🤖 Project Knowledge & AI Model Development Guidelines (AGENTS.md)
> **DOAE T&V Automation System (ระบบกรอกแผนเยี่ยมเยียนอัตโนมัติ T&V)**  
> **Last Updated:** 2026-08-13
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
- **AI Integration:** Google GenAI SDK (`google-genai`) สำหรับฟีเจอร์ช่วยวิเคราะห์/ประมวลผลข้อความจากแผน Excel
- **Frontend:** Vanilla HTML5, CSS3 (Modern Responsive Dashboard, CSS Variables, Glassmorphism design), Vanilla JavaScript (`static/app.js`)
- **Data Persistence & Cache:** 
  - ข้อมูลภูมิศาสตร์ (จังหวัด/อำเภอ/ตำบล/หมู่บ้าน) เก็บเป็น JSON ใน `data/` และ `config/districts.json`
  - รหัสผ่าน T&V ของผู้ใช้ **ไม่เก็บในฐานข้อมูลหรือไฟล์** (เก็บเฉพาะใน `sessionStorage` บน Browser ของผู้ใช้ชั่วคราวเท่านั้น)
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
├── requirements.txt           # Python Dependencies (Flask, Playwright, Pandas, google-genai ฯลฯ)
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
