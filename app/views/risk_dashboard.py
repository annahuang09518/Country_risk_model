from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.validation import calculate_data_quality, workbook_impact_frame, workbook_scoring_frame
from risk_model import ImpactEngine, IndicatorScoringEngine, LikelihoodEngine, RiskRatingEngine


def _score_indicator_for_rule(risk_name: str, indicator_name: str, signal_type: str, raw_value: Any, rule) -> Any:
    if not indicator_name:
        return None
    score_map = {
        "Level": [rule.score_1, rule.score_2, rule.score_3, rule.score_4, rule.score_5],
        "Trend": [rule.trend_1, rule.trend_2, rule.trend_3, rule.trend_4, rule.trend_5],
        "Event": [rule.event_1, rule.event_2, rule.event_3, rule.event_4, rule.event_5],
    }
    payload = {"risk_id": risk_name, "indicator_id": indicator_name, "signal_type": signal_type}
    for idx, band in enumerate(score_map.get(signal_type, []), start=1):
        payload[f"score_{idx}"] = band
    table = pd.DataFrame([payload])
    return IndicatorScoringEngine.score_indicator(
        risk_id=risk_name,
        indicator_id=indicator_name,
        raw_value=raw_value,
        parameter_table=table,
        signal_type=signal_type,
    )


def _risk_rank_label(value: Any) -> int:
    mapping = {"High": 0, "Medium": 1, "Low": 2, "N/A": 3}
    return mapping.get(str(value), 99)


def _derive_confidence(data_quality: Dict[str, Any]) -> str:
    pct = data_quality.get("data_completeness_pct", 0.0)
    if pct >= 85:
        return "High"
    if pct >= 60:
        return "Medium"
    return "Low"


def _risk_summary_table() -> pd.DataFrame:
    params = st.session_state.parameters
    rows: List[Dict[str, Any]] = []

    scoring_df = workbook_scoring_frame(params)
    impact_df = workbook_impact_frame(params)
    for risk in params.risks:
        country_values = st.session_state.country_data.get(risk.level_3, {})
        project_values = st.session_state.project_data.get(risk.level_3, {})
        likelihood_result = LikelihoodEngine.score_risk(risk.level_3, country_values, scoring_df)
        impact_result = ImpactEngine.score_risk(risk.level_3, project_values, impact_df)
        rating_result = RiskRatingEngine.score_risk(
            risk.level_3,
            country_values,
            project_values,
            scoring_df,
            impact_df,
            params.risk_matrix_df,
            risk_override_text=risk.override_rule,
        )

        data_quality = calculate_data_quality(params, st.session_state.country_data, st.session_state.project_data)
        trend_value = likelihood_result.trend_subscore
        confidence_value = _derive_confidence(data_quality)

        rows.append(
            {
                "Level-1 Risk": risk.level_1,
                "Level-2 Risk": risk.level_2,
                "Level-3 Risk": risk.level_3,
                "Likelihood Raw": likelihood_result.weighted_raw_score,
                "Likelihood Rating": likelihood_result.discrete_score,
                "Impact Raw": impact_result.raw_score,
                "Impact Rating": impact_result.discrete_score,
                "Baseline Risk": rating_result.baseline_risk_rating,
                "Override": rating_result.override_triggered,
                "Final Risk": rating_result.final_risk_rating,
                "Trend": trend_value,
                "Confidence": confidence_value,
                "Top Driver 1": likelihood_result.top_contributing_indicators[0].indicator_id if likelihood_result.top_contributing_indicators else "",
                "Top Driver 2": likelihood_result.top_contributing_indicators[1].indicator_id if len(likelihood_result.top_contributing_indicators) > 1 else "",
                "Top Driver 3": likelihood_result.top_contributing_indicators[2].indicator_id if len(likelihood_result.top_contributing_indicators) > 2 else "",
                "_FinalPriority": _risk_rank_label(rating_result.final_risk_rating),
                "_Likelihood": likelihood_result.discrete_score,
                "_Impact": impact_result.discrete_score,
                "_RiskResult": rating_result,
                "_LikelihoodResult": likelihood_result,
                "_ImpactResult": impact_result,
                "_RuleRow": next((item for item in params.scoring_rules if item.risk_name == risk.level_3), None),
            }
        )

    summary = pd.DataFrame(rows)
    if summary.empty:
        st.session_state.risk_details = {}
        return summary
    summary = summary.sort_values(["_FinalPriority", "Level-1 Risk", "Level-2 Risk", "Level-3 Risk"], ascending=[True, True, True, True])
    detail_lookup = {row["Level-3 Risk"]: row for _, row in summary.iterrows()}
    st.session_state.risk_details = detail_lookup
    return summary.drop(columns=["_FinalPriority", "_Likelihood", "_Impact", "_RiskResult", "_LikelihoodResult", "_ImpactResult", "_RuleRow"])


