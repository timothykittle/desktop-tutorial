"""SEO Audit Pro - full-site on-page, off-page, and technical SEO auditing.

Works on ANY website, not just your own: point it at a competitor's URL, a
client's site, or a live site you're researching (SEO checks only read public
pages), or load a local folder / uploaded files to audit and repair offline.
The one exception is the security module, which sends benign probes and is
therefore scoped to a site you own or are authorized to test.

Package layout (what each module does):
  crawler      - fetches pages within one domain (respects robots.txt)
  localsite    - loads a local folder / uploaded files into the same shape
  onpage       - titles, metas, headings, content, links, images, schema
  technical    - crawlability, robots/sitemaps, HTTPS, AI-crawler access
  offpage      - visible off-page signals + user metrics + action plan
  pagespeed    - Google PageSpeed / Core Web Vitals
  security     - defensive header/TLS/exposed-file audit (authorized sites)
  logfile      - server access-log crawl-budget analysis
  issues       - shared Issue / SectionResult data model + scoring
  audit        - orchestrator that runs the sections and saves outputs
  report       - HTML / JSON / CSV / log report writers
  fixes        - ready-to-upload robots.txt / llms.txt / schema / .htaccess
  repair       - writes a corrected, upload-ready copy of the site
  verify       - re-audits the repaired copy to prove what got fixed
  backup       - byte-for-byte backup of originals before repair
  locations    - local-SEO town landing-page generator
  assistant    - chat engine: interviews the business, generates deliverables
  content      - full blog posts, service landing pages, bulk meta descriptions
  prompts      - AEO/GEO prompt research + AI-answer visibility tracking
  gitsource    - clone a repo to audit/repair and push results back
  diagnostics  - environment self-check for the GUI Debug panel
"""

__version__ = "1.0.0"
APP_NAME = "SEO Audit Pro"
