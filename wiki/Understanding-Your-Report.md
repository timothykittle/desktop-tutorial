# Understanding Your Report

Every audit writes a timestamped folder under `./audits/` containing:

| File | What it is |
|------|-----------|
| `report.html` | The main, human-readable report (opens automatically) |
| `report.json` | The same findings as structured data (for automation) |
| `issues.csv` | One row per issue — sort/filter in a spreadsheet |
| `audit-log.txt` | The full run log |

## The overall score

Each audit produces an **overall score out of 100**. It's derived from the
issues found, weighted by severity — so a handful of critical problems hurts
far more than many minor notices.

## Severities

| Severity | Weight | Meaning |
|----------|:------:|---------|
| 🔴 **CRITICAL** | 10 | Actively hurting SEO / blocking indexing — fix first |
| 🟠 **WARNING** | 4 | Real problem, should be fixed |
| 🔵 **NOTICE** | 1 | Minor / best-practice improvement |
| 🟢 **PASSED** | 0 | The check passed — shown so you know what's healthy |

Issues are sorted worst-first, so the top of the report is your to-do list.

## Sections

A complete audit runs several sections, each returning its own findings and
sub-score:

- **On-page** — titles, meta descriptions, headings, content depth, URLs,
  images/alt text, internal linking, keyword usage, schema, viewport.
- **Technical** — crawlability, `robots.txt`, sitemaps, HTTPS, redirects,
  performance headers, and **AI-crawler access** (GPTBot, ClaudeBot,
  PerplexityBot, Google-Extended, etc.).
- **Off-page** — visible off-page signals (social profiles, NAP/local data,
  Organization schema) plus any metrics you supply, and an action plan.
- **PageSpeed** — Google Core Web Vitals (LCP, INP, CLS) for mobile & desktop.
- **Security** *(optional)* — see **[[Security Audit]]**.

Full details of each check are in **[[Checks Reference]]**.

## From findings to fixes

The report tells you *what's* wrong. To *fix* it:

- Use the ready-to-upload fix files (`robots.txt`, `llms.txt`, schema,
  `.htaccess`) written into the audit folder.
- Or run the **repair engine** to produce a corrected copy of the whole site
  and then **verify** exactly what got fixed — see
  **[[Repair, Verify and Backups]]**.
