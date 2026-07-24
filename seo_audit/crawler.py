"""Site crawler: discovers and fetches pages within one domain.

Respects robots.txt for our own user agent, stays on the start domain,
and collects everything the checkers need (HTML, headers, timing, links).
"""

import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

USER_AGENT = "SEOAuditPro/1.0 (+site audit tool)"

# File extensions we never treat as crawlable pages
SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico",
    ".css", ".js", ".json", ".xml", ".pdf", ".zip", ".gz", ".rar",
    ".mp3", ".mp4", ".webm", ".avi", ".mov", ".woff", ".woff2", ".ttf",
    ".eot", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".exe",
)


@dataclass
class PageData:
    """Everything captured about a single crawled page."""
    url: str
    status_code: int = 0
    ok: bool = False
    error: str = ""
    html: str = ""
    soup: BeautifulSoup = None
    headers: dict = field(default_factory=dict)
    response_time_ms: int = 0
    content_length: int = 0
    redirected_from: str = ""
    final_url: str = ""
    internal_links: list = field(default_factory=list)   # (href, anchor_text)
    external_links: list = field(default_factory=list)   # (href, anchor_text)
    depth: int = 0


def normalize_url(url: str) -> str:
    """Strip fragments and trailing slashes (except root) for dedup."""
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def same_domain(url: str, root_netloc: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    root = root_netloc.lower()
    return netloc == root or netloc == f"www.{root}" or f"www.{netloc}" == root


def _sitemap_locs(xml_text: str) -> list:
    """Pull <loc> values out of sitemap XML without a parser dependency."""
    return [m.strip() for m in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml_text)]


def registrable_domain(netloc: str) -> str:
    """Naive registrable domain: strip "www." and keep the last two labels.

    Good enough for .com/.net/etc without a public-suffix dependency.
    """
    host = netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


