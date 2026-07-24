"""Local-SEO location page generator with a New York gazetteer.

Turns a plain-English service area ("Suffolk County", "NYC and Long
Island") into a concrete town list, then writes one unique, upload-ready
landing page per town under <output>/areas-served/<town-slug>/index.html,
plus a hub page and a paste-in footer nav snippet. Unknown place names
are kept as-is so any US business can list its own towns.
"""

import hashlib
import html
import json
import os
import re

# --------------------------------------------------------------------------
# PART 1 - gazetteer data
# --------------------------------------------------------------------------


def _dedupe(names):
    """Order-preserving de-duplication (case-insensitive)."""
    seen, out = set(), []
    for name in names:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(name.strip())
    return out


_SUFFOLK_TOWNS = [
    "Babylon", "Brookhaven", "East Hampton", "Huntington", "Islip",
    "Riverhead", "Shelter Island", "Smithtown", "Southampton", "Southold",
]

_SUFFOLK_COMMUNITIES = [
    "Amityville", "Bay Shore", "Bohemia", "Brentwood", "Centereach",
    "Commack", "Copiague", "Deer Park", "Dix Hills", "East Islip",
    "East Northport", "Farmingville", "Hauppauge", "Holbrook", "Holtsville",
    "Kings Park", "Lake Grove", "Lindenhurst", "Medford", "Melville",
    "Miller Place", "Mount Sinai", "Nesconset", "Northport", "Patchogue",
    "Port Jefferson", "Ronkonkoma", "Sayville", "Selden", "Shirley",
    "Stony Brook", "West Babylon", "West Islip", "Wyandanch",
]

_NASSAU_TOWNS = [
    "Hempstead", "North Hempstead", "Oyster Bay", "Glen Cove", "Long Beach",
]

_NASSAU_COMMUNITIES = [
    "Baldwin", "Bellmore", "Bethpage", "East Meadow", "Elmont",
    "Farmingdale", "Franklin Square", "Freeport", "Garden City",
    "Great Neck", "Hicksville", "Levittown", "Lynbrook", "Massapequa",
    "Merrick", "Mineola", "New Hyde Park", "Oceanside", "Plainview",
    "Port Washington", "Rockville Centre", "Roslyn", "Seaford", "Syosset",
    "Uniondale", "Valley Stream", "Wantagh", "Westbury",
]

_SUFFOLK = _dedupe(_SUFFOLK_TOWNS + _SUFFOLK_COMMUNITIES)
_NASSAU = _dedupe(_NASSAU_TOWNS + _NASSAU_COMMUNITIES)

_BOROUGHS = ["Manhattan", "Brooklyn", "Queens", "The Bronx", "Staten Island"]

_BROOKLYN_NEIGHBORHOODS = [
    "Williamsburg", "Greenpoint", "Bushwick", "Bedford-Stuyvesant",
    "Crown Heights", "Park Slope", "Prospect Heights", "Fort Greene",
    "Clinton Hill", "Brooklyn Heights", "DUMBO", "Downtown Brooklyn",
    "Cobble Hill", "Carroll Gardens", "Red Hook", "Sunset Park",
    "Bay Ridge", "Bensonhurst", "Borough Park", "Flatbush", "Midwood",
    "Sheepshead Bay", "Brighton Beach", "Coney Island", "Canarsie",
]

_QUEENS_NEIGHBORHOODS = [
    "Astoria", "Long Island City", "Sunnyside", "Woodside",
    "Jackson Heights", "Elmhurst", "Corona", "Flushing", "Forest Hills",
    "Rego Park", "Kew Gardens", "Jamaica", "Ridgewood", "Maspeth",
    "Middle Village", "Glendale", "Bayside", "Whitestone", "College Point",
    "Fresh Meadows", "Ozone Park", "Howard Beach", "Richmond Hill",
    "Woodhaven", "Rockaway Beach",
]

_MANHATTAN_NEIGHBORHOODS = [
    "Financial District", "Tribeca", "SoHo", "Greenwich Village",
    "West Village", "East Village", "Lower East Side", "Chinatown",
    "Chelsea", "Flatiron District", "Gramercy", "Midtown",
    "Hell's Kitchen", "Murray Hill", "Upper East Side", "Upper West Side",
    "Morningside Heights", "Harlem", "East Harlem", "Washington Heights",
    "Inwood", "NoHo",
]

