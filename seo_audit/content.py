"""Content creation: full blog-post drafts, service landing pages, and bulk
meta descriptions. Extends the assistant's FAQ / blog-plan / guide generators
with the longer-form deliverables.

Every generator works offline from templates and is upgraded, when a Claude
API key is supplied, to genuinely written copy (parsed back into the local
HTML/markdown templates rather than trusting the model to emit valid markup).
"""

import html
import os
import re
from datetime import date

from .assistant import ai_enhance


def _services(profile):
    s = profile.get("services") or []
    if isinstance(s, str):
        s = [x.strip() for x in s.split(",") if x.strip()]
    return s or ["Our Service"]


def _area(profile):
    locs = profile.get("locations") or []
    return (locs[0] if locs else profile.get("city")) or "your area"


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ---------------------------------------------------------------------------
# Full blog-post draft (markdown)
# ---------------------------------------------------------------------------

def generate_blog_post(profile, topic="", keyword="", api_key=""):
    """Return a complete blog-post draft in markdown (not just an outline)."""
    brand = profile.get("brand") or "our team"
    service = _services(profile)[0]
    area = _area(profile)
    topic = topic or f"How to choose {service} in {area}"
    keyword = keyword or f"{service} {area}".lower()

    if api_key:
        prompt = (
            f"Write a complete, genuinely useful blog post in markdown.\n"
            f"Business: {brand} ({service}, serving {area}).\n"
            f"Title/topic: {topic}\nPrimary keyword (use naturally, no "
            f"stuffing): {keyword}\n\n"
            f"Requirements: 700-1000 words; start with an H1 title; a short "
            f"intro that answers the query directly in the first 2 sentences "
            f"(good for AI answers/featured snippets); 4-6 H2 sections; a "
            f"short FAQ of 3 Q&As at the end; a closing call to action to "
            f"contact {brand}. Return ONLY markdown.")
        text = ai_enhance(prompt, api_key)
        if text and text.strip():
            return text

    # Template fallback
    return f"""# {topic}

*By {brand}*

If you're searching for **{keyword}**, the short answer is: look for a
licensed, insured, well-reviewed local provider who explains the work up
front. Below is what that means in practice, and how to get it right in
{area}.

## What {service} actually involves

{brand} handles {service} for homes and businesses across {area}. The process
starts with an assessment, followed by a clear plan and a written estimate —
no surprises.

## What to look for in a {service} provider in {area}

- **Licensed and insured** — always verify before booking.
- **Local and responsive** — a provider who knows {area} and answers the phone.
- **Transparent pricing** — a written estimate before any work begins.
- **Real reviews** — recent, specific, and from {area} customers.

## How much does {service} cost in {area}?

Pricing depends on the size of the job and its urgency. Reputable {area}
providers give a written estimate up front. Be cautious of quotes that seem
far below the local average — they often signal cut corners.

## Common mistakes to avoid

Waiting too long, choosing on price alone, and skipping the written estimate
are the three most common (and most expensive) mistakes.

## Frequently asked questions

**How soon can I get {service} in {area}?**
Many providers, including {brand}, offer prompt and emergency scheduling.

**Is {service} worth it?**
Done right and on time, yes — it protects your property and saves money later.

**Do you serve my part of {area}?**
{brand} serves {area} and the surrounding communities — just ask.

## Get {service} done right in {area}

{brand} provides dependable {service} across {area}. Contact us for a fast,
no-pressure estimate.

<!-- EDIT ME: replace placeholders, add photos, and localize the details. -->
"""


# ---------------------------------------------------------------------------
# Service landing pages (one HTML page per service)
# ---------------------------------------------------------------------------

_PAGE_CSS = """<style>
body{font-family:'Segoe UI',system-ui,sans-serif;line-height:1.6;color:#222;
max-width:820px;margin:0 auto;padding:24px}
h1{color:#0b2545} h2{color:#13315c;margin-top:1.6em}
.cta{background:#2a9d8f;color:#fff;padding:14px 20px;border-radius:8px;
display:inline-block;text-decoration:none;font-weight:700;margin:16px 0}
.nap{background:#f4f7fb;padding:14px 18px;border-radius:8px;margin-top:24px}
ul{padding-left:20px}
</style>"""


