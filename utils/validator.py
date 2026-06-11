import re
from typing import List, Tuple


REQUIRED_PASSENGER = ["영문이름", "생년월일", "여권번호", "성별"]
REQUIRED_COMMON = ["국적", "입국편명", "입국일", "호텔이름", "호텔전화번호"]


def validate_passenger(idx: int, passenger: dict, common_info: dict) -> List[str]:
    """
    단일 승객 검증. 오류 문자열 목록 반환.
    idx: 1-based 번호
    """
    errors = []
    no = passenger.get("NO", idx)
    name = passenger.get("영문이름", f"#{idx}")
    prefix = f"{no}번 {name}"

    # 필수 승객 필드
    if not passenger.get("영문이름", "").strip():
        errors.append(f"{prefix}: 영문이름 없음")

    dob = str(passenger.get("생년월일", "")).strip()
    if not dob:
        errors.append(f"{prefix}: 생년월일 없음")
    elif not re.match(r"^\d{8}$", dob):
        errors.append(f"{prefix}: 생년월일 형식 오류 (YYYYMMDD 아님: '{dob}')")

    if not passenger.get("여권번호", "").strip():
        errors.append(f"{prefix}: 여권번호 없음")

    gender = str(passenger.get("성별", "")).strip()
    if not gender:
        errors.append(f"{prefix}: 성별 없음")
    elif gender not in ["M", "F"]:
        errors.append(f"{prefix}: 성별 오류 (M/F 아님: '{gender}')")

    # 필수 공통 필드
    for field in REQUIRED_COMMON:
        if not str(common_info.get(field, "")).strip():
            errors.append(f"{prefix}: 공통정보 '{field}' 없음")

    # 이름 길이 경고 (칸 초과 가능성)
    name_val = passenger.get("영문이름", "")
    if len(name_val) > 25:
        errors.append(f"{prefix}: 이름이 길어 칸 초과 가능 ({len(name_val)}자)")

    return errors


def validate_all(passengers: List[dict], common_info: dict) -> Tuple[List[dict], List[str]]:
    """
    전체 승객 검증.
    반환: (정상 승객 목록, 오류 메시지 목록)
    """
    all_errors = []
    valid_passengers = []

    for i, p in enumerate(passengers, 1):
        errs = validate_passenger(i, p, common_info)
        if errs:
            all_errors.extend(errs)
        else:
            valid_passengers.append(p)

    return valid_passengers, all_errors
