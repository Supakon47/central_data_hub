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
- **หน้าจัดการข้อมูล** — เพิ่ม แก้ไข และลบระเบียนในสำเนากลางหลังปลดล็อกด้วยรหัสผ่านผู้ดูแล
- **Traceability** — เก็บชื่อชีต เลขแถวต้นทาง ข้อมูลต้นฉบับที่นำเข้า และประวัติการ import เพื่อย้อนตรวจได้
- **Audit log** — เก็บประวัติการสร้าง แก้ไข และลบที่ทำผ่านหน้าผู้ดูแล
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
- Import / sync: openpyxl, Google Sheets API (read-only)
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
- รูปที่ฝังลงใน Excel จะถูกดึงออกมาเมื่อ anchor อยู่ในคอลัมน์ที่มีหัวข้อ `รูปภาพ` ของชีตนั้น ระบบหา column นี้จากชื่อหัวตาราง จึงรองรับทั้ง G, H หรือคอลัมน์อื่น
- หากพบรูปมากกว่า 1 รูปในช่องเดียวกัน ระบบจะไม่เดาเลือกภาพ แต่บันทึกเป็นประเด็นให้เจ้าหน้าที่ตรวจสอบ
- Google Sheets ที่แสดงรูปโดยไม่มี URL ยังไม่ถูก extract ใน MVP นี้
- Google Drive file ต้องอนุญาตให้ผู้ใช้เว็บเปิดดูได้ มิฉะนั้น browser จะไม่สามารถแสดงภาพ

## เปิดใช้หน้าจัดการข้อมูล

หน้าจัดการใช้แก้เฉพาะ **สำเนากลาง** ในระบบนี้ ไม่ได้เขียนกลับไปยัง Excel หรือ Google Sheets ต้นทาง เพื่อป้องกันการแก้ข้อมูลของแต่ละฝ่ายโดยไม่ตั้งใจ

1. Rebuild ระบบก่อนหนึ่งครั้ง:

```powershell
docker compose up -d --build --force-recreate
```

2. สร้าง password hash และ session secret โดยคำสั่งนี้จะถามรหัสผ่าน (อย่างน้อย 12 ตัวอักษร) และแสดงค่า 2 บรรทัด โดยไม่บันทึกรหัสผ่านลงไฟล์เอง:

```powershell
docker compose run --rm -it web python -m app.generate_admin_credentials
```

3. เปิดไฟล์ `.env` ในโฟลเดอร์โครงการ แล้ววางสองบรรทัดที่คำสั่งแสดง เช่น:

```text
ADMIN_PASSWORD_HASH='pbkdf2_sha256$...'
ADMIN_SESSION_SECRET=...
ADMIN_SESSION_TTL_SECONDS=28800
```

4. Recreate web container เพื่อให้อ่านค่าล่าสุด:

```powershell
docker compose up -d --force-recreate
```

5. เปิดเว็บ แล้วเลือกแท็บ **จัดการข้อมูล** จากนั้นกรอกรหัสผ่านที่ตั้งไว้

การแก้ไขระเบียนจาก Excel/Google Sheets จะถูกเก็บใน Audit log และยังอยู่ต่อเมื่อแถวต้นทางไม่เปลี่ยน แต่หาก sync ในอนาคตพบว่าแถวต้นทางมีข้อมูลใหม่ ระบบจะใช้ข้อมูลใหม่จากต้นทางแทนค่าในสำเนากลาง ส่วนระเบียนที่เพิ่มจากหน้าผู้ดูแลจะอยู่ใต้แหล่งข้อมูล `แก้ไขโดยเจ้าหน้าที่` และการลบระเบียนจากแหล่งข้อมูลที่ sync อาจถูกนำเข้ากลับมาได้ในการ sync รอบถัดไป

## โครงสร้างโครงการ

