"""
fill_card.py
============
일본 외국인입국기록(출입국카드) 자동 텍스트 오버레이 유틸리티

기준 해상도 : 1654 × 2337 px  (A4 200 DPI — 실제 템플릿 크기)
좌표계      : 좌상단 원점, x→ 오른쪽, y↓ 아래
텍스트 색상 : 거의 검정 (15, 15, 60) — 진한 네이비

사용법:
    python fill_card.py                          # 예시 데이터로 실행
    python fill_card.py input.jpg output.png     # 이미지 직접 지정
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ── 기준 해상도 (A4 200 DPI = 실제 템플릿 크기) ──────────────
CANVAS_W = 1654
CANVAS_H = 2337

# ── 텍스트 색상 ────────────────────────────────────────────────
INK = (15, 15, 60)          # 진한 네이비 (인감·관공서 느낌)
CHECK_INK = (10, 10, 10)    # 체크 기호 — 순검정

# ── 기본 폰트 크기 ────────────────────────────────────────────
DEFAULT_FONT_SIZE = 28

# ── 예시 데이터 ────────────────────────────────────────────────
SAMPLE_DATA: dict = {
    # 인적 사항
    "family_name":  "KIM",
    "given_names":  "HYUNGKYOU",
    "dob_day":      "24",       # 두 자릿수
    "dob_month":    "11",
    "dob_year":     "1982",     # 네 자릿수

    # 주소 / 편명
    "country":      "KOREA",
    "city":         "BUSAN",
    "flight_no":    "BX143",
    "hotel_name":   "U-BELL HOTEL FUKUOKA",    # 길면 Auto-shrink 적용
    "hotel_tel":    "0927-61-0345",

    # 입국 목적 (tourism / business / relatives / others 중 하나)
    "purpose":      "tourism",

    # 체류 기간 / 하단 질문 — 모두 No
    "stay_duration": "3 DAYS",
}

# ══════════════════════════════════════════════════════════════
# 좌표 정의  (기준해상도 1494 × 2012 px)
# ══════════════════════════════════════════════════════════════
# 각 항목:  (x, y, width, height, align)
#   align: "left" | "center" | "right"
#   auto_shrink: True → 텍스트가 width를 넘으면 폰트 크기를 동적으로 줄임

FIELDS: dict[str, dict] = {

    # ── 인적 사항 ─────────────────────────────────────────────
    # 원본 좌표(1494×2012 기준)를 A4 200DPI(1654×2337)로 스케일: sx=1.107, sy=1.162
    "family_name": {
        "x": 177, "y": 128, "w": 465, "h": 64,
        "align": "left", "font_size": 31, "auto_shrink": True,
    },
    "given_names": {
        "x": 659, "y": 128, "w": 587, "h": 64,
        "align": "left", "font_size": 31, "auto_shrink": True,
    },

    # 생년월일
    "dob_day": {
        "x": 177, "y": 221, "w": 66,  "h": 58,
        "align": "center", "font_size": 30, "auto_shrink": False,
    },
    "dob_month": {
        "x": 260, "y": 221, "w": 66,  "h": 58,
        "align": "center", "font_size": 30, "auto_shrink": False,
    },
    "dob_year": {
        "x": 371, "y": 221, "w": 122, "h": 58,
        "align": "center", "font_size": 30, "auto_shrink": False,
        "letter_spacing": 4,
    },

    # ── 주소 / 편명 ───────────────────────────────────────────
    "country": {
        "x": 659, "y": 221, "w": 354, "h": 58,
        "align": "left", "font_size": 30, "auto_shrink": True,
    },
    "city": {
        "x": 1025, "y": 221, "w": 222, "h": 58,
        "align": "left", "font_size": 30, "auto_shrink": True,
    },
    "flight_no": {
        "x": 952, "y": 314, "w": 288, "h": 70,
        "align": "center", "font_size": 31, "auto_shrink": True,
    },
    "hotel_name": {
        "x": 177, "y": 410, "w": 753, "h": 64,
        "align": "left", "font_size": 30, "auto_shrink": True,
    },
    "hotel_tel": {
        "x": 941, "y": 410, "w": 299, "h": 64,
        "align": "left", "font_size": 30, "auto_shrink": True,
    },
    "stay_duration": {
        "x": 952, "y": 389, "w": 288, "h": 58,
        "align": "center", "font_size": 28, "auto_shrink": True,
    },
}

# 체크박스: (x, y) = 체크 기호를 배치할 칸의 정중앙
CHECKBOXES: dict[str, tuple[int, int]] = {
    "tourism":  (153, 332),
    "business": (319, 332),
    # 하단 질문 No 체크 — 3개 고정
    "no_q1": (1032, 701),
    "no_q2": (1032, 760),
    "no_q3": (1032, 827),
}

# ══════════════════════════════════════════════════════════════
# 폰트 로더
# ══════════════════════════════════════════════════════════════

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """
    Gothic 계열 폰트를 우선순위대로 시도.
    Windows: Noto Sans JP → MS Gothic → Meiryo → Yu Gothic → Arial
    Linux  : Noto Sans → DejaVu
    """
    candidates = [
        # Windows
        r"C:\Windows\Fonts\NotoSansJP-Regular.ttf",
        r"C:\Windows\Fonts\NotoSans-Regular.ttf",
        r"C:\Windows\Fonts\msgothic.ttc",
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\YuGothR.ttc",
        r"C:\Windows\Fonts\arial.ttf",
        # Linux / Streamlit Cloud
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # 최후 수단: PIL 기본 폰트 (크기 고정)
    return ImageFont.load_default()


# ══════════════════════════════════════════════════════════════
# 이미지 정규화
# ══════════════════════════════════════════════════════════════

def normalize_image(img: Image.Image) -> Image.Image:
    """
    입력 이미지를 기준 해상도(CANVAS_W × CANVAS_H)로 리사이즈.

    고급 사용 시 OpenCV 워핑 적용 가이드:
    ──────────────────────────────────────
    import cv2, numpy as np

    # 1) 소스 이미지에서 양식 4귀퉁이 좌표를 수동 or 자동으로 검출
    src_pts = np.float32([[x1,y1],[x2,y2],[x3,y3],[x4,y4]])

    # 2) 목표 해상도 귀퉁이 좌표
    dst_pts = np.float32([
        [0, 0],
        [CANVAS_W-1, 0],
        [CANVAS_W-1, CANVAS_H-1],
        [0, CANVAS_H-1],
    ])

    # 3) 원근 변환 행렬 계산 후 워핑
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(cv2_img, M, (CANVAS_W, CANVAS_H))
    ──────────────────────────────────────
    """
    if img.size == (CANVAS_W, CANVAS_H):
        return img.copy()

    return img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)


# ══════════════════════════════════════════════════════════════
# 텍스트 렌더링 헬퍼
# ══════════════════════════════════════════════════════════════

def _measure_text(draw: ImageDraw.ImageDraw, text: str,
                  font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    """텍스트 픽셀 크기 반환 (width, height)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit_font(draw: ImageDraw.ImageDraw, text: str,
              max_w: int, start_size: int,
              min_size: int = 10) -> ImageFont.FreeTypeFont:
    """
    Auto-shrink: 텍스트가 max_w를 초과하면 폰트 크기를 1px씩 줄임.
    min_size 이하로는 내려가지 않음.
    """
    size = start_size
    font = _load_font(size)
    while size > min_size:
        tw, _ = _measure_text(draw, text, font)
        if tw <= max_w:
            break
        size -= 1
        font = _load_font(size)
    return font