def _build_detail_for_risk(selected_risk: str, summary_df: pd.DataFrame) -> Dict[str, Any]:
    risk_key = selected_risk
    params = st.session_state.parameters
    row = summary_df[summary_df["Level-3 Risk"] == risk_key].iloc[0]
    risk_name = risk_key
    risk_record = next((item for item in params.risks if item.level_3 == risk_name), None)
    rule = next((item for item in params.scoring_rules if item.risk_name == risk_name), None)
    impact_rule = next((item for item in params.impact_rules if item.risk_name == risk_name), None)
    likelihood_result = row.get("_LikelihoodResult") if "_LikelihoodResult" in row else None
    impact_result = row.get("_ImpactResult") if "_ImpactResult" in row else None
    rating_result = row.get("_RiskResult") if "_RiskResult" in row else None
    return {
        "risk": risk_record,
        "rule": rule,
        "impact_rule": impact_rule,
        "likelihood_result": likelihood_result,
        "impact_result": impact_result,
        "rating_result": rating_result,
    }


def _export_assessment_excel(summary_df: pd.DataFrame) -> bytes:
    assessment = st.session_state.assessment
    country_data = st.session_state.country_data
    project_data = st.session_state.project_data
    country_meta = getattr(st.session_state, "country_meta", {})
    data_quality = calculate_data_quality(st.session_state.parameters, country_data, project_data)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Level-3 Risk Results", index=False)
        pd.DataFrame([assessment]).to_excel(writer, sheet_name="Assessment Summary", index=False)
        pd.DataFrame([data_quality]).to_excel(writer, sheet_name="Data Quality and Confidence", index=False)

        country_rows = []
        for risk_name, values in country_data.items():
            for indicator, raw_value in values.items():
                row = {"Risk": risk_name, "Indicator": indicator, "原始值": raw_value}
                row.update(country_meta.get(risk_name, {}).get(indicator, {}))
                country_rows.append(row)
        pd.DataFrame(country_rows).to_excel(writer, sheet_name="Raw Country Inputs", index=False)

        project_rows = []
        for risk_name, values in project_data.items():
            for metric, raw_value in values.items():
                project_rows.append({"Risk": risk_name, "项目指标": metric, "原始值": raw_value})
        pd.DataFrame(project_rows).to_excel(writer, sheet_name="Raw Project Inputs", index=False)

        likelihood_rows = []
        impact_rows = []
        override_rows = []
        scoring_df = workbook_scoring_frame(st.session_state.parameters)
        impact_df = workbook_impact_frame(st.session_state.parameters)
        for risk in st.session_state.parameters.risks:
            risk_name = risk.level_3
            country_values = st.session_state.country_data.get(risk_name, {})
            project_values = st.session_state.project_data.get(risk_name, {})
            likelihood_result = LikelihoodEngine.score_risk(risk_name, country_values, scoring_df)
            impact_result = ImpactEngine.score_risk(risk_name, project_values, impact_df)
            rating_result = RiskRatingEngine.score_risk(
                risk_name,
                country_values,
                project_values,
                scoring_df,
                impact_df,
                st.session_state.parameters.risk_matrix_df,
                risk_override_text=risk.override_rule,
            )
            for c in likelihood_result.top_contributing_indicators:
                likelihood_rows.append(
                    {
                        "Risk": risk_name,
                        "Indicator": c.indicator_id,
                        "Type": c.signal_type,
                        "原始值": c.raw_value,
                        "标准化评分": c.sub_score,
                        "Weight": c.weight,
                        "加权贡献": c.weighted_contribution,
                        "缺失 Data": c.missing_data,
                    }
                )
            for c in impact_result.contributors:
                impact_rows.append(
                    {
                        "Risk": risk_name,
                        "项目指标": c.metric_name,
                        "原始值": c.raw_value,
                        "Normalized Value": c.normalized_value,
                        "Score": c.score,
                        "匹配区间": c.matched_band,
                        "评分说明": c.rationale,
                    }
                )
            override_rows.append(
                {
                    "Risk": risk_name,
                    "Likelihood Raw": likelihood_result.weighted_raw_score,
                    "Likelihood Rating": likelihood_result.discrete_score,
                    "Impact Raw": impact_result.raw_score,
                    "Impact Rating": impact_result.discrete_score,
                    "Baseline Risk": rating_result.baseline_risk_rating,
                    "Override Triggered": rating_result.override_triggered,
                    "Override Reason": rating_result.override_reason,
                    "Final Risk": rating_result.final_risk_rating,
                }
            )

        pd.DataFrame(likelihood_rows).to_excel(writer, sheet_name="Likelihood Calculation Details", index=False)
        pd.DataFrame(impact_rows).to_excel(writer, sheet_name="Impact Calculation Details", index=False)
        pd.DataFrame(override_rows).to_excel(writer, sheet_name="Override-RedLine Results", index=False)

    return buffer.getvalue()


