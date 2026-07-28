"""Connect to GitHub: clone a repo to audit/repair, and push results back.

Uses the local `git` command via subprocess (so it works with whatever auth
the user already has configured, and with an optional token for private repos
or pushing). Everything is best-effort and returns a status dict rather than
raising, so the GUI can show a friendly message.

Security notes:
  - A personal-access token, when supplied, is embedded in the remote URL only
    for the duration of a command and is masked in all log output.
  - Pushing defaults to a NEW branch (never force, never the default branch)
    so the tool can't clobber the user's existing work.
"""

import os
import re
import shutil
import subprocess
import tempfile
from datetime import date
from urllib.parse import urlparse, urlunparse

GITHUB_URL_RE = re.compile(r"^(https://github\.com/|git@github\.com:)", re.I)


def git_available():
    return shutil.which("git") is not None


def _mask(text, token):
    return text.replace(token, "***") if token else text


def _auth_url(url, token):
    """Embed a token into an https GitHub URL: https://x-access-token:TOKEN@..."""
    if not token or not url.lower().startswith("https://"):
        return url
    p = urlparse(url)
    netloc = f"x-access-token:{token}@{p.hostname}"
    if p.port:
        netloc += f":{p.port}"
    return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))


def _run(args, cwd=None, token="", log=None, timeout=180):
    log = log or (lambda m: None)
    shown = " ".join(_mask(a, token) for a in args)
    log(f"  $ {shown}")
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, _mask(str(exc), token)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, _mask(out.strip(), token)


def clone_repo(url, dest_dir=None, token="", branch="", log=None):
    """Clone a GitHub repo (shallow) so its files can be loaded/audited.

    Returns {"ok", "dir", "error"}. `dest_dir` defaults to a fresh temp dir.
    """
    log = log or (lambda m: None)
    if not git_available():
        return {"ok": False, "dir": "", "error":
                "git is not installed. Install Git for Windows from "
                "https://git-scm.com/download/win, then try again."}
    if not GITHUB_URL_RE.match(url.strip()):
        return {"ok": False, "dir": "", "error":
                "Enter a GitHub repo URL like https://github.com/owner/repo"}
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="seoaudit_clone_")
    args = ["git", "clone", "--depth", "1"]
    if branch:
        args += ["--branch", branch]
    args += [_auth_url(url.strip(), token), dest_dir]
    log(f"Cloning {url} ...")
    ok, out = _run(args, token=token, log=log)
    if not ok:
        hint = ""
        if "authentication" in out.lower() or "denied" in out.lower() \
                or "not found" in out.lower():
            hint = ("  (For a private repo, supply a personal-access token "
                    "with 'repo' scope.)")
        return {"ok": False, "dir": dest_dir, "error": out + hint}
    log("  Clone complete.")
    return {"ok": True, "dir": dest_dir, "error": ""}


def push_folder(folder, repo_url, token="", branch="", message="", log=None):
    """Publish the contents of `folder` (e.g. the repaired site package) to a
    GitHub repo on a NEW branch. Safe by design: fresh branch, no force-push,
    never touches the default branch history.

    Returns {"ok", "branch", "error"}.
    """
    log = log or (lambda m: None)
    if not git_available():
        return {"ok": False, "branch": "", "error": "git is not installed."}
    if not os.path.isdir(folder):
        return {"ok": False, "branch": "", "error": f"No such folder: {folder}"}
    if not GITHUB_URL_RE.match((repo_url or "").strip()):
        return {"ok": False, "branch": "", "error":
                "Enter the target GitHub repo URL."}
    branch = branch or f"seo-audit-pro/repaired-{date.today():%Y-%m-%d}"
    message = message or "Add SEO Audit Pro repaired site package"

    work = tempfile.mkdtemp(prefix="seoaudit_push_")
    try:
        # Clone the target so we push a proper commit onto a new branch.
        ok, out = _run(["git", "clone", "--depth", "1",
                        _auth_url(repo_url.strip(), token), work],
                       token=token, log=log)
        if not ok:
            return {"ok": False, "branch": branch, "error": out}
        ok, _ = _run(["git", "checkout", "-b", branch], cwd=work,
                     token=token, log=log)
        if not ok:
            return {"ok": False, "branch": branch,
                    "error": f"Could not create branch {branch}."}
        # Copy the folder's contents into the repo (skip the repo's own .git).
        for name in os.listdir(folder):
            src = os.path.join(folder, name)
            dst = os.path.join(work, name)
            if name == ".git":
                continue
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        _run(["git", "add", "-A"], cwd=work, token=token, log=log)
        # Identity may be unset on a fresh machine; set a local one.
        _run(["git", "config", "user.email", "seo-audit-pro@local"],
             cwd=work, token=token, log=log)
        _run(["git", "config", "user.name", "SEO Audit Pro"],
             cwd=work, token=token, log=log)
        ok, out = _run(["git", "commit", "-m", message], cwd=work,
                       token=token, log=log)
        if not ok and "nothing to commit" in out.lower():
            return {"ok": False, "branch": branch,
                    "error": "Nothing to push - the folder is empty or identical."}
        ok, out = _run(["git", "push", "-u",
                        _auth_url(repo_url.strip(), token), branch],
                       cwd=work, token=token, log=log)
        if not ok:
            return {"ok": False, "branch": branch, "error": out}
        log(f"  Pushed to branch '{branch}'.")
        return {"ok": True, "branch": branch, "error": ""}
    finally:
        shutil.rmtree(work, ignore_errors=True)
