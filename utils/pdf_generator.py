"""
PDF 생성 모듈
- JPG 템플릿 위에 reportlab으로 텍스트 오버레이
- 배경은 흰색(잉크 절약), 텍스트는 검정
"""
from __future__ import annotations

import io
import os
import tempfile
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PAGE_W, PAGE_H = A4  # 595.28, 841.89


# ── 폰트 등록 ──────────────────────────────────────────────────
def _register_fonts():
    candidates = [
        ("Arial", r"C:\Windows\Fonts\arial.ttf"),
        ("ArialBold", r"C:\Windows\Fonts\arialbd.ttf"),
    ]
    registered = []
    for name, path in candidates:
        try:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(name, path))
                registered.append(name)
        except Exception:
            pass
    return registered


_REGISTERED = _register_fonts()
_DEFAULT_FONT = "Arial" if "Arial" in _REGISTERED else "Helvetica"


# ── 배경 처리 ──────────────────────────────────────────────────

def _whiten_background(jpg_path: str, threshold: int = 200) -> str:
    """
    JPG 템플릿에서 밝은 배경 픽셀을 순백으로 변환.
    선/글자(어두운 픽셀)는 그대로 유지 → 잉크 절약.
    임시 PNG 경로 반환.
    """
    img = Image.open(jpg_path).convert("RGB")
    gray = img.convert("L")

    pixels = img.load()
    gray_pixels = gray.load()
    w, h = img.size

    for y in range(h):
        for x in range(w):
            if gray_pixels[x, y] > threshold:
                pixels[x, y] = (255, 255, 255)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(tmp.name, format="PNG")
    tmp.close()
    return tmp.name


def _prepare_template(jpg_path: Optional[str], whiten: bool = True) -> Optional[str]:
    """템플릿 준비. whiten=True이면 배경 흰색 처리."""
    if not jpg_path or not os.path.exists(jpg_path):
        return None
    if whiten:
        return _whiten_background(jpg_path)
    return jpg_path


# ── reportlab 내부 유틸 ────────────────────────────────────────

def _rl_y(y_from_top: float, font_size: float = 10) -> float:
    return PAGE_H - y_from_top - font_size


def _fit_font_size(c: canvas.Canvas, text: str, font: str,
                   font_size: float, max_width: float) -> float:
    if max_width <= 0:
        return font_size
    while font_size > 5:
        if c.stringWidth(text, font, font_size) <= max_width:
            break
        font_size -= 0.5
    return font_size


def _draw_text(c: canvas.Canvas, text: str, pos: dict, warn_fields: list) -> None:
    font_size = float(pos.get("font_size", 9))
    max_w = float(pos.get("width", 0))
    x = float(pos["x"])
    y_top = float(pos["y"])

    fitted = _fit_font_size(c, text, _DEFAULT_FONT, font_size, max_w)
    if fitted < font_size - 1:
        warn_fields.append(pos.get("label", "?"))

    c.setFont(_DEFAULT_FONT, fitted)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(x, _rl_y(y_top, fitted), text)


def _draw_split_text(c: canvas.Canvas, text: str, pos: dict) -> None:
    x = float(pos["x"])
    y_top = float(pos["y"])
    cell_gap = float(pos.get("cell_gap", 13.5))
    font_size = float(pos.get("font_size", 9))

    c.setFont(_DEFAULT_FONT, font_size)
    c.setFillColorRGB(0, 0, 0)
    for i, ch in enumerate(text):
        c.drawString(x + i * cell_gap, _rl_y(y_top, font_size), ch)


def _draw_checkbox(c: canvas.Canvas, checked: bool, pos: dict) -> None:
    if not checked:
        return
    x = float(pos["x"])
    y_top = float(pos["y"])
    font_size = float(pos.get("font_size", 10))
    c.setFont(_DEFAULT_FONT, font_size)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(x, _rl_y(y_top, font_size), "X")


# ── 데이터 → 필드값 매핑 ─────────────────────────────────────