def _zh_value(value: Any) -> Any:
    return {"High":"高", "Medium":"中", "Low":"低", "N/A":"暂未评估", "Stable":"稳定", "Improving":"改善", "Deteriorating":"恶化", "Yes":"是", "No":"否", True:"是", False:"否"}.get(value, value)

def _display_summary(df: pd.DataFrame) -> pd.DataFrame:
    column_map = {
        "Level-1 Risk":"一级风险", "Level-2 Risk":"二级风险", "Level-3 Risk":"三级风险",
        "Likelihood Raw":"发生可能性原始分", "Likelihood Rating":"发生可能性评分",
        "Impact Raw":"影响程度原始分", "Impact Rating":"影响程度评分",
        "Baseline Risk":"基准风险等级", "Final Risk":"综合风险等级",
        "Override":"特殊调整", "Trend":"趋势", "Confidence":"置信度"
    }
    out = df.rename(columns=column_map).copy()
    for col in ["基准风险等级", "综合风险等级", "特殊调整", "趋势", "置信度"]:
        if col in out.columns:
            out[col] = out[col].map(_zh_value)
    return out

def _management_risk_level(row: pd.Series, mode: str) -> str:
    if mode == "country_only":
        score = row.get("Likelihood Rating")
        if score is None or pd.isna(score):
            return "N/A"
        if float(score) >= 4:
            return "High"
        if float(score) >= 3:
            return "Medium"
        return "Low"
    return str(row.get("Final Risk") or "N/A")


def _overall_management_level(summary: pd.DataFrame, mode: str) -> str:
    if summary.empty:
        return "N/A"
    levels = summary.apply(lambda row: _management_risk_level(row, mode), axis=1)
    if (levels == "High").any():
        return "High"
    if (levels == "Medium").any():
        return "Medium"
    if (levels == "Low").any():
        return "Low"
    return "N/A"


def _level_style(level: str) -> Dict[str, str]:
    return {
        "High": {"bg": "#fef2f2", "border": "#dc2626", "text": "#991b1b"},
        "Medium": {"bg": "#fffbeb", "border": "#f59e0b", "text": "#92400e"},
        "Low": {"bg": "#f0fdf4", "border": "#16a34a", "text": "#166534"},
        "N/A": {"bg": "#f8fafc", "border": "#94a3b8", "text": "#475569"},
    }.get(level, {"bg": "#f8fafc", "border": "#94a3b8", "text": "#475569"})


