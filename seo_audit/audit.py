"""Audit orchestrator - runs the selected sections and saves all outputs.
Used by both the GUI and the CLI."""

import os
from urllib.parse import urlparse

from .crawler import SiteCrawler
from .onpage import run_onpage_audit
from .technical import run_technical_audit
from .offpage import run_offpage_audit
from .pagespeed import run_pagespeed_audit
from . import fixes as fixgen
from .report import make_output_dir, save_reports


class AuditRunner:
    def __init__(self, url: str, max_pages: int = 30, keywords: list = None,
                 psi_api_key: str = "", offpage_manual: dict = None,
                 output_base: str = "audits", log=None, stop_flag=None):
        self.url = url if url.startswith(("http://", "https://")) else "https://" + url
        self.max_pages = max_pages
        self.keywords = [k.strip() for k in (keywords or []) if k.strip()]
        self.psi_api_key = psi_api_key
        self.offpage_manual = offpage_manual or {}
        self.output_base = output_base
        self.log_lines = []
        self._log_cb = log or (lambda m: None)
        self.stop_flag = stop_flag or (lambda: False)

    def log(self, msg: str):
        self.log_lines.append(msg)
        self._log_cb(msg)

    def run(self, do_onpage=True, do_technical=True, do_offpage=True,
            do_pagespeed=True) -> dict:
        """Runs the audit. Returns {'sections': [...], 'paths': {...},
        'output_dir': str, 'overall': int}."""
        sections = []
        self.log(f"Starting audit of {self.url}")
        self.log(f"Sections: "
                 f"{'on-page ' if do_onpage else ''}"
                 f"{'technical ' if do_technical else ''}"
                 f"{'off-page ' if do_offpage else ''}"
                 f"{'pagespeed' if do_pagespeed else ''}".strip())

        # ---- crawl (needed by on-page, technical, off-page) ----
        crawler = None
        pages, broken = {}, {}
        if do_onpage or do_technical or do_offpage:
            self.log(f"\n[1/5] Crawling site (up to {self.max_pages} pages)...")
            crawler = SiteCrawler(self.url, max_pages=self.max_pages,
                                  log=self.log, stop_flag=self.stop_flag)
            pages = crawler.crawl()
            self.log(f"  Crawled {len(pages)} pages.")
            if do_onpage:
                self.log("\n[2/5] Checking broken internal links...")
                broken = crawler.check_broken_links()
                self.log(f"  Found {len(broken)} broken link target(s).")

        if do_onpage and not self.stop_flag():
            self.log("\n[3/5] Running on-page checks (titles, metas, headings, "
                     "content, images, links, schema, keywords)...")
            sections.append(run_onpage_audit(pages, broken, self.keywords,
                                             log=self.log))
        if do_technical and not self.stop_flag():
            self.log("\n[4/5] Running technical + AI-readiness checks...")
            sections.append(run_technical_audit(
                self.url, pages,
                session=crawler.session if crawler else None, log=self.log))
        if do_offpage and not self.stop_flag():
            self.log("\n[5/5] Running off-page analysis...")
            sections.append(run_offpage_audit(self.url, pages,
                                              manual=self.offpage_manual,
                                              log=self.log))
        if do_pagespeed and not self.stop_flag():
            self.log("\n[PSI] Fetching PageSpeed & Core Web Vitals from Google...")
            sections.append(run_pagespeed_audit(self.url, self.psi_api_key,
                                                log=self.log))

        # ---- outputs ----
        output_dir = make_output_dir(self.output_base, self.url)
        self.log(f"\nSaving reports to {os.path.abspath(output_dir)}")

        socials, key_pages = {}, []
        for s in sections:
            socials = s.data.get("social_profiles") or socials
            for p in s.data.get("pages", []):
                key_pages.append((p["url"], p.get("title", "")))
        brand = (self.offpage_manual.get("brand_name")
                 or urlparse(self.url).netloc.removeprefix("www.").split(".")[0].title())
        fixgen.write_fix_files(output_dir, self.url, brand, socials=socials,
                               key_pages=key_pages,
                               is_local=bool(self.offpage_manual.get("is_local_business")))
        self.log("  Wrote fix templates (robots.txt, llms.txt, schema) to /fixes")

        paths = save_reports(output_dir, self.url, sections, self.log_lines,
                             meta={"max_pages": self.max_pages,
                                   "keywords": self.keywords})
        overall = round(sum(s.score for s in sections) / max(len(sections), 1))
        self.log(f"\nDone. Overall score: {overall}/100")
        for kind, path in paths.items():
            self.log(f"  {kind.upper():5s} -> {path}")
        return {"sections": sections, "paths": paths,
                "output_dir": output_dir, "overall": overall}
