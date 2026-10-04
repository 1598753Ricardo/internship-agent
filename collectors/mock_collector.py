"""Evidence-bearing synthetic postings for the local pipeline."""

from dataclasses import replace
from datetime import date, datetime, timedelta

from collectors.base import BaseCollector
from models.job import Job


class MockCollector(BaseCollector):
    def collect(self) -> list[Job]:
        today = date.today()
        now = datetime.now().astimezone()
        active_deadline = (today + timedelta(days=20)).isoformat()
        expired_deadline = (today - timedelta(days=1)).isoformat()

        def posting(job_id: str, raw_text: str, **fields: object) -> Job:
            return Job(
                id=job_id,
                source="mock",
                source_type="unknown",
                source_url=f"https://example.com/jobs/{job_id}#details",
                raw_text=raw_text,
                description=raw_text,
                requirements=[],
                collected_at=now,
                **fields,
            )

        foreign = posting(
            "foreign-law",
            f"南方涉外律师事务所｜涉外法律实习生。地点：东莞市；不支持远程，需现场到岗；每周2天；实习3个月；截止日期：{active_deadline}。"
            "要求：法学专业，本科及以上，大三或大四，CET-6。"
            "业务：涉外法律、跨境业务。工作：法律检索、合同审查、英文法律工作、文书起草。",
            title="涉外法律实习生", company="南方涉外律师事务所", location="东莞市", remote=False,
            education="本科及以上", required_majors=["法学"], required_grades=["大三", "大四"],
            required_skills=["CET-6"], internship_days_per_week=2, internship_duration="3个月",
            deadline=active_deadline, published_at=None, direction="涉外法律",
        )
        return [
            foreign,
            posting(
                "arbitration",
                "华南仲裁律师事务所｜国际仲裁实习生。地点：广州市；不支持远程，需现场到岗；每周3天。"
                "要求：法学专业，本科及以上，CET-6。"
                "业务：国际仲裁。工作：仲裁材料整理、英文法律工作、法律检索。",
                title="国际仲裁实习生", company="华南仲裁律师事务所", location="广州市", remote=False,
                education="本科及以上", required_majors=["法学"], required_skills=["CET-6"],
                internship_days_per_week=3, internship_duration=None, deadline=None, published_at=None,
                direction="国际仲裁",
            ),
            posting(
                "corporate-law",
                "湾区科技｜企业法务实习生。地点：深圳市；不支持远程，需现场到岗；每周2天。"
                "要求：法学专业，本科及以上，CET-4。"
                "业务：企业法务。工作：合同审查、尽职调查、文书起草。",
                title="企业法务实习生", company="湾区科技", location="深圳市", remote=False,
                education="本科及以上", required_majors=["法学"], required_skills=["CET-4"],
                internship_days_per_week=2, internship_duration=None, deadline=None, published_at=None,
                direction="企业法务",
            ),
            posting(
                "compliance",
                "南粤金融｜合规实习生。地点：广州；不支持远程，需现场到岗；每周3天。"
                "要求：法学或会计学专业，本科及以上，初级会计。"
                "业务：合规。工作：法规研究、尽职调查。",
                title="合规实习生", company="南粤金融", location="广州", remote=False,
                education="本科及以上", required_majors=["法学", "会计学"], required_skills=["初级会计"],
                internship_days_per_week=3, internship_duration=None, deadline=None, published_at=None,
                direction="合规",
            ),
            posting(
                "unknown-days",
                "岭南律师事务所｜商事诉讼实习生。地点：东莞；不支持远程，需现场到岗。"
                "要求：法学专业。业务：商事诉讼。工作：诉讼材料整理、文书起草、法律检索。",
                title="商事诉讼实习生", company="岭南律师事务所", location="东莞", remote=False,
                education=None, required_majors=["法学"], internship_days_per_week=None,
                internship_duration=None, deadline=None, published_at=None, direction="商事诉讼",
            ),
            posting(
                "remote-law",
                "北方研究院｜远程法律研究实习生。地点：北京；支持远程。"
                "要求：法学专业，CET-6。业务：涉外法律。"
                "工作：法规研究、英文法律工作、法律检索。",
                title="远程法律研究实习生", company="北方研究院", location="北京", remote=True,
                education=None, required_majors=["法学"], required_skills=["CET-6"],
                internship_days_per_week=None, internship_duration=None, deadline=None,
                published_at=None, direction="涉外法律",
            ),
            posting(
                "five-days",
                "珠江企业｜企业法务实习生。地点：广州；不支持远程，需现场到岗；每周5天。"
                "要求：法学专业，本科及以上。业务：企业法务。工作：合同审查、法律检索。",
                title="企业法务实习生", company="珠江企业", location="广州", remote=False,
                education="本科及以上", required_majors=["法学"], internship_days_per_week=5,
                internship_duration=None, deadline=None, published_at=None, direction="企业法务",
            ),
            posting(
                "wrong-city",
                "海河律师事务所｜商事诉讼实习生。地点：天津；不支持远程，需现场到岗；每周2天。"
                "要求：法学专业。业务：商事诉讼。工作：诉讼。",
                title="商事诉讼实习生", company="海河律师事务所", location="天津", remote=False,
                education=None, required_majors=["法学"], internship_days_per_week=2,
                internship_duration=None, deadline=None, published_at=None, direction="商事诉讼",
            ),
            posting(
                "expired",
                f"过期招聘公司｜法务实习生。地点：深圳；不支持远程，需现场到岗；每周2天；截止日期：{expired_deadline}。"
                "要求：法学专业。业务：企业法务。工作：合同审查。",
                title="法务实习生", company="过期招聘公司", location="深圳", remote=False,
                education=None, required_majors=["法学"], internship_days_per_week=2,
                internship_duration=None, deadline=expired_deadline, published_at=None, direction="企业法务",
            ),
            posting(
                "unrelated",
                "智算科技｜算法工程实习生。地点：广州；不支持远程，需现场到岗；每周2天。"
                "要求：计算机科学专业，Python。工作：机器学习模型训练。",
                title="算法工程实习生", company="智算科技", location="广州", remote=False,
                education=None, required_majors=["计算机科学"], required_skills=["Python"],
                internship_days_per_week=2, internship_duration=None, deadline=None, published_at=None,
            ),
            replace(foreign, id="foreign-law-copy", title=" 涉外法律实习生 ", location="东莞", source_url="https://example.com/jobs/foreign-law-copy"),
        ]
