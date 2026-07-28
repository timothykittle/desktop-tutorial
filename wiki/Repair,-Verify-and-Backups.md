# Repair, Verify and Backups

The audit tells you what's wrong; the **repair engine** fixes what it safely
can and hands you an upload-ready copy of the site.

## Philosophy: conservative and reviewable

The repairer will **add** what's missing and fix what's unambiguously broken —
but it **never deletes visible content**, never overwrites your originals, and
**logs every change** with before/after so you can review before uploading.

## What repair produces

Repaired output is written to **`./site_package/`**:

- **Fixed HTML files** — corrected titles, metas, headings, alt text, viewport,
  canonical tags, schema, and more.
- **`robots.txt`** — sensible defaults that allow AI crawlers.
- **`llms.txt`** — a markdown summary that helps AI engines understand and cite
  the site.
- **`sitemap.xml`** — generated from the discovered pages.
- **A detailed change log** — every edit, with before/after values.

Review the change log, then upload the files to your host.

## Verify — proof, not promises

After repair, the **verify** step re-audits the corrected copy and compares it
against the original findings, splitting everything into:

- **Repaired (verified)** — an original issue that is now gone on re-check.
- **Needs Repair** — an original issue still present.
- **Needs Repair (manual)** — findings the on-page repairer can't touch
  (off-page, page speed, backlinks, broken external links, etc.).

This way "fixed" means *re-checked and confirmed*, not just attempted.

## Backups — a pristine safety net

Before any repair (or on demand), the tool copies **every** original file —
byte-for-byte, including files it can't parse — into a dated, sequenced backup
folder under **`./backups/`**:

```
Backup_ORIGINAL_MM-DD-YYYY     first backup of a location
Backup_2_MM-DD-YYYY            second, third, ...
Backup_3_MM-DD-YYYY
```

Because repair writes to a separate folder and never touches your source, your
originals are safe either way — the backup just makes the safety net explicit.

## Ready-to-upload fix files (without full repair)

Even without running a full repair, each audit writes standalone fix files
(recommended `robots.txt`, `llms.txt`, schema JSON-LD, an `.htaccess` snippet)
into the audit folder, so you can grab just the piece you need.
