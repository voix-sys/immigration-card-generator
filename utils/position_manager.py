import json
import os
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "configs"


# ──────────────────────────────────────────────────────────────
# 기본 좌표 정의
# 좌표계: x, y = A4 포인트 기준 (좌상단 원점, 우/아래 방향 증가)
# A4 = 595 × 842 pt  (1pt ≈ 0.353mm)
#
# 이미지를 직접 보고 추정한 초기값 — UI 위치 보정으로 미세조정 가능
# ──────────────────────────────────────────────────────────────

DEFAULT_IMMIGRATION = {
    # ── 氏名 / Name ──────────────────────────────────────────
    "family_name": {
        "label": "성(Family Name)",
        "type": "text",
        "x": 168, "y": 62,
        "width": 175, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    "given_name": {
        "label": "이름(Given Names)",
        "type": "text",
        "x": 365, "y": 62,
        "width": 185, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    # ── 生年月日 / Date of Birth (split: D M Y 순서) ──────────
    # 칸 순서: Day(2) | Month(2) | Year(4)  → 왼쪽부터 입력
    "dob_split": {
        "label": "생년월일(DDMMYYYY split)",
        "type": "split_text",
        "x": 108, "y": 83,
        "cell_gap": 13.5,
        "font_size": 9
    },
    # ── 現住所 / Home Address ────────────────────────────────
    "country": {
        "label": "국명(Country name)",
        "type": "text",
        "x": 256, "y": 83,
        "width": 110, "height": 16,
        "font_size": 8,
        "align": "left"
    },
    "city": {
        "label": "도시명(City name)",
        "type": "text",
        "x": 392, "y": 83,
        "width": 150, "height": 16,
        "font_size": 8,
        "align": "left"
    },
    # ── 渡航目的 / Purpose of visit ─────────────────────────
    "purpose_tourism": {
        "label": "목적: 관광(Tourism) □",
        "type": "checkbox",
        "x": 110, "y": 108,
        "font_size": 10
    },
    "purpose_business": {
        "label": "목적: 상용(Business) □",
        "type": "checkbox",
        "x": 200, "y": 108,
        "font_size": 10
    },
    "purpose_relatives": {
        "label": "목적: 친족방문(Visiting relatives) □",
        "type": "checkbox",
        "x": 292, "y": 108,
        "font_size": 10
    },
    "purpose_others": {
        "label": "목적: 기타(Others) □",
        "type": "checkbox",
        "x": 110, "y": 126,
        "font_size": 10
    },
    # ── 航空機便名 / Flight No. ──────────────────────────────
    "flight_no": {
        "label": "항공편명(Flight No.)",
        "type": "text",
        "x": 402, "y": 103,
        "width": 148, "height": 15,
        "font_size": 9,
        "align": "left"
    },
    # ── 日本滞在予定期間 / Stay duration ──────────────────────
    "stay_duration": {
        "label": "체류예정기간(Stay duration)",
        "type": "text",
        "x": 402, "y": 120,
        "width": 148, "height": 15,
        "font_size": 9,
        "align": "left"
    },
    # ── 日本の連絡先 / Address in Japan ──────────────────────
    "hotel_name": {
        "label": "호텔명(Address in Japan)",
        "type": "text",
        "x": 110, "y": 150,
        "width": 240, "height": 14,
        "font_size": 8,
        "align": "left"
    },
    # ── TEL ──────────────────────────────────────────────────
    "hotel_tel": {
        "label": "전화번호(TEL)",
        "type": "text",
        "x": 385, "y": 150,
        "width": 165, "height": 14,
        "font_size": 9,
        "align": "left"
    },
}


DEFAULT_CUSTOMS = {
    # ── 탑승기명(선박명) / 출발지 ────────────────────────────
    "flight_no": {
        "label": "탑승기명(선박명)",
        "type": "text",
        "x": 108, "y": 97,
        "width": 195, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    "departure": {
        "label": "출발지",
        "type": "text",
        "x": 398, "y": 97,
        "width": 155, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    # ── 入国日자 (年/月/日) ──────────────────────────────────
    "entry_year": {
        "label": "입국연도(年)",
        "type": "text",
        "x": 168, "y": 121,
        "width": 45, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    "entry_month": {
        "label": "입국월(月)",
        "type": "text",
        "x": 270, "y": 121,
        "width": 28, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    "entry_day": {
        "label": "입국일(日)",
        "type": "text",
        "x": 348, "y": 121,
        "width": 28, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    # ── 성명(영문) ───────────────────────────────────────────
    "family_name": {
        "label": "성(Surname)",
        "type": "text",
        "x": 168, "y": 146,
        "width": 168, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    "given_name": {
        "label": "이름(Given Name)",
        "type": "text",
        "x": 396, "y": 146,
        "width": 158, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    # ── 현주소(일본내 체류지) ────────────────────────────────
    "hotel_address": {
        "label": "현주소(체류지)",
        "type": "text",
        "x": 108, "y": 170,
        "width": 445, "height": 16,
        "font_size": 8,
        "align": "left"
    },
    # ── 전화번호 ─────────────────────────────────────────────
    "hotel_tel": {
        "label": "전화번호",
        "type": "text",
        "x": 168, "y": 192,
        "width": 175, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    # ── 국적 / 직업 ──────────────────────────────────────────
    "nationality": {
        "label": "국적",
        "type": "text",
        "x": 168, "y": 214,
        "width": 128, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    "occupation": {
        "label": "직업",
        "type": "text",
        "x": 400, "y": 214,
        "width": 152, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    # ── 생년월일 (年/月/日) ──────────────────────────────────
    "dob_year": {
        "label": "생년(年)",
        "type": "text",
        "x": 168, "y": 238,
        "width": 45, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    "dob_month": {
        "label": "생월(月)",
        "type": "text",
        "x": 270, "y": 238,
        "width": 28, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    "dob_day": {
        "label": "생일(日)",
        "type": "text",
        "x": 348, "y": 238,
        "width": 28, "height": 16,
        "font_size": 9,
        "align": "left"
    },
    # ── 여권번호 ─────────────────────────────────────────────
    "passport_no": {
        "label": "여권번호",
        "type": "text",
        "x": 168, "y": 260,
        "width": 210, "height": 16,
        "font_size": 9,
        "align": "left"
    },
}


def get_config_path(form_type: str) -> Path:
    return CONFIG_DIR / f"{form_type}_positions.json"


def load_positions(form_type: str) -> dict:
    path = get_config_path(form_type)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return get_default_positions(form_type)


def save_positions(form_type: str, positions: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = get_config_path(form_type)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)


def get_default_positions(form_type: str) -> dict:
    if form_type == "immigration_card":
        return DEFAULT_IMMIGRATION
    elif form_type == "customs_declaration":
        return DEFAULT_CUSTOMS
    return {}


def init_default_configs() -> None:
    """configs 폴더에 기본 JSON 파일이 없으면 생성."""
    for form_type in ["immigration_card", "customs_declaration"]:
        path = get_config_path(form_type)
        if not path.exists():
            save_positions(form_type, get_default_positions(form_type))
