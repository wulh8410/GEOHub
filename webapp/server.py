from __future__ import annotations

import html
import json
import os
import socket
import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from flask import Flask, jsonify, request, send_file

from geo_seo_hub.diagnose import _default_fetch, _validate_public_url
from geo_seo_hub.site_diagnose import site_diagnose


APP_ROOT = Path(__file__).resolve().parent
RUNS_ROOT = Path(os.environ.get("GEO_CHECK_RUNS", str(APP_ROOT.parent / "runs"))).resolve()
JOBS_ROOT = RUNS_ROOT / "web-jobs"
JOBS_ROOT.mkdir(parents=True, exist_ok=True)
app = Flask(__name__, static_folder="static", static_url_path="")
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.metas: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.headings: Counter[str] = Counter()
        self.html_lang = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        if tag == "html":
            self.html_lang = values.get("lang", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = values.get("name", values.get("property", "")).lower()
            if key:
                self.metas[key] = values.get("content", "").strip()
        elif tag == "link" and values.get("rel", "").lower() == "canonical":
            self.metas["canonical"] = values.get("href", "")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.headings[tag] += 1
        elif tag == "img":
            self.images.append(values)
        elif tag == "a" and values.get("href"):
            self.links.append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data.strip())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_job(job: dict) -> None:
    job_dir = JOBS_ROOT / job["id"]
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def public_url(url: str) -> str:
    return _validate_public_url(url, resolver=socket.getaddrinfo)[0]


def fetch_text(url: str) -> tuple[str, str]:
    normalized, addresses = _validate_public_url(url, resolver=socket.getaddrinfo)
    result = _default_fetch(
        normalized,
        resolver=socket.getaddrinfo,
        initial_addresses=addresses,
        user_agent="GEOCheckSEOAudit/1.0 (+bounded-public-site-audit)",
    )
    return result.body.decode("utf-8", errors="replace"), result.final_url


