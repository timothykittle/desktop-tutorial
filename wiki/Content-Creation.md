# Content Creation

The **Content creation** button group turns the loaded business's details into
publish-ready pages and copy. Everything works offline from templates; with an
Anthropic API key set, the copy is genuinely written by Claude and parsed back
into the app's own templates (so the markup is always valid).

First, tell the assistant about the business (name, services, area, phone) so
the generators have real data to work with.

## What it generates

| Button | Output | Notes |
|--------|--------|-------|
| **❓ FAQ page** | `faq.html` | Q&A page with FAQ schema |
| **✍️ Blog plan (12 topics)** | `blog-plan.md` | A quarter's worth of topics/angles |
| **📝 Full blog-post draft** | `blog-<topic>.md` | 700–1000 words: snippet-friendly intro, sections, FAQ, CTA |
| **🗂️ Service landing pages** | `content/service-pages/<service>.html` | One polished page per service, with NAP |
| **🏷️ Bulk meta descriptions** | `content/meta-descriptions.csv` | A ≤155-char description for every crawled/uploaded page |

## Full blog-post draft

Prompts you for a topic (or suggests one). Produces a complete draft — not just
an outline — with an intro that answers the query in the first two sentences
(good for featured snippets and AI answers), several sections, a short FAQ, and
a call to action. Placeholders are marked `<!-- EDIT ME -->` so you know what to
localize.

## Service landing pages

Generates one SEO-structured HTML page per service the business offers, each
with a title, meta description, service list, "why choose us," an FAQ, a
call-to-action button, and a NAP block. Great raw material for the prompts
surfaced by **[[AI Visibility (AEO-GEO)]]**.

## Bulk meta descriptions

Reads the pages from your current source (crawl or upload), writes a compelling
≤155-character meta description for each, and exports them to CSV with the
current title and character count — ready to paste into your CMS.

## Also available (via the assistant)

- **Google Business Profile setup guide**
- **AI-integration guide** for the business
- **Outreach / backlink templates**

## Tip: pair with the prompt list

Generate your **[[AI Visibility (AEO-GEO)]]** prompt list first, then use these
tools to answer the highest-intent prompts directly on the site. That's the
fastest path from "audited" to "cited in AI answers."
