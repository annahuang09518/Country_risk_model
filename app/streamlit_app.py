"""
Country Risk Assessment Model - Streamlit Frontend

This application provides an interactive interface for the risk assessment model.
All business logic is delegated to the backend engines; this module only handles
UI, input collection, and result visualization.
"""

import streamlit as st
from pathlib import Path
from typing import Optional
import sys
import logging

# Add parent directory to path to import risk_model
sys.path.insert(0, str(Path(__file__).parent.parent))

from risk_model import ParameterLoader

logger = logging.getLogger(__name__)


DEMO_SCENARIOS = {
    "Low Risk Demo": {
        "country": "Singapore",
        "project_name": "Low Risk Demo Energy Project",
        "project_type": "Power Generation",
        "project_stage": "Operation",
        "investment_mode": "Greenfield",
        "currency": "USD",
        "assessment_horizon": 10,
        "country_bias": 0.8,
        "project_bias": 0.7,
    },
    "Medium Risk Demo": {
        "country": "Indonesia",
        "project_name": "Medium Risk Demo Energy Project",
        "project_type": "Renewable Energy",
        "project_stage": "Construction",
        "investment_mode": "Joint Venture",
        "currency": "USD",
        "assessment_horizon": 10,
        "country_bias": 1.5,
        "project_bias": 1.3,
    },
    "High Risk Demo": {
        "country": "Pakistan",
        "project_name": "High Risk Demo Energy Project",
        "project_type": "Transmission & Distribution",
        "project_stage": "Operation",
        "investment_mode": "Acquisition",
        "currency": "USD",
        "assessment_horizon": 10,
        "country_bias": 2.3,
        "project_bias": 2.2,
    },
}


def _apply_project_value_scenario(values: dict, scenario: str, index: int) -> dict:
    if scenario == "Low Risk Demo":
        base = 0.2 + (index % 5) * 0.08
    elif scenario == "Medium Risk Demo":
        base = 0.45 + (index % 5) * 0.12
    else:
        base = 0.7 + (index % 5) * 0.15
    for key in values:
        values[key] = round(float(values[key]) * (0.9 + base * 0.45), 2)
    return values


def _build_demo_data(scenario_name: str):
    scenario = DEMO_SCENARIOS[scenario_name]
    params = st.session_state.parameters
    country_data = {}
    project_data = {}

    country_bias = scenario["country_bias"]
    project_bias = scenario["project_bias"]

    for index, risk in enumerate(params.risks):
        rule = next((item for item in params.scoring_rules if item.risk_name == risk.level_3), None)
        risk_payload = {}
        if rule:
            if rule.level_indicator:
                level_value = 1 + country_bias * (1.2 + (index % 4) * 0.25)
                risk_payload[rule.level_indicator] = round(max(0.2, min(level_value, 9.5)), 2)
            if rule.trend_indicator:
                trend_value = 1 + (country_bias * 0.85) + (index % 3) * 0.35
                risk_payload[rule.trend_indicator] = round(max(0.2, min(trend_value, 9.5)), 2)
            if rule.event_indicator:
                event_value = 0.5 + country_bias * 0.7 + (index % 2) * 0.7
                risk_payload[rule.event_indicator] = round(max(0.0, min(event_value, 9.5)), 2)
        country_data[risk.level_3] = risk_payload

        project_payload = {
            "project_investment_amount": 500_000_000 * project_bias,
            "total_assets": 450_000_000 * project_bias,
            "annual_revenue": 120_000_000 * (project_bias * 0.9),
            "ebitda": 40_000_000 * (project_bias * 0.8),
            "annual_distributable_cash_flow": 30_000_000 * (project_bias * 0.8),
            "local_currency_revenue_share": 70 + index % 20,
            "foreign_currency_debt_share": 20 + (index % 40),
            "annual_profit_repatriation": 20_000_000 * project_bias,
            "government_soe_revenue_exposure": 20 + (index % 50),
            "project_staff_count": 500,
            "expected_operational_interruption_days": 5 + index % 15,
            "uninsured_asset_exposure": 10 + (index % 25),
            "import_equipment_fuel_exposure": 15 + (index % 35),
            "permits_licenses": 70 + (index % 25),
            "subsidies_tax_incentives": 50 + (index % 35),
            "ppa_tariff_characteristics": 60 + (index % 30),
        }
        project_data[risk.level_3] = project_payload

    return {
        "name": f"{scenario_name} - {scenario['country']}",
        "date": None,
        "country": scenario["country"],
        "project_name": scenario["project_name"],
        "project_type": scenario["project_type"],
        "project_stage": scenario["project_stage"],
        "investment_mode": scenario["investment_mode"],
        "currency": scenario["currency"],
        "assessment_horizon": scenario["assessment_horizon"],
        "country_data": country_data,
        "project_data": project_data,
    }


def load_demo_scenario(scenario_name: str):
    if scenario_name not in DEMO_SCENARIOS:
        return
    demo = _build_demo_data(scenario_name)
    st.session_state.assessment.update({
        "name": demo["name"],
        "date": None,
        "country": demo["country"],
        "project_name": demo["project_name"],
        "project_type": demo["project_type"],
        "project_stage": demo["project_stage"],
        "investment_mode": demo["investment_mode"],
        "currency": demo["currency"],
        "assessment_horizon": demo["assessment_horizon"],
    })
    st.session_state.country_data = demo["country_data"]
    st.session_state.project_data = demo["project_data"]
    st.session_state.results = "ready"
    st.session_state.active_demo = scenario_name


logger = logging.getLogger(__name__)

