"""Technical SEO checks: crawlability, indexing, robots.txt, sitemaps,
HTTPS, performance headers, and 2026-era AI crawler access (GPTBot,
ClaudeBot, PerplexityBot, Google-Extended, etc.)."""

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

from .crawler import USER_AGENT
from .issues import SectionResult, CRITICAL, WARNING, NOTICE, PASSED

# AI crawlers that matter for visibility in AI answers (AI Overviews,
# ChatGPT Search, Perplexity, Claude, etc.) as of 2026.
AI_CRAWLERS = [
    ("GPTBot", "OpenAI - training + ChatGPT answers"),
    ("OAI-SearchBot", "OpenAI - ChatGPT Search results"),
    ("ChatGPT-User", "OpenAI - live page fetches for user questions"),
    ("ClaudeBot", "Anthropic - Claude answers"),
    ("Claude-User", "Anthropic - live fetches for Claude users"),
    ("PerplexityBot", "Perplexity - search index"),
    ("Perplexity-User", "Perplexity - live fetches"),
    ("Google-Extended", "Google - Gemini training (does NOT affect Search/AI Overviews)"),
    ("Applebot-Extended", "Apple - Apple Intelligence training"),
    ("CCBot", "Common Crawl - feeds many AI training sets"),
    ("Bytespider", "ByteDance - training"),
    ("meta-externalagent", "Meta - AI training"),
]

SEARCH_CRAWLERS = [
    ("Googlebot", "Google Search"),
    ("Bingbot", "Bing / ChatGPT Search backbone"),
]


def _robots_rules(robots_txt: str) -> dict:
    """Parse robots.txt into {user_agent_lower: [(directive, path), ...]}."""
    rules, current_agents = {}, []
    seen_directive_since_agent = True
    for raw in robots_txt.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if seen_directive_since_agent:
                current_agents = []
                seen_directive_since_agent = False
            current_agents.append(value.lower())
            rules.setdefault(value.lower(), [])
        elif key in ("allow", "disallow"):
            seen_directive_since_agent = True
            for agent in current_agents:
                rules[agent].append((key, value))
    return rules


def _agent_access(rules: dict, agent: str) -> str:
    """Return 'blocked', 'allowed', or 'default' for full-site access."""
    agent = agent.lower()
    group = rules.get(agent)
    if group is None:
        group = rules.get("*")
        if group is None:
            return "default"
    for directive, path in group:
        if directive == "disallow" and path == "/":
            # An explicit "Allow: /" in the same group overrides
            if any(d == "allow" and p == "/" for d, p in group):
                return "allowed"
            return "blocked"
    return "allowed"


