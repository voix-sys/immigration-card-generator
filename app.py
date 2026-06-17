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
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.data_cleaner import clean_passenger
from utils.validator import validate_all, validate_passenger
from utils.position_manager import load_positions, init_default_configs
from utils.pdf_generator import generate_preview_image
from fill_card import fill_card, passenger_to_card_data

# ── 엑셀 스마트 로더 ───────────────────────────────────────────
_COL_PATTERNS = {
    "NO":    ["no", "번호", "순번", "no."],
    "영문이름": ["영문이름", "영문성명", "영문명", "성명(영문)", "영어이름", "영어성명",
               "name", "english name", "eng name", "eng.name"],
    "생년월일": ["생년월일", "생년", "birthday", "birth", "dob", "date of birth"],
    "여권번호": ["여권번호", "여권", "passport", "passport no", "passportno", "p/p"],
    "성별":   ["성별", "sex", "gender"],
}

def _detect_header_row(raw_df: pd.DataFrame) -> int:
    """NO 또는 영문이름이 있는 행을 헤더 행으로 탐지 (최대 10행 탐색)"""
    for i in range(min(10, len(raw_df))):
        cells = [str(v).strip().lower() for v in raw_df.iloc[i] if pd.notna(v)]
        if any(c in ("no", "no.") for c in cells):
            return i
        if any("영문" in c or "name" in c for c in cells):
            return i
    return 0

