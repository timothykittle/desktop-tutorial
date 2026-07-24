"""Report generation: HTML report, JSON data, CSV issue list, and a
plain-text audit log - all saved into a timestamped folder per audit."""

import csv
import html
import json
import os
from datetime import datetime
from urllib.parse import urlparse

from .issues import CRITICAL, WARNING, NOTICE, PASSED

SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, NOTICE: 2, PASSED: 3}
SEVERITY_COLOR = {CRITICAL: "#d93025", WARNING: "#ea8600",
                  NOTICE: "#1a73e8", PASSED: "#188038"}


def _score_color(score):
    return "#188038" if score >= 80 else "#ea8600" if score >= 50 else "#d93025"


def make_output_dir(base_dir: str, url: str) -> str:
    domain = urlparse(url if "//" in url else f"https://{url}").netloc or "site"
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(base_dir, f"{domain.replace(':', '_')}_{stamp}")
    os.makedirs(out, exist_ok=True)
    return out


def save_reports(output_dir: str, url: str, sections: list, log_lines: list,
                 meta: dict = None) -> dict:
    """sections: list of SectionResult. Returns {format: path}."""
    meta = meta or {}
    paths = {}

    # ---- audit log ----
    log_path = os.path.join(output_dir, "audit_log.txt")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(f"SEO Audit Pro - audit log\nSite: {url}\n"
                 f"Date: {datetime.now().isoformat(timespec='seconds')}\n"
                 + "=" * 60 + "\n")
        fh.write("\n".join(log_lines))
    paths["log"] = log_path

    # ---- JSON ----
    json_path = os.path.join(output_dir, "report.json")
    payload = {
        "site": url,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "meta": meta,
        "overall_score": round(sum(s.score for s in sections) / max(len(sections), 1)),
        "sections": [
            {
                "name": s.name,
                "score": s.score,
                "counts": s.counts(),
                "issues": [i.as_dict() for i in s.issues],
                "data": s.data,
            }
            for s in sections
        ],
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    paths["json"] = json_path

    # ---- CSV issues ----
    csv_path = os.path.join(output_dir, "issues.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Section", "Severity", "Category", "Issue", "URL",
                         "How to fix"])
        for s in sections:
            for i in sorted(s.issues, key=lambda x: SEVERITY_ORDER.get(x.severity, 9)):
                if i.severity == PASSED:
                    continue
                writer.writerow([s.name, i.severity, i.category, i.message,
                                 i.url, i.fix])
    paths["csv"] = csv_path

    # ---- HTML ----
    html_path = os.path.join(output_dir, "report.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(url, sections, payload["overall_score"], meta))
    paths["html"] = html_path
    return paths


def render_html(url: str, sections: list, overall: int, meta: dict) -> str:
    e = html.escape
    parts = [f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO Audit - {e(url)}</title>
<style>
 body{{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#f6f8fa;color:#202124}}
 .wrap{{max-width:1100px;margin:0 auto;padding:24px}}
 header{{background:#0b2545;color:#fff;padding:28px 24px;border-radius:0 0 12px 12px}}
 h1{{margin:0 0 4px;font-size:26px}} h2{{margin-top:36px}}
 .sub{{opacity:.8;font-size:14px}}
 .scores{{display:flex;gap:16px;flex-wrap:wrap;margin-top:20px}}
 .card{{background:#fff;border-radius:10px;padding:18px 22px;box-shadow:0 1px 4px rgba(0,0,0,.08);min-width:150px}}
 .card .num{{font-size:34px;font-weight:700}}
 .card .lbl{{font-size:13px;color:#5f6368}}
 table{{border-collapse:collapse;width:100%;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-top:10px}}
 th,td{{padding:10px 12px;text-align:left;font-size:14px;border-bottom:1px solid #eee;vertical-align:top}}
 th{{background:#f1f3f4;font-size:12px;text-transform:uppercase;letter-spacing:.4px}}
 .sev{{font-weight:700;white-space:nowrap}}
 .fix{{color:#3c4043;font-size:13px}}
 .url{{color:#1a73e8;font-size:12px;word-break:break-all}}
 details{{margin-top:8px}} summary{{cursor:pointer;font-weight:600;padding:6px 0}}
 .passed-table td{{color:#188038}}
 footer{{margin:40px 0 20px;font-size:12px;color:#5f6368;text-align:center}}
</style></head><body>
<header><div class="wrap">
<h1>SEO Audit Report</h1>
<div class="sub">{e(url)} &middot; {datetime.now().strftime('%B %d, %Y %H:%M')}</div>
<div class="scores">
<div class="card"><div class="num" style="color:{_score_color(overall)}">{overall}</div>
<div class="lbl">Overall score / 100</div></div>"""]
    for s in sections:
        parts.append(
            f'<div class="card"><div class="num" style="color:{_score_color(s.score)}">'
            f'{s.score}</div><div class="lbl">{e(s.name)}</div></div>')
    parts.append("</div></div></header><div class='wrap'>")

    # Executive summary of critical items
    criticals = [(s.name, i) for s in sections for i in s.issues
                 if i.severity == CRITICAL]
    if criticals:
        parts.append("<h2>Fix these first</h2><table><tr><th>Section</th>"
                     "<th>Issue</th><th>How to fix</th></tr>")
        for section_name, i in criticals:
            parts.append(
                f"<tr><td>{e(section_name)}</td>"
                f"<td>{e(i.message)}"
                + (f"<div class='url'>{e(i.url)}</div>" if i.url else "")
                + f"</td><td class='fix'>{e(i.fix)}</td></tr>")
        parts.append("</table>")

    for s in sections:
        counts = s.counts()
        parts.append(f"<h2>{e(s.name)} &mdash; {s.score}/100</h2>"
                     f"<div class='sub'>{counts[CRITICAL]} critical &middot; "
                     f"{counts[WARNING]} warnings &middot; {counts[NOTICE]} notices "
                     f"&middot; {counts[PASSED]} passed</div>")
        active = sorted((i for i in s.issues if i.severity != PASSED),
                        key=lambda x: SEVERITY_ORDER.get(x.severity, 9))
        if active:
            parts.append("<table><tr><th>Severity</th><th>Category</th>"
                         "<th>Issue</th><th>How to fix</th></tr>")
            for i in active:
                parts.append(
                    f"<tr><td class='sev' style='color:{SEVERITY_COLOR[i.severity]}'>"
                    f"{i.severity}</td><td>{e(i.category)}</td>"
                    f"<td>{e(i.message)}"
                    + (f"<div class='url'>{e(i.url)}</div>" if i.url else "")
                    + f"</td><td class='fix'>{e(i.fix)}</td></tr>")
            parts.append("</table>")
        passed = [i for i in s.issues if i.severity == PASSED]
        if passed:
            parts.append(f"<details><summary>{len(passed)} passed checks</summary>"
                         "<table class='passed-table'>")
            for i in passed:
                parts.append(f"<tr><td>{e(i.category)}</td><td>{e(i.message)}"
                             + (f"<div class='url'>{e(i.url)}</div>" if i.url else "")
                             + "</td></tr>")
            parts.append("</table></details>")

        # Off-page extras
        if "action_plan" in s.data:
            parts.append("<details open><summary>Off-page action plan</summary><ul>")
            for step in s.data["action_plan"]:
                parts.append(f"<li>{e(step)}</li>")
            parts.append("</ul></details>")
        if "research_links" in s.data:
            parts.append("<details><summary>Research links</summary><ul>")
            for name, link in s.data["research_links"].items():
                parts.append(f"<li><a href='{e(link)}' target='_blank'>{e(name)}</a></li>")
            parts.append("</ul></details>")
        if "keyword_coverage" in s.data:
            parts.append("<details open><summary>Keyword coverage</summary>"
                         "<table><tr><th>Keyword</th><th>In titles</th>"
                         "<th>In H1s</th><th>Pages mentioning it</th>"
                         "<th>Primary page (first title match)</th></tr>")
            for kw, cov in s.data["keyword_coverage"].items():
                title_pages = cov["pages_with_keyword_in_title"]
                primary = title_pages[0] if title_pages else "-"
                parts.append(
                    f"<tr><td><b>{e(kw)}</b></td>"
                    f"<td>{len(title_pages)}</td>"
                    f"<td>{len(cov['pages_with_keyword_in_h1'])}</td>"
                    f"<td>{cov['pages_mentioning_in_body']} of "
                    f"{cov['total_pages_checked']}</td>"
                    f"<td class='url'>{e(primary)}</td></tr>")
            parts.append("</table></details>")
        if "ai_access" in s.data and s.data["ai_access"]:
            parts.append("<details open><summary>Crawler access matrix "
                         "(robots.txt)</summary><table><tr><th>Crawler</th>"
                         "<th>Purpose</th><th>Access</th></tr>")
            for agent, info in s.data["ai_access"].items():
                access = info["access"]
                color = "#188038" if access in ("allowed", "default") else "#d93025"
                label = {"allowed": "Allowed", "default": "Allowed (no rule)",
                         "blocked": "BLOCKED"}.get(access, access)
                parts.append(f"<tr><td>{e(agent)}</td><td>{e(info['purpose'])}</td>"
                             f"<td style='color:{color};font-weight:600'>{label}</td></tr>")
            parts.append("</table></details>")
        if "bot_hits" in s.data and s.data["bot_hits"]:
            parts.append("<details open><summary>Bot hits in log</summary>"
                         "<table><tr><th>Bot</th><th>Hits</th></tr>")
            for bot, hits in s.data["bot_hits"].items():
                parts.append(f"<tr><td>{e(bot)}</td><td>{hits:,}</td></tr>")
            parts.append("</table></details>")

    parts.append(
        "<footer>Generated by SEO Audit Pro &middot; Validate structured data at "
        "<a href='https://search.google.com/test/rich-results'>Rich Results Test</a>"
        " and <a href='https://validator.schema.org/'>Schema Validator</a>"
        "</footer></div></body></html>")
    return "".join(parts)
