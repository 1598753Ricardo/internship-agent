from datetime import date, datetime, timedelta

from collectors.base import BaseCollector
from models.job import Job


class MockCollector(BaseCollector):
    def collect(self) -> list[Job]:
        today = date.today()
        now = datetime.now().astimezone()

        def job(
            job_id: str,
            title: str,
            company: str,
            location: str,
            direction: str,
            *,
            remote: bool = False,
            days: int | None = 3,
            deadline_offset: int = 20,
            required_majors: list[str] | None = None,
            required_skills: list[str] | None = None,
            education: str = "本科及以上",
            description: str = "协助团队开展日常实习工作。",
        ) -> Job:
            return Job(
                id=job_id,
                title=title,
                company=company,
                location=location,
                remote=remote,
                source="mock",
                source_url=f"https://example.com/jobs/{job_id}#details",
                description=description,
                requirements=["法学相关专业优先"] if required_majors is None else ["相关专业要求见岗位信息"],
                education=education,
                internship_days_per_week=days,
                internship_duration="3个月",
                deadline=today + timedelta(days=deadline_offset),
                published_at=today - timedelta(days=2),
                collected_at=now,
                direction=direction,
                required_majors=required_majors or [],
                required_skills=required_skills or [],
            )

        return [
            job("foreign-law", "涉外法律实习生", "南方涉外律师事务所", " 广州市 ", "涉外法律", remote=True, required_majors=["法学"], required_skills=["CET-6"], description="协助跨境合同审查和英文法律检索。"),
            job("law-firm", "律师助理实习生", "岭南律师事务所", "东莞市", "律师事务所", required_majors=["法学"], required_skills=["CET-4", "法律检索"], description="协助诉讼材料整理和法律检索。"),
            job("corporate-law", "企业法务实习生", "湾区科技", "深圳", "企业法务", required_majors=["法学"], required_skills=["CET-4"], description="协助合同审核和公司治理事务。"),
            job("compliance", "合规实习生", "南粤金融", "广州", "合规", required_majors=["法学", "会计学"], required_skills=["初级会计"], description="协助内控和合规资料整理。"),
            job("remote-law", "远程法律研究实习生", "北方研究院", "北京", "涉外法律", remote=True, required_majors=["法学"], required_skills=["CET-6"], description="远程参与英文法规和案例研究。"),
            job("five-days", "律所实习生", "珠江律师事务所", "广州", "律师事务所", days=5, required_majors=["法学"], description="每周需到岗五天，协助团队办理案件。"),
            job("wrong-city", "法律实习生", "海河律师事务所", "天津", "律师事务所", required_majors=["法学"]),
            job("expired", "法务实习生", "过期招聘公司", "深圳", "企业法务", deadline_offset=-1, required_majors=["法学"]),
            job("unrelated", "算法工程实习生", "智算科技", "广州", "人工智能", required_majors=["计算机科学"], required_skills=["Python"], description="训练和部署机器学习模型。"),
            job("foreign-law-copy", " 涉外法律实习生 ", "南方涉外律师事务所", "广州", "涉外法律", required_majors=["法学"], required_skills=["CET-6"]),
        ]