def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼명을 표준 필드명으로 매핑"""
    col_map = {}
    for std, patterns in _COL_PATTERNS.items():
        for col in df.columns:
            if col.strip().lower() in patterns:
                col_map[col] = std
                break
    df = df.rename(columns=col_map)
    if "NO" not in df.columns:
        df.insert(0, "NO", range(1, len(df) + 1))
    return df

def load_excel_smart(file_obj) -> tuple[pd.DataFrame, str]:
    """여행사 엑셀/CSV를 자동 인식해 표준 DataFrame 반환. (df, 오류메시지) 반환"""
    name = file_obj.name
    try:
        if name.endswith(".csv"):
            raw = pd.read_excel(file_obj, dtype=str, header=None)
        else:
            raw = pd.read_excel(file_obj, dtype=str, header=None)
        header_row = _detect_header_row(raw)
        df = pd.read_excel(file_obj, dtype=str, header=header_row).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        df = _map_columns(df)
        # 영문이름 없는 행 제거
        if "영문이름" in df.columns:
            df = df[df["영문이름"].str.strip() != ""]
        required = {"영문이름", "생년월일", "여권번호"}
        missing = required - set(df.columns)
        if missing:
            return None, f"필수 컬럼을 찾을 수 없음: {missing}\n실제 컬럼: {list(df.columns)}"
        return df, ""
    except Exception as e:
        return None, str(e)

# ── 초기화 ─────────────────────────────────────────────────────
init_default_configs()

st.set_page_config(
    page_title="일본 입국서류 자동출력",
    page_icon="✈",
    layout="wide",
)

st.markdown("""
<style>
  .stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],
  [data-testid="block-container"],section[data-testid="stMainBlockContainer"],
  .main,.block-container{background-color:#ffffff!important}
  [data-testid="stSidebar"],[data-testid="stSidebar"]>div{background-color:#f0f0f0!important}
  *,*::before,*::after{color:#111111!important}
  input,textarea,[data-baseweb="input"] input,[data-baseweb="textarea"] textarea{
    background-color:#ffffff!important;color:#111111!important;border-color:#aaaaaa!important}
  [data-baseweb="select"]>div,[data-baseweb="select"] span,[data-baseweb="popover"] li,
  [data-baseweb="menu"] ul,[role="listbox"],[role="option"]{
    background-color:#ffffff!important;color:#111111!important}
  [role="option"]:hover{background-color:#e8eaf6!important}
  [data-testid="stNumberInput"]>div,[data-testid="stNumberInput"] button{
    background-color:#ffffff!important;color:#111111!important;border-color:#aaaaaa!important}
  [data-testid="stRadio"]>div,[data-testid="stCheckbox"]>div{background-color:transparent!important}
  [data-testid="metric-container"],[data-testid="stMetric"],
  [data-testid="stMetricValue"],[data-testid="stMetricLabel"]{
    background-color:#f5f7ff!important;color:#111111!important}
  [data-testid="stExpander"],[data-testid="stExpander"]>div,details,summary{
    background-color:#f9f9f9!important;color:#111111!important;border-color:#cccccc!important}
  [data-testid="stAlert"],[data-testid="stAlert"]>div,[data-testid="stAlert"] p{color:#111111!important}
  [data-testid="stJson"],.stJson{background-color:#f5f5f5!important;color:#111111!important}
  [data-testid="stDataFrame"],.dvn-scroller,.glideDataEditor,.stDataFrame{background-color:#ffffff!important}
  [data-testid="stTabs"] [role="tablist"],[data-testid="stTabs"] [role="tab"]{
    background-color:#f0f0f0!important;color:#111111!important}
  [data-testid="stTabs"] [role="tab"][aria-selected="true"]{
    background-color:#ffffff!important;border-bottom:2px solid #1a56db!important}
  hr{border-color:#cccccc!important}
  [data-testid="stButton"]>button,.stButton>button{
    background-color:#1a56db!important;color:#ffffff!important;border:none!important}
  [data-testid="stButton"]>button:hover,.stButton>button:hover{background-color:#1245b5!important}
  [data-testid="stDownloadButton"]>button{background-color:#0e7c3a!important;color:#ffffff!important}
  code,pre{background-color:#f3f3f3!important;color:#333333!important}
</style>
""", unsafe_allow_html=True)

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
            "도시": "BUSAN",
            "입국편명": "",
            "여행기간": "3 DAYS",
            "입국일": str(date.today()),
            "호텔이름": "",
            "호텔전화번호": "",
            "여행목적": "관광",
        },
        "passengers": [],
        "cleaned_passengers": [],
        "imm_jpg_bytes": None,
        "cus_jpg_bytes": None,
        "hotel_presets": HOTEL_PRESETS,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


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
    imgs_html = "".join(
        f'<div class="page"><img src="data:image/jpeg;base64,{b64}" /></div>'
        for b64 in images_b64
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#f0f0f0;font-family:sans-serif}}
  .toolbar{{position:fixed;top:0;left:0;right:0;background:#1f4e79;color:white;
    padding:10px 20px;display:flex;align-items:center;gap:12px;z-index:999;
    box-shadow:0 2px 8px rgba(0,0,0,.3)}}
  .toolbar h3{{margin:0;font-size:15px;flex:1}}
  .btn{{background:white;color:#1f4e79;border:none;padding:8px 20px;
    border-radius:5px;font-size:14px;font-weight:bold;cursor:pointer}}
  .btn:hover{{background:#e8f0fe}}
  .content{{padding-top:55px}}
  .page{{width:210mm;margin:12px auto;background:white;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
  .page img{{width:100%;display:block}}
  @media print{{
    body{{background:white}}.toolbar{{display:none}}.content{{padding-top:0}}
    .page{{width:100%;margin:0;box-shadow:none;page-break-after:always}}
    .page:last-child{{page-break-after:avoid}}
  }}
</style></head><body>
<div class="toolbar">
  <h3>✈ 일본 입국서류 — {title}</h3>
  <button class="btn" onclick="window.print()">🖨 인쇄</button>
  <button class="btn" onclick="window.close()">✕ 닫기</button>
</div>
<div class="content">{imgs_html}</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════
# fill_card 렌더러
# ══════════════════════════════════════════════════════════════
def _render_imm_image(passenger: dict, common: dict):
    from PIL import Image as _PILImage
    data = passenger_to_card_data(passenger, common)
    jpg_bytes = st.session_state.imm_jpg_bytes
    if not jpg_bytes:
        return _PILImage.new("RGB", (1654, 2337), (255, 255, 255))
    tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp_in.write(jpg_bytes); tmp_in.close()
    tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp_out.close()
    try:
        fill_card(tmp_in.name, data, tmp_out.name)
    finally:
        os.unlink(tmp_in.name)
    img = _PILImage.open(tmp_out.name).copy()
    os.unlink(tmp_out.name)
    return img


# ══════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════
st.sidebar.title("✈ 일본 입국서류")
st.sidebar.markdown("자동 출력 프로그램")
st.sidebar.divider()

menu = st.sidebar.radio(
    "메뉴",
    ["1. 정보 & 명단", "2. 미리보기", "3. 출력"],
    label_visibility="collapsed",
)

# 상태 표시
n_pax = len(st.session_state.cleaned_passengers)
if n_pax:
    st.sidebar.success(f"✅ 승객 {n_pax}명 로드됨")
else:
    st.sidebar.warning("⚠ 명단 없음")

# 템플릿 자동 로드
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_IMM_JPG = _TEMPLATE_DIR / "immigration_card.jpg"
_CUS_JPG = _TEMPLATE_DIR / "customs_declaration.jpg"

if st.session_state.imm_jpg_bytes is None and _IMM_JPG.exists():
    st.session_state.imm_jpg_bytes = _IMM_JPG.read_bytes()
if st.session_state.cus_jpg_bytes is None and _CUS_JPG.exists():
    st.session_state.cus_jpg_bytes = _CUS_JPG.read_bytes()

imm_ok = st.session_state.imm_jpg_bytes is not None
cus_ok = st.session_state.cus_jpg_bytes is not None
st.sidebar.markdown(f"{'✅' if imm_ok else '❌'} 출입국카드")
st.sidebar.markdown(f"{'✅' if cus_ok else '❌'} 휴대품신고서")

with st.sidebar.expander("JPG 교체 (선택사항)"):
    imm_upload = st.file_uploader("출입국카드 교체", type=["jpg","jpeg","png"], key="upload_imm")
    if imm_upload:
        st.session_state.imm_jpg_bytes = imm_upload.read()
        st.rerun()
    cus_upload = st.file_uploader("휴대품신고서 교체", type=["jpg","jpeg","png"], key="upload_cus")
    if cus_upload:
        st.session_state.cus_jpg_bytes = cus_upload.read()
        st.rerun()


# ══════════════════════════════════════════════════════════════
# 화면 1: 정보 & 명단
# ══════════════════════════════════════════════════════════════
if menu == "1. 정보 & 명단":
    st.title("행사 정보 & 명단")

    ci = st.session_state.common_info
    presets = st.session_state.hotel_presets

    # ── 행사 정보 ────────────────────────────────────────────
    with st.expander("✈ 행사 정보", expanded=True):
        c1, c2, c3 = st.columns(3)

        with c1:
            # 호텔 프리셋 선택 → 자동 적용
            preset_names = [p["name"] for p in presets]
            sel_preset = st.selectbox("호텔 프리셋", preset_names, key="preset_sel")
            sel = next(p for p in presets if p["name"] == sel_preset)
            if sel["name"] != "직접입력":
                ci["호텔이름"] = sel["hotel"]
                ci["호텔전화번호"] = sel["tel"]

            ci["호텔이름"] = st.text_input("호텔명", value=ci["호텔이름"]).upper()
            ci["호텔전화번호"] = st.text_input("호텔 전화", value=ci["호텔전화번호"])

        with c2:
            flight_options = ["BX143", "BX124", "BX148", "BX182", "TW311", "직접입력"]
            cur_flight = ci["입국편명"]
            flight_sel = st.selectbox(
                "입국편명",
                flight_options,
                index=flight_options.index(cur_flight) if cur_flight in flight_options else len(flight_options)-1,
            )
            if flight_sel == "직접입력":
                ci["입국편명"] = st.text_input("편명 직접입력", value=cur_flight if cur_flight not in flight_options[:-1] else "").upper()
            else:
                ci["입국편명"] = flight_sel

            stay_options = [f"{i} DAYS" for i in range(1, 8)] + ["직접입력"]
            cur_stay = ci["여행기간"]
            stay_sel = st.selectbox(
                "체류기간",
                stay_options,
                index=stay_options.index(cur_stay) if cur_stay in stay_options else len(stay_options)-1,
            )
            if stay_sel == "직접입력":
                ci["여행기간"] = st.text_input("체류기간 직접입력", value=cur_stay if cur_stay not in stay_options[:-1] else "")
            else:
                ci["여행기간"] = stay_sel

        with c3:
            city_options = ["BUSAN", "DAEGU", "INCHEON", "직접입력"]
            cur_city = ci["도시"]
            city_sel = st.selectbox(
                "출발도시",
                city_options,
                index=city_options.index(cur_city) if cur_city in city_options else len(city_options)-1,
            )
            if city_sel == "직접입력":
                ci["도시"] = st.text_input("도시 직접입력", value=cur_city if cur_city not in city_options[:-1] else "").upper()
            else:
                ci["도시"] = city_sel

            today = date.today()
            date_options = [str(today + __import__('datetime').timedelta(days=i)) for i in range(0, 15)]
            cur_date = ci["입국일"]
            date_sel = st.selectbox(
                "입국일",
                date_options,
                format_func=lambda d: f"{d} ({['월','화','수','목','금','토','일'][date.fromisoformat(d).weekday()]})",
                index=date_options.index(cur_date) if cur_date in date_options else 0,
            )
            ci["입국일"] = date_sel
            ci["여행목적"] = st.selectbox("여행목적", ["관광", "상용", "친족방문", "기타"],
                                        index=["관광","상용","친족방문","기타"].index(ci.get("여행목적","관광")))

        ci["국적"] = "KOREA"
        st.session_state.common_info = ci

    # ── 명단 업로드 ──────────────────────────────────────────
    with st.expander("👥 명단 업로드", expanded=True):
        tab_file, tab_paste = st.tabs(["📁 파일 업로드", "📋 직접 붙여넣기"])

        with tab_file:
            col_up, col_dl = st.columns([3, 1])
            with col_up:
                uploaded = st.file_uploader(
                    "엑셀(.xlsx) 또는 CSV",
                    type=["xlsx", "csv"],
                    label_visibility="collapsed",
                )
            with col_dl:
                sample_data = {
                    "NO": [1, 2], "영문이름": ["KIM/HYUNG KYOU", "RYU/SE YEON"],
                    "생년월일": ["1982-11-24", "1983-10-17"],
                    "여권번호": ["M12345678", "M98765432"], "성별": ["M", "F"],
                }
                buf = io.BytesIO()
                pd.DataFrame(sample_data).to_excel(buf, index=False)
                buf.seek(0)
                st.download_button("📥 샘플", data=buf.read(),
                                   file_name="sample.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            if uploaded:
                df, err = load_excel_smart(uploaded)
                if err:
                    st.error(f"파일 읽기 오류: {err}")
                else:
                    raw = df.to_dict("records")
                    cleaned = [clean_passenger(p) for p in raw]
                    st.session_state.passengers = raw
                    st.session_state.cleaned_passengers = cleaned
                    st.success(f"✅ {len(cleaned)}명 로드 완료")

        with tab_paste:
            st.caption("헤더 포함, 탭 또는 쉼표 구분:")
            st.code("NO\t영문이름\t생년월일\t여권번호\t성별")
            pasted = st.text_area("붙여넣기", height=150)
            if st.button("적용"):
                try:
                    sep = "\t" if "\t" in pasted else ","
                    df = pd.read_csv(io.StringIO(pasted), sep=sep, dtype=str).fillna("")
                    df.columns = [c.strip() for c in df.columns]
                    raw = df.to_dict("records")
                    cleaned = [clean_passenger(p) for p in raw]
                    st.session_state.passengers = raw
                    st.session_state.cleaned_passengers = cleaned
                    st.success(f"✅ {len(cleaned)}명 적용")
                except Exception as e:
                    st.error(f"파싱 오류: {e}")

    # ── 검증 결과 ────────────────────────────────────────────
    if st.session_state.cleaned_passengers:
        passengers = st.session_state.cleaned_passengers
        common = st.session_state.common_info
        _, all_errors = validate_all(passengers, common)

        c1, c2, c3 = st.columns(3)
        c1.metric("승객 수", len(passengers))
        c2.metric("정상", len(passengers) - len(all_errors))
        c3.metric("오류", len(all_errors))

        if all_errors:
            for err in all_errors:
                st.error(err)
        else:
            st.success("✅ 모든 데이터 정상 — 미리보기/출력으로 이동하세요.")

        rows = []
        for p in passengers:
            errs = validate_passenger(int(str(p.get("NO", 0)) or 0), p, common)
            rows.append({
                "NO": p.get("NO", ""), "영문이름": p.get("영문이름", ""),
                "생년월일": p.get("생년월일", ""), "여권번호": p.get("여권번호", ""),
                "상태": "✅" if not errs else f"❌ {len(errs)}건",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# 화면 2: 미리보기
# ══════════════════════════════════════════════════════════════
elif menu == "2. 미리보기":
    st.title("미리보기")

    if not st.session_state.cleaned_passengers:
        st.warning("먼저 '1. 정보 & 명단'에서 명단을 업로드하세요.")
        st.stop()

    passengers = st.session_state.cleaned_passengers
    common = st.session_state.common_info

    col_a, col_b = st.columns([3, 1])
    with col_a:
        pax_idx = st.selectbox(
            "승객 선택",
            range(len(passengers)),
            format_func=lambda i: f"{passengers[i].get('NO','')}: {passengers[i].get('영문이름','')}",
        )
    with col_b:
        form_choice = st.radio("양식", ["출입국카드", "휴대품신고서"], horizontal=False)

    passenger = passengers[pax_idx]

    with st.spinner("이미지 생성 중..."):
        if form_choice == "출입국카드":
            preview_img = _render_imm_image(passenger, common)
        else:
            positions = load_positions("customs_declaration")
            jpg_bytes = st.session_state.cus_jpg_bytes
            tmp_jpg = _write_jpg_to_tmp(jpg_bytes) if jpg_bytes else None
            preview_img = generate_preview_image(
                "customs_declaration", passenger, common, positions, tmp_jpg, scale=1.0
            )
            if tmp_jpg and os.path.exists(tmp_jpg):
                os.unlink(tmp_jpg)

    st.image(preview_img,
             caption=f"{passenger.get('영문이름','')} — {form_choice}",
             use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 화면 3: 출력
# ══════════════════════════════════════════════════════════════
elif menu == "3. 출력":
    st.title("인쇄 / PDF 출력")

    if not st.session_state.cleaned_passengers:
        st.warning("먼저 '1. 정보 & 명단'에서 명단을 업로드하세요.")
        st.stop()

    passengers = st.session_state.cleaned_passengers
    common = st.session_state.common_info

    col1, col2 = st.columns(2)
    with col1:
        target = st.radio("출력 대상", ["전체 승객", "선택 승객"])
        if target == "선택 승객":
            selected_indices = st.multiselect(
                "승객 선택",
                range(len(passengers)),
                format_func=lambda i: f"{passengers[i].get('NO','')}: {passengers[i].get('영문이름','')}",
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

    st.divider()

    # ── 웹 인쇄 ─────────────────────────────────────────────
    st.subheader("🖨 웹 인쇄 (권장)")
    st.caption("버튼 클릭 → 새 탭 열림 → Ctrl+P")

    if st.button("🖨 인쇄 미리보기 열기", type="primary"):
        with st.spinner(f"{n}명 이미지 생성 중..."):
            images_b64 = []
            cus_positions = load_positions("customs_declaration")
            cus_tmp = _write_jpg_to_tmp(st.session_state.cus_jpg_bytes) if st.session_state.cus_jpg_bytes else None

            for p in selected_passengers:
                if include_imm:
                    img = _render_imm_image(p, common)
                    images_b64.append(_img_to_base64(img))
                if include_cus:
                    img = generate_preview_image(
                        "customs_declaration", p, common, cus_positions, cus_tmp, scale=1.0
                    )
                    images_b64.append(_img_to_base64(img))

            if cus_tmp and os.path.exists(cus_tmp):
                os.unlink(cus_tmp)

        html = _build_print_html(images_b64, title=f"입국서류 {n}명")
        html_b64 = base64.b64encode(html.encode("utf-8")).decode()
        components.html(f"""
        <script>
        const html = atob("{html_b64}");
        const blob = new Blob([html], {{type: 'text/html'}});
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        </script>""", height=0)
        st.success(f"✅ {len(images_b64)}페이지 — 새 탭이 열립니다.")
        st.info("팝업 차단 시: 주소창 우측 팝업 허용 클릭")

    st.divider()

    # ── PDF 다운로드 ─────────────────────────────────────────
    st.subheader("📄 PDF 다운로드")

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("📄 통합 PDF"):
            with st.spinner("PDF 생성 중..."):
                pages = []
                cus_positions = load_positions("customs_declaration")
                cus_tmp = _write_jpg_to_tmp(st.session_state.cus_jpg_bytes) if st.session_state.cus_jpg_bytes else None

                for p in selected_passengers:
                    if include_imm:
                        pages.append(_render_imm_image(p, common).convert("RGB"))
                    if include_cus:
                        img = generate_preview_image(
                            "customs_declaration", p, common, cus_positions, cus_tmp, scale=1.0
                        )
                        pages.append(img.convert("RGB"))

                if cus_tmp and os.path.exists(cus_tmp):
                    os.unlink(cus_tmp)

                buf = io.BytesIO()
                if pages:
                    pages[0].save(buf, format="PDF", save_all=True,
                                  append_images=pages[1:], resolution=200)
                buf.seek(0)
                pdf_bytes = buf.read()

            st.download_button(
                label=f"📥 통합 PDF ({n}명, {len(pdf_bytes)//1024}KB)",
                data=pdf_bytes,
                file_name="immigration_forms.pdf",
                mime="application/pdf",
            )

    with col_b:
        if st.button("📦 개인별 ZIP"):
            with st.spinner("생성 중..."):
                zip_buf = io.BytesIO()
                cus_positions = load_positions("customs_declaration")
                cus_tmp = _write_jpg_to_tmp(st.session_state.cus_jpg_bytes) if st.session_state.cus_jpg_bytes else None

                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for p in selected_passengers:
                        name_safe = p.get("영문이름", "unknown").replace(" ", "_").replace("/", "-")
                        no = p.get("NO", "")

                        if include_imm:
                            img = _render_imm_image(p, common).convert("RGB")
                            buf = io.BytesIO()
                            img.save(buf, format="PDF", resolution=200)
                            zf.writestr(f"{no}_{name_safe}_immigration.pdf", buf.getvalue())

                        if include_cus:
                            img = generate_preview_image(
                                "customs_declaration", p, common, cus_positions, cus_tmp, scale=1.0
                            ).convert("RGB")
                            buf = io.BytesIO()
                            img.save(buf, format="PDF", resolution=200)
                            zf.writestr(f"{no}_{name_safe}_customs.pdf", buf.getvalue())

                if cus_tmp and os.path.exists(cus_tmp):
                    os.unlink(cus_tmp)

            zip_buf.seek(0)
            st.download_button(
                label=f"📥 ZIP ({n}명)",
                data=zip_buf.read(),
                file_name="immigration_forms.zip",
                mime="application/zip",
            )
