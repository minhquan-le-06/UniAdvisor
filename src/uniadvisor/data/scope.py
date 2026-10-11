"""Scope rules: which schools are in Hà Nội / TP.HCM and which programs are taught there."""

from __future__ import annotations

import re
import unicodedata

from uniadvisor.data.text import fold, nfc


def strip_accents(text: str) -> str:
    """'Thanh Hoá' -> 'thanh hoa' (so tone-mark placement variants match)."""
    text = unicodedata.normalize("NFD", nfc(text).lower().replace("đ", "d"))
    return re.sub(r"\s+", " ", "".join(c for c in text if unicodedata.category(c) != "Mn")).strip()


# The 63 provinces before the 2025 merger, the post-merger names, and common campus city names.
# Used only to recognise a place named in a program or school name; no merger mapping is applied here.
PLACES = [
    "An Giang", "Bà Rịa", "Vũng Tàu", "Bắc Giang", "Bắc Kạn", "Bạc Liêu", "Bắc Ninh", "Bến Tre", "Bình Định",
    "Bình Dương", "Bình Phước", "Bình Thuận", "Cà Mau", "Cần Thơ", "Cao Bằng", "Đà Nẵng", "Đắk Lắk", "Đắk Nông",
    "Điện Biên", "Đồng Nai", "Đồng Tháp", "Gia Lai", "Hà Giang", "Hà Nam", "Hà Tĩnh", "Hải Dương", "Hải Phòng",
    "Hậu Giang", "Hòa Bình", "Hưng Yên", "Khánh Hòa", "Kiên Giang", "Kon Tum", "Lai Châu", "Lâm Đồng",
    "Lạng Sơn", "Lào Cai", "Long An", "Nam Định", "Nghệ An", "Ninh Bình", "Ninh Thuận", "Phú Thọ", "Phú Yên",
    "Quảng Bình", "Quảng Nam", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị", "Sóc Trăng", "Sơn La", "Tây Ninh",
    "Thái Bình", "Thái Nguyên", "Thanh Hóa", "Huế", "Tiền Giang", "Trà Vinh", "Tuyên Quang", "Vĩnh Long",
    "Vĩnh Phúc", "Yên Bái", "Vinh", "Nha Trang", "Đà Lạt", "Buôn Ma Thuột", "Quy Nhơn", "Pleiku", "Thủ Dầu Một",
]
_PLACE_RE = re.compile(r"\b(" + "|".join(re.escape(strip_accents(p)) for p in PLACES) + r")\b")

_HN_RE = re.compile(r"\bha noi\b|\bhn\b")
_HCM_RE = re.compile(r"\bho chi minh\b|\btp\.?\s?hcm\b|\btphcm\b|\bhcm\b|\bsai gon\b")
# Former provinces merged into TP.HCM in 2025 (Nghị quyết 202/2025/QH15) and their main towns.
# ("Thuận An" is left out: Hà Nội has a commune of that name too.)
_FORMER_HCM_RE = re.compile(r"\bbinh duong\b|\bba ria\b|\bvung tau\b|\bthu dau mot\b|\bdi an\b")
# Matched on accented lowercase text: without accents "tại" (at) collides with "tài" (tài chính).
_CAMPUS_RE = re.compile(r"phân hiệu|cơ sở(?!\s+(?:dữ liệu|hạ tầng|vật chất))|\btại\b|campus")


def city_from_address(address: str) -> tuple[str | None, str]:
    """(city, basis) from a postal address.

    The city named last wins ('Xa lộ Hà Nội, ..., TP.HCM' -> HCM). An address in TP.HCM or naming no city that
    names a former province merged into TP.HCM gives 'HCM_FORMER'.
    """
    text = strip_accents(address)
    if not text:
        return None, "no_address"
    last = {}
    for city, pattern in (("HN", _HN_RE), ("HCM", _HCM_RE)):
        hits = [m.start() for m in pattern.finditer(text)]
        if hits:
            last[city] = hits[-1]
    city = max(last, key=last.get) if last else None
    if city != "HN" and _FORMER_HCM_RE.search(text):
        return "HCM_FORMER", "address_former_province"
    if city:
        return city, "address"
    if _PLACE_RE.search(text):
        return None, "address_other_province"
    return None, "address_without_place"


def province_to_city(province: str) -> str | None:
    text = strip_accents(province)
    if _HN_RE.search(text):
        return "HN"
    if _HCM_RE.search(text):
        return "HCM"
    return None


def decide_school_city(address: str, province: str) -> tuple[str | None, str]:
    """City of a school's main site. The address is preferred: the export's province field is unreliable
    (125 schools carry 'Đồng Nai', many of them elsewhere). When the address is missing or names no place,
    the province field is used, and the school is listed for review."""
    city, basis = city_from_address(address)
    if basis in ("no_address", "address_without_place"):
        return province_to_city(province), "province_field"
    return city, basis


def campus_place(name: str) -> tuple[str, str | None]:
    """Classify a program or school name that may name a campus.

    Returns ('none', None) when no campus is named, ('outside', place) when it names a campus outside
    Hà Nội / TP.HCM, ('inside', 'HN' | 'HCM') when the campus named is in one of them, ('unclear', None) when
    campus words appear without a recognised place.
    """
    if not _CAMPUS_RE.search(fold(name)):
        return "none", None
    text = strip_accents(name)
    for m in _PLACE_RE.finditer(text):
        return "outside", m.group(1)
    if _FORMER_HCM_RE.search(text):
        return "outside", "former_hcm_province"
    hn, hcm = _HN_RE.search(text), _HCM_RE.search(text)
    if hn and not hcm:
        return "inside", "HN"
    if hcm and not hn:
        return "inside", "HCM"
    return "unclear", None
