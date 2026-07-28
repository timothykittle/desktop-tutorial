# Contributing to SEO Audit Pro

Thanks for helping improve the tool! This is a short guide; the full design map
is in the [wiki Architecture page](../wiki/Architecture.md).

## Project layout

- `seo_audit_gui.py` — the desktop GUI (front end only; no SEO logic).
- `run_audit_cli.py` — headless runner over the same engine.
- `seo_audit/` — all analysis lives here. Every module opens with a docstring
  explaining its job; see the package `__init__.py` for a one-line map.

## Getting set up

```bash
pip install -r requirements.txt
# optional extras:
pip install tkinterdnd2 anthropic pyinstaller

python seo_audit_gui.py         # run the GUI
python run_audit_cli.py <url>   # run the CLI
```

## Conventions

- **Keep the top-of-file docstring accurate.** Every source file must explain
  what it does; update it when behavior changes.
- **Checkers** return a `SectionResult` of `Issue`s (see `seo_audit/issues.py`),
  each with a severity. Scores are severity-weighted.
- **Generators** (content, prompts, fixes, locations) work **offline from
  templates** and optionally upgrade through `assistant.ai_enhance(prompt, key)`.
  Parse any AI output back into local templates — don't trust the model to emit
  valid markup.
- **Long work runs on a background thread**; the GUI passes a main-thread
  snapshot of inputs and communicates back via a queue, so the UI never blocks.
- **Audit any site**: the SEO checks read only public pages. The security module
  sends benign probes, so keep it scoped to authorized targets.

## Before you open a PR

- Test the affected path — a live URL *and* a local folder (the offline path)
  where relevant.
- Don't commit secrets or personal data. Runtime files (`settings.json`,
  `business_profile.json`, `audits/`, `site_package/`, `backups/`) are
  git-ignored — keep them that way.
- Update the wiki if usage or behavior changed.
- Fill in the pull request template.

## Reporting bugs / requesting features

Use the issue forms (New issue → pick a template). The bug form asks for the
diagnostics output — **Debug → Run diagnostics** in the GUI — which captures
most of what's needed to reproduce.
