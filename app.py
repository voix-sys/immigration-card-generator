"""
immigration-card-generator
일본 입국 서류 자동 출력 프로그램 — 클라우드 버전
"""
import base64
import io
import os
import tempfile
import zipfile
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.data_cleaner import clean_passenger
from utils.validator import validate_all, validate_passenger
from utils.position_manager import (
    load_positions, save_positions, init_default_configs,
)
from utils.pdf_generator import (
    generate_single_pdf, generate_combined_pdf, generate_preview_image,
)

# ── 초기화 ─────────────────────────────────────────────────────
init_default_configs()

st.set_page_config(
    page_title="일본 입국서류 자동출력",
    page_icon="✈",
    layout="wide",
)

# ── 호텔 프리셋 ────────────────────────────────────────────────
HOTEL_PRESETS = [
    {"name": "직접입력", "hotel": "", "tel": ""},
    {"name": "후쿠오카", "hotel": "U-BELL HOTEL", "tel": "0927-61-0345"},
    {"name": "대마도", "hotel": "SOAR RESORT", "tel": "0920-54-8802"},
    {"name": "후쿠오카(벳부)", "hotel": "BEPPU SUGINOI HOTEL", "tel": "0977-24-1141"},
]

# ── 세션 상태 초기화 ───────────────────────────────────────────
def _init_state():
    defaults = {
        "common_info": {
            "국적": "KOREA",
            "도시": "",
            "입국편명": "",
            "여행기간": "7 DAYS",
            "입국일": str(date.today()),
            "호텔이름": "",
            "호텔전화번호": "",
            "여행목적": "관광",
        },
        "passengers": [],
        "cleaned_passengers": [],
        "imm_jpg_bytes": None,
        "cus_jpg_bytes": None,
        "imm_positions": None,
        "cus_positions": None,
        "hotel_presets": HOTEL_PRESETS,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def _get_positions(form_type: str) -> dict:
    key = "imm_positions" if form_type == "immigration_card" else "cus_positions"
    if st.session_state[key] is None:
        st.session_state[key] = load_positions(form_type)
    return st.session_state[key]


def _save_session_positions(form_type: str, positions: dict):
    key = "imm_positions" if form_type == "immigration_card" else "cus_positions"
    st.session_state[key] = positions
    save_positions(form_type, positions)


def _write_jpg_to_tmp(jpg_bytes: bytes, suffix: str = ".jpg") -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(jpg_bytes)
    tmp.close()
    return tmp.name


def _img_to_base64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode()


def _build_print_html(images_b64: list[str], title: str = "") -> str:
    """인쇄용 HTML 생성 — 각 이미지를 A4 한 페이지씩"""
    imgs_html = "".join(
        f'<div class="page"><img src="data:image/jpeg;base64,{b64}" /></div>'
        for b64 in images_b64
    )
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #f0f0f0; font-family: sans-serif; }}
  .toolbar {{
    position: fixed; top: 0; left: 0; right: 0;
    background: #1f4e79; color: white;
    padding: 10px 20px; display: flex;
    align-items: center; gap: 12px;
    z-index: 999; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }}
  .toolbar h3 {{ margin: 0; font-size: 15px; flex: 1; }}
  .btn {{
    background: white; color: #1f4e79;
    border: none; padding: 8px 20px;
    border-radius: 5px; font-size: 14px;
    font-weight: bold; cursor: pointer;
  }}
  .btn:hover {{ background: #e8f0fe; }}
  .content {{ padding-top: 55px; }}
  .page {{
    width: 210mm; margin: 12px auto;
    background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  }}
  .page img {{ width: 100%; display: block; }}
  @media print {{
    body {{ background: white; }}
    .toolbar {{ display: none; }}
    .content {{ padding-top: 0; }}
    .page {{
      width: 100%; margin: 0;
      box-shadow: none;
      page-break-after: always;
    }}
    .page:last-child {{ page-break-after: avoid; }}
  }}
</style>
</head>
<body>
<div class="toolbar">
  <h3>✈ 일본 입국서류 — {title}</h3>
  <button class="btn" onclick="window.print()">🖨 인쇄</button>
  <button class="btn" onclick="window.close()">✕ 닫기</button>
</div>
<div class="content">
{imgs_html}
</div>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════
st.sidebar.title("✈ 일본 입국서류")
st.sidebar.markdown("자동 출력 프로그램")
st.sidebar.divider()

menu = st.sidebar.radio(
    "메뉴",
    [
        "1. 행사정보 입력",
        "2. 명단 업로드",
        "3. 데이터 검증",
        "4. 양식 위치 설정",
        "5. 미리보기",
        "6. 인쇄 / PDF",
    ],
    label_visibility="collapsed",
)

if st.session_state.cleaned_passengers:
    st.sidebar.success(f"✅ 승객 {len(st.session_state.cleaned_passengers)}명")
else:
    st.sidebar.warning("⚠ 명단 없음")

st.sidebar.divider()
st.sidebar.markdown("**양식 JPG 업로드**")

imm_upload = st.sidebar.file_uploader(
    "출입국카드 JPG", type=["jpg", "jpeg", "png"], key="upload_imm"
)
if imm_upload:
    st.session_state.imm_jpg_bytes = imm_upload.read()
    st.sidebar.success("출입국카드 ✅")

cus_upload = st.sidebar.file_uploader(
    "휴대품신고서 JPG", type=["jpg", "jpeg", "png"], key="upload_cus"
)
if cus_upload:
    st.session_state.cus_jpg_bytes = cus_upload.read()
    st.sidebar.success("휴대품신고서 ✅")


# ══════════════════════════════════════════════════════════════
# 화면 1: 행사정보 입력
# ══════════════════════════════════════════════════════════════
if menu == "1. 행사정보 입력":
    st.title("행사정보 입력")

    ci = st.session_state.common_info
    presets = st.session_state.hotel_presets

    col1, col2 = st.columns(2)
    with col1:
        ci["국적"] = st.text_input("국적 (Nationality)", value=ci["국적"]).upper()

        city_options = ["BUSAN", "DAEGU", "INCHEON", "직접입력"]
        current_city = ci["도시"]
        city_sel = st.selectbox(
            "출발도시 (Departure City)",
            city_options,
            index=city_options.index(current_city) if current_city in city_options else len(city_options) - 1,
        )
        if city_sel == "직접입력":
            ci["도시"] = st.text_input("도시 직접 입력", value=current_city if current_city not in city_options[:-1] else "").upper()
        else:
            ci["도시"] = city_sel

        flight_options = ["BX143", "BX124", "BX148", "BX182", "TW311", "직접입력"]
        current_flight = ci["입국편명"]
        flight_sel = st.selectbox(
            "입국편명 (Flight No.)",
            flight_options,
            index=flight_options.index(current_flight) if current_flight in flight_options else len(flight_options) - 1,
        )
        if flight_sel == "직접입력":
            ci["입국편명"] = st.text_input("편명 직접 입력", value=current_flight if current_flight not in flight_options[:-1] else "").upper()
        else:
            ci["입국편명"] = flight_sel
        stay_options = [f"{i} DAY{'S' if i > 1 else ''}" for i in range(1, 6)] + ["직접입력"]
        current_stay = ci["여행기간"]
        stay_sel = st.selectbox(
            "체류예정기간 (Stay Duration)",
            stay_options,
            index=stay_options.index(current_stay) if current_stay in stay_options else len(stay_options) - 1,
        )
        if stay_sel == "직접입력":
            ci["여행기간"] = st.text_input("직접 입력", value=current_stay if current_stay not in stay_options[:-1] else "")
        else:
            ci["여행기간"] = stay_sel

        today = date.today()
        date_options = [str(today + __import__('datetime').timedelta(days=i)) for i in range(0, 15)]
        date_options_display = [(d, f"{d} ({['월','화','수','목','금','토','일'][date.fromisoformat(d).weekday()]})") for d in date_options]
        current_date = ci["입국일"]
        date_sel = st.selectbox(
            "입국일 (Entry Date)",
            [d for d, _ in date_options_display],
            format_func=lambda d: next(label for dd, label in date_options_display if dd == d),
            index=date_options.index(current_date) if current_date in date_options else 0,
        )
        ci["입국일"] = date_sel
        ci["여행목적"] = st.selectbox(
            "여행목적 (Purpose)",
            ["관광", "상용", "친족방문", "기타"],
            index=["관광", "상용", "친족방문", "기타"].index(ci.get("여행목적", "관광")),
        )

    with col2:
        st.markdown("**호텔 선택**")

        preset_names = [p["name"] for p in presets]
        sel_preset = st.selectbox("저장된 호텔", preset_names)
        sel = next(p for p in presets if p["name"] == sel_preset)

        if sel["name"] != "직접입력":
            if st.button("이 호텔 적용"):
                ci["호텔이름"] = sel["hotel"]
                ci["호텔전화번호"] = sel["tel"]
                st.rerun()

        ci["호텔이름"] = st.text_input("호텔이름 (Hotel Name)", value=ci["호텔이름"]).upper()
        ci["호텔전화번호"] = st.text_input("호텔전화번호 (Hotel TEL)", value=ci["호텔전화번호"])

        st.divider()
        st.markdown("**호텔 프리셋 추가**")
        new_name = st.text_input("프리셋 이름", key="new_preset_name")
        new_hotel = st.text_input("호텔명", key="new_preset_hotel")
        new_tel = st.text_input("전화번호", key="new_preset_tel")
        if st.button("➕ 프리셋 추가"):
            if new_name and new_hotel:
                presets.append({"name": new_name, "hotel": new_hotel.upper(), "tel": new_tel})
                st.session_state.hotel_presets = presets
                st.success(f"'{new_name}' 추가됨")
                st.rerun()

        # 프리셋 삭제
        deletable = [p["name"] for p in presets if p["name"] != "직접입력"]
        if deletable:
            del_target = st.selectbox("삭제할 프리셋", ["선택안함"] + deletable)
            if del_target != "선택안함" and st.button("🗑 삭제"):
                st.session_state.hotel_presets = [p for p in presets if p["name"] != del_target]
                st.success(f"'{del_target}' 삭제됨")
                st.rerun()

    if st.button("💾 저장", type="primary"):
        st.session_state.common_info = ci
        st.success("저장 완료!")

    st.divider()
    st.subheader("현재 저장된 정보")
    st.json(st.session_state.common_info)


# ══════════════════════════════════════════════════════════════
# 화면 2: 명단 업로드
# ══════════════════════════════════════════════════════════════
elif menu == "2. 명단 업로드":
    st.title("명단 업로드")

    tab_file, tab_paste = st.tabs(["📁 파일 업로드", "📋 직접 붙여넣기"])

    with tab_file:
        uploaded = st.file_uploader(
            "엑셀(.xlsx) 또는 CSV 파일을 업로드하세요",
            type=["xlsx", "csv"],
        )
        if uploaded:
            try:
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded, dtype=str).fillna("")
                else:
                    df = pd.read_excel(uploaded, dtype=str).fillna("")

                df.columns = [c.strip() for c in df.columns]
                required_cols = {"NO", "영문이름", "생년월일", "여권번호", "성별"}
                missing = required_cols - set(df.columns)
                if missing:
                    st.error(f"필수 컬럼 없음: {missing}")
                else:
                    raw = df.to_dict("records")
                    cleaned = [clean_passenger(p) for p in raw]
                    st.session_state.passengers = raw
                    st.session_state.cleaned_passengers = cleaned
                    st.success(f"✅ {len(cleaned)}명 로드 완료")
            except Exception as e:
                st.error(f"파일 읽기 오류: {e}")

        st.divider()
        sample_data = {
            "NO": [1, 2, 3],
            "영문이름": ["KIM/HYUNG KYOU", "RYU/SE YEON", "CHOI/HYUN WOO"],
            "생년월일": ["1982-11-24", "1983-10-17", "090924-4"],
            "여권번호": ["M12345678", "M98765432", "M55555555"],
            "성별": ["M", "F", "여"],
        }
        buf = io.BytesIO()
        pd.DataFrame(sample_data).to_excel(buf, index=False)
        buf.seek(0)
        st.download_button(
            "📥 샘플 엑셀 다운로드",
            data=buf.read(),
            file_name="sample_passengers.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with tab_paste:
        st.markdown("헤더 포함, 탭 또는 쉼표 구분으로 붙여넣기:")
        st.code("NO\t영문이름\t생년월일\t여권번호\t성별\n1\tKIM/HYUNG KYOU\t1982-11-24\tM12345678\tM")
        pasted = st.text_area("데이터 붙여넣기", height=200)
        if st.button("붙여넣기 데이터 적용"):
            try:
                sep = "\t" if "\t" in pasted else ","
                df = pd.read_csv(io.StringIO(pasted), sep=sep, dtype=str).fillna("")
                df.columns = [c.strip() for c in df.columns]
                raw = df.to_dict("records")
                cleaned = [clean_passenger(p) for p in raw]
                st.session_state.passengers = raw
                st.session_state.cleaned_passengers = cleaned
                st.success(f"✅ {len(cleaned)}명 적용 완료")
            except Exception as e:
                st.error(f"파싱 오류: {e}")

    if st.session_state.cleaned_passengers:
        st.divider()
        st.subheader("변환 결과 비교")
        rows = []
        for orig, cln in zip(
            st.session_state.passengers,
            st.session_state.cleaned_passengers,
        ):
            rows.append({
                "NO": orig.get("NO", ""),
                "원본 이름": orig.get("영문이름", ""),
                "→ 변환 이름": cln.get("영문이름", ""),
                "원본 생년월일": str(orig.get("생년월일", "")),
                "→ 변환 생년월일": cln.get("생년월일", ""),
                "원본 성별": str(orig.get("성별", "")),
                "→ 변환 성별": cln.get("성별", ""),
                "여권번호": cln.get("여권번호", ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 화면 3: 데이터 검증
# ══════════════════════════════════════════════════════════════
elif menu == "3. 데이터 검증":
    st.title("데이터 검증")

    if not st.session_state.cleaned_passengers:
        st.warning("먼저 명단을 업로드하세요.")
    else:
        passengers = st.session_state.cleaned_passengers
        common = st.session_state.common_info

        valid_list, all_errors = validate_all(passengers, common)

        col1, col2, col3 = st.columns(3)
        col1.metric("전체 승객", len(passengers))
        col2.metric("정상", len(valid_list))
        col3.metric("오류", len(passengers) - len(valid_list))

        st.divider()
        if all_errors:
            st.subheader("⚠ 오류 목록")
            for err in all_errors:
                st.error(err)
        else:
            st.success("✅ 모든 데이터 정상 — 인쇄 가능합니다.")

        st.subheader("전체 데이터 확인")
        preview_rows = []
        for p in passengers:
            errs = validate_passenger(int(str(p.get("NO", 0)) or 0), p, common)
            preview_rows.append({
                "NO": p.get("NO", ""),
                "영문이름": p.get("영문이름", ""),
                "생년월일": p.get("생년월일", ""),
                "여권번호": p.get("여권번호", ""),
                "성별": p.get("성별", ""),
                "상태": "✅" if not errs else f"❌ {len(errs)}건",
            })
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 화면 4: 양식 위치 설정
# ══════════════════════════════════════════════════════════════
elif menu == "4. 양식 위치 설정":
    st.title("양식 위치 설정")
    st.info("📐 좌표 기준: A4 포인트 (좌상단=0,0 / A4=595×842pt)\n\n5번 미리보기와 함께 번갈아 보면서 조정하세요.")

    form_sel = st.radio(
        "양식 선택",
        ["출입국카드 (外国人入国記録)", "휴대품신고서 (휴대품·별송품)"],
        horizontal=True,
    )
    form_type = "immigration_card" if "출입국" in form_sel else "customs_declaration"
    positions = _get_positions(form_type)
    field_names = list(positions.keys())

    selected_field = st.selectbox(
        "필드 선택", field_names,
        format_func=lambda k: f"{k}  ─  {positions[k].get('label', '')}"
    )

    pos = dict(positions[selected_field])
    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        pos["x"] = st.number_input("X (좌→우 pt)", value=float(pos.get("x", 0)), step=0.5, format="%.1f")
        pos["y"] = st.number_input("Y (상→하 pt)", value=float(pos.get("y", 0)), step=0.5, format="%.1f")
    with col2:
        if pos.get("type") in ["text", "multiline"]:
            pos["width"] = st.number_input("Width (pt)", value=float(pos.get("width", 100)), step=0.5, format="%.1f")
            pos["height"] = st.number_input("Height (pt)", value=float(pos.get("height", 16)), step=0.5, format="%.1f")
        elif pos.get("type") == "split_text":
            pos["cell_gap"] = st.number_input("Cell Gap (pt)", value=float(pos.get("cell_gap", 13.5)), step=0.5, format="%.1f")
    with col3:
        pos["font_size"] = st.number_input(
            "Font Size (pt)", value=float(pos.get("font_size", 9)),
            step=0.5, format="%.1f", min_value=5.0, max_value=20.0
        )

    positions[selected_field] = pos

    col_save, col_reset = st.columns([1, 4])
    with col_save:
        if st.button("💾 저장", type="primary"):
            _save_session_positions(form_type, positions)
            st.success("저장 완료!")
    with col_reset:
        if st.button("🔄 기본값 초기화"):
            from utils.position_manager import get_default_positions
            _save_session_positions(form_type, get_default_positions(form_type))
            st.success("초기화 완료! 페이지를 새로고침하세요.")

    # ── 전체 필드 오버레이 시각화 ──────────────────────────
    st.divider()
    st.subheader("📍 전체 필드 위치 시각화")
    st.caption("빨간 박스 = 선택된 필드 / 파란 박스 = 나머지 필드")

    jpg_bytes = (
        st.session_state.imm_jpg_bytes
        if form_type == "immigration_card"
        else st.session_state.cus_jpg_bytes
    )

    if jpg_bytes:
        from PIL import Image, ImageDraw, ImageFont
        from reportlab.lib.pagesizes import A4
        PAGE_W_REF, PAGE_H_REF = A4

        overlay_img = Image.open(io.BytesIO(jpg_bytes)).convert("RGB")
        # 배경 흰색 처리
        gray = overlay_img.convert("L")
        px = overlay_img.load(); gp = gray.load()
        for yy in range(overlay_img.height):
            for xx in range(overlay_img.width):
                if gp[xx, yy] > 200:
                    px[xx, yy] = (255, 255, 255)

        iw, ih = overlay_img.size
        sx, sy = iw / PAGE_W_REF, ih / PAGE_H_REF
        draw = ImageDraw.Draw(overlay_img)

        for k, v in positions.items():
            x0 = float(v["x"]) * sx
            y0 = float(v["y"]) * sy
            ftype = v.get("type", "text")
            color = (220, 0, 0) if k == selected_field else (0, 80, 200)
            lw = 3 if k == selected_field else 1

            if ftype in ["text", "multiline"]:
                w = float(v.get("width", 60)) * sx
                h = float(v.get("height", 14)) * sy
                draw.rectangle([x0, y0 - h, x0 + w, y0 + 4], outline=color, width=lw)
                draw.text((x0 + 2, y0 - h + 1), k, fill=color)
            elif ftype == "split_text":
                gap = float(v.get("cell_gap", 13.5)) * sx
                for i in range(8):
                    cx = x0 + i * gap
                    draw.rectangle([cx, y0 - 12 * sy, cx + gap - 1, y0 + 3], outline=color, width=lw)
                draw.text((x0, y0 - 12 * sy - 12), k, fill=color)
            elif ftype == "checkbox":
                draw.rectangle([x0, y0 - 10 * sy, x0 + 10 * sx, y0 + 3], outline=color, width=lw)
                draw.text((x0, y0 - 10 * sy - 12), k, fill=color)

        # 상단 400pt만 크롭해서 표시 (카드 영역만)
        crop_h = int(370 * sy)
        overlay_img = overlay_img.crop((0, 0, iw, min(crop_h, ih)))
        overlay_img = overlay_img.resize((iw, min(crop_h, ih)), Image.LANCZOS)
        st.image(overlay_img, use_container_width=True)
    else:
        st.info("💡 사이드바에서 JPG를 업로드하면 필드 위치를 시각적으로 확인할 수 있습니다.")

    st.divider()
    st.subheader("전체 필드 좌표표")
    st.dataframe(pd.DataFrame([
        {
            "key": k, "label": v.get("label", ""), "type": v.get("type", "text"),
            "x": v.get("x", 0), "y": v.get("y", 0),
            "width": v.get("width", "-"), "font_size": v.get("font_size", 9),
            "cell_gap": v.get("cell_gap", "-"),
        }
        for k, v in positions.items()
    ]), use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 화면 5: 미리보기
# ══════════════════════════════════════════════════════════════
elif menu == "5. 미리보기":
    st.title("미리보기")

    if not st.session_state.cleaned_passengers:
        st.warning("먼저 명단을 업로드하세요.")
    else:
        passengers = st.session_state.cleaned_passengers
        common = st.session_state.common_info

        col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([2, 2, 1])
        with col_ctrl1:
            pax_idx = st.selectbox(
                "승객 선택",
                range(len(passengers)),
                format_func=lambda i: f"{passengers[i].get('NO', '')}: {passengers[i].get('영문이름', '')}",
            )
        with col_ctrl2:
            form_choice = st.radio("양식", ["출입국카드", "휴대품신고서"], horizontal=True)
        with col_ctrl3:
            scale = st.slider("확대/축소", 0.3, 1.5, 0.6, 0.1)

        form_type = "immigration_card" if form_choice == "출입국카드" else "customs_declaration"
        positions = _get_positions(form_type)
        passenger = passengers[pax_idx]

        jpg_bytes = (
            st.session_state.imm_jpg_bytes
            if form_type == "immigration_card"
            else st.session_state.cus_jpg_bytes
        )
        tmp_jpg = None
        if jpg_bytes:
            tmp_jpg = _write_jpg_to_tmp(jpg_bytes)

        preview_img = generate_preview_image(
            form_type, passenger, common, positions, tmp_jpg, scale=scale
        )
        if tmp_jpg:
            os.unlink(tmp_jpg)

        st.image(
            preview_img,
            caption=f"{passenger.get('영문이름', '')} — {form_choice}",
            use_container_width=True,
        )
        if not jpg_bytes:
            st.info("💡 사이드바에서 JPG를 업로드하면 실제 양식 위에 미리보기가 표시됩니다.")


# ══════════════════════════════════════════════════════════════
# 화면 6: 인쇄 / PDF
# ══════════════════════════════════════════════════════════════
elif menu == "6. 인쇄 / PDF":
    st.title("인쇄 / PDF 생성")

    if not st.session_state.cleaned_passengers:
        st.warning("먼저 명단을 업로드하세요.")
    else:
        passengers = st.session_state.cleaned_passengers
        common = st.session_state.common_info

        # ── 출력 설정 ──────────────────────────────────────
        st.subheader("출력 설정")
        col1, col2 = st.columns(2)

        with col1:
            target = st.radio("출력 대상", ["전체 승객", "선택 승객"])
            if target == "선택 승객":
                selected_indices = st.multiselect(
                    "승객 선택",
                    range(len(passengers)),
                    format_func=lambda i: f"{passengers[i].get('NO', '')}: {passengers[i].get('영문이름', '')}",
                )
                selected_passengers = [passengers[i] for i in selected_indices]
            else:
                selected_passengers = passengers

        with col2:
            doc_type = st.radio("출력 서류", ["출입국카드만", "휴대품신고서만", "두 서류 모두"])
            include_imm = doc_type in ["출입국카드만", "두 서류 모두"]
            include_cus = doc_type in ["휴대품신고서만", "두 서류 모두"]

        n = len(selected_passengers)
        st.info(f"출력 예정: {n}명")

        if n == 0:
            st.stop()

        imm_positions = _get_positions("immigration_card")
        cus_positions = _get_positions("customs_declaration")

        imm_tmp = _write_jpg_to_tmp(st.session_state.imm_jpg_bytes) if st.session_state.imm_jpg_bytes else None
        cus_tmp = _write_jpg_to_tmp(st.session_state.cus_jpg_bytes) if st.session_state.cus_jpg_bytes else None

        st.divider()

        # ══════════════════════════════════════════════════
        # 웹 인쇄 (브라우저 인쇄 대화상자)
        # ══════════════════════════════════════════════════
        st.subheader("🖨 웹 인쇄 (권장)")
        st.caption("버튼 클릭 → 새 탭에서 미리보기 → Ctrl+P (또는 인쇄 버튼)")

        if st.button("🖨 인쇄 미리보기 열기", type="primary"):
            with st.spinner("이미지 생성 중..."):
                images_b64 = []
                for p in selected_passengers:
                    if include_imm:
                        img = generate_preview_image(
                            "immigration_card", p, common,
                            imm_positions, imm_tmp, scale=1.0
                        )
                        images_b64.append(_img_to_base64(img))
                    if include_cus:
                        img = generate_preview_image(
                            "customs_declaration", p, common,
                            cus_positions, cus_tmp, scale=1.0
                        )
                        images_b64.append(_img_to_base64(img))

            html = _build_print_html(
                images_b64,
                title=f"입국서류 {n}명"
            )

            # base64로 인코딩해서 새 탭 링크 제공
            html_b64 = base64.b64encode(html.encode("utf-8")).decode()
            js = f"""
            <script>
            const html = atob("{html_b64}");
            const blob = new Blob([html], {{type: 'text/html'}});
            const url = URL.createObjectURL(blob);
            window.open(url, '_blank');
            </script>
            """
            components.html(js, height=0)
            st.success(f"✅ {len(images_b64)}페이지 생성 완료 — 새 탭이 열립니다.")
            st.info("팝업이 차단된 경우: 브라우저 주소창 우측의 팝업 허용 버튼을 클릭하세요.")

        st.divider()

        # ══════════════════════════════════════════════════
        # PDF 다운로드
        # ══════════════════════════════════════════════════
        st.subheader("📄 PDF 다운로드")

        col_a, col_b = st.columns(2)

        with col_a:
            if st.button("📄 통합 PDF 생성"):
                with st.spinner("PDF 생성 중..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                        tmp_out = f.name
                    result = generate_combined_pdf(
                        passengers=selected_passengers,
                        common=common,
                        imm_positions=imm_positions,
                        cus_positions=cus_positions,
                        imm_template=imm_tmp,
                        cus_template=cus_tmp,
                        output_path=tmp_out,
                        include_immigration=include_imm,
                        include_customs=include_cus,
                    )
                    with open(tmp_out, "rb") as f:
                        pdf_bytes = f.read()
                    os.unlink(tmp_out)

                st.download_button(
                    label=f"📥 통합 PDF ({result['count']}명, {len(pdf_bytes)//1024}KB)",
                    data=pdf_bytes,
                    file_name="immigration_forms.pdf",
                    mime="application/pdf",
                )

        with col_b:
            if st.button("📦 개인별 ZIP 생성"):
                zip_buf = io.BytesIO()
                with st.spinner("생성 중..."):
                    with zipfile.ZipFile(zip_buf, "w") as zf:
                        for p in selected_passengers:
                            name_safe = p.get("영문이름", "unknown").replace(" ", "_")
                            no = p.get("NO", "")
                            for form_type, template, positions, suffix in [
                                ("immigration_card", imm_tmp, imm_positions, "immigration"),
                                ("customs_declaration", cus_tmp, cus_positions, "customs"),
                            ]:
                                if form_type == "immigration_card" and not include_imm:
                                    continue
                                if form_type == "customs_declaration" and not include_cus:
                                    continue
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                                    fp = f.name
                                generate_single_pdf(form_type, p, common, positions, template, fp)
                                zf.write(fp, f"{no}_{name_safe}_{suffix}.pdf")
                                os.unlink(fp)

                zip_buf.seek(0)
                st.download_button(
                    label=f"📥 ZIP ({n}명)",
                    data=zip_buf.read(),
                    file_name="immigration_forms_individual.zip",
                    mime="application/zip",
                )

        # 임시파일 정리
        for tmp in [imm_tmp, cus_tmp]:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
