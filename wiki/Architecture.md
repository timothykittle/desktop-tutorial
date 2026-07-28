# Architecture (for developers)

A quick map for anyone extending the tool. All analysis lives in the
`seo_audit` package; the GUI and CLI are thin front ends over it.

## Front ends

| File | Role |
|------|------|
| `seo_audit_gui.py` | Tkinter desktop UI. Collects a source, runs package functions on a **background thread**, shows/saves results. Contains **no SEO logic** itself. |
| `run_audit_cli.py` | Headless runner over the same engine (see **[[GitHub and CLI]]**). |
| `build_exe.py` | PyInstaller build script for the standalone `.exe`. |

## The `seo_audit` package

| Module | Responsibility |
|--------|---------------|
| `crawler.py` | Fetch pages within one domain (respects `robots.txt`). |
| `localsite.py` | Load a local folder / uploaded files into the same `{url: PageData}` shape the crawler produces. |
| `issues.py` | Shared `Issue` / `SectionResult` data model + severity weights/scoring. |
| `onpage.py` | On-page checks. |
| `technical.py` | Technical + AI-crawler-access checks. |
| `offpage.py` | Off-page signals, supplied-metric scoring, action plan. |
| `pagespeed.py` | Google PageSpeed / Core Web Vitals. |
| `security.py` | Passive defensive audit + hardening-file generator. |
| `logfile.py` | Server access-log crawl-budget analysis. |
| `audit.py` | Orchestrator — runs the selected sections, saves outputs. |
| `report.py` | HTML / JSON / CSV / log writers. |
| `fixes.py` | Ready-to-upload `robots.txt` / `llms.txt` / schema / `.htaccess`. |
| `repair.py` | Writes a corrected, upload-ready copy of the site. |
| `verify.py` | Re-audits the repaired copy to prove what got fixed. |
| `backup.py` | Byte-for-byte backup of originals before repair. |
| `locations.py` | Local-SEO town landing-page generator (NY gazetteer + any US town). |
| `assistant.py` | Chat engine: interviews the business, generates deliverables; `ai_enhance()` is the shared Claude call. |
| `content.py` | Full blog posts, service landing pages, bulk meta descriptions. |
| `prompts.py` | AEO/GEO prompt research + AI-answer visibility tracking. |
| `gitsource.py` | Clone a repo to audit/repair and push results back. |
| `diagnostics.py` | Environment self-check for the GUI Debug panel. |

## Conventions

- **Checkers** return a `SectionResult` of `Issue`s, each with a severity from
  `issues.py`. Scores are severity-weighted.
- **Generators** (content, prompts, fixes, locations) work **offline from
  templates** and optionally upgrade via `assistant.ai_enhance(prompt, key)`.
  AI output is parsed back into local templates — never trusted to emit valid
  markup directly.
- **Long work runs on a background thread**; the GUI marshals a main-thread
  snapshot of inputs and communicates back via a queue, so the UI never blocks.

## Adding a new check

1. Add the logic to the relevant `*.py` (or a new module).
2. Return `Issue`s via a `SectionResult`.
3. Wire it into `audit.py` if it should run in a complete audit, and add a GUI
   button if it needs its own action.

See the top-of-file docstring in each module for specifics.
