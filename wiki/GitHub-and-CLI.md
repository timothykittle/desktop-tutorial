# GitHub and CLI

## Auditing a GitHub repository

The tool can clone a repo, audit/repair its files, and push results back
(`gitsource.py`). It uses your local `git` via subprocess, so it works with
whatever auth you already have configured.

- Supply a **personal-access token** for private repos or to push. The token is
  embedded in the remote URL only for the duration of a command and is
  **masked in all log output**.
- Pushing defaults to a **new branch** — never a force-push, never your default
  branch — so the tool can't clobber existing work.

Everything is best-effort and returns a status message rather than crashing, so
the GUI can show a friendly result.

## Command-line usage (headless)

`run_audit_cli.py` runs the same engine as the GUI — ideal for automation, CI,
or scheduled audits.

```bash
# Basic audit
python run_audit_cli.py https://example.com

# Bare domains work too
python run_audit_cli.py example.com

# Deeper crawl + target keywords
python run_audit_cli.py example.com --max-pages 50 \
    --keywords "blue widgets, widget repair"

# Skip sections you don't need
python run_audit_cli.py example.com --skip-pagespeed

# Audit local files instead of a live site
python run_audit_cli.py ./my-site-folder --local

# Analyze a server access log (crawl-budget insight)
python run_audit_cli.py --log-file access.log
```

### Options

| Flag | Purpose |
|------|---------|
| `url` | Site URL (or local path with `--local`) |
| `--max-pages N` | Crawl depth (default 30) |
| `--keywords "a, b"` | Target keywords for on-page checks |
| `--psi-key KEY` | Google PageSpeed API key |
| `--skip-pagespeed` / `--skip-onpage` / `--skip-technical` / `--skip-offpage` | Skip a section |
| `--brand NAME` | Brand name for off-page/content |
| `--backlinks` / `--referring-domains` / `--domain-authority` | Supply off-page metrics |
| `--local` | Treat `url` as a local folder/file |
| `--log-file PATH` | Analyze a server access log |
| `--output DIR` | Output base folder (default `audits`) |

Reports are written to `./audits/<domain>-<timestamp>/`, same as the GUI.
