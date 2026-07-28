# Checks Reference

What each audit section looks at. Every check returns a severity
(CRITICAL / WARNING / NOTICE / PASSED) and, where relevant, a concrete fix.

## On-page (`onpage.py`)

- **Title tags** — presence, length, duplication, keyword placement.
- **Meta descriptions** — presence, length (~155 chars), duplication.
- **Headings** — exactly one `<h1>`, logical `h2`/`h3` structure.
- **Content** — thin-content detection, word counts.
- **URLs** — length, readability, stop-word/parameter noise.
- **Images** — missing `alt` text, oversized/unnamed files.
- **Internal linking** — orphan pages, generic anchor text
  ("click here", "read more"), inbound-link counts.
- **Keywords** — usage and density for your target terms (no stuffing).
- **Schema markup** — presence and type of JSON-LD structured data.
- **Mobile** — viewport meta tag.

## Technical (`technical.py`)

- **Crawlability & indexing** — `noindex`, blocked resources, status codes.
- **`robots.txt`** — presence and sanity.
- **Sitemaps** — `sitemap.xml` presence and validity.
- **HTTPS** — secure scheme and HTTP→HTTPS redirect.
- **Performance headers** — caching/compression signals.
- **AI-crawler access** — whether major AI crawlers (GPTBot, ClaudeBot,
  PerplexityBot, Google-Extended, and more) are allowed. This drives your
  visibility in AI answers — see **[[AI Visibility (AEO-GEO)]]**.

## Off-page (`offpage.py`)

Real backlink indexes are paid services, so this section:

1. **Detects** visible off-page signals from the site itself — social profiles,
   NAP (name/address/phone), local business data, Organization schema, contact
   info.
2. **Scores** any metrics you supply (backlinks, referring domains, domain
   authority) from the GUI or CLI flags.
3. **Generates an action plan** with one-click research links (Search Console
   links report, brand-mention searches, citation checkers).

## PageSpeed (`pagespeed.py`)

- Google **PageSpeed Insights** scores for mobile and desktop.
- **Core Web Vitals**: LCP, INP, CLS, graded good / needs-improvement / poor.
- Works without an API key for occasional use; a free key raises the quota
  (see **[[Configuration and Privacy]]**).

## Security (`security.py`)

Passive, defensive checks for a site you own or are authorized to test — see
**[[Security Audit]]**.

## Server log analysis (`logfile.py`)

Feed a raw access log (Apache/Nginx common or combined format) to see which
bots — Googlebot, Bingbot, AI crawlers — hit which URLs, how often, and with
what status codes. Great for crawl-budget insight. Available via the CLI
`--log-file` flag and the GUI.
