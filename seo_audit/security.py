"""Defensive website security audit + hardening-file generator.

Intended for a site you own or are explicitly authorized to test. Unlike the
SEO checks (which only read public pages, fine for ANY site), the security
module also sends a small set of benign "is this file public?" probes, so it
is deliberately scoped to authorized targets. Every check here is still
passive: response-header inspection, HTML analysis of pages we already
crawled, a short socket/TLS handshake to read the certificate expiry, and
that fixed probe list. No exploitation, no brute forcing, no authentication
bypass - just best-practice checks and concrete, actionable fixes.

Mirrors the structure of technical.py: one run_*_audit function that
returns a SectionResult, plus a file generator that writes ready-to-upload
hardening templates into the audit output folder.
"""

import os
import re
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests

from .crawler import USER_AGENT
from .issues import SectionResult, CRITICAL, WARNING, NOTICE, PASSED

# Small, safe list of paths that should never be publicly readable. We do a
# single benign GET/HEAD per path - this is NOT a brute-force scan.
SENSITIVE_PATHS = [
    "/.git/config",
    "/.env",
    "/wp-config.php.bak",
    "/.htaccess",
    "/backup.zip",
    "/phpinfo.php",
    "/server-status",
]

# Signatures that make a 200 response on a sensitive path plausibly real
# (vs a themed 200 soft-404 page).
_PATH_SIGNATURES = {
    "/.git/config": ("[core]", "repositoryformatversion", "[remote"),
    "/.env": ("APP_", "DB_", "SECRET", "API_KEY", "PASSWORD", "="),
    "/wp-config.php.bak": ("DB_NAME", "DB_PASSWORD", "wp-settings", "<?php"),
    "/.htaccess": ("RewriteEngine", "RewriteRule", "Options ", "Order "),
    "/backup.zip": ("PK",),
    "/phpinfo.php": ("phpinfo()", "PHP Version", "php_uname"),
    "/server-status": ("Apache Server Status", "Server uptime", "Total accesses"),
}

# Hosts that usually indicate a third-party CDN where SRI matters.
_CDN_HINTS = ("cdn", "jsdelivr", "unpkg", "cloudflare", "cdnjs", "bootstrapcdn")

# Headers whose value leaking a version number is an information disclosure.
_VERSION_RE = re.compile(r"\d+\.\d+")


def _fetch(session, method, url, timeout, **kwargs):
    """Wrapper that never raises - returns the response or None."""
    try:
        return session.request(method, url, timeout=timeout, **kwargs)
    except requests.RequestException:
        return None


def _lower_headers(headers) -> dict:
    return {str(k).lower(): v for k, v in dict(headers or {}).items()}


def _representative_response(session, pages, origin, timeout):
    """Return (lower_headers, raw_headers, response) for a live fetch of a
    representative page, so we can inspect Set-Cookie and security headers
    exactly as the server sends them. Falls back to crawled PageData headers.
    """
    ok_pages = [p for p in pages.values() if getattr(p, "ok", False)]
    target = None
    if ok_pages:
        target = ok_pages[0].final_url or ok_pages[0].url
    target = target or origin + "/"
    resp = _fetch(session, "GET", target, timeout, allow_redirects=True)
    if resp is not None:
        return _lower_headers(resp.headers), resp, target
    # Fall back to whatever the crawler captured.
    if ok_pages:
        return _lower_headers(ok_pages[0].headers), None, ok_pages[0].url
    return {}, None, target


