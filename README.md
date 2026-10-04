# Internship Agent

Internship Agent 是一个本地运行的实习岗位推荐 MVP。v0.2 面向单个用户，使用带招聘原文的模拟岗位打通采集、标准化、去重、过滤、证据驱动评分和 Markdown 日报生成。

## 项目结构

- `collectors/`：采集器接口与模拟数据。未来采集器继承 `BaseCollector`，返回 `list[Job]`。
- `models/`：统一的 `Job` 数据结构。
- `pipeline/`：从原文提取标签、标准化、去重、过滤与四项评分。
- `reports/`：Markdown 日报生成。
- `config/`：用户偏好示例；本地 `profile.yaml` 不提交到 Git。
- `data/`：日报输出目录。

## 安装和运行

需要 Python 3.11+。在项目根目录执行：

```bash
pip install -r requirements.txt
cp config/profile.example.yaml config/profile.yaml
python main.py
```

Windows PowerShell 可将 `cp` 换成 `Copy-Item`。从 v0.1 升级的用户需要按新示例迁移本地 `config/profile.yaml`；新结构区分首选与可接受地点、强偏好与中等偏好方向。运行后查看 `data/daily_report.md`。测试命令为 `pytest`。

## 当前规则

- 同一公司、标题、城市的岗位只保留首次出现的一条。
- 截止日期已过、明确要求其他专业、明确异地且不能远程的岗位被过滤。未注明的地点、远程方式或每周天数不会被猜测。
- 每周天数超过上限的岗位保留，但时间地点项计 0 分，并显示问题。
- 总分为资格匹配 0–30、方向匹配 0–25、时间地点 0–25、岗位内容 0–20；65 分及以上计入日报的“推荐”。未知字段得到中性分，不会被写成已确认的优势。
- 业务与任务标签只从 `raw_text` 中的明确词语提取，`evidence` 保留相应原文片段。无原文依据的传入标签会被移除。
- 单条岗位的异常链接或日期会记录到 `data_quality`，相应字段视为未知；整批处理继续。缺少岗位 ID、标题、公司或可核对的招聘原文时，跳过该条并打印 warning。

目前只使用内置模拟岗位，链接为示例地址，没有接入真实招聘网站或 AI API。关键词提取不能完整理解否定、同义词和复杂学历条件；对这些内容仍需人工核实。`background` 已保存在用户偏好中，当前没有岗位背景要求字段，因此暂不参与评分。