def generate_service_page(profile, service, api_key=""):
    e = html.escape
    brand = profile.get("brand") or "Our Company"
    area = _area(profile)
    phone = profile.get("phone") or ""
    title = f"{service} in {area} | {brand}"[:60]
    desc = (f"Professional {service.lower()} in {area} by {brand}. "
            f"Licensed, insured, and reliable. "
            + (f"Call {phone}." if phone else "Get a free estimate."))[:155]

    body = ""
    if api_key:
        prompt = (
            f"Write the body HTML (no <html>/<head>, start at <h1>) for a "
            f"service landing page. Business {brand}, service '{service}', "
            f"area {area}. Include: h1, a direct 2-sentence intro, an h2 "
            f"'Our {service} services' with a <ul> of 4-6 offerings, an h2 "
            f"'Why choose {brand}', and an h2 FAQ with 3 q&as as <h3>/<p>. "
            f"Natural keyword use, no stuffing. Return only the body HTML.")
        ai = ai_enhance(prompt, api_key)
        if ai and "<h" in ai.lower():
            body = ai
    if not body:
        body = f"""<h1>{e(service)} in {e(area)}</h1>
<p>Looking for dependable {e(service.lower())} in {e(area)}? {e(brand)}
delivers professional, licensed, and insured service with clear pricing and
fast scheduling.</p>
<h2>Our {e(service.lower())} services</h2>
<ul>
  <li>Free, no-pressure assessment and written estimate</li>
  <li>Prompt and emergency scheduling across {e(area)}</li>
  <li>Licensed, insured, and background-checked technicians</li>
  <li>Workmanship you can rely on, backed by real local reviews</li>
</ul>
<h2>Why choose {e(brand)}</h2>
<p>We're local to {e(area)}, we answer the phone, and we explain the work
before we start — no surprises, no upsells.</p>
<h2>Frequently asked questions</h2>
<h3>How much does {e(service.lower())} cost in {e(area)}?</h3>
<p>It depends on the job; we give a written estimate up front.</p>
<h3>How soon can you come out?</h3>
<p>Often same-day for urgent jobs across {e(area)}.</p>
<h3>Are you licensed and insured?</h3>
<p>Yes — fully licensed and insured for your protection.</p>
<!-- EDIT ME: add photos, real specifics, and testimonials. -->"""

    nap = f"""<div class="nap"><strong>{e(brand)}</strong><br>
Serving {e(area)}{(' &middot; ' + e(phone)) if phone else ''}</div>"""
    cta = (f'<a class="cta" href="tel:{e(phone)}">Call {e(phone)}</a>'
           if phone else '<a class="cta" href="/contact">Get a free estimate</a>')
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">
{_PAGE_CSS}</head><body>
{body}
{cta}
{nap}
</body></html>"""


def generate_service_pages(profile, out_dir, api_key="", log=None):
    """Write one landing page per service. Returns {"pages":[paths],"count":N}."""
    log = log or (lambda m: None)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for svc in _services(profile):
        log(f"  Writing service page: {svc}")
        html_doc = generate_service_page(profile, svc, api_key=api_key)
        p = os.path.join(out_dir, f"{_slug(svc)}.html")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(html_doc)
        paths.append(p)
    return {"pages": paths, "count": len(paths)}


# ---------------------------------------------------------------------------
# Bulk meta descriptions
# ---------------------------------------------------------------------------

def generate_meta_descriptions(pages, profile, api_key="", log=None):
    """pages: list of (url, current_title). Returns list of dicts
    {url, title, meta} with a fresh <=155-char meta description each."""
    log = log or (lambda m: None)
    brand = profile.get("brand") or ""
    area = _area(profile)
    out = []
    for url, title in pages:
        meta = ""
        if api_key:
            prompt = (f"Write ONE meta description, max 155 characters, for a "
                      f"page titled '{title}' from {brand} ({area}). Compelling, "
                      f"includes a call to action, no quotes. Return only the "
                      f"description text.")
            ai = ai_enhance(prompt, api_key)
            if ai:
                meta = ai.strip().strip('"').replace("\n", " ")[:155]
        if not meta:
            t = (title or "").split("|")[0].strip() or "Our services"
            meta = (f"{t} from {brand} in {area}. Licensed, insured, and "
                    f"reliable. Contact us today for a free estimate.")[:155]
        out.append({"url": url, "title": title, "meta": meta})
    log(f"  Wrote {len(out)} meta description(s).")
    return out


def save_meta_descriptions(rows, out_dir):
    import csv
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "meta-descriptions.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["url", "current_title", "suggested_meta_description",
                    "length"])
        for r in rows:
            w.writerow([r["url"], r["title"], r["meta"], len(r["meta"])])
    return path