_BRONX_NEIGHBORHOODS = [
    "Riverdale", "Kingsbridge", "Fordham", "Belmont", "Morris Park",
    "Pelham Bay", "Throgs Neck", "City Island", "Parkchester",
    "Soundview", "Hunts Point", "Mott Haven", "Melrose", "Morrisania",
    "Concourse", "Highbridge", "Tremont", "University Heights", "Norwood",
    "Wakefield", "Williamsbridge", "Co-op City",
]

_STATEN_ISLAND_NEIGHBORHOODS = [
    "St. George", "Tompkinsville", "Stapleton", "New Brighton",
    "West Brighton", "Port Richmond", "Mariners Harbor", "Westerleigh",
    "New Dorp", "Great Kills", "Eltingville", "Annadale", "Tottenville",
    "Huguenot", "Richmondtown", "Todt Hill", "Grasmere", "Dongan Hills",
    "Midland Beach", "South Beach",
]

_WESTCHESTER = [
    "Yonkers", "White Plains", "New Rochelle", "Mount Vernon", "Scarsdale",
    "Rye", "Harrison", "Mamaroneck", "Port Chester", "Peekskill",
    "Ossining", "Tarrytown", "Dobbs Ferry", "Hastings-on-Hudson",
    "Bronxville", "Larchmont", "Pelham", "Croton-on-Hudson", "Yorktown",
    "Somers",
]

# Normalized lookup key -> list of place names it expands to.
NY_GAZETTEER = {
    "suffolk county": _SUFFOLK,
    "nassau county": _NASSAU,
    "long island": _dedupe(_SUFFOLK + _NASSAU),
    "nyc": _BOROUGHS,
    "new york city": _BOROUGHS,
    "five boroughs": _BOROUGHS,
    "brooklyn": _BROOKLYN_NEIGHBORHOODS,
    "queens": _QUEENS_NEIGHBORHOODS,
    "manhattan": _MANHATTAN_NEIGHBORHOODS,
    "the bronx": _BRONX_NEIGHBORHOODS,
    "bronx": _BRONX_NEIGHBORHOODS,
    "staten island": _STATEN_ISLAND_NEIGHBORHOODS,
    "westchester county": _WESTCHESTER,
}

# Display names for boroughs when they appear as one term among several
# (e.g. inside an "nyc" expansion) rather than as the whole query.
_BOROUGH_DISPLAY = {
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "manhattan": "Manhattan",
    "the bronx": "The Bronx",
    "bronx": "The Bronx",
    "staten island": "Staten Island",
}

# All 62 New York State counties (used by the clarify prompt).
NY_COUNTIES = [
    "Albany", "Allegany", "Bronx", "Broome", "Cattaraugus", "Cayuga",
    "Chautauqua", "Chemung", "Chenango", "Clinton", "Columbia", "Cortland",
    "Delaware", "Dutchess", "Erie", "Essex", "Franklin", "Fulton",
    "Genesee", "Greene", "Hamilton", "Herkimer", "Jefferson", "Kings",
    "Lewis", "Livingston", "Madison", "Monroe", "Montgomery", "Nassau",
    "New York", "Niagara", "Oneida", "Onondaga", "Ontario", "Orange",
    "Orleans", "Oswego", "Otsego", "Putnam", "Queens", "Rensselaer",
    "Richmond", "Rockland", "St. Lawrence", "Saratoga", "Schenectady",
    "Schoharie", "Schuyler", "Seneca", "Steuben", "Suffolk", "Sullivan",
    "Tioga", "Tompkins", "Ulster", "Warren", "Washington", "Wayne",
    "Westchester", "Wyoming", "Yates",
]

# Terms that mean "the whole state" - too broad to generate pages for.
_STATE_TERMS = {
    "ny", "n.y.", "nys", "new york", "new york state", "ny state",
    "state of new york", "upstate", "upstate ny", "upstate new york",
}

MAX_LOCATIONS = 120


# --------------------------------------------------------------------------
# PART 2 - resolution
# --------------------------------------------------------------------------


