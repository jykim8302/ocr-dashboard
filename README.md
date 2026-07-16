# 📊 Project 2: 멀티모달 OCR 분석 대시보드 실습 프로젝트

본 프로젝트는 수강생들이 **크롤링이나 코드 수정 없이** 제공된 정형 정답 데이터와 영수증/수기 설문지 이미지 데이터를 연계하여, **"데이터 매칭 검증 ➔ OpenCV 전처리 ➔ 가상 OCR 추출 ➔ 품질 평가 및 정확도 비교 ➔ 데이터 정제(스마트 결측치 보완) ➔ 프리미엄 Streamlit 대시보드 시각화"**에 이르는 데이터 파이프라인 전 과정을 학습할 수 있도록 완벽하게 세팅된 실습 환경입니다.

---

## 📂 프로젝트 폴더 구조

프로젝트는 교육적 목적과 유지보수성을 극대화하기 위해 다음과 같은 체계적인 구조로 설계되었습니다.

```text
project2_vision_ocr_dashboard/ (프로젝트 루트)
├─ data/
│  ├─ source_structured/               # 원본 정형 정답 데이터 및 프리뷰
│  │  ├─ ground_truth_multimodal_240.csv   # OCR 정답 기준 데이터 (Ground Truth)
│  │  ├─ ground_truth_multimodal_240.xlsx  # Excel 버전
│  │  └─ image_contact_sheet_preview.jpg   # 이미지 프리뷰 시트
│  ├─ input_images/                    # 실습용 실제 이미지 데이터 (240장)
│  │  ├─ receipts/                         # 영수증 이미지 120장
│  │  └─ surveys/                          # 수기 설문지 이미지 120장
│  ├─ ocr/                             # OCR 가공 결과 폴더 [자동 생성]
│  │  ├─ preprocessed_images/              # OpenCV로 이진화/Denoise된 전처리 이미지 저장소
│  │  └─ ocr_extracted_raw.csv             # OCR 추출 Raw 데이터
│  └─ processed/                       # 최종 정제 데이터 폴더 [자동 생성]
│     └─ ocr_cleaned_dataset.xlsx          # 최종 정제 및 보완된 분석용 마스터셋
├─ app/                                # Streamlit 웹 대시보드 폴더 [자동 생성]
│  └─ vision_dashboard.py                  # 임원 보고용 스타일 대시보드 앱
├─ reports/                            # 실무 보고서 및 품질 평가서 폴더 [자동 생성]
│  ├─ data_image_validation_report.txt     # 1단계: 원본 데이터-이미지 매칭 검증 보고서
│  ├─ ocr_quality_report.xlsx              # 3단계: 상세 OCR 정확도 평가 엑셀 (전처리 전후 비교)
│  └─ ocr_quality_summary.txt              # 3단계: OCR 성능 분석 요약 텍스트 리포트
├─ src/                                # 데이터 파이프라인 백엔드 스크립트 폴더
│  ├─ validate_data.py                     # 1단계: 데이터-이미지 1:1 매칭성 검증
│  ├─ ocr_extractor.py                     # 2단계: OpenCV 전처리 + 가상 OCR 추출기
│  ├─ evaluate_ocr.py                      # 3단계: OCR 정확도 정량 평가기
│  └─ clean_data.py                        # 4단계: 결측치 보간 및 데이터 표준화 정제
├─ requirements.txt                    # 프로젝트 필수 라이브러리 목록
└─ README.md                           # 프로젝트 실행 가이드 (본 파일)
```

---

## ⚡ 빠른 실행 가이드 (Quick Start)

본 프로젝트는 초고속 파이썬 패키지 매니저인 `uv`를 기본 탑재하고 있어, 복잡한 파이썬 환경 설정이나 설치 과정 없이 단 몇 초 만에 격리된 가상 환경을 생성하고 파이프라인을 가동할 수 있습니다.

### 0. 사전 준비 (uv 가상환경 생성 및 패키지 설치)

터미널(PowerShell 또는 CMD)을 열고 프로젝트 루트 폴더에서 아래 명령어들을 차례대로 실행하세요.

```powershell
# 1. 초고속 파이썬 가상환경 생성 (파이썬이 안 깔려있어도 자동으로 다운로드합니다!)
uv venv

# 2. 필수 패키지 일괄 설치 (pandas, opencv, streamlit, plotly, openpyxl 등)
uv pip install -r requirements.txt
```

---

## 💻 데이터 파이프라인 구동 단계 (1~5단계)

파이썬 환경 구축이 끝났다면, 아래 5개 단계를 순서대로 실행하며 데이터가 흘러가는 구조를 파악합니다.

### 1단계: 원본 데이터 & 이미지 매칭 검증 (`validate_data.py`)
제공된 CSV 파일 속 파일명(`image_filename`)과 실제 폴더 내 240장 이미지의 파일 유무, 중복 ID 등을 물리적으로 교차 대조합니다.
```powershell
uv run src/validate_data.py
```
* **결과 확인**: `reports/data_image_validation_report.txt` 가 생성되어 매칭 정합성(100% 안전)을 보고합니다.

---

### 2단계: OpenCV 이미지 전처리 & 가상 OCR 추출 (`ocr_extractor.py`)
이미지의 화질 상태(`has_noise`, `is_low_resolution`)에 따라 OCR 추출 정확도가 어떻게 바뀌는지 시뮬레이션하고, OpenCV를 통해 노이즈 제거 및 명암 조절을 실행합니다.

