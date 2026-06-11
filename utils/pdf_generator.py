"""
PDF 생성 모듈
- JPG 템플릿 위에 reportlab으로 텍스트 오버레이
- 또는 템플릿 없이 빈 A4 페이지에 출력
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# A4 포인트 크기
PAGE_W, PAGE_H = A4  # 595.28, 841.89

# 좌표 기준 참조 크기 (pt) — JSON 좌표 그대로 사용
REF_W = PAGE_W
REF_H = PAGE_H


# ── 폰트 등록 ─────────────────────────────────────────────────
def _register_fonts():
    """시스템 폰트 등록 시도. 실패 시 Helvetica 사용."""
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


# ── 내부 유틸 ─────────────────────────────────────────────────

def _rl_y(y_from_top: float, font_size: float = 10) -> float:
    """JSON 좌표(상단 기준 y) → reportlab 좌표(하단 기준 y)"""
    return PAGE_H - y_from_top - font_size


def _fit_font_size(c: canvas.Canvas, text: str, font: str,
                   font_size: float, max_width: float) -> float:
    """텍스트가 max_width를 넘으면 font_size를 줄여 반환."""
    if max_width <= 0:
        return font_size
    while font_size > 5:
        if c.stringWidth(text, font, font_size) <= max_width:
            break
        font_size -= 0.5
    return font_size


def _draw_text(c: canvas.Canvas, text: str, pos: dict,
               warn_fields: list) -> None:
    font_size = float(pos.get("font_size", 9))
    max_w = float(pos.get("width", 0))
    x = float(pos["x"])
    y_top = float(pos["y"])

    fitted = _fit_font_size(c, text, _DEFAULT_FONT, font_size, max_w)
    if fitted < font_size - 1:
        warn_fields.append(pos.get("label", "?"))

    c.setFont(_DEFAULT_FONT, fitted)
    c.drawString(x, _rl_y(y_top, fitted), text)


def _draw_split_text(c: canvas.Canvas, text: str, pos: dict) -> None:
    """한 글자씩 cell_gap 간격으로 출력."""
    x = float(pos["x"])
    y_top = float(pos["y"])
    cell_gap = float(pos.get("cell_gap", 13.5))
    font_size = float(pos.get("font_size", 9))

    c.setFont(_DEFAULT_FONT, font_size)
    for i, ch in enumerate(text):
        c.drawString(x + i * cell_gap, _rl_y(y_top, font_size), ch)


def _draw_checkbox(c: canvas.Canvas, checked: bool, pos: dict) -> None:
    if not checked:
        return
    x = float(pos["x"])
    y_top = float(pos["y"])
    font_size = float(pos.get("font_size", 10))
    mark = pos.get("mark", "X")
    c.setFont(_DEFAULT_FONT, font_size)
    c.drawString(x, _rl_y(y_top, font_size), mark)


# ── 데이터 → 필드값 매핑 ─────────────────────────────────────

def _build_immigration_fields(passenger: dict, common: dict) -> dict:
    """출입국카드 필드값 딕셔너리 구성."""
    name = passenger.get("영문이름", "")
    parts = name.split(" ", 1)
    family = parts[0] if parts else ""
    given = parts[1] if len(parts) > 1 else ""

    dob = str(passenger.get("생년월일", ""))  # YYYYMMDD
    # 카드 순서: Day Month Year
    dob_dmyyyy = ""
    if len(dob) == 8:
        dob_dmyyyy = dob[6:8] + dob[4:6] + dob[0:4]  # DDMMYYYY

    gender = passenger.get("성별", "M")
    purpose = common.get("여행목적", "관광")

    entry_date = str(common.get("입국일", ""))  # YYYY-MM-DD or YYYYMMDD
    entry_date = entry_date.replace("-", "")

    return {
        "family_name": family,
        "given_name": given,
        "dob_split": dob_dmyyyy,       # DDMMYYYY 순
        "country": common.get("국적", ""),
        "city": common.get("도시", ""),
        "purpose_tourism":   purpose in ["관광", "Tourism", "tourism", ""],
        "purpose_business":  purpose in ["상용", "Business", "business"],
        "purpose_relatives": purpose in ["친족", "Visiting relatives"],
        "purpose_others":    purpose in ["기타", "Others"],
        "flight_no":    common.get("입국편명", ""),
        "stay_duration": common.get("여행기간", ""),
        "hotel_name":   common.get("호텔이름", ""),
        "hotel_tel":    common.get("호텔전화번호", ""),
    }


def _build_customs_fields(passenger: dict, common: dict) -> dict:
    """휴대품신고서 필드값 딕셔너리 구성."""
    name = passenger.get("영문이름", "")
    parts = name.split(" ", 1)
    family = parts[0] if parts else ""
    given = parts[1] if len(parts) > 1 else ""

    dob = str(passenger.get("생년월일", ""))  # YYYYMMDD
    dob_y = dob[0:4] if len(dob) == 8 else ""
    dob_m = dob[4:6] if len(dob) == 8 else ""
    dob_d = dob[6:8] if len(dob) == 8 else ""

    entry_raw = str(common.get("입국일", "")).replace("-", "")
    ey = entry_raw[0:4] if len(entry_raw) >= 8 else entry_raw[:4] if len(entry_raw) >= 4 else ""
    em = entry_raw[4:6] if len(entry_raw) >= 6 else ""
    ed = entry_raw[6:8] if len(entry_raw) >= 8 else ""

    hotel = common.get("호텔이름", "")
    city = common.get("도시", "")
    hotel_address = f"{hotel} ({city})" if city else hotel

    return {
        "flight_no":    common.get("입국편명", ""),
        "departure":    common.get("도시", ""),
        "entry_year":   ey,
        "entry_month":  em,
        "entry_day":    ed,
        "family_name":  family,
        "given_name":   given,
        "hotel_address": hotel_address,
        "hotel_tel":    common.get("호텔전화번호", ""),
        "nationality":  common.get("국적", ""),
        "occupation":   "COMPANY EMPLOYEE",
        "dob_year":     dob_y,
        "dob_month":    dob_m,
        "dob_day":      dob_d,
        "passport_no":  passenger.get("여권번호", ""),
    }


# ── 단일 페이지 PDF 생성 ────────────────────────────────────

def _add_page(c: canvas.Canvas, template_path: Optional[str],
              fields: dict, positions: dict) -> list:
    """
    캔버스에 한 페이지 추가.
    반환: 경고 필드 목록
    """
    warn_fields = []

    # 배경 이미지
    if template_path and os.path.exists(template_path):
        c.drawImage(ImageReader(template_path),
                    0, 0, width=PAGE_W, height=PAGE_H,
                    preserveAspectRatio=False)
    else:
        # 템플릿 없음 → 흰 배경만 (텍스트 없음)
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1)
        c.setFillColorRGB(0, 0, 0)

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

    return warn_fields


# ── 공개 API ─────────────────────────────────────────────────

def generate_single_pdf(
    form_type: str,
    passenger: dict,
    common: dict,
    positions: dict,
    template_path: Optional[str],
    output_path: str,
) -> list:
    """단일 승객 단일 양식 PDF 생성. 경고 목록 반환."""
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
    """
    여러 승객 통합 PDF 생성.
    반환: {"warns": [...], "count": N}
    """
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


# ── 미리보기 이미지 생성 (PIL) ────────────────────────────────

def generate_preview_image(
    form_type: str,
    passenger: dict,
    common: dict,
    positions: dict,
    template_path: Optional[str],
    scale: float = 1.0,
) -> Image.Image:
    """
    PIL Image로 미리보기 생성.
    template_path: JPG 경로 (없으면 빈 흰 이미지)
    scale: 확대/축소 배율
    """
    # 참조 크기 (A4 @ 150dpi)
    REF_PX_W = 1240
    REF_PX_H = 1754

    if template_path and os.path.exists(template_path):
        img = Image.open(template_path).convert("RGB")
        img_w, img_h = img.size
    else:
        img = Image.new("RGB", (REF_PX_W, REF_PX_H), (240, 240, 240))
        img_w, img_h = REF_PX_W, REF_PX_H

    # pt → px 변환 비율
    sx = img_w / PAGE_W
    sy = img_h / PAGE_H

    draw = ImageDraw.Draw(img)

    try:
        font_base = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 14)
    except Exception:
        font_base = ImageFont.load_default()

    if form_type == "immigration_card":
        fields = _build_immigration_fields(passenger, common)
    else:
        fields = _build_customs_fields(passenger, common)

    for key, pos in positions.items():
        value = fields.get(key)
        if value is None:
            continue

        ftype = pos.get("type", "text")
        x_pt = float(pos["x"])
        y_pt = float(pos["y"])
        fs_pt = float(pos.get("font_size", 9))

        # pt → px
        x_px = x_pt * sx
        y_px = y_pt * sy
        fs_px = max(8, int(fs_pt * sy * 0.95))

        try:
            font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", fs_px)
        except Exception:
            font = font_base

        if ftype == "text":
            text = str(value) if value else ""
            if not text:
                continue
            max_w = float(pos.get("width", 0)) * sx
            tw = draw.textlength(text, font=font) if hasattr(draw, "textlength") else fs_px * len(text) * 0.6
            color = (200, 0, 0) if (max_w > 0 and tw > max_w * 1.05) else (0, 0, 180)
            draw.text((x_px, y_px), text, fill=color, font=font)

        elif ftype == "split_text":
            text = str(value) if value else ""
            if not text:
                continue
            cell_gap_px = float(pos.get("cell_gap", 13.5)) * sx
            for i, ch in enumerate(text):
                draw.text((x_px + i * cell_gap_px, y_px), ch,
                          fill=(0, 0, 180), font=font)

        elif ftype == "checkbox":
            if value:
                draw.text((x_px, y_px), "X", fill=(0, 0, 180), font=font)

    # 스케일 적용
    if scale != 1.0:
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img
