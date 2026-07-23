"""SEO Audit Pro - Windows GUI application.

Run:  python seo_audit_gui.py   (or double-click run_windows.bat)

Full-site SEO auditing with one click:
  - On-page: titles, metas, headings, content, URLs, images, internal links,
    keywords, schema markup, mobile-friendliness
  - Technical: HTTPS, robots.txt, sitemap, AI crawler access (GPTBot,
    ClaudeBot, PerplexityBot...), llms.txt, crawl errors, noindex
  - Off-page: social/brand signals, NAP/local, backlink metrics scoring,
    action plan and one-click research links
  - PageSpeed & Core Web Vitals via Google's API
  - Server log analysis for crawl-budget insight
Reports save to ./audits/<domain>_<timestamp>/ as HTML, JSON, CSV, and a
plain-text audit log, plus ready-to-upload fix files (robots.txt, llms.txt,
schema templates).
"""

import json
import os
import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import quote_plus, urlparse

from seo_audit import APP_NAME, __version__
from seo_audit.audit import AuditRunner
from seo_audit.logfile import analyze_log_file
from seo_audit.report import make_output_dir, save_reports

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
AUDITS_DIR = os.path.join(APP_DIR, "audits")

QUICK_TOOLS = [
    ("Google Search Console", "https://search.google.com/search-console"),
    ("PageSpeed Insights", "https://pagespeed.web.dev/analysis?url={url}"),
    ("Rich Results Test", "https://search.google.com/test/rich-results?url={url}"),
    ("Schema Validator", "https://validator.schema.org/#url={url}"),
    ("Bing Webmaster", "https://www.bing.com/webmasters"),
    ("Google Business Profile", "https://business.google.com/"),
]


class SeoAuditApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"{APP_NAME} v{__version__}")
        root.geometry("980x720")
        root.minsize(860, 620)
        self.msg_queue = queue.Queue()
        self.worker = None
        self.stop_requested = False
        self.last_result = None
        self._build_ui()
        self._load_settings()
        self._poll_queue()

    # ---------------- UI construction ----------------
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass
        style.configure("Run.TButton", font=("Segoe UI", 10, "bold"))

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        # --- Site settings ---
        site = ttk.LabelFrame(outer, text=" 1. Site ", padding=8)
        site.pack(fill="x")
        ttk.Label(site, text="Website URL:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        ttk.Entry(site, textvariable=self.url_var, width=52).grid(
            row=0, column=1, sticky="we", padx=6)
        ttk.Label(site, text="Max pages:").grid(row=0, column=2, sticky="e")
        self.max_pages_var = tk.IntVar(value=30)
        ttk.Spinbox(site, from_=1, to=500, textvariable=self.max_pages_var,
                    width=6).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(site, text="Target keywords (comma-separated):").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        self.keywords_var = tk.StringVar()
        ttk.Entry(site, textvariable=self.keywords_var).grid(
            row=1, column=1, columnspan=3, sticky="we", padx=6, pady=(6, 0))
        ttk.Label(site, text="PageSpeed API key (optional):").grid(
            row=2, column=0, sticky="w", pady=(6, 0))
        self.psi_key_var = tk.StringVar()
        ttk.Entry(site, textvariable=self.psi_key_var, show="*").grid(
            row=2, column=1, columnspan=3, sticky="we", padx=6, pady=(6, 0))
        site.columnconfigure(1, weight=1)

        # --- Off-page inputs ---
        off = ttk.LabelFrame(
            outer, text=" 2. Off-page data (optional - from GSC/Moz/Ahrefs "
                        "free tools) ", padding=8)
        off.pack(fill="x", pady=(8, 0))
        self.brand_var = tk.StringVar()
        self.backlinks_var = tk.StringVar()
        self.refdomains_var = tk.StringVar()
        self.da_var = tk.StringVar()
        self.local_var = tk.BooleanVar(value=False)
        for col, (label, var, width) in enumerate([
                ("Brand name:", self.brand_var, 18),
                ("Backlinks:", self.backlinks_var, 10),
                ("Referring domains:", self.refdomains_var, 10),
                ("Domain Authority:", self.da_var, 6)]):
            ttk.Label(off, text=label).grid(row=0, column=col * 2, sticky="e",
                                            padx=(8 if col else 0, 2))
            ttk.Entry(off, textvariable=var, width=width).grid(
                row=0, column=col * 2 + 1, sticky="w")
        ttk.Checkbutton(off, text="Local business (check citations/NAP)",
                        variable=self.local_var).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        # --- Audit buttons ---
        actions = ttk.LabelFrame(outer, text=" 3. Run audit ", padding=8)
        actions.pack(fill="x", pady=(8, 0))
        self.run_buttons = []
        specs = [
            ("Run FULL Audit", dict(do_onpage=True, do_technical=True,
                                    do_offpage=True, do_pagespeed=True), "Run.TButton"),
            ("On-Page Only", dict(do_onpage=True, do_technical=False,
                                  do_offpage=False, do_pagespeed=False), None),
            ("Technical + AI Only", dict(do_onpage=False, do_technical=True,
                                         do_offpage=False, do_pagespeed=False), None),
            ("Off-Page Only", dict(do_onpage=False, do_technical=False,
                                   do_offpage=True, do_pagespeed=False), None),
            ("PageSpeed / CWV Only", dict(do_onpage=False, do_technical=False,
                                          do_offpage=False, do_pagespeed=True), None),
        ]
        for col, (label, kwargs, style_name) in enumerate(specs):
            btn = ttk.Button(actions, text=label,
                             command=lambda k=kwargs: self.start_audit(**k),
                             **({"style": style_name} if style_name else {}))
            btn.grid(row=0, column=col, padx=4, pady=2, sticky="we")
            self.run_buttons.append(btn)
            actions.columnconfigure(col, weight=1)
        self.stop_btn = ttk.Button(actions, text="Stop", state="disabled",
                                   command=self.request_stop)
        self.stop_btn.grid(row=0, column=len(specs), padx=4)
        row2 = ttk.Frame(actions)
        row2.grid(row=1, column=0, columnspan=len(specs) + 1, sticky="we",
                  pady=(6, 0))
        ttk.Button(row2, text="Analyze Server Log File...",
                   command=self.analyze_log).pack(side="left", padx=(0, 4))
        ttk.Button(row2, text="Open Reports Folder",
                   command=self.open_reports_folder).pack(side="left", padx=4)
        self.open_report_btn = ttk.Button(row2, text="Open Last HTML Report",
                                          state="disabled",
                                          command=self.open_last_report)
        self.open_report_btn.pack(side="left", padx=4)

        # --- Quick tools ---
        tools = ttk.LabelFrame(
            outer, text=" 4. Quick tools (opens in browser, uses the URL above) ",
            padding=8)
        tools.pack(fill="x", pady=(8, 0))
        for col, (label, template) in enumerate(QUICK_TOOLS):
            ttk.Button(tools, text=label,
                       command=lambda t=template: self.open_tool(t)).grid(
                row=col // 3, column=col % 3, padx=4, pady=2, sticky="we")
        ttk.Button(tools, text="Brand Mentions Search",
                   command=self.open_brand_mentions).grid(
            row=2, column=0, padx=4, pady=2, sticky="we")
        ttk.Button(tools, text="Moz Link Explorer (free DA)",
                   command=lambda: self.open_tool(
                       "https://moz.com/link-explorer?site={domain}")).grid(
            row=2, column=1, padx=4, pady=2, sticky="we")
        ttk.Button(tools, text="Ahrefs Free Backlink Checker",
                   command=lambda: self.open_tool(
                       "https://ahrefs.com/backlink-checker?target={domain}")).grid(
            row=2, column=2, padx=4, pady=2, sticky="we")
        for col in range(3):
            tools.columnconfigure(col, weight=1)

        # --- Progress / log ---
        progress = ttk.LabelFrame(outer, text=" Audit progress ", padding=8)
        progress.pack(fill="both", expand=True, pady=(8, 0))
        self.progress_bar = ttk.Progressbar(progress, mode="indeterminate")
        self.progress_bar.pack(fill="x")
        text_frame = ttk.Frame(progress)
        text_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.log_text = tk.Text(text_frame, height=12, wrap="word",
                                state="disabled", font=("Consolas", 9),
                                background="#0b2545", foreground="#d7e3f4")
        scroll = ttk.Scrollbar(text_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.status_var = tk.StringVar(value="Ready. Enter a URL and click "
                                             "'Run FULL Audit'.")
        ttk.Label(outer, textvariable=self.status_var, anchor="w").pack(
            fill="x", pady=(6, 0))

    # ---------------- Settings persistence ----------------
    def _load_settings(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
                s = json.load(fh)
            self.url_var.set(s.get("url", ""))
            self.keywords_var.set(s.get("keywords", ""))
            self.psi_key_var.set(s.get("psi_api_key", ""))
            self.max_pages_var.set(s.get("max_pages", 30))
            self.brand_var.set(s.get("brand", ""))
            self.backlinks_var.set(s.get("backlinks", ""))
            self.refdomains_var.set(s.get("referring_domains", ""))
            self.da_var.set(s.get("domain_authority", ""))
            self.local_var.set(s.get("is_local", False))
        except (OSError, json.JSONDecodeError):
            pass

    def _save_settings(self):
        s = {
            "url": self.url_var.get(),
            "keywords": self.keywords_var.get(),
            "psi_api_key": self.psi_key_var.get(),
            "max_pages": self.max_pages_var.get(),
            "brand": self.brand_var.get(),
            "backlinks": self.backlinks_var.get(),
            "referring_domains": self.refdomains_var.get(),
            "domain_authority": self.da_var.get(),
            "is_local": self.local_var.get(),
        }
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
                json.dump(s, fh, indent=2)
        except OSError:
            pass

    # ---------------- Helpers ----------------
    def _get_url(self, required=True):
        url = self.url_var.get().strip()
        if not url and required:
            messagebox.showwarning(APP_NAME, "Please enter a website URL first.")
            return None
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def log(self, msg):
        self.msg_queue.put(("log", msg))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", payload + "\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "done":
                    self._on_audit_done(payload)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _set_running(self, running: bool):
        state = "disabled" if running else "normal"
        for btn in self.run_buttons:
            btn.configure(state=state)
        self.stop_btn.configure(state="normal" if running else "disabled")
        if running:
            self.progress_bar.start(12)
        else:
            self.progress_bar.stop()

    # ---------------- Audit execution ----------------
    def start_audit(self, **section_flags):
        url = self._get_url()
        if not url:
            return
        if self.worker and self.worker.is_alive():
            return
        self._save_settings()
        self.stop_requested = False
        self._set_running(True)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.msg_queue.put(("status", f"Auditing {url} ..."))

        keywords = [k for k in self.keywords_var.get().split(",") if k.strip()]
        manual = {
            "brand_name": self.brand_var.get().strip(),
            "backlinks": self.backlinks_var.get().strip(),
            "referring_domains": self.refdomains_var.get().strip(),
            "domain_authority": self.da_var.get().strip(),
            "is_local_business": self.local_var.get(),
        }
        runner = AuditRunner(
            url, max_pages=self.max_pages_var.get(), keywords=keywords,
            psi_api_key=self.psi_key_var.get().strip(), offpage_manual=manual,
            output_base=AUDITS_DIR, log=self.log,
            stop_flag=lambda: self.stop_requested)

        def work():
            try:
                result = runner.run(**section_flags)
                self.msg_queue.put(("done", result))
            except Exception as exc:  # surface anything to the user
                self.log(f"\nERROR: {exc}")
                self.msg_queue.put(("done", None))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _on_audit_done(self, result):
        self._set_running(False)
        if result:
            self.last_result = result
            self.open_report_btn.configure(state="normal")
            self.msg_queue.put(
                ("status", f"Audit complete - overall score "
                           f"{result['overall']}/100. Reports in "
                           f"{result['output_dir']}"))
            if messagebox.askyesno(
                    APP_NAME, f"Audit complete!\n\nOverall score: "
                              f"{result['overall']}/100\n\nOpen the HTML report now?"):
                self.open_last_report()
        else:
            self.msg_queue.put(("status", "Audit failed or was stopped - "
                                          "see the log above."))

    def request_stop(self):
        self.stop_requested = True
        self.log("Stop requested - finishing current step...")

    # ---------------- Log file analysis ----------------
    def analyze_log(self):
        path = filedialog.askopenfilename(
            title="Choose a server access log file",
            filetypes=[("Log files", "*.log *.txt *.gz2 *.access"),
                       ("All files", "*.*")])
        if not path:
            return
        url = self._get_url(required=False) or "logfile-analysis"
        self._set_running(True)
        self.msg_queue.put(("status", f"Analyzing log {os.path.basename(path)}..."))

        def work():
            try:
                self.log(f"Analyzing {path} ...")
                section = analyze_log_file(path, log=self.log)
                out = make_output_dir(AUDITS_DIR, url)
                paths = save_reports(out, url, [section],
                                     [f"Log file analyzed: {path}"],
                                     meta={"log_file": path})
                self.log(f"Report saved: {paths['html']}")
                self.msg_queue.put(("done", {
                    "sections": [section], "paths": paths,
                    "output_dir": out, "overall": section.score}))
            except Exception as exc:
                self.log(f"\nERROR: {exc}")
                self.msg_queue.put(("done", None))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    # ---------------- Browser / folder helpers ----------------
    def open_tool(self, template: str):
        url = self._get_url(required="{url}" in template or
                            "{domain}" in template)
        if ("{url}" in template or "{domain}" in template) and not url:
            return
        target = template
        if url:
            domain = urlparse(url).netloc
            target = template.replace("{url}", quote_plus(url)) \
                             .replace("{domain}", quote_plus(domain))
        webbrowser.open(target)

    def open_brand_mentions(self):
        url = self._get_url()
        if not url:
            return
        domain = urlparse(url).netloc.removeprefix("www.")
        brand = self.brand_var.get().strip() or domain.split(".")[0]
        q = quote_plus(f'"{brand}" -site:{domain}')
        webbrowser.open(f"https://www.google.com/search?q={q}")

    def open_reports_folder(self):
        os.makedirs(AUDITS_DIR, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(AUDITS_DIR)  # noqa: attribute exists on Windows
        else:
            webbrowser.open("file://" + AUDITS_DIR)

    def open_last_report(self):
        if self.last_result:
            webbrowser.open("file://" +
                            os.path.abspath(self.last_result["paths"]["html"]))

    def on_close(self):
        self._save_settings()
        self.stop_requested = True
        self.root.destroy()


def main():
    root = tk.Tk()
    app = SeoAuditApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
