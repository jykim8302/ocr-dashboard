import os
import re
import pandas as pd
import numpy as np

def clean_amount(val):
    """
    추출된 금액 데이터에서 숫자만 남기고 정수로 변환을 시도합니다.
    """
    if pd.isna(val) or val == "" or val is None:
        return np.nan
    
    # 만약 정수나 실수형이면 바로 반환
    if isinstance(val, (int, float)):
        return val if not np.isnan(val) else np.nan

    # 문자열인 경우 숫자만 추출
    val_str = str(val).strip()
    digits = re.sub(r'[^0-9]', '', val_str)
    if digits:
        return float(digits)
    return np.nan

def parse_extracted_scores(score_str):
    """
    "만족도:5, 편의성:5, 속도:1" 형식의 문자열에서 개별 점수를 파싱합니다.
    """
    scores = {'satisfaction': np.nan, 'usability': np.nan, 'speed': np.nan}
    if pd.isna(score_str) or not isinstance(score_str, str) or score_str == "":
        return scores
    
    parts = score_str.split(",")
    for part in parts:
        if ":" in part:
            k, v = part.split(":")
            k = k.strip()
            v = v.strip()
            val = float(v) if v.isdigit() else np.nan
            if '만족도' in k:
                scores['satisfaction'] = val
            elif '편의성' in k:
                scores['usability'] = val
            elif '속도' in k:
                scores['speed'] = val
    return scores

