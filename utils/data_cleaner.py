import re


def normalize_name(name: str) -> str:
    """
    KIM/HYUNG KYOU → KIM HYUNGKYOU
    KIM HYUNG KYOU → KIM HYUNGKYOU
    KIM HYUNGKYOU  → KIM HYUNGKYOU (그대로)
    """
    if not name or not isinstance(name, str):
        return ""

    name = name.strip().upper()

    # 하이픈을 슬래시처럼 처리 (KIM-GILDONG → KIM/GILDONG)
    if "-" in name and "/" not in name:
        name = name.replace("-", "/", 1)

    if "/" in name:
        parts = name.split("/", 1)
        family = parts[0].strip()
        given = parts[1].strip().replace(" ", "")
        return f"{family} {given}"
    else:
        parts = name.split(" ", 1)
        if len(parts) == 2:
            family = parts[0].strip()
            given = parts[1].strip().replace(" ", "")
            return f"{family} {given}"
        return name


def normalize_birthdate(dob) -> str:
    """
    1983-10-17  → 19831017
    19831017    → 19831017
    831017-2    → 19831017  (1900s: suffix 1,2)
    090924-4    → 20090924  (2000s: suffix 3,4)
    831017      → 19831017  (suffix 없으면 yy>24 → 19xx, else 20xx)
    """
    if dob is None:
        return ""

    dob = str(dob).strip()

    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", dob):
        return dob.replace("-", "")

    # YYYYMMDD
    if re.match(r"^\d{8}$", dob):
        return dob

    # YYMMDD-N
    m = re.match(r"^(\d{6})-?(\d)$", dob)
    if m:
        yymmdd, suffix = m.group(1), int(m.group(2))
        yy = int(yymmdd[:2])
        mm = yymmdd[2:4]
        dd = yymmdd[4:6]
        century = "19" if suffix in [1, 2] else "20"
        return f"{century}{yymmdd[:2]}{mm}{dd}"

    # YYMMDD (6자리)
    if re.match(r"^\d{6}$", dob):
        yy = int(dob[:2])
        century = "19" if yy > 24 else "20"
        return f"{century}{dob}"

    # 숫자만 추출 8자리
    digits = re.sub(r"\D", "", dob)
    if len(digits) == 8:
        return digits

    return dob


def normalize_gender(gender) -> str:
    """M/F/남/여/MR/MS/1/2/3/4 → M 또는 F"""
    if not gender:
        return ""

    g = str(gender).strip().upper()

    if g in ["M", "남", "남자", "MR", "1", "3", "MALE"]:
        return "M"
    if g in ["F", "여", "여자", "MS", "2", "4", "FEMALE"]:
        return "F"

    if g and g[0] in ["M", "1", "3"]:
        return "M"
    if g and g[0] in ["F", "2", "4"]:
        return "F"

    return g


def clean_passenger(passenger: dict) -> dict:
    """승객 레코드 정규화. 원본값은 _원본 키로 보존."""
    cleaned = passenger.copy()

    for field in ["영문이름", "생년월일", "성별"]:
        if field in cleaned:
            cleaned[f"{field}_원본"] = cleaned[field]

    if "영문이름" in cleaned:
        cleaned["영문이름"] = normalize_name(str(cleaned["영문이름"]))

    if "생년월일" in cleaned:
        cleaned["생년월일"] = normalize_birthdate(cleaned["생년월일"])

    if "성별" in cleaned:
        cleaned["성별"] = normalize_gender(cleaned["성별"])

    return cleaned
