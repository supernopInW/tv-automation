# 🤖 Project Knowledge & AI Model Development Guidelines (AGENTS.md)
> **DOAE T&V Automation System (ระบบกรอกแผนเยี่ยมเยียนอัตโนมัติ T&V)**  
> **Last Updated:** 2026-08-04  
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

ระบบ **DOAE T&V Automation** เป็น Web Application (Flask + Playwright + JavaScript) ที่ถูกพัฒนาขึ้นเพื่อช่วยเจ้าหน้าที่สำนักงานเกษตรอำเภอ (เริ่มต้นจาก **สำนักงานเกษตรอำเภอสีดา จ.นครราชสีมา**) นำข้อมูล **"แผนการเยี่ยมเยียนรายเดือน" จากไฟล์ Excel** เข้าสู่ระบบพอร์ทัล **DOAE T&V (https://tandv.doae.go.th)** (Workflow 26) โดยอัตโนมัติ

---

## 🛠️ 2. สถาปัตยกรรมระบบ & Tech Stack (Architecture & Tech Stack)

- **Backend:** Python 3.10+, Flask, Pandas, openpyxl, xlrd
- **Automation Engine:** Playwright (Chromium Async/Sync API) สำหรับควบคุม Headless/Headed Browser ไปยังระบบ T&V
- **AI Integration:** Google GenAI SDK (`google-genai`) สำหรับฟีเจอร์ช่วยวิเคราะห์/ประมวลผลข้อความจากแผน Excel
- **Frontend:** Vanilla HTML5, CSS3 (Modern Responsive Dashboard, CSS Variables, Glassmorphism design), Vanilla JavaScript (`static/app.js`)
- **Data Persistence & Cache:** ข้อมูลภูมิศาสตร์ใน `data/` และ `config/districts.json`
- **Tunneling & Deployment:** Cloudflare Tunnel (`cloudflared.exe`) และ Ngrok (`ngrok.exe`)

---

## 📁 3. แผนผังโครงสร้างไฟล์สำคัญ (Key Directory & File Structure)

ดูรายละเอียดไฟล์ทั้งหมดได้ใน [AGENTS.md](file:///d:/จากไดรฟ์C/Downloads/tv_automation/AGENTS.md) ที่ Root Directory ของโปรเจกต์

---

## ⚙️ 4. กฎธุรกิจและตรรกะสำคัญ (Core Business Logic)

1. **กฎวันจันทร์ (Monday Rule - ประชุมสำนักงาน):** จันทร์แรกของเดือน = **DM (รหัส 13)** / จันทร์อื่น = **WM (รหัส 14)** ที่สำนักงานเกษตรอำเภอ (จำนวนคนอ้างอิงจากช่อง "จำนวนสมาชิกสำนักงาน")
2. **งานภาคสนาม:** สุ่มหมู่บ้าน 2-4 หมู่บ้านตามตำบลที่รับผิดชอบ (`หมู่ X, Y ตำบล [ชื่อตำบล]`) และสุ่มจำนวนบุคคลเป้าหมายจาก `[20, 30, 50, 60]` คน
3. **การขยายวัน:** ขยายช่วงวันใน Excel (เช่น `๕-๗ ส.ค. ๖๙`) เป็นหลายแถววันจริง
4. **โหมด Playwright:** Dry-run (ทดสอบ) / Save Draft (บันทึกชั่วคราว) / Submit (บันทึก & ส่ง)
5. **ความปลอดภัย:** ห้ามเก็บรหัสผ่าน T&V ลงไฟล์/DB เด็ดขาด
6. **ปุ่มสร้างแผนอัตโนมัติ:** เมื่อเลือกอำเภอและตำบลในพื้นที่รับผิดชอบแล้ว ระบบจะปลดล็อกปุ่มและทำ Auto-confirm ให้อัตโนมัติเมื่อกดสร้างแผน

---

## 📝 5. ข้อตกลงการอัปเดตไฟล์ (Self-Updating Protocol)

- ทุกครั้งที่มีการแก้ไขโปรเจกต์ ให้ทำการอัปเดตไฟล์ [AGENTS.md](file:///d:/จากไดรฟ์C/Downloads/tv_automation/AGENTS.md) ที่ Root และไฟล์นี้เสมอเพื่อคงความสมบูรณ์และทันสมัยของข้อมูล