def _normalize_term(term: str) -> str:
    """Lowercase/strip a raw term, drop trailing NY qualifiers, and
    expand 'co.'/'co' abbreviations to 'county'."""
    t = re.sub(r"\s+", " ", term.strip().lower()).strip(" .,-")
    # Drop a trailing state qualifier, but never reduce the term to nothing
    # ("new york" alone must survive so it can trigger the clarify path).
    for suffix in (" new york state", " ny state", " new york", " nys",
                   " n.y.", " ny"):
        if t.endswith(suffix) and t[: -len(suffix)].strip(" .,-"):
            t = t[: -len(suffix)].strip(" .,-")
            break
    t = re.sub(r"\bco\.?$", "county", t)
    return t


def _split_terms(query: str) -> list:
    """Split a query on commas, ampersands, plus signs and ' and '."""
    parts = re.split(r",|;|&|\+|\band\b", query, flags=re.I)
    return [p for p in (part.strip() for part in parts) if p]


def _title_case(term: str) -> str:
    """Title-case a literal town name, keeping small joining words lower."""
    small = {"of", "on", "the", "at", "by", "in"}
    words = term.split()
    out = []
    for i, word in enumerate(words):
        low = word.lower()
        if 0 < i < len(words) - 1 and low in small:
            out.append(low)
        else:
            out.append("-".join(w[:1].upper() + w[1:] for w in word.split("-")))
    return " ".join(out)


def resolve_locations(query: str) -> dict:
    """Resolve a plain-English service-area query into a town list.

    Returns {"status": "ok"|"clarify", "locations": [names], "message": str}.
    """
    raw_terms = _split_terms(query or "")
    terms = [_normalize_term(t) for t in raw_terms]
    terms = [t for t in terms if t]

    if not terms:
        return {
            "status": "clarify",
            "locations": [],
            "message": "No location given. Name the counties, regions, or "
                       "towns you serve (e.g. 'Suffolk County', 'NYC and "
                       "Long Island', or a comma-separated town list).",
        }

    state_terms = [t for t in terms if t in _STATE_TERMS]
    place_terms = [t for t in terms if t not in _STATE_TERMS]

    if state_terms and not place_terms:
        shown = ", ".join(NY_COUNTIES[:20])
        return {
            "status": "clarify",
            "locations": [],
            "message": (
                "'New York' covers the whole state - too broad for useful "
                "location pages. Please narrow it down: name specific "
                "counties, regions (e.g. Long Island, NYC, Westchester "
                "County), or a list of cities/towns. NY counties include: "
                f"{shown}, ... ({len(NY_COUNTIES)} counties total)."
            ),
        }

    # Whole query is exactly one borough -> expand to its neighborhoods.
    single_borough = len(place_terms) == 1 and place_terms[0] in _BOROUGH_DISPLAY

    locations, unknown, notes = [], [], []
    for term in place_terms:
        key = term if term in NY_GAZETTEER else (
            term + " county" if term + " county" in NY_GAZETTEER else term)
        if key in _BOROUGH_DISPLAY and not single_borough:
            # Part of a larger query: keep the borough as a single page.
            locations.append(_BOROUGH_DISPLAY[key])
        elif key in NY_GAZETTEER:
            locations.extend(NY_GAZETTEER[key])
        else:
            name = _title_case(term)
            locations.append(name)
            unknown.append(name)

    locations = _dedupe(locations)
    if unknown:
        notes.append(
            "Not in the built-in NY gazetteer, kept as custom town names: "
            + ", ".join(unknown) + ".")
    if state_terms:
        notes.append("Ignored state-level qualifier(s): "
                     + ", ".join(sorted(set(state_terms))) + ".")
    if len(locations) > MAX_LOCATIONS:
        notes.append(f"List truncated from {len(locations)} to "
                     f"{MAX_LOCATIONS} locations.")
        locations = locations[:MAX_LOCATIONS]

    message = f"Resolved {len(locations)} location(s)."
    if notes:
        message += " " + " ".join(notes)
    return {"status": "ok", "locations": locations, "message": message}


# --------------------------------------------------------------------------
# PART 3 - page generation
# --------------------------------------------------------------------------