def _check_certificate(result, host):
    """Open a TLS socket and read the certificate's notAfter date."""
    port = 443
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            result.add(NOTICE, "TLS Certificate",
                       "Connected but could not read the certificate expiry.",
                       fix="Verify the certificate manually with your host or an "
                           "online SSL checker.")
            return
        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc)
        days_left = (expires - datetime.now(timezone.utc)).days
        if days_left < 0:
            result.add(CRITICAL, "TLS Certificate",
                       f"TLS certificate EXPIRED {abs(days_left)} day(s) ago "
                       f"({not_after}).",
                       fix="Renew the TLS certificate immediately. Enable "
                           "auto-renewal (e.g. Let's Encrypt / certbot) so it "
                           "cannot lapse again.")
        elif days_left < 21:
            result.add(WARNING, "TLS Certificate",
                       f"TLS certificate expires in {days_left} day(s) ({not_after}).",
                       fix="Renew the certificate now and enable auto-renewal so "
                           "it renews well before expiry.")
        else:
            result.add(PASSED, "TLS Certificate",
                       f"TLS certificate valid for {days_left} more day(s).")
    except Exception as exc:
        result.add(NOTICE, "TLS Certificate",
                   f"Could not verify the TLS certificate ({exc}).",
                   fix="Check the certificate manually (browser padlock, or an "
                       "SSL checker such as SSL Labs).")


def _check_security_headers(result, headers, is_https):
    """Inspect security response headers on a representative page."""
    present, missing = [], []

    def has(name):
        return name.lower() in headers

    # HSTS - CRITICAL if https and missing.
    if has("strict-transport-security"):
        result.add(PASSED, "Security Headers", "HSTS (Strict-Transport-Security) is set.")
        present.append("Strict-Transport-Security")
    elif is_https:
        result.add(CRITICAL, "Security Headers",
                   "Missing HSTS (Strict-Transport-Security) header.",
                   fix="Add 'Strict-Transport-Security: max-age=31536000; "
                       "includeSubDomains' once you are sure all subdomains are "
                       "HTTPS-only. Prevents SSL-stripping downgrade attacks.")
        missing.append("Strict-Transport-Security")

    # CSP - WARNING if missing.
    csp = headers.get("content-security-policy", "")
    if csp:
        result.add(PASSED, "Security Headers", "Content-Security-Policy is set.")
        present.append("Content-Security-Policy")
    else:
        result.add(WARNING, "Security Headers", "Missing Content-Security-Policy header.",
                   fix="Add a Content-Security-Policy (start in Report-Only mode) to "
                       "mitigate XSS and data-injection. A starter policy is in the "
                       "generated security files - TEST before enforcing.")
        missing.append("Content-Security-Policy")

    # X-Content-Type-Options: nosniff - WARNING.
    xcto = headers.get("x-content-type-options", "")
    if "nosniff" in xcto.lower():
        result.add(PASSED, "Security Headers", "X-Content-Type-Options: nosniff is set.")
        present.append("X-Content-Type-Options")
    else:
        result.add(WARNING, "Security Headers",
                   "Missing X-Content-Type-Options: nosniff header.",
                   fix="Add 'X-Content-Type-Options: nosniff' to stop browsers "
                       "MIME-sniffing responses into an unexpected content type.")
        missing.append("X-Content-Type-Options")

    # Clickjacking: X-Frame-Options OR CSP frame-ancestors - WARNING.
    xfo = headers.get("x-frame-options", "")
    if xfo or "frame-ancestors" in csp.lower():
        result.add(PASSED, "Security Headers",
                   "Clickjacking protection present (X-Frame-Options or CSP "
                   "frame-ancestors).")
        present.append("X-Frame-Options")
    else:
        result.add(WARNING, "Security Headers",
                   "No clickjacking protection (X-Frame-Options / CSP frame-ancestors).",
                   fix="Add 'X-Frame-Options: SAMEORIGIN' (or a CSP "
                       "'frame-ancestors' directive) to prevent your pages being "
                       "framed by attackers.")
        missing.append("X-Frame-Options")

    # Referrer-Policy - NOTICE.
    if has("referrer-policy"):
        result.add(PASSED, "Security Headers", "Referrer-Policy is set.")
        present.append("Referrer-Policy")
    else:
        result.add(NOTICE, "Security Headers", "Missing Referrer-Policy header.",
                   fix="Add 'Referrer-Policy: strict-origin-when-cross-origin' to "
                       "avoid leaking full URLs to third parties.")
        missing.append("Referrer-Policy")

    # Permissions-Policy - NOTICE.
    if has("permissions-policy"):
        result.add(PASSED, "Security Headers", "Permissions-Policy is set.")
        present.append("Permissions-Policy")
    else:
        result.add(NOTICE, "Security Headers", "Missing Permissions-Policy header.",
                   fix="Add a Permissions-Policy header to disable browser features "
                       "you do not use (camera, microphone, geolocation, etc.).")
        missing.append("Permissions-Policy")

    return present, missing


