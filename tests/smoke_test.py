"""Offline smoke test - exercises the audit checkers and generators without any
network access, so it can run in CI on every push / pull request.

It does NOT hit a live site (the crawler needs the network). Instead it loads a
tiny in-memory HTML fixture through the same local-site loader the GUI/CLI use,
runs the on-page / technical / off-page checkers against it, and exercises the
offline template paths of the content and prompt generators.

Exit code 0 = everything ran and returned sane values; non-zero = a failure CI
should surface. Run locally with:  python tests/smoke_test.py
"""

import os
import sys
import tempfile

# Make the repo root importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seo_audit.localsite import load_local_site
from seo_audit.onpage import run_onpage_audit
from seo_audit.technical import run_technical_audit
from seo_audit.offpage import run_offpage_audit
from seo_audit import prompts as promptsmod
from seo_audit import content as contentmod
from seo_audit import assistant as assistantmod

FIXTURE = """<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acme Pest Control in Springfield | Fast, Licensed</title>
<meta name="description" content="Acme Pest Control offers licensed pest and termite service in Springfield.">
</head><body>
<h1>Pest Control in Springfield</h1>
<p>Acme Pest Control keeps Springfield homes pest-free with licensed, insured
technicians and same-day service.</p>
<h2>Our services</h2>
<ul><li>Pest control</li><li>Termite treatment</li></ul>
<a href="about.html">About us</a>
<img src="team.jpg" alt="The Acme team">
</body></html>"""

PROFILE = {
    "brand": "Acme Pest Control",
    "services": ["Pest Control", "Termite Treatment"],
    "locations": ["Springfield"],
    "city": "Springfield",
    "phone": "555-123-4567",
    "base_url": "https://acmepest.example",
}


def check(label, condition):
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        check.failed += 1
check.failed = 0


def main():
    print("SEO Audit Pro - offline smoke test")

    # 1. Load a local fixture the same way the app does.
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(FIXTURE)
    pages, inventory = load_local_site(tmp, base_url=PROFILE["base_url"])
    check("local-site loader returns pages", len(pages) >= 1)

    # 2. Run the audit checkers offline.
    onpage = run_onpage_audit(pages, {}, ["pest control"], log=lambda m: None)
    check("on-page audit returns a score 0-100", 0 <= onpage.score <= 100)
    technical = run_technical_audit(PROFILE["base_url"], pages, session=None,
                                    log=lambda m: None)
    check("technical audit returns a score 0-100", 0 <= technical.score <= 100)
    offpage = run_offpage_audit(PROFILE["base_url"], pages, manual={},
                                log=lambda m: None)
    check("off-page audit returns a score 0-100", 0 <= offpage.score <= 100)

    # 3. Prompt research (offline templates).
    research = promptsmod.research_prompts(PROFILE)
    check("prompt research produces prompts", research["count"] > 0)
    check("prompt research has clusters", len(research["clusters"]) >= 3)

    # 4. Visibility tracking in manual mode (no API key -> browser rows).
    track = promptsmod.track_visibility(research["flat"][:3], PROFILE,
                                        api_key="",
                                        history_dir=os.path.join(tmp, "track"),
                                        log=lambda m: None)
    check("tracking runs in manual mode", track["mode"] == "manual")
    check("tracking summary totals match", track["summary"]["total"] == 3)

    # 5. Content generators (offline templates).
    post = contentmod.generate_blog_post(PROFILE)
    check("blog post draft is non-trivial", len(post) > 500 and post.startswith("#"))
    page = contentmod.generate_service_page(PROFILE, "Pest Control")
    check("service page is valid-ish HTML", "<h1" in page.lower() and "</html>" in page.lower())
    metas = contentmod.generate_meta_descriptions(
        [("https://acmepest.example/", "Home | Acme")], PROFILE)
    check("meta description within 155 chars", 0 < len(metas[0]["meta"]) <= 155)

    # 6. Assistant FAQ generator (offline template path).
    faq = assistantmod.generate_faq_page(PROFILE)
    check("FAQ page generated", "<" in faq and len(faq) > 200)

    print(f"\n{'PASSED' if check.failed == 0 else 'FAILED'} "
          f"({check.failed} failure(s))")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
