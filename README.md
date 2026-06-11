# 일본 입국서류 자동출력 프로그램

외国人入国記録(출입국카드) + 휴대품·별송품 신고서를 단체 명단에서 자동으로 PDF 출력합니다.

---

## 설치

```bash
cd immigration-card-generator
pip install -r requirements.txt
```

---

## 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속

---

## 양식 JPG 파일 위치

```
templates/
├── immigration_card.jpg       ← 외国人入国記録 스캔본 (A4)
└── customs_declaration.jpg    ← 휴대품·별송품 신고서 스캔본 (A4)
```

- **A4 사이즈** JPG로 저장해야 좌표가 정확히 맞습니다.
- JPG가 없어도 실행은 가능하지만 미리보기/출력이 흰 배경에 텍스트만 나옵니다.

---

## 엑셀 명단 양식

| 컬럼 | 설명 | 입력 예 |
|------|------|---------|
| NO | 번호 | 1 |
| 영문이름 | 여권 영문명 | KIM/HYUNG KYOU |
| 생년월일 | 생년월일 | 1983-10-17 / 831017-2 / 19831017 |
| 여권번호 | 여권번호 | M12345678 |
| 성별 | 성별 | M / F / 남 / 여 / 1 / 2 |

샘플 파일 생성:
```bash
python create_sample.py
```

---

## 이름 변환 규칙

| 입력 | 출력 |
|------|------|
| KIM/HYUNG KYOU | KIM HYUNGKYOU |
| RYU/SE YEON | RYU SEYEON |
| KIM HYUNGKYOU | KIM HYUNGKYOU (그대로) |

---

## 생년월일 변환 규칙

| 입력 | 출력 |
|------|------|
| 1983-10-17 | 19831017 |
| 831017-2 | 19831017 (1900년대) |
| 090924-4 | 20090924 (2000년대) |
| 19831017 | 19831017 (그대로) |

---

## 좌표 설정 방법

1. 앱 실행 후 **4. 양식 위치 설정** 메뉴 진입
2. 출입국카드 / 휴대품신고서 선택
3. 필드 선택 후 x, y, font_size 등 수정
4. **5. 미리보기**에서 실시간 확인
5. **💾 설정 저장** 클릭

좌표 기준: A4 포인트 (595×842pt), 좌상단이 (0,0)

---

## PDF 생성 방법

1. **1. 행사정보 입력** → 공통 여행 정보 입력 후 저장
2. **2. 명단 업로드** → 엑셀/CSV 업로드
3. **3. 데이터 검증** → 오류 확인 및 수정
4. **5. 미리보기** → 좌표 확인
5. **6. PDF 생성** → 출력 대상/서류 선택 후 생성 및 다운로드

---

## 폴더 구조

```
immigration-card-generator/
├── app.py                          메인 앱
├── requirements.txt
├── create_sample.py                샘플 엑셀 생성
├── utils/
│   ├── data_cleaner.py             이름/날짜/성별 변환
│   ├── validator.py                데이터 검증
│   ├── position_manager.py         좌표 JSON 관리
│   └── pdf_generator.py            PDF/미리보기 생성
├── configs/
│   ├── immigration_card_positions.json
│   └── customs_declaration_positions.json
├── templates/                      ← JPG 양식 파일 여기에 넣기
├── sample/
│   └── sample_passengers.xlsx
└── output/generated/               생성된 PDF 저장
```