def _check_disclosure_headers(result, headers):
    """Flag headers that reveal the server stack / version."""
    server = headers.get("server", "")
    if server and _VERSION_RE.search(server):
        result.add(NOTICE, "Information Disclosure",
                   f"Server header reveals software version: '{server}'.",
                   fix="Set 'ServerTokens Prod' (Apache) or 'server_tokens off' "
                       "(nginx) to hide the version banner.")
    for name, header in (("X-Powered-By", "x-powered-by"),
                         ("X-AspNet-Version", "x-aspnet-version"),
                         ("X-AspNetMvc-Version", "x-aspnetmvc-version"),
                         ("X-Generator", "x-generator")):
        if header in headers:
            result.add(NOTICE, "Information Disclosure",
                       f"{name} header exposes your stack: '{headers[header]}'.",
                       fix=f"Remove/obfuscate the {name} response header so you do "
                           "not advertise the exact software an attacker could target.")


def _check_cookies(result, resp, is_https):
    """Inspect Set-Cookie headers from the representative response."""
    if resp is None:
        return
    raw = resp.raw.headers if hasattr(resp, "raw") else None
    cookies = []
    # requests folds duplicate Set-Cookie headers; use the raw urllib3 headers
    # to get each one separately when available.
    try:
        if raw is not None and hasattr(raw, "get_all"):
            cookies = raw.get_all("Set-Cookie") or []
    except Exception:
        cookies = []
    if not cookies:
        sc = resp.headers.get("Set-Cookie")
        if sc:
            cookies = [sc]
    flagged = set()
    for cookie in cookies:
        name = cookie.split("=", 1)[0].strip()
        low = cookie.lower()
        if is_https and "secure" not in low and ("secure", name) not in flagged:
            flagged.add(("secure", name))
            result.add(WARNING, "Cookies",
                       f"Cookie '{name}' is missing the Secure attribute.",
                       fix=f"Add 'Secure' to the '{name}' cookie so it is only sent "
                           "over HTTPS.")
        if "httponly" not in low and ("httponly", name) not in flagged:
            flagged.add(("httponly", name))
            result.add(WARNING, "Cookies",
                       f"Cookie '{name}' is missing the HttpOnly attribute.",
                       fix=f"Add 'HttpOnly' to the '{name}' cookie so JavaScript "
                           "cannot read it (mitigates XSS cookie theft).")
        if "samesite" not in low and ("samesite", name) not in flagged:
            flagged.add(("samesite", name))
            result.add(WARNING, "Cookies",
                       f"Cookie '{name}' is missing the SameSite attribute.",
                       fix=f"Add 'SameSite=Lax' (or Strict) to the '{name}' cookie "
                           "to mitigate CSRF.")


def _is_http_url(value: str) -> bool:
    return value.strip().lower().startswith("http://")


def _check_mixed_content(result, pages):
    """On each https page, find absolute http:// subresources."""
    reported = 0
    total_pages = 0
    for url, page in pages.items():
        if not getattr(page, "ok", False) or page.soup is None:
            continue
        base = page.final_url or page.url
        if not base.lower().startswith("https://"):
            continue
        insecure = []
        for tag, attr in (("script", "src"), ("img", "src"),
                          ("iframe", "src"), ("form", "action")):
            for el in page.soup.find_all(tag):
                val = el.get(attr)
                if val and _is_http_url(val):
                    insecure.append(val.strip())
        for el in page.soup.find_all("link", href=True):
            rels = [r.lower() for r in (el.get("rel") or [])]
            if "stylesheet" in rels and _is_http_url(el["href"]):
                insecure.append(el["href"].strip())
        if insecure:
            total_pages += 1
            if reported < 10:
                reported += 1
                result.add(WARNING, "Mixed Content",
                           f"{len(insecure)} insecure http:// resource(s) on an "
                           f"HTTPS page (e.g. {insecure[0]}).", url,
                           fix="Serve every subresource over https:// (or use "
                               "protocol-relative/https URLs). Browsers block or "
                               "warn on mixed content.")
    return total_pages


