"""Extract only tags with literal support in the recruitment text."""

import re


BUSINESS_TERMS: dict[str, tuple[str, ...]] = {
    "涉外法律": ("涉外法律",),
    "国际仲裁": ("国际仲裁",),
    "跨境业务": ("跨境业务",),
    "企业法务": ("企业法务",),
    "合规": ("合规",),
    "商事诉讼": ("商事诉讼",),
    "公司业务": ("公司业务",),
    "知识产权": ("知识产权",),
    "资本市场": ("资本市场",),
    "并购": ("并购",),
}

TASK_TERMS: dict[str, tuple[str, ...]] = {
    "法律检索": ("法律检索",),
    "合同审查": ("合同审查", "合同审核"),
    "文书起草": ("文书起草",),
    "尽职调查": ("尽职调查",),
    "法规研究": ("法规研究",),
    "仲裁": ("仲裁",),
    "诉讼": ("诉讼",),
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
                if any(term in sentence for term in terms):
                    tags.append(tag)
                    if sentence not in evidence:
                        evidence.append(sentence)
                    break
    return business, tasks, evidence
