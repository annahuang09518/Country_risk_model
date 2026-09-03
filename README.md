# 国别及项目风险评估模型

基于国别权威数据、趋势信号及事件信息，对境外投资国别风险进行快速筛查；在补充项目基础信息后，可进一步评估项目影响程度并形成综合风险等级。

## 使用模式

- **国家风险筛查**：仅选择国家，查看各三级风险的发生可能性、趋势及数据置信度。
- **国家 + 项目风险评估**：在国家风险分析基础上补充少量项目基础信息，进一步计算影响程度及综合风险等级。

## 本地运行

建议使用 Python 3.11。

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app/streamlit_app.py
```

浏览器访问：`http://localhost:8501`

## Streamlit Community Cloud 部署

1. 将本项目上传至 GitHub 仓库。
2. 在 Streamlit Community Cloud 新建应用。
3. 选择对应仓库和 `main` 分支。
4. Main file path 填写：`app/streamlit_app.py`。
5. 部署完成后即可获得可分享的网页链接。

## 项目结构

```text
app/                 Streamlit 前端与页面
risk_model/          评分及风险计算引擎
src/                 国家数据源、国家主表及趋势计算
data/                模型参数工作簿
requirements.txt     Python 依赖
runtime.txt          部署 Python 版本
```

## 数据与模型说明

- 缺失数据不会自动按 0 处理。
- 不同国家的数据源覆盖程度可能不同，系统会通过数据完整度/置信度提示使用者。
- 本模型为基于规则与指标的半定量风险评估原型，主要用于风险筛查、比较与预警，不代表统计意义上的事件发生概率。

## 分享前注意

若仓库包含内部方法论、客户信息或不希望公开的模型参数，建议使用 **Private GitHub Repository**，并结合组织认可的部署及访问控制方式使用。