#### 옵션 A: OpenCV 이미지 전처리를 적용하여 정확도 극대화하기 (강력 추천 ★)
```powershell
uv run src/ocr_extractor.py --preprocess
```
* **동작**: `data/input_images/` 속 원본 이미지들을 로딩하여 **Grayscale 변환 ➔ 대비 향상(CLAHE) ➔ 가우시안 블러(노이즈 제거) ➔ 적응형 이진화(Thresholding)**를 적용한 가독성 보정 이미지 240장을 `data/ocr/preprocessed_images/` 폴더에 실시간 생성하며 높은 신뢰도로 OCR 결과를 모사합니다.

#### 옵션 B: 전처리를 적용하지 않고 오염된 채로 기본 추출하기
```powershell
uv run src/ocr_extractor.py
```
* **동작**: 전처리를 미적용한 채 가공하므로, 노이즈나 저해상도 이미지 영역에서 추출 문자 깨짐, 날짜 공백, 수기 메모 판독 실패 등이 발생하여 신뢰도가 대폭 낮게 추출됩니다.

---

### 3단계: OCR 추출 품질 및 정확도 정량 평가 (`evaluate_ocr.py`)
OCR 원시 결과 데이터(`ocr_extracted_raw.csv`)와 정답 데이터(`ground_truth_multimodal_240.csv`)를 `record_id` 기준으로 조인하여 정밀 비교 평가를 진행합니다.
```powershell
uv run src/evaluate_ocr.py
```
* **결과 확인**: 
  * `reports/ocr_quality_report.xlsx` (상세 비교 평가 엑셀)
  * `reports/ocr_quality_summary.txt` (요약 텍스트 보고서 - **전처리 적용 전후 성능 비교 등 교육 지표 탑재**)

---

### 4단계: 결측치 탐지, 스마트 보간 및 데이터 표준화 정제 (`clean_data.py`)
실무에서 불가피하게 발생하는 OCR 누락/깨짐 데이터에 비즈니스 임퓨테이션(Imputation) 규칙을 적용하여 정형 데이터셋으로 변환합니다.
- **날짜 누락**: 원본 정답 마스터 테이블에서 누락 날짜 자동 복구 및 `YYYY-MM-DD` 표준 포맷 정규화
- **금액 누락**: 영수증(`receipt`) 문서인 경우 원본 금액으로 보충 후 보완 플래그(`amount_imputed = True`) 마킹
- **설문 점수 누락**: **동일한 부서(respondent_dept)의 다른 설문 응답 평균점수로 스마트 보간** 후 보완 플래그(`scores_imputed = True`) 마킹
- **메모 누락/인식에러**: 비어있거나 판독 불능 메모는 `'확인필요'` 텍스트로 보완
```powershell
uv run src/clean_data.py
```
* **결과 확인**: `data/processed/ocr_cleaned_dataset.xlsx` 정제된 마스터 데이터셋이 완성됩니다.

---

### 5단계: 임원 보고용 멀티모달 OCR 분석 대시보드 실행 (`vision_dashboard.py`)
정제가 완료된 분석용 데이터셋(`ocr_cleaned_dataset.xlsx`)을 사용하여, 한눈에 전처리 효과와 집행 통계를 파악할 수 있는 프리미엄 대시보드를 구동합니다.
```powershell
uv run streamlit run app/vision_dashboard.py
```
* **구동 확인**: 브라우저 창이 열리며 네이비/화이트/민트 톤의 고품격 인터랙티브 화면이 구동됩니다.
* **대시보드 주요 특징**:
  - **4대 KPI 카드**: 전체 분석 문서 수, 원시 OCR 추출 성공률, 스마트 결측치 보완 건수, 평균 만족도 또는 영수증 집행 총합 표시
  - **범주별 세부 분석**: 영수증 카테고리별 집행 비율(Plotly 도넛 차트) 및 부서별 설문 3대 지표 평균 비교(Plotly 그룹 막대 차트)
  - **OpenCV 전처리 가시성 검증**: 노이즈 상태에 따른 OCR 정확도 대비 및 전처리 보정 전후 복구율 시각화 그래프 제공
  - **수동 검증 테이블**: 신뢰도가 너무 낮거나 보간이 적용된 건, 수기내용 '확인필요' 대상을 실시간 검색할 수 있는 세련된 데이터 테이블

---

## 🎓 교육 및 실습 제언 (교수자/수강생 가이드)

1. **시나리오 비교 실습**:
   - 수강생들에게 먼저 **[2단계 옵션 B] (전처리 미적용 추출) ➔ [3단계 품질평가] ➔ [4단계 정제] ➔ [5단계 대시보드]**를 구동하게 하여, 저해상도 이미지에서 인식률이 얼마나 붕괴되는지(정밀도 약 43%), 그리고 이에 따라 4단계에서 얼마나 많은 누락 보완건이 발생하는지 대시보드로 통계를 확인하게 합니다.
   - 그 다음 **[2단계 옵션 A] (OpenCV 전처리 적용 추출) ➔ [3단계 품질평가] ➔ [4단계 정제] ➔ [5단계 대시보드]**를 구동하게 하여, 간단한 OpenCV 이진화 및 필터 처리를 통해 데이터 신뢰도가 어떻게 복구되고 대시보드의 점검 필요 대상 목록이 어떻게 줄어드는지 실시간 비교 체험하게 함으로써 **"이미지 전처리 엔지니어링의 위력"**을 생생하게 체득할 수 있습니다.
