# Central Data Hub

เว็บแอปพลิเคชันต้นแบบสำหรับรวมข้อมูลจากหลายแหล่งเข้าสู่สำเนาฐานข้อมูลกลางแบบอ่านอย่างเดียว เพื่อให้เจ้าหน้าที่ค้นหา กรอง ดูรายละเอียด และติดตามความพร้อมของข้อมูลได้จากหน้าเดียว

โครงการเริ่มจากข้อมูลทะเบียนโบราณวัตถุที่อยู่ใน Excel/Google Sheets และออกแบบให้ขยายไปยังแหล่งข้อมูลของหลายฝ่ายในอนาคต โดยไม่แก้ไขข้อมูลต้นทาง

> สถานะปัจจุบัน: MVP สำหรับทดลองภายใน ยังไม่พร้อมใช้งาน production

## ความสามารถ

- **Data Explorer** — ค้นหาจากเลขทะเบียน เลขทะเบียนเดิม รายการ ชนิด อายุสมัย และประวัติที่มา พร้อมตัวกรองตามชีตและสถานะงาน
- **Detail** — แสดงรายละเอียดของระเบียน แหล่งที่มา สถานะการทำงาน และรายการเลขทะเบียนที่อาจซ้ำ
- **รูปภาพ** — แสดงภาพเมื่อคอลัมน์ `รูปภาพ` มี URL ที่เปิดได้ รวมถึง Google Drive share URL ที่แปลงเป็น image URL อัตโนมัติ
- **Dashboard** — สรุปจำนวนระเบียน ความครบถ้วนของข้อมูล และสถานะงานตามชีตต้นทาง
- **Data Catalog** — แสดงแหล่งข้อมูล จำนวนระเบียน สถานะ sync ล่าสุด และประเด็นคุณภาพข้อมูล
- **Traceability** — เก็บชื่อชีต เลขแถวต้นทาง ข้อมูลต้นฉบับที่นำเข้า และประวัติการ import เพื่อย้อนตรวจได้
- **Idempotent import** — นำเข้าไฟล์เดิมซ้ำได้โดยไม่สร้างระเบียนซ้ำ; ระบบจะข้ามแถวที่ไม่มีการเปลี่ยนแปลง

## สถาปัตยกรรม

```text
Excel / Google Sheets ของแต่ละฝ่าย
              │
              ▼
      Import / Sync service
      - validate
      - normalize
      - data-quality checks
              │
              ▼
        PostgreSQL + pgvector
        - records
        - data sources
        - sync history
              │
              ▼
           FastAPI API
              │
              ▼
        Web interface
```

## Tech stack

- Backend: Python, FastAPI, SQLAlchemy
- Database: PostgreSQL 16 with pgvector (Docker) หรือ SQLite สำหรับ local demo
- Import: openpyxl
- Frontend: HTML, CSS และ JavaScript แบบไม่มี framework
- Container: Docker Compose

## เริ่มต้นใช้งานด้วย Docker

### สิ่งที่ต้องมี

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Git (เฉพาะกรณี clone จาก GitHub)

### 1. Clone และเปิดโฟลเดอร์โครงการ

```powershell
git clone <repository-url>
cd Central-data-hub
```

### 2. เริ่มระบบ

```powershell
docker compose up -d --build
```

ตรวจสอบสถานะ:

```powershell
docker compose ps
```

ควรเห็นทั้ง `db` และ `web` มีสถานะ `Up` โดย `db` ต้องเป็น `healthy`

### 3. นำเข้าไฟล์ Excel

คำสั่งนี้ mount ไฟล์จากเครื่องเข้าสู่ container แบบอ่านอย่างเดียว (`:ro`) ดังนั้นระบบจะไม่แก้ไขไฟล์ต้นฉบับ

```powershell
docker compose run --rm -v "C:\path\to\your-file.xlsx:/imports/source.xlsx:ro" web python -m app.import_workbook /imports/source.xlsx
```

ตัวอย่างสำหรับไฟล์บน Desktop:

```powershell
docker compose run --rm -v "C:\Users\Supakon\Desktop\บัญชีเดินทุ่ง.xlsx:/imports/source.xlsx:ro" web python -m app.import_workbook /imports/source.xlsx
```

เมื่อ import สำเร็จ ระบบจะแสดงจำนวน `inserted`, `updated` และ `skipped`

### 4. เปิดเว็บไซต์

