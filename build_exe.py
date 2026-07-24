"""Build a standalone Windows .exe with PyInstaller.

Run on Windows (after `setup_windows.bat`):
    python build_exe.py
or double-click build_windows_exe.bat.

Produces dist\\SEO Audit Pro.exe - a single file you can copy anywhere and
double-click; end users do NOT need Python installed.
"""

import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(APP_DIR, "seo_audit_gui.py")


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Bundle the whole seo_audit package plus optional runtime deps.
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "SEO Audit Pro",
        "--onefile",
        "--windowed",                       # no console window
        "--collect-submodules", "seo_audit",
        "--hidden-import", "bs4",
        "--hidden-import", "requests",
        # anthropic and tkinterdnd2 are optional; include if present
        "--collect-all", "tkinterdnd2",
        ENTRY,
    ]
    # Drop --collect-all for packages that aren't installed, so the build
    # doesn't fail on optional extras.
    for opt_pkg in ("tkinterdnd2",):
        try:
            __import__(opt_pkg)
        except ImportError:
            idx = args.index("--collect-all")
            del args[idx:idx + 2]
            print(f"(optional package {opt_pkg} not installed - skipping)")

    print("Building... this takes a minute or two.")
    subprocess.check_call(args, cwd=APP_DIR)
    exe = os.path.join(APP_DIR, "dist", "SEO Audit Pro.exe")
    print(f"\nDone. Your executable is at:\n  {exe}\n"
          "Copy it anywhere and double-click to run.")


if __name__ == "__main__":
    main()
