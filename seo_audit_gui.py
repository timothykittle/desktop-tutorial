"""SEO Audit Pro - Windows GUI application (v2).

Audits ANY website - a competitor, a client, or your own - by URL (SEO checks
read only public pages), or a local folder / uploaded files for offline audit
and repair. The business details entered in the assistant describe whichever
site is loaded, so generated content is written for that site's business.

Run:  python seo_audit_gui.py   (or double-click run_windows.bat)
Build a standalone .exe:  python build_exe.py

This file is the desktop front end only; all analysis lives in the `seo_audit`
package (see its __init__ for a per-module map). The GUI's job is to collect a
source, run the package's functions on a background thread, and show/save the
results - it deliberately contains no SEO logic of its own.

Layout:
  LEFT  - source (enter a URL, or drag-and-drop / browse a website folder or
          files), an AI assistant chat that interviews you and builds pages,
          and a live audit/progress log.
  RIGHT - a vertical stack of square action buttons: Google Search Console,
          Crawl, robots.txt, llms.txt, then one button per on-page and
          off-page check, a COMPLETE AUDIT button, and the site/location
          builders.

Everything saves to ./audits/ (reports) and ./site_package/ (repaired files,
location pages, robots.txt/llms.txt/schema ready to upload for SEO/AEO/GEO).
"""

import json
import os
import queue
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from urllib.parse import quote_plus, urlparse

# Optional drag-and-drop support
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND = True
except Exception:
    _DND = False

from seo_audit import APP_NAME, __version__
from seo_audit.audit import AuditRunner
from seo_audit.logfile import analyze_log_file
from seo_audit.report import make_output_dir, save_reports

# New v2 modules (built alongside this GUI)
from seo_audit.localsite import load_local_site
from seo_audit.diagnostics import run_diagnostics
from seo_audit.verify import build_and_verify, render_split_html, split_results
from seo_audit.backup import make_backup
from seo_audit import gitsource
from seo_audit import prompts as promptsmod
from seo_audit import content as contentmod
from seo_audit import repair as repairmod
from seo_audit import locations as locmod

# Security module is optional (may not be installed in older copies)
try:
    from seo_audit import security as secmod
    _SEC = True
except Exception:
    _SEC = False
