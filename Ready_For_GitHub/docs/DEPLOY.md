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

แอปพลิเคชันจะทำงานทันทีที่ URL: **`http://<IP-ของเซิร์ฟเวอร์>:7860`**

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

- [x] ไฟล์ `docker-compose.yml` และ `Dockerfile` พร้อมใช้งาน
- [x] มีโฟลเดอร์ `data/` และฐานข้อมูลภูมิศาสตร์ไทยครบถ้วน
- [x] ตรวจสอบระบบสุ่มสร้างแผนบนเว็บ / อัปโหลด Excel
- [x] ตรวจสอบกฎวันจันทร์ (DM/WM) และการใช้จำนวนสมาชิกสำนักงาน
- [x] ตรวจสอบการสุ่มเป้าหมายภาคสนาม `[20, 30, 50, 60]` คน
- [x] ยืนยันความปลอดภัย: ไม่มีรหัสผ่าน T&V ของผู้ใช้ถูกเก็บบันทึกบนเซิร์ฟเวอร์