def _check_forms_and_scripts(result, pages, origin):
    """Login form hygiene, cross-domain posts, third-party script surface, SRI."""
    site_host = urlparse(origin).netloc.lower()
    third_party_hosts = set()
    cdn_without_sri = []
    for url, page in pages.items():
        if not getattr(page, "ok", False) or page.soup is None:
            continue
        base = page.final_url or page.url

        for form in page.soup.find_all("form"):
            method = (form.get("method") or "get").strip().lower()
            action = (form.get("action") or "").strip()
            action_abs = urljoin(base, action) if action else base
            has_password = form.find("input", attrs={"type": "password"}) is not None
            if has_password:
                if _is_http_url(action_abs):
                    result.add(CRITICAL, "Forms",
                               "Password/login form submits over insecure http://.",
                               url,
                               fix="Point the form action at an https:// URL. "
                                   "Submitting credentials over HTTP exposes them "
                                   "to anyone on the network.")
                elif method != "post":
                    result.add(WARNING, "Forms",
                               "Login form (has a password field) does not use "
                               "method=POST - credentials may end up in the URL/logs.",
                               url,
                               fix="Set method=\"post\" on login forms so "
                                   "credentials are not placed in the query string.")
            action_host = urlparse(action_abs).netloc.lower()
            if action and action_host and action_host != site_host:
                result.add(NOTICE, "Forms",
                           f"Form posts to a different domain ({action_host}).", url,
                           fix="Confirm this third-party form endpoint is trusted "
                               "and intended; cross-domain posts can leak form data.")

        for script in page.soup.find_all("script", src=True):
            src = script["src"].strip()
            src_abs = urljoin(base, src)
            host = urlparse(src_abs).netloc.lower()
            if host and host != site_host and not host.endswith("." + site_host):
                third_party_hosts.add(host)
                if any(h in src_abs.lower() for h in _CDN_HINTS) and \
                        not script.get("integrity"):
                    cdn_without_sri.append((url, src_abs))

    if len(third_party_hosts) >= 5:
        hosts = ", ".join(sorted(third_party_hosts)[:12])
        result.add(NOTICE, "Supply Chain",
                   f"Scripts loaded from {len(third_party_hosts)} distinct "
                   f"third-party hosts ({hosts}).",
                   fix="Minimise third-party JavaScript; each host is a supply-chain "
                       "risk. Self-host what you can and add Subresource Integrity "
                       "(SRI) to the rest.")
    seen = set()
    for url, src in cdn_without_sri:
        if src in seen:
            continue
        seen.add(src)
        result.add(NOTICE, "Supply Chain",
                   f"CDN script without Subresource Integrity: {src}", url,
                   fix="Add an 'integrity' (SRI hash) and 'crossorigin' attribute so "
                       "a compromised CDN cannot silently swap the file.")


def _check_exposed_paths(result, session, origin, timeout):
    """One benign request per sensitive path. Never a brute-force scan."""
    exposed = []
    for path in SENSITIVE_PATHS:
        url = origin + path
        resp = _fetch(session, "GET", url, timeout, allow_redirects=False,
                      stream=True)
        if resp is None:
            continue
        try:
            status = resp.status_code
            body = ""
            if status == 200:
                try:
                    body = resp.content[:2048].decode("utf-8", "ignore")
                except Exception:
                    body = ""
            resp.close()
        except Exception:
            continue
        if status == 200:
            sigs = _PATH_SIGNATURES.get(path, ())
            plausible = (not sigs) or any(s in body for s in sigs) or \
                any(s in (resp.headers.get("Content-Type", "")) for s in ("zip", "octet"))
            if plausible:
                exposed.append(path)
                result.add(CRITICAL, "Exposed Files",
                           f"Publicly accessible sensitive file: {path} (HTTP 200).",
                           url,
                           fix=f"Block public access to {path} at the web-server "
                               "level and remove it from the document root. Rotate "
                               "any secrets that were exposed.")
    return exposed


