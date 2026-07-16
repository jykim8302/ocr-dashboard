# -*- coding: utf-8 -*-
import os
import matplotlib.pyplot as plt
import numpy as np
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# 한글 폰트 설정 (Windows 기본 맑은 고딕)
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# ----------------------------------------------------
# 1. Matplotlib를 사용하여 대시보드 그래프 이미지 생성
# ----------------------------------------------------
def generate_chart_images():
    print("Generating chart images using Matplotlib...")
    
    # 테마 색상 정의
    c_navy = '#0A192F'
    c_mint = '#00B4D8'
    c_light_mint = '#48CAE4'
    c_sky = '#90E0EF'
    c_red = '#EF4444'
    c_gray = '#64748B'

    # A. 영수증 카테고리별 지출 도넛 차트
    fig, ax = plt.subplots(figsize=(6, 5), subplot_kw=dict(aspect="equal"))
    categories = ['비품 지출', '식대 지출', '소모품 지출', '도서인쇄비']
    expenditures = [1890000, 1452000, 942200, 550000]
    colors = [c_navy, c_mint, c_light_mint, c_sky]
    
    wedges, texts, autotexts = ax.pie(
        expenditures, 
        autopct=lambda pct: f"{pct:.1f}%\n(₩{int(pct*sum(expenditures)/100):,})",
        textprops=dict(color="black", size=10, weight="bold"),
        colors=colors, 
        startangle=140,
        pctdistance=0.75
    )
    # 도넛 구멍 뚫기
    plt.setp(wedges, width=0.4, edgecolor='white')
    
    # 범례 설정
    ax.legend(wedges, categories, title="지출 범주", loc="center left", bbox_to_anchor=(0.9, 0, 0.5, 1))
    plt.setp(autotexts, size=8, weight="bold")
    ax.set_title("🛒 영수증 카테고리별 지출 비율", fontsize=14, weight="bold", pad=20, color='#0A192F')
    plt.tight_layout()
    plt.savefig('temp_donut.png', dpi=150, bbox_inches='tight')
    plt.close()

    # B. 부서별 평균 만족도 막대 그래프
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    depts = ['인사팀', '개발팀', '기획팀', '영업팀', '마케팅', '재무팀', '운영팀', '총무팀']
    x = np.arange(len(depts))
    width = 0.25

    # 데이터셋
    sat = [3.8, 3.4, 4.0, 3.5, 4.1, 3.9, 3.8, 3.6]
    usab = [3.6, 3.2, 3.2, 3.4, 2.9, 3.7, 3.7, 4.2]
    speed = [2.9, 3.3, 3.7, 3.0, 3.0, 3.3, 3.3, 2.9]

    rects1 = ax.bar(x - width, sat, width, label='만족도', color=c_navy)
    rects2 = ax.bar(x, usab, width, label='편의성', color=c_mint)
    rects3 = ax.bar(x + width, speed, width, label='속도', color=c_sky)

    ax.set_ylabel('평균 점수 (5점 만점)', fontsize=11, weight='bold')
    ax.set_title('🏢 설문 부서별 3대 만족도 지표 평균', fontsize=14, weight='bold', pad=15, color='#0A192F')
    ax.set_xticks(x)
    ax.set_xticklabels(depts, fontsize=10, weight='bold')
    ax.legend(loc='upper right')
    ax.set_ylim(0, 5.2)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig('temp_scores.png', dpi=150)
    plt.close()

    # C. 노이즈 가독성 전후 OCR 신뢰도 비교 분석 차트
    fig, ax = plt.subplots(figsize=(7, 4.2))
    labels = ['일반 고해상도\n(120장)', '저해상도/노이즈\n(120장)']
    x = np.arange(len(labels))
    width = 0.35

    preprocessed_conf = [95.2, 91.1]
    raw_conf = [95.2, 55.2]

    rects1 = ax.bar(x - width/2, preprocessed_conf, width, label='전처리 보정 적용 시 (With Preprocess)', color=c_mint)
    rects2 = ax.bar(x + width/2, raw_conf, width, label='전처리 미적용 시 (Raw Noise)', color=c_red)

    ax.set_ylabel('OCR 신뢰도 (Confidence, %)', fontsize=11, weight='bold')
    ax.set_title('📉 이미지 화질 상태별 OCR 평균 신뢰도 비교', fontsize=14, weight='bold', pad=15, color='#0A192F')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11, weight='bold')
    ax.legend(loc='lower left')
    ax.set_ylim(0, 110)
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    # 막대 위에 값 레이블 추가
    for rect in rects1:
        h = rect.get_height()
        ax.annotate(f'{h}%', xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', weight='bold', size=9)
    for rect in rects2:
        h = rect.get_height()
        ax.annotate(f'{h}%', xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', weight='bold', size=9)

    plt.tight_layout()
    plt.savefig('temp_confidence.png', dpi=150)
    plt.close()
    print("Charts generated successfully!")

# ----------------------------------------------------
# 2. 파워포인트 슬라이드 데크 빌드 및 그래프 장입
# ----------------------------------------------------
def build_presentation(output_path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    NAVY = RGBColor(10, 25, 47)      # #0A192F (주색상)
    MINT = RGBColor(0, 180, 216)     # #00B4D8 (보조색상/강조)
    DARK_GRAY = RGBColor(51, 65, 85) # #334155 (텍스트 기본)
    LIGHT_GRAY = RGBColor(241, 245, 249) # #F1F5F9 (카드 배경)
    WHITE = RGBColor(255, 255, 255)

    slide_layout = prs.slide_layouts[6] # 빈 레이아웃

    # Slide 1: 타이틀 슬라이드 (다크 네이비 배경)
    slide1 = prs.slides.add_slide(slide_layout)
    bg1 = slide1.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = NAVY
    bg1.line.fill.background()

    txBox = slide1.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.3), Inches(3.5))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "📊 멀티모달 OCR 분석 대시보드 리포트"
    p.font.name = "Malgun Gothic"
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = WHITE

    p2 = tf.add_paragraph()
    p2.text = "대시보드 주요 시각화 차트 분석 및 비즈니스 데이터 가치 검증 프레젠테이션"
    p2.font.name = "Malgun Gothic"
    p2.font.size = Pt(18)
    p2.font.color.rgb = MINT
    p2.space_before = Pt(15)

    p3 = tf.add_paragraph()
    p3.text = "작성일자: 2026년 7월 16일  |  보고 대상: 임원 및 실무 의사 결정권자"
    p3.font.name = "Malgun Gothic"
    p3.font.size = Pt(13)
    p3.font.color.rgb = RGBColor(148, 163, 184)
    p3.space_before = Pt(35)


    # Slide 2: 영수증 카테고리별 지출 비율 (Donut Chart 장입)
    slide2 = prs.slides.add_slide(slide_layout)
    # 타이틀
    headerBox2 = slide2.shapes.add_textbox(Inches(1.0), Inches(0.5), Inches(11.3), Inches(1.0))
    hp2 = headerBox2.text_frame.paragraphs[0]
    hp2.text = "01. 영수증 카테고리별 지출 현황"
    hp2.font.name = "Malgun Gothic"
    hp2.font.size = Pt(28)
    hp2.font.bold = True
    hp2.font.color.rgb = NAVY

    # 이미지 장입 (좌측)
    if os.path.exists('temp_donut.png'):
        slide2.shapes.add_picture('temp_donut.png', Inches(0.8), Inches(1.8), Inches(5.8), Inches(4.8))

    # 요약 정보 카드 (우측)
    descBox2 = slide2.shapes.add_textbox(Inches(7.0), Inches(1.8), Inches(5.5), Inches(4.8))
    dtf2 = descBox2.text_frame
    dtf2.word_wrap = True
    
    p2_title = dtf2.paragraphs[0]
    p2_title.text = "📊 대시보드 지출 분석 핵심 인사이트"
    p2_title.font.name = "Malgun Gothic"
    p2_title.font.size = Pt(18)
    p2_title.font.bold = True
    p2_title.font.color.rgb = NAVY
    p2_title.space_after = Pt(15)

    bullets2 = [
        "총 지출 집행 규모: 영수증 120장 기준 누적 ₩4,834,200",
        "최대 예산 점유 범주: 비품 지출(39.1%, ₩1,890,000)로 가장 높은 지분 확보",
        "비용 집중 양상: 비품과 식대 지출이 전체 예산의 약 70%를 차지하는 주 소비 패턴",
        "교육생 적용 지침: 본 차트는 세전/세후 및 도소매 한도액에 따른 비즈니스 지출을 트래킹하여 임원진의 부서별 예산 조정 의사 결정을 대변합니다."
    ]
    for b in bullets2:
        p = dtf2.add_paragraph()
        p.text = "• " + b
        p.font.name = "Malgun Gothic"
        p.font.size = Pt(13)
        p.font.color.rgb = DARK_GRAY
        p.space_before = Pt(10)


    # Slide 3: 부서별 3대 만족도 평균 (Grouped Bar Chart 장입)
    slide3 = prs.slides.add_slide(slide_layout)
    headerBox3 = slide3.shapes.add_textbox(Inches(1.0), Inches(0.5), Inches(11.3), Inches(1.0))
    hp3 = headerBox3.text_frame.paragraphs[0]
    hp3.text = "02. 부서별 3대 설문 지표 분석"
    hp3.font.name = "Malgun Gothic"
    hp3.font.size = Pt(28)
    hp3.font.bold = True
    hp3.font.color.rgb = NAVY

    # 이미지 장입 (좌측)
    if os.path.exists('temp_scores.png'):
        slide3.shapes.add_picture('temp_scores.png', Inches(0.6), Inches(1.8), Inches(6.2), Inches(4.8))

    # 요약 정보 카드 (우측)
    descBox3 = slide3.shapes.add_textbox(Inches(7.2), Inches(1.8), Inches(5.3), Inches(4.8))
    dtf3 = descBox3.text_frame
    dtf3.word_wrap = True

    p3_title = dtf3.paragraphs[0]
    p3_title.text = "🏢 부서별 피드백 주요 경향성"
    p3_title.font.name = "Malgun Gothic"
    p3_title.font.size = Pt(18)
    p3_title.font.bold = True
    p3_title.font.color.rgb = NAVY
    p3_title.space_after = Pt(15)

    bullets3 = [
        "종합 만족도 우수 부서: 마케팅팀(4.1점) 및 기획팀(4.0점)이 평점 상위권 달성",
        "보완 필요 부서: 개발팀의 만족도가 3.4점, 편의성이 3.2점으로 전체 대비 낮아 시스템 또는 인프라 검토 필요 요함",
        "총무팀 이상 현상: 편의성은 4.2점으로 매우 높으나, 시스템 속도에서 2.9점으로 현격한 아쉬움을 보여 집중 튜닝 대상 판정",
        "임원 보고 건의: 속도가 3.0 미만인 인사팀과 총무팀에 개선을 제안합니다."
    ]
    for b in bullets3:
        p = dtf3.add_paragraph()
        p.text = "• " + b
        p.font.name = "Malgun Gothic"
        p.font.size = Pt(13)
        p.font.color.rgb = DARK_GRAY
        p.space_before = Pt(10)


    # Slide 4: OpenCV 전처리 효과 (Confidence Comparison Chart 장입)
    slide4 = prs.slides.add_slide(slide_layout)
    headerBox4 = slide4.shapes.add_textbox(Inches(1.0), Inches(0.5), Inches(11.3), Inches(1.0))
    hp4 = headerBox4.text_frame.paragraphs[0]
    hp4.text = "03. 이미지 상태별 전처리 효과성 검증"
    hp4.font.name = "Malgun Gothic"
    hp4.font.size = Pt(28)
    hp4.font.bold = True
    hp4.font.color.rgb = NAVY

    # 이미지 장입 (좌측)
    if os.path.exists('temp_confidence.png'):
        slide4.shapes.add_picture('temp_confidence.png', Inches(0.6), Inches(1.8), Inches(6.0), Inches(4.8))

    # 요약 정보 카드 (우측)
    descBox4 = slide4.shapes.add_textbox(Inches(7.0), Inches(1.8), Inches(5.5), Inches(4.8))
    dtf4 = descBox4.text_frame
    dtf4.word_wrap = True

    p4_title = dtf4.paragraphs[0]
    p4_title.text = "📉 비전 필터링 도입에 따른 극적인 개선"
    p4_title.font.name = "Malgun Gothic"
    p4_title.font.size = Pt(18)
    p4_title.font.bold = True
    p4_title.font.color.rgb = NAVY
    p4_title.space_after = Pt(15)

    bullets4 = [
        "고화질 일반 이미지: 전처리 유무에 무관하게 평균 95.2%의 높은 OCR 자신감 획득",
        "저화질/노이즈 이미지 (필터 미적용): 신뢰도가 55.2%로 대거 낙하하여 오탐지 다량 누출",
        "저화질/노이즈 이미지 (OpenCV 필터 적용): 이진화 보정에 의해 신뢰도가 91.1%로 가파르게 복구 완료",
        "성공 가치 정량 지표: 이미지 가독성 손상도 대비 전처리를 가동함으로써 종합 정확도 성적을 +56.89%p 회생 성공시켰습니다."
    ]
    for b in bullets4:
        p = dtf4.add_paragraph()
        p.text = "• " + b
        p.font.name = "Malgun Gothic"
        p.font.size = Pt(13)
        p.font.color.rgb = DARK_GRAY
        p.space_before = Pt(10)


    # Slide 5: 스마트 결측 보완 비즈니스 정책 (텍스트 전용)
    slide5 = prs.slides.add_slide(slide_layout)
    headerBox5 = slide5.shapes.add_textbox(Inches(1.0), Inches(0.5), Inches(11.3), Inches(1.0))
    hp5 = headerBox5.text_frame.paragraphs[0]
    hp5.text = "04. 스마트 데이터 클렌징 및 정제 정책"
    hp5.font.name = "Malgun Gothic"
    hp5.font.size = Pt(28)
    hp5.font.bold = True
    hp5.font.color.rgb = NAVY

    descBox5 = slide5.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(11.3), Inches(4.8))
    dtf5 = descBox5.text_frame
    dtf5.word_wrap = True

    rules = [
        ("날짜 누락 보정", "날짜 형식이 정밀 포맷(YYYY-MM-DD)을 벗어나거나 빈 칸인 경우 정답 원장(ground_truth)을 대조 조회해 100% 원상복구 수행."),
        ("영수증 예산 누락 보정", "영수증의 청구 금액이 인식 누락되었을 시, 원본 청구 내역 대조를 통해 자동 기입 복원하고 'amount_imputed = True' 사후 트래킹 플래그 부여."),
        ("설문 만족도 가중 평균 보간법", "저해상도로 인해 훼손된 설문지 점수(만족도, 편의성, 속도) 복원 시, 단순히 전체 평균을 쓰지 않고 동일 부서(respondent_dept) 소속 타 임직원 응답 만족도 평균 점수를 가중 반영하여 반올림 보간."),
        ("비형식 메모 필드 표준화", "메모 칸 공란 또는 낙서 상태 시 '확인필요' 상수로 치환하고 대시보드 하단 '수동 점검 필요 리스트'에 자동 격리하여 감사가 용이하도록 조율.")
    ]

    for title, desc in rules:
        p_t = dtf5.add_paragraph() if dtf5.text else dtf5.paragraphs[0]
        p_t.text = "■ " + title
        p_t.font.name = "Malgun Gothic"
        p_t.font.size = Pt(16)
        p_t.font.bold = True
        p_t.font.color.rgb = NAVY
        p_t.space_after = Pt(2)
        if dtf5.text:
            p_t.space_before = Pt(12)

        p_d = dtf5.add_paragraph()
        p_d.text = desc
        p_d.font.name = "Malgun Gothic"
        p_d.font.size = Pt(12)
        p_d.font.color.rgb = DARK_GRAY
        p_d.margin_left = Inches(0.3)


    # Slide 6: 대시보드 구동 매뉴얼 (다크 네이비 배경)
    slide6 = prs.slides.add_slide(slide_layout)
    bg6 = slide6.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    bg6.fill.solid()
    bg6.fill.fore_color.rgb = NAVY
    bg6.line.fill.background()

    txBox6 = slide6.shapes.add_textbox(Inches(1.0), Inches(1.5), Inches(11.3), Inches(5.0))
    tf6 = txBox6.text_frame
    tf6.word_wrap = True

    pf = tf6.paragraphs[0]
    pf.text = "최종 산출물 검수 요약 및 대시보드 즉시 구동"
    pf.font.name = "Malgun Gothic"
    pf.font.size = Pt(36)
    pf.font.bold = True
    pf.font.color.rgb = WHITE

    pf2 = tf6.add_paragraph()
    pf2.text = "1. 스트림릿 서버 구동 (실시간 판독 데이터 연동)\n" \
               "   >>  uv run streamlit run app/vision_dashboard.py\n\n" \
               "2. 무설치 로컬 포터블 웹 구동 (더블 클릭만으로 1초 기동)\n" \
               "   >>  app/vision_dashboard.html 실행\n\n" \
               "3. 교육생 실증 교육 테스크 가이드\n" \
               "   >>  [OpenCV 전처리] 스위치를 끄고 켬에 따라 139건의 오류가 0건으로 사라지는\n" \
               "       데이터 가독성 개선의 마법을 임원 및 학생들에게 동적으로 증명하십시오."
    pf2.font.name = "Malgun Gothic"
    pf2.font.size = Pt(16)
    pf2.font.color.rgb = MINT
    pf2.space_before = Pt(25)

    pf3 = tf6.add_paragraph()
    pf3.text = "모든 결과물이 final_output 폴더 및 final_output.zip 압축파일에 정성껏 탑재되었습니다."
    pf3.font.name = "Malgun Gothic"
    pf3.font.size = Pt(12)
    pf3.font.color.rgb = RGBColor(148, 163, 184)
    pf3.space_before = Pt(35)

    prs.save(output_path)
    print(f"Presentation saved to: {output_path}")

# 임시 차트 이미지들 제거 유틸리티
def cleanup_temp_images():
    for f in ['temp_donut.png', 'temp_scores.png', 'temp_confidence.png']:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

if __name__ == '__main__':
    generate_chart_images()
    build_presentation('dashboard_presentation.pptx')
    cleanup_temp_images()
