"""Local site loader: turns an uploaded/local website folder (or single
HTML file, or a list of files) into the same {url: PageData} structure
the crawler produces, so the audit engine can run without a live site.

Relative links between local files are resolved onto the mapped URLs so
inbound-link / orphan logic works, and hrefs pointing at files that do
not exist in the loaded set are reported as broken local links.
"""

import os
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .crawler import PageData, normalize_url, same_domain

DEFAULT_BASE = "https://local.site"

HTML_EXTENSIONS = (".html", ".htm")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif",
                    ".svg", ".ico", ".bmp")
INDEX_NAMES = ("index.html", "index.htm")


def _collect_files(path):
    """Resolve `path` (dir, file, or list of either) to (root, [abs files])."""
    items = path if isinstance(path, (list, tuple)) else [path]
    files = []
    roots = []
    for item in items:
        item = os.path.abspath(str(item))
        if os.path.isdir(item):
            roots.append(item)
            for dirpath, _dirnames, names in os.walk(item):
                files.extend(os.path.join(dirpath, n) for n in names)
        elif os.path.isfile(item):
            roots.append(os.path.dirname(item))
            files.append(item)
    root = os.path.commonpath(roots) if roots else os.getcwd()
    return root, sorted(set(files))


def _inventory_bucket(rel_path: str) -> str:
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in HTML_EXTENSIONS:
        return "html_files"
    if ext == ".css":
        return "css"
    if ext == ".js":
        return "js"
    if ext in IMAGE_EXTENSIONS:
        return "images"
    if ext == ".csv":
        return "csv"
    if ext == ".md":
        return "md"
    if ext == ".txt":
        return "txt"
    return "other"


def _map_url(rel_path: str, base: str) -> str:
    """Map a relative file path onto the base URL.

    folder/index.html -> base/folder, page.html -> base/page.html.
    """
    parts = rel_path.split("/")
    if parts[-1].lower() in INDEX_NAMES:
        parts = parts[:-1]
    return normalize_url(base + "/" + "/".join(parts))


def load_local_site(path, base_url="") -> tuple:
    """Load a local website folder / file(s) into audit-ready structures.

    `path` may be a directory (walked recursively for .html/.htm files),
    a single HTML file, or a list of paths (mixed types allowed).
    If `base_url` is given (e.g. "https://example.com"), file paths are
    mapped onto it; otherwise a synthetic base "https://local.site" is used.

    Returns (pages, inventory): `pages` is {url: PageData} exactly like
    SiteCrawler.crawl() produces, and `inventory` describes every file
    found plus any broken local links
    ({"broken_local_links": {target_url: [source_urls...]}}).
    """
    root, files = _collect_files(path)

    base = base_url.strip().rstrip("/") if base_url else DEFAULT_BASE
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    base_netloc = urlparse(base).netloc

    inventory = {"html_files": 0, "css": 0, "js": 0, "images": 0,
                 "csv": 0, "md": 0, "txt": 0, "other": 0,
                 "broken_local_links": {}, "root": str(path)
                 if not isinstance(path, (list, tuple)) else root,
                 "files": []}

    rel_paths = {}   # abs path -> relative posix path
    known_urls = set()
    for abs_path in files:
        rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
        rel_paths[abs_path] = rel
        inventory["files"].append(rel)
        inventory[_inventory_bucket(rel)] += 1
        # Every file is addressable at its literal path and (for index
        # files) at its containing folder's URL.
        known_urls.add(_map_url(rel, base))
        known_urls.add(normalize_url(base + "/" + rel))

    pages: dict = {}
    broken: dict = {}  # broken url -> set of pages linking to it

    for abs_path in files:
        rel = rel_paths[abs_path]
        if not rel.lower().endswith(HTML_EXTENSIONS):
            continue
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        url = _map_url(rel, base)
        page = PageData(url=url, status_code=200, ok=True, html=html,
                        final_url=url, depth=rel.count("/"),
                        response_time_ms=0, content_length=len(html))
        page.soup = BeautifulSoup(html, "html.parser")

        # Resolve links against the file's real location so relative
        # hrefs between local files land on the right mapped URLs.
        join_base = base + "/" + rel
        for a in page.soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urljoin(join_base, href)
            if not absolute.startswith(("http://", "https://")):
                continue
            anchor = a.get_text(strip=True) or a.find("img", alt=True) and a.find("img")["alt"] or ""
            if same_domain(absolute, base_netloc):
                link = normalize_url(absolute)
                page.internal_links.append((link, anchor))
                if link not in known_urls:
                    broken.setdefault(link, set()).add(url)
            else:
                page.external_links.append((absolute, anchor))
        pages[url] = page

    inventory["broken_local_links"] = {u: sorted(srcs)
                                       for u, srcs in broken.items()}
    return pages, inventory
