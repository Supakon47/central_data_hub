import re
import unicodedata
from urllib.parse import urlparse
from urllib.parse import parse_qs


GOOGLE_SHEETS_IMAGE_FORMULA = re.compile(
    r'^\s*=\s*IMAGE\s*\(\s*"((?:[^"]|"")*)"', re.IGNORECASE
)
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
REGISTRATION_PLACEHOLDERS = {"", "-", "ไม่มี", "ไม่พบ", "ไม่ระบุ", "ชิ้นส่วน"}
# Storage-room workbooks write "no number" in many forms, often with a running
# count or a temporary prefix: "ไม่มีเลข 3", "ไม่มีเลขวัตถุ(3)", "ไม่พบเลข",
# "ไม่ให้เลขปพ.12", "เลขไม่ชัดเจน", "99/เลขลบเลือน", "99/C1-1-ไม่มีเลข 5",
# "เงินพดด้วง(ไม่มีเลข)(2)". None of these identifies an object, so any value
# containing one of these markers must never become a shared matching key.
REGISTRATION_PLACEHOLDER_MARKERS = re.compile(r"ไม่มี|ไม่พบ|ไม่ให้เลข|ไม่ระบุ|ไม่ชัด|ลบเลือน|รอหาเลข")
# A bare running number such as "2" or "(1)" is a row counter, and "99/" is an
# unfinished entry; neither is a registration.
BARE_COUNTER = re.compile(r"^\(?\d+\)?/?$")


def clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def clean_multiline_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\r\n?", "\n", str(value))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def normalise_header(value: object | None) -> str:
    return clean_text(value) or ""


def normalise_registration_no(value: object | None) -> str | None:
    """Create a conservative key for comparing registration values.

    The function deliberately preserves the original value in source data and
    does not guess missing components. It only resolves spacing, Unicode and
    Thai-digit differences that should not make two registrations distinct.
    """
    text = clean_text(value)
    if not text:
        return None
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", "", text).translate(THAI_DIGITS).replace("／", "/")
    if text in REGISTRATION_PLACEHOLDERS or REGISTRATION_PLACEHOLDER_MARKERS.search(text):
        return None
    # A real registration always carries a number; text-only values such as
    # "?" or an object name typed into the wrong column cannot be matched.
    if not re.search(r"\d", text) or BARE_COUNTER.match(text):
        return None
    return text.upper()


def is_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalise_image_url(value: object | None) -> str | None:
    """Return a browser-displayable image URL when the source supplies one.

    Google Drive share URLs are converted to its image endpoint. The file still
    needs sharing permissions that allow the logged-in viewer to open it.
    """
    url = clean_text(value)
    if url and url.startswith("/media/"):
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        if not parsed.query and not parsed.fragment and ".." not in parts:
            return parsed.path
    if not is_http_url(url):
        return None
    parsed = urlparse(url)
    if parsed.netloc.lower().endswith("drive.google.com"):
        match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
        file_id = match.group(1) if match else parse_qs(parsed.query).get("id", [None])[0]
        if file_id:
            return f"https://drive.google.com/uc?export=view&id={file_id}"
    return url


def image_url_from_google_sheets_formula(value: object | None) -> str | None:
    """Extract a usable URL from a Google Sheets ``=IMAGE(\"URL\")`` formula.

    The Sheets values API does not expose pixels from inserted image objects.
    Reading the formula view is safe and lets the import retain the original
    formatted values for all non-image fields.
    """
    formula = clean_text(value)
    if not formula:
        return None
    match = GOOGLE_SHEETS_IMAGE_FORMULA.match(formula)
    if not match:
        return None
    return normalise_image_url(match.group(1).replace('""', '"'))