def main():
    print("=" * 60)
    print(" 4단계: OCR 품질 평가 및 정확도 비교 분석 시작")
    print("=" * 60)

    # 1. 파일 확인
    gt_path = "data/source_structured/ground_truth_multimodal_240.csv"
    ocr_path = "data/ocr/ocr_extracted_raw.csv"
    report_xlsx = "reports/ocr_quality_report.xlsx"
    report_summary_txt = "reports/ocr_quality_summary.txt"

    if not os.path.exists(gt_path):
        print(f"[오류] 정답 파일이 누락되었습니다: {gt_path}")
        return
    if not os.path.exists(ocr_path):
        print(f"[오류] OCR 추출 데이터가 누락되었습니다: {ocr_path}. 2단계를 먼저 실행해 주세요.")
        return

    # 데이터 로드
    df_gt = pd.read_csv(gt_path)
    df_ocr = pd.read_csv(ocr_path)

    # 두 데이터 프레임 병합 (record_id 기준)
    df = pd.merge(df_gt, df_ocr, on='record_id', suffixes=('_gt', '_ocr'))
    print(f"-> 총 {len(df)}개 일치 레코드 병합 완료")

    # 2. 개별 항목 평가 루프
    evaluation_records = []

    for idx, row in df.iterrows():
        record_id = row['record_id']
        doc_type = row['document_type_gt']
        has_noise = row['has_noise']
        is_low_res = row['is_low_resolution']
        is_bad_image = has_noise or is_low_res
        prep_used = row['preprocessing_used']

        # 날짜 비교 (NaN 처리 포함)
        gt_date = str(row['doc_date']).strip() if pd.notna(row['doc_date']) else ""
        ocr_date = str(row['extracted_date']).strip() if pd.notna(row['extracted_date']) else ""
        date_match = int(gt_date == ocr_date)

        # 상호명 / 부서명 비교
        gt_store_or_dept = ""
        if doc_type == 'receipt':
            gt_store_or_dept = str(row['organization_or_store']).strip() if pd.notna(row['organization_or_store']) else ""
        else:
            gt_store_or_dept = str(row['respondent_dept']).strip() if pd.notna(row['respondent_dept']) else ""
        
        ocr_store_or_dept = str(row['extracted_store_or_dept']).strip() if pd.notna(row['extracted_store_or_dept']) else ""
        store_dept_match = int(gt_store_or_dept == ocr_store_or_dept)

        # 금액 비교 (영수증 한정)
        amount_match = np.nan
        gt_amount = np.nan
        ocr_amount_cleaned = np.nan
        if doc_type == 'receipt':
            gt_amount = float(row['total_amount']) if pd.notna(row['total_amount']) else np.nan
            ocr_amount_cleaned = clean_amount(row['extracted_amount'])
            if pd.isna(gt_amount) and pd.isna(ocr_amount_cleaned):
                amount_match = 1
            elif pd.isna(gt_amount) or pd.isna(ocr_amount_cleaned):
                amount_match = 0
            else:
                amount_match = int(gt_amount == ocr_amount_cleaned)

        # 설문 점수 비교 (설문 한정)
        sat_match = np.nan
        usa_match = np.nan
        spd_match = np.nan
        composite_score_match = np.nan

        if doc_type == 'survey':
            gt_sat = float(row['satisfaction_score']) if pd.notna(row['satisfaction_score']) else np.nan
            gt_usa = float(row['usability_score']) if pd.notna(row['usability_score']) else np.nan
            gt_spd = float(row['speed_score']) if pd.notna(row['speed_score']) else np.nan

            ocr_scores = parse_extracted_scores(row['extracted_scores'])
            ocr_sat = ocr_scores['satisfaction']
            ocr_usa = ocr_scores['usability']
            ocr_spd = ocr_scores['speed']

            sat_match = int(gt_sat == ocr_sat) if pd.notna(gt_sat) and pd.notna(ocr_sat) else (1 if pd.isna(gt_sat) and pd.isna(ocr_sat) else 0)
            usa_match = int(gt_usa == ocr_usa) if pd.notna(gt_usa) and pd.notna(ocr_usa) else (1 if pd.isna(gt_usa) and pd.isna(ocr_usa) else 0)
            spd_match = int(gt_spd == ocr_spd) if pd.notna(gt_spd) and pd.notna(ocr_spd) else (1 if pd.isna(gt_spd) and pd.isna(ocr_spd) else 0)
            
            composite_score_match = int(sat_match == 1 and usa_match == 1 and spd_match == 1)

        # 수기 메모 비교
        gt_note = str(row['handwritten_note']).strip() if pd.notna(row['handwritten_note']) else ""
        ocr_note = str(row['extracted_note']).strip() if pd.notna(row['extracted_note']) else ""
        # 전처리 완료 텍스트 흔적 등 처리 위해 완전히 같거나 gt가 비어있고 ocr도 비어있으면 매치로 판정
        if gt_note == "" and (ocr_note == "" or pd.isna(row['extracted_note'])):
            note_match = 1
        elif gt_note != "" and ocr_note != "":
            # 완전히 일치하는지 또는 포함 관계인지
            note_match = int(gt_note in ocr_note or ocr_note in gt_note)
        else:
            note_match = 0

        evaluation_records.append({
            'record_id': record_id,
            'document_type': doc_type,
            'has_noise': has_noise,
            'is_low_resolution': is_low_res,
            'is_bad_image': is_bad_image,
            'preprocessing_used': prep_used,
            'gt_date': gt_date,
            'ocr_date': ocr_date,
            'date_match': date_match,
            'gt_store_or_dept': gt_store_or_dept,
            'ocr_store_or_dept': ocr_store_or_dept,
            'store_dept_match': store_dept_match,
            'gt_amount': gt_amount,
            'ocr_amount': ocr_amount_cleaned,
            'amount_match': amount_match,
            'sat_match': sat_match,
            'usa_match': usa_match,
            'spd_match': spd_match,
            'composite_score_match': composite_score_match,
            'gt_note': gt_note,
            'ocr_note': ocr_note,
            'note_match': note_match,
            'confidence': row['confidence']
        })

    df_eval = pd.DataFrame(evaluation_records)

    # 3. 그룹별 품질 메트릭 계산
    # 전체 메트릭 계산 함수
    def get_metrics_for_df(sub_df):
        if len(sub_df) == 0:
            return {
                'count': 0, 'date_accuracy': 0, 'store_dept_accuracy': 0,
                'amount_accuracy': 0, 'score_accuracy': 0, 'note_accuracy': 0,
                'overall_accuracy': 0, 'mean_confidence': 0
            }
        
        d_acc = sub_df['date_match'].mean()
        sd_acc = sub_df['store_dept_match'].mean()
        
        # 영수증 전용 금액 정확도
        receipt_df = sub_df[sub_df['document_type'] == 'receipt']
        a_acc = receipt_df['amount_match'].mean() if len(receipt_df) > 0 else np.nan
        
        # 설문지 전용 점수 정확도
        survey_df = sub_df[sub_df['document_type'] == 'survey']
        s_acc = survey_df['composite_score_match'].mean() if len(survey_df) > 0 else np.nan
        
        n_acc = sub_df['note_match'].mean()
        m_conf = sub_df['confidence'].mean()

        # 종합 정확도 계산 (각 문서 종류별 활성화된 주요 필드의 가중평균)
        accuracies = [d_acc, sd_acc, n_acc]
        if pd.notna(a_acc): accuracies.append(a_acc)
        if pd.notna(s_acc): accuracies.append(s_acc)
        overall = np.mean(accuracies)

        return {
            'count': len(sub_df),
            'date_accuracy': d_acc,
            'store_dept_accuracy': sd_acc,
            'amount_accuracy': a_acc,
            'score_accuracy': s_acc,
            'note_accuracy': n_acc,
            'overall_accuracy': overall,
            'mean_confidence': m_conf
        }

    # 전체 요약
    summary_data = []

    # 전체
    m = get_metrics_for_df(df_eval)
    summary_data.append({'구분': '전체 문서', **m})

    # 문서 유형별
    for dt in ['receipt', 'survey']:
        m = get_metrics_for_df(df_eval[df_eval['document_type'] == dt])
        summary_data.append({'구분': f'문서유형: {dt}', **m})

    # 이미지 상태별 (일반 vs 오염)
    m = get_metrics_for_df(df_eval[df_eval['is_bad_image'] == False])
    summary_data.append({'구분': '이미지상태: 일반 이미지', **m})
    m = get_metrics_for_df(df_eval[df_eval['is_bad_image'] == True])
    summary_data.append({'구분': '이미지상태: 저해상도/노이즈 이미지', **m})

    # 오염 이미지 중 전처리 유무 비교
    bad_df = df_eval[df_eval['is_bad_image'] == True]
    m = get_metrics_for_df(bad_df[bad_df['preprocessing_used'] == True])
    summary_data.append({'구분': '오염이미지 - 전처리 적용', **m})
    m = get_metrics_for_df(bad_df[bad_df['preprocessing_used'] == False])
    summary_data.append({'구분': '오염이미지 - 전처리 미적용', **m})

    df_summary = pd.DataFrame(summary_data)

    # 4. 저장 처리
    # 4-1. Excel 파일로 저장 (상세 + 요약)
    with pd.ExcelWriter(report_xlsx, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='Summary_Metrics', index=False)
        df_eval.to_excel(writer, sheet_name='Detailed_Evaluation', index=False)
    
    # 4-2. 텍스트 보고서 생성
    overall_all = df_summary.iloc[0]['overall_accuracy']
    overall_receipt = df_summary.iloc[1]['overall_accuracy']
    overall_survey = df_summary.iloc[2]['overall_accuracy']
    
    normal_img_acc = df_summary.iloc[3]['overall_accuracy']
    bad_img_acc = df_summary.iloc[4]['overall_accuracy']
    
    bad_prep_acc = df_summary.iloc[5]['overall_accuracy']
    bad_noprep_acc = df_summary.iloc[6]['overall_accuracy']

    with open(report_summary_txt, 'w', encoding='utf-8') as f:
        f.write("============================================================\n")
        f.write("             Project 2 OCR 품질 평가 보고서 요약본\n")
        f.write("============================================================\n\n")
        f.write(f"- 분석 시점: 2026-07-16 09:59:00\n")
        f.write(f"- 전체 검증 레코드 수: {len(df_eval)}건\n")
        f.write(f"- 이미지 전처리 가동 상태: {'[가동]' if df_eval['preprocessing_used'].any() else '[비가동]'}\n\n")
        
        f.write("1. 주요 성능 지표 (KPI Summary)\n")
        f.write("------------------------------------------------------------\n")
        f.write(f"- 종합 평균 인식 정확도: {overall_all * 100:.2f}%\n")
        f.write(f"  * 영수증 종합 정확도: {overall_receipt * 100:.2f}%\n")
        f.write(f"  * 설문지 종합 정확도: {overall_survey * 100:.2f}%\n")
        f.write(f"- 평균 OCR 신뢰도 (Confidence): {df_eval['confidence'].mean() * 100:.2f}%\n\n")

        f.write("2. 이미지 가독성 상태별 분석 결과\n")
        f.write("------------------------------------------------------------\n")
        f.write(f"- 일반 고해상도 이미지 (120장): 종합 정확도 {normal_img_acc * 100:.2f}%\n")
        f.write(f"- 저해상도 / 노이즈 이미지 (120장): 종합 정확도 {bad_img_acc * 100:.2f}%\n\n")

        f.write("3. 이미지 전처리(OpenCV) 도입 효과 검증 (★ 핵심 학습 포인트)\n")
        f.write("------------------------------------------------------------\n")
        f.write("저해상도 및 노이즈가 포함된 '유해 이미지 120장'에 대한 효과 분석:\n")
        f.write(f"- OpenCV 전처리 미적용 시 종합 정확도 : {bad_noprep_acc * 100:.2f}%\n")
        f.write(f"- OpenCV 전처리 적용 시 종합 정확도    : {bad_prep_acc * 100:.2f}%\n")
        gain = (bad_prep_acc - bad_noprep_acc) * 100
        f.write(f"--> 전처리 파이프라인 적용에 따른 정확도 향상분: +{gain:.2f}%p\n\n")
        
        f.write("4. 상세 요약 표 (Summary Table)\n")
        f.write("------------------------------------------------------------\n")
        # 간단한 마크다운 형태의 표 작성
        f.write(f"{'구분':<25} | {'샘플수':<6} | {'날짜정밀도':<8} | {'상호/부서':<8} | {'금액정밀도':<8} | {'점수정밀도':<8} | {'종합정확도':<8}\n")
        f.write("-" * 85 + "\n")
        for idx, row in df_summary.iterrows():
            f.write(f"{row['구분']:<25} | {int(row['count']):<6} | {row['date_accuracy'] * 100:8.1f}% | {row['store_dept_accuracy'] * 100:8.1f}% | "
                    f"{'' if pd.isna(row['amount_accuracy']) else f'{row['amount_accuracy'] * 100:.1f}%':<10} | "
                    f"{'' if pd.isna(row['score_accuracy']) else f'{row['score_accuracy'] * 100:.1f}%':<10} | {row['overall_accuracy'] * 100:8.1f}%\n")

    print(f"\n[평가 분석 완료]")
    print(f"- 종합 정확도: {overall_all * 100:.2f}% (영수증 {overall_receipt * 100:.2f}%, 설문 {overall_survey * 100:.2f}%)")
    print(f"- 이미지 상태별 정확도: 일반 {normal_img_acc * 100:.2f}% vs 오염 {bad_img_acc * 100:.2f}%")
    print(f"- 전처리 효과: 미적용 {bad_noprep_acc * 100:.2f}% -> 적용 {bad_prep_acc * 100:.2f}% (+{gain:.2f}%p 향상!)")
    print(f"- 상세 엑셀 리포트 저장 완료: '{report_xlsx}'")
    print(f"- 분석 요약본 저장 완료: '{report_summary_txt}'")
    print("=" * 60)

if __name__ == "__main__":
    main()
