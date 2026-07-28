"""Split audit results into 'Needs Repair' vs 'Repaired (verified)'.

The honest way to know something is repaired is to re-check it. After the
repair engine writes a corrected copy of the site, we re-audit those files and
compare against the original findings:

  - an original issue that is GONE from the re-audit  -> Repaired (verified)
  - an original issue still present                   -> Needs Repair
  - findings the on-page repairer can't touch         -> Needs Repair (manual):
    off-page, page speed, backlinks, broken links, etc.

Matching is done on (page path, category) so it survives the numbers changing
inside a message (e.g. "Title too long (69 chars)" simply disappearing).
"""

from urllib.parse import urlparse

from .issues import PASSED

# Categories the on-page repairer actually rewrites in the HTML. Anything else
# (off-page, performance, crawl errors...) can't be auto-verified from the
# repaired files, so it stays under "Needs Repair" labelled manual.
AUTO_FIXABLE = {
    "Title Tags", "Meta Descriptions", "Headings", "Image Optimization",
    "Mobile Friendliness", "Canonical Tags", "Schema Markup", "Social Meta",
}


def _path(url: str) -> str:
    try:
        p = urlparse(url).path or "/"
    except Exception:
        return url
    return p.rstrip("/") or "/"


def _key(issue) -> tuple:
    return (_path(issue.url), issue.category)


def split_results(original_sections, reaudit_section):
    """original_sections: list[SectionResult] from the first audit.
    reaudit_section: SectionResult from re-auditing the REPAIRED files
                     (on-page only), or None if we couldn't re-audit.

    Returns {"repaired": [dict], "needs_repair": [dict], "summary": {...}}.
    Each dict: {severity, category, message, url, fix, origin_section, status}.
    """
    # (path, category) pairs that STILL have a real (non-passed) issue.
    still_bad = set()
    if reaudit_section:
        for i in reaudit_section.issues:
            if i.severity != PASSED:
                still_bad.add(_key(i))

    repaired, needs = [], []
    for section in original_sections:
        for i in section.issues:
            if i.severity == PASSED:
                continue
            row = i.as_dict()
            row["origin_section"] = section.name
            auto = i.category in AUTO_FIXABLE and section.name == "On-Page SEO"
            if reaudit_section is None:
                # Can't verify; everything stays as needs-repair.
                row["status"] = "needs_repair"
                needs.append(row)
            elif auto and _key(i) not in still_bad:
                row["status"] = "repaired"
                repaired.append(row)
            else:
                row["status"] = ("needs_repair" if auto
                                 else "needs_repair_manual")
                needs.append(row)

    summary = {
        "repaired": len(repaired),
        "needs_repair": len(needs),
        "verified": reaudit_section is not None,
    }
    return {"repaired": repaired, "needs_repair": needs, "summary": summary}


def build_and_verify(pages, output_dir, business, keywords=None,
                     categories=None, base_url="", log=None):
    """Full flow used by the GUI's 'Build & verify repairs' action:
      1. audit the original pages (on-page)
      2. repair them into output_dir
      3. re-load + re-audit the repaired files
      4. split findings into repaired / needs-repair
    Returns {"result": <repair_site dict>, "split": <split_results dict>,
             "reaudited": bool}.
    """
    log = log or (lambda m: None)
    from .onpage import run_onpage_audit
    from .offpage import run_offpage_audit
    from . import repair as repairmod
    from .localsite import load_local_site

    keywords = keywords or []
    # 1. original audit (on-page + off-page for the full picture)
    log("Auditing the current site...")
    before_on = run_onpage_audit(pages, {}, keywords, log=log)
    name = base_url or business.get("brand") or "site"
    before_off = run_offpage_audit(name, pages,
                                   manual={"brand_name": business.get("brand", ""),
                                           "is_local_business": business.get("is_local", False)},
                                   log=log)
    original_sections = [before_on, before_off]

    # 2. repair
    log("Building repaired copy...")
    result = repairmod.repair_site(pages, output_dir, business, keywords=keywords,
                                   categories=categories, base_url=base_url, log=log)

    # 3. re-audit the repaired files
    reaudit = None
    reaudited = False
    try:
        repaired_root = result.get("output_dir", output_dir)
        log("Re-checking the repaired files to confirm fixes...")
        rpages, _inv = load_local_site(repaired_root, base_url=base_url)
        if rpages:
            reaudit = run_onpage_audit(rpages, {}, keywords, log=lambda m: None)
            reaudited = True
    except Exception as exc:
        log(f"(Could not re-audit repaired files: {exc}; "
            f"showing everything as needs-repair.)")

    # 4. split
    split = split_results(original_sections, reaudit)
    log(f"Verified: {split['summary']['repaired']} repaired, "
        f"{split['summary']['needs_repair']} still need attention.")
    return {"result": result, "split": split, "reaudited": reaudited}