ไปที่ [http://127.0.0.1:8000](http://127.0.0.1:8000)

หากเพิ่งอัปเดต frontend แต่ Chrome ยังแสดงหน้าเดิม ให้เปิด URL ใหม่พร้อม query ชั่วคราว เช่น:

```text
http://127.0.0.1:8000/?refresh=latest
```

## คำสั่ง Docker ที่ใช้บ่อย

| งาน | คำสั่ง |
|---|---|
| เริ่มระบบ | `docker compose up -d` |
| rebuild หลังแก้โค้ด | `docker compose up -d --build --force-recreate` |
| ดู log ของเว็บ | `docker compose logs web --tail 100` |
| ดูสถานะ container | `docker compose ps` |
| หยุดระบบ | `docker compose down` |

`docker compose down` จะไม่ลบข้อมูล PostgreSQL volume โดยปกติ หลีกเลี่ยง `docker compose down -v` หากยังต้องการเก็บข้อมูลทดสอบ

## เริ่มต้นใช้งานแบบ local demo (ไม่ใช้ Docker)

วิธีนี้ใช้ SQLite ในโฟลเดอร์ `data/` เหมาะกับการพัฒนาและทดลองคนเดียว

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m app.import_workbook "C:\path\to\your-file.xlsx"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

เปิด [http://127.0.0.1:8000](http://127.0.0.1:8000)

> ไม่จำเป็นต้อง activate virtual environment จึงไม่ติดปัญหา PowerShell execution policy

## รูปภาพในระเบียน

ระบบจะแสดงรูปภาพได้เมื่อคอลัมน์ `รูปภาพ` มี URL `http://` หรือ `https://` ที่ browser เข้าถึงได้ เช่น URL ของ object storage หรือ Google Drive ที่ตั้ง permission ถูกต้อง

- สถานะ `ถ่ายภาพแล้ว` เป็นเพียง workflow status และไม่ใช่ไฟล์ภาพ
- รูปที่ฝังลงใน Excel/Google Sheets โดยไม่มี URL ยังไม่ถูก extract ใน MVP นี้
- Google Drive file ต้องอนุญาตให้ผู้ใช้เว็บเปิดดูได้ มิฉะนั้น browser จะไม่สามารถแสดงภาพ

## โครงสร้างโครงการ

```text
central-data-hub/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI routes
│   │   ├── models.py           # Database schema
│   │   ├── import_workbook.py  # Excel import command
│   │   └── normalization.py    # Data and image URL normalization
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── docker-compose.yml
└── .env.example
```

## การจัดการข้อมูลและข้อจำกัด

- Import ปัจจุบันรองรับไฟล์ `.xlsx`
- ระบบเก็บแถวข้อมูลตาม `source / sheet / row` เพื่อรักษาที่มา
- เลขทะเบียนซ้ำจะถูกแสดงเป็น candidate สำหรับตรวจสอบ ไม่ถูก merge อัตโนมัติ
- Google Sheets connector ยังเป็นโครงสร้างเตรียมไว้และตั้งใจให้เป็น **read-only**
- ยังไม่มีระบบ login, SSO, RBAC หรือ audit retention ที่เพียงพอสำหรับ production

## ก่อนเชื่อม Google Sheets จริง

1. เลือก Google Sheets pilot 2–3 ชุดและระบุเจ้าของข้อมูล
2. สร้าง Google service account แบบ read-only
3. แชร์เฉพาะ spreadsheet ที่ได้รับอนุมัติให้ service account
4. กำหนด field mapping และ data-quality rules ของแต่ละฝ่าย
5. ทดสอบ sync แบบ dry-run ก่อนเปิด schedule จริง
6. เพิ่ม SSO/RBAC, secrets management, backup, monitoring และ UAT ก่อนใช้งานจริง

## ความปลอดภัย

- อย่า commit `.env`, service-account JSON, รหัสผ่าน หรือไฟล์ข้อมูลจริงขึ้น GitHub
- ค่า PostgreSQL password ใน `docker-compose.yml` เป็นค่า development เท่านั้น ต้องเปลี่ยนก่อนใช้งานนอกเครื่องส่วนตัว
- ควรใช้ข้อมูลที่ anonymized สำหรับ demo เมื่อข้อมูลมีข้อจำกัดด้านการเข้าถึง
- ระบบ MVP นี้ไม่ควรถูกเปิดสู่ Internet โดยไม่มี authentication, HTTPS และการกำหนดสิทธิ์

## Roadmap

- [ ] Google Sheets read-only sync service และ scheduled sync
- [ ] หน้าเพิ่ม/แก้ไข Data Source และ Field Mapping สำหรับผู้ดูแล
- [ ] User authentication, SSO และ RBAC
- [ ] Data-quality workflow และการจัดการ duplicate candidates
- [ ] Export ที่ควบคุมสิทธิ์
- [ ] Image storage และ preview สำหรับไฟล์ภาพจริง
- [ ] ต่อยอดสู่ระบบ AI ค้นหาความคล้ายของภาพโบราณวัตถุ