_PAGE_CSS = """
    * { box-sizing: border-box; }
    body { margin: 0; font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
           color: #1f2937; line-height: 1.65; background: #f8fafc; }
    header.site { background: #0f3557; color: #fff; padding: 28px 20px; }
    header.site .wrap, main, footer.site .wrap {
        max-width: 860px; margin: 0 auto; padding: 0 20px; }
    header.site h1 { margin: 0 0 6px; font-size: 1.9em; line-height: 1.25; }
    header.site p.tagline { margin: 0; opacity: .9; }
    main { padding: 28px 20px 40px; }
    section { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
              padding: 22px 26px; margin-bottom: 22px; }
    h2 { color: #0f3557; margin-top: 0; font-size: 1.3em; }
    ul { padding-left: 22px; }
    li { margin-bottom: 6px; }
    a { color: #0b62b8; }
    .cta { background: #0f3557; color: #fff; text-align: center; }
    .cta h2 { color: #fff; }
    .cta a.btn { display: inline-block; background: #f59e0b; color: #1f2937;
                 font-weight: 700; padding: 13px 30px; border-radius: 8px;
                 text-decoration: none; margin-top: 8px; }
    .nap { font-style: normal; }
    .nap strong { display: block; font-size: 1.05em; }
    footer.site { background: #0f3557; color: #dbe6f1; padding: 22px 20px;
                  font-size: .92em; }
    footer.site a { color: #fff; }
    nav.crumbs { font-size: .9em; margin-bottom: 18px; }
    .towns { columns: 3; column-gap: 28px; }
    @media (max-width: 640px) {
        header.site h1 { font-size: 1.45em; }
        section { padding: 16px 18px; }
        .towns { columns: 1; }
    }
""".rstrip()

_INTRO_TEMPLATES = [
    ("Looking for dependable {service_l} in {town}? {brand} has you "
     "covered. We know {town} well - its homes, its businesses, and the "
     "problems its property owners face - and we bring that local "
     "knowledge to every job. When you call, you get a team that treats "
     "{town} like its own backyard."),
    ("{brand} is proud to provide {service_l} throughout {town}, {st}. "
     "From quick one-off visits to ongoing service plans, our technicians "
     "arrive on time, explain exactly what they find, and get the job "
     "done right the first time. Ask your neighbors in {town} - our "
     "reputation is built on repeat customers."),
    ("Home and business owners in {town} choose {brand} because we make "
     "{service_l} simple: honest pricing, clear communication, and work "
     "that holds up. Whether you are near the center of {town} or on its "
     "quieter side streets, we are only a short drive away."),
    ("When {town} residents need {service_l}, they want a company that "
     "answers the phone and shows up. That is {brand}. We have served "
     "the {town} area for years, and we back every visit with a "
     "satisfaction guarantee - no shortcuts, no surprises."),
]

_WHY_US_TEMPLATES = [
    ("<ul><li>Local team that knows {town} and gets there fast</li>"
     "<li>Up-front, honest pricing - no surprise fees</li>"
     "<li>Licensed, insured, and background-checked technicians</li>"
     "<li>Workmanship backed by a satisfaction guarantee</li></ul>"),
    ("<ul><li>Fast response times across {town} and nearby areas</li>"
     "<li>Clear written estimates before any work begins</li>"
     "<li>Friendly, uniformed pros who respect your property</li>"
     "<li>Hundreds of happy customers across the region</li></ul>"),
    ("<ul><li>Years of hands-on experience serving {town} properties</li>"
     "<li>Modern equipment and proven, safe methods</li>"
     "<li>Flexible scheduling, including same-week appointments</li>"
     "<li>We stand behind every job - period</li></ul>"),
]

_CTA_TEMPLATES = [
    ("Ready for {service_l} in {town}? Call {brand} now at "
     "<a class=\"btn\" href=\"tel:{tel}\">{phone}</a> for a free, "
     "no-obligation estimate."),
    ("Get your free {town} quote today - speak with a real person at "
     "{brand}. <a class=\"btn\" href=\"tel:{tel}\">Call {phone}</a>"),
    ("Don't wait for the problem to grow. {brand} serves {town} "
     "{st_full} - <a class=\"btn\" href=\"tel:{tel}\">Tap to call "
     "{phone}</a> and book your visit."),
]

_STATE_NAMES = {"NY": "New York", "NJ": "New Jersey", "CT": "Connecticut",
                "PA": "Pennsylvania", "MA": "Massachusetts", "FL": "Florida",
                "CA": "California", "TX": "Texas"}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _town_hash(town: str) -> int:
    return int(hashlib.md5(town.lower().encode("utf-8")).hexdigest(), 16)


