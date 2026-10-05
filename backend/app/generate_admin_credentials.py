"""Generate values to paste into a local .env file; it does not write secrets."""

import getpass
import secrets

from .admin_security import hash_password


if __name__ == "__main__":
    password = getpass.getpass("ตั้งรหัสผ่านผู้ดูแล (อย่างน้อย 12 ตัวอักษร): ")
    confirmation = getpass.getpass("ยืนยันรหัสผ่าน: ")
    if password != confirmation:
        raise SystemExit("รหัสผ่านไม่ตรงกัน")
    try:
        password_hash = hash_password(password)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print("คัดลอกสองบรรทัดนี้ลงในไฟล์ .env (ห้ามนำไปใส่ Git):")
    # Single quotes keep the $ separators literal when Docker Compose reads .env.
    print(f"ADMIN_PASSWORD_HASH='{password_hash}'")
    print(f"ADMIN_SESSION_SECRET={secrets.token_urlsafe(48)}")