def _check_directory_listing(result, session, origin, timeout):
    """Look for Apache/nginx 'Index of /' autoindex pages."""
    for path in ("/", "/uploads/", "/images/", "/assets/", "/files/"):
        resp = _fetch(session, "GET", origin + path, timeout, allow_redirects=True)
        if resp is None or resp.status_code != 200:
            continue
        if "Index of /" in resp.text[:4000]:
            result.add(WARNING, "Directory Listing",
                       f"Directory listing (autoindex) is enabled at {path}.",
                       origin + path,
                       fix="Disable directory listing: 'Options -Indexes' (Apache) "
                           "or 'autoindex off;' (nginx).")


def _check_security_txt(result, session, origin, timeout):
    resp = _fetch(session, "GET", origin + "/.well-known/security.txt", timeout,
                  allow_redirects=True)
    if resp is not None and resp.status_code == 200 and "contact" in resp.text.lower():
        result.add(PASSED, "security.txt",
                   "A /.well-known/security.txt file is published.")
    else:
        result.add(NOTICE, "security.txt",
                   "No /.well-known/security.txt file found.",
                   fix="Publish a security.txt with a Contact: address so "
                       "researchers can report vulnerabilities responsibly. A "
                       "template is in the generated security files.")


def _check_cms_exposure(result, session, pages, origin, timeout):
    """Light WordPress/CMS exposure checks. Detection stays best-effort."""
    generator = ""
    for page in pages.values():
        if getattr(page, "ok", False) and page.soup is not None:
            meta = page.soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
            if meta and meta.get("content"):
                generator = meta["content"]
                break

    is_wp = "wordpress" in generator.lower()
    if not is_wp:
        resp = _fetch(session, "GET", origin + "/wp-login.php", timeout,
                      allow_redirects=True)
        if resp is not None and resp.status_code == 200 and \
                "user_login" in resp.text.lower():
            is_wp = True

    if generator:
        result.add(NOTICE, "CMS Exposure",
                   f"CMS/generator advertised in HTML: '{generator}'.",
                   fix="Remove the generator meta tag so you do not advertise the "
                       "exact CMS/version an attacker can target.")

    if is_wp:
        result.add(NOTICE, "CMS Exposure",
                   "WordPress detected. Harden the login.",
                   fix="Enforce strong passwords + 2FA, limit login attempts, "
                       "restrict /wp-login.php and /wp-admin by IP where possible, "
                       "and keep core/plugins/themes updated.")
        resp = _fetch(session, "GET", origin + "/wp-json/wp/v2/users", timeout,
                      allow_redirects=True)
        if resp is not None and resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                data = None
            if isinstance(data, list) and data and isinstance(data[0], dict) and \
                    ("slug" in data[0] or "name" in data[0]):
                result.add(WARNING, "CMS Exposure",
                           "WordPress REST API exposes the username list "
                           "(/wp-json/wp/v2/users) - user enumeration.",
                           origin + "/wp-json/wp/v2/users",
                           fix="Disable or restrict the users REST endpoint (a "
                               "security plugin or filter) so attackers cannot "
                               "harvest valid usernames.")


def _check_exposed_emails(result, pages):
    emails = set()
    example = ""
    for page in pages.values():
        if not getattr(page, "ok", False) or page.soup is None:
            continue
        for a in page.soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                addr = href[7:].split("?", 1)[0].strip()
                if addr:
                    emails.add(addr.lower())
                    example = example or addr
    if emails:
        result.add(NOTICE, "Information Disclosure",
                   f"{len(emails)} email address(es) exposed in mailto: links "
                   f"(e.g. {example}) - harvestable by spam bots.",
                   fix="Replace raw mailto: links with a contact form, or obfuscate "
                       "the address, to reduce spam/phishing harvesting.")


