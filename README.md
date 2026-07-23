# SEO Audit Pro

A Windows desktop app (with a full GUI) that audits any website for
**on-page**, **off-page**, and **technical / AI-readiness** SEO — then saves
audit logs, an HTML report, a CSV issue list, and **ready-to-upload fix
files** (robots.txt, llms.txt, schema markup templates).

Built for 2026 SEO: alongside classic Google checks it audits **AI crawler
access** (GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, PerplexityBot,
Google-Extended, CCBot and more) so your content stays eligible for AI
Overviews, ChatGPT Search, Perplexity, and Claude answers (AEO/GEO).

---

## Windows setup (one time)

1. Install Python from <https://www.python.org/downloads/> —
   **tick "Add python.exe to PATH"** during install.
2. Double-click **`setup_windows.bat`** (installs two small libraries).
3. Double-click **`run_windows.bat`** to launch the app.

No other installs needed — the GUI uses Tkinter, which ships with Python.

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
(thin-content detection), keyword usage in title/H1/body with stuffing
detection, URL structure (length, underscores, case, depth, parameters),
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
local SEO, citation checklist, scored backlink/referring-domain/Domain
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
