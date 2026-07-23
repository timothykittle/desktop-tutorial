"""On-page SEO checks: titles, metas, headings, content, URLs, images,
internal linking, keywords, schema markup, mobile viewport."""

import json
import re
from collections import Counter
from urllib.parse import urlparse, urljoin

from .issues import SectionResult, CRITICAL, WARNING, NOTICE, PASSED

GENERIC_ANCHORS = {"click here", "here", "read more", "learn more", "more",
                   "link", "this", "click", "go", "page"}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "at", "by", "from", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "as", "we", "our", "you", "your", "i",
    "not", "no", "so", "if", "then", "than", "these", "those", "will",
    "can", "all", "have", "has", "had", "do", "does", "did", "their",
}


def _words(text: str) -> list:
    return re.findall(r"[a-zA-Z0-9']+", text.lower())


def _visible_text(soup) -> str:
    body = soup.find("body")
    if not body:
        return ""
    clone_texts = []
    for el in body.find_all(string=True):
        parent = el.parent.name if el.parent else ""
        if parent in ("script", "style", "noscript", "template"):
            continue
        text = el.strip()
        if text:
            clone_texts.append(text)
    return " ".join(clone_texts)


def run_onpage_audit(pages: dict, broken_links: dict, keywords: list,
                     log=None) -> SectionResult:
    log = log or (lambda m: None)
    result = SectionResult("On-Page SEO")
    ok_pages = {u: p for u, p in pages.items() if p.ok and p.soup}
    if not ok_pages:
        result.add(CRITICAL, "Crawl", "No pages could be crawled and parsed.",
                   fix="Check that the site is online and serves HTML.")
        return result

    titles, descriptions = {}, {}
    inbound_links = Counter()
    page_summaries = []

    for url, page in ok_pages.items():
        for link, _ in page.internal_links:
            if link != url:
                inbound_links[link] += 1

    for url, page in ok_pages.items():
        soup = page.soup
        summary = {"url": url}

        # ---------------- Title tag ----------------
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        summary["title"] = title
        if not title:
            result.add(CRITICAL, "Title Tags", "Missing <title> tag.", url,
                       fix="Add a unique, descriptive title of 30-60 characters "
                           "with the page's primary keyword near the front.")
        else:
            titles.setdefault(title, []).append(url)
            if len(title) < 30:
                result.add(WARNING, "Title Tags",
                           f"Title too short ({len(title)} chars): \"{title}\"", url,
                           fix="Expand to 30-60 characters; include the primary "
                               "keyword and a benefit or differentiator.")
            elif len(title) > 60:
                result.add(WARNING, "Title Tags",
                           f"Title too long ({len(title)} chars) - may be cut off "
                           f"in search results.", url,
                           fix="Shorten to under 60 characters, keeping the "
                               "primary keyword near the beginning.")
            else:
                result.add(PASSED, "Title Tags", f"Title length OK ({len(title)} chars).", url)

        # ---------------- Meta description ----------------
        meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        desc = (meta.get("content") or "").strip() if meta else ""
        summary["meta_description"] = desc
        if not desc:
            result.add(CRITICAL, "Meta Descriptions", "Missing meta description.", url,
                       fix="Add a 70-160 character meta description that summarizes "
                           "the page, includes the primary keyword, and ends with a "
                           "call to action.")
        else:
            descriptions.setdefault(desc, []).append(url)
            if len(desc) < 70:
                result.add(WARNING, "Meta Descriptions",
                           f"Meta description too short ({len(desc)} chars).", url,
                           fix="Expand to 70-160 characters to use the full snippet space.")
            elif len(desc) > 160:
                result.add(WARNING, "Meta Descriptions",
                           f"Meta description too long ({len(desc)} chars) - will be "
                           f"truncated.", url,
                           fix="Trim to 160 characters or fewer; front-load the key message.")
            else:
                result.add(PASSED, "Meta Descriptions", "Meta description length OK.", url)

        # ---------------- Headings ----------------
        h1s = soup.find_all("h1")
        summary["h1"] = h1s[0].get_text(strip=True) if h1s else ""
        if len(h1s) == 0:
            result.add(CRITICAL, "Headings", "No H1 heading found.", url,
                       fix="Add exactly one H1 that states the page topic and "
                           "includes the primary keyword.")
        elif len(h1s) > 1:
            result.add(WARNING, "Headings", f"{len(h1s)} H1 headings found "
                       f"(should be exactly 1).", url,
                       fix="Keep one H1; demote the others to H2/H3.")
        else:
            result.add(PASSED, "Headings", "Exactly one H1 present.", url)

        heading_seq = [int(h.name[1]) for h in
                       soup.find_all(re.compile(r"^h[1-6]$"))]
        for i in range(1, len(heading_seq)):
            if heading_seq[i] - heading_seq[i - 1] > 1:
                result.add(NOTICE, "Headings",
                           f"Heading level skip: H{heading_seq[i-1]} followed by "
                           f"H{heading_seq[i]}.", url,
                           fix="Keep a logical hierarchy (H1 > H2 > H3) without "
                               "skipping levels.")
                break
        empty_headings = [h.name for h in soup.find_all(re.compile(r"^h[1-6]$"))
                          if not h.get_text(strip=True)]
        if empty_headings:
            result.add(NOTICE, "Headings",
                       f"{len(empty_headings)} empty heading tag(s) found.", url,
                       fix="Remove empty heading tags or add descriptive text.")

        # ---------------- Content quality ----------------
        text = _visible_text(soup)
        word_count = len(_words(text))
        summary["word_count"] = word_count
        if word_count < 300:
            result.add(WARNING, "Content Quality",
                       f"Thin content: only {word_count} words.", url,
                       fix="Expand to 300+ words of genuinely useful content that "
                           "matches the search intent for the page's target query. "
                           "Answer the questions a searcher would have.")
        else:
            result.add(PASSED, "Content Quality", f"Word count OK ({word_count}).", url)

        # ---------------- Keyword usage ----------------
        if keywords:
            text_lower = text.lower()
            title_lower = title.lower()
            h1_lower = summary["h1"].lower()
            for kw in keywords:
                kw_l = kw.lower().strip()
                if not kw_l:
                    continue
                occurrences = text_lower.count(kw_l)
                in_title = kw_l in title_lower
                in_h1 = kw_l in h1_lower
                if page.depth == 0:  # judge keyword placement on the start page
                    if not in_title:
                        result.add(WARNING, "Keyword Usage",
                                   f"Keyword \"{kw}\" not found in the title tag.", url,
                                   fix=f"Work \"{kw}\" naturally into the title, "
                                       f"ideally near the front.")
                    if not in_h1:
                        result.add(NOTICE, "Keyword Usage",
                                   f"Keyword \"{kw}\" not found in the H1.", url,
                                   fix=f"Include \"{kw}\" (or a close variant) in the H1.")
                    if occurrences == 0:
                        result.add(WARNING, "Keyword Usage",
                                   f"Keyword \"{kw}\" does not appear in body content.", url,
                                   fix=f"Mention \"{kw}\" naturally in the first 100 words "
                                       f"and a few times through the copy. Do not stuff.")
                    elif word_count and occurrences / word_count > 0.03:
                        result.add(WARNING, "Keyword Usage",
                                   f"Possible keyword stuffing: \"{kw}\" appears "
                                   f"{occurrences} times ({occurrences / word_count:.1%} "
                                   f"density).", url,
                                   fix="Keep density under ~2-3%; use synonyms and "
                                       "related terms instead.")
                    else:
                        result.add(PASSED, "Keyword Usage",
                                   f"Keyword \"{kw}\" used {occurrences}x - looks natural.",
                                   url)

        # ---------------- URL structure ----------------
        parsed = urlparse(url)
        path = parsed.path
        if len(url) > 115:
            result.add(NOTICE, "URL Structure", f"Long URL ({len(url)} chars).", url,
                       fix="Prefer short, descriptive URLs (3-5 words).")
        if "_" in path:
            result.add(NOTICE, "URL Structure", "URL uses underscores.", url,
                       fix="Use hyphens instead of underscores in URL slugs.")
        if re.search(r"[A-Z]", path):
            result.add(NOTICE, "URL Structure", "URL contains uppercase characters.", url,
                       fix="Use lowercase URLs and 301-redirect the uppercase variants.")
        if parsed.query and page.depth == 0:
            result.add(NOTICE, "URL Structure", "URL contains query parameters.", url,
                       fix="Prefer clean paths; use canonical tags on parameterized URLs.")
        if path.count("/") > 4:
            result.add(NOTICE, "URL Structure",
                       f"Deep URL ({path.count('/')} levels).", url,
                       fix="Keep important pages within 3 clicks / levels of the homepage.")

        # ---------------- Images ----------------
        images = soup.find_all("img")
        missing_alt = [img for img in images
                       if not (img.get("alt") or "").strip()
                       and not img.get("role") == "presentation"]
        summary["images"] = len(images)
        summary["images_missing_alt"] = len(missing_alt)
        if missing_alt:
            examples = ", ".join((img.get("src") or "?")[:60] for img in missing_alt[:3])
            result.add(WARNING, "Image Optimization",
                       f"{len(missing_alt)} of {len(images)} images missing alt text "
                       f"(e.g. {examples}).", url,
                       fix="Add descriptive alt text to every content image. "
                           "Describe the image; include a keyword only when natural.")
        elif images:
            result.add(PASSED, "Image Optimization",
                       f"All {len(images)} images have alt text.", url)
        bad_names = [img for img in images if re.search(
            r"(?:^|/)(?:img|image|dsc|screenshot|untitled|photo)?[_-]?\d{2,}[^/]*$",
            (img.get("src") or "").lower())]
        if bad_names:
            result.add(NOTICE, "Image Optimization",
                       f"{len(bad_names)} image(s) with non-descriptive file names "
                       f"(e.g. IMG_1234.jpg).", url,
                       fix="Rename image files descriptively, e.g. "
                           "blue-widget-front-view.webp.")
        legacy_fmt = [img for img in images if re.search(
            r"\.(png|jpe?g|gif|bmp)(\?|$)", (img.get("src") or "").lower())]
        if len(legacy_fmt) > 2:
            result.add(NOTICE, "Image Optimization",
                       f"{len(legacy_fmt)} image(s) using legacy formats (JPG/PNG/GIF).",
                       url,
                       fix="Serve modern formats (WebP/AVIF) and compress images; "
                           "add width/height attributes to prevent layout shift.")
        no_dims = [img for img in images
                   if not (img.get("width") and img.get("height"))
                   and not img.get("style")]
        if len(no_dims) > 2:
            result.add(NOTICE, "Image Optimization",
                       f"{len(no_dims)} image(s) missing width/height attributes "
                       f"(causes layout shift / hurts CLS).", url,
                       fix="Add explicit width and height attributes to all images.")
        no_lazy = [img for img in images if not img.get("loading")]
        if len(images) > 5 and len(no_lazy) > 3:
            result.add(NOTICE, "Image Optimization",
                       "Most images lack loading=\"lazy\".", url,
                       fix="Add loading=\"lazy\" to below-the-fold images.")

        # ---------------- Internal linking ----------------
        summary["internal_links"] = len(page.internal_links)
        if len(page.internal_links) == 0:
            result.add(WARNING, "Internal Linking", "Page has no internal links.", url,
                       fix="Link to related pages using descriptive anchor text.")
        generic = [a for _, a in page.internal_links if a.lower().strip() in GENERIC_ANCHORS]
        if generic:
            result.add(NOTICE, "Internal Linking",
                       f"{len(generic)} internal link(s) with generic anchor text "
                       f"(\"click here\", \"read more\"...).", url,
                       fix="Use descriptive, keyword-relevant anchor text that says "
                           "where the link goes.")

        # ---------------- Canonical ----------------
        canonical = soup.find("link", rel=lambda v: v and "canonical" in v)
        if not canonical or not canonical.get("href"):
            result.add(WARNING, "Canonical Tags", "No canonical tag found.", url,
                       fix=f"Add <link rel=\"canonical\" href=\"{url}\"> to prevent "
                           f"duplicate-content issues.")
        else:
            result.add(PASSED, "Canonical Tags", "Canonical tag present.", url)

        # ---------------- Mobile viewport ----------------
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            result.add(CRITICAL, "Mobile Friendliness",
                       "Missing viewport meta tag - page is not mobile-friendly.", url,
                       fix="Add <meta name=\"viewport\" content=\"width=device-width, "
                           "initial-scale=1\"> to the <head>.")
        else:
            result.add(PASSED, "Mobile Friendliness", "Viewport meta tag present.", url)

        # ---------------- Schema / structured data ----------------
        ld_blocks = soup.find_all("script", type="application/ld+json")
        schema_types = []
        for block in ld_blocks:
            try:
                data = json.loads(block.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict):
                        graph = item.get("@graph")
                        nodes = graph if isinstance(graph, list) else [item]
                        for node in nodes:
                            if isinstance(node, dict) and node.get("@type"):
                                t = node["@type"]
                                schema_types.extend(t if isinstance(t, list) else [t])
            except (json.JSONDecodeError, TypeError):
                result.add(WARNING, "Schema Markup",
                           "JSON-LD block contains invalid JSON.", url,
                           fix="Fix the JSON syntax; validate at "
                               "https://validator.schema.org/.")
        has_microdata = bool(soup.find(attrs={"itemscope": True}))
        summary["schema_types"] = sorted(set(schema_types))
        if not ld_blocks and not has_microdata:
            result.add(WARNING, "Schema Markup", "No structured data found on page.", url,
                       fix="Add JSON-LD structured data (Organization/LocalBusiness on "
                           "the homepage; Article, Product, FAQPage, BreadcrumbList as "
                           "appropriate). Validate with Google's Rich Results Test.")
        elif schema_types:
            result.add(PASSED, "Schema Markup",
                       f"Structured data found: {', '.join(sorted(set(schema_types)))}.",
                       url)

        # ---------------- Social meta (helps sharing + AI engines) ----------------
        og = soup.find("meta", attrs={"property": "og:title"})
        if not og:
            result.add(NOTICE, "Social Meta",
                       "Missing Open Graph tags (og:title / og:description / og:image).",
                       url,
                       fix="Add Open Graph and Twitter Card meta tags so shared links "
                           "and AI answer engines render rich previews.")

        page_summaries.append(summary)

    # ---------------- Cross-page checks ----------------
    for title, urls in titles.items():
        if len(urls) > 1:
            result.add(WARNING, "Title Tags",
                       f"Duplicate title on {len(urls)} pages: \"{title[:70]}\" "
                       f"({', '.join(urls[:3])}...)",
                       fix="Give every page a unique title describing its specific content.")
    for desc, urls in descriptions.items():
        if len(urls) > 1:
            result.add(WARNING, "Meta Descriptions",
                       f"Duplicate meta description on {len(urls)} pages "
                       f"({', '.join(urls[:3])}...)",
                       fix="Write a unique meta description for each page.")

    orphans = [u for u in ok_pages
               if inbound_links[u] == 0 and ok_pages[u].depth > 0]
    for u in orphans:
        result.add(WARNING, "Internal Linking",
                   "Page has no internal links pointing to it (orphan-ish).", u,
                   fix="Link to this page from related content and/or navigation.")

    for link, sources in broken_links.items():
        result.add(CRITICAL, "Internal Linking",
                   f"Broken internal link: {link} (linked from {len(sources)} page(s), "
                   f"e.g. {sources[0]}).",
                   fix="Fix or remove the link, or 301-redirect the target URL.")

    result.data["pages"] = page_summaries
    result.data["crawled"] = len(ok_pages)
    return result