def run_security_audit(start_url, pages, session=None, log=None, timeout=15):
    """Run the defensive website security audit.

    `pages` is a dict[url -> PageData] from the crawler. Reuses the passed
    requests session when given. Returns a SectionResult named
    "Website Security".
    """
    log = log or (lambda m: None)
    result = SectionResult("Website Security")
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)

    if not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url
    parsed = urlparse(start_url)
    scheme, netloc = parsed.scheme, parsed.netloc
    host = netloc.split(":")[0]
    origin = f"{scheme}://{netloc}"
    is_https = scheme == "https"

    # ---------------- HTTPS & TLS ----------------
    log("  Checking HTTPS and TLS...")
    if not is_https:
        result.add(CRITICAL, "HTTPS", "Site is being served over HTTP, not HTTPS.",
                   fix="Install a TLS certificate and 301-redirect all HTTP traffic "
                       "to HTTPS.")
    else:
        result.add(PASSED, "HTTPS", "Site is served over HTTPS.")
        resp = _fetch(session, "GET", f"http://{netloc}/", timeout,
                      allow_redirects=True)
        if resp is not None:
            if urlparse(resp.url).scheme == "https":
                result.add(PASSED, "HTTPS", "HTTP correctly redirects to HTTPS.")
            else:
                result.add(CRITICAL, "HTTPS",
                           "HTTP does NOT redirect to HTTPS (site reachable insecurely).",
                           fix="Add a server-level 301 redirect from http:// to "
                               "https:// for every URL.")
        else:
            result.add(NOTICE, "HTTPS", "Could not test the HTTP->HTTPS redirect.")
        _check_certificate(result, host)

    # ---------------- Representative response ----------------
    log("  Inspecting security response headers...")
    headers, rep_resp, _ = _representative_response(session, pages, origin, timeout)

    present, missing = _check_security_headers(result, headers, is_https)
    _check_disclosure_headers(result, headers)
    _check_cookies(result, rep_resp, is_https)

    # ---------------- Mixed content ----------------
    log("  Scanning for mixed content...")
    mixed_pages = _check_mixed_content(result, pages)

    # ---------------- Forms & third-party scripts ----------------
    log("  Reviewing forms and third-party scripts...")
    _check_forms_and_scripts(result, pages, origin)

    # ---------------- Exposed files ----------------
    log("  Probing for publicly exposed sensitive files...")
    exposed = _check_exposed_paths(result, session, origin, timeout)

    # ---------------- Directory listing ----------------
    _check_directory_listing(result, session, origin, timeout)

    # ---------------- security.txt ----------------
    _check_security_txt(result, session, origin, timeout)

    # ---------------- CMS exposure ----------------
    log("  Checking CMS exposure...")
    _check_cms_exposure(result, session, pages, origin, timeout)

    # ---------------- Exposed emails ----------------
    _check_exposed_emails(result, pages)

    result.data["headers_present"] = {h: True for h in present}
    result.data["missing_headers"] = missing
    result.data["exposed_paths"] = exposed
    result.data["mixed_content_pages"] = mixed_pages

    return result


# ===================================================================
# Hardening-file generator
# ===================================================================