```text
central-data-hub/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI routes
│   │   ├── models.py           # Database schema
│   │   ├── import_workbook.py  # Excel import command
│   │   ├── configure_google_sheet.py # Register an approved Google Sheets tab
│   │   ├── sync_google_sheet.py      # Read-only Google Sheets sync command
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
- Google Sheets connector อ่านข้อมูลผ่าน Google Sheets API แบบ **read-only** เท่านั้น และต้องมีแหล่งข้อมูลใน Data Catalog ก่อนจึงจะสั่ง sync ได้
- MVP รองรับหัวตารางที่แถวแรกของ range (`A:ZZ`) และใช้ลำดับแถวเป็น identity ของแหล่งข้อมูล; อย่าย้ายแถวจำนวนมากโดยไม่ sync/ตรวจสอบผล
- ยังไม่มีระบบ login, SSO, RBAC หรือ audit retention ที่เพียงพอสำหรับ production

## Google Sheets read-only sync (Pilot)

ใช้กับ Google Sheets ที่เจ้าของข้อมูลอนุมัติเท่านั้น ระบบไม่มีหน้าสำหรับวาง credential หรือ URL ของชีต และ credential จะไม่ถูกบันทึกลงฐานข้อมูล

1. เลือกชีตทดสอบ 1 ชุด ระบุเจ้าของข้อมูล และเตรียมหัวคอลัมน์ที่ระบบรู้จัก เช่น `เลขทะเบียน`, `รายการ`, `ชนิด` โดยให้หัวตารางอยู่แถวแรกของช่วงข้อมูล
2. สร้าง Google service account สำหรับงานนี้ แล้วแชร์เฉพาะ spreadsheet ทดสอบให้ email ของ service account ในสิทธิ์ **Viewer**
3. Rebuild เพื่อให้ container มี Google Sheets library:

```powershell
docker compose up -d --build --force-recreate
```

4. ลงทะเบียนชีตไว้ใน Data Catalog (คำสั่งนี้ยังไม่อ่านข้อมูลจาก Google):

```powershell
docker compose run --rm web python -m app.configure_google_sheet --source-name "ทะเบียนโบราณวัตถุ ฝ่ายตัวอย่าง" --spreadsheet-id "SPREADSHEET_ID" --sheet "Sheet1" --read-range "A:ZZ" --owner "ชื่อฝ่าย"
```

`SPREADSHEET_ID` คือข้อความระหว่าง `/d/` และ `/edit` ใน URL ของ Google Sheets ไม่ใช่ URL ทั้งเส้น

5. นำไฟล์ service-account JSON จากตำแหน่งที่ปลอดภัยมา mount เข้า container แบบอ่านอย่างเดียว แล้วทดสอบ **dry-run** ก่อน ทุกอย่างในคำสั่งนี้เป็นข้อมูลในเครื่องและไฟล์ credential จะไม่ถูกเขียนลง project:

```powershell
docker compose run --rm -v "C:\safe\google-service-account.json:/run/secrets/google-service-account.json:ro" -e GOOGLE_SHEETS_ENABLED=true -e GOOGLE_SERVICE_ACCOUNT_FILE=/run/secrets/google-service-account.json web python -m app.sync_google_sheet --source-name "ทะเบียนโบราณวัตถุ ฝ่ายตัวอย่าง" --dry-run
```

ผลลัพธ์ dry-run ต้องมี `ready_to_import: true` และรายชื่อ header ที่รู้จักก่อนดำเนินการต่อ หากขึ้น permission error ให้ตรวจว่าแชร์ชีตให้ service account แล้ว และหากขึ้นว่าไม่พบ header ให้ตรวจชื่อคอลัมน์หรือเพิ่ม field mapping ก่อน

6. เมื่อ dry-run ถูกต้อง ให้สั่งคำสั่งเดิมโดยตัด `--dry-run` ออก ระบบจะนำเข้าหรืออัปเดตเฉพาะข้อมูลที่เปลี่ยนไป และไม่แก้ไข Google Sheet ต้นทาง:

```powershell
docker compose run --rm -v "C:\safe\google-service-account.json:/run/secrets/google-service-account.json:ro" -e GOOGLE_SHEETS_ENABLED=true -e GOOGLE_SERVICE_ACCOUNT_FILE=/run/secrets/google-service-account.json web python -m app.sync_google_sheet --source-name "ทะเบียนโบราณวัตถุ ฝ่ายตัวอย่าง"
```

ยังไม่มี scheduled sync อัตโนมัติใน MVP เพื่อให้เริ่มจากการตรวจผลด้วยเจ้าหน้าที่ก่อน

## ความปลอดภัย

- อย่า commit `.env`, service-account JSON, รหัสผ่าน หรือไฟล์ข้อมูลจริงขึ้น GitHub
- ค่า `ADMIN_PASSWORD_HASH` เป็น hash ทางเดียว; ห้ามตั้ง `ADMIN_PASSWORD_HASH` เป็นรหัสผ่านธรรมดา และควรเปลี่ยนรหัสผ่านด้วยการสร้าง hash ใหม่
- ค่า PostgreSQL password ใน `docker-compose.yml` เป็นค่า development เท่านั้น ต้องเปลี่ยนก่อนใช้งานนอกเครื่องส่วนตัว
- ควรใช้ข้อมูลที่ anonymized สำหรับ demo เมื่อข้อมูลมีข้อจำกัดด้านการเข้าถึง
- รหัสผ่านหน้าแอดมินนี้เหมาะกับ pilot ภายในเครื่อง/เครือข่ายที่เชื่อถือได้เท่านั้น; ก่อนเปิดสู่ Internet ต้องเปลี่ยนเป็น SSO/RBAC, HTTPS, rate limiting และระบบจัดการ secrets ที่เหมาะสม

## Roadmap

- [x] Google Sheets read-only sync service พร้อม dry-run และ allow-list ของชีต
- [x] Password-protected admin page สำหรับแก้ไขสำเนากลาง พร้อม audit log
- [ ] Scheduled sync พร้อม monitoring และ notification
- [ ] หน้าเพิ่ม/แก้ไข Data Source และ Field Mapping สำหรับผู้ดูแล
- [ ] User authentication, SSO และ RBAC
- [ ] Data-quality workflow และการจัดการ duplicate candidates
- [ ] Export ที่ควบคุมสิทธิ์
- [ ] Image storage และ preview สำหรับไฟล์ภาพจริง
- [ ] ต่อยอดสู่ระบบ AI ค้นหาความคล้ายของภาพโบราณวัตถุ
