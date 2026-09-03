"""项目影响评估页面。

用户仅需填写一次项目基本情况，系统将这些信息映射到各三级风险的
影响程度计算中。底层影响程度评分逻辑保持不变，本页面仅负责收集、
校验和展示项目输入。
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from app.components.validation import workbook_impact_frame
from risk_model import ImpactEngine

# 01 项目基本情况
BASIC_FIELDS = [
    ("project_investment_amount", "项目总投资额", "项目预计或实际总投资金额，用于衡量重大风险事件可能影响的项目规模。"),
    ("total_assets", "项目总资产", "项目当前总资产规模；如项目尚未运营，可填写预计形成的资产规模。"),
]

# 02 财务与资金情况
FINANCIAL_FIELDS = [
    ("annual_revenue", "年度营业收入", "项目最近年度实际营业收入；尚未运营的项目可填写预计稳定运营年度收入。"),
    ("ebitda", "年度息税折旧摊销前利润（EBITDA）", "用于衡量项目经营收益及风险事件对盈利能力的潜在影响。"),
    ("annual_distributable_cash_flow", "年度可分配现金流", "项目年度可用于分红、偿债或再投资的现金流。"),
    ("annual_profit_repatriation", "预计年度跨境资金汇回金额", "项目每年预计汇回境内或其他境外主体的股息、利润、偿债资金等金额；如无跨境汇回需求，可填0。主要用于评估外汇管制和资本流动限制的潜在影响。"),
    ("foreign_currency_debt_share", "外币债务占比（%）", "项目有息债务中以外币计价的比例，主要用于评估汇率、外汇流动性和融资相关风险。"),
    ("local_currency_revenue_share", "本币收入占比（%）", "项目营业收入中以当地货币计价的比例，用于判断汇率变动及货币错配对项目的影响。"),
]

# 03 业务与经营依赖情况
BUSINESS_FIELDS = [
    ("government_soe_revenue_exposure", "政府及国有企业客户收入占比（%）", "项目年度收入中来自当地政府、政府机构或国有企业客户的比例，主要用于评估政府履约和公共部门支付风险。"),
    ("uninsured_asset_exposure", "未投保资产占比（%）", "项目资产中未由保险覆盖的比例，用于判断重大事件发生后的潜在资产损失程度。"),
    ("import_equipment_fuel_exposure", "进口设备及燃料依赖程度（%）", "项目生产经营所需关键设备、原材料、燃料或服务中依赖跨境进口的比例，主要用于评估贸易限制、关税和供应链中断影响。"),
    ("project_staff_count", "项目员工人数", "项目当前或预计直接雇佣员工人数，用于辅助判断运营中断、安全事件及劳工相关风险影响。"),
    ("expected_operational_interruption_days", "预计运营中断天数", "在相关风险事件发生时，预计项目可能中断运营的天数；如无法判断可留空。"),
]

# 04 政府审批与政策依赖情况
POLICY_FIELDS = [
    ("permits_licenses", "关键政府许可/审批依赖程度（0-100）", "用于反映项目持续建设或经营对特许经营权、电力业务许可、采矿许可、土地、环保等关键许可或审批的依赖程度；数值越高表示依赖越强。"),
    ("subsidies_tax_incentives", "补贴及税收优惠依赖程度（0-100）", "用于反映项目收益对政府补贴、税收优惠或其他政策支持的依赖程度；数值越高表示依赖越强。"),
    ("ppa_tariff_characteristics", "购电协议（PPA）/电价机制依赖程度（0-100）", "用于反映项目收入对购电协议、政府定价、限价或其他受监管价格机制的依赖程度；数值越高表示依赖越强。"),
]

ALL_FIELDS = BASIC_FIELDS + FINANCIAL_FIELDS + BUSINESS_FIELDS + POLICY_FIELDS

PERCENT_FIELDS = {
    "local_currency_revenue_share",
    "foreign_currency_debt_share",
    "government_soe_revenue_exposure",
    "uninsured_asset_exposure",
    "import_equipment_fuel_exposure",
    "permits_licenses",
    "subsidies_tax_incentives",
    "ppa_tariff_characteristics",
}

MONETARY_FIELDS = {
    "project_investment_amount",
    "total_assets",
    "annual_revenue",
    "ebitda",
    "annual_distributable_cash_flow",
    "annual_profit_repatriation",
}


def _coerce_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return text
    return value


def _validate_profile(profile: Dict[str, Any]) -> list[str]:
    errors = []
    for key, label, _help in ALL_FIELDS:
        value = profile.get(key)
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"{label}：请输入数字。")
            continue
        if key in PERCENT_FIELDS and not (0 <= value <= 100):
            errors.append(f"{label}：数值必须介于 0-100 之间（当前值 {value}）。")
        if key in MONETARY_FIELDS and value < 0:
            errors.append(f"{label}：金额不允许为负数。")
        if key in {"project_staff_count", "expected_operational_interruption_days"} and value < 0:
            errors.append(f"{label}：不允许为负数。")
    return errors


def _render_section(title: str, fields: list[tuple[str, str, str]], project_profile: Dict[str, Any]) -> None:
    st.subheader(title)
    cols = st.columns(2)
    for idx, (key, label, help_text) in enumerate(fields):
        with cols[idx % 2]:
            current = project_profile.get(key)
            value = st.text_input(
                label,
                value="" if current is None else str(current),
                key=f"profile_{key}",
                help=help_text,
                placeholder="不掌握可留空",
            )
            project_profile[key] = _coerce_value(value)
            st.caption(help_text)


def render():
    st.header("项目影响评估")
    st.write(
        "请填写项目基本情况。系统将结合项目规模、财务情况、业务依赖及监管特征，"
        "自动评估各项国别风险发生后可能对项目造成的影响程度。无需对各项风险逐一评分。"
    )
    st.info("仅填写已掌握的信息即可；未填写的数据将标记为“待评估”，不会默认按0处理。无需准备完整财务模型。")

    params = st.session_state.parameters
    if params is None:
        st.warning("模型参数尚未加载。")
        return

    project_profile = st.session_state.project_data.setdefault("_profile", {})

    _render_section("01 项目基本情况", BASIC_FIELDS, project_profile)
    _render_section("02 财务与资金情况", FINANCIAL_FIELDS, project_profile)
    _render_section("03 业务与经营依赖情况", BUSINESS_FIELDS, project_profile)
    _render_section("04 政府审批与政策依赖情况", POLICY_FIELDS, project_profile)

    completed = sum(1 for key, _label, _help in ALL_FIELDS if project_profile.get(key) is not None)
    total = len(ALL_FIELDS)
    st.progress(completed / total if total else 0)
    st.caption(f"项目信息完整度：{completed} / {total} 项")

    validation_errors = _validate_profile(project_profile)
    if validation_errors:
        st.error("输入校验未通过：")
        for err in validation_errors:
            st.write(f"- {err}")

    # 将一份项目基础信息应用到全部三级风险；不改变底层 ImpactEngine 的计算方式。
    if not validation_errors:
        for risk in params.risks:
            st.session_state.project_data[risk.level_3] = dict(project_profile)

    st.divider()
    st.subheader("影响程度结果预览")
    if validation_errors:
        st.info("请先修正上方校验错误后再查看影响程度结果。")
    else:
        impact_rules_df = workbook_impact_frame(params)
        preview_rows = []
        for risk in params.risks:
            rule = next((item for item in params.impact_rules if item.risk_name == risk.level_3), None)
            if rule is None:
                continue
            result = ImpactEngine.score_risk(risk.level_3, project_profile, impact_rules_df)
            preview_rows.append(
                {
                    "三级风险": risk.level_3,
                    "影响程度原始分": None if result.raw_score is None else round(result.raw_score, 2),
                    "影响程度评分": result.discrete_score,
                    "评估状态": "待评估" if result.missing_data else "已评估",
                    "是否触发最低评分": "是" if result.applied_floor is not None else "否",
                }
            )
        if preview_rows:
            st.dataframe(preview_rows, use_container_width=True, hide_index=True)

    st.divider()
    if st.button("生成风险评估结果", use_container_width=True, disabled=bool(validation_errors)):
        st.session_state.results = "ready"
        st.success("项目信息已确认，请前往“风险评估结果”查看完整结果。")