def _htaccess_security() -> str:
    return """# ==========================================================================
# Apache security hardening snippet - generated by SEO Audit Pro
# MERGE this into your existing .htaccess. DO NOT blindly overwrite yours.
# Requires mod_headers. Test on a staging copy first.
# ==========================================================================

# --- Hide server version banners --------------------------------------------
# (These two usually belong in httpd.conf; include here if your host honours
#  them in .htaccess. Otherwise ask your host to set them.)
ServerTokens Prod
ServerSignature Off

# --- Disable directory listing ----------------------------------------------
Options -Indexes

<IfModule mod_headers.c>
  # HTTPS only, for a year, including subdomains. Only enable once you are
  # certain every subdomain is HTTPS-only.
  Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"

  # Stop MIME sniffing.
  Header always set X-Content-Type-Options "nosniff"

  # Clickjacking protection.
  Header always set X-Frame-Options "SAMEORIGIN"

  # Limit referrer leakage.
  Header always set Referrer-Policy "strict-origin-when-cross-origin"

  # Minimal Permissions-Policy: disable features you almost certainly don't use.
  Header always set Permissions-Policy "geolocation=(), microphone=(), camera=(), payment=()"

  # Remove stack-revealing headers.
  Header always unset X-Powered-By
  Header unset X-Powered-By

  # ---------------------------------------------------------------------------
  # STARTER Content-Security-Policy - COMMENTED OUT ON PURPOSE.
  # A wrong CSP will break your site. Roll it out in Report-Only mode FIRST,
  # watch the violation reports, then tighten and switch to enforcing.
  # ---------------------------------------------------------------------------
  # Header always set Content-Security-Policy-Report-Only "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'self'"
  # Once verified, enforce with:
  # Header always set Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'self'"
</IfModule>

# --- Block access to sensitive dotfiles and backups -------------------------
<FilesMatch "(^\\.|\\.(env|bak|old|orig|save|swp|sql|zip|tar|gz|log|ini|htaccess|htpasswd)$)">
  Require all denied
</FilesMatch>

# Block the .git directory and other VCS metadata.
RedirectMatch 404 /\\.git(/|$)
RedirectMatch 404 /\\.svn(/|$)
RedirectMatch 404 /\\.hg(/|$)

# Block common exposed files explicitly.
<FilesMatch "^(wp-config\\.php\\.bak|phpinfo\\.php|backup\\.zip)$">
  Require all denied
</FilesMatch>
"""


def _nginx_security() -> str:
    return """# ==========================================================================
# nginx security hardening - generated by SEO Audit Pro
# Add the add_header lines inside the relevant server {} block and MERGE the
# location blocks. Reload nginx only after 'nginx -t' passes.
# ==========================================================================

# Hide the nginx version banner (http {} context).
server_tokens off;

# --- Security response headers (server {} context) --------------------------
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=(), payment=()" always;

# STARTER Content-Security-Policy - test in Report-Only FIRST, it can break the site.
# add_header Content-Security-Policy-Report-Only "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'self'" always;
# add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'self'" always;

# --- Disable directory listing ----------------------------------------------
autoindex off;

# --- Deny dotfiles (.git, .env, .htaccess, ...) -----------------------------
location ~ /\\. {
    deny all;
    return 404;
}

# --- Deny backups / sensitive extensions ------------------------------------
location ~* \\.(env|bak|old|orig|save|swp|sql|zip|tar|gz|log|ini|htaccess|htpasswd)$ {
    deny all;
    return 404;
}

# --- Deny specific commonly-exposed files -----------------------------------
location ~* ^/(wp-config\\.php\\.bak|phpinfo\\.php|backup\\.zip)$ {
    deny all;
    return 404;
}
"""


def _webconfig_security() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!--
  IIS (web.config) security hardening - generated by SEO Audit Pro.
  MERGE these nodes into your existing web.config. Back up first and test.
-->
<configuration>
  <system.webServer>

    <!-- Security response headers -->
    <httpProtocol>
      <customHeaders>
        <add name="Strict-Transport-Security" value="max-age=31536000; includeSubDomains" />
        <add name="X-Content-Type-Options" value="nosniff" />
        <add name="X-Frame-Options" value="SAMEORIGIN" />
        <add name="Referrer-Policy" value="strict-origin-when-cross-origin" />
        <add name="Permissions-Policy" value="geolocation=(), microphone=(), camera=(), payment=()" />
        <!-- STARTER CSP - test in Report-Only first; a wrong CSP breaks the site.
        <add name="Content-Security-Policy-Report-Only" value="default-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'self'" />
        -->
        <!-- Remove stack-revealing headers -->
        <remove name="X-Powered-By" />
      </customHeaders>
    </httpProtocol>

    <!-- Disable directory browsing -->
    <directoryBrowse enabled="false" />

    <security>
      <requestFiltering removeServerHeader="true">
        <!-- Block sensitive segments/paths -->
        <hiddenSegments>
          <add segment=".git" />
          <add segment=".svn" />
          <add segment=".env" />
        </hiddenSegments>
        <!-- Block sensitive file extensions -->
        <fileExtensions>
          <add fileExtension=".bak" allowed="false" />
          <add fileExtension=".env" allowed="false" />
          <add fileExtension=".config" allowed="false" />
          <add fileExtension=".sql" allowed="false" />
          <add fileExtension=".old" allowed="false" />
        </fileExtensions>
      </requestFiltering>
    </security>

  </system.webServer>