def seo_quick_audit(url: str, job_dir: Path) -> dict:
    normalized = public_url(url)
    page_html, final_url = fetch_text(normalized)
    parser = PageParser()
    parser.feed(page_html)
    parser.close()
    host = urlsplit(final_url).hostname or ""
    title = " ".join(part for part in parser.title_parts if part).strip()
    description = parser.metas.get("description", "")
    robots_text = ""
    robots_status = "未找到"
    try:
        robots_text, _ = fetch_text(urljoin(final_url, "/robots.txt"))
        robots_status = "已发现" if robots_text else "为空"
    except Exception:
        pass
    sitemap_status = "未声明"
    for line in robots_text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_status = "已在 robots.txt 声明"
            break
    internal = 0
    external = 0
    nofollow = 0
    for link in parser.links:
        target = urljoin(final_url, link["href"])
        target_host = urlsplit(target).hostname
        if target_host and target_host != host:
            external += 1
        else:
            internal += 1
        if "nofollow" in link.get("rel", "").lower():
            nofollow += 1
    with_alt = sum(1 for image in parser.images if image.get("alt", "").strip())
    checks = [
        ("标题", bool(title), "页面需要唯一且清晰的 title。"),
        ("标题长度", 20 <= len(title) <= 60, "建议标题长度控制在 20–60 个字符。"),
        ("Meta 描述", bool(description), "补充能概括页面价值的 Meta description。"),
        ("描述长度", 70 <= len(description) <= 170, "建议描述长度控制在 70–170 个字符。"),
        ("H1 标题", parser.headings["h1"] == 1, "每页建议保留一个清晰的 H1。"),
        ("Canonical", bool(parser.metas.get("canonical")), "声明 canonical，减少重复内容歧义。"),
        ("页面语言", bool(parser.html_lang), "为 html 标签补充 lang 属性。"),
        ("图片替代文本", not parser.images or with_alt == len(parser.images), "为缺少 alt 的图片添加替代文本。"),
        ("robots.txt", robots_status == "已发现", "检查 robots.txt 是否可访问。"),
        ("Sitemap", sitemap_status == "已在 robots.txt 声明", "在 robots.txt 中声明 XML Sitemap。"),
    ]
    score = round(sum(10 for _label, passed, _help in checks if passed))
    findings = [
        {"label": label, "status": "通过" if passed else "待优化", "recommendation": help}
        for label, passed, help in checks
    ]
    audit = {
        "engine": "页面 SEO 快检",
        "url": final_url,
        "created_at": now_iso(),
        "score": score,
        "title": title or "未检测到 title",
        "description": description or "未检测到 Meta description",
        "headings": dict(parser.headings),
        "images": {"total": len(parser.images), "with_alt": with_alt, "missing_alt": len(parser.images) - with_alt},
        "links": {"internal": internal, "external": external, "nofollow": nofollow},
        "robots": robots_status,
        "sitemap": sitemap_status,
        "findings": findings,
        "limitations": "此快检仅基于本次公开页面与 robots.txt 快照，不包含第三方流量、排名或 WHOIS 数据。",
    }
    report_path = job_dir / "seo-quick-report.html"
    report_path.write_text(render_seo_report(audit), encoding="utf-8")
    (job_dir / "seo-quick-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"score": score, "report": str(report_path), "summary": audit}


def render_seo_report(audit: dict) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(item['label'])}</td><td class='{ 'pass' if item['status'] == '通过' else 'warn' }'>{html.escape(item['status'])}</td><td>{html.escape(item['recommendation'])}</td></tr>"
        for item in audit["findings"]
    )
    h = audit["headings"]
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>页面 SEO 快检报告</title><style>body{{margin:0;background:#101813;color:#eaf2ea;font:16px system-ui,-apple-system,'Microsoft YaHei',sans-serif}}main{{max-width:1050px;margin:auto;padding:48px 28px}}.eyebrow{{color:#a3ff57;letter-spacing:.12em;font-size:12px}}h1{{font-size:42px;margin:12px 0}}.muted{{color:#a7b4a8}}.score{{font-size:72px;font-weight:800;color:#a3ff57}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:32px 0}}.panel{{background:#152119;border:1px solid #2a3a2c;border-radius:18px;padding:22px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:14px;border-bottom:1px solid #2a3a2c;text-align:left}}.pass{{color:#a3ff57}}.warn{{color:#ffd166}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}h1{{font-size:32px}}}}</style></head><body><main><div class='eyebrow'>GEO CHECK · 页面 SEO 快检</div><h1>可直接执行的页面基础审计</h1><p class='muted'>{html.escape(audit['url'])}</p><section class='grid'><div class='panel'><div class='muted'>基础健康分</div><div class='score'>{audit['score']}</div><div>基于 10 项可观察页面信号</div></div><div class='panel'><h2>页面摘要</h2><p><b>Title：</b>{html.escape(audit['title'])}</p><p><b>Meta 描述：</b>{html.escape(audit['description'])}</p><p><b>robots：</b>{html.escape(audit['robots'])}　<b>Sitemap：</b>{html.escape(audit['sitemap'])}</p></div></section><section class='panel'><h2>结构与资源</h2><p>H1：{h.get('h1',0)}　H2：{h.get('h2',0)}　H3：{h.get('h3',0)}</p><p>图片：{audit['images']['total']}，含 alt：{audit['images']['with_alt']}，缺 alt：{audit['images']['missing_alt']}</p><p>链接：内链 {audit['links']['internal']}，外链 {audit['links']['external']}，nofollow {audit['links']['nofollow']}</p></section><section class='panel'><h2>逐项结果</h2><table><thead><tr><th>检查项</th><th>状态</th><th>建议</th></tr></thead><tbody>{rows}</tbody></table></section><p class='muted'>{html.escape(audit['limitations'])}</p></main></body></html>"""


def run_job(job_id: str) -> None:
    with jobs_lock:
        job = jobs[job_id]
        job["status"] = "running"
        job["started_at"] = now_iso()
        write_job(job)
    job_dir = JOBS_ROOT / job_id
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            geo_future = pool.submit(site_diagnose, job["url"], RUNS_ROOT, locale="zh-CN", max_pages=10, render_mode="http")
            seo_future = pool.submit(seo_quick_audit, job["url"], job_dir)
            geo_result = geo_future.result()
            seo_result = seo_future.result()
        with jobs_lock:
            job.update({
                "status": "completed",
                "completed_at": now_iso(),
                "geo": {"score": geo_result.get("overall_score"), "report": geo_result["report"], "pages": geo_result.get("representative_pages")},
                "seo": {"score": seo_result["score"], "report": seo_result["report"]},
            })
            write_job(job)
    except Exception as exc:
        with jobs_lock:
            job.update({"status": "failed", "completed_at": now_iso(), "error": str(exc)})
            write_job(job)


def public_job(job: dict) -> dict:
    data = {key: value for key, value in job.items() if key not in {"error"}}
    if job.get("status") == "failed":
        data["error"] = job.get("error", "诊断失败")
    return data


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/jobs")
def list_jobs():
    with jobs_lock:
        records = sorted((public_job(job) for job in jobs.values()), key=lambda item: item.get("created_at", ""), reverse=True)
    return jsonify(records)


@app.post("/api/jobs")
def create_job():
    payload = request.get_json(silent=True) or {}
    try:
        url = public_url(str(payload.get("url", "")))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "url": url, "status": "queued", "created_at": now_iso()}
    with jobs_lock:
        jobs[job_id] = job
        write_job(job)
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return jsonify(public_job(job)), 202


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "未找到该诊断任务"}), 404
    return jsonify(public_job(job))


@app.get("/api/jobs/<job_id>/reports/<engine>")
def get_report(job_id: str, engine: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get("status") != "completed" or engine not in {"geo", "seo"}:
        return jsonify({"error": "报告尚不可用"}), 404
    path = Path(job[engine]["report"]).resolve()
    allowed = RUNS_ROOT.resolve()
    if allowed not in path.parents or not path.is_file():
        return jsonify({"error": "报告文件不可用"}), 404
    return send_file(path, mimetype="text/html")


@app.get("/api/jobs/<job_id>/downloads/<engine>")
def download_report(job_id: str, engine: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get("status") != "completed" or engine not in {"geo", "seo"}:
        return jsonify({"error": "报告尚不可用"}), 404
    path = Path(job[engine]["report"]).resolve()
    allowed = RUNS_ROOT.resolve()
    if allowed not in path.parents or not path.is_file():
        return jsonify({"error": "报告文件不可用"}), 404
    label = "geohub" if engine == "geo" else "seo-quick"
    return send_file(
        path,
        mimetype="text/html",
        as_attachment=True,
        download_name=f"geo-check-{label}-{job_id}.html",
    )


def load_history() -> None:
    for record in JOBS_ROOT.glob("*/job.json"):
        try:
            job = json.loads(record.read_text(encoding="utf-8"))
            if job.get("id"):
                jobs[job["id"]] = job
        except (OSError, ValueError, TypeError):
            continue


load_history()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8787")), threaded=True)