def _build_immigration_fields(passenger: dict, common: dict) -> dict:
    name = passenger.get("영문이름", "")
    parts = name.split(" ", 1)
    family = parts[0] if parts else ""
    given = parts[1] if len(parts) > 1 else ""

    dob = str(passenger.get("생년월일", ""))
    dob_d = dob[6:8] if len(dob) == 8 else ""
    dob_m = dob[4:6] if len(dob) == 8 else ""
    dob_y = dob[0:4] if len(dob) == 8 else ""

    purpose = common.get("여행목적", "관광")

    return {
        "family_name": family,
        "given_name": given,
        "dob_day":   dob_d,
        "dob_month": dob_m,
        "dob_year":  dob_y,
        "country": common.get("국적", ""),
        "city": common.get("도시", ""),
        "purpose_tourism":   purpose in ["관광", "Tourism", "tourism", ""],
        "purpose_business":  purpose in ["상용", "Business", "business"],
        "purpose_relatives": purpose in ["친족", "Visiting relatives"],
        "purpose_others":    purpose in ["기타", "Others"],
        "flight_no":     common.get("입국편명", ""),
        "stay_duration": common.get("여행기간", ""),
        "hotel_name":    common.get("호텔이름", ""),
        "hotel_tel":     common.get("호텔전화번호", ""),
    }


def _build_customs_fields(passenger: dict, common: dict) -> dict:
    name = passenger.get("영문이름", "")
    parts = name.split(" ", 1)
    family = parts[0] if parts else ""
    given = parts[1] if len(parts) > 1 else ""

    dob = str(passenger.get("생년월일", ""))
    dob_y = dob[0:4] if len(dob) == 8 else ""
    dob_m = dob[4:6] if len(dob) == 8 else ""
    dob_d = dob[6:8] if len(dob) == 8 else ""

    entry_raw = str(common.get("입국일", "")).replace("-", "")
    ey = entry_raw[0:4] if len(entry_raw) >= 8 else ""
    em = entry_raw[4:6] if len(entry_raw) >= 6 else ""
    ed = entry_raw[6:8] if len(entry_raw) >= 8 else ""

    hotel = common.get("호텔이름", "")
    city = common.get("도시", "")
    hotel_address = f"{hotel} ({city})" if city else hotel

    return {
        "flight_no":     common.get("입국편명", ""),
        "departure":     common.get("도시", ""),
        "entry_year":    ey,
        "entry_month":   em,
        "entry_day":     ed,
        "family_name":   family,
        "given_name":    given,
        "hotel_address": hotel_address,
        "hotel_tel":     common.get("호텔전화번호", ""),
        "nationality":   common.get("국적", ""),
        "occupation":    "COMPANY EMPLOYEE",
        "dob_year":      dob_y,
        "dob_month":     dob_m,
        "dob_day":       dob_d,
        "passport_no":   passenger.get("여권번호", ""),
    }


# ── 단일 페이지 렌더링 ─────────────────────────────────────────

def _add_page(c: canvas.Canvas, template_path: Optional[str],
              fields: dict, positions: dict) -> list:
    warn_fields = []

    # 흰 배경 먼저
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # 템플릿 이미지 (배경 흰색 처리 후)
    cleaned_tmp = None
    if template_path and os.path.exists(template_path):
        cleaned_tmp = _whiten_background(template_path)
        c.drawImage(ImageReader(cleaned_tmp),
                    0, 0, width=PAGE_W, height=PAGE_H,
                    preserveAspectRatio=False)

    c.setFillColorRGB(0, 0, 0)

    # 필드 출력
    for key, pos in positions.items():
        value = fields.get(key)
        if value is None:
            continue
        ftype = pos.get("type", "text")
        if ftype == "text":
            text = str(value)
            if text:
                _draw_text(c, text, pos, warn_fields)
        elif ftype == "split_text":
            text = str(value)
            if text:
                _draw_split_text(c, text, pos)
        elif ftype == "checkbox":
            _draw_checkbox(c, bool(value), pos)

    if cleaned_tmp and os.path.exists(cleaned_tmp):
        os.unlink(cleaned_tmp)

    return warn_fields


# ── 공개 API ──────────────────────────────────────────────────