class SiteCrawler:
    def __init__(self, start_url: str, max_pages: int = 50, delay: float = 0.3,
                 timeout: int = 15, log=None, stop_flag=None,
                 include_subdomains: bool = False,
                 seed_from_sitemap: bool = False):
        if not start_url.startswith(("http://", "https://")):
            start_url = "https://" + start_url
        self.start_url = start_url
        self.root_netloc = urlparse(start_url).netloc
        self.include_subdomains = include_subdomains
        self.seed_from_sitemap = seed_from_sitemap
        self.root_domain = registrable_domain(self.root_netloc)
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.log = log or (lambda msg: None)
        self.stop_flag = stop_flag or (lambda: False)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.pages: dict[str, PageData] = {}
        self.broken_links: dict[str, list] = {}  # broken url -> [pages linking to it]
        self.robots_sitemaps: list = []  # sitemap URLs found in robots.txt
        # Per-host robots.txt parsers. A crawl can span hosts (apex <-> www
        # redirects, or sibling subdomains when include_subdomains is set), and
        # each host has its own robots.txt - so fetch and cache one per host
        # rather than applying the start host's rules everywhere.
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.robots = self._load_robots(
            f"{urlparse(self.start_url).scheme}://{self.root_netloc}",
            collect_sitemaps=True)

    def _load_robots(self, origin, collect_sitemaps=False):
        """Fetch + parse robots.txt for one origin (scheme://host). Cached by
        host. `collect_sitemaps` records Sitemap: lines into robots_sitemaps."""
        host = urlparse(origin).netloc.lower()
        if host in self._robots_cache:
            return self._robots_cache[host]
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = self.session.get(f"{origin}/robots.txt", timeout=self.timeout)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                if collect_sitemaps:
                    for line in resp.text.splitlines():
                        if line.lower().startswith("sitemap:"):
                            self.robots_sitemaps.append(line.split(":", 1)[1].strip())
            else:
                rp.parse([])
        except requests.RequestException:
            rp.parse([])
        self._robots_cache[host] = rp
        return rp

    def _is_internal(self, url: str) -> bool:
        """Same-domain check, optionally accepting sibling subdomains."""
        if self.include_subdomains:
            return registrable_domain(urlparse(url).netloc) == self.root_domain
        return same_domain(url, self.root_netloc)

    def _allowed(self, url: str) -> bool:
        """Check robots.txt for the URL's OWN host (lazily fetched + cached),
        not the host the crawl happened to start from."""
        try:
            parsed = urlparse(url)
            rp = self._load_robots(f"{parsed.scheme}://{parsed.netloc}")
            return rp.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def fetch_page(self, url: str, depth: int = 0) -> PageData:
        page = PageData(url=url, depth=depth)
        try:
            start = time.time()
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            page.response_time_ms = int((time.time() - start) * 1000)
            page.status_code = resp.status_code
            page.headers = dict(resp.headers)
            page.final_url = resp.url
            if resp.history:
                page.redirected_from = url
            content_type = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and "text/html" in content_type:
                page.ok = True
                page.html = resp.text
                page.content_length = len(resp.content)
                page.soup = BeautifulSoup(resp.text, "html.parser")
                self._extract_links(page)
        except requests.RequestException as exc:
            page.error = str(exc)
        return page

    def _extract_links(self, page: PageData):
        base = page.final_url or page.url
        for a in page.soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urljoin(base, href)
            if not absolute.startswith(("http://", "https://")):
                continue
            anchor = a.get_text(strip=True) or a.find("img", alt=True) and a.find("img")["alt"] or ""
            if self._is_internal(absolute):
                page.internal_links.append((normalize_url(absolute), anchor))
            else:
                page.external_links.append((absolute, anchor))

    def _seed_from_sitemap(self, queue, seen):
        """Enqueue URLs from the site's sitemap(s). Never fatal."""
        try:
            sitemaps = list(self.robots_sitemaps) or [
                f"{urlparse(self.start_url).scheme}://{self.root_netloc}/sitemap.xml"]
            locs = []
            fetched_children = 0
            for sitemap_url in sitemaps:
                text = self._fetch_sitemap(sitemap_url)
                if text is None:
                    continue
                if "<sitemapindex" in text:
                    # Sitemap index: follow child sitemaps one level deep.
                    for child in _sitemap_locs(text):
                        if fetched_children >= 5:
                            break
                        fetched_children += 1
                        child_text = self._fetch_sitemap(child)
                        if child_text is not None:
                            locs.extend(_sitemap_locs(child_text))
                else:
                    locs.extend(_sitemap_locs(text))
            added = 0
            for loc in locs:
                if not loc.startswith(("http://", "https://")):
                    continue
                if not self._is_internal(loc):
                    continue
                url = normalize_url(loc)
                if url in seen:
                    continue
                seen.add(url)
                queue.append((url, 1))
                added += 1
                if len(seen) >= self.max_pages * 2:
                    break
            if added:
                self.log(f"  Seeded {added} URL(s) from sitemap.")
        except Exception as exc:
            self.log(f"  Sitemap seeding skipped: {exc}")

    def _fetch_sitemap(self, url: str):
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            pass
        return None

    def crawl(self) -> dict:
        """Breadth-first crawl from the start URL. Returns {url: PageData}."""
        queue = [(normalize_url(self.start_url), 0)]
        seen = {queue[0][0]}
        if self.seed_from_sitemap:
            self._seed_from_sitemap(queue, seen)
        while queue and len(self.pages) < self.max_pages:
            if self.stop_flag():
                self.log("Crawl stopped by user.")
                break
            url, depth = queue.pop(0)
            path = urlparse(url).path.lower()
            if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue
            if not self._allowed(url):
                self.log(f"  Skipped (robots.txt): {url}")
                continue
            self.log(f"  Crawling [{len(self.pages) + 1}/{self.max_pages}]: {url}")
            page = self.fetch_page(url, depth)
            self.pages[url] = page
            if page.status_code >= 400 or page.error:
                continue
            for link, _anchor in page.internal_links:
                if link not in seen and self._is_internal(link):
                    seen.add(link)
                    queue.append((link, depth + 1))
            if self.delay:
                time.sleep(self.delay)
        return self.pages

    def check_broken_links(self, log=None):
        """HEAD-check every internal link found during the crawl."""
        log = log or self.log
        link_sources: dict[str, set] = {}
        for url, page in self.pages.items():
            for link, _anchor in page.internal_links:
                link_sources.setdefault(link, set()).add(url)
        checked: dict[str, int] = {}
        for url in self.pages:
            checked[url] = self.pages[url].status_code
        to_check = [l for l in link_sources if l not in checked]
        log(f"  Verifying {len(to_check)} uncrawled internal links...")
        for link in to_check:
            if self.stop_flag():
                break
            try:
                resp = self.session.head(link, timeout=self.timeout, allow_redirects=True)
                status = resp.status_code
                if status == 405:  # server rejects HEAD, retry with GET
                    resp = self.session.get(link, timeout=self.timeout, stream=True)
                    status = resp.status_code
                    resp.close()
                checked[link] = status
            except requests.RequestException:
                checked[link] = 0
        for link, status in checked.items():
            if (status >= 400 or status == 0) and link in link_sources:
                self.broken_links[link] = sorted(link_sources[link])
        return self.broken_links
