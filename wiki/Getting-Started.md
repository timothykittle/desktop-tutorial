# Getting Started

## Requirements

- **Python 3.9+** (only if running from source; the built `.exe` needs nothing).
- Two small packages: `requests` and `beautifulsoup4`.
- Optional extras that unlock more: `tkinterdnd2` (drag-and-drop uploads),
  `anthropic` (Claude-written copy), `pyinstaller` (build the `.exe`).

## Install & run (Windows, from source)

1. Double-click **`setup_windows.bat`** — it creates a virtual environment and
   installs the required packages.
2. Double-click **`run_windows.bat`** to launch the GUI.

Or from any terminal:

```bash
pip install -r requirements.txt
python seo_audit_gui.py
```

To also get drag-and-drop and Claude-enhanced copy:

```bash
pip install tkinterdnd2 anthropic
```

## Prefer a single file? Build the EXE

See **[[Building the Windows EXE]]**. The result is one
`dist/SEO Audit Pro.exe` you can copy to any Windows PC — no Python required.

## Your first audit (60 seconds)

1. Launch the app.
2. In the **left panel**, type a website into the URL box, e.g.
   `https://example.com`.
3. Click **COMPLETE AUDIT** on the right.
4. Watch the live log. When it finishes, the HTML report opens automatically.

Reports are saved under **`./audits/<domain>-<timestamp>/`**. See
**[[Understanding Your Report]]** for how to read them.

## No live site? Audit local files

Drag a website folder (or individual `.html` files) onto the left panel, or use
**Browse**. Everything works offline — including repair. See
**[[Auditing Any Site]]**.

## Optional: connect the AI assistant

Paste an Anthropic API key into the assistant/settings field to upgrade the
generated copy (FAQs, blog drafts, service pages, prompt research) from
templates to genuinely written content. Without a key, everything still works
from built-in templates. See **[[Configuration and Privacy]]**.
