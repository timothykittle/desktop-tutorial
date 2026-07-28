# Auditing Any Site

SEO Audit Pro can analyze a site from four kinds of source. The SEO checks read
only public information, so auditing a **competitor** or a **client** site is
fine. (The **[[Security Audit]]** is the one exception — it sends benign probes
and is scoped to a site you own or are authorized to test.)

## 1. A live URL

Type or paste a URL into the box on the left and click **Crawl** or **COMPLETE
AUDIT**.

- **Max pages** controls how far the crawler goes (default 30). Raise it for a
  full-site audit, lower it for a quick look.
- The crawler stays on the start domain and respects `robots.txt`.

## 2. A local folder

Drag a website's folder onto the left panel, or click **Browse** and pick it.
The loader turns local files into the same structure a crawl produces, so
**every** feature works — including repair — with no network needed. Relative
links between files are resolved, so orphan-page and broken-link checks work
offline.

## 3. Uploaded individual files

Drag one or more `.html` files (or select them via **Browse**). Useful for
auditing a single page or a handful of templates.

> Drag-and-drop needs the optional `tkinterdnd2` package. Without it, use the
> **Browse** button instead.

## 4. A GitHub repository

Enter a repo URL to clone it, audit/repair the files, and optionally push the
results back to a new branch. See **[[GitHub and CLI]]**.

## Google Search Console

The **Google Search Console** button opens the right GSC reports for the site
you've loaded, so you can pull real impressions/clicks/queries alongside the
audit. GSC data requires that you have access to that property.

## What a "site" means for generated content

When you use the assistant or content tools, the business details you enter
describe **whichever site is loaded** — so a generated FAQ, blog post, or
service page is written for that site's business, whether it's yours or a
client's.

## Where results go

| Output | Folder |
|--------|--------|
| Reports (HTML/JSON/CSV/log) | `./audits/<domain>-<timestamp>/` |
| Repaired copy + fix files | `./site_package/` |
| Backups of originals | `./backups/` |

See **[[Configuration and Privacy]]** to change the save location.
