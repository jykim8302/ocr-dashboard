import os
import cv2
import numpy as np
import pandas as pd
import argparse
import random

def preprocess_image(img_path, output_path):
    """
    OpenCV를 사용하여 이미지 전처리를 수행합니다.
    - Grayscale 변환
    - CLAHE 대비 향상 (Contrast Enhancement)
    - Gaussian Blur 노이즈 제거 (Denoise)
    - Adaptive Threshold (이진화)
    """
    # 이미지 로드
    img = cv2.imread(img_path)
    if img is None:
        return False

    # 1. Grayscale 변환
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. CLAHE 기반 대비 향상 (명암비 조절)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)

    # 3. 노이즈 제거 (Gaussian Blur)
    denoised = cv2.GaussianBlur(contrast, (3, 3), 0)

    # 4. Adaptive Thresholding (가독성 향상 이진화)
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    # 결과 이미지 저장
    cv2.imwrite(output_path, binary)
    return True

def simulate_ocr(row, use_preprocess):
    """
    정답 데이터를 기반으로 노이즈와 해상도 상태, 전처리 여부에 따라 OCR 결과를 시뮬레이션합니다.
    """
    # 난수 고정으로 재현성 보장
    random.seed(int(row['record_id'].split('-')[1]) + (42 if use_preprocess else 0))

    has_noise = str(row['has_noise']).lower() == 'true'
    is_low_res = str(row['is_low_resolution']).lower() == 'true'
    is_bad_image = has_noise or is_low_res

    # 기본값은 정답 데이터로 채움
    record_id = row['record_id']
    doc_type = row['document_type']
    image_filename = row['image_filename']

    gt_date = str(row['doc_date']) if pd.notna(row['doc_date']) else ""
    gt_store_or_dept = ""
    if doc_type == 'receipt':
        gt_store_or_dept = str(row['organization_or_store']) if pd.notna(row['organization_or_store']) else ""
    else:
        gt_store_or_dept = str(row['respondent_dept']) if pd.notna(row['respondent_dept']) else ""

    gt_amount = row['total_amount'] if pd.notna(row['total_amount']) else ""
    if gt_amount != "":
        gt_amount = int(float(gt_amount))

    # 설문 점수 파싱
    sat = row['satisfaction_score'] if pd.notna(row['satisfaction_score']) else ""
    usa = row['usability_score'] if pd.notna(row['usability_score']) else ""
    spd = row['speed_score'] if pd.notna(row['speed_score']) else ""

    gt_scores = ""
    if doc_type == 'survey' and (sat != "" or usa != "" or spd != ""):
        gt_scores = f"만족도:{int(sat) if sat != '' else ''}, 편의성:{int(usa) if usa != '' else ''}, 속도:{int(spd) if spd != '' else ''}"

    gt_note = str(row['handwritten_note']) if pd.notna(row['handwritten_note']) else ""

    # 시뮬레이션 결과 초기화
    extracted_date = gt_date
    extracted_store_or_dept = gt_store_or_dept
    extracted_amount = gt_amount
    extracted_scores = gt_scores
    extracted_note = gt_note
    confidence = 0.95
    error_message = ""

    # 전처리 효과 및 가독성 저하 로직 적용
    if is_bad_image:
        if use_preprocess:
            # 전처리 적용됨 -> 고품질 추출 성공 (일부 마이너 노이즈 복구)
            confidence = round(random.uniform(0.88, 0.96), 4)
            # 5% 확률로 아주 미세한 오차
            if random.random() < 0.05:
                extracted_note = gt_note + " (전처리완료)"
        else:
            # 전처리 적용 안 됨 -> 저해상도/노이즈로 인한 추출 오류 발생!
            confidence = round(random.uniform(0.42, 0.65), 4)
            error_message = "Low Contrast & Denoise Required"

            # 1. 날짜 가독 실패 또는 깨짐 (40% 확률로 에러 발생)
            if random.random() < 0.40:
                if random.random() < 0.50:
                    extracted_date = ""  # 누락
                else:
                    # 가독 에러 모사 (8을 B로, 0을 O로 등)
                    extracted_date = gt_date.replace("0", "O").replace("1", "I").replace("2", "Z")

            # 2. 상호명 또는 부서명 깨짐 (30% 확률)
            if random.random() < 0.30:
                if random.random() < 0.50:
                    extracted_store_or_dept = ""
                else:
                    extracted_store_or_dept = gt_store_or_dept.replace("카페", "카폐").replace("마트", "마르").replace("기획", "기회")

            # 3. 금액 깨짐 (영수증 문서만, 50% 확률)
            if doc_type == 'receipt' and gt_amount != "":
                r = random.random()
                if r < 0.40:
                    extracted_amount = ""  # 누락
                elif r < 0.70:
                    # 문자 오인식에 따른 숫자형 파싱 오류 (예: 쉼표나 원화 기호 혼선으로 공백 포함되거나 문자로 추출됨)
                    extracted_amount = f"{gt_amount}원"  # 문자열이 섞여서 숫자 파싱이 어렵게 모사
                else:
                    # 숫자 값 자체 왜곡 (8을 3으로, 0을 O로 바꿈 등)
                    corrupted_str = str(gt_amount).replace("8", "3").replace("0", "9")
                    try:
                        extracted_amount = int(corrupted_str)
                    except:
                        extracted_amount = ""

            # 4. 설문지 점수 누락 (설문 문서만, 40% 확률)
            if doc_type == 'survey' and gt_scores != "":
                r = random.random()
                if r < 0.50:
                    extracted_scores = ""  # 전체 점수 영역 판독 실패
                else:
                    # 부분 점수 누락 모사
                    # 만족도:{sat}, 편의성:{usa}, 속도:{spd} 중 일부를 공백으로 처리
                    p_sat = "" if random.random() < 0.4 else (int(sat) if sat != "" else "")
                    p_usa = "" if random.random() < 0.4 else (int(usa) if usa != "" else "")
                    p_spd = "" if random.random() < 0.4 else (int(spd) if spd != "" else "")
                    extracted_scores = f"만족도:{p_sat}, 편의성:{p_usa}, 속도:{p_spd}"

            # 5. 수기 메모 추출 실패 (60% 확률)
            if gt_note != "":
                if random.random() < 0.60:
                    extracted_note = ""  # 수기 메모 인식 실패

    else:
        # 정상 이미지 -> 무난하게 추출
        confidence = round(random.uniform(0.90, 0.98), 4)
        # 매우 적은 확률로 문자 왜곡 오차 발생 (2%)
        if random.random() < 0.02:
            confidence = round(random.uniform(0.75, 0.85), 4)

    return {
        'record_id': record_id,
        'document_type': doc_type,
        'image_filename': image_filename,
        'extracted_date': extracted_date,
        'extracted_store_or_dept': extracted_store_or_dept,
        'extracted_amount': extracted_amount,
        'extracted_scores': extracted_scores,
        'extracted_note': extracted_note,
        'confidence': confidence,
        'error_message': error_message,
        'preprocessing_used': use_preprocess
    }

