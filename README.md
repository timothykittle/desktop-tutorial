# SEO Audit Pro

A Windows desktop app (with a full GUI) that audits any website for
**on-page**, **off-page**, and **technical / AI-readiness** SEO — then saves
audit logs, an HTML report, a CSV issue list, and **ready-to-upload fix
files** (robots.txt, llms.txt, schema markup templates).

Built for 2026 SEO: alongside classic Google checks it audits **AI crawler
access** (GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, PerplexityBot,
Google-Extended, CCBot and more) so your content stays eligible for AI
Overviews, ChatGPT Search, Perplexity, and Claude answers (AEO/GEO).

It doesn't just *find* problems — it **fixes and builds** them: upload your
site's files (or point it at a live domain), and it produces a repaired,
ready-to-upload copy with corrected titles, meta descriptions, headings,
image alt text, schema, viewport, robots.txt, and llms.txt. A built-in **AI
assistant** interviews you about your business and generates local **location
pages** (say "Suffolk County" and get a landing page for every town), FAQ
pages, a blog plan, and Google Business Profile / AI-integration guides.

---

## Windows setup (one time)

1. Install Python from <https://www.python.org/downloads/> —
   **tick "Add python.exe to PATH"** during install.
2. Double-click **`setup_windows.bat`** (installs the required libraries).
3. Double-click **`run_windows.bat`** to launch the app.

The GUI uses Tkinter, which ships with Python. Two optional extras add
polish: `tkinterdnd2` (drag-and-drop upload) and `anthropic` (lets the AI
assistant use Claude for higher-quality generated copy). `setup_windows.bat`
installs them automatically.

### Make a standalone .exe (no Python needed on other PCs)

Double-click **`build_windows_exe.bat`** (or run `python build_exe.py`). It
uses PyInstaller to produce **`dist\SEO Audit Pro.exe`** — a single file you
can copy to any Windows PC and double-click; the end user does **not** need
Python installed.

## The two-panel window

- **Left** — your **source** (type a live URL, *or* drag-and-drop / browse a
  website folder or files to upload), the **AI assistant** chat, and a live
  activity log.
- **Right** — a stack of square buttons: Google Search Console, Crawl,
  robots.txt, llms.txt, then one button per on-page and off-page check, a
  **COMPLETE AUDIT** button, and the **build** tools (repaired site package,
  location pages, FAQ, blog plan, guides).

## Upload & repair (build for hosting)

1. Drag your website folder onto the drop zone (or **Choose Folder…**). The
   app loads every HTML page plus CSS/JS/image/CSV/MD/TXT inventory and flags
   broken local links.
2. Tell the **AI assistant** your business name, services, area, phone, etc.
   (it asks one question at a time).
3. Click **Build & verify repairs**. You get a `site_package/repaired-site/`
   folder — the same file structure, with every fixable on-page issue
   corrected, plus `robots.txt`, `llms.txt`, `sitemap.xml`, and a
   `repair_log.csv` listing every change (before/after). Upload it to your host.

## Needs Repair vs Repaired (verified)

The **Results** tab has two sections. When you run an audit, every issue lands
under **⚠ Needs Repair**. When you click **Build & verify repairs**, the app
rebuilds the site *and then re-audits the rebuilt files* — anything the
re-check confirms is fixed moves down into **✓ Repaired (verified)**, and only
what's genuinely still outstanding stays under Needs Repair. Items the on-page
repairer can't touch (backlinks, page speed, off-page) are kept under Needs
Repair and tagged **MANUAL**. The same split is saved as
`repaired-site/repair-status.html`.

> "Repaired" always means *re-checked and confirmed*, not just "attempted" —
> so an item only leaves Needs Repair once it actually passes. Set a base URL
> (or audit a live URL) so the re-check can map the rebuilt files back to their
> pages; without one, items stay under Needs Repair until you verify manually.

The repairer is conservative: it **adds** what's missing and fixes what's
unambiguously broken (titles, metas, one-H1 rule, image alt text, viewport,
canonical, Open Graph, homepage schema) and never deletes your visible content.

## Security audit & hardening (for your own site)

Click **Security audit** for a defensive check of the site you're auditing:
HTTPS + HTTP→HTTPS redirect, TLS certificate expiry, missing security headers
(HSTS, CSP, X-Content-Type-Options, clickjacking, Referrer-Policy,
Permissions-Policy), insecure cookies (Secure/HttpOnly/SameSite), mixed
content, insecure login forms, third-party script / missing-SRI exposure,
publicly exposed files (`.git`, `.env`, backups), directory listing, missing
`security.txt`, and WordPress user enumeration. Every finding comes with a
fix. **Build security hardening files** then writes ready-to-upload
`.htaccess` / nginx / IIS header configs plus a `security.txt` template.

These are passive, best-practice checks for a site you own — no exploitation.

## Debug panel

The **Debug** buttons help when something doesn't work:

- **Run diagnostics** — checks Python, required and optional libraries, every
  app module, folder write access, network/proxy, and DNS, then saves
  `diagnostics.txt`. Run this first if the app misbehaves.