def _page_title(service: str, town: str, st: str, brand: str) -> str:
    """Build '<Service> in <Town>, <ST> | <Brand>' capped at 60 chars,
    shortening the service name (then dropping the brand) if needed."""
    title = f"{service} in {town}, {st} | {brand}"
    if len(title) <= 60:
        return title
    words = service.split()
    while len(words) > 1:
        words = words[:-1]
        title = f"{' '.join(words)} in {town}, {st} | {brand}"
        if len(title) <= 60:
            return title
    title = f"{service} in {town}, {st}"
    if len(title) <= 60:
        return title
    return title[:57].rstrip() + "..."


def _meta_description(service: str, town: str, st: str, brand: str,
                      phone: str) -> str:
    desc = (f"{brand} provides trusted {service.lower()} in {town}, {st}. "
            f"Fast response, honest pricing, satisfaction guaranteed."
            + (f" Call {phone} for a free estimate." if phone else ""))
    if len(desc) > 158:
        desc = desc[:155].rstrip(" .,") + "..."
    return desc


def _jsonld(business: dict, town: str, base_url: str) -> str:
    brand = business.get("brand") or "Your Business"
    schema = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": brand,
        "description": business.get("description")
        or f"{brand} - serving {town} and surrounding communities.",
        "telephone": business.get("phone") or "",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": business.get("street") or "",
            "addressLocality": business.get("city") or "",
            "addressRegion": business.get("state") or "NY",
            "postalCode": business.get("zip") or "",
            "addressCountry": "US",
        },
        "areaServed": {"@type": "City", "name": town},
    }
    if base_url:
        schema["url"] = base_url.rstrip("/") + "/"
    socials = business.get("socials") or {}
    if isinstance(socials, dict) and socials:
        schema["sameAs"] = list(socials.values())
    return ('<script type="application/ld+json">\n'
            + json.dumps(schema, indent=2)
            + "\n</script>")


def _services_list(business: dict, service: str) -> list:
    services = business.get("services")
    if isinstance(services, str):
        services = [s.strip() for s in re.split(r",|\n|;", services)
                    if s.strip()]
    if not services:
        services = [service]
    return services


