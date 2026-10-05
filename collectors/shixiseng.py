"""Low-rate collection of public Shixiseng search and detail pages."""

import itertools
import json
import random
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from collectors.base import BaseCollector
from models.job import Job


BASE_URL = "https://www.shixiseng.com"
SEARCH_URL = f"{BASE_URL}/interns"
DETAIL_PATH = re.compile(r"^/intern/(inn_[a-zA-Z0-9]+)$")
USER_AGENT = "InternshipAgent/0.4 (+https://github.com/1598753Ricardo/internship-agent)"
KEYWORDS = ("法务", "律师", "合规")
CITIES = ("东莞", "广州", "深圳")
EDUCATION = {"本科", "本科及以上", "硕士", "硕士及以上", "不限"}
OFFLINE_MARKERS = ("当前职位已下线", "该职位已下线", "职位已下线")
APPLY_MARKERS = ("投个简历", "立即投递", "投递简历", "申请职位")
DEADLINE_PATTERN = re.compile(r"截止日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})(?!\d)")


class AccessRestricted(Exception):
    """The public HTTP flow was refused or challenged; do not retry it."""


def canonical_detail_url(href: str) -> tuple[str, str] | None:
    parts = urlsplit(urljoin(BASE_URL, href))
    if parts.scheme != "https" or (parts.hostname or "").lower() not in {"www.shixiseng.com", "shixiseng.com"}:
        return None
    match = DETAIL_PATH.fullmatch(parts.path.rstrip("/"))
    if not match:
        return None
    source_job_id = match.group(1)
    return f"{BASE_URL}/intern/{source_job_id}", source_job_id


def discover_detail_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select('a[href*="/intern/inn_"]'):
        result = canonical_detail_url(anchor.get("href", ""))
        if result and result[0] not in seen:
            seen.add(result[0])
            urls.append(result[0])
    return urls


def has_next_page(html: str) -> bool:
    button = BeautifulSoup(html, "html.parser").select_one(".el-pagination .btn-next")
    return bool(button and not button.has_attr("disabled"))


def _lines(element) -> list[str]:
    return [line for text in element.stripped_strings if (line := " ".join(text.split()))]


def _requirement_lines(lines: list[str]) -> list[str]:
    headings = ("任职要求", "岗位要求", "任职资格", "职位要求")
    start = next((i for i, line in enumerate(lines) if any(line.startswith(head) for head in headings)), None)
    return lines[start + 1:] if start is not None else []


def _explicit_major_requirements(lines: list[str]) -> list[str]:
    majors: list[str] = []
    for line in lines:
        if "优先" in line or "不限" in line:
            continue
        for major in re.findall(r"(?<!非)(法学|会计学|计算机科学)专业", line):
            if major not in majors:
                majors.append(major)
    return majors


def _explicit_grade_requirements(lines: list[str]) -> list[str]:
    grades: list[str] = []
    for line in lines:
        if any(word in line for word in ("优先", "以上", "不限", "非")):
            continue
        for grade in re.findall(r"大[一二三四]|研[一二三]", line):
            if grade not in grades:
                grades.append(grade)
    return grades


def _explicit_skills(lines: list[str]) -> list[str]:
    skills: list[str] = []
    for line in lines:
        if "优先" in line:
            continue
        for skill in re.findall(r"CET-[46]|初级会计", line, flags=re.IGNORECASE):
            skill = skill.upper() if skill.lower().startswith("cet") else skill
            if skill not in skills:
                skills.append(skill)
    return skills


def _deadline_from_text(text: str) -> date | None:
    for match in DEADLINE_PATTERN.finditer(text):
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            continue
    return None