def render_split_html(url, split, out_path):
    """Write a standalone two-section HTML page: Needs Repair / Repaired."""
    import html as _html
    from datetime import datetime
    e = _html.escape
    s = split["summary"]

    def rows(items, repaired):
        if not items:
            return ("<p class='empty'>Nothing here yet.</p>" if repaired
                    else "<p class='empty'>Nothing outstanding — great!</p>")
        out = ["<table><tr><th>Severity</th><th>Category</th><th>Item</th>"
               "<th>Page</th>" + ("" if repaired else "<th>How to fix</th>") + "</tr>"]
        for it in items:
            sev = it["severity"]
            manual = it.get("status") == "needs_repair_manual"
            color = {"CRITICAL": "#d93025", "WARNING": "#ea8600",
                     "NOTICE": "#1a73e8"}.get(sev, "#5f6368")
            label = ("REPAIRED" if repaired else
                     ("MANUAL" if manual else sev))
            lc = "#188038" if repaired else color
            out.append(
                f"<tr><td style='color:{lc};font-weight:700'>{label}</td>"
                f"<td>{e(it['category'])}</td><td>{e(it['message'])}</td>"
                f"<td class='u'>{e(it['url'])}</td>"
                + ("" if repaired else f"<td class='fix'>{e(it['fix'])}</td>")
                + "</tr>")
        out.append("</table>")
        return "".join(out)

    verified_note = ("These were re-checked on the repaired files and confirmed "
                     "fixed." if s["verified"] else
                     "Re-check was unavailable, so nothing is listed as verified "
                     "yet — rebuild with a base URL set to enable verification.")
    doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Repair status - {e(url)}</title><style>
 body{{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#f6f8fa;color:#202124}}
 .wrap{{max-width:1050px;margin:0 auto;padding:24px}}
 header{{background:#0b2545;color:#fff;padding:24px;border-radius:0 0 12px 12px}}
 h1{{margin:0 0 4px}} h2{{margin-top:28px}}
 .cards{{display:flex;gap:16px;margin-top:16px}}
 .card{{background:#fff;border-radius:10px;padding:16px 22px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
 .card .n{{font-size:32px;font-weight:700}}
 .needs .n{{color:#d93025}} .rep .n{{color:#188038}}
 table{{border-collapse:collapse;width:100%;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-top:8px}}
 th,td{{padding:9px 12px;text-align:left;font-size:14px;border-bottom:1px solid #eee;vertical-align:top}}
 th{{background:#f1f3f4;font-size:12px;text-transform:uppercase;letter-spacing:.4px}}
 .u{{color:#1a73e8;font-size:12px;word-break:break-all}} .fix{{color:#3c4043;font-size:13px}}
 .empty{{color:#5f6368;font-style:italic}}
 .sec-rep h2{{color:#188038}} .sec-needs h2{{color:#d93025}}
</style></head><body>
<header><div class="wrap"><h1>Repair status</h1>
<div>{e(url)} &middot; {datetime.now():%B %d, %Y %H:%M}</div>
<div class="cards">
 <div class="card needs"><div class="n">{s['needs_repair']}</div><div>Needs repair</div></div>
 <div class="card rep"><div class="n">{s['repaired']}</div><div>Repaired &#10003;</div></div>
</div></div></header><div class="wrap">
<div class="sec-needs"><h2>&#9888;&#65039; Needs repair ({s['needs_repair']})</h2>
{rows(split['needs_repair'], False)}</div>
<div class="sec-rep"><h2>&#10003; Repaired ({s['repaired']})</h2>
<p class="empty">{verified_note}</p>
{rows(split['repaired'], True)}</div>
</div></body></html>"""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return out_path