def run_technical_audit(start_url: str, pages: dict, session=None,
                        log=None, timeout=15) -> SectionResult:
    log = log or (lambda m: None)
    result = SectionResult("Technical SEO & AI Readiness")
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)

    if not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url
    parsed = urlparse(start_url)
    scheme, netloc = parsed.scheme, parsed.netloc
    origin = f"{scheme}://{netloc}"

    # ---------------- HTTPS ----------------
    log("  Checking HTTPS and redirects...")
    if scheme != "https":
        result.add(CRITICAL, "HTTPS", "Site audited over HTTP, not HTTPS.",
                   fix="Install a TLS certificate and 301-redirect all HTTP "
                       "traffic to HTTPS.")
    else:
        result.add(PASSED, "HTTPS", "Site serves over HTTPS.")
        try:
            resp = session.get(f"http://{netloc}/", timeout=timeout,
                               allow_redirects=True)
            if urlparse(resp.url).scheme == "https":
                result.add(PASSED, "HTTPS", "HTTP correctly redirects to HTTPS.")
            else:
                result.add(CRITICAL, "HTTPS",
                           "HTTP version does NOT redirect to HTTPS (duplicate site).",
                           fix="Add a server-level 301 redirect from http:// to https://.")
        except requests.RequestException:
            result.add(NOTICE, "HTTPS", "Could not test the HTTP->HTTPS redirect.")

    # ---------------- www / non-www consistency ----------------
    alt_host = netloc[4:] if netloc.startswith("www.") else f"www.{netloc}"
    try:
        resp = session.get(f"{scheme}://{alt_host}/", timeout=timeout,
                           allow_redirects=True)
        final_host = urlparse(resp.url).netloc
        if resp.status_code == 200 and final_host not in (netloc, alt_host):
            pass
        elif resp.status_code == 200 and final_host == alt_host:
            result.add(WARNING, "Canonical Domain",
                       f"Both {netloc} and {alt_host} resolve with 200 - "
                       f"duplicate content risk.",
                       fix=f"301-redirect {alt_host} to {netloc} (pick one canonical host).")
        else:
            result.add(PASSED, "Canonical Domain",
                       f"{alt_host} redirects to the canonical host.")
    except requests.RequestException:
        pass

    # ---------------- robots.txt ----------------
    log("  Checking robots.txt and AI crawler access...")
    robots_txt, robots_status = "", 0
    try:
        resp = session.get(f"{origin}/robots.txt", timeout=timeout)
        robots_status, robots_txt = resp.status_code, resp.text
    except requests.RequestException as exc:
        result.add(WARNING, "Robots.txt", f"Could not fetch robots.txt: {exc}")

    ai_access = {}
    if robots_status == 200:
        result.add(PASSED, "Robots.txt", "robots.txt found.")
        rules = _robots_rules(robots_txt)
        if _agent_access(rules, "googlebot") == "blocked":
            result.add(CRITICAL, "Robots.txt",
                       "Googlebot is blocked from the entire site!",
                       fix="Remove the 'Disallow: /' rule for Googlebot/* in robots.txt.")
        if "sitemap" not in robots_txt.lower():
            result.add(NOTICE, "Robots.txt", "No Sitemap: directive in robots.txt.",
                       fix=f"Add 'Sitemap: {origin}/sitemap.xml' to robots.txt.")
        for agent, purpose in SEARCH_CRAWLERS + AI_CRAWLERS:
            ai_access[agent] = {"access": _agent_access(rules, agent),
                                "purpose": purpose}
        blocked_ai = [a for a, info in ai_access.items()
                      if info["access"] == "blocked"
                      and a not in ("Googlebot", "Bingbot")]
        answer_bots = {"GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot",
                       "PerplexityBot"}
        blocked_answer = [a for a in blocked_ai if a in answer_bots]
        if blocked_answer:
            result.add(WARNING, "AI Crawlers",
                       f"AI answer-engine crawlers blocked: {', '.join(blocked_answer)}. "
                       f"Your content cannot appear in those AI answers.",
                       fix="If you WANT visibility in ChatGPT/Claude/Perplexity answers, "
                           "allow these bots in robots.txt. Blocking them is a valid "
                           "choice only if you deliberately opt out of AI answers.")
        elif all(info["access"] in ("allowed", "default")
                 for a, info in ai_access.items() if a in answer_bots):
            result.add(PASSED, "AI Crawlers",
                       "AI answer-engine crawlers (GPTBot, ClaudeBot, PerplexityBot...) "
                       "are not blocked - content is eligible for AI answers.")
    elif robots_status == 404:
        result.add(NOTICE, "Robots.txt", "No robots.txt file (all crawlers allowed "
                   "by default).",
                   fix=f"Create {origin}/robots.txt with a Sitemap directive and "
                       f"deliberate AI-crawler rules. (A template is generated in "
                       f"the fixes folder.)")
        for agent, purpose in SEARCH_CRAWLERS + AI_CRAWLERS:
            ai_access[agent] = {"access": "default", "purpose": purpose}
    result.data["ai_access"] = ai_access
    result.data["robots_txt"] = robots_txt[:5000]

    # ---------------- llms.txt (GEO/AEO) ----------------
    try:
        resp = session.get(f"{origin}/llms.txt", timeout=timeout)
        if resp.status_code == 200 and len(resp.text) > 20:
            result.add(PASSED, "AI Readiness (GEO)", "llms.txt found - helps AI "
                       "engines understand and cite your site.")
        else:
            result.add(NOTICE, "AI Readiness (GEO)",
                       "No llms.txt file found.",
                       fix="Add an /llms.txt file - a markdown summary of your site "
                           "and key pages - to guide AI engines (a template is "
                           "generated in the fixes folder).")
    except requests.RequestException:
        pass

    # ---------------- sitemap.xml ----------------
    log("  Checking XML sitemap...")
    sitemap_urls = re.findall(r"(?im)^sitemap:\s*(\S+)", robots_txt)
    candidates = sitemap_urls or [f"{origin}/sitemap.xml",
                                  f"{origin}/sitemap_index.xml"]
    sitemap_found, sitemap_count = False, 0
    for sm_url in candidates[:3]:
        try:
            resp = session.get(sm_url, timeout=timeout)
            if resp.status_code == 200 and b"<" in resp.content[:100]:
                try:
                    root = ET.fromstring(resp.content)
                    locs = [el.text.strip() for el in root.iter()
                            if el.tag.endswith("loc") and el.text]
                    sitemap_found, sitemap_count = True, len(locs)
                    result.add(PASSED, "XML Sitemap",
                               f"Sitemap found at {sm_url} ({len(locs)} URLs"
                               f"{' / child sitemaps' if root.tag.endswith('sitemapindex') else ''}).")
                    break
                except ET.ParseError:
                    result.add(WARNING, "XML Sitemap",
                               f"Sitemap at {sm_url} is not valid XML.",
                               fix="Regenerate the sitemap and validate it.")
                    sitemap_found = True
                    break
        except requests.RequestException:
            continue
    if not sitemap_found:
        result.add(WARNING, "XML Sitemap", "No XML sitemap found.",
                   fix=f"Generate a sitemap.xml, host it at {origin}/sitemap.xml, "
                       f"reference it in robots.txt, and submit it in Google "
                       f"Search Console.")
    result.data["sitemap_count"] = sitemap_count

    # ---------------- Custom 404 ----------------
    try:
        resp = session.get(f"{origin}/seo-audit-404-check-xyz123", timeout=timeout)
        if resp.status_code == 200:
            result.add(WARNING, "Error Handling",
                       "Non-existent URLs return 200 (soft 404s).",
                       fix="Return a real 404 status for missing pages so search "
                           "engines don't index junk URLs.")
        elif resp.status_code == 404:
            result.add(PASSED, "Error Handling", "Missing pages correctly return 404.")
    except requests.RequestException:
        pass

    # ---------------- Per-page technical signals ----------------
    ok_pages = {u: p for u, p in pages.items() if p.ok}
    slow = [(u, p.response_time_ms) for u, p in ok_pages.items()
            if p.response_time_ms > 1500]
    for u, ms in slow[:10]:
        result.add(WARNING, "Page Speed", f"Slow server response: {ms} ms "
                   f"(target < 600 ms TTFB).", u,
                   fix="Enable server caching / a CDN, upgrade hosting, or reduce "
                       "server-side work. Confirm with the PageSpeed tab.")
    if ok_pages and not slow:
        avg = sum(p.response_time_ms for p in ok_pages.values()) // max(len(ok_pages), 1)
        result.add(PASSED, "Page Speed", f"Server response times look good "
                   f"(avg {avg} ms across {len(ok_pages)} pages).")

    sample = next(iter(ok_pages.values()), None)
    if sample:
        headers = {k.lower(): v for k, v in sample.headers.items()}
        if "content-encoding" not in headers:
            result.add(WARNING, "Page Speed", "No compression (gzip/brotli) detected "
                       "on HTML responses.",
                       fix="Enable gzip or brotli compression on the web server/CDN.")
        else:
            result.add(PASSED, "Page Speed",
                       f"Compression enabled ({headers['content-encoding']}).")
        if "strict-transport-security" not in headers and scheme == "https":
            result.add(NOTICE, "Security Headers", "Missing HSTS header.",
                       fix="Add Strict-Transport-Security: max-age=31536000 header.")
        if "cache-control" not in headers:
            result.add(NOTICE, "Page Speed", "No Cache-Control header on pages.",
                       fix="Set sensible Cache-Control headers for HTML and long "
                           "max-age for static assets.")

    noindexed = []
    for u, p in ok_pages.items():
        if p.soup:
            robots_meta = p.soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
            if robots_meta and "noindex" in (robots_meta.get("content") or "").lower():
                noindexed.append(u)
        xr = p.headers.get("X-Robots-Tag", "")
        if "noindex" in xr.lower() and u not in noindexed:
            noindexed.append(u)
    for u in noindexed:
        result.add(WARNING, "Indexability", "Page has a noindex directive.", u,
                   fix="Remove noindex if this page should rank; keep it only for "
                       "pages you deliberately exclude from search.")

    redirect_chain = [u for u, p in pages.items() if p.redirected_from]
    if redirect_chain:
        result.add(NOTICE, "Redirects",
                   f"{len(redirect_chain)} crawled URL(s) reached via redirects.",
                   fix="Update internal links to point directly at final URLs.")

    errors = [(u, p.status_code or p.error) for u, p in pages.items()
              if not p.ok and (p.status_code >= 400 or p.error)]
    for u, status in errors[:10]:
        result.add(CRITICAL, "Crawl Errors", f"Page returned {status}.", u,
                   fix="Fix the page or 301-redirect it to a relevant live URL.")

    return result