def parse_detail(html: str, url: str) -> Job:
    result = canonical_detail_url(url)
    if result is None:
        raise ValueError("invalid Shixiseng detail URL")
    source_url, source_job_id = result
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one(".job-header .new_job_name")
    company_node = soup.select_one(".com_intro .com-name")
    body_node = soup.select_one(".con-job .job_detail")
    visible_status = soup.get_text(" ", strip=True)
    offline = next((marker for marker in OFFLINE_MARKERS if marker in visible_status), "")
    if not title_node or not company_node or (not body_node and not offline):
        raise ValueError("missing title, company, or job detail container")

    title = title_node.get_text(" ", strip=True)
    company = company_node.get_text(" ", strip=True)
    body_lines = _lines(body_node) if body_node else []
    if not title or not company or (not body_lines and not offline):
        raise ValueError("empty title, company, or job description")
    requirements = _requirement_lines(body_lines)
    body_text = "\n".join(body_lines)

    def header_text(selector: str) -> str:
        node = soup.select_one(f".job-header .job_msg {selector}")
        return node.get_text(" ", strip=True) if node else ""

    location = header_text(".job_position")
    academic = header_text(".job_academic")
    education = academic if academic in EDUCATION else None
    if education is None:
        for line in requirements:
            match = re.fullmatch(r"学历要求[:：]\s*(本科|本科及以上|硕士|硕士及以上|不限)[。\s]*", line)
            if match:
                education = match.group(1)
                break

    week_text = header_text(".job_week")
    week_match = re.search(r"(?<!\d)([1-7])\s*天\s*[／/]\s*周", week_text)
    if week_match is None:
        week_match = re.search(r"每周\D{0,5}([1-7])\s*天", body_text)
    days = int(week_match.group(1)) if week_match else None

    duration_text = header_text(".job_time")
    duration_match = re.search(r"实习\s*(\d+\s*个?月(?:或以上|以上)?)", duration_text)
    if duration_match is None:
        duration_match = re.search(r"实习\s*(\d+\s*个?月(?:或以上|以上)?)", body_text)
    duration = duration_match.group(1).replace(" ", "") if duration_match else None

    application = ""
    deadline = None
    for heading in soup.select(".job_til"):
        if "投递要求" in heading.get_text(" ", strip=True):
            section = heading.find_parent(class_="con-job")
            if section:
                application = section.get_text(" ", strip=True)
                deadline = _deadline_from_text(application)
                break
    if deadline is None:
        for container in soup.select(".content_left, .job-header"):
            deadline = _deadline_from_text(container.get_text(" ", strip=True))
            if deadline is not None:
                break
    if deadline is not None and deadline.isoformat() not in application:
        application = "\n".join(part for part in (application, f"截止日期：{deadline.isoformat()}") if part)

    refreshed_text = ""
    refresh_node = soup.select_one(".job-header .job_date")
    if refresh_node:
        candidate = refresh_node.get_text(" ", strip=True)
        if "刷新" in candidate:
            refresh_match = re.search(r"\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?", candidate)
            if refresh_match:
                refreshed_text = refresh_match.group(0)

    address_node = soup.select_one(".job_city .com_position")
    address = address_node.get_text(" ", strip=True) if address_node else ""
    action_node = soup.select_one(".job-header .top_deliver_btn")
    action = action_node.get_text(" ", strip=True) if action_node else ""
    is_active = False if offline else True if any(marker in action for marker in APPLY_MARKERS) else None

    relevant_text = "\n".join(part for part in (
        title, company, location, academic, week_text, duration_text,
        f"{refreshed_text} 刷新" if refreshed_text else "",
        "职位描述：", *body_lines, application,
        f"工作地点：{address}" if address else "", offline, action if is_active is True else "",
    ) if part)
    remote_denied = any(mark in relevant_text for mark in ("不支持远程", "不可远程", "无法远程"))
    remote_supported = bool(re.search(r"(?<!不)支持远程|(?<!不)可远程|远程办公|远程实习", relevant_text))
    remote = False if remote_denied else True if remote_supported else None

    return Job(
        id=f"shixiseng:{source_job_id}", source_job_id=source_job_id,
        title=title, company=company, location=location, remote=remote,
        source="shixiseng", source_type="job_platform", source_url=source_url,
        description=body_text, requirements=requirements, education=education,
        required_majors=_explicit_major_requirements(requirements),
        required_grades=_explicit_grade_requirements(requirements),
        required_skills=_explicit_skills(requirements),
        internship_days_per_week=days, internship_duration=duration,
        deadline=deadline, published_at=None, collected_at=datetime.now().astimezone(),
        refreshed_at=refreshed_text or None,
        raw_text=relevant_text, is_active=is_active,
    )


