"""Off-page SEO audit.

Real backlink indexes (Ahrefs/Semrush/Moz/Majestic) are paid services, so
this module does three things instead:
  1. Detects the off-page signals visible from the site itself (social
     profiles, NAP/local data, Organization schema, contact info).
  2. Accepts user-supplied metrics (backlinks, referring domains, DA) from
     the GUI and scores them.
  3. Generates a prioritized off-page action plan with direct research
     links (Google Search Console links report, brand-mention searches,
     citation checkers) the user can open with one click.
"""

import json
import re
from urllib.parse import urlparse, quote_plus

from .issues import SectionResult, CRITICAL, WARNING, NOTICE, PASSED

SOCIAL_PLATFORMS = {
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "linkedin.com": "LinkedIn",
    "x.com": "X (Twitter)",
    "twitter.com": "X (Twitter)",
    "youtube.com": "YouTube",
    "tiktok.com": "TikTok",
    "pinterest.com": "Pinterest",
}

CITATION_SITES = [
    "Google Business Profile (business.google.com)",
    "Bing Places (bingplaces.com)",
    "Apple Business Connect (businessconnect.apple.com)",
    "Yelp",
    "Facebook Business Page",
    "Better Business Bureau",
    "Industry-specific directories for your niche",
    "Local chamber of commerce / city directories",
]