- **Verbose logging** — shows full tracebacks in the activity log.
- **Save log to file** / **Copy last error** — grab the log or the last full
  traceback to attach when asking for help.

## Build location pages (local SEO)

Click **Build location pages** (or tell the assistant your service area). Say
**"Suffolk County"** → a landing page for all ~44 towns. **"NYC and Long
Island"** → the five boroughs plus every LI town. **"New York"** alone → it
asks you to narrow down. Each page is a complete, unique HTML5 document
(varied intros so pages aren't duplicates) with LocalBusiness schema,
`areaServed`, NAP, a click-to-call CTA, and a review placeholder — plus an
`areas-served/` hub and a paste-ready footer link block.

## Using the app

1. Enter your **website URL**, optional **target keywords**, and how many
   pages to crawl.
2. (Optional) Fill the **off-page** fields — get free numbers from
   Google Search Console → Links, Moz Link Explorer, or Ahrefs Free
   Webmaster Tools. Tick **Local business** for citation/NAP checks.
3. Click **Run FULL Audit** (or one of the single-section buttons).
4. When it finishes, the HTML report opens; everything is saved to
   `audits/<domain>_<timestamp>/`:

| File | What it is |
|---|---|
| `report.html` | Full visual report with scores and fix instructions |
| `report.json` | Machine-readable results (for automations) |
| `issues.csv` | Spreadsheet of every issue (open in Excel) |
| `audit_log.txt` | Plain-text log of the whole audit run |
| `fixes/robots.txt` | Recommended robots.txt with deliberate AI-crawler rules |
| `fixes/llms.txt` | AEO/GEO file template for AI engines — edit and upload |
| `fixes/organization-schema.html` | JSON-LD schema to paste into your homepage |
| `fixes/local-business-schema.html` | LocalBusiness schema (local mode) |
| `fixes/faq-schema.html` | FAQ schema template (great for AI answers) |
| `fixes/htaccess-snippet.txt` | Apache speed/HTTPS/caching snippet |

Upload the edited files in `fixes/` to your web host's site root.

## What gets checked

**On-page** — title tags & meta descriptions (length, missing, duplicates),
heading structure (H1 count, level skips), content depth vs search intent
(thin-content detection), **site-wide keyword coverage** (which pages target
each keyword in titles/H1s, keywords no page targets, cannibalization when
too many pages compete, homepage placement, stuffing detection on every
page), URL structure (length, underscores, case, depth, parameters),
image optimization (alt text, file names, formats, dimensions, lazy
loading), internal linking (broken links, orphan pages, generic anchors),
canonical tags, mobile viewport, schema markup (JSON-LD validation + types),
Open Graph tags.

**Technical & AI readiness** — HTTPS + HTTP→HTTPS redirect, www/non-www
canonicalization, robots.txt analysis with a full **crawler access matrix**
(Googlebot, Bingbot + 12 AI crawlers), llms.txt presence, XML sitemap
discovery & validation, soft-404 detection, noindex detection, server
response times, compression, caching & security headers, redirect chains,
crawl errors.

**Off-page** — social profiles linked from the site, Organization /
LocalBusiness schema & `sameAs` brand entity, NAP (name/address/phone) for
local SEO, **local landing pages** (detects whether individual city/town
pages exist, or only a generic areas-served page), citation checklist,
scored backlink/referring-domain/Domain
Authority assessment (you paste the numbers from free tools), links-per-domain
spam ratio, one-click research links (GSC links report, brand-mention Google
searches, Moz, Ahrefs), and a prioritized off-page action plan.

**Performance** — Google PageSpeed Insights integration: Lighthouse
performance scores plus **real-user Core Web Vitals (LCP, INP, CLS)** for
mobile and desktop with targeted fixes. Works without an API key; add a
[free key](https://developers.google.com/speed/docs/insights/v5/get-started)
in the app for heavy use.

**Crawl budget (advanced)** — "Analyze Server Log File" parses your raw
Apache/Nginx access log and shows exactly which bots visit (Googlebot,
Bingbot, GPTBot, ClaudeBot, PerplexityBot…), what they crawl, and how much
crawl budget is wasted on errors.

## GUI quick-tool buttons

One click opens: **Google Search Console**, **PageSpeed Insights**,
**Rich Results Test**, **Schema Markup Validator**, **Bing Webmaster
Tools**, **Google Business Profile**, **Brand Mentions search**, **Moz Link
Explorer**, and **Ahrefs Backlink Checker** — pre-filled with your URL where
the tool supports it.

> Google Search Console has no public "connect" API for third-party desktop
> apps without OAuth app verification, so the button opens your GSC property
> directly — use its Links, Performance, and Indexing reports alongside this
> tool's output.

## Command line (optional)

```
python run_audit_cli.py https://example.com --max-pages 50 --keywords "blue widgets, widget repair"
python run_audit_cli.py --log-file access.log
```

## Notes

- The crawler respects `robots.txt`, identifies itself as `SEOAuditPro/1.0`,
  and rate-limits itself (~3 pages/second max).
- Only audit sites you own or have permission to audit.
- Backlink counts require third-party indexes; this tool scores the numbers
  you paste from free sources rather than pretending to have its own index.