def _management_summary_sentence(overall: str, counts: Dict[str, int], mode: str) -> str:
    high = counts.get("High", 0)
    medium = counts.get("Medium", 0)
    low = counts.get("Low", 0)
    pending = counts.get("N/A", 0)
    prefix = "基于当前可获取的国别数据" if mode == "country_only" else "基于国别风险发生可能性与项目影响程度"
    if overall == "High":
        conclusion = f"整体风险关注等级为高，当前识别出 {high} 项高风险；另有 {medium} 项中风险、{low} 项低风险"
    elif overall == "Medium":
        conclusion = f"整体风险关注等级为中，当前无高风险，识别出 {medium} 项中风险；低风险 {low} 项"
    elif overall == "Low":
        conclusion = "整体风险关注等级为低，当前未识别出高风险或中风险"
    else:
        conclusion = "当前数据不足以形成完整的整体风险判断"
    if pending:
        conclusion += f"，另有 {pending} 项待评估"
    return f"{prefix}，{conclusion}。"


def _risk_reason_summary(row: pd.Series, mode: str) -> str:
    driver = row.get("Top Driver 1") or "关键国别指标"
    trend = _zh_value(row.get("Trend"))
    likelihood = row.get("Likelihood Rating")
    impact = row.get("Impact Rating")
    if mode == "country_only":
        return f"发生可能性 {likelihood}/5；主要关注因素：{driver}；风险趋势：{trend}。"
    impact_text = "待评估" if impact is None or pd.isna(impact) else f"{impact}/5"
    return f"发生可能性 {likelihood}/5，影响程度 {impact_text}；主要关注因素：{driver}；趋势：{trend}。"


def _render_risk_matrix(params, summary: pd.DataFrame):
    matrix = params.risk_matrix_df.copy()
    z = matrix.applymap(lambda v: {"Low": 0, "Medium": 1, "High": 2}.get(str(v), 0)).astype(float)
    fig = go.Figure(
        data=go.Heatmap(
            z=z.values,
            x=list(z.columns),
            y=list(reversed(z.index)),
            text=matrix.replace({"High": "高", "Medium": "中", "Low": "低"}).values,
            texttemplate="%{text}",
            hovertemplate="发生可能性 %{y}<br>影响程度 %{x}<br>风险等级 %{text}<extra></extra>",
            colorscale=[[0, "#22c55e"], [0.5, "#f59e0b"], [1, "#ef4444"]],
            zmin=0,
            zmax=2,
            showscale=False,
            xgap=2,
            ygap=2,
        )
    )
    for risk in params.risks:
        rating_rows = summary[summary["Level-3 Risk"] == risk.level_3]
        if rating_rows.empty:
            continue
        rating_row = rating_rows.iloc[0]
        x_value = rating_row["Impact Rating"]
        y_value = rating_row["Likelihood Rating"]
        if x_value is None or y_value is None or pd.isna(x_value) or pd.isna(y_value):
            continue
        fig.add_trace(go.Scatter(
            x=[x_value], y=[y_value], mode="markers",
            marker={"size": 11, "color": {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}.get(str(rating_row["Final Risk"]), "#64748b")},
            hovertemplate=f"{risk.level_3}<br>发生可能性 {y_value}<br>影响程度 {x_value}<extra></extra>",
            showlegend=False,
        ))
    fig.update_layout(
        xaxis_title="影响程度 1–5", yaxis_title="发生可能性 1–5",
        template="plotly_white", height=460,
        margin={"l": 30, "r": 30, "t": 20, "b": 30},
    )
    st.plotly_chart(fig, use_container_width=True)