def _draw_text_in_cell(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int, y: int,
    w: int, h: int,
    align: str = "left",
    font_size: int = DEFAULT_FONT_SIZE,
    auto_shrink: bool = True,
    letter_spacing: int = 0,
    color: tuple = INK,
) -> None:
    """
    지정 셀(x, y, w, h) 안에 텍스트를 배치.

    Parameters
    ----------
    x, y    : 셀 좌상단 좌표 (기준해상도 px)
    w, h    : 셀 크기
    align   : "left" | "center" | "right"
    auto_shrink : True 이면 텍스트가 w를 초과할 때 폰트 축소
    letter_spacing : 글자 사이 추가 간격 (px). 0이면 기본값 사용.
    """
    if not text:
        return

    # 1) 폰트 결정
    if auto_shrink:
        font = _fit_font(draw, text, w, font_size)
    else:
        font = _load_font(font_size)

    # 2) 텍스트 크기 측정
    tw, th = _measure_text(draw, text, font)

    # 3) 수직 중앙 정렬 (셀 높이 기준)
    ty = y + (h - th) // 2

    # 4) 수평 정렬
    if align == "center":
        tx = x + (w - tw) // 2
    elif align == "right":
        tx = x + w - tw
    else:  # left
        tx = x

    # 5) 자간 처리가 필요한 경우 (letter_spacing > 0) → 글자 1자씩 배치
    if letter_spacing > 0:
        cx = tx
        for ch in text:
            draw.text((cx, ty), ch, font=font, fill=color)
            cw, _ = _measure_text(draw, ch, font)
            cx += cw + letter_spacing
    else:
        draw.text((tx, ty), text, font=font, fill=color)


