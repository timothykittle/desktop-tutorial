"""Site crawler: discovers and fetches pages within one domain.

Respects robots.txt for our own user agent, stays on the start domain,
and collects everything the checkers need (HTML, headers, timing, links).
"""

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


class SiteCrawler:
    def __init__(self, start_url: str, max_pages: int = 50, delay: float = 0.3,
                 timeout: int = 15, log=None, stop_flag=None):
        if not start_url.startswith(("http://", "https://")):
            start_url = "https://" + start_url
        self.start_url = start_url
        self.root_netloc = urlparse(start_url).netloc
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
        self.robots = self._load_robots()

    def _load_robots(self):
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{urlparse(self.start_url).scheme}://{self.root_netloc}/robots.txt"
        try:
            resp = self.session.get(robots_url, timeout=self.timeout)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp.parse([])
        except requests.RequestException:
            rp.parse([])
        return rp

    def _allowed(self, url: str) -> bool:
        try:
            return self.robots.can_fetch(USER_AGENT, url)
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
            if same_domain(absolute, self.root_netloc):
                page.internal_links.append((normalize_url(absolute), anchor))
            else:
                page.external_links.append((absolute, anchor))

    def crawl(self) -> dict:
        """Breadth-first crawl from the start URL. Returns {url: PageData}."""
        queue = [(normalize_url(self.start_url), 0)]
        seen = {queue[0][0]}
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
                if link not in seen:
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