# Set page config
st.set_page_config(
    page_title="国别及项目风险评估模型",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Add styling
st.markdown("""
<style>
    [data-testid="stMetricDeltaContainer"] { display: none; }
    .risk-card-high { background: linear-gradient(135deg, #fff1f2, #fef2f2); border-left: 5px solid #dc2626; padding: 0.75rem 1rem; border-radius: 0.5rem; }
    .risk-card-medium { background: linear-gradient(135deg, #fff7ed, #fffbeb); border-left: 5px solid #f59e0b; padding: 0.75rem 1rem; border-radius: 0.5rem; }
    .risk-card-low { background: linear-gradient(135deg, #f0fdf4, #ecfdf5); border-left: 5px solid #16a34a; padding: 0.75rem 1rem; border-radius: 0.5rem; }
    .hero { background: linear-gradient(135deg, #0f172a, #1e293b); padding: 1.5rem 1.5rem; border-radius: 0.8rem; color: white; }
    .tag { background: #e2e8f0; color: #0f172a; padding: 0.3rem 0.6rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .section-label { font-size: 0.78rem; letter-spacing: 0.08em; color: #475569; text-transform: uppercase; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# Initialize session state
@st.cache_resource
def load_parameters():
    """Load and cache the workbook parameters."""
    loader = ParameterLoader()
    params = loader.load(Path(__file__).parent.parent / "data" / "model_parameters.xlsx")
    logger.info(f"Loaded {len(params.risks)} Level-3 risks from workbook")
    return params


def initialize_session_state():
    """Initialize all session state variables."""
    if "parameters" not in st.session_state:
        st.session_state.parameters = load_parameters()

    if "assessment" not in st.session_state:
        st.session_state.assessment = {
            "name": "",
            "date": None,
            "country": None,
            "project_name": "",
            "project_type": None,
            "project_stage": None,
            "investment_mode": None,
            "currency": "USD",
            "assessment_horizon": 10,
        }

    if "country_data" not in st.session_state:
        st.session_state.country_data = {}

    if "project_data" not in st.session_state:
        st.session_state.project_data = {}

    if "results" not in st.session_state:
        st.session_state.results = None

    if "data_completeness" not in st.session_state:
        st.session_state.data_completeness = 0

    if "active_demo" not in st.session_state:
        st.session_state.active_demo = "None"

    if "country_meta" not in st.session_state:
        st.session_state.country_meta = {}

    if "assessment" in st.session_state and "mode" not in st.session_state.assessment:
        st.session_state.assessment["mode"] = "country_project"

    if "country_automation" not in st.session_state:
        st.session_state.country_automation = None


# Initialize session
initialize_session_state()

# Sidebar navigation
st.sidebar.title("导航")
st.sidebar.markdown("<div class='tag'>国别及项目风险评估模型</div>", unsafe_allow_html=True)

_page_options = ["Overview", "Assessment Setup", "Country Risk Data", "Project Impact Input", "Risk Dashboard"]
_page_labels = {"Overview": "模型概览", "Assessment Setup": "评估设置", "Country Risk Data": "国家风险分析", "Project Impact Input": "项目影响评估", "Risk Dashboard": "风险评估结果"}

if "pending_nav" in st.session_state:
    st.session_state.nav_page = st.session_state.pop("pending_nav")
elif "nav_page" not in st.session_state:
    st.session_state.nav_page = "Overview"

page = st.sidebar.radio(
    "Select Page",
    _page_options,
    label_visibility="collapsed",
    key="nav_page",
    format_func=lambda x: _page_labels.get(x, x),
)


def _go_to(target_page: str, mode: Optional[str] = None) -> None:
    """Switch the active page (and optionally the assessment mode) then rerun."""
    if mode is not None:
        st.session_state.assessment["mode"] = mode
    st.session_state.pending_nav = target_page
    st.rerun()


if page == "Overview":
    st.markdown(
        '<div class="hero"><h2>国别及项目风险评估模型</h2>'
        '<p>基于权威国别数据、趋势信号及事件信息，对境外投资风险进行快速筛查；'
        '如提供项目基础信息，可进一步评估项目影响程度并形成综合风险等级。</p></div>',
        unsafe_allow_html=True,
    )
    st.write("")

    st.subheader("选择评估模式")
    mode_col1, mode_col2 = st.columns(2)
    with mode_col1:
        st.markdown(
            '<div class="risk-card-low"><b>A. 国家风险筛查</b><br/>'
            '仅选择国家，系统自动获取可用的权威数据并计算各三级风险的发生可能性、趋势和置信度。</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("开始国家风险筛查", use_container_width=True, key="start_country_only"):
            _go_to("Assessment Setup", mode="country_only")
    with mode_col2:
        st.markdown(
            '<div class="risk-card-medium"><b>B. 国家 + 项目风险评估</b><br/>'
            '在国家风险分析基础上，补充少量项目基础信息，进一步计算影响程度并形成最终高 / 中 / 低风险等级。</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("开始国家 + 项目风险评估", use_container_width=True, key="start_country_project"):
            _go_to("Assessment Setup", mode="country_project")

    st.caption("流程：选择评估模式 → 选择国家 → 国家风险分析 → 项目概况（可选） → 风险仪表盘")

elif page == "Assessment Setup":
    from app.views import assessment_setup
    assessment_setup.render()

elif page == "Country Risk Data":
    from app.views import country_risk_data
    country_risk_data.render()

elif page == "Project Impact Input":
    from app.views import project_impact
    project_impact.render()

elif page == "Risk Dashboard":
    from app.views import risk_dashboard
    risk_dashboard.render()

# Footer
st.sidebar.divider()
st.sidebar.caption("国别及项目风险评估模型")
st.sidebar.caption("Workbook-driven model")
