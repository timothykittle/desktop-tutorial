# Configuration and Privacy

## Where files are saved

By default the tool writes next to itself:

| Folder | Contents |
|--------|----------|
| `./audits/` | Reports (HTML/JSON/CSV/log), one timestamped folder per run |
| `./site_package/` | Repaired files, location pages, content, AI-visibility data |
| `./backups/` | Byte-for-byte backups of originals before repair |

You can change the base **save location** in the GUI (the save-root field);
the CLI accepts `--output DIR` for report output.

## Settings and business profile

- **`settings.json`** — remembers GUI preferences (save root, last options).
- **`business_profile.json`** — remembers the business details you gave the
  assistant, so you don't re-enter them each session.

Both are stored locally and are **git-ignored** (they never get committed).
Delete `business_profile.json` to start fresh with a different business.

## API keys

Two optional keys unlock extra quality/quota — both are optional and stored
locally:

| Key | Enables | Get one |
|-----|---------|---------|
| **Anthropic API key** | Claude-written copy (content, prompt research) and automatic AI-visibility tracking | console.anthropic.com |
| **Google PageSpeed key** | Higher PageSpeed quota (works keyless for occasional use) | developers.google.com/speed/docs/insights/v5/get-started |

Without either key, everything still works — content falls back to templates,
and visibility tracking falls back to manual browser searches.

## Your data & privacy

- Audits of a **live URL** fetch that site's public pages (like any browser).
- **Local folder / file** audits happen entirely offline.
- Nothing about the audited site is uploaded anywhere **unless** you supply an
  API key — in which case prompt/content text is sent to that provider (Claude
  or Google) to generate results, per their terms.
- Starting a **new session** or loading a different site discards the previous
  in-memory data; only the files written to the folders above persist.

## Networking

Outbound requests (crawling, PageSpeed, Claude) go over HTTPS. If you're behind
a corporate proxy and audits fail, check the **[[Troubleshooting]]** page and
the Debug panel's network test.
