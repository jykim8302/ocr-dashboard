import os
import pandas as pd

def main():
    print("=" * 60)
    print(" 1단계: 원본 데이터 & 이미지 매칭 검증 시작")
    print("=" * 60)

    # 1. 경로 설정
    csv_path = "data/source_structured/ground_truth_multimodal_240.csv"
    report_dir = "reports"
    report_path = os.path.join(report_dir, "data_image_validation_report.txt")

    # 결과 디렉토리 생성
    os.makedirs(report_dir, exist_ok=True)
    os.makedirs("data/ocr", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)
    os.makedirs("app", exist_ok=True)

    # 2. CSV 로드
    if not os.path.exists(csv_path):
        print(f"[오류] 정답 파일이 누락되었습니다: {csv_path}")
        return

    df = pd.read_csv(csv_path)
    print(f"-> 정답 데이터 로드 완료 ({len(df)}개 레코드)")

    # 3. 데이터 검증 항목 정의
    total_records = len(df)
    duplicates = df[df.duplicated(subset=['record_id'], keep=False)]
    duplicate_count = duplicates['record_id'].nunique()

    # 이미지 파일 존재 여부 검사
    missing_images = []
    invalid_extensions = []
    receipt_count = 0
    survey_count = 0

    valid_extensions = ('.jpg', '.jpeg', '.png')

    for idx, row in df.iterrows():
        record_id = row['record_id']
        doc_type = row['document_type']
        img_path = row['image_filename']

        # 문서 타입 카운트
        if doc_type == 'receipt':
            receipt_count += 1
        elif doc_type == 'survey':
            survey_count += 1

        # 경로 정규화 (역슬래시/슬래시 호환)
        normalized_img_path = img_path.replace('/', os.sep).replace('\\', os.sep)

        # 이미지 확장자 검사
        _, ext = os.path.splitext(normalized_img_path.lower())
        if ext not in valid_extensions:
            invalid_extensions.append({
                'record_id': record_id,
                'document_type': doc_type,
                'image_filename': img_path,
                'issue': '잘못된 확장자'
            })

        # 이미지 실재 여부 검사
        if not os.path.exists(normalized_img_path):
            missing_images.append({
                'record_id': record_id,
                'document_type': doc_type,
                'image_filename': img_path,
                'issue': '이미지 파일 누락'
            })

    # 4. 리포트 생성 및 저장
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("============================================================\n")
        f.write("      Project 2 OCR 데이터 & 이미지 매칭 검증 보고서\n")
        f.write("============================================================\n\n")
        f.write(f"- 분석 일시: 2026-07-16 09:59:00\n")
        f.write(f"- 대상 데이터: {csv_path}\n\n")
        f.write("1. 종합 요약\n")
        f.write("------------------------------------------------------------\n")
        f.write(f"- 전체 정답 레코드 수: {total_records}개\n")
        f.write(f"  * 영수증(receipt) 수: {receipt_count}개\n")
        f.write(f"  * 수기 설문지(survey) 수: {survey_count}개\n")
        f.write(f"- 중복 record_id 그룹 수: {duplicate_count}개\n")
        f.write(f"- 누락 이미지 수: {len(missing_images)}개\n")
        f.write(f"- 잘못된 확장자 수: {len(invalid_extensions)}개\n\n")

        # 중복 record_id 상세 테이블
        f.write("2. 중복 record_id 상세 리스트\n")
        f.write("------------------------------------------------------------\n")
        if len(duplicates) > 0:
            f.write(f"{'record_id':<12} | {'document_type':<15} | {'image_filename'}\n")
            f.write("-" * 75 + "\n")
            for idx, row in duplicates.iterrows():
                f.write(f"{row['record_id']:<12} | {row['document_type']:<15} | {row['image_filename']}\n")
        else:
            f.write("-> 중복된 record_id가 발견되지 않았습니다. (안전)\n")
        f.write("\n")

        # 누락 이미지 상세 테이블
        f.write("3. 누락 이미지 및 파일 오류 상세 리스트\n")
        f.write("------------------------------------------------------------\n")
        issues_combined = missing_images + invalid_extensions
        if len(issues_combined) > 0:
            f.write(f"{'record_id':<12} | {'구분':<12} | {'문제 유형':<18} | {'파일 경로'}\n")
            f.write("-" * 80 + "\n")
            for item in issues_combined:
                f.write(f"{item['record_id']:<12} | {item['document_type']:<12} | {item['issue']:<18} | {item['image_filename']}\n")
        else:
            f.write("-> 모든 이미지 파일이 정해진 경로에 존재하며, 확장자가 올바릅니다. (안전)\n")

    # 5. 콘솔 출력
    print(f"\n[검증 결과]")
    print(f"- 전체 정답 레코드: {total_records}개 (영수증 {receipt_count}장 / 설문지 {survey_count}장)")
    print(f"- 중복 record_id: {duplicate_count}건")
    print(f"- 누락 이미지: {len(missing_images)}건")
    print(f"- 확장자 에러: {len(invalid_extensions)}건")
    print(f"-> 상세 검증 보고서가 '{report_path}'에 저장되었습니다.")
    print("=" * 60)

if __name__ == "__main__":
    main()