from seo_audit.assistant import (
    AssistantEngine, generate_faq_page, generate_blog_plan,
    generate_gbp_guide, generate_ai_integration_guide,
    generate_outreach_templates,
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
PROFILE_PATH = os.path.join(APP_DIR, "business_profile.json")

# Output folders live under a configurable save root (default: the app folder).
# set_save_root() re-points all three when the user picks a location.
SAVE_ROOT = APP_DIR
AUDITS_DIR = os.path.join(SAVE_ROOT, "audits")
PACKAGE_DIR = os.path.join(SAVE_ROOT, "site_package")
BACKUP_DIR = os.path.join(SAVE_ROOT, "backups")


def set_save_root(root):
    """Re-point audits/site_package/backups at a new base folder."""
    global SAVE_ROOT, AUDITS_DIR, PACKAGE_DIR, BACKUP_DIR
    SAVE_ROOT = root
    AUDITS_DIR = os.path.join(root, "audits")
    PACKAGE_DIR = os.path.join(root, "site_package")
    BACKUP_DIR = os.path.join(root, "backups")

# Palette
NAVY = "#0b2545"
NAVY2 = "#13315c"
ACCENT = "#2a9d8f"
LIGHT = "#e8eef6"


class SeoAuditApp:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} v{__version__}")
        root.geometry("1180x820")
        root.minsize(1000, 680)
        self.msg_queue = queue.Queue()
        self.worker = None
        self.stop_requested = False
        self.last_result = None
        self.last_error = ""

        # Source state: a URL, a loaded local upload, or a cloned GitHub repo.
        self.source_mode = tk.StringVar(value="url")   # "url" | "local"
        self.local_paths = []          # uploaded files/folder (in-memory session)
        self.local_pages = None        # loaded PageData dict (discarded each session)
        self.local_broken = {}
        self.local_inventory = {}
        self.source_root_paths = []    # original folder/files to back up
        self.clone_dir = ""            # temp GitHub clone, cleaned on new session

        self.assistant = AssistantEngine(PROFILE_PATH)
        self._build_ui()
        self._load_settings()
        self._poll_queue()
        self._assistant_say(self.assistant.start())
        # Capture uncaught main-thread callback errors for the Debug panel
        root.report_callback_exception = self._tk_error

    def _tk_error(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        self.last_error = text
        self.log(f"\nUI ERROR: {val}")
        if self._verbose():
            self.log(text)
        try:
            messagebox.showerror(
                APP_NAME, f"Something went wrong:\n{val}\n\n"
                          "Click 'Copy last error' in the Debug section for details.")
        except Exception:
            pass

    # ==================================================================
    # UI construction
    # ==================================================================
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass
        style.configure("Sq.TButton", font=("Segoe UI", 9, "bold"), padding=6)
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=10)
        style.configure("Head.TLabel", font=("Segoe UI", 11, "bold"))

        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        # ---- LEFT column (source + assistant + log) ----
        left = ttk.Frame(outer)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(2, weight=1)
        left.rowconfigure(3, weight=1)
        left.columnconfigure(0, weight=1)

        self._build_source(left)
        self._build_assistant(left)
        self._build_log(left)

        # ---- RIGHT column (action buttons) ----
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="ns")
        self._build_actions(right)

        # ---- status bar ----
        self.status_var = tk.StringVar(value="Ready. Enter a URL or upload a "
                                             "website folder, then run an audit.")
        ttk.Label(outer, textvariable=self.status_var, anchor="w",
                  relief="sunken", padding=4).grid(row=1, column=0, columnspan=2,
                                                   sticky="ew", pady=(6, 0))
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    def _build_source(self, parent):
        box = ttk.LabelFrame(parent, text=" 1. Source ", padding=8)
        box.grid(row=0, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)

        ttk.Radiobutton(box, text="Audit a live URL:", value="url",
                        variable=self.source_mode,
                        command=self._sync_source).grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.url_var).grid(row=0, column=1,
                                                       columnspan=2, sticky="ew", padx=6)
        opts = ttk.Frame(box)
        opts.grid(row=1, column=1, columnspan=2, sticky="w", padx=6)
        self.subdomains_var = tk.BooleanVar(value=False)
        self.sitemap_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Include subdomains",
                        variable=self.subdomains_var).pack(side="left")
        ttk.Checkbutton(opts, text="Seed from sitemap",
                        variable=self.sitemap_var).pack(side="left", padx=(10, 0))
        ttk.Label(opts, text="Max pages:").pack(side="left", padx=(10, 2))
        self.max_pages_var = tk.IntVar(value=40)
        ttk.Spinbox(opts, from_=1, to=1000, width=6,
                    textvariable=self.max_pages_var).pack(side="left")

        ttk.Radiobutton(box, text="Or upload a website (folder or files):",
                        value="local", variable=self.source_mode,
                        command=self._sync_source).grid(row=2, column=0,
                                                        columnspan=3, sticky="w",
                                                        pady=(8, 2))
        # Drop zone
        self.drop = tk.Label(
            box, text=("⬇  Drag a website folder or files here\n"
                       "(HTML, CSS, JS, MD, CSV, TXT, images)\n"
                       "or use the buttons below"),
            relief="ridge", borderwidth=2, height=4, background="#f4f7fb",
            foreground="#5a6b82", font=("Segoe UI", 9))
        self.drop.grid(row=3, column=0, columnspan=3, sticky="ew", pady=2)
        if _DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self._on_drop)
        btns = ttk.Frame(box)
        btns.grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Button(btns, text="Choose Folder…",
                   command=self._pick_folder).pack(side="left")
        ttk.Button(btns, text="Choose Files…",
                   command=self._pick_files).pack(side="left", padx=4)
        ttk.Button(btns, text="New session (clear)",
                   command=self.act_new_session).pack(side="left", padx=4)

        # GitHub source
        gh = ttk.Frame(box)
        gh.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        gh.columnconfigure(1, weight=1)
        ttk.Label(gh, text="Or load from GitHub:").grid(row=0, column=0, sticky="w")
        self.gh_url_var = tk.StringVar()
        ttk.Entry(gh, textvariable=self.gh_url_var).grid(row=0, column=1,
                                                         sticky="ew", padx=4)
        ttk.Button(gh, text="Clone & load",
                   command=self.act_load_github).grid(row=0, column=2)
        ttk.Label(gh, text="Token (private repos, optional):").grid(
            row=1, column=0, sticky="w", pady=(2, 0))
        self.gh_token_var = tk.StringVar()
        ttk.Entry(gh, textvariable=self.gh_token_var, show="*").grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=(2, 0))

        ttk.Label(box, text="Site's public base URL (recommended for uploads):").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.base_url_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.base_url_var, width=28).grid(
            row=6, column=2, sticky="ew", padx=6, pady=(6, 0))

        # Save location
        save = ttk.Frame(box)
        save.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        save.columnconfigure(1, weight=1)
        ttk.Label(save, text="Save results to:").grid(row=0, column=0, sticky="w")
        self.save_root_var = tk.StringVar(value=SAVE_ROOT)
        ttk.Entry(save, textvariable=self.save_root_var).grid(
            row=0, column=1, sticky="ew", padx=4)
        ttk.Button(save, text="Browse…",
                   command=self._pick_save_root).grid(row=0, column=2)

        self.source_summary = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.source_summary, foreground=ACCENT,
                  font=("Segoe UI", 8)).grid(row=8, column=0, columnspan=3, sticky="w")

        # keywords
        ttk.Label(box, text="Target keywords (comma-separated):").grid(
            row=9, column=0, sticky="w", pady=(6, 0))
        self.keywords_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.keywords_var).grid(
            row=9, column=1, columnspan=2, sticky="ew", padx=6, pady=(6, 0))

    def _build_assistant(self, parent):
        box = ttk.LabelFrame(parent, text=" 2. AI Assistant (interviews you & "
                                          "builds pages) ", padding=6)
        box.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        self.chat = tk.Text(box, height=9, wrap="word", state="disabled",
                            font=("Segoe UI", 9), background="#ffffff")
        self.chat.grid(row=0, column=0, columnspan=2, sticky="nsew")
        sc = ttk.Scrollbar(box, command=self.chat.yview)
        sc.grid(row=0, column=2, sticky="ns")
        self.chat.configure(yscrollcommand=sc.set)
        self.chat.tag_configure("bot", foreground=NAVY, font=("Segoe UI", 9, "bold"))
        self.chat.tag_configure("me", foreground="#333333")
        self.chat.tag_configure("act", foreground=ACCENT, font=("Segoe UI", 9, "italic"))
        self.chat_in = tk.StringVar()
        entry = ttk.Entry(box, textvariable=self.chat_in)
        entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        entry.bind("<Return>", lambda e: self._assistant_send())
        ttk.Button(box, text="Send", command=self._assistant_send).grid(
            row=1, column=1, padx=4, pady=(4, 0))
        self.pending_action = None
        self.action_btn = ttk.Button(box, text="", command=self._run_pending_action)
        # placed dynamically when an action is offered

    def _build_log(self, parent):
        self.nb = ttk.Notebook(parent)
        self.nb.grid(row=3, column=0, sticky="nsew", pady=(8, 0))

        # --- Tab 1: Results (Needs Repair / Repaired) ---
        results = ttk.Frame(self.nb, padding=4)
        self.nb.add(results, text="Results")
        results.rowconfigure(1, weight=1)
        results.rowconfigure(3, weight=1)
        results.columnconfigure(0, weight=1)
        self.results_summary = tk.StringVar(
            value="Run an audit to list what needs repair; build & verify to "
                  "move fixed items to Repaired.")
        ttk.Label(results, textvariable=self.results_summary,
                  font=("Segoe UI", 8), foreground="#5f6368").grid(
            row=0, column=0, sticky="w", pady=(0, 2))

        ttk.Label(results, text="⚠  NEEDS REPAIR",
                  foreground="#d93025", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="e")
        self.tree_needs = self._results_tree(results, 1)
        ttk.Label(results, text="✓  REPAIRED (verified)",
                  foreground="#188038", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=0, sticky="w", pady=(6, 0))
        self.tree_repaired = self._results_tree(results, 3)

        # --- Tab 2: Activity log ---
        logf = ttk.Frame(self.nb)
        self.nb.add(logf, text="Activity log")
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.log_text = tk.Text(logf, height=8, wrap="word", state="disabled",
                                font=("Consolas", 9), background=NAVY,
                                foreground="#d7e3f4")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sc = ttk.Scrollbar(logf, command=self.log_text.yview)
        sc.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sc.set)

    def _results_tree(self, parent, row):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        cols = ("sev", "cat", "item", "page")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=5)
        for c, w, t in [("sev", 70, "Status"), ("cat", 130, "Category"),
                        ("item", 320, "Item"), ("page", 160, "Page")]:
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w")
        tree.tag_configure("CRITICAL", foreground="#d93025")
        tree.tag_configure("WARNING", foreground="#ea8600")
        tree.tag_configure("NOTICE", foreground="#1a73e8")
        tree.tag_configure("MANUAL", foreground="#8430ce")
        tree.tag_configure("REPAIRED", foreground="#188038")
        tree.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(frame, command=tree.yview)
        vs.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vs.set)
        return tree

    def _populate_results(self, split):
        """Fill the Needs Repair / Repaired trees from a verify split dict."""
        self.tree_needs.delete(*self.tree_needs.get_children())
        self.tree_repaired.delete(*self.tree_repaired.get_children())
        for it in split.get("needs_repair", []):
            manual = it.get("status") == "needs_repair_manual"
            tag = "MANUAL" if manual else it["severity"]
            label = "MANUAL" if manual else it["severity"]
            self.tree_needs.insert("", "end", tags=(tag,), values=(
                label, it["category"], it["message"][:120],
                urlparse(it["url"]).path or it["url"]))
        for it in split.get("repaired", []):
            self.tree_repaired.insert("", "end", tags=("REPAIRED",), values=(
                "FIXED ✓", it["category"], it["message"][:120],
                urlparse(it["url"]).path or it["url"]))
        s = split.get("summary", {})
        verified = "verified against the rebuilt files" if s.get("verified") \
            else "not yet verified"
        self.results_summary.set(
            f"{s.get('needs_repair', 0)} need repair, "
            f"{s.get('repaired', 0)} repaired ({verified}).")
        self.nb.select(0)  # show the Results tab

    def _results_from_sections(self, sections):
        """Turn a plain audit (no repair yet) into an all-needs-repair split."""
        from seo_audit.verify import split_results
        return split_results(sections, None)

    def _build_actions(self, parent):
        # Scrollable canvas so the button stack always fits
        canvas = tk.Canvas(parent, width=320, highlightthickness=0,
                           background=LIGHT)
        canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        def header(text):
            ttk.Label(inner, text=text, style="Head.TLabel").pack(
                anchor="w", pady=(10, 2), padx=4)

        def sq(text, cmd, big=False):
            b = ttk.Button(inner, text=text, command=cmd,
                           style="Big.TButton" if big else "Sq.TButton")
            b.pack(fill="x", padx=4, pady=2)
            return b

        header("Tools & setup")
        sq("\U0001F50D  Google Search Console",
           lambda: webbrowser.open("https://search.google.com/search-console"))
        sq("\U0001F577️  Crawl / Load site", self.act_crawl)
        sq("\U0001F916  Robots.txt  (add / repair)", self.act_robots)
        sq("\U0001F9E0  llms.txt for AI  (add / repair)", self.act_llms)
        sq("\U0001F517  Sitemap.xml  (generate)", self.act_sitemap)

        header("On-page audit")
        self.onpage_buttons = [
            ("Title tags & meta descriptions", {"titles", "metas"}),
            ("Heading structure (H1/H2/H3)", {"headings"}),
            ("Content & search intent", {"content"}),
            ("URL structure", {"urls"}),
            ("Image optimization (alt/names)", {"images"}),
            ("Internal linking", {"links"}),
            ("Page speed & Core Web Vitals", {"speed"}),
            ("Mobile-friendliness", {"mobile"}),
            ("Schema / structured data", {"schema"}),
            ("Keyword usage", {"keywords"}),
        ]
        for label, cats in self.onpage_buttons:
            sq(label, lambda c=cats, l=label: self.act_onpage_single(l, c))

        header("Off-page audit")
        for label in ["Backlinks (quality & relevance)", "Brand mentions",
                      "Local citations & listings", "Social signals & reputation",
                      "Guest posting / digital PR", "Domain authority"]:
            sq(label, self.act_offpage)

        header("Security")
        sq("\U0001F512  Security audit", self.act_security_audit)
        sq("\U0001F6E1️  Build security hardening files", self.act_security_files)

        header("Run everything")
        sq("✅  COMPLETE AUDIT (all checks)", self.act_complete_audit, big=True)

        header("Build & repair (for hosting)")
        sq("\U0001F4BE  Back up originals now", self.act_backup)
        sq("\U0001F6E0️  Build & verify repairs", self.act_build_package, big=True)
        sq("On-page fixes only", lambda: self.act_build_package(onpage_only=True))
        sq("☁️  Save / push to GitHub", self.act_push_github)
        sq("\U0001F4CD  Build location pages", self.act_location_pages)
        sq("\U0001F4C8  Off-page action plan", self.act_offpage_plan)

        header("AI visibility (AEO/GEO)")
        sq("\U0001F50E  Prompt research", self.act_prompt_research)
        sq("\U0001F4CA  Track AI visibility", self.act_track_visibility)

        header("Content creation")
        sq("❓  FAQ page", self.act_faq)
        sq("✍️  Blog plan (12 topics)", self.act_blog)
        sq("\U0001F4DD  Full blog-post draft", self.act_blog_post)
        sq("\U0001F5C2️  Service landing pages", self.act_service_pages)
        sq("\U0001F3F7️  Bulk meta descriptions", self.act_meta_descriptions)

        header("Guides")
        sq("Set up Google Business Profile", self.act_gbp_guide)
        sq("Integrate AI into the business", self.act_ai_guide)
        sq("Outreach / backlink templates", self.act_outreach)

        header("Debug")
        sq("\U0001F527  Run diagnostics", self.act_diagnostics)
        self.verbose_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(inner, text="Verbose logging",
                        variable=self.verbose_var).pack(anchor="w", padx=6)
        sq("Save log to file", self.act_save_log)
        sq("Copy last error", self.act_copy_error)

        header("Reports")
        sq("Open reports folder", lambda: self._open_folder(AUDITS_DIR))
        sq("Open site package folder", lambda: self._open_folder(PACKAGE_DIR))
        self.open_report_btn = sq("Open last HTML report", self.open_last_report)
        self.open_report_btn.configure(state="disabled")

        header("Validators")
        sq("PageSpeed Insights",
           lambda: self._open_tool("https://pagespeed.web.dev/analysis?url={url}"))
        sq("Rich Results Test",
           lambda: self._open_tool("https://search.google.com/test/rich-results?url={url}"))
        sq("Schema Markup Validator",
           lambda: self._open_tool("https://validator.schema.org/#url={url}"))
        sq("Analyze server log file…", self.act_logfile)
        # PageSpeed API key
        keyf = ttk.Frame(inner)
        keyf.pack(fill="x", padx=4, pady=(8, 4))
        ttk.Label(keyf, text="PageSpeed API key:").pack(anchor="w")
        self.psi_key_var = tk.StringVar()
        ttk.Entry(keyf, textvariable=self.psi_key_var, show="*").pack(fill="x")
        ttk.Label(keyf, text="Claude API key (optional, AI copy):").pack(anchor="w",
                                                                        pady=(4, 0))
        self.claude_key_var = tk.StringVar()
        ttk.Entry(keyf, textvariable=self.claude_key_var, show="*").pack(fill="x")
        self.claude_key_var.trace_add("write", lambda *a: self._sync_claude_key())

    # ==================================================================
    # Source handling
    # ==================================================================
    def _sync_source(self):
        mode = self.source_mode.get()
        self.drop.configure(background="#eef7f4" if mode == "local" else "#f4f7fb")

    def _sync_claude_key(self):
        self.assistant.api_key = self.claude_key_var.get().strip()

    def _on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        self._load_local(list(paths))

    def _pick_folder(self):
        d = filedialog.askdirectory(title="Choose your website folder")
        if d:
            self._load_local([d])

    def _pick_files(self):
        fs = filedialog.askopenfilenames(
            title="Choose website files",
            filetypes=[("Web files", "*.html *.htm *.css *.js *.md *.csv *.txt "
                        "*.png *.jpg *.jpeg *.webp *.svg"), ("All files", "*.*")])
        if fs:
            self._load_local(list(fs))

    def _load_local(self, paths, from_github=False):
        # A fresh load starts a fresh in-memory session: drop the prior site's
        # parsed data before reading the new one.
        if not from_github:
            self._discard_session(keep_clone=False)
        self.source_mode.set("local")
        self._sync_source()
        self.local_paths = paths
        self.source_root_paths = list(paths)   # originals we can back up
        base = self.base_url_var.get().strip()
        try:
            if len(paths) == 1 and os.path.isdir(paths[0]):
                arg = paths[0]
            else:
                arg = paths
            pages, inv = load_local_site(arg, base_url=base)
            self.local_pages = pages
            self.local_inventory = inv
            self.local_broken = inv.get("broken_local_links", {})
            n = inv.get("html_files", len(pages))
            self.source_summary.set(
                f"Loaded {n} HTML page(s), {inv.get('images', 0)} image(s), "
                f"{inv.get('css', 0)} CSS, {inv.get('js', 0)} JS; "
                f"{len(self.local_broken)} broken local link(s). "
                f"(In memory only - discarded when you start a new session.)")
            self.log(f"Loaded {'GitHub repo' if from_github else 'local site'}: "
                     f"{n} pages from {paths[0]}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not load site: {exc}")
            self.log(f"ERROR loading site: {exc}")

    def _discard_session(self, keep_clone=True):
        """Drop the in-memory parsed site (kept only for the session)."""
        self.local_pages = None
        self.local_broken = {}
        self.local_inventory = {}
        self.local_paths = []
        self.source_root_paths = []
        if not keep_clone and self.clone_dir:
            import shutil
            shutil.rmtree(self.clone_dir, ignore_errors=True)
            self.clone_dir = ""

    def act_new_session(self):
        self._discard_session(keep_clone=False)
        try:
            self.tree_needs.delete(*self.tree_needs.get_children())
            self.tree_repaired.delete(*self.tree_repaired.get_children())
        except Exception:
            pass
        self.source_summary.set("Session cleared - loaded site data discarded.")
        self.log("New session: in-memory site data discarded.")

    def _pick_save_root(self):
        d = filedialog.askdirectory(title="Choose where to save results & backups")
        if d:
            self.save_root_var.set(d)
            set_save_root(d)
            self.log(f"Save location set to {d}")

    def act_load_github(self):
        url = self.gh_url_var.get().strip()
        token = self.gh_token_var.get().strip()
        if not url:
            messagebox.showinfo(APP_NAME, "Paste a GitHub repo URL first.")
            return
        # apply save root before we clone under it
        set_save_root(self.save_root_var.get().strip() or APP_DIR)

        def job():
            self._discard_session(keep_clone=False)
            res = gitsource.clone_repo(url, token=token, log=self.log)
            if not res["ok"]:
                self.msg_queue.put(("status", "GitHub clone failed - see log."))
                self.log("GitHub clone failed: " + res["error"])
                messagebox.showerror(APP_NAME, "Could not load the repo:\n\n"
                                     + res["error"])
                return
            self.clone_dir = res["dir"]
            # Load on the main thread (Tk-touching) via a callback.
            self.root.after(0, lambda: self._load_local([res["dir"]],
                                                        from_github=True))
            self.msg_queue.put(("status", "GitHub repo cloned and loaded."))
        self._run_bg(job, f"Cloning {url} ...")

    def _current_url(self, required=True):
        url = self.url_var.get().strip()
        if not url and required and self.source_mode.get() == "url":
            messagebox.showwarning(APP_NAME, "Enter a website URL first, or "
                                             "switch to uploading a folder.")
            return None
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    # ==================================================================
    # Assistant chat
    # ==================================================================
    def _assistant_say(self, text, tag="bot"):
        self.chat.configure(state="normal")
        prefix = "Assistant: " if tag == "bot" else ""
        self.chat.insert("end", prefix + text + "\n\n", tag)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _assistant_send(self):
        text = self.chat_in.get().strip()
        if not text:
            return
        self.chat_in.set("")
        self._assistant_say("You: " + text, "me")
        reply = self.assistant.handle(text)
        self._assistant_say(reply.text)
        # sync profile-derived fields into the form
        prof = self.assistant.profile
        if prof.get("keywords") and not self.keywords_var.get().strip():
            self.keywords_var.set(", ".join(prof["keywords"]))
        if reply.action:
            self._offer_action(reply.action, reply.action_params or {})
        else:
            self.action_btn.pack_forget()
            self.pending_action = None

    def _offer_action(self, action, params):
        labels = {
            "generate_location_pages": "\U0001F4CD  Build these location pages now",
            "generate_faq": "❓  Generate the FAQ page now",
            "generate_blog_plan": "✍️  Generate the blog plan now",
            "generate_gbp_guide": "Open the Google Business Profile guide",
        }
        self.pending_action = (action, params)
        self.action_btn.configure(text=labels.get(action, "Do it"))
        self.action_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    def _run_pending_action(self):
        if not self.pending_action:
            return
        action, params = self.pending_action
        if action == "generate_location_pages":
            self.act_location_pages(locations=params.get("locations"))
        elif action == "generate_faq":
            self.act_faq()
        elif action == "generate_blog_plan":
            self.act_blog()
        elif action == "generate_gbp_guide":
            self.act_gbp_guide()
        self.action_btn.grid_forget()
        self.pending_action = None

    # ==================================================================
    # Business profile helper
    # ==================================================================
    def _business(self):
        p = self.assistant.profile
        return {
            "brand": p.get("brand", ""),
            "description": p.get("description", ""),
            "phone": p.get("phone", ""),
            "street": p.get("street", ""),
            "city": p.get("city", ""),
            "state": p.get("state", "NY"),
            "zip": p.get("zip", ""),
            "socials": p.get("socials", {}),
            "is_local": p.get("is_local", False),
            "services": p.get("services", []),
            "keywords": p.get("keywords", []),
        }

    def _keywords(self):
        kw = [k.strip() for k in self.keywords_var.get().split(",") if k.strip()]
        return kw or self.assistant.profile.get("keywords", [])

    # ==================================================================
    # Progress plumbing
    # ==================================================================
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
                    self._on_done(payload)
                elif kind == "busy":
                    self._busy(payload)
                elif kind == "results":
                    self._populate_results(payload)
                elif kind == "chat":
                    self._assistant_say(payload, "act")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _busy(self, on):
        if on:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _run_bg(self, fn, status=""):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME, "A task is already running - please wait.")
            return
        if status:
            self.msg_queue.put(("status", status))
        self.stop_requested = False
        verbose = self._verbose()   # read Tk var on the main thread
        self._busy(True)

        def work():
            try:
                fn()
            except Exception as exc:
                tb = traceback.format_exc()
                self.last_error = tb
                self.log(f"\nERROR: {exc}")
                if verbose:
                    self.log(tb)
                else:
                    self.log("(Enable 'Verbose logging' in the Debug section, or "
                             "click 'Copy last error', for the full traceback.)")
                self.msg_queue.put(("done", None))
            finally:
                self.msg_queue.put(("status", "Ready."))
                self.msg_queue.put(("busy", False))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _on_done(self, result):
        if result and result.get("paths", {}).get("html"):
            self.last_result = result
            self.open_report_btn.configure(state="normal")
            # Populate "Needs Repair" from the audit's issues (nothing verified
            # as repaired until you run Build & verify repairs).
            sections = result.get("sections")
            if sections:
                try:
                    self._populate_results(split_results(sections, None))
                except Exception:
                    pass
            overall = result.get("overall")
            msg = f"Audit complete - overall score {overall}/100." if overall is not None \
                else "Done."
            self.msg_queue.put(("status", msg + f"  Saved to {result['output_dir']}"))
            if messagebox.askyesno(APP_NAME, msg + "\n\nOpen the HTML report now?"):
                self.open_last_report()

    # ==================================================================
    # Context snapshot (read all Tk vars on the MAIN thread only)
    # ==================================================================
    def _snapshot(self):
        """Read every Tk variable here, on the main thread, and hand the
        worker a plain dict. Tkinter variables must never be touched from a
        background thread."""
        url = self.url_var.get().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        # Apply the save location (main thread) so the output globals are set
        # before any worker uses them.
        set_save_root(self.save_root_var.get().strip() or APP_DIR)
        return {
            "mode": self.source_mode.get(),
            "url": url,
            "max_pages": self.max_pages_var.get(),
            "subdomains": self.subdomains_var.get(),
            "sitemap": self.sitemap_var.get(),
            "base_url": self.base_url_var.get().strip(),
            "keywords": [k.strip() for k in self.keywords_var.get().split(",")
                         if k.strip()] or self.assistant.profile.get("keywords", []),
            "psi_key": self.psi_key_var.get().strip(),
            "claude_key": self.claude_key_var.get().strip(),
            "business": self._business(),
            "offpage_manual": self._offpage_manual(),
            "source_root_paths": list(self.source_root_paths),
            "backup_dir": self._site_backup_dir(),
        }

    def _ctx_name(self, ctx):
        if ctx["mode"] == "local":
            return ctx["base_url"] or "uploaded-site"
        return ctx["url"] or "site"

    # ==================================================================
    # Getting pages (crawl OR local) - worker-thread safe (takes ctx)
    # ==================================================================
    def _get_pages(self, ctx):
        """Return (pages, broken, crawler_or_None). Uses local upload if set,
        else crawls the URL. Runs in a worker thread - no Tk access."""
        if ctx["mode"] == "local" and self.local_pages:
            self.log(f"Using uploaded site ({len(self.local_pages)} pages).")
            return self.local_pages, self.local_broken, None
        url = ctx["url"]
        if not url:
            self.log("No URL provided.")
            return None, {}, None
        from seo_audit.crawler import SiteCrawler
        self.log(f"Crawling {url} ...")
        crawler = SiteCrawler(
            url, max_pages=ctx["max_pages"], log=self.log,
            stop_flag=lambda: self.stop_requested,
            include_subdomains=ctx["subdomains"],
            seed_from_sitemap=ctx["sitemap"])
        pages = crawler.crawl()
        broken = crawler.check_broken_links()
        return pages, broken, crawler

    # ==================================================================
    # ACTIONS - audits
    # ==================================================================
    def act_crawl(self):
        ctx = self._snapshot()
        if not self._have_source(ctx):
            return

        def job():
            pages, broken, _ = self._get_pages(ctx)
            if pages is None:
                return
            ok = sum(1 for p in pages.values() if p.ok)
            self.log(f"Done. {ok} page(s) OK, {len(broken)} broken link target(s).")
            self.msg_queue.put(("status", f"Crawl/load complete: {ok} pages."))
        self._run_bg(job, "Crawling / loading site...")

    def act_onpage_single(self, label, cats):
        ctx = self._snapshot()
        if not self._have_source(ctx):
            return

        def job():
            from seo_audit.onpage import run_onpage_audit
            pages, broken, _ = self._get_pages(ctx)
            if pages is None:
                return
            self.log(f"Running on-page check: {label}")
            section = run_onpage_audit(pages, broken, ctx["keywords"], log=self.log)
            self._save_single(section, ctx)
        self._run_bg(job, f"Checking: {label}")

    def act_offpage(self):
        ctx = self._snapshot()
        if not self._have_source(ctx):
            return

        def job():
            from seo_audit.offpage import run_offpage_audit
            pages, broken, _ = self._get_pages(ctx)
            if pages is None:
                return
            section = run_offpage_audit(self._ctx_name(ctx), pages,
                                        manual=ctx["offpage_manual"], log=self.log)
            self._save_single(section, ctx)
        self._run_bg(job, "Running off-page analysis...")

    def act_offpage_plan(self):
        self.act_offpage()

    def _offpage_manual(self):
        p = self.assistant.profile
        return {"brand_name": p.get("brand", ""),
                "is_local_business": p.get("is_local", False)}

    def act_complete_audit(self):
        ctx = self._snapshot()
        if not self._have_source(ctx):
            return
        self._save_settings()
        if ctx["mode"] == "local" and self.local_pages:
            self._complete_audit_local(ctx)
        else:
            self._complete_audit_url(ctx)

    def _complete_audit_url(self, ctx):
        def job():
            runner = AuditRunner(
                ctx["url"], max_pages=ctx["max_pages"], keywords=ctx["keywords"],
                psi_api_key=ctx["psi_key"], offpage_manual=ctx["offpage_manual"],
                output_base=AUDITS_DIR, log=self.log,
                stop_flag=lambda: self.stop_requested)
            result = runner.run(do_onpage=True, do_technical=True,
                                do_offpage=True, do_pagespeed=True)
            self.msg_queue.put(("done", result))
        self._run_bg(job, f"Complete audit of {ctx['url']} ...")

    def _complete_audit_local(self, ctx):
        name = self._ctx_name(ctx)

        def job():
            from seo_audit.onpage import run_onpage_audit
            from seo_audit.offpage import run_offpage_audit
            from seo_audit.technical import run_technical_audit
            pages, broken = self.local_pages, self.local_broken
            self.log("Running complete audit on uploaded site...")
            sections = [
                run_onpage_audit(pages, broken, ctx["keywords"], log=self.log),
                run_offpage_audit(name, pages, manual=ctx["offpage_manual"],
                                  log=self.log),
            ]
            out = make_output_dir(AUDITS_DIR, name)
            paths = save_reports(out, name, sections, ["Local upload audit"],
                                 meta={"source": "upload"})
            overall = round(sum(s.score for s in sections) / max(len(sections), 1))
            self.msg_queue.put(("done", {"paths": paths, "output_dir": out,
                                         "overall": overall, "sections": sections}))
        self._run_bg(job, "Complete audit of uploaded site...")

    def _save_single(self, section, ctx):
        name = self._ctx_name(ctx)
        out = make_output_dir(AUDITS_DIR, name)
        paths = save_reports(out, name, [section],
                             [f"Single check: {section.name}"])
        self.msg_queue.put(("done", {"paths": paths, "output_dir": out,
                                     "overall": section.score, "sections": [section]}))

    def _have_source(self, ctx):
        if ctx["mode"] == "local" and self.local_pages:
            return True
        if ctx["mode"] == "url" and ctx["url"]:
            return True
        messagebox.showwarning(APP_NAME, "Enter a website URL, or upload a "
                                         "website folder/files first.")
        return False

    def act_logfile(self):
        path = filedialog.askopenfilename(
            title="Choose a server access log",
            filetypes=[("Logs", "*.log *.txt *.access"), ("All files", "*.*")])
        if not path:
            return

        def job():
            self.log(f"Analyzing log {path} ...")
            section = analyze_log_file(path, log=self.log)
            out = make_output_dir(AUDITS_DIR, "logfile-analysis")
            paths = save_reports(out, "logfile-analysis", [section],
                                 [f"Log: {path}"])
            self.msg_queue.put(("done", {"paths": paths, "output_dir": out,
                                         "overall": section.score, "sections": [section]}))
        self._run_bg(job, "Analyzing server log...")

    # ==================================================================
    # ACTIONS - security
    # ==================================================================
    def act_security_audit(self):
        if not _SEC:
            messagebox.showinfo(APP_NAME, "Security module not available in this "
                                          "copy. Run diagnostics for details.")
            return
        ctx = self._snapshot()
        if not self._have_source(ctx):
            return

        def job():
            pages, broken, crawler = self._get_pages(ctx)
            if pages is None:
                return
            url = ctx["url"] or ctx["base_url"] or self._ctx_name(ctx)
            self.log("Running website security audit (defensive checks)...")
            section = secmod.run_security_audit(
                url, pages, session=crawler.session if crawler else None,
                log=self.log)
            self._save_single(section, ctx)
        self._run_bg(job, "Running security audit...")

    def act_security_files(self):
        if not _SEC:
            messagebox.showinfo(APP_NAME, "Security module not available.")
            return
        ctx = self._snapshot()
        url = ctx["url"] or ctx["base_url"] or "site"

        def job():
            # generate_security_files appends its own "security/" subfolder
            self.log("Building security hardening files...")
            res = secmod.generate_security_files(PACKAGE_DIR, url)
            out = os.path.join(PACKAGE_DIR, "security")
            self.log(f"Wrote: {', '.join(os.path.basename(x) for x in res['written'])}")
            self.msg_queue.put(("status", f"Security files written to {out}"))
            if messagebox.askyesno(APP_NAME, f"Security hardening files written "
                                             f"to:\n{out}\n\nOpen the folder?"):
                self._open_folder(out)
        self._run_bg(job, "Building security files...")

    # ==================================================================
    # ACTIONS - debug
    # ==================================================================
    def _verbose(self):
        try:
            return bool(self.verbose_var.get())
        except Exception:
            return False

    def act_diagnostics(self):
        def job():
            report = run_diagnostics(APP_DIR, AUDITS_DIR, PACKAGE_DIR, log=self.log)
            path = os.path.join(APP_DIR, "diagnostics.txt")
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(report)
                self.log(f"Diagnostics saved to {path}")
            except OSError:
                pass
            self.msg_queue.put(("status", "Diagnostics complete - see the log."))
        self._run_bg(job, "Running diagnostics...")

    def act_save_log(self):
        path = filedialog.asksaveasfilename(
            title="Save activity log", defaultextension=".txt",
            initialfile=f"seo-audit-log-{datetime.now():%Y%m%d-%H%M%S}.txt",
            filetypes=[("Text", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.log_text.get("1.0", "end"))
            messagebox.showinfo(APP_NAME, f"Log saved to:\n{path}")
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Could not save log: {exc}")

    def act_copy_error(self):
        if not self.last_error:
            messagebox.showinfo(APP_NAME, "No error has occurred yet.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_error)
        messagebox.showinfo(APP_NAME, "Last error (full traceback) copied to the "
                                      "clipboard. Paste it when asking for help.")

    # ==================================================================
    # ACTIONS - build / repair
    # ==================================================================
    def act_robots(self):
        self._build_files_only("robots.txt")

    def act_llms(self):
        self._build_files_only("llms.txt")

    def act_sitemap(self):
        self._build_files_only("sitemap.xml")

    # ---- backup + GitHub save ----
    def _site_name(self):
        base = self.base_url_var.get().strip() or self.url_var.get().strip()
        if base:
            host = urlparse(base if "//" in base else "//" + base).netloc
            if host:
                return host.replace(":", "_")
        if self.source_root_paths:
            return os.path.basename(str(self.source_root_paths[0]).rstrip("/\\")) \
                or "site"
        return "site"

    def _site_backup_dir(self):
        return os.path.join(BACKUP_DIR, self._site_name())

    def _do_backup(self, ctx, quiet=False):
        """Back up the loaded originals using paths captured in the ctx
        snapshot (no Tk access - safe from a worker thread). Returns the
        result dict or None."""
        roots = ctx.get("source_root_paths") or []
        if not roots:
            if not quiet:
                self.log("Backup skipped: no uploaded files (a live-URL audit "
                         "has nothing local to back up).")
            return None
        try:
            return make_backup(roots, ctx["backup_dir"], log=self.log)
        except Exception as exc:
            self.log(f"Backup error: {exc}")
            return None

    def act_backup(self):
        ctx = self._snapshot()
        if ctx["mode"] != "local" or not ctx["source_root_paths"]:
            messagebox.showinfo(APP_NAME, "Upload a folder/files (or load a "
                                          "GitHub repo) first - there's nothing "
                                          "local to back up for a live URL.")
            return

        def job():
            res = self._do_backup(ctx)
            if res:
                msg = (f"Backed up {res['files_copied']} file(s) to "
                       f"{os.path.basename(res['folder'])}"
                       + (f" ({len(res['skipped'])} unreadable skipped)"
                          if res['skipped'] else ""))
                self.msg_queue.put(("status", msg))
                if messagebox.askyesno(APP_NAME, msg + f"\n\nLocation:\n"
                                       f"{res['folder']}\n\nOpen the folder?"):
                    self._open_folder(os.path.dirname(res['folder']))
        self._run_bg(job, "Backing up originals...")

    def act_push_github(self):
        set_save_root(self.save_root_var.get().strip() or APP_DIR)
        pkg = os.path.join(PACKAGE_DIR, "repaired-site")
        if not os.path.isdir(pkg):
            messagebox.showinfo(APP_NAME, "Build the repaired site package first "
                                          "(Build & verify repairs), then push it.")
            return
        if not gitsource.git_available():
            messagebox.showerror(APP_NAME, "Git isn't installed. Install Git for "
                                 "Windows from https://git-scm.com/download/win.")
            return
        url = self._ask_text("Save to GitHub",
                             "Target GitHub repo URL to push the repaired site to\n"
                             "(a new branch is created - your main branch is untouched):")
        if not url:
            return
        token = self.gh_token_var.get().strip()
        if not messagebox.askyesno(APP_NAME, f"Push the repaired site package to:\n"
                                   f"{url}\n\nThis creates a NEW branch and does not "
                                   f"touch your existing branches. Continue?"):
            return

        def job():
            self.log(f"Pushing repaired site to {url} ...")
            res = gitsource.push_folder(pkg, url, token=token, log=self.log)
            if res["ok"]:
                self.msg_queue.put(("status", f"Pushed to branch {res['branch']}."))
                messagebox.showinfo(APP_NAME, f"Pushed the repaired site to a new "
                                    f"branch:\n\n{res['branch']}\n\nOpen a pull "
                                    f"request on GitHub to review and merge it.")
            else:
                self.log("Push failed: " + res["error"])
                messagebox.showerror(APP_NAME, "Push failed:\n\n" + res["error"])
        self._run_bg(job, "Pushing to GitHub...")

    def _build_files_only(self, which):
        ctx = self._snapshot()
        if not self._have_source(ctx):
            return

        def job():
            pages, broken, _ = self._get_pages(ctx)
            if pages is None:
                return
            base = ctx["url"] or ctx["base_url"] or ""
            page_list = [(u, (p.soup.title.get_text(strip=True)
                              if p.soup and p.soup.title else u))
                         for u, p in pages.items() if p.ok]
            out = os.path.join(PACKAGE_DIR, "site-files")
            res = repairmod.repair_files_only(out, ctx["business"], page_list,
                                              base, log=self.log)
            self.log(f"Wrote: {', '.join(os.path.basename(x) for x in res['written'])}")
            self.msg_queue.put(("status", f"{which} + supporting files written to {out}"))
            if messagebox.askyesno(APP_NAME, f"{which} and supporting files written "
                                             f"to:\n{out}\n\nOpen the folder?"):
                self._open_folder(out)
        self._run_bg(job, f"Building {which} ...")

    def act_build_package(self, onpage_only=False):
        cats = None
        if onpage_only:
            cats = {"titles", "metas", "headings", "images", "mobile",
                    "canonical", "schema", "social"}
        ctx = self._snapshot()
        if not self._have_source(ctx):
            return

        def job():
            pages, broken, _ = self._get_pages(ctx)
            if pages is None:
                return
            base = ctx["url"] or ctx["base_url"] or ""
            # Safety net: back up the untouched originals BEFORE repairing.
            self._do_backup(ctx, quiet=True)
            out = os.path.join(PACKAGE_DIR, "repaired-site")
            self.log("Building repaired site package (with verification)...")
            # Audit -> repair -> re-audit the repaired files -> split results.
            outcome = build_and_verify(pages, out, ctx["business"],
                                       keywords=ctx["keywords"], categories=cats,
                                       base_url=base, log=self.log)
            res, split = outcome["result"], outcome["split"]
            self.msg_queue.put(("results", split))
            # Two-section HTML report (Needs Repair / Repaired)
            status_html = os.path.join(res.get("output_dir", out),
                                       "repair-status.html")
            try:
                render_split_html(base or "your site", split, status_html)
            except Exception:
                status_html = ""
            self.last_result = {"paths": {"html": status_html},
                                "output_dir": res.get("output_dir", out)} \
                if status_html else self.last_result
            s = split["summary"]
            verified = "" if outcome["reaudited"] else \
                "\n(Note: set a base URL to enable automatic verification.)"
            self.msg_queue.put(("status", f"{s['repaired']} repaired, "
                                          f"{s['needs_repair']} still need attention."))
            if messagebox.askyesno(
                    APP_NAME,
                    f"Repaired site package built and re-checked!\n\n"
                    f"✓ Repaired (verified): {s['repaired']}\n"
                    f"⚠ Still needs repair: {s['needs_repair']}\n\n"
                    f"Saved to:\n{res.get('output_dir', out)}{verified}\n\n"
                    f"Open the Needs Repair / Repaired report?"):
                if status_html:
                    webbrowser.open("file://" + os.path.abspath(status_html))
                else:
                    self._open_folder(res.get("output_dir", out))
        self._run_bg(job, "Building & verifying repairs...")

    def act_location_pages(self, locations=None):
        ctx = self._snapshot()
        biz = ctx["business"]
        if not biz.get("brand"):
            messagebox.showinfo(APP_NAME, "Tell the AI assistant your business "
                                          "name and services first (left panel).")
            return
        if not locations:
            # ask the assistant / user for an area
            area = self._ask_text("Location pages",
                                  "What area do you serve?\n(e.g. 'Suffolk County', "
                                  "'NYC and Long Island', or a list of towns)")
            if not area:
                return
            resolved = locmod.resolve_locations(area)
            if resolved["status"] == "clarify":
                messagebox.showinfo(APP_NAME, resolved["message"])
                return
            locations = resolved["locations"]
        service = (biz.get("services") or ["Our Services"])
        service = service[0] if isinstance(service, list) and service else "Our Services"
        base = ctx["url"] or ctx["base_url"] or ""

        def job():
            out = os.path.join(PACKAGE_DIR, "location-pages")
            self.log(f"Generating {len(locations)} location page(s)...")
            res = locmod.generate_location_pages(biz, locations, out,
                                                 base_url=base, service=service,
                                                 log=self.log)
            self.log(f"Wrote {res['count']} page(s) + hub.")
            self.msg_queue.put(("status", f"{res['count']} location pages saved to {out}"))
            if messagebox.askyesno(APP_NAME, f"Generated {res['count']} location "
                                             f"pages + an areas-served hub.\n\n"
                                             f"Saved to:\n{out}\n\nOpen the folder?"):
                self._open_folder(out)
        self._run_bg(job, "Generating location pages...")

    def act_faq(self):
        biz = self._business()
        key = self.claude_key_var.get().strip()
        self._write_generated("FAQ page", "faq.html",
                              lambda: generate_faq_page(biz, key))

    def act_blog(self):
        biz = self._business()
        key = self.claude_key_var.get().strip()
        self._write_generated("Blog plan", "blog-plan.md",
                              lambda: generate_blog_plan(biz, key))

    def act_gbp_guide(self):
        biz = self._business()
        self._write_generated("Google Business Profile guide",
                              "google-business-profile-guide.md",
                              lambda: generate_gbp_guide(biz))

    def act_ai_guide(self):
        biz = self._business()
        self._write_generated("AI integration guide", "ai-integration-guide.md",
                              lambda: generate_ai_integration_guide(biz))

    def act_outreach(self):
        biz = self._business()
        self._write_generated("Outreach templates", "outreach-templates.md",
                              lambda: generate_outreach_templates(biz))

    # ==================================================================
    # ACTIONS - AI visibility (prompt research + tracking)
    # ==================================================================
    def _content_profile(self):
        """Assistant profile + the base URL from the form, for the prompt /
        content modules (read on the main thread)."""
        p = dict(self.assistant.profile)
        base = self.base_url_var.get().strip() or self.url_var.get().strip()
        if base:
            p["base_url"] = base
        return p

    def act_prompt_research(self):
        prof = self._content_profile()
        key = self.claude_key_var.get().strip()
        set_save_root(self.save_root_var.get().strip() or APP_DIR)
        if not prof.get("brand"):
            messagebox.showinfo(APP_NAME, "Tell the AI assistant your business "
                                          "name and services first (left panel).")
            return

        def job():
            self.log("Researching AI-answer prompt targets...")
            research = promptsmod.research_prompts(prof, api_key=key)
            out = os.path.join(PACKAGE_DIR, "ai-visibility")
            saved = promptsmod.save_prompts(prof, research, out)
            self.log(f"Found {research['count']} prompts across "
                     f"{len(research['clusters'])} intent clusters.")
            self.msg_queue.put(("status", f"{research['count']} prompt targets "
                                          f"saved to {out}"))
            if messagebox.askyesno(APP_NAME, f"Generated {research['count']} "
                                   f"AI-answer prompt targets"
                                   + (" (AI-curated)" if key else " (templates; "
                                      "add a Claude key for sharper phrasing)")
                                   + f".\n\nSaved to:\n{out}\n\nOpen the list?"):
                webbrowser.open("file://" + os.path.abspath(saved["md"]))
        self._run_bg(job, "Researching prompts...")

    def act_track_visibility(self):
        prof = self._content_profile()
        key = self.claude_key_var.get().strip()
        set_save_root(self.save_root_var.get().strip() or APP_DIR)
        out = os.path.join(PACKAGE_DIR, "ai-visibility")
        json_path = os.path.join(out, "ai-prompt-targets.json")
        if not prof.get("brand"):
            messagebox.showinfo(APP_NAME, "Set your business name/services first.")
            return
        if not key and not messagebox.askyesno(
                APP_NAME, "No Claude API key set, so tracking will open browser "
                          "searches for each prompt for you to check manually.\n\n"
                          "With a key, the app asks Claude (with live web search) "
                          "and records whether you appear automatically.\n\n"
                          "Continue in manual mode?"):
            return

        def job():
            # Use saved prompts if present, else research now.
            plist = []
            if os.path.exists(json_path):
                try:
                    with open(json_path, encoding="utf-8") as fh:
                        plist = json.load(fh).get("flat", [])
                except (OSError, ValueError):
                    plist = []
            if not plist:
                self.log("No saved prompts yet - researching first...")
                plist = promptsmod.research_prompts(prof, api_key=key)["flat"]
            self.log(f"Tracking AI visibility for {len(plist)} prompt(s) "
                     f"({'AI + web search' if key else 'manual browser'})...")
            res = promptsmod.track_visibility(
                plist, prof, api_key=key,
                history_dir=os.path.join(out, "tracking"), log=self.log,
                max_prompts=25 if key else 60)
            s = res["summary"]
            # Manual mode: open the first few browser searches to get started.
            if res["mode"] == "manual":
                for row in res["rows"][:8]:
                    if row.get("google"):
                        webbrowser.open(row["google"])
            delta = res.get("delta") or {}
            dtxt = ""
            if delta.get("visible") is not None:
                v = delta["visible"]
                dtxt = f"\nChange since last run: {'+' if v >= 0 else ''}{v} visible."
            self.msg_queue.put(("status", f"AI visibility: {s['visible']}/{s['total']} "
                                          f"prompts."))
            messagebox.showinfo(
                APP_NAME,
                (f"AI-answer visibility for {prof.get('brand')}:\n\n"
                 f"Cited (in answer sources): {s['cited']}\n"
                 f"Mentioned (in answer text): {s['mentioned']}\n"
                 f"Absent: {s['absent']}\n"
                 + (f"Manual to check: {s['manual']}\n" if s.get('manual') else "")
                 + dtxt +
                 f"\n\nHistory saved to:\n{os.path.join(out, 'tracking')}")
                if res["mode"] == "ai" else
                (f"Opened browser searches for the first prompts. Check each for "
                 f"{prof.get('brand')} / your domain and log the result.\n\n"
                 f"All {len(res['rows'])} prompts + search links saved to:\n"
                 f"{os.path.join(out, 'tracking')}\n\nAdd a Claude API key for "
                 f"automatic tracking."))
        self._run_bg(job, "Tracking AI visibility...")

    # ==================================================================
    # ACTIONS - expanded content creation
    # ==================================================================
    def act_blog_post(self):
        prof = self._content_profile()
        key = self.claude_key_var.get().strip()
        topic = self._ask_text("Blog post", "Blog post topic (leave blank for a "
                               "suggested one):") or ""
        self._write_generated(
            "Blog post draft",
            f"blog-{(topic or 'post').lower().replace(' ', '-')[:40]}.md",
            lambda: contentmod.generate_blog_post(prof, topic=topic, api_key=key))

    def act_service_pages(self):
        prof = self._content_profile()
        key = self.claude_key_var.get().strip()
        set_save_root(self.save_root_var.get().strip() or APP_DIR)
        if not prof.get("services"):
            messagebox.showinfo(APP_NAME, "Tell the assistant your services first.")
            return

        def job():
            out = os.path.join(PACKAGE_DIR, "content", "service-pages")
            self.log("Generating service landing pages...")
            res = contentmod.generate_service_pages(prof, out, api_key=key,
                                                    log=self.log)
            self.msg_queue.put(("status", f"{res['count']} service pages -> {out}"))
            if messagebox.askyesno(APP_NAME, f"Generated {res['count']} service "
                                   f"landing page(s).\n\nSaved to:\n{out}\n\n"
                                   f"Open the folder?"):
                self._open_folder(out)
        self._run_bg(job, "Generating service pages...")

    def act_meta_descriptions(self):
        ctx = self._snapshot()
        prof = self._content_profile()
        key = self.claude_key_var.get().strip()
        if not self._have_source(ctx):
            return

        def job():
            pages, broken, _ = self._get_pages(ctx)
            if pages is None:
                return
            page_list = [(u, (p.soup.title.get_text(strip=True)
                              if p.soup and p.soup.title else u))
                         for u, p in pages.items() if p.ok]
            self.log(f"Writing meta descriptions for {len(page_list)} page(s)...")
            rows = contentmod.generate_meta_descriptions(page_list, prof,
                                                        api_key=key, log=self.log)
            out = os.path.join(PACKAGE_DIR, "content")
            path = contentmod.save_meta_descriptions(rows, out)
            self.msg_queue.put(("status", f"Meta descriptions -> {path}"))
            if messagebox.askyesno(APP_NAME, f"Wrote {len(rows)} meta "
                                   f"description(s) to:\n{path}\n\nOpen it?"):
                webbrowser.open("file://" + os.path.abspath(path))
        self._run_bg(job, "Writing meta descriptions...")

    def _write_generated(self, label, filename, producer):
        def job():
            self.log(f"Generating {label}...")
            content = producer()
            out = os.path.join(PACKAGE_DIR, "content")
            os.makedirs(out, exist_ok=True)
            path = os.path.join(out, filename)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self.log(f"Saved {label} -> {path}")
            self.msg_queue.put(("status", f"{label} saved to {path}"))
            if messagebox.askyesno(APP_NAME, f"{label} generated:\n{path}\n\nOpen it now?"):
                webbrowser.open("file://" + os.path.abspath(path))
        self._run_bg(job, f"Generating {label}...")

    # ==================================================================
    # Misc helpers
    # ==================================================================
    def _ask_text(self, title, prompt):
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text=prompt, padding=10, justify="left").pack()
        var = tk.StringVar()
        ent = ttk.Entry(dlg, textvariable=var, width=44)
        ent.pack(padx=10, pady=6)
        ent.focus_set()
        result = {"v": None}
        def ok():
            result["v"] = var.get().strip()
            dlg.destroy()
        ttk.Button(dlg, text="OK", command=ok).pack(pady=(0, 10))
        ent.bind("<Return>", lambda e: ok())
        self.root.wait_window(dlg)
        return result["v"]

    def _open_tool(self, template):
        url = self._current_url(required=False) or self.base_url_var.get()
        if "{url}" in template and not url:
            messagebox.showinfo(APP_NAME, "Enter a URL first.")
            return
        webbrowser.open(template.replace("{url}", quote_plus(url or "")))

    def _open_folder(self, path):
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            webbrowser.open("file://" + os.path.abspath(path))

    def open_last_report(self):
        if self.last_result:
            webbrowser.open("file://" +
                            os.path.abspath(self.last_result["paths"]["html"]))

    # ==================================================================
    # Settings
    # ==================================================================
    def _load_settings(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
                s = json.load(fh)
            self.url_var.set(s.get("url", ""))
            self.keywords_var.set(s.get("keywords", ""))
            self.psi_key_var.set(s.get("psi_api_key", ""))
            self.claude_key_var.set(s.get("claude_api_key", ""))
            self.base_url_var.set(s.get("base_url", ""))
            self.max_pages_var.set(s.get("max_pages", 40))
            self.subdomains_var.set(s.get("subdomains", False))
            self.sitemap_var.set(s.get("sitemap", True))
            self.gh_url_var.set(s.get("github_url", ""))
            root = s.get("save_root", "")
            if root:
                self.save_root_var.set(root)
                set_save_root(root)
        except (OSError, json.JSONDecodeError):
            pass

    def _save_settings(self):
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
                json.dump({
                    "url": self.url_var.get(),
                    "keywords": self.keywords_var.get(),
                    "psi_api_key": self.psi_key_var.get(),
                    "claude_api_key": self.claude_key_var.get(),
                    "base_url": self.base_url_var.get(),
                    "max_pages": self.max_pages_var.get(),
                    "subdomains": self.subdomains_var.get(),
                    "sitemap": self.sitemap_var.get(),
                    "github_url": self.gh_url_var.get(),
                    "save_root": self.save_root_var.get(),
                    # NB: GitHub token and API keys' secrecy - token is never
                    # persisted; API keys are (user convenience) - keep
                    # settings.json out of shared/committed folders.
                }, fh, indent=2)
        except OSError:
            pass

    def on_close(self):
        self._save_settings()
        self.stop_requested = True
        # Discard the in-memory session and any temp GitHub clone.
        self._discard_session(keep_clone=False)
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if _DND else tk.Tk()
    app = SeoAuditApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
