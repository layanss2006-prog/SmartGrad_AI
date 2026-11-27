from pathlib import Path
from zipfile import ZipFile, BadZipFile
from django.core.exceptions import ValidationError
from django.utils.translation import get_language

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".csv", ".txt", ".png", ".jpg", ".jpeg",
}

def validate_submission_file(upload):
    name = Path(upload.name).name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS or name.startswith("."):
        raise ValidationError("نوع الملف غير مسموح." if get_language() == "ar" else "This file type is not allowed.")
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError("الحد الأقصى لحجم الملف 10 ميجابايت." if get_language() == "ar" else "Maximum file size is 10 MB.")

    head = upload.read(16)
    upload.seek(0)
    signatures = {
        ".pdf": head.startswith(b"%PDF-"),
        ".png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": head.startswith(b"\xff\xd8\xff"),
        ".jpeg": head.startswith(b"\xff\xd8\xff"),
    }
    if suffix in signatures and not signatures[suffix]:
        raise ValidationError("محتوى الملف لا يطابق امتداده." if get_language() == "ar" else "File content does not match its extension.")
    if suffix in {".docx", ".xlsx", ".pptx"}:
        try:
            with ZipFile(upload) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names:
                    raise ValidationError("ملف Office غير صالح." if get_language() == "ar" else "Invalid Office document.")
        except (BadZipFile, OSError):
            raise ValidationError("ملف Office غير صالح." if get_language() == "ar" else "Invalid Office document.")
        finally:
            upload.seek(0)
    if suffix in {".doc", ".xls", ".ppt"} and not head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise ValidationError("محتوى الملف لا يطابق امتداده." if get_language() == "ar" else "File content does not match its extension.")
    if suffix in {".txt", ".csv"} and (b"\x00" in head):
        raise ValidationError("ملف نصي غير صالح." if get_language() == "ar" else "Invalid text file.")
