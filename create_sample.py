"""샘플 엑셀 파일 생성 스크립트"""
from pathlib import Path
import pandas as pd

sample_data = {
    "NO": [1, 2, 3, 4, 5],
    "영문이름": [
        "KIM/HYUNG KYOU",
        "RYU/SE YEON",
        "CHOI/HYUN WOO",
        "PARK/SEON LYEOL",
        "LEE/JI YEON",
    ],
    "생년월일": [
        "1982-11-24",
        "1983-10-17",
        "090924-4",
        "19750305",
        "831017-2",
    ],
    "여권번호": [
        "M12345678",
        "M98765432",
        "M55555555",
        "M11111111",
        "M22222222",
    ],
    "성별": ["M", "F", "여", "M", "F"],
}

out = Path(__file__).parent / "sample" / "sample_passengers.xlsx"
out.parent.mkdir(exist_ok=True)
pd.DataFrame(sample_data).to_excel(out, index=False)
print(f"샘플 파일 생성: {out}")
