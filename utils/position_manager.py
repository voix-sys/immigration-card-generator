import json
import os
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "configs"

# ──────────────────────────────────────────────────────────────
# 좌표계: A4 포인트 기준, 좌상단 원점 (x→, y↓)
# A4 = 595 × 842 pt
#
# 이미지 분석 기준:
#   카드 상단 y ≈ 15pt, 하단 y ≈ 320pt
#   카드 좌  x ≈ 18pt, 우  x ≈ 577pt
#   좌측 레이블 열 너비 ≈ 98pt (x=18~116)
#   입력 영역 시작 x ≈ 118pt
#
# 행별 y 범위 (상단 기준):
#   Row0 헤더        : y=15~40
#   Row1 氏名/Name   : y=40~67  → 입력 y≈53
#   Row2 生年月日等  : y=67~93  → 입력 y≈79
#   Row3 渡航目的上  : y=93~123 → 입력 y≈107
#   Row4 渡航目的下  : y=123~140→ 입력 y≈128
#   Row5 連絡先/TEL  : y=140~163→ 입력 y≈151
# ──────────────────────────────────────────────────────────────

DEFAULT_IMMIGRATION = {
    # ── Row1: 氏名 / Name ──────────────────────────────────
    "family_name": {
        "label": "성(Family Name)",
        "type": "text",
        "x": 168, "y": 53,
        "width": 182, "height": 15,
        "font_size": 10,
        "align": "left"
    },
    "given_name": {
        "label": "이름(Given Names)",
        "type": "text",
        "x": 362, "y": 53,
        "width": 205, "height": 15,
        "font_size": 10,
        "align": "left"
    },

    # ── Row2: 生年月日 (DDMMYYYY, 한 글자씩) ───────────────
    # 카드 순서: Day(2자) · Month(2자) · Year(4자)
    # 각 칸 폭 ≈ 13pt, Day시작 x≈118, Month x≈150, Year x≈184
    "dob_split": {
        "label": "생년월일(DDMMYYYY 칸분리)",
        "type": "split_text",
        "x": 118, "y": 79,
        "cell_gap": 13.5,
        "font_size": 9
    },

    # ── Row2: 国名 Country name ────────────────────────────
    # 现住所(빈칸) 다음, 国名 헤더 뒤 입력 영역
    "country": {
        "label": "국명(Country name)",
        "type": "text",
        "x": 268, "y": 79,
        "width": 102, "height": 15,
        "font_size": 9,
        "align": "left"
    },

    # ── Row2: 都市名 City name ─────────────────────────────
    "city": {
        "label": "도시명(City name)",
        "type": "text",
        "x": 393, "y": 79,
        "width": 174, "height": 15,
        "font_size": 9,
        "align": "left"
    },

    # ── Row3: 渡航目的 체크박스 ────────────────────────────
    # □ 칸 안에 X 표시 — □ 위치에서 약간 오른쪽/아래
    "purpose_tourism": {
        "label": "목적: 관광(Tourism) □",
        "type": "checkbox",
        "x": 112, "y": 105,
        "font_size": 9
    },
    "purpose_business": {
        "label": "목적: 상용(Business) □",
        "type": "checkbox",
        "x": 203, "y": 105,
        "font_size": 9
    },
    "purpose_relatives": {
        "label": "목적: 친족(Visiting relatives) □",
        "type": "checkbox",
        "x": 296, "y": 105,
        "font_size": 9
    },
    "purpose_others": {
        "label": "목적: 기타(Others) □",
        "type": "checkbox",
        "x": 112, "y": 127,
        "font_size": 9
    },

    # ── Row3: 航空機便名 / Flight No. ──────────────────────
    "flight_no": {
        "label": "항공편명(Flight No.)",
        "type": "text",
        "x": 408, "y": 104,
        "width": 155, "height": 14,
        "font_size": 9,
        "align": "left"
    },

    # ── Row4: 日本滞在予定期間 / Stay duration ─────────────
    "stay_duration": {
        "label": "체류예정기간(Stay duration)",
        "type": "text",
        "x": 408, "y": 124,
        "width": 155, "height": 14,
        "font_size": 9,
        "align": "left"
    },

    # ── Row5: 日本の連絡先 / Address in Japan ──────────────
    "hotel_name": {
        "label": "호텔명(Address in Japan)",
        "type": "text",
        "x": 118, "y": 151,
        "width": 248, "height": 13,
        "font_size": 8,
        "align": "left"
    },

    # ── Row5: TEL ──────────────────────────────────────────
    "hotel_tel": {
        "label": "전화번호(TEL)",
        "type": "text",
        "x": 392, "y": 151,
        "width": 175, "height": 13,
        "font_size": 9,
        "align": "left"
    },
}


DEFAULT_CUSTOMS = {
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
    "hotel_address": {
        "label": "현주소(체류지)",
        "type": "text",
        "x": 108, "y": 170,
        "width": 445, "height": 16,
        "font_size": 8,
        "align": "left"
    },
    "hotel_tel": {
        "label": "전화번호",
        "type": "text",
        "x": 168, "y": 192,
        "width": 175, "height": 16,
        "font_size": 9,
        "align": "left"
    },
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
    for form_type in ["immigration_card", "customs_declaration"]:
        path = get_config_path(form_type)
        if not path.exists():
            save_positions(form_type, get_default_positions(form_type))