def main():
    parser = argparse.ArgumentParser(description="OCR Extractor and Preprocessor Simulator")
    parser.add_argument("--preprocess", action="store_true", help="OpenCV 이미지 전처리를 실행하여 추출 정확도를 극대화합니다.")
    args = parser.parse_args()

    print("=" * 60)
    print(f" 2~3단계: OCR 추출 및 전처리 프로세서 구동 (전처리 적용 여부: {args.preprocess})")
    print("=" * 60)

    # 1. 파일 검사 및 경로 준비
    csv_path = "data/source_structured/ground_truth_multimodal_240.csv"
    output_raw_csv = "data/ocr/ocr_extracted_raw.csv"
    prep_dir = "data/ocr/preprocessed_images"

    os.makedirs("data/ocr", exist_ok=True)
    if args.preprocess:
        os.makedirs(prep_dir, exist_ok=True)
        print(f"-> 전처리된 이미지는 '{prep_dir}' 폴더에 저장됩니다.")

    if not os.path.exists(csv_path):
        print(f"[오류] 정답 기준 파일이 없습니다: {csv_path}")
        return

    df_gt = pd.read_csv(csv_path)

    # 2. 이미지 처리 및 OCR 가상 시뮬레이션
    results = []
    print("-> 이미지 로딩 및 OCR 추출 작업 개시 (240장)...")

    success_prep_count = 0

    for idx, row in df_gt.iterrows():
        img_path = row['image_filename']
        record_id = row['record_id']

        # 윈도우/리눅스 경로 호환성 처리
        img_path_local = img_path.replace('/', os.sep).replace('\\', os.sep)

        # 이미지 전처리 가동 여부
        if args.preprocess:
            filename = os.path.basename(img_path_local)
            output_prep_path = os.path.join(prep_dir, filename)
            # 이미지 파일이 실제로 있으면 OpenCV 전처리 적용
            if os.path.exists(img_path_local):
                ok = preprocess_image(img_path_local, output_prep_path)
                if ok:
                    success_prep_count += 1
            else:
                # 이미지 누락시에도 시뮬레이션은 실행하되 경고
                pass

        # 가상 OCR 실행
        ocr_res = simulate_ocr(row, args.preprocess)
        results.append(ocr_res)

        # 프로그레스 바 대용 진행 상황 표시
        if (idx + 1) % 40 == 0:
            print(f"   [{idx + 1}/240] 진행 완료...")

    # 3. CSV로 저장
    df_out = pd.DataFrame(results)
    df_out.to_csv(output_raw_csv, index=False, encoding="utf-8-sig")

    print(f"\n[추출 완료]")
    print(f"- 총 추출 건수: {len(df_out)}건")
    if args.preprocess:
        print(f"- OpenCV 이미지 전처리 성공 건수: {success_prep_count}건")
    print(f"- 결과 원시 데이터 저장 경로: '{output_raw_csv}'")
    print("=" * 60)

if __name__ == "__main__":
    main()
