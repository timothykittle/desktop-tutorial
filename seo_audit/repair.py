"""Add-or-repair engine: takes crawled or locally-loaded pages and writes a
repaired, ready-to-upload copy of the site ("site package"): fixed HTML files
plus robots.txt, llms.txt, sitemap.xml and a detailed change log.

Philosophy: conservative. ADD what's missing, fix what's unambiguously
broken, never delete visible content, and log every change with
before/after so the owner can review before uploading.
"""

import csv
import json
import os
import re
from datetime import date
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape

from bs4 import BeautifulSoup

from . import fixes

ALL_CATEGORIES = {"titles", "metas", "headings", "images", "mobile",
                  "canonical", "schema", "social", "links", "files"}

# Anchor texts that tell users (and search engines) nothing.
GENERIC_ANCHORS = {"click here", "read more", "here", "more", "link"}

# Host used by the local-upload loader when pages have no real URL.
LOCAL_HOST = "local.site"

TITLE_MAX = 65        # longer than this gets truncated...
TITLE_TARGET = 60     # ...down to a word boundary at or under this
DESC_MAX = 165
DESC_TARGET = 155


# ---------------------------------------------------------------- helpers

def _truncate_at_word(text: str, limit: int) -> str:
    """Collapse whitespace and cut to <= limit chars at a word boundary."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit + 1]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    else:
        cut = text[:limit]
    return cut.rstrip(" ,;:-|&")


def _snip(text: str, limit: int = 200) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _origin(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _public_url(page_url: str, base_url: str) -> str:
    """Map a page URL to its public URL. Empty string when unknowable
    (local upload with no base_url given)."""
    parsed = urlparse(page_url)
    path = parsed.path or "/"
    if base_url:
        return _origin(base_url) + path
    if parsed.netloc and parsed.netloc != LOCAL_HOST:
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    return ""


def _output_relpath(page_url: str) -> str:
    """Where a page lands inside the site package, mirroring its URL path.
    "/" -> index.html; "/about" -> about/index.html; "/x.html" stays x.html."""
    path = urlparse(page_url).path or "/"
    path = path.strip("/")
    # never let a hostile path escape the output dir
    parts = [p for p in path.split("/") if p not in ("", ".", "..")]
    if not parts:
        return "index.html"
    if "." in parts[-1]:
        return "/".join(parts)
    return "/".join(parts) + "/index.html"


def _slug_to_words(page_url: str) -> str:
    """Humanize the last URL path segment ("/our-team.html" -> "Our Team")."""
    path = urlparse(page_url).path.strip("/")
    slug = path.split("/")[-1] if path else ""
    slug = os.path.splitext(slug)[0]
    slug = re.sub(r"[-_]+", " ", slug).strip()
    return slug.title() if slug else "Home"


def _alt_from_filename(src: str) -> str:
    """Derive alt text from an image filename; empty string when the name
    carries no meaning (never hallucinate content)."""
    name = os.path.basename(urlparse(src or "").path)
    name = os.path.splitext(name)[0]
    name = re.sub(r"[-_+.]+", " ", name)
    kept = []
    for token in name.split():
        if re.fullmatch(r"\d{2,5}x\d{2,5}", token, re.I):
            continue  # dimensions like 300x200
        if re.fullmatch(r"[0-9a-f]{6,}", token, re.I):
            continue  # hex-ish hash chunks
        if re.fullmatch(r"\d{5,}", token):
            continue  # long id numbers
        kept.append(token)
    cleaned = " ".join(kept).strip()
    if len(re.sub(r"[^A-Za-z]", "", cleaned)) < 3:
        return ""
    return cleaned.title()


def _ensure_head(soup):
    """Return (head, created_bool); creates <head> when missing."""
    if soup.head:
        return soup.head, False
    head = soup.new_tag("head")
    if soup.html:
        soup.html.insert(0, head)
    else:
        soup.insert(0, head)
    return head, True


def _homepage_url(page_urls: list) -> str:
    """Shortest URL path wins ("/" beats "/about")."""
    if not page_urls:
        return ""
    return min(page_urls,
               key=lambda u: (len(urlparse(u).path.strip("/")), u))


def _extract_schema_dict(template_html: str) -> dict:
    """Pull the JSON object back out of a fixes.py <script> template."""
    match = re.search(r"<script[^>]*>\s*(\{.*\})\s*</script>",
                      template_html, re.S)
    return json.loads(match.group(1)) if match else {}


def _build_schema(site_url: str, business: dict) -> dict:
    """Organization (or LocalBusiness) JSON-LD from the fixes.py builders,
    with real business values filled in wherever we actually have them."""
    brand = business.get("brand") or "EDIT ME: business name"
    socials = business.get("socials") or {}
    if business.get("is_local"):
        schema = _extract_schema_dict(
            fixes.local_business_schema_template(site_url, brand))
        if business.get("phone"):
            schema["telephone"] = business["phone"]
        address = schema.get("address", {})
        for key, field in (("streetAddress", "street"),
                           ("addressLocality", "city"),
                           ("addressRegion", "state"),
                           ("postalCode", "zip"),
                           ("addressCountry", "country")):
            if business.get(field):
                address[key] = business[field]
        schema["address"] = address
        if isinstance(business.get("hours"), str) and business["hours"]:
            schema["openingHours"] = business["hours"]
            schema.pop("openingHoursSpecification", None)
        if socials:
            schema["sameAs"] = list(socials.values())
    else:
        schema = _extract_schema_dict(
            fixes.organization_schema_template(site_url, brand, socials))
        if business.get("phone"):
            schema.setdefault("contactPoint", {})["telephone"] = \
                business["phone"]
    if business.get("description"):
        schema["description"] = business["description"]
    return schema


def _sitemap_xml(urls: list) -> str:
    today = date.today().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        lines += ["  <url>",
                  f"    <loc>{xml_escape(url)}</loc>",
                  f"    <lastmod>{today}</lastmod>",
                  "  </url>"]
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def _build_llms_txt(site_url: str, business: dict, page_list: list) -> str:
    """llms.txt from the fixes.py template, with the About section filled
    in for real when the business data allows it - the whole point of the
    file is letting AI engines understand and recommend the business."""
    brand = business.get("brand") or urlparse(_origin(site_url)).netloc
    text = fixes.llms_txt_template(site_url, brand,
                                   business.get("description", ""),
                                   key_pages=page_list)
    about = []
    if business.get("description"):
        about.append(business["description"])
    services = business.get("services")
    if services:
        if isinstance(services, (list, tuple)):
            services = ", ".join(str(s) for s in services)
        about.append(f"Services: {services}.")
    location = ", ".join(v for v in (business.get("city"),
                                     business.get("state")) if v)
    if location:
        about.append(f"Located in {location}.")
    if business.get("phone"):
        about.append(f"Phone: {business['phone']}.")
    if about:
        lines = [(" ".join(about) if line.startswith("EDIT ME:") else line)
                 for line in text.splitlines()]
        text = "\n".join(lines)
    return text


def _write_site_files(output_dir: str, site_url: str, business: dict,
                      page_list: list, log) -> list:
    """robots.txt + llms.txt + sitemap.xml into output_dir. Returns paths."""
    os.makedirs(output_dir, exist_ok=True)
    written = []
    files = {
        "robots.txt": fixes.recommended_robots_txt(site_url),
        "llms.txt": _build_llms_txt(site_url, business, page_list),
        "sitemap.xml": _sitemap_xml([u for u, _t in page_list]),
    }
    for name, content in files.items():
        path = os.path.join(output_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        written.append(path)
        log(f"  Wrote {name}")
    return written


# ------------------------------------------------------------- public API

def repair_site(pages: dict, output_dir: str, business: dict,
                keywords: list = None, categories: set = None,
                base_url: str = "", log=None) -> dict:
    """Repair every crawled/loaded page and write a ready-to-upload site
    package into output_dir. `categories` limits which repair families run
    (None = all). Returns a summary dict with counts and log file paths.
    """
    log = log or (lambda msg: None)
    business = business or {}
    cats = set(categories) & ALL_CATEGORIES if categories else set(ALL_CATEGORIES)
    brand = business.get("brand", "")
    os.makedirs(output_dir, exist_ok=True)

    entries = []          # change-log rows
    repaired_pages = set()   # relpaths that received >= 1 real change
    page_relpaths = set()    # relpaths of every written HTML page

    def add_entry(relpath, url, category, action, before, after):
        entries.append({"file": relpath, "url": url, "category": category,
                        "action": action, "before": _snip(before),
                        "after": _snip(after)})
        if action != "suggestion":
            repaired_pages.add(relpath)

    ok_pages = {u: p for u, p in pages.items()
                if getattr(p, "ok", False) and getattr(p, "html", "")}
    homepage = _homepage_url(list(ok_pages))
    site_url = base_url or _public_url(homepage, base_url) or homepage or ""
    page_list = []  # (public_url, title) collected for llms.txt/sitemap

    for url, page in ok_pages.items():
        relpath = _output_relpath(url)
        page_relpaths.add(relpath)
        log(f"  Repairing: {url} -> {relpath}")
        soup = BeautifulSoup(page.html, "html.parser")
        public_url = _public_url(url, base_url)

        # ---- titles -------------------------------------------------
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        if "titles" in cats:
            head, created = _ensure_head(soup)
            if created:
                add_entry(relpath, url, "titles", "created <head>",
                          "(no <head>)", "<head>")
            if not title_text:
                h1 = soup.find("h1")
                base = (h1.get_text(strip=True) if h1 else "") or _slug_to_words(url)
                new_title = base + (f" | {brand}" if brand else "")
                new_title = _truncate_at_word(new_title, TITLE_TARGET)
                if title_tag is None:
                    title_tag = soup.new_tag("title")
                    head.append(title_tag)
                title_tag.string = new_title
                add_entry(relpath, url, "titles", "added title",
                          "(missing/empty)", new_title)
                title_text = new_title
            elif len(title_text) > TITLE_MAX:
                new_title = _truncate_at_word(title_text, TITLE_TARGET)
                old = title_text
                title_tag.string = new_title
                add_entry(relpath, url, "titles", "truncated title",
                          old, new_title)
                title_text = new_title

        # ---- metas --------------------------------------------------
        desc_tag = soup.find("meta", attrs={
            "name": lambda v: v and v.lower() == "description"})
        desc_text = (desc_tag.get("content") or "").strip() if desc_tag else ""
        if "metas" in cats:
            head, created = _ensure_head(soup)
            if created:
                add_entry(relpath, url, "metas", "created <head>",
                          "(no <head>)", "<head>")
            if not desc_text:
                new_desc = ""
                for p in soup.find_all("p"):
                    text = p.get_text(" ", strip=True)
                    if len(text.split()) >= 40:
                        new_desc = _truncate_at_word(text, DESC_TARGET)
                        break
                if not new_desc:
                    parts = [x for x in (business.get("description"), brand) if x]
                    if parts:
                        new_desc = _truncate_at_word(" - ".join(parts), DESC_TARGET)
                if new_desc:
                    if desc_tag is None:
                        desc_tag = soup.new_tag("meta")
                        desc_tag["name"] = "description"
                        head.append(desc_tag)
                    desc_tag["content"] = new_desc
                    add_entry(relpath, url, "metas", "added meta description",
                              "(missing/empty)", new_desc)
                    desc_text = new_desc
            elif len(desc_text) > DESC_MAX:
                new_desc = _truncate_at_word(desc_text, DESC_TARGET)
                add_entry(relpath, url, "metas", "trimmed meta description",
                          desc_text, new_desc)
                desc_tag["content"] = new_desc
                desc_text = new_desc

        # ---- headings -----------------------------------------------
        if "headings" in cats:
            h1s = soup.find_all("h1")
            if not h1s:
                h2 = soup.find("h2")
                if h2:
                    before = str(h2)
                    h2.name = "h1"
                    add_entry(relpath, url, "headings",
                              "promoted first H2 to H1", before, str(h2))
                else:
                    h1_text = title_text
                    if brand and h1_text.endswith(f" | {brand}"):
                        h1_text = h1_text[:-len(f" | {brand}")].rstrip()
                    h1_text = h1_text or _slug_to_words(url)
                    new_h1 = soup.new_tag("h1")
                    new_h1.string = h1_text
                    target = soup.body or soup
                    target.insert(0, new_h1)
                    add_entry(relpath, url, "headings", "inserted H1",
                              "(no H1)", str(new_h1))
            elif len(h1s) > 1:
                for extra in h1s[1:]:
                    before = str(extra)
                    extra.name = "h2"
                    add_entry(relpath, url, "headings",
                              "demoted extra H1 to H2", before, str(extra))

        # ---- images -------------------------------------------------
        if "images" in cats:
            for idx, img in enumerate(soup.find_all("img")):
                if not img.has_attr("alt") and \
                        (img.get("role") or "").lower() != "presentation":
                    before = str(img)
                    img["alt"] = _alt_from_filename(img.get("src", ""))
                    add_entry(relpath, url, "images", "added alt text",
                              before, str(img))
                if idx >= 2 and not img.has_attr("loading"):
                    before = str(img)
                    img["loading"] = "lazy"
                    add_entry(relpath, url, "images", "added loading=lazy",
                              before, str(img))

        # ---- mobile -------------------------------------------------
        if "mobile" in cats:
            viewport = soup.find("meta", attrs={
                "name": lambda v: v and v.lower() == "viewport"})
            if not viewport:
                head, created = _ensure_head(soup)
                if created:
                    add_entry(relpath, url, "mobile", "created <head>",
                              "(no <head>)", "<head>")
                tag = soup.new_tag("meta")
                tag["name"] = "viewport"
                tag["content"] = "width=device-width, initial-scale=1"
                head.append(tag)
                add_entry(relpath, url, "mobile", "added viewport meta",
                          "(missing)", str(tag))

        # ---- canonical ----------------------------------------------
        canonical_url = public_url
        if "canonical" in cats:
            existing = soup.find("link", rel="canonical")
            if existing:
                canonical_url = existing.get("href") or canonical_url
            elif not canonical_url:
                add_entry(relpath, url, "canonical", "suggestion",
                          "(no canonical)",
                          "Local upload without a site URL - set the site's "
                          "public URL to generate canonical tags.")
            else:
                head, created = _ensure_head(soup)
                if created:
                    add_entry(relpath, url, "canonical", "created <head>",
                              "(no <head>)", "<head>")
                tag = soup.new_tag("link", rel="canonical", href=canonical_url)
                head.append(tag)
                add_entry(relpath, url, "canonical", "added canonical link",
                          "(missing)", str(tag))

        # ---- social -------------------------------------------------
        if "social" in cats:
            head, created = _ensure_head(soup)
            if created:
                add_entry(relpath, url, "social", "created <head>",
                          "(no <head>)", "<head>")

            def _og(prop):
                return soup.find("meta", attrs={"property": prop})

            og_values = [("og:title", title_text),
                         ("og:description", desc_text),
                         ("og:type", "website"),
                         ("og:url", canonical_url)]
            for prop, value in og_values:
                if value and not _og(prop):
                    tag = soup.new_tag("meta")
                    tag["property"] = prop
                    tag["content"] = value
                    head.append(tag)
                    add_entry(relpath, url, "social", f"added {prop}",
                              "(missing)", str(tag))
            has_twitter = soup.find("meta", attrs={
                "name": lambda v: v and v.lower().startswith("twitter:")})
            if not has_twitter:
                tag = soup.new_tag("meta")
                tag["name"] = "twitter:card"
                tag["content"] = "summary_large_image"
                head.append(tag)
                add_entry(relpath, url, "social", "added twitter:card",
                          "(missing)", str(tag))

        # ---- schema (homepage only) ---------------------------------
        if "schema" in cats and url == homepage:
            has_ld = soup.find("script", attrs={
                "type": lambda v: v and v.lower() == "application/ld+json"})
            if not has_ld:
                head, created = _ensure_head(soup)
                if created:
                    add_entry(relpath, url, "schema", "created <head>",
                              "(no <head>)", "<head>")
                schema = _build_schema(site_url or url, business)
                tag = soup.new_tag("script")
                tag["type"] = "application/ld+json"
                tag.string = "\n" + json.dumps(schema, indent=2) + "\n"
                head.append(tag)
                add_entry(relpath, url, "schema",
                          "added " + schema.get("@type", "Organization")
                          + " JSON-LD", "(no structured data)",
                          json.dumps(schema))

        # ---- links (suggestions only, never rewritten) ---------------
        if "links" in cats:
            for a in soup.find_all("a", href=True):
                text = a.get_text(" ", strip=True).lower().strip(".!")
                if text in GENERIC_ANCHORS:
                    add_entry(relpath, url, "links", "suggestion", str(a),
                              f'Replace generic anchor text "{text}" with '
                              "words describing the destination page.")

        # ---- write the repaired page --------------------------------
        out_path = os.path.join(output_dir, relpath)
        os.makedirs(os.path.dirname(out_path) or output_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(str(soup))

        final_title = soup.find("title")
        page_list.append((public_url or url,
                          final_title.get_text(strip=True) if final_title else ""))

    # ---- site-wide files --------------------------------------------
    if "files" in cats and page_list:
        for path in _write_site_files(output_dir, site_url or "example.com",
                                      business, page_list, log):
            add_entry(os.path.basename(path), site_url, "files",
                      "wrote " + os.path.basename(path), "(missing)", path)

    # ---- change log ---------------------------------------------------
    log_json = os.path.join(output_dir, "repair_log.json")
    log_csv = os.path.join(output_dir, "repair_log.csv")
    with open(log_json, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)
    with open(log_csv, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["file", "url", "category",
                                                "action", "before", "after"])
        writer.writeheader()
        writer.writerows(entries)

    changes = sum(1 for e in entries if e["action"] != "suggestion")
    suggestions = len(entries) - changes
    by_category = {}
    for e in entries:
        by_category[e["category"]] = by_category.get(e["category"], 0) + 1
    log(f"Repair complete: {changes} changes, {suggestions} suggestions "
        f"across {len(ok_pages)} pages.")
    return {
        "pages_repaired": len(repaired_pages & page_relpaths),
        "changes": changes,
        "suggestions": suggestions,
        "output_dir": output_dir,
        "log_json": log_json,
        "log_csv": log_csv,
        "by_category": by_category,
    }


def repair_files_only(output_dir, business, page_list, base_url,
                      log=None) -> dict:
    """Write just robots.txt, llms.txt and sitemap.xml into output_dir
    (used by the GUI's "Add/Repair robots.txt" / "Add/Repair llms.txt"
    buttons). page_list is a list of (url, title) tuples."""
    log = log or (lambda msg: None)
    business = business or {}
    site_url = base_url or (page_list[0][0] if page_list else "example.com")
    written = _write_site_files(output_dir, site_url, business,
                                page_list or [], log)
    return {"written": written}