def render():
    st.header("风险评估结果")
    st.caption("先看整体风险判断，再按需展开重点风险及单项风险解释。")

    params = st.session_state.parameters
    if params is None:
        st.warning("模型参数尚未加载。")
        return

    summary = _risk_summary_table()
    if summary.empty:
        st.info("暂无风险评估结果，请先完成评估设置及必要的数据输入。")
        return

    assessment = st.session_state.assessment
    mode = assessment.get("mode", "country_project")
    country_name = assessment.get("country_display") or assessment.get("country") or "当前国家"
    project_name = assessment.get("project_name") or "未填写项目名称"
    data_quality = calculate_data_quality(params, st.session_state.country_data, st.session_state.project_data)

    management_levels = summary.apply(lambda row: _management_risk_level(row, mode), axis=1)
    counts = management_levels.value_counts().to_dict()
    overall = _overall_management_level(summary, mode)
    style = _level_style(overall)
    mode_text = "国家风险筛查" if mode == "country_only" else "国家 + 项目风险评估"

    st.markdown(
        f'''<div style="background:{style['bg']};border-left:7px solid {style['border']};padding:22px 26px;border-radius:10px;margin:10px 0 18px 0;">
        <div style="font-size:15px;color:#64748b;margin-bottom:6px;">总体风险判断 · {mode_text}</div>
        <div style="font-size:34px;font-weight:700;color:{style['text']};margin-bottom:8px;">{_zh_value(overall)}风险</div>
        <div style="font-size:18px;font-weight:600;color:#1f2937;margin-bottom:8px;">{country_name}{' · ' + project_name if mode != 'country_only' else ''}</div>
        <div style="font-size:16px;line-height:1.7;color:#374151;">{_management_summary_sentence(overall, counts, mode)}</div>
        </div>''',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("高风险", counts.get("High", 0))
    c2.metric("中风险", counts.get("Medium", 0))
    c3.metric("低风险", counts.get("Low", 0))
    c4.metric("待评估", counts.get("N/A", 0))

    st.divider()
    st.subheader("管理层重点关注")
    st.caption("优先展示高风险和中风险事项。点击风险名称可查看原因与评分依据。")

    focus = summary.copy()
    focus["_MgmtLevel"] = management_levels.values
    priority = {"High": 0, "Medium": 1, "Low": 2, "N/A": 3}
    focus["_Priority"] = focus["_MgmtLevel"].map(priority).fillna(99)
    focus = focus.sort_values(["_Priority", "Likelihood Rating", "Impact Rating"], ascending=[True, False, False])
    focus = focus[focus["_MgmtLevel"].isin(["High", "Medium"])].head(6)

    if focus.empty:
        st.success("当前未识别出需要管理层重点关注的高风险或中风险事项。")
    else:
        for _, row in focus.iterrows():
            level = row["_MgmtLevel"]
            with st.expander(f"{_zh_value(level)}风险｜{row['Level-3 Risk']}", expanded=False):
                a, b, c = st.columns(3)
                a.metric("发生可能性", f"{row['Likelihood Rating']}/5" if pd.notna(row["Likelihood Rating"]) else "待评估")
                if mode == "country_only":
                    b.metric("风险趋势", _zh_value(row["Trend"]))
                    c.metric("数据置信度", _zh_value(row["Confidence"]))
                else:
                    b.metric("影响程度", f"{row['Impact Rating']}/5" if pd.notna(row["Impact Rating"]) else "待评估")
                    c.metric("风险趋势", _zh_value(row["Trend"]))
                st.write(_risk_reason_summary(row, mode))
                drivers = [row.get("Top Driver 1"), row.get("Top Driver 2"), row.get("Top Driver 3")]
                drivers = [d for d in drivers if d]
                if drivers:
                    st.write("**主要影响因素：** " + "、".join(drivers))
                if mode != "country_only":
                    st.write(f"**综合风险等级：** {_zh_value(row['Final Risk'])}；**基准风险等级：** {_zh_value(row['Baseline Risk'])}")
                    if bool(row.get("Override")):
                        st.warning("该风险触发了特殊调整规则，最终等级可能高于风险矩阵的基准结果。")

    st.divider()
    st.subheader("全部风险一览")
    st.caption("默认仅展示管理层最需要的字段；完整计算过程可在下方单项风险解释中查看。")

    f1, f2, f3 = st.columns(3)
    level_filter = f1.selectbox("风险等级", ["All", "High", "Medium", "Low", "N/A"], format_func=lambda x: {"All": "全部", "High": "高", "Medium": "中", "Low": "低", "N/A": "待评估"}.get(x, x))
    level1_filter = f2.selectbox("一级风险", ["All"] + sorted(summary["Level-1 Risk"].dropna().unique().tolist()), format_func=lambda x: "全部" if x == "All" else x)
    trend_filter = f3.selectbox("趋势", ["All"] + sorted(summary["Trend"].dropna().astype(str).unique().tolist()), format_func=lambda x: "全部" if x == "All" else _zh_value(x))

    table = summary.copy()
    table["管理层风险等级"] = management_levels.values
    if level_filter != "All": table = table[table["管理层风险等级"] == level_filter]
    if level1_filter != "All": table = table[table["Level-1 Risk"] == level1_filter]
    if trend_filter != "All": table = table[table["Trend"].astype(str) == trend_filter]
    table["_Priority"] = table["管理层风险等级"].map(priority).fillna(99)
    table = table.sort_values(["_Priority", "Likelihood Rating", "Impact Rating"], ascending=[True, False, False])
    simple_cols = ["Level-1 Risk", "Level-2 Risk", "Level-3 Risk", "管理层风险等级", "Likelihood Rating", "Trend", "Confidence"]
    if mode != "country_only": simple_cols.insert(5, "Impact Rating")
    simple = table[simple_cols].copy().rename(columns={
        "Level-1 Risk": "一级风险", "Level-2 Risk": "二级风险", "Level-3 Risk": "三级风险",
        "管理层风险等级": "风险等级", "Likelihood Rating": "发生可能性", "Impact Rating": "影响程度",
        "Trend": "趋势", "Confidence": "数据置信度",
    })
    for col in ["风险等级", "趋势", "数据置信度"]:
        if col in simple.columns: simple[col] = simple[col].map(_zh_value)
    st.dataframe(simple, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("单项风险解释")
    st.caption("选择任一三级风险，查看“结论—原因—计算依据”的完整解释。")
    selected_risk = st.selectbox("选择三级风险", summary["Level-3 Risk"].tolist())
    details_by_risk = st.session_state.get("risk_details", {})
    selected_detail = details_by_risk.get(selected_risk, {})
    risk_row = summary[summary["Level-3 Risk"] == selected_risk].iloc[0]
    risk_result = selected_detail.get("_RiskResult")
    likelihood_result = selected_detail.get("_LikelihoodResult")
    impact_result = selected_detail.get("_ImpactResult")
    rule = next((item for item in params.scoring_rules if item.risk_name == selected_risk), None)
    selected_mgmt_level = _management_risk_level(risk_row, mode)
    detail_style = _level_style(selected_mgmt_level)

    st.markdown(
        f'''<div style="background:{detail_style['bg']};border-left:5px solid {detail_style['border']};padding:16px 20px;border-radius:8px;margin:8px 0 14px 0;">
        <strong style="font-size:19px;color:#111827;">{selected_risk}</strong><br>
        <span style="font-size:16px;color:{detail_style['text']};font-weight:700;">当前判断：{_zh_value(selected_mgmt_level)}风险</span><br>
        <span style="color:#374151;line-height:1.7;">{_risk_reason_summary(risk_row, mode)}</span>
        </div>''', unsafe_allow_html=True)

    with st.expander("展开查看详细解释与计算依据", expanded=False):
        st.markdown("#### 1. 结论说明")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("风险等级", _zh_value(selected_mgmt_level))
        c2.metric("发生可能性", f"{risk_row['Likelihood Rating']}/5" if pd.notna(risk_row["Likelihood Rating"]) else "待评估")
        c3.metric("影响程度" if mode != "country_only" else "风险趋势", f"{risk_row['Impact Rating']}/5" if mode != "country_only" and pd.notna(risk_row["Impact Rating"]) else _zh_value(risk_row["Trend"]))
        c4.metric("数据置信度", _zh_value(risk_row["Confidence"]))
        if risk_result is not None and mode != "country_only":
            st.write(f"基准风险等级为 **{_zh_value(risk_result.baseline_risk_rating)}**，最终综合风险等级为 **{_zh_value(risk_result.final_risk_rating)}**。")
            if risk_result.override_triggered:
                st.warning(f"已触发特殊调整规则：{risk_result.override_reason or '达到模型预设的特殊调整条件'}")

        st.markdown("#### 2. 为什么得到这个发生可能性")
        if likelihood_result is not None and rule is not None:
            st.write("模型综合当前风险水平、变化趋势和近期事件信号形成发生可能性评分。")
            s1, s2, s3 = st.columns(3)
            s1.metric("当前风险水平", likelihood_result.level_subscore if likelihood_result.level_subscore is not None else "缺失")
            s2.metric("变化趋势", likelihood_result.trend_subscore if likelihood_result.trend_subscore is not None else "缺失")
            s3.metric("近期事件", likelihood_result.event_subscore if likelihood_result.event_subscore is not None else "缺失")
            contributor_rows = []
            for signal, signal_type, label in [
                (rule.level_indicator, "Level", "当前风险水平"),
                (rule.trend_indicator, "Trend", "变化趋势"),
                (rule.event_indicator, "Event", "近期事件"),
            ]:
                if not signal: continue
                raw_value = st.session_state.country_data.get(selected_risk, {}).get(signal)
                score_result = _score_indicator_for_rule(selected_risk, signal, signal_type, raw_value, rule)
                weight = getattr(rule, f"{signal_type.lower()}_weight")
                contributor_rows.append({
                    "判断维度": label, "使用指标": signal, "原始数据": raw_value,
                    "评分": score_result.standardized_score if score_result else None,
                    "权重": f"{weight:.0%}" if pd.notna(weight) else "",
                    "数据来源": st.session_state.country_meta.get(selected_risk, {}).get(signal, {}).get("source", ""),
                    "数据日期": st.session_state.country_meta.get(selected_risk, {}).get(signal, {}).get("observation_date", ""),
                })
            if contributor_rows: st.dataframe(pd.DataFrame(contributor_rows), use_container_width=True, hide_index=True)

        if mode != "country_only":
            st.markdown("#### 3. 为什么得到这个影响程度")
            if impact_result is not None:
                st.write(f"主要影响因素：**{impact_result.driver or '项目基础信息'}**")
                if impact_result.contributors:
                    impact_rows = [{"项目信息": c.metric_name, "项目填写值": c.raw_value, "影响程度评分": c.score, "评分说明": c.rationale} for c in impact_result.contributors]
                    st.dataframe(pd.DataFrame(impact_rows), use_container_width=True, hide_index=True)
                else:
                    st.info("当前缺少用于计算该风险影响程度的项目数据，因此影响程度仍待评估。")

            st.markdown("#### 4. 最终风险如何形成")
            st.write("发生可能性 + 项目影响程度 → 风险矩阵 → 特殊调整规则 → 综合风险等级。")
            if risk_result is not None:
                st.write(f"本项风险的发生可能性为 **{risk_result.likelihood_score}/5**，影响程度为 **{risk_result.impact_score}/5**，风险矩阵得到 **{_zh_value(risk_result.baseline_risk_rating)}**，最终判断为 **{_zh_value(risk_result.final_risk_rating)}**。")

    st.divider()
    with st.expander("模型与数据说明（供进一步核查）", expanded=False):
        st.markdown("#### 数据完整度")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("必需指标", data_quality["total_required_indicators"])
        q2.metric("已获取", data_quality["available_required_indicators"])
        q3.metric("缺失", data_quality["missing_required_indicators"])
        q4.metric("完整度", f"{data_quality['data_completeness_pct']:.1f}%")
        st.caption(f"当前数据置信度：{_zh_value(_derive_confidence(data_quality))}。置信度用于说明数据基础，不代表风险高低。")
        if mode != "country_only":
            st.markdown("#### 5×5 发生可能性 × 影响程度风险矩阵")
            _render_risk_matrix(params, summary)
        st.markdown("#### 模型判定说明")
        if mode == "country_only":
            st.write("国家风险筛查模式只判断各项国别风险的发生可能性与趋势，不使用项目影响程度形成项目综合风险等级。管理层关注等级按发生可能性 1–2=低、3=中、4–5=高展示。")
        else:
            st.write("国家 + 项目风险评估模式先计算国别风险发生可能性，再结合项目影响程度，通过风险矩阵形成基准风险等级；如满足特殊调整条件，再形成最终综合风险等级。")

    st.download_button(
        label="下载完整风险评估结果（Excel）",
        data=_export_assessment_excel(summary),
        file_name="country_risk_assessment.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
