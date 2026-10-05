import re
from urllib.parse import urlparse
from urllib.parse import parse_qs


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
    if not is_http_url(url):
        return None
    parsed = urlparse(url)
    if parsed.netloc.lower().endswith("drive.google.com"):
        match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
        file_id = match.group(1) if match else parse_qs(parsed.query).get("id", [None])[0]
        if file_id:
            return f"https://drive.google.com/uc?export=view&id={file_id}"
    return url
