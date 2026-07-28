# Building the Windows EXE

Ship SEO Audit Pro as a single `.exe` that runs on any Windows PC — the end
user does **not** need Python installed.

## Steps

1. On Windows, run **`setup_windows.bat`** once (creates the environment and
   installs dependencies).
2. Double-click **`build_windows_exe.bat`**, or run:

   ```bash
   python build_exe.py
   ```

3. The result is **`dist/SEO Audit Pro.exe`** — a single file you can copy
   anywhere and double-click.

## Requirements

- `pyinstaller` (installed by `setup_windows.bat`, or `pip install pyinstaller`).
- Build **on Windows** to produce a Windows `.exe` (PyInstaller is not a
  cross-compiler).

## What ends up in the build

The build bundles the `seo_audit` package and the GUI. Optional extras behave
the same as when running from source:

- If `anthropic` is installed at build time, Claude-enhanced copy is available
  in the `.exe` (users still supply their own API key at runtime).
- If `tkinterdnd2` is installed, drag-and-drop uploads work.

## Distributing

Copy the single `.exe` to any Windows machine. On first run it will create its
working folders (`audits/`, `site_package/`, `backups/`) next to itself — see
**[[Configuration and Privacy]]** for where data is stored and how to change it.
