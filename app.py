"""
immigration-card-generator
일본 입국 서류 자동 출력 프로그램 — 클라우드 버전
"""
import io
import os
import tempfile
import zipfile
from pathlib import Path
from datetime import date

import pandas as pd
import streamlit as st

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
        "imm_jpg_bytes": None,   # 출입국카드 JPG (bytes)
        "cus_jpg_bytes": None,   # 휴대품신고서 JPG (bytes)
        "imm_positions": None,
        "cus_positions": None,
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


def _write_jpg_to_tmp(jpg_bytes: bytes, suffix: str) -> str:
    """JPG bytes를 임시 파일로 저장하고 경로 반환."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(jpg_bytes)
    tmp.close()
    return tmp.name


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
        "6. PDF 생성",
    ],
    label_visibility="collapsed",
)

# 승객 수
if st.session_state.cleaned_passengers:
    st.sidebar.success(f"✅ 승객 {len(st.session_state.cleaned_passengers)}명")
else:
    st.sidebar.warning("⚠ 명단 없음")

# 템플릿 JPG 업로드 (사이드바 상시 표시)
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

st.sidebar.caption("업로드하지 않으면 흰 배경으로 출력됩니다")


# ══════════════════════════════════════════════════════════════
# 화면 1: 행사정보 입력
# ══════════════════════════════════════════════════════════════
if menu == "1. 행사정보 입력":
    st.title("행사정보 입력")
    st.markdown("모든 승객에게 공통으로 적용되는 여행 정보입니다.")

    ci = st.session_state.common_info

    col1, col2 = st.columns(2)
    with col1:
        ci["국적"] = st.text_input("국적 (Nationality)", value=ci["국적"]).upper()
        ci["도시"] = st.text_input("출발도시 (Departure City)", value=ci["도시"]).upper()
        ci["입국편명"] = st.text_input("입국편명 (Flight No.)", value=ci["입국편명"]).upper()
        ci["여행기간"] = st.text_input(
            "체류예정기간 (Stay Duration)", value=ci["여행기간"],
            help="예: 7 DAYS / 3 NIGHTS 4 DAYS"
        )
    with col2:
        ci["입국일"] = st.text_input(
            "입국일 (Entry Date)", value=ci["입국일"],
            help="YYYY-MM-DD 형식"
        )
        ci["호텔이름"] = st.text_input("호텔이름 (Hotel Name)", value=ci["호텔이름"]).upper()
        ci["호텔전화번호"] = st.text_input("호텔전화번호 (Hotel TEL)", value=ci["호텔전화번호"])
        ci["여행목적"] = st.selectbox(
            "여행목적 (Purpose)",
            ["관광", "상용", "친족방문", "기타"],
            index=["관광", "상용", "친족방문", "기타"].index(ci.get("여행목적", "관광")),
        )

    if st.button("💾 저장", type="primary"):
        st.session_state.common_info = ci
        st.success("행사정보가 저장되었습니다.")

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

        # 샘플 엑셀 다운로드
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

    # 변환 결과 비교
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
            st.success("✅ 모든 데이터 정상 — PDF 생성 가능합니다.")

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
    st.info("📐 좌표 기준: A4 포인트 (좌상단=0,0 / A4=595×842pt)\n\n미리보기에서 확인하면서 x/y를 조정하세요.")

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
            defaults = get_default_positions(form_type)
            _save_session_positions(form_type, defaults)
            st.success("초기화 완료! 페이지를 새로고침하세요.")

    st.divider()
    st.subheader("전체 필드 좌표")
    table_rows = [
        {
            "key": k,
            "label": v.get("label", ""),
            "type": v.get("type", "text"),
            "x": v.get("x", 0),
            "y": v.get("y", 0),
            "width": v.get("width", "-"),
            "font_size": v.get("font_size", 9),
            "cell_gap": v.get("cell_gap", "-"),
        }
        for k, v in positions.items()
    ]
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True)


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

        # JPG 임시파일 경로
        jpg_bytes = (
            st.session_state.imm_jpg_bytes
            if form_type == "immigration_card"
            else st.session_state.cus_jpg_bytes
        )
        tmp_jpg = None
        if jpg_bytes:
            tmp_jpg = _write_jpg_to_tmp(jpg_bytes, ".jpg")

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
# 화면 6: PDF 생성
# ══════════════════════════════════════════════════════════════
elif menu == "6. PDF 생성":
    st.title("PDF 생성")

    if not st.session_state.cleaned_passengers:
        st.warning("먼저 명단을 업로드하세요.")
    else:
        passengers = st.session_state.cleaned_passengers
        common = st.session_state.common_info

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

        st.info(
            f"출력 예정: {len(selected_passengers)}명 × "
            f"{'출입국카드' if include_imm else ''}"
            f"{'＋' if include_imm and include_cus else ''}"
            f"{'휴대품신고서' if include_cus else ''}"
        )

        imm_positions = _get_positions("immigration_card")
        cus_positions = _get_positions("customs_declaration")

        # JPG 임시파일 준비
        imm_tmp = _write_jpg_to_tmp(st.session_state.imm_jpg_bytes, ".jpg") if st.session_state.imm_jpg_bytes else None
        cus_tmp = _write_jpg_to_tmp(st.session_state.cus_jpg_bytes, ".jpg") if st.session_state.cus_jpg_bytes else None

        # ── 통합 PDF 생성 ──────────────────────────────────
        if st.button("🖨 통합 PDF 생성", type="primary", disabled=len(selected_passengers) == 0):
            with st.spinner("PDF 생성 중..."):
                out_buf = io.BytesIO()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                    tmp_pdf_path = tmp_pdf.name

                result = generate_combined_pdf(
                    passengers=selected_passengers,
                    common=common,
                    imm_positions=imm_positions,
                    cus_positions=cus_positions,
                    imm_template=imm_tmp,
                    cus_template=cus_tmp,
                    output_path=tmp_pdf_path,
                    include_immigration=include_imm,
                    include_customs=include_cus,
                )
                with open(tmp_pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                os.unlink(tmp_pdf_path)

            if result["warns"]:
                st.warning(f"⚠ 글자 자동 축소 필드: {', '.join(set(result['warns']))}")

            st.download_button(
                label=f"📥 통합 PDF 다운로드 ({result['count']}명, {len(pdf_bytes)//1024}KB)",
                data=pdf_bytes,
                file_name="immigration_forms.pdf",
                mime="application/pdf",
            )

        st.divider()

        # ── 개인별 ZIP 생성 ────────────────────────────────
        if st.button("📦 개인별 PDF → ZIP", disabled=len(selected_passengers) == 0):
            zip_buf = io.BytesIO()
            warns_all = []

            with st.spinner("개인별 PDF 생성 중..."):
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for p in selected_passengers:
                        name_safe = p.get("영문이름", "unknown").replace(" ", "_")
                        no = p.get("NO", "")

                        if include_imm:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                                fp = f.name
                            w = generate_single_pdf(
                                "immigration_card", p, common, imm_positions, imm_tmp, fp
                            )
                            warns_all.extend(w)
                            zf.write(fp, f"{no}_{name_safe}_immigration.pdf")
                            os.unlink(fp)

                        if include_cus:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                                fp = f.name
                            w = generate_single_pdf(
                                "customs_declaration", p, common, cus_positions, cus_tmp, fp
                            )
                            warns_all.extend(w)
                            zf.write(fp, f"{no}_{name_safe}_customs.pdf")
                            os.unlink(fp)

            if warns_all:
                st.warning(f"⚠ 자동 축소 필드: {', '.join(set(warns_all))}")

            zip_buf.seek(0)
            st.download_button(
                label=f"📥 ZIP 다운로드 ({len(selected_passengers)}명)",
                data=zip_buf.read(),
                file_name="immigration_forms_individual.zip",
                mime="application/zip",
            )

        # 임시파일 정리
        if imm_tmp and os.path.exists(imm_tmp):
            os.unlink(imm_tmp)
        if cus_tmp and os.path.exists(cus_tmp):
            os.unlink(cus_tmp)