</configuration>
"""


def _security_txt(origin: str) -> str:
    return f"""# /.well-known/security.txt - generated by SEO Audit Pro
# Host this file at: {origin}/.well-known/security.txt
# Spec: https://securitytxt.org  (RFC 9116)
# Fill in the EDIT-ME values below, then publish over HTTPS.

Contact: mailto:security@EDIT-ME-your-domain.com
# You may list more than one Contact (email, form URL, or phone):
# Contact: https://EDIT-ME-your-domain.com/security-contact

# Expires MUST be a future date (ISO 8601). Update before it lapses.
Expires: EDIT-ME-2027-01-01T00:00:00.000Z

# Optional but recommended:
# Encryption: {origin}/pgp-key.txt
# Acknowledgments: {origin}/security-thanks
Policy: {origin}/security-policy
Preferred-Languages: en
"""


def _security_readme(origin: str) -> str:
    return f"""WEBSITE SECURITY HARDENING FILES
================================
Generated by SEO Audit Pro for {origin}

These are best-practice DEFENSIVE templates for a site you own. Review, edit
the EDIT-ME placeholders, and apply the file that matches YOUR web server.
Always merge into existing config - never blindly overwrite - and test on a
staging copy first.

FILES
-----
1. htaccess-security.txt   -> Apache. Merge into your site's .htaccess.
                              Sets security headers, hides version banners,
                              disables directory listing (Options -Indexes),
                              and blocks .git/.env/.htaccess/backup files.

2. nginx-security.conf     -> nginx. Add the add_header lines to your
                              server {{}} block and merge the location blocks.
                              Run 'nginx -t' before reloading.

3. web.config-security.xml -> IIS. Merge the nodes into your web.config
                              (customHeaders + requestFiltering hiddenSegments).

4. security.txt            -> Publish at {origin}/.well-known/security.txt so
                              researchers can report issues responsibly.

5. SECURITY-README.txt     -> This file.

IMPORTANT: CONTENT-SECURITY-POLICY
----------------------------------
The starter Content-Security-Policy in each file is COMMENTED OUT on purpose.
A wrong CSP will break your site (block scripts, styles, images).
  1. Enable it first in REPORT-ONLY mode
     (Content-Security-Policy-Report-Only).
  2. Load your site, watch the browser console / violation reports.
  3. Adjust the policy until there are no legitimate violations.
  4. Only then switch to the enforcing Content-Security-Policy header.

VERIFY YOUR CHANGES
-------------------
After applying, re-test with:
  - https://observatory.mozilla.org/   (Mozilla Observatory)
  - https://securityheaders.com/        (securityheaders.com)

These graders confirm your headers are present and well-formed.
"""


def generate_security_files(output_dir, start_url, findings_section=None):
    """Write ready-to-upload hardening files into <output_dir>/security/.

    Returns {"written": [paths]}.
    """
    if not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url
    p = urlparse(start_url)
    origin = f"{p.scheme}://{p.netloc}"

    sec_dir = os.path.join(output_dir, "security")
    os.makedirs(sec_dir, exist_ok=True)

    files = {
        "htaccess-security.txt": _htaccess_security(),
        "nginx-security.conf": _nginx_security(),
        "web.config-security.xml": _webconfig_security(),
        "security.txt": _security_txt(origin),
        "SECURITY-README.txt": _security_readme(origin),
    }

    written = []
    for name, content in files.items():
        path = os.path.join(sec_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        written.append(path)
    return {"written": written}