def _document(title: str, head_extra: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"{head_extra}\n"
        f"<style>{_PAGE_CSS}\n</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def _location_page_html(business: dict, town: str, neighbors: list,
                        service: str, base_url: str, slug: str) -> str:
    brand = business.get("brand") or "Your Business"
    st = (business.get("state") or "NY").upper()
    st_full = _STATE_NAMES.get(st, st)
    phone = business.get("phone") or ""
    tel = re.sub(r"[^\d+]", "", phone)
    service_l = service.lower() if service != service.upper() else service
    h = _town_hash(town)

    e_town, e_brand = html.escape(town), html.escape(brand)
    fmt = dict(town=e_town, brand=e_brand, service_l=html.escape(service_l),
               st=st, st_full=html.escape(st_full),
               phone=html.escape(phone), tel=html.escape(tel))

    intro = _INTRO_TEMPLATES[h % len(_INTRO_TEMPLATES)].format(**fmt)
    why_us = _WHY_US_TEMPLATES[(h // 7) % len(_WHY_US_TEMPLATES)].format(**fmt)
    cta = _CTA_TEMPLATES[(h // 31) % len(_CTA_TEMPLATES)].format(**fmt)

    title = _page_title(service, town, st, brand)
    meta_desc = _meta_description(service, town, st, brand, phone)

    head = [f'<meta name="description" content="{html.escape(meta_desc)}">']
    canonical = ""
    if base_url:
        canonical = f"{base_url.rstrip('/')}/areas-served/{slug}/"
        head.append(f'<link rel="canonical" href="{html.escape(canonical)}">')
    head += [
        f'<meta property="og:title" content="{html.escape(title)}">',
        f'<meta property="og:description" content="{html.escape(meta_desc)}">',
        '<meta property="og:type" content="website">',
    ]
    if canonical:
        head.append(f'<meta property="og:url" content="{html.escape(canonical)}">')
    head.append(_jsonld(business, town, base_url))

    services = _services_list(business, service)
    services_li = "\n".join(
        f"      <li>{html.escape(s)} in {e_town}</li>" if i == 0
        else f"      <li>{html.escape(s)}</li>"
        for i, s in enumerate(services[:8]))

    if neighbors:
        neighbor_txt = ", ".join(html.escape(n) for n in neighbors[:-1])
        if len(neighbors) > 1:
            neighbor_txt += " and " + html.escape(neighbors[-1])
        else:
            neighbor_txt = html.escape(neighbors[0])
        area_para = (
            f"<p>{e_town} sits right in the heart of our service area. "
            f"In addition to {e_town}, our crews are regularly out in "
            f"nearby {neighbor_txt}, so we can almost always fit "
            f"{e_town} appointments in quickly - often the same week.</p>")
    else:
        area_para = (f"<p>{e_town} is part of our core service area, and "
                     f"we schedule visits there every week.</p>")

    nap_lines = [f"<strong>{e_brand}</strong>"]
    if business.get("street"):
        nap_lines.append(html.escape(business["street"]))
    city_line = ", ".join(x for x in (business.get("city"), st) if x)
    if business.get("zip"):
        city_line = (city_line + " " + str(business["zip"])).strip()
    if city_line:
        nap_lines.append(html.escape(city_line))
    if phone:
        nap_lines.append(f'Phone: <a href="tel:{html.escape(tel)}">'
                         f"{html.escape(phone)}</a>")
    nap_html = "<br>\n        ".join(nap_lines)

    home_href = (base_url.rstrip("/") + "/") if base_url else "/"

    body = f"""<header class="site">
  <div class="wrap">
    <h1>{html.escape(service)} in {e_town}, {st}</h1>
    <p class="tagline">{e_brand} &middot; Serving {e_town} and surrounding {html.escape(st_full)} communities</p>
  </div>
</header>
<main>
  <nav class="crumbs">
    <a href="{html.escape(home_href)}">Home</a> &rsaquo;
    <a href="../index.html">Areas We Serve</a> &rsaquo; {e_town}
  </nav>
  <section>
    <p>{intro}</p>
  </section>
  <section>
    <h2>Our services in {e_town}</h2>
    <ul>
{services_li}
    </ul>
  </section>
  <section>
    <h2>Why {e_town} chooses {e_brand}</h2>
    {why_us}
  </section>
  <section>
    <h2>Serving {e_town} and beyond</h2>
    {area_para}
  </section>
  <!-- [TESTIMONIAL PLACEHOLDER - add a real review from a {e_town} customer]
       Replace this comment with a short, genuine review from a {e_town}
       customer (name + neighborhood adds credibility). Real local
       testimonials are one of the strongest local ranking and conversion
       signals. -->
  <section class="cta">
    <h2>Get started in {e_town} today</h2>
    <p>{cta}</p>
  </section>
  <section>
    <h2>Contact</h2>
    <address class="nap">
        {nap_html}
    </address>
  </section>
</main>
<footer class="site">
  <div class="wrap">
    <p>&copy; {e_brand}. {html.escape(service)} in {e_town}, {st}.
    <a href="../index.html">All areas we serve</a> &middot;
    <a href="{html.escape(home_href)}">Homepage</a></p>
  </div>
</footer>"""

    head_extra = "\n".join(head)
    return _document(title, head_extra, body)


def _hub_page_html(business: dict, entries: list, base_url: str) -> str:
    """entries = [(town, slug), ...]"""
    brand = business.get("brand") or "Your Business"
    st = (business.get("state") or "NY").upper()
    title = f"Areas We Serve | {brand}"
    e_brand = html.escape(brand)
    home_href = (base_url.rstrip("/") + "/") if base_url else "/"

    head = [
        f'<meta name="description" content="{html.escape(f"Full list of towns and communities served by {brand}. Find your local {brand} service page.")}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{html.escape(title)}">',
    ]
    if base_url:
        canonical = base_url.rstrip("/") + "/areas-served/"
        head.append(f'<link rel="canonical" href="{html.escape(canonical)}">')

    # Categorize alphabetically by first letter.
    groups = {}
    for town, slug in entries:
        groups.setdefault(town[0].upper(), []).append((town, slug))

    sections = []
    for letter in sorted(groups):
        links = "\n".join(
            f'        <li><a href="{html.escape(slug)}/index.html">'
            f"{html.escape(town)}, {st}</a></li>"
            for town, slug in sorted(groups[letter]))
        sections.append(
            f"    <h2>{letter}</h2>\n"
            f'    <ul class="towns">\n{links}\n    </ul>')
    town_sections = "\n".join(sections)

    body = f"""<header class="site">
  <div class="wrap">
    <h1>Areas We Serve</h1>
    <p class="tagline">{e_brand} &middot; {len(entries)} communities and counting</p>
  </div>
</header>
<main>
  <nav class="crumbs"><a href="{html.escape(home_href)}">Home</a> &rsaquo; Areas We Serve</nav>
  <section>
    <p>{e_brand} proudly serves the communities below. Choose your town
    for local service details, or <a href="{html.escape(home_href)}">head back to
    our homepage</a> to learn more about what we do. Don't see your town?
    We may still cover it - give us a call.</p>
  </section>
  <section>
{town_sections}
  </section>
</main>
<footer class="site">
  <div class="wrap">
    <p>&copy; {e_brand}. <a href="{html.escape(home_href)}">Homepage</a></p>
  </div>
</footer>"""

    return _document(title, "\n".join(head), body)


def _footer_snippet_html(entries: list, st: str) -> str:
    """Ready-to-paste footer <nav> linking the hub + top 10 towns."""
    links = ['      <a href="/areas-served/">All Areas We Serve</a>']
    for town, slug in entries[:10]:
        links.append(f'      <a href="/areas-served/{html.escape(slug)}/">'
                     f"{html.escape(town)}, {st}</a>")
    joined = "\n".join(links)
    return f"""<!-- FOOTER SERVICE-AREA LINKS - generated by SEO Audit Pro
     HOW TO USE: paste this <nav> block into your site-wide footer
     (on every page, usually just above the copyright line). Sitewide
     internal links to your top location pages help them rank. If your
     pages live somewhere other than /areas-served/, adjust the hrefs. -->
<nav aria-label="Service areas" class="service-area-links">
  <strong>Service Areas:</strong>
{joined}
</nav>
"""


def generate_location_pages(business: dict, locations: list, output_dir: str,
                            base_url: str = "", service: str = "",
                            log=None) -> dict:
    """Write one landing page per location plus a hub page and footer
    snippet under <output_dir>/areas-served/.

    business keys (all optional): brand, description, phone, street, city,
    state (default "NY"), zip, services (list or str), socials (dict).
    Returns {"pages": [paths], "hub": path, "count": N}.
    """
    log = log or (lambda m: None)
    business = business or {}
    st = (business.get("state") or "NY").upper()
    if not service:
        services = _services_list(business, "")
        service = services[0] if services and services[0] else "Local Services"
    service = service.strip()

    hub_dir = os.path.join(output_dir, "areas-served")
    os.makedirs(hub_dir, exist_ok=True)

    towns = _dedupe(locations)[:MAX_LOCATIONS]
    entries = [(town, f"{_slugify(town)}-{st.lower()}") for town in towns]

    paths = []
    for i, (town, slug) in enumerate(entries):
        # 2-3 neighboring towns from the same generated list.
        neighbors = []
        for k in range(1, len(entries)):
            other = entries[(i + k) % len(entries)][0]
            if other != town:
                neighbors.append(other)
            if len(neighbors) == 3:
                break
        page_dir = os.path.join(hub_dir, slug)
        os.makedirs(page_dir, exist_ok=True)
        path = os.path.join(page_dir, "index.html")
        html_text = _location_page_html(business, town, neighbors, service,
                                        base_url, slug)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html_text)
        paths.append(path)
        log(f"  Wrote location page: areas-served/{slug}/index.html")

    hub_path = os.path.join(hub_dir, "index.html")
    with open(hub_path, "w", encoding="utf-8") as fh:
        fh.write(_hub_page_html(business, entries, base_url))
    log("  Wrote hub page: areas-served/index.html")

    snippet_path = os.path.join(hub_dir, "FOOTER-LINKS-SNIPPET.html")
    with open(snippet_path, "w", encoding="utf-8") as fh:
        fh.write(_footer_snippet_html(entries, st))
    log("  Wrote footer links snippet: areas-served/FOOTER-LINKS-SNIPPET.html")

    return {"pages": paths, "hub": hub_path, "count": len(paths)}