def run_offpage_audit(start_url: str, pages: dict, manual: dict = None,
                      log=None) -> SectionResult:
    """manual = optional dict from the GUI:
    {backlinks, referring_domains, domain_authority, brand_name, is_local_business}
    """
    log = log or (lambda m: None)
    manual = manual or {}
    result = SectionResult("Off-Page SEO")
    domain = urlparse(start_url if "//" in start_url else f"https://{start_url}").netloc
    bare_domain = domain.removeprefix("www.")
    brand = (manual.get("brand_name") or bare_domain.split(".")[0]).strip()

    ok_pages = {u: p for u, p in pages.items() if p.ok and p.soup}

    # ---------------- Social presence detected on the site ----------------
    log("  Detecting social profiles and brand signals...")
    found_socials = {}
    for _, page in ok_pages.items():
        for href, _anchor in page.external_links:
            host = urlparse(href).netloc.lower().removeprefix("www.")
            for platform_host, name in SOCIAL_PLATFORMS.items():
                if host == platform_host or host.endswith("." + platform_host):
                    found_socials.setdefault(name, href)
    result.data["social_profiles"] = found_socials
    if found_socials:
        result.add(PASSED, "Social Signals",
                   f"Social profiles linked from the site: "
                   f"{', '.join(sorted(found_socials))}.")
    else:
        result.add(WARNING, "Social Signals",
                   "No social profile links found anywhere on the site.",
                   fix="Create/claim profiles on the platforms your audience uses "
                       "and link them in the site footer. Consistent, active "
                       "profiles support brand credibility and branded search.")

    # ---------------- Organization / LocalBusiness schema ----------------
    has_org_schema, has_local_schema, has_sameas = False, False, False
    for _, page in ok_pages.items():
        for block in page.soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(block.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                nodes = item.get("@graph") if isinstance(item.get("@graph"), list) else [item]
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    types = node.get("@type") or ""
                    types = types if isinstance(types, list) else [types]
                    types_l = [str(t).lower() for t in types]
                    if "organization" in types_l:
                        has_org_schema = True
                    if any("localbusiness" in t or t in
                           ("restaurant", "store", "dentist", "attorney",
                            "plumber", "electrician") for t in types_l):
                        has_local_schema = True
                    if node.get("sameAs"):
                        has_sameas = True
    if has_org_schema or has_local_schema:
        result.add(PASSED, "Brand Entity",
                   "Organization/LocalBusiness schema found - helps Google and AI "
                   "engines understand your brand entity.")
        if not has_sameas:
            result.add(NOTICE, "Brand Entity",
                       "Organization schema has no sameAs links to social profiles.",
                       fix="Add a sameAs array listing your official social profiles "
                           "and Wikipedia/Wikidata pages if any - it consolidates "
                           "your brand entity for search and AI engines.")
    else:
        result.add(WARNING, "Brand Entity",
                   "No Organization or LocalBusiness schema found.",
                   fix="Add Organization schema (with logo, sameAs social links) to "
                       "the homepage. For local businesses, use LocalBusiness with "
                       "name, address, phone, hours, and geo coordinates.")

    # ---------------- Local SEO / NAP ----------------
    is_local = manual.get("is_local_business")
    phone_found = any(re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}",
                                p.html) for p in ok_pages.values())
    address_found = any(p.soup.find("address") or
                        re.search(r"\b\d{5}(?:-\d{4})?\b", p.html or "")
                        for p in ok_pages.values())
    if is_local:
        if phone_found and address_found:
            result.add(PASSED, "Local Citations",
                       "NAP data (phone + address) found on the site.")
        else:
            missing = [x for x, ok in (("phone number", phone_found),
                                       ("street address", address_found)) if not ok]
            result.add(WARNING, "Local Citations",
                       f"Local business but no {' or '.join(missing)} visible on site.",
                       fix="Display your exact Name, Address, Phone (NAP) in the "
                           "footer and contact page, matching your Google Business "
                           "Profile character-for-character.")
        result.add(NOTICE, "Local Citations",
                   "Verify citations are consistent across the major directories.",
                   fix="Check NAP consistency on: " + "; ".join(CITATION_SITES) + ".")

    # ---------------- User-supplied backlink metrics ----------------
    def _to_int(value):
        try:
            return int(str(value).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    backlinks = _to_int(manual.get("backlinks"))
    ref_domains = _to_int(manual.get("referring_domains"))
    da = _to_int(manual.get("domain_authority"))

    if ref_domains is not None:
        if ref_domains < 10:
            result.add(CRITICAL, "Backlinks",
                       f"Very small backlink profile ({ref_domains} referring "
                       f"domains). Off-page authority is the biggest gap.",
                       fix="Prioritize link earning: digital PR, original data/"
                           "research, guest posts on relevant sites, supplier/"
                           "partner links, local sponsorships, and HARO/Connectively "
                           "press requests. Quality and relevance beat quantity.")
        elif ref_domains < 50:
            result.add(WARNING, "Backlinks",
                       f"Modest backlink profile ({ref_domains} referring domains).",
                       fix="Keep building relevant links steadily; analyze the "
                           "referring domains of the top 3 ranking competitors and "
                           "close the gap.")
        else:
            result.add(PASSED, "Backlinks",
                       f"{ref_domains} referring domains reported.")
    if backlinks is not None and ref_domains:
        ratio = backlinks / max(ref_domains, 1)
        if ratio > 50:
            result.add(NOTICE, "Backlinks",
                       f"High links-per-domain ratio ({ratio:.0f}:1) - profile may "
                       f"be dominated by sitewide/spammy links.",
                       fix="Review the profile for low-quality sitewide links; "
                           "diversify referring domains.")
    if da is not None:
        level = (CRITICAL if da < 10 else WARNING if da < 30 else PASSED)
        msg = (f"Domain Authority ~{da}. "
               + ("Very low - new or unlinked domain." if da < 10
                  else "Room to grow vs established competitors." if da < 30
                  else "Solid authority base."))
        result.add(level, "Domain Authority", msg,
                   fix="" if da >= 30 else
                   "Authority compounds over time: consistent publishing, digital "
                   "PR, and earning links from authoritative, topically relevant "
                   "sites. Avoid buying links.")
    if backlinks is None and ref_domains is None and da is None:
        result.add(NOTICE, "Backlinks",
                   "No backlink metrics provided - fill in the Off-Page fields "
                   "(optional) for a scored assessment.",
                   fix="Get free numbers from: Google Search Console > Links, "
                       "Bing Webmaster Tools, Moz Link Explorer (free tier), or "
                       "Ahrefs Free Webmaster Tools, then re-run the audit.")

    # ---------------- Research links (opened from the GUI/report) ----------------
    q = quote_plus(f'"{brand}" -site:{bare_domain}')
    result.data["research_links"] = {
        "GSC Links report": "https://search.google.com/search-console/links",
        "Brand mentions (Google)": f"https://www.google.com/search?q={q}",
        "Brand mentions last month":
            f"https://www.google.com/search?q={q}&tbs=qdr:m",
        "Moz Link Explorer (free)":
            f"https://moz.com/link-explorer?site={quote_plus(bare_domain)}",
        "Ahrefs free backlink checker":
            f"https://ahrefs.com/backlink-checker?target={quote_plus(bare_domain)}",
        "Google Business Profile": "https://business.google.com/",
        "Bing Webmaster Tools": "https://www.bing.com/webmasters",
    }
    result.data["brand_name"] = brand
    result.data["action_plan"] = [
        "Weekly: check Google Search Console > Links for new/lost backlinks.",
        "Monthly: search unlinked brand mentions and request a link "
        "(use the Brand Mentions button).",
        "Build 1-2 genuinely useful linkable assets per quarter "
        "(original data, tools, in-depth guides).",
        "Pitch guest posts / digital PR only to topically relevant sites - "
        "one relevant link beats ten generic ones.",
        "Local: keep NAP identical everywhere; collect Google reviews "
        "steadily and respond to all of them.",
        "Monitor reputation: set Google Alerts for your brand name.",
        "Disavow only proven toxic links; ignore random spam links otherwise.",
    ]
    return result
