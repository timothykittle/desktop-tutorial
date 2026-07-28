# Security Audit

The **Security audit** button runs a **defensive** check of the loaded site and
generates ready-to-upload hardening files.

> ⚠️ **Authorized targets only.** Unlike the SEO checks (which only read public
> pages and are fine for any site), the security module sends a small set of
> benign *"is this file public?"* probes. Run it only on a site you **own or are
> explicitly authorized to test.**

## What it checks (all passive)

- **HTTPS** and HTTP→HTTPS redirect.
- **TLS certificate** — reads expiry via a short handshake.
- **Security headers** — HSTS, Content-Security-Policy, X-Frame-Options,
  X-Content-Type-Options, Referrer-Policy, Permissions-Policy, and more.
- **Information disclosure** — server/version banners, exposed metadata.
- **Exposed files** — a small, fixed list of benign probes for things that
  shouldn't be public (e.g. `.env`, `.git/`, backup files).

No exploitation, no brute forcing, no authentication bypass — just
best-practice checks and concrete fixes.

## What it generates

Hardening templates written into the audit folder, including:

- **`htaccess-security.txt`** — Apache header/hardening rules to merge into your
  `.htaccess`.
- **Content-Security-Policy** guidance.

### ⚠️ Roll out CSP carefully

A wrong Content-Security-Policy can break your site (block scripts, styles,
images). The generated guidance says it explicitly: deploy CSP in
**Report-Only** mode first, load the site while watching the browser console /
violation reports, fix what breaks, and only then enforce it.

## After the audit

Fix the CRITICAL/WARNING items first (see severities in
**[[Understanding Your Report]]**), upload the hardening rules, then re-run the
audit to confirm the headers now pass.
