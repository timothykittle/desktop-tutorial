# Troubleshooting

## Use the Debug panel first

The GUI has a **Debug** section with a **Run diagnostics** button. It checks:

- Python version and platform.
- Whether optional packages (`tkinterdnd2`, `anthropic`, `pyinstaller`) are
  installed.
- Network/proxy access.
- Write permissions for the output folders.
- That every internal module imports cleanly.

It prints a plain-text report you can **save to a file** (and a **Copy last
error** button) — the fastest way to diagnose "it won't run" or "a button did
nothing." Turn on **Verbose logging** to see more detail in the live log.

## Common issues

**Drag-and-drop does nothing.**
Install the optional package: `pip install tkinterdnd2`, or use the **Browse**
button instead.

**Generated copy is generic / template-like.**
That's the offline fallback. Add an Anthropic API key to get Claude-written
content — see **[[Configuration and Privacy]]**.

**AI-visibility tracking only opens browser searches.**
That's manual mode (no API key). Add an Anthropic API key for automatic
cited/mentioned/absent classification — see
**[[AI Visibility (AEO-GEO)]]**.

**PageSpeed fails or is rate-limited.**
Keyless requests have tight limits. Add a free Google PageSpeed key, or use
`--skip-pagespeed`.

**Crawl returns very few pages.**
Raise **Max pages**, and check the site's `robots.txt` isn't blocking the
crawler. Some pages may be JavaScript-rendered (the crawler reads server HTML).

**A live audit fails but local files work.**
Likely a network/proxy problem — run diagnostics and check the network test.

**The `.exe` won't build.**
Build on Windows with `pyinstaller` installed — see
**[[Building the Windows EXE]]**.

**Push to GitHub failed.**
Provide a personal-access token for private repos/pushing; pushes go to a new
branch by design — see **[[GitHub and CLI]]**.

## Still stuck?

Save the diagnostics report and the `audit-log.txt` from the affected run —
together they capture almost everything needed to pinpoint the problem.