def generate_single_pdf(
    form_type: str,
    passenger: dict,
    common: dict,
    positions: dict,
    template_path: Optional[str],
    output_path: str,
) -> list:
    if form_type == "immigration_card":
        fields = _build_immigration_fields(passenger, common)
    else:
        fields = _build_customs_fields(passenger, common)

    c = canvas.Canvas(output_path, pagesize=(PAGE_W, PAGE_H))
    warns = _add_page(c, template_path, fields, positions)
    c.save()
    return warns


def generate_combined_pdf(
    passengers: list,
    common: dict,
    imm_positions: dict,
    cus_positions: dict,
    imm_template: Optional[str],
    cus_template: Optional[str],
    output_path: str,
    include_immigration: bool = True,
    include_customs: bool = True,
) -> dict:
    c = canvas.Canvas(output_path, pagesize=(PAGE_W, PAGE_H))
    all_warns = []

    for p in passengers:
        if include_immigration:
            fields = _build_immigration_fields(p, common)
            w = _add_page(c, imm_template, fields, imm_positions)
            all_warns.extend(w)
            c.showPage()
        if include_customs:
            fields = _build_customs_fields(p, common)
            w = _add_page(c, cus_template, fields, cus_positions)
            all_warns.extend(w)
            c.showPage()

    c.save()
    return {"warns": all_warns, "count": len(passengers)}


# ── 미리보기 이미지 (PIL) ──────────────────────────────────────

def generate_preview_image(
    form_type: str,
    passenger: dict,
    common: dict,
    positions: dict,
    template_path: Optional[str],
    scale: float = 1.0,
) -> Image.Image:
    REF_PX_W = 1240
    REF_PX_H = 1754

    if template_path and os.path.exists(template_path):
        img = Image.open(template_path).convert("RGB")
        # 배경 흰색 처리
        gray = img.convert("L")
        pixels = img.load()
        gp = gray.load()
        w, h = img.size
        for y in range(h):
            for x in range(w):
                if gp[x, y] > 200:
                    pixels[x, y] = (255, 255, 255)
        img_w, img_h = img.size
    else:
        img = Image.new("RGB", (REF_PX_W, REF_PX_H), (255, 255, 255))
        img_w, img_h = REF_PX_W, REF_PX_H

    sx = img_w / PAGE_W
    sy = img_h / PAGE_H
    draw = ImageDraw.Draw(img)

    # 폰트 로드
    font_paths = [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    def _load_font(size):
        for fp in font_paths:
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
        return ImageFont.load_default()

    if form_type == "immigration_card":
        fields = _build_immigration_fields(passenger, common)
    else:
        fields = _build_customs_fields(passenger, common)

    BLACK = (0, 0, 0)
    RED   = (200, 0, 0)

    for key, pos in positions.items():
        value = fields.get(key)
        if value is None:
            continue

        ftype = pos.get("type", "text")
        x_pt  = float(pos["x"])
        y_pt  = float(pos["y"])
        fs_pt = float(pos.get("font_size", 9))

        x_px  = x_pt * sx
        y_px  = y_pt * sy
        fs_px = max(8, int(fs_pt * sy * 0.95))
        font  = _load_font(fs_px)

        if ftype == "text":
            text = str(value) if value else ""
            if not text:
                continue
            max_w = float(pos.get("width", 0)) * sx
            try:
                tw = draw.textlength(text, font=font)
            except Exception:
                tw = fs_px * len(text) * 0.6
            color = RED if (max_w > 0 and tw > max_w * 1.05) else BLACK
            draw.text((x_px, y_px), text, fill=color, font=font)

        elif ftype == "split_text":
            text = str(value) if value else ""
            if not text:
                continue
            cell_gap_px = float(pos.get("cell_gap", 13.5)) * sx
            for i, ch in enumerate(text):
                draw.text((x_px + i * cell_gap_px, y_px), ch, fill=BLACK, font=font)

        elif ftype == "checkbox":
            if value:
                draw.text((x_px, y_px), "X", fill=BLACK, font=font)

    if scale != 1.0:
        img = img.resize((int(img_w * scale), int(img_h * scale)), Image.LANCZOS)

    return img