def _draw_check(
    draw: ImageDraw.ImageDraw,
    cx: int, cy: int,
    size: int = 30,
    symbol: str = "✓",
) -> None:
    """
    체크 기호를 (cx, cy) 정중앙에 배치.
    symbol: "✓" (체크) 또는 "■" (속채움 박스)
    """
    font = _load_font(size)
    tw, th = _measure_text(draw, symbol, font)
    draw.text(
        (cx - tw // 2, cy - th // 2),
        symbol,
        font=font,
        fill=CHECK_INK,
    )


# ══════════════════════════════════════════════════════════════
# 메인 렌더러
# ══════════════════════════════════════════════════════════════

def fill_card(
    template_path: str | Path,
    data: dict,
    output_path: str | Path,
    whiten: bool = True,
) -> Image.Image:
    """
    출입국카드 템플릿에 data를 오버레이하여 output_path에 저장.

    Parameters
    ----------
    template_path : 배경 JPG/PNG 경로
    data          : SAMPLE_DATA 형식의 딕셔너리
    output_path   : 저장 경로 (.png 권장)
    whiten        : True → 밝은 배경 픽셀을 순백(255)으로 처리 (잉크 절약)
    """
    # ── 1. 이미지 로드 & 정규화 ────────────────────────────────
    img = Image.open(template_path).convert("RGB")
    img = normalize_image(img)

    # ── 2. 배경 흰색 처리 (선택) ───────────────────────────────
    if whiten:
        import numpy as np
        arr = np.array(img)
        gray = np.mean(arr, axis=2)
        mask = gray > 200                   # 밝은 픽셀
        arr[mask] = [255, 255, 255]
        img = Image.fromarray(arr.astype("uint8"))

    draw = ImageDraw.Draw(img)

    # ── 3. 인적 사항 텍스트 ────────────────────────────────────
    _draw_text_in_cell(draw, data.get("family_name", ""),
                       **FIELDS["family_name"])
    _draw_text_in_cell(draw, data.get("given_names", ""),
                       **FIELDS["given_names"])

    _draw_text_in_cell(draw, data.get("dob_day", ""),
                       **FIELDS["dob_day"])
    _draw_text_in_cell(draw, data.get("dob_month", ""),
                       **FIELDS["dob_month"])
    _draw_text_in_cell(draw, data.get("dob_year", ""),
                       **FIELDS["dob_year"])

    # ── 4. 주소 / 편명 텍스트 ─────────────────────────────────
    _draw_text_in_cell(draw, data.get("country", ""),
                       **FIELDS["country"])
    _draw_text_in_cell(draw, data.get("city", ""),
                       **FIELDS["city"])
    _draw_text_in_cell(draw, data.get("flight_no", ""),
                       **FIELDS["flight_no"])
    _draw_text_in_cell(draw, data.get("hotel_name", ""),
                       **FIELDS["hotel_name"])
    _draw_text_in_cell(draw, data.get("hotel_tel", ""),
                       **FIELDS["hotel_tel"])
    _draw_text_in_cell(draw, data.get("stay_duration", ""),
                       **FIELDS["stay_duration"])

    # ── 5. 입국 목적 체크박스 ──────────────────────────────────
    purpose = data.get("purpose", "tourism").lower()
    if purpose in ("tourism", "관광"):
        _draw_check(draw, *CHECKBOXES["tourism"])
    elif purpose in ("business", "상용"):
        _draw_check(draw, *CHECKBOXES["business"])
    # relatives / others 체크박스가 필요하면 CHECKBOXES 딕셔너리에 추가

    # ── 6. 하단 질문 No 체크 (3개 고정) ───────────────────────
    for key in ("no_q1", "no_q2", "no_q3"):
        _draw_check(draw, *CHECKBOXES[key])

    # ── 7. 저장 ────────────────────────────────────────────────
    img.save(str(output_path), format="PNG", optimize=False)
    print(f"[fill_card] saved: {output_path}  ({CANVAS_W}×{CANVAS_H}px = A4 200DPI)")
    return img


# ══════════════════════════════════════════════════════════════
# Streamlit 통합 헬퍼 (app.py에서 import해서 사용)
# ══════════════════════════════════════════════════════════════

def passenger_to_card_data(passenger: dict, common: dict) -> dict:
    """
    app.py의 passenger / common_info 딕셔너리를
    fill_card() 가 사용하는 data 딕셔너리로 변환.
    """
    name = passenger.get("영문이름", "")
    parts = name.split(" ", 1)
    family = parts[0] if parts else ""
    given  = parts[1] if len(parts) > 1 else ""

    dob = str(passenger.get("생년월일", ""))
    dob_d = dob[6:8] if len(dob) == 8 else ""
    dob_m = dob[4:6] if len(dob) == 8 else ""
    dob_y = dob[0:4] if len(dob) == 8 else ""

    purpose_raw = common.get("여행목적", "관광")
    purpose_map = {"관광": "tourism", "상용": "business",
                   "친족방문": "relatives", "기타": "others"}
    purpose = purpose_map.get(purpose_raw, "tourism")

    return {
        "family_name":   family,
        "given_names":   given,
        "dob_day":       dob_d,
        "dob_month":     dob_m,
        "dob_year":      dob_y,
        "country":       common.get("국적", "KOREA"),
        "city":          common.get("도시", ""),
        "flight_no":     common.get("입국편명", ""),
        "hotel_name":    common.get("호텔이름", ""),
        "hotel_tel":     common.get("호텔전화번호", ""),
        "stay_duration": common.get("여행기간", ""),
        "purpose":       purpose,
    }


# ══════════════════════════════════════════════════════════════
# CLI 진입점
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 기본 경로
    template = Path(__file__).parent / "templates" / "immigration_card.jpg"
    output   = Path(__file__).parent / "output" / "filled_sample.png"

    # 인자 오버라이드: python fill_card.py input.jpg output.png
    if len(sys.argv) >= 3:
        template = Path(sys.argv[1])
        output   = Path(sys.argv[2])
    elif len(sys.argv) == 2:
        template = Path(sys.argv[1])

    if not template.exists():
        print(f"[오류] 템플릿 파일을 찾을 수 없음: {template}")
        sys.exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)

    result = fill_card(template, SAMPLE_DATA, output)

    # 결과 미리보기 (선택 — 주석 해제 시 창 표시)
    # result.show()
