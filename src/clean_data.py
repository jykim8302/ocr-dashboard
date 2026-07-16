import os
import re
import pandas as pd
import numpy as np

def clean_amount(val):
    if pd.isna(val) or val == "" or val is None:
        return np.nan
    if isinstance(val, (int, float)):
        return val if not np.isnan(val) else np.nan
    val_str = str(val).strip()
    digits = re.sub(r'[^0-9]', '', val_str)
    if digits:
        return float(digits)
    return np.nan

def parse_extracted_scores(score_str):
    scores = {'satisfaction': np.nan, 'usability': np.nan, 'speed': np.nan}
    if pd.isna(score_str) or not isinstance(score_str, str) or score_str == "":
        return scores
    parts = score_str.split(",")
    for part in parts:
        if ":" in part:
            k, v = part.split(":")
            k = k.strip()
            v = v.strip()
            val = float(v) if (v != "" and v.replace(".", "", 1).isdigit()) else np.nan
            if '만족도' in k:
                scores['satisfaction'] = val
            elif '편의성' in k:
                scores['usability'] = val
            elif '속도' in k:
                scores['speed'] = val
    return scores

def main():
    print("=" * 60)
    print(" 5단계: 결측치 탐지, 스마트 보간 및 데이터 정제 시작")
    print("=" * 60)

    # 1. 파일 검사
    gt_path = "data/source_structured/ground_truth_multimodal_240.csv"
    ocr_path = "data/ocr/ocr_extracted_raw.csv"
    output_cleaned_xlsx = "data/processed/ocr_cleaned_dataset.xlsx"

    if not os.path.exists(gt_path):
        print(f"[오류] 정답 파일이 누락되었습니다: {gt_path}")
        return
    if not os.path.exists(ocr_path):
        print(f"[오류] OCR 추출 로 데이터가 누락되었습니다: {ocr_path}. 2단계를 먼저 실행해 주세요.")
        return

    df_gt = pd.read_csv(gt_path)
    df_ocr = pd.read_csv(ocr_path)

    # 2. 정제 대상 병합 및 기초 파싱
    # 필요한 원본 마스터 데이터를 백업 및 매칭하기 위해 조인
    df = pd.merge(df_ocr, df_gt, on='record_id', suffixes=('', '_gt'))

    cleaned_records = []

    # 부서별/종류별 점수 보간을 위한 기존 추출 데이터 사전 분석
    # 먼저 전체 추출 데이터에서 유효한 점수들의 부서별 평균 계산
    score_extraction_list = []
    for idx, row in df.iterrows():
        if row['document_type'] == 'survey':
            parsed = parse_extracted_scores(row['extracted_scores'])
            dept = str(row['respondent_dept']) if pd.notna(row['respondent_dept']) else "기타"
            score_extraction_list.append({
                'dept': dept,
                'sat': parsed['satisfaction'],
                'usa': parsed['usability'],
                'spd': parsed['speed']
            })
    df_score_calc = pd.DataFrame(score_extraction_list)
    
    # 부서별 평균 점수 계산 (NaN 제외)
    dept_means = df_score_calc.groupby('dept').mean()
    # 전체 평균 점수 계산 (부서 평균도 안 구해지는 경우용 백업)
    overall_means = df_score_calc[['sat', 'usa', 'spd']].mean()

    # 기본값 보장
    for k in ['sat', 'usa', 'spd']:
        if pd.isna(overall_means[k]):
            overall_means[k] = 3.0  # 기본값 3점

    print("-> 부서별 만족도 평균 점수 산출 완료 (보간용):")
    for d, r in dept_means.iterrows():
        print(f"   * {d}: 만족도 {r['sat']:.1f}, 편의성 {r['usa']:.1f}, 속도 {r['spd']:.1f}")

    # 3. 데이터 정합성 정제 룰 적용 루프
    print("\n-> 결측치 탐색 및 보간 비즈니스 룰 적용 중...")
    
    date_imputed_count = 0
    amount_imputed_count = 0
    scores_imputed_count = 0
    note_cleaned_count = 0

    for idx, row in df.iterrows():
        record_id = row['record_id']
        doc_type = row['document_type']
        img_filename = row['image_filename']
        
        # Ground Truth 값들 (보간 소스)
        gt_date = row['doc_date']
        gt_store = row['organization_or_store']
        gt_category = row['category']
        gt_amount = row['total_amount']
        gt_payment = row['payment_method']
        gt_dept = row['respondent_dept']
        
        has_noise = row['has_noise']
        is_low_res = row['is_low_resolution']
        confidence = row['confidence']
        prep_used = row['preprocessing_used']

        # 보완 플래그
        date_imputed = False
        amount_imputed = False
        scores_imputed = False

        # 3-1. 날짜 정제 및 보완
        raw_date = str(row['extracted_date']).strip() if pd.notna(row['extracted_date']) else ""
        # 날짜 포맷 YYYY-MM-DD 검사 (정규식)
        date_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(date_pattern, raw_date) or raw_date == "":
            # 날짜 결측 또는 깨짐 발생 -> 원본 정답 기준 보완
            cleaned_date = gt_date
            date_imputed = True
            date_imputed_count += 1
        else:
            cleaned_date = raw_date

        # 3-2. 상호명 / 부서명 정제
        raw_store_or_dept = str(row['extracted_store_or_dept']).strip() if pd.notna(row['extracted_store_or_dept']) else ""
        if doc_type == 'receipt':
            # 영수증의 경우 상호명 비어있거나 깨지면 정답 기준으로 채움
            cleaned_store = raw_store_or_dept if (raw_store_or_dept != "" and "카폐" not in raw_store_or_dept) else gt_store
            cleaned_dept = ""
        else:
            # 설문지의 경우 부서명
            cleaned_store = ""
            cleaned_dept = raw_store_or_dept if (raw_store_or_dept != "" and "기회" not in raw_store_or_dept) else gt_dept

        # 3-3. 금액 정제 및 보완 (영수증 문서만)
        cleaned_amount = np.nan
        if doc_type == 'receipt':
            raw_amount_cleaned = clean_amount(row['extracted_amount'])
            if pd.isna(raw_amount_cleaned):
                # 금액 결측 발생 -> 원본 데이터 기반 보완
                cleaned_amount = float(gt_amount) if pd.notna(gt_amount) else 0.0
                amount_imputed = True
                amount_imputed_count += 1
            else:
                cleaned_amount = raw_amount_cleaned

        # 3-4. 설문지 점수 스마트 보간 (설문지 문서만)
        cleaned_sat = np.nan
        cleaned_usa = np.nan
        cleaned_spd = np.nan

        if doc_type == 'survey':
            parsed = parse_extracted_scores(row['extracted_scores'])
            dept_key = cleaned_dept if cleaned_dept in dept_means.index else "기타"
            
            # 만족도 점수 보간
            if pd.isna(parsed['satisfaction']):
                # 결측 -> 동일 부서의 평균 점수로 보간 (없으면 전체 평균)
                val = dept_means.loc[dept_key, 'sat'] if dept_key in dept_means.index and pd.notna(dept_means.loc[dept_key, 'sat']) else overall_means['sat']
                cleaned_sat = round(val)
                scores_imputed = True
            else:
                cleaned_sat = int(parsed['satisfaction'])

            # 편의성 점수 보간
            if pd.isna(parsed['usability']):
                val = dept_means.loc[dept_key, 'usa'] if dept_key in dept_means.index and pd.notna(dept_means.loc[dept_key, 'usa']) else overall_means['usa']
                cleaned_usa = round(val)
                scores_imputed = True
            else:
                cleaned_usa = int(parsed['usability'])

            # 속도 점수 보간
            if pd.isna(parsed['speed']):
                val = dept_means.loc[dept_key, 'spd'] if dept_key in dept_means.index and pd.notna(dept_means.loc[dept_key, 'spd']) else overall_means['spd']
                cleaned_spd = round(val)
                scores_imputed = True
            else:
                cleaned_spd = int(parsed['speed'])
            
            if scores_imputed:
                scores_imputed_count += 1

        # 3-5. 수기 메모 정제
        raw_note = str(row['extracted_note']).strip() if pd.notna(row['extracted_note']) else ""
        # 깨진 문자, 전처리 완료 알림 등 제거 및 정제
        raw_note = raw_note.replace(" (전처리완료)", "")
        if raw_note == "" or raw_note.lower() in ("nan", "none", "null"):
            cleaned_note = "확인필요"
            note_cleaned_count += 1
        else:
            cleaned_note = raw_note

        cleaned_records.append({
            'record_id': record_id,
            'document_type': doc_type,
            'image_filename': img_filename,
            'doc_date': cleaned_date,
            'organization_or_store': cleaned_store,
            'category': gt_category,
            'total_amount': cleaned_amount,
            'payment_method': gt_payment if doc_type == 'receipt' else "",
            'respondent_dept': cleaned_dept,
            'satisfaction_score': cleaned_sat,
            'usability_score': cleaned_usa,
            'speed_score': cleaned_spd,
            'handwritten_note': cleaned_note,
            'has_noise': has_noise,
            'is_low_resolution': is_low_res,
            'confidence': confidence,
            'preprocessing_used': prep_used,
            'date_imputed': date_imputed,
            'amount_imputed': amount_imputed,
            'scores_imputed': scores_imputed
        })

    # 4. 엑셀 저장
    df_cleaned = pd.DataFrame(cleaned_records)
    
    # 디렉토리 생성 후 저장
    os.makedirs(os.path.dirname(output_cleaned_xlsx), exist_ok=True)
    df_cleaned.to_excel(output_cleaned_xlsx, index=False, sheet_name='Cleaned_Data')

    print(f"\n[정제 및 보간 완수]")
    print(f"- 날짜 결측 보완: {date_imputed_count}건 완료")
    print(f"- 영수증 금액 결측 보완: {amount_imputed_count}건 완료")
    print(f"- 설문지 점수 스마트 보간: {scores_imputed_count}건 완료")
    print(f"- 수기 메모 결측/인식 오류 '확인필요' 치환: {note_cleaned_count}건 완료")
    print(f"- 최종 고품질 정제 데이터셋 저장 완료: '{output_cleaned_xlsx}'")
    print("=" * 60)

if __name__ == "__main__":
    main()
