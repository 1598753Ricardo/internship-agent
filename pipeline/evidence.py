"""Extract only tags with literal support in the recruitment text."""

import re


BUSINESS_TERMS: dict[str, tuple[str, ...]] = {
    "涉外法律": ("涉外法律",),
    "国际仲裁": ("国际仲裁",),
    "跨境业务": ("跨境业务",),
    "企业法务": ("企业法务",),
    "合规": ("合规", "公司合规", "合规风控"),
    "商事诉讼": ("商事诉讼",),
    "商事争议": ("商事争议解决", "商事争议"),
    "公司业务": ("公司业务",),
    "知识产权": ("知识产权", "专利", "商标", "著作权"),
    "资本市场": ("资本市场", "IPO", "上市"),
    "并购": ("投融资并购", "投融资", "并购重组", "并购"),
    "数据合规": ("数据保护", "隐私保护", "网络安全合规"),
    "反垄断": ("反垄断", "竞争法"),
    "金融": ("银行金融", "金融监管"),
}

TASK_TERMS: dict[str, tuple[str, ...]] = {
    "法律研究": ("法律研究", "法律调研"),
    "法律检索": ("法律检索", "案例检索", "法规检索", "法律法规检索"),
    "合同审查": ("合同审查", "合同审核", "合同审阅"),
    "合同起草": ("合同起草", "合同草案"),
    "文书起草": ("文书起草", "文件起草", "法律文件起草", "起草法律文件"),
    "尽职调查": ("尽职调查",),
    "法规研究": ("法规研究", "监管政策跟踪"),
    "仲裁": ("仲裁",),
    "诉讼": ("诉讼",),
    "案件支持": ("案件材料整理",),
    "客户沟通": ("客户沟通",),
    "英文法律工作": ("英文法律工作",),
    "纯行政": ("纯行政",),
    "纯文员": ("纯文员",),
    "扫描": ("扫描",),
    "装订": ("装订",),
    "跑腿": ("跑腿",),
    "客服": ("客服",),
    "销售": ("销售",),
}


def extract_tags(raw_text: str) -> tuple[list[str], list[str], list[str]]:
    sentences = [part.strip() for part in re.split(r"(?<=[。；;！!])|\n", raw_text) if part.strip()]
    business: list[str] = []
    tasks: list[str] = []
    evidence: list[str] = []
    for rules, tags in ((BUSINESS_TERMS, business), (TASK_TERMS, tasks)):
        for tag, terms in rules.items():
            for sentence in sentences:
                if any(term.casefold() in sentence.casefold() for term in terms):
                    tags.append(tag)
                    if sentence not in evidence:
                        evidence.append(sentence)
                    break
    return business, tasks, evidence
