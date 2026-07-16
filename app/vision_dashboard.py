import os
import streamlit as pd_st
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ----------------------------------------------------
# 1. 페이지 초기 설정 및 임원 보고용 테마 (CSS) 적용
# ----------------------------------------------------
st.set_page_config(
    page_title="멀티모달 OCR 분석 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 임원 보고용 Navy & Mint 프리미엄 스타일 CSS
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* 메인 타이틀 */
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #0A192F;
        margin-bottom: 0.2rem;
        border-bottom: 3px solid #172A45;
        padding-bottom: 0.5rem;
    }
    
    .sub-title {
        font-size: 1.0rem;
        color: #606F7B;
        margin-bottom: 1.5rem;
    }
    
    /* 프리미엄 카드 디자인 */
    .kpi-card {
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 1.25rem;
        box-shadow: 0 4px 15px rgba(10, 25, 47, 0.05);
        border: 1px solid #E2E8F0;
        border-top: 4px solid #00B4D8;
        transition: transform 0.2s ease-in-out;
    }
    
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 20px rgba(10, 25, 47, 0.08);
    }
    
    .kpi-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0F172A;
        margin-top: 0.3rem;
        margin-bottom: 0.2rem;
    }
    
    .kpi-delta {
        font-size: 0.8rem;
        font-weight: 500;
        color: #10B981; /* 민트/그린 계열 */
    }
    
    .kpi-delta-red {
        font-size: 0.8rem;
        font-weight: 500;
        color: #EF4444;
    }
    
    /* 사이드바 스타일링 */
    .css-163o978 {
        background-color: #0A192F;
    }
    
    </style>
    """, unsafe_allow_html=True)

# ----------------------------------------------------
# 2. 데이터 로드 및 오류 처리
# ----------------------------------------------------
data_path = "data/processed/ocr_cleaned_dataset.xlsx"

@st.cache_data
def load_data(path):
    if os.path.exists(path):
        return pd.read_excel(path, sheet_name='Cleaned_Data')
    return None

df = load_data(data_path)

if df is None:
    st.title("📊 멀티모달 OCR 분석 대시보드")
    st.error("⚠️ 정제 데이터셋 파일을 찾을 수 없습니다!")
    st.info(f"경로: `{data_path}`")
    st.markdown("""
    대시보드를 구동하기 전에 아래 **데이터 파이프라인 스크립트**들을 순서대로 실행하여 실습 데이터를 완성해 주세요.
    
    ### 💻 실습 스크립트 실행 순서 (터미널에서 실행)
    
    1. **데이터 매칭 검증**:
       ```bash
       python src/validate_data.py
       ```
    2. **OpenCV 전처리 및 OCR 추출 (전처리 모드 추천)**:
       ```bash
       python src/ocr_extractor.py --preprocess
       ```
       *(만약 전처리 효과를 비교하고 싶다면 `--preprocess` 없이 한 번 더 실행해 본 뒤 평가를 진행하세요.)*
    
    3. **OCR 품질 비교 평가**:
       ```bash
       python src/evaluate_ocr.py
       ```
    4. **결측치 정제 및 보간**:
       ```bash
       python src/clean_data.py
       ```
       
    정제 작업이 완료되면 이 페이지를 새로고침(F5) 하세요!
    """)
    st.stop()

# ----------------------------------------------------
# 3. 사이드바 필터 설계
# ----------------------------------------------------
st.sidebar.image("data/source_structured/image_contact_sheet_preview.jpg", use_container_width=True, caption="OCR 실습 대상 이미지 개요")
st.sidebar.markdown("<h2 style='color: #0A192F;'>⚙️ 대시보드 필터 컨트롤</h2>", unsafe_allow_html=True)

# 3-1. 문서 유형 필터 (영수증 / 설문지)
doc_types_options = ["전체보기", "Receipt (영수증)", "Survey (설문지)"]
selected_doc_type = st.sidebar.selectbox("📂 문서 유형 선택", doc_types_options)

# 3-2. 부서 필터 (설문지 응답 부서용)
# 부서 목록 추출 (빈 값 제외 및 고유값)
all_depts = df['respondent_dept'].dropna().unique().tolist()
all_depts = [d for d in all_depts if str(d).strip() != "" and str(d) != "nan"]
all_depts.sort()

selected_depts = st.sidebar.multiselect(
    "🏢 설문 부서 필터 (Survey 한정)",
    options=all_depts,
    default=all_depts
)

# 데이터 필터링 적용
filtered_df = df.copy()

# 문서 유형 필터 적용
if selected_doc_type == "Receipt (영수증)":
    filtered_df = filtered_df[filtered_df['document_type'] == 'receipt']
elif selected_doc_type == "Survey (설문지)":
    filtered_df = filtered_df[filtered_df['document_type'] == 'survey']

# 부서 필터 적용 (설문 데이터에 한해서만 필터링하고 영수증 데이터는 부서 필터에 영향받지 않게 하거나, 설문일때만 부서매칭 적용)
if selected_doc_type == "Survey (설문지)" and len(selected_depts) > 0:
    filtered_df = filtered_df[filtered_df['respondent_dept'].isin(selected_depts)]
elif selected_doc_type == "전체보기" and len(selected_depts) > 0:
    # 설문지는 선택부서만, 영수증은 전부 보여줌
    filtered_df = filtered_df[
        (filtered_df['document_type'] == 'receipt') |
        ((filtered_df['document_type'] == 'survey') & (filtered_df['respondent_dept'].isin(selected_depts)))
    ]

# ----------------------------------------------------
# 4. 헤더 영역
# ----------------------------------------------------
st.markdown("<h1 class='main-title'>📊 멀티모달 OCR 분석 대시보드</h1>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>본 대시보드는 영수증 120장 및 수기 설문지 120장에 대한 OCR 추출 결과의 전처리 효과와 보간 가독성 데이터를 분석합니다. (임원 보고용 프리미엄 뷰)</div>", unsafe_allow_html=True)

# ----------------------------------------------------
# 5. 상단 KPI 카드 영역 (4개 가로 배치)
# ----------------------------------------------------
kpi_col1, kpi_card2, kpi_col3, kpi_col4 = st.columns(4)

# KPI 1: 전체 분석 문서 수
total_docs = len(filtered_df)
with kpi_col1:
    st.markdown(f"""
        <div class='kpi-card' style='border-top-color: #0A192F;'>
            <div class='kpi-label'>📋 전체 분석 문서 수</div>
            <div class='kpi-value'>{total_docs:,} 건</div>
            <div class='kpi-delta'>전체 이미지 240장 매칭</div>
        </div>
    """, unsafe_allow_html=True)

# KPI 2: 원시 OCR 성공률 (신뢰도 0.85 이상)
raw_success_mask = filtered_df['confidence'] >= 0.85
raw_success_rate = raw_success_mask.mean() * 100 if total_docs > 0 else 0
with kpi_card2:
    st.markdown(f"""
        <div class='kpi-card' style='border-top-color: #10B981;'>
            <div class='kpi-label'>🎯 원시 OCR 추출 성공률</div>
            <div class='kpi-value'>{raw_success_rate:.1f} %</div>
            <div class='kpi-delta'>신뢰도 85% 이상 정밀 추출</div>
        </div>
    """, unsafe_allow_html=True)

# KPI 3: 결측치 보완 및 보간 건수
total_imputed = (
    filtered_df['date_imputed'].sum() + 
    filtered_df['amount_imputed'].sum() + 
    filtered_df['scores_imputed'].sum()
)
with kpi_col3:
    st.markdown(f"""
        <div class='kpi-card' style='border-top-color: #F59E0B;'>
            <div class='kpi-label'>🛡️ 스마트 결측치 보완 건수</div>
            <div class='kpi-value'>{total_imputed} 건</div>
            <div class='kpi-delta'>날짜/금액/설문점수 자동 복구</div>
        </div>
    """, unsafe_allow_html=True)

# KPI 4: 유형별 핵심 가치 메트릭 (동적 표시)
with kpi_col4:
    if selected_doc_type == "Receipt (영수증)":
        total_amt = filtered_df['total_amount'].sum()
        st.markdown(f"""
            <div class='kpi-card' style='border-top-color: #00B4D8;'>
                <div class='kpi-label'>💰 총 영수증 집행 금액</div>
                <div class='kpi-value'>₩ {int(total_amt):,}</div>
                <div class='kpi-delta'>카테고리별 누적 총합</div>
            </div>
        """, unsafe_allow_html=True)
    elif selected_doc_type == "Survey (설문지)":
        avg_sat = filtered_df['satisfaction_score'].mean()
        st.markdown(f"""
            <div class='kpi-card' style='border-top-color: #00B4D8;'>
                <div class='kpi-label'>⭐ 설문 종합 평균 만족도</div>
                <div class='kpi-value'>{avg_sat:.2f} / 5.0</div>
                <div class='kpi-delta'>만족도/편의성/속도 종합</div>
            </div>
        """, unsafe_allow_html=True)
    else:
        # 전체 보기 시 하이브리드 메트릭
        avg_sat = df[df['document_type'] == 'survey']['satisfaction_score'].mean()
        st.markdown(f"""
            <div class='kpi-card' style='border-top-color: #00B4D8;'>
                <div class='kpi-label'>📊 설문 만족도 & 영수증 규모</div>
                <div class='kpi-value'>{avg_sat:.1f}점 / ₩{int(df[df['document_type']=='receipt']['total_amount'].sum()/10000):,}만</div>
                <div class='kpi-delta'>설문 평균 및 영수증 집행 총합</div>
            </div>
        """, unsafe_allow_html=True)

st.write("")

# ----------------------------------------------------
# 6. 중간 메인 시각화 영역 (좌우 2분할)
# ----------------------------------------------------
col_chart1, col_chart2 = st.columns([1, 1])

# 6-1. 좌측 차트: 영수증 또는 설문지 테마 차트
with col_chart1:
    st.markdown("<h3 style='color: #0A192F; font-size: 1.25rem;'>🎨 문서 범주별 세부 분석</h3>", unsafe_allow_html=True)
    
    if selected_doc_type == "Receipt (영수증)":
        # 카테고리별 금액 도넛 차트
        cat_df = filtered_df.groupby('category')['total_amount'].sum().reset_index()
        fig_donut = px.pie(
            cat_df, 
            values='total_amount', 
            names='category', 
            hole=0.4,
            color_discrete_sequence=['#0A192F', '#00B4D8', '#10B981', '#F59E0B', '#64748B']
        )
        fig_donut.update_layout(
            margin=dict(t=20, b=20, l=10, r=10),
            legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_donut, use_container_width=True)
        
    elif selected_doc_type == "Survey (설문지)":
        # 부서별 3대 만족도 지표 가로 막대 차트
        dept_scores = filtered_df.groupby('respondent_dept')[['satisfaction_score', 'usability_score', 'speed_score']].mean().reset_index()
        dept_scores_melted = dept_scores.melt(id_vars='respondent_dept', var_name='지표', value_name='평균점수')
        dept_scores_melted['지표'] = dept_scores_melted['지표'].map({
            'satisfaction_score': '전체 만족도',
            'usability_score': '사용 편의성',
            'speed_score': '응답 속도'
        })
        
        fig_bar = px.bar(
            dept_scores_melted,
            x='respondent_dept',
            y='평균점수',
            color='지표',
            barmode='group',
            color_discrete_sequence=['#0A192F', '#00B4D8', '#10B981']
        )
        fig_bar.update_layout(
            xaxis_title="부서명",
            yaxis_title="점수 (5점 만점)",
            margin=dict(t=20, b=20, l=10, r=10),
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        
    else:
        # 전체보기 시 두 형태를 모두 보여줌: 문서 유형 분포 비율 원형 차트
        type_df = filtered_df.groupby('document_type').size().reset_index(name='count')
        type_df['document_type'] = type_df['document_type'].map({'receipt': '영수증 (Receipt)', 'survey': '수기 설문지 (Survey)'})
        fig_pie = px.pie(
            type_df, 
            values='count', 
            names='document_type',
            hole=0.4,
            color_discrete_sequence=['#0A192F', '#00B4D8']
        )
        fig_pie.update_layout(
            margin=dict(t=20, b=20, l=10, r=10),
            legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_pie, use_container_width=True)

# 6-2. 우측 차트: 이미지 가독성 상태별 전처리 파급 효과 비교 분석 (★ 교육적 핵심 시각화)
with col_chart2:
    st.markdown("<h3 style='color: #0A192F; font-size: 1.25rem;'>⚡ 이미지 해상도/노이즈에 따른 전처리(OpenCV) 도입 효과</h3>", unsafe_allow_html=True)
    
    # 이미지 상태 분류 (Normal vs Bad)
    plot_df = filtered_df.copy()
    plot_df['image_status'] = plot_df.apply(lambda r: 'Bad (저해상도/노이즈)' if (r['has_noise'] or r['is_low_resolution']) else 'Normal (일반 고해상도)', axis=1)
    
    # 상태별 + 전처리사용여부별 평균 OCR 신뢰도 비교 계산
    group_stats = plot_df.groupby(['image_status', 'preprocessing_used'])['confidence'].mean().reset_index()
    group_stats['confidence_pct'] = group_stats['confidence'] * 100
    group_stats['preprocessing_used_str'] = group_stats['preprocessing_used'].map({True: 'OpenCV 전처리 적용', False: '기본 추출(전처리 미적용)'})
    
    fig_effect = px.bar(
        group_stats,
        x='image_status',
        y='confidence_pct',
        color='preprocessing_used_str',
        barmode='group',
        text=group_stats['confidence_pct'].apply(lambda x: f"{x:.1f}%"),
        color_discrete_sequence=['#10B981', '#64748B'] # 민트 (전처리 효과) vs 회색 (미적용)
    )
    
    fig_effect.update_layout(
        xaxis_title="이미지 가독성 상태",
        yaxis_title="평균 OCR 신뢰도 (Confidence %)",
        yaxis_range=[0, 110],
        margin=dict(t=20, b=20, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
    )
    fig_effect.update_traces(textposition='outside')
    st.plotly_chart(fig_effect, use_container_width=True)

# ----------------------------------------------------
# 7. 하단 영역: OCR 실패 혹은 점검이 시급한 데이터 리스트 테이블 (필터링 적용)
# ----------------------------------------------------
st.write("")
st.markdown("<h3 style='color: #0A192F; font-size: 1.3rem;'>⚠️ 수동 보완/검증 필요 문서 리스트</h3>", unsafe_allow_html=True)
st.markdown("<div style='font-size: 0.9rem; color: #64748B; margin-bottom: 0.8rem;'>OCR 정합성 신뢰도가 낮거나(80% 미만), 수기 메모 인식 불가로 '확인필요' 처리가 되었거나, 보간 정책이 강제로 적용된 정밀 수동 검수 대상들입니다.</div>", unsafe_allow_html=True)

# 정밀 검증 조건
alert_mask = (
    (filtered_df['confidence'] < 0.80) |
    (filtered_df['handwritten_note'] == "확인필요") |
    (filtered_df['amount_imputed'] == True) |
    (filtered_df['scores_imputed'] == True)
)

alert_df = filtered_df[alert_mask].copy()

# 보기 좋게 표 컬럼 정제 및 한글 레이블화
columns_to_show = [
    'record_id', 'document_type', 'doc_date', 'organization_or_store', 
    'respondent_dept', 'total_amount', 'satisfaction_score', 
    'handwritten_note', 'confidence', 'preprocessing_used'
]

# 컬럼 존재 확인 후 안전하게 추출
columns_to_show = [col for col in columns_to_show if col in alert_df.columns]

if len(alert_df) > 0:
    table_df = alert_df[columns_to_show].copy()
    table_df['document_type'] = table_df['document_type'].map({'receipt': '영수증', 'survey': '설문지'})
    table_df['confidence'] = table_df['confidence'].apply(lambda x: f"{x*100:.1f}%")
    table_df['preprocessing_used'] = table_df['preprocessing_used'].map({True: '적용', False: '미적용'})
    
    # 쉼표 포맷
    if 'total_amount' in table_df.columns:
        table_df['total_amount'] = table_df['total_amount'].apply(lambda x: f"{int(x):,}" if pd.notna(x) and x != "" else "")

    # 검색 창 제공
    search_query = st.text_input("🔍 테이블 검색 (문서ID, 상호명, 수기내용, 부서 등으로 검색하세요)", "")
    if search_query:
        # 전체 칼럼 문자열 포함 여부 체크로 유연한 실시간 검색 제공
        search_mask = table_df.astype(str).apply(lambda row: row.str.contains(search_query, case=False).any(), axis=1)
        table_df = table_df[search_mask]

    # 임원 보고에 맞추어 깔끔한 데이터 테이블 출력 (길지 않게 최대 12개 행으로 스크롤 제공)
    st.dataframe(table_df, use_container_width=True, height=350)
    st.markdown(f"**💡 필터링된 점검 필요 데이터: 총 {len(table_df)}건**")
else:
    st.success("✅ 전처리 및 보간이 완벽히 정제되었습니다. 수동 점검 대상 문서가 없습니다!")
