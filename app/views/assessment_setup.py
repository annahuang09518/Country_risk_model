"""
Page 1: Assessment Setup

Collects assessment metadata including country, project details, and assessment context.
Persists all inputs to session_state for use in subsequent pages.
"""

import streamlit as st
from datetime import date, timedelta

# All country/economy selectors use the same global ISO master as the
# country-risk automation page. This avoids maintaining two inconsistent lists.
from src.country_reference import all_country_display_names, lookup_by_display_name, lookup_country

COUNTRIES = all_country_display_names()

PROJECT_TYPES = [
    "Power Generation",
    "Renewable Energy",
    "Hydropower",
    "Thermal Power",
    "Transmission & Distribution",
    "Energy Infrastructure",
    "Water & Sanitation",
    "Transportation",
    "Telecommunications",
    "Oil & Gas",
    "Mining",
    "Other",
]

PROJECT_STAGES = [
    "Opportunity Screening",
    "Due Diligence",
    "Investment Decision",
    "Construction",
    "Operation",
    "Exit",
]

INVESTMENT_MODES = [
    "Greenfield",
    "Brownfield",
    "Acquisition",
    "Joint Venture",
    "Minority Investment",
]

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CNY", "INR", "BRL", "AUD", "CAD", "Other"]

PROJECT_TYPE_LABELS = {
    "Power Generation": "发电", "Renewable Energy": "可再生能源", "Hydropower": "水电",
    "Thermal Power": "火电", "Transmission & Distribution": "输配电", "Energy Infrastructure": "能源基础设施",
    "Water & Sanitation": "水务与环境卫生", "Transportation": "交通运输", "Telecommunications": "电信",
    "Oil & Gas": "石油与天然气", "Mining": "采矿", "Other": "其他",
}
PROJECT_STAGE_LABELS = {
    "Opportunity Screening": "机会筛选", "Due Diligence": "尽职调查", "Investment Decision": "投资决策",
    "Construction": "建设期", "Operation": "运营期", "Exit": "退出期",
}
INVESTMENT_MODE_LABELS = {
    "Greenfield": "绿地投资", "Brownfield": "棕地投资", "Acquisition": "并购",
    "Joint Venture": "合资", "Minority Investment": "少数股权投资",
}
CURRENCY_LABELS = {"USD":"美元", "EUR":"欧元", "GBP":"英镑", "JPY":"日元", "CNY":"人民币", "INR":"印度卢比", "BRL":"巴西雷亚尔", "AUD":"澳元", "CAD":"加元", "Other":"其他"}


def render():
    """Render the Assessment Setup page."""
    
    st.header("评估设置")
    st.write("设置评估背景及项目基本信息")
    
    # Create two columns for better layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("评估信息")
        
        # Assessment Name
        assessment_name = st.text_input(
            "评估名称",
            value=st.session_state.assessment.get("name", ""),
            help="用于识别本次评估的名称",
        )
        st.session_state.assessment["name"] = assessment_name
        
        # Assessment Date
        assessment_date = st.date_input(
            "评估日期",
            value=st.session_state.assessment.get("date") or date.today(),
            help="本次评估的基准日期",
        )
        st.session_state.assessment["date"] = assessment_date
        
        # Country / economy.  Store canonical ISO3 in session state so every
        # downstream connector receives the same identifier, while the UI remains
        # Chinese-first and bilingual.
        current_country = st.session_state.assessment.get("country")
        current_entry = lookup_country(current_country) if current_country else None
        current_display = (
            f"{current_entry.country_name_cn}（{current_entry.country_name_en}）"
            if current_entry else None
        )
        country_index = COUNTRIES.index(current_display) if current_display in COUNTRIES else None
        country_display = st.selectbox(
            "国家 / 经济体",
            COUNTRIES,
            index=country_index,
            placeholder="请选择国家或经济体...",
            help="覆盖全球 ISO 3166-1 国家及经济体；部分数据源对个别经济体可能暂无数据。",
        )
        country_entry = lookup_by_display_name(country_display) if country_display else None
        st.session_state.assessment["country"] = country_entry.iso3 if country_entry else None
        st.session_state.assessment["country_display"] = country_display
    
    with col2:
        st.subheader("项目信息")
        
        # Project Name
        project_name = st.text_input(
            "项目名称",
            value=st.session_state.assessment.get("project_name", ""),
            help="请输入项目名称",
        )
        st.session_state.assessment["project_name"] = project_name
        
        # Project Type
        project_type = st.selectbox(
            "项目类型",
            PROJECT_TYPES,
            index=None,
            placeholder="请选择项目类型...",
            format_func=lambda x: PROJECT_TYPE_LABELS.get(x, x),
        )
        st.session_state.assessment["project_type"] = project_type
        
        # Project Stage
        project_stage = st.selectbox(
            "项目阶段",
            PROJECT_STAGES,
            index=None,
            placeholder="请选择项目阶段...",
            format_func=lambda x: PROJECT_STAGE_LABELS.get(x, x),
        )
        st.session_state.assessment["project_stage"] = project_stage
    
    # Investment Mode and Financial Details
    col3, col4 = st.columns(2)

    with col3:
        investment_mode = st.selectbox(
            "投资模式",
            INVESTMENT_MODES,
            index=None,
            placeholder="请选择投资模式...",
            format_func=lambda x: INVESTMENT_MODE_LABELS.get(x, x),
        )
        st.session_state.assessment["investment_mode"] = investment_mode

    with col4:
        currency = st.selectbox(
            "币种",
            CURRENCIES,
            index=CURRENCIES.index(st.session_state.assessment.get("currency", "USD")),
            format_func=lambda x: CURRENCY_LABELS.get(x, x),
        )
        st.session_state.assessment["currency"] = currency

    st.divider()
    st.subheader("评估模式")
    assessment_mode = st.radio(
        "评估模式",
        ["国别风险筛查", "国别 + 项目风险筛查"],
        index=0 if st.session_state.assessment.get("mode", "country_project") == "country_only" else 1,
        help="国别风险筛查仅计算发生可能性；国别 + 项目风险筛查将进一步计算项目影响程度及综合风险等级。",
    )
    st.session_state.assessment["mode"] = (
        "country_only" if assessment_mode.startswith("国别风险筛查") else "country_project"
    )
    
    # Assessment Horizon
    assessment_horizon = st.slider(
        "评估期限（年）",
        min_value=1,
        max_value=50,
        value=st.session_state.assessment.get("assessment_horizon", 10),
        help="项目期限或本次风险评估覆盖期间",
    )
    st.session_state.assessment["assessment_horizon"] = assessment_horizon
    
    # Validation and Next Steps
    st.divider()
    
    # Validate required fields
    required_fields = ["name", "country", "project_name", "project_type", "project_stage"]
    has_required = all(st.session_state.assessment.get(field) for field in required_fields)
    
    if has_required:
        st.success("✓ 评估设置已完成，请进入国家风险分析。")
    else:
        missing = [f for f in required_fields if not st.session_state.assessment.get(f)]
        field_labels = {"name":"评估名称", "country":"国家", "project_name":"项目名称", "project_type":"项目类型", "project_stage":"项目阶段"}
        st.warning(f"⚠ 以下必填项尚未填写：{', '.join(field_labels.get(f, f) for f in missing)}")
    
    # Display current state (for debugging)
    if st.checkbox("显示评估详情"):
        st.json(st.session_state.assessment)

