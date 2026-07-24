"""Self-diagnostics for the GUI's Debug panel.

Checks the runtime environment, optional dependencies, network/proxy access,
write permissions, and module imports, then returns a plain-text report the
GUI can show and save. Used to troubleshoot "it won't run" / "a button did
nothing" problems without needing a developer.
"""

import os
import platform
import socket
import sys
import time
from datetime import datetime

CHECK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"


def _line(status, label, detail=""):
    return f"  {status}  {label}" + (f"  -  {detail}" if detail else "")


def run_diagnostics(app_dir, audits_dir, package_dir, log=None) -> str:
    """Return a multi-line diagnostics report. `log` is an optional
    callable(str) that receives each line as it's produced."""
    out = []

    def emit(s):
        out.append(s)
        if log:
            log(s)

    emit("=" * 58)
    emit("SEO Audit Pro - Diagnostics")
    emit(f"Time: {datetime.now().isoformat(timespec='seconds')}")
    emit("=" * 58)

    # --- Python / platform ---
    emit("\nEnvironment:")
    emit(_line(CHECK, "Python", sys.version.split()[0]))
    emit(_line(CHECK, "Platform", f"{platform.system()} {platform.release()}"))
    emit(_line(CHECK, "Executable", sys.executable))
    frozen = getattr(sys, "frozen", False)
    emit(_line(CHECK if not frozen else CHECK, "Running as",
               "packaged .exe" if frozen else "Python script"))

    # --- Required dependencies ---
    emit("\nRequired libraries:")
    for mod, why in [("requests", "HTTP / crawling"),
                     ("bs4", "HTML parsing"),
                     ("tkinter", "the GUI itself")]:
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "")
            emit(_line(CHECK, mod, f"{why} ({ver})" if ver else why))
        except Exception as exc:
            emit(_line(FAIL, mod, f"MISSING - {why}. Run setup_windows.bat. ({exc})"))

    # --- Optional dependencies ---
    emit("\nOptional libraries (extra features):")
    for mod, why in [("tkinterdnd2", "drag-and-drop upload"),
                     ("anthropic", "AI-written copy via Claude"),
                     ("PyInstaller", "building the .exe")]:
        try:
            __import__(mod)
            emit(_line(CHECK, mod, why))
        except Exception:
            emit(_line(WARN, mod, f"not installed - {why} disabled "
                                  f"(pip install {mod})"))

    # --- Internal modules ---
    emit("\nApplication modules:")
    for mod in ["seo_audit.crawler", "seo_audit.onpage", "seo_audit.technical",
                "seo_audit.offpage", "seo_audit.pagespeed", "seo_audit.logfile",
                "seo_audit.report", "seo_audit.fixes", "seo_audit.audit",
                "seo_audit.localsite", "seo_audit.repair", "seo_audit.locations",
                "seo_audit.assistant"]:
        try:
            __import__(mod)
            emit(_line(CHECK, mod))
        except Exception as exc:
            emit(_line(FAIL, mod, f"import error: {exc}"))
    # security module is optional / newer
    try:
        __import__("seo_audit.security")
        emit(_line(CHECK, "seo_audit.security"))
    except Exception as exc:
        emit(_line(WARN, "seo_audit.security", f"not available: {exc}"))

    # --- Write permissions ---
    emit("\nFolders (need write access for reports & builds):")
    for label, path in [("app dir", app_dir), ("audits", audits_dir),
                        ("site_package", package_dir)]:
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".write_test")
            with open(probe, "w") as fh:
                fh.write("ok")
            os.remove(probe)
            emit(_line(CHECK, label, path))
        except Exception as exc:
            emit(_line(FAIL, label, f"NOT writable: {path} ({exc})"))

    # --- Network ---
    emit("\nNetwork (needed to audit live sites & call APIs):")
    _net_check(emit)

    # --- Proxy / env ---
    emit("\nProxy / environment:")
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "ANTHROPIC_API_KEY"):
        val = os.environ.get(var)
        if var == "ANTHROPIC_API_KEY":
            emit(_line(CHECK if val else WARN, var,
                       "set" if val else "not set (AI copy uses templates)"))
        else:
            emit(_line(CHECK, var, val or "(none)"))

    emit("\nDiagnostics complete. If any [FAIL] lines appear above, fix those "
         "first. Attach this report when asking for help.")
    return "\n".join(out)


def _net_check(emit):
    try:
        import requests
    except Exception:
        emit(_line(FAIL, "requests", "cannot test network - library missing"))
        return
    for name, url in [("example.com", "https://example.com"),
                      ("Google PageSpeed API",
                       "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
                       "?url=https://example.com&strategy=mobile")]:
        try:
            t = time.time()
            r = requests.get(url, timeout=12)
            ms = int((time.time() - t) * 1000)
            status = CHECK if r.status_code < 500 else WARN
            emit(_line(status, name, f"HTTP {r.status_code} in {ms} ms"))
        except Exception as exc:
            emit(_line(WARN, name, f"unreachable: {exc}"))
    # DNS
    try:
        socket.gethostbyname("example.com")
        emit(_line(CHECK, "DNS resolution", "working"))
    except Exception as exc:
        emit(_line(FAIL, "DNS resolution", str(exc)))
