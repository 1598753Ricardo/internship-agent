# Internship Agent

Internship Agent 是一个本地运行的实习岗位推荐 MVP。第一阶段面向单个用户，使用模拟岗位打通采集、标准化、去重、硬规则过滤、规则评分和 Markdown 日报生成。

## 项目结构

- `collectors/`：采集器接口与模拟数据。未来采集器继承 `BaseCollector`，返回 `list[Job]`。
- `models/`：统一的 `Job` 数据结构。
- `pipeline/`：标准化、去重、过滤与评分。
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

Windows PowerShell 可将 `cp` 换成 `Copy-Item`。修改 `config/profile.yaml` 中的专业、地点、方向、可投入天数和技能即可定制单用户偏好。运行后查看 `data/daily_report.md`。

## 当前规则

- 同一公司、标题、城市的岗位只保留首次出现的一条。
- 截止日期已过、明确要求其他专业、异地且不能按用户设置远程的岗位被过滤。
- 每周天数超过上限的岗位保留，但会扣分并显示注意事项。
- 评分范围为 0–100，考虑方向、地点、远程、时间、技能和学历；65 分及以上计入日报的“推荐”。

目前只使用内置模拟岗位，没有接入真实招聘网站或 AI API。评分和专业判断是简单规则，岗位信息仍需通过原始链接核实。