class ShixisengCollector(BaseCollector):
    def __init__(self, max_jobs: int = 30, pages: int = 1, http=None, cache_dir: Path | None = None):
        if max_jobs < 1 or pages not in (1, 2):
            raise ValueError("max_jobs must be positive and pages must be 1 or 2")
        self.max_jobs = max_jobs
        self.pages = pages
        self.http = http or requests
        self.cache_dir = cache_dir
        self.stats = {"discovered": 0, "fetched": 0, "parsed": 0, "failed": 0, "cache_hits": 0}
        self.blocked_reason: str | None = None
        self._last_request_at: float | None = None

    def _request(self, url: str, params: dict | None = None) -> str:
        if self._last_request_at is not None:
            wait = 1.0 + random.uniform(0, 0.3) - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at = time.monotonic()
        response = self.http.get(
            url, params=params, headers={"User-Agent": USER_AGENT},
            timeout=20, allow_redirects=False,
        )
        if response.status_code in {403, 429}:
            raise AccessRestricted(f"HTTP {response.status_code} at {url}")
        if 300 <= response.status_code < 400:
            raise AccessRestricted(f"HTTP redirect {response.status_code} at {url}")
        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code}")
        html = response.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if any(term in page_title for term in ("验证码", "安全验证", "访问限制", "访问受限")):
            raise AccessRestricted(f"verification page at {url}")
        visible = soup.get_text(" ", strip=True)
        if len(visible) < 1500 and any(term in visible for term in ("验证码", "安全验证", "访问限制")):
            raise AccessRestricted(f"verification page at {url}")
        return html

    def _cached_html(self, source_job_id: str) -> str | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{source_job_id}.json"
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            checked = datetime.fromisoformat(cached["last_checked"])
            if checked.tzinfo is not None and datetime.now(timezone.utc) - checked < timedelta(hours=24):
                return cached["html"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def _save_cache(self, source_job_id: str, html: str) -> None:
        if self.cache_dir is None:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self.cache_dir / f"{source_job_id}.json"
            path.write_text(json.dumps({"last_checked": datetime.now(timezone.utc).isoformat(), "html": html}, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            print(f"[warning] shixiseng cache write failed: {source_job_id}: {exc}", file=sys.stderr)

    def collect(self) -> list[Job]:
        self.stats = {"discovered": 0, "fetched": 0, "parsed": 0, "failed": 0, "cache_hits": 0}
        self.blocked_reason = None
        buckets: list[list[str]] = []
        for keyword in KEYWORDS:
            for city in CITIES:
                found: list[str] = []
                for page in range(1, self.pages + 1):
                    params = {"keyword": keyword, "city": city, "type": "intern"}
                    if page > 1:
                        params["page"] = page
                    try:
                        html = self._request(SEARCH_URL, params)
                        found.extend(discover_detail_urls(html))
                    except AccessRestricted as exc:
                        self.blocked_reason = str(exc)
                        print(f"[warning] shixiseng access restricted: {exc}", file=sys.stderr)
                        self._print_stats()
                        return []
                    except (requests.RequestException, ValueError) as exc:
                        print(f"[warning] shixiseng search failed: {keyword}/{city}/page {page}: {exc}", file=sys.stderr)
                        break
                    if not has_next_page(html):
                        break
                buckets.append(found)

        discovered: list[str] = []
        seen: set[str] = set()
        for row in itertools.zip_longest(*buckets):
            for url in row:
                if url and url not in seen:
                    seen.add(url)
                    discovered.append(url)
        self.stats["discovered"] = len(discovered)

        jobs: list[Job] = []
        for url in discovered[:self.max_jobs]:
            self.stats["fetched"] += 1
            try:
                source_job_id = canonical_detail_url(url)[1]
                html = self._cached_html(source_job_id)
                if html is not None:
                    try:
                        job = parse_detail(html, url)
                    except ValueError:
                        html = None
                    else:
                        self.stats["cache_hits"] += 1
                if html is None:
                    html = self._request(url)
                    job = parse_detail(html, url)
                    self._save_cache(source_job_id, html)
            except AccessRestricted as exc:
                self.stats["failed"] += 1
                self.blocked_reason = str(exc)
                print(f"[warning] shixiseng access restricted: {exc}", file=sys.stderr)
                break
            except (requests.RequestException, ValueError) as exc:
                self.stats["failed"] += 1
                print(f"[warning] shixiseng parse failed: {url} + {exc}", file=sys.stderr)
                continue
            jobs.append(job)
            self.stats["parsed"] += 1
        self._print_stats()
        return jobs

    def _print_stats(self) -> None:
        for key, value in self.stats.items():
            print(f"[shixiseng] {key}: {value}")
