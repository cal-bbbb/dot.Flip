"""Read-only file/EXIF metadata panel shown under the file list."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QFormLayout, QLineEdit, QMenu, QVBoxLayout, QWidget

from ..core.formats import format_for_path
from .widgets import divider, panel_header, section_label

_GENERAL = [("name", "Name:"), ("type", "Type:"), ("author", "Author:"), ("creator", "Creator:"),
            ("date_created", "Date Created:"), ("date_modified", "Date Modified:")]
_FILE_DEPENDENT = [("dimensions", "Dimensions:"), ("zoom", "Zoom:"), ("aperture", "Aperture:"),
                   ("image_quality", "Image Quality:"), ("location", "Location:")]

_ARTIST_TAG = 0x013B
_MODEL_TAG = 0x0110
_MAKE_TAG = 0x010F
_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825
_FOCAL_LENGTH = 0x920A
_F_NUMBER = 0x829D
_DATETIME_ORIGINAL = 0x9003


def _fmt_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m/%d/%Y %H:%M:%S UTC")


def _fmt_exif_date(text: str) -> str | None:
    try:
        dt = datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    return dt.strftime("%m/%d/%Y %H:%M:%S UTC")


def _dms_to_degrees(dms) -> float:
    d, m, s = (float(x) for x in dms)
    return d + m / 60 + s / 3600


def _format_gps(gps: dict) -> str | None:
    try:
        lat, lat_ref = gps.get(2), gps.get(1)
        lon, lon_ref = gps.get(4), gps.get(3)
        if not lat or not lon:
            return None
        lat_deg = _dms_to_degrees(lat) * (1 if lat_ref == "N" else -1)
        lon_deg = _dms_to_degrees(lon) * (1 if lon_ref == "E" else -1)
        return f"{lat_deg:.5f}, {lon_deg:.5f}"
    except Exception:
        return None


def read_metadata(path: Path) -> dict:
    """Best-effort file and EXIF metadata; missing fields are simply absent, never fabricated."""
    info: dict = {"name": path.name}
    try:
        info["date_modified"] = _fmt_date(path.stat().st_mtime)
    except OSError:
        pass
    fmt = format_for_path(path)
    try:
        with Image.open(path) as img:
            profile = "ICC" if img.info.get("icc_profile") else "sRGB"
            label = fmt.label if fmt else (img.format or "")
            info["type"] = f"{label} ({profile})" if label else profile
            info["dimensions"] = f"{img.width} x {img.height} px"
            mp = img.width * img.height / 1_000_000
            info["image_quality"] = f"{mp:.0f}MP" if mp >= 10 else f"{mp:.1f}MP"

            exif = img.getexif()
            if not exif:
                return info
            artist = exif.get(_ARTIST_TAG)
            if artist:
                info["author"] = str(artist).strip()
            creator = exif.get(_MODEL_TAG) or exif.get(_MAKE_TAG)
            if creator:
                info["creator"] = str(creator).strip()

            exif_ifd = exif.get_ifd(_EXIF_IFD) if hasattr(exif, "get_ifd") else {}
            created = _fmt_exif_date(str(exif_ifd.get(_DATETIME_ORIGINAL, "")))
            if created:
                info["date_created"] = created
            focal = exif_ifd.get(_FOCAL_LENGTH)
            if focal:
                info["zoom"] = f"{float(focal):.0f}mm"
            fnum = exif_ifd.get(_F_NUMBER)
            if fnum:
                info["aperture"] = f"f/{float(fnum):.1f}"

            gps_ifd = exif.get_ifd(_GPS_IFD) if hasattr(exif, "get_ifd") else {}
            location = _format_gps(gps_ifd)
            if location:
                info["location"] = location
    except Exception:
        pass
    return info


class FileInfoPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(panel_header("File Info", QMenu()))

        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(10, 10, 10, 10)
        self._fields: dict[str, QLineEdit] = {}

        form.addRow(section_label("General"))
        for key, label in _GENERAL:
            self._fields[key] = self._add_field(form, label)
        form.addRow(divider())
        form.addRow(section_label("File-dependent"))
        for key, label in _FILE_DEPENDENT:
            self._fields[key] = self._add_field(form, label)

        lay.addWidget(body)

    def _add_field(self, form: QFormLayout, label: str) -> QLineEdit:
        w = QLineEdit()
        w.setReadOnly(True)
        w.setPlaceholderText("—")
        form.addRow(label, w)
        return w

    def set_path(self, path: Path | None) -> None:
        info = read_metadata(path) if path is not None else {}
        for key, field in self._fields.items():
            field.setText(info.get(key, ""))
