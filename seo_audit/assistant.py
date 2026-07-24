"""AI assistant engine that powers the chat panel in the GUI.

Interviews the user about their business (so the audit / repair /
location-page tools get real data), persists the answers as a JSON
profile, and generates deliverables (FAQ page, blog plan, GBP guide,
AI-adoption guide, outreach templates).

Works 100% offline with templates; if an Anthropic API key is supplied
the FAQ and blog-plan copy is enhanced through the Claude API, with a
silent fallback to the templates when the SDK/network is unavailable.
"""

import html
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date


# ---------------------------------------------------------------------------
# Reply model
# ---------------------------------------------------------------------------

@dataclass
class AssistantReply:
    text: str
    done: bool = False
    action: str = ""            # "", "generate_location_pages", "generate_faq",
                                # "generate_blog_plan", "generate_gbp_guide"
    action_params: dict = None


# ---------------------------------------------------------------------------
# Profile defaults / interview questions
# ---------------------------------------------------------------------------

def _empty_profile() -> dict:
    return {
        "brand": "",
        "services": [],
        "description": "",
        "keywords": [],
        "is_local": None,
        "locations": [],
        "phone": "",
        "address_raw": "",
        "street": "",
        "city": "",
        "state": "",
        "zip": "",
        "socials": {},
        "has_gbp": None,
    }


# Interview order. "locations" is only asked when is_local is True.
FIELD_ORDER = [
    "brand", "services", "description", "keywords", "is_local",
    "locations", "phone", "address", "socials", "has_gbp",
]

QUESTIONS = {
    "brand": "What's the business name?",
    "services": ("What does the business do? List your main services "
                 "(comma-separated)."),
    "description": ("In one sentence, how would you describe the business? "
                    "(Or type 'you write it' and I'll draft one from your "
                    "services.)"),
    "keywords": ("What search keywords do you want to rank for? "
                 "(comma-separated)"),
    "is_local": "Do you serve customers in a local area (yes/no)?",
    "locations": ("What areas do you serve? (e.g. 'Suffolk County', "
                  "'NYC and Long Island', or list towns)"),
    "phone": "What's the best phone number for customers to call?",
    "address": ("What's the business address? (street, city, state, zip "
                "in one answer)"),
    "socials": "Paste your social profile links, or 'none'.",
    "has_gbp": "Do you have a Google Business Profile? (yes/no)",
}

_YES_WORDS = {"y", "yes", "yeah", "yep", "yup", "sure", "definitely",
              "correct", "of course", "we do", "i do", "true"}
_NO_WORDS = {"n", "no", "nope", "nah", "not yet", "we don't", "we dont",
             "i don't", "i dont", "none", "false"}

_SOCIAL_DOMAINS = ["facebook", "instagram", "linkedin", "twitter", "x.com",
                   "youtube", "tiktok", "yelp", "pinterest", "nextdoor",
                   "threads"]

HELP_TEXT = (
    "Here's what I can do:\n"
    "  - Interview you about your business to build a profile\n"
    "  - 'faq' - generate an SEO-ready FAQ page (HTML + FAQPage schema)\n"
    "  - 'blog' - generate a 3-month, 12-post blog plan\n"
    "  - 'google business' or 'gbp' - Google Business Profile setup guide\n"
    "  - 'location pages' or 'add locations <areas>' - build location "
    "pages for the areas you serve\n"
    "  - Answer my questions any time to keep filling in the profile"
)


def _parse_yes_no(text: str):
    """Loose yes/no parse. Returns True/False, or None if unclear."""
    t = text.strip().lower().rstrip(".!")
    if not t:
        return None
    if t in _YES_WORDS or t in _NO_WORDS:
        return True if t in _YES_WORDS else False
    first = t.split()[0].rstrip(",.!")
    if first in _YES_WORDS:
        return True
    if first in _NO_WORDS:
        return False
    if re.search(r"\byes\b", t):
        return True
    if re.search(r"\bno\b", t):
        return False
    return None


def _split_list(text: str) -> list:
    """Split a free-text answer into a clean list (commas / 'and')."""
    parts = re.split(r",|;|\band\b|\n", text)
    return [p.strip(" .") for p in parts if p.strip(" .")]


def _fallback_resolve_locations(query: str) -> dict:
    """Used when seo_audit.locations isn't available yet: treat the raw
    answer as a comma-separated town list."""
    towns = [t.strip(" .") for t in re.split(r",|\n", query) if t.strip(" .")]
    if not towns:
        towns = [query.strip()]
    return {"status": "ok", "locations": towns, "message": ""}


# ---------------------------------------------------------------------------
# Assistant engine
# ---------------------------------------------------------------------------

class AssistantEngine:
    """Interview state machine + command handler backing the chat panel."""

    def __init__(self, profile_path: str, api_key: str = ""):
        self.profile_path = profile_path
        self.api_key = api_key
        self._profile = _empty_profile()
        self._answered = set()      # field names already answered
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self):
        if not os.path.exists(self.profile_path):
            return
        try:
            with open(self.profile_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if "profile" in data and isinstance(data.get("profile"), dict):
            stored, answered = data["profile"], data.get("answered", [])
        else:                       # tolerate a bare profile dict
            stored, answered = data, []
        for key in self._profile:
            if key in stored:
                self._profile[key] = stored[key]
        self._answered = set(answered)
        # Infer answered fields from populated values (e.g. hand-edited file).
        for key in ("brand", "description", "phone"):
            if self._profile[key]:
                self._answered.add(key)
        for key in ("services", "keywords", "locations"):
            if self._profile[key]:
                self._answered.add(key)
        if self._profile["address_raw"]:
            self._answered.add("address")
        if self._profile["is_local"] is not None:
            self._answered.add("is_local")
        if self._profile["has_gbp"] is not None:
            self._answered.add("has_gbp")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.profile_path) or ".",
                        exist_ok=True)
            with open(self.profile_path, "w", encoding="utf-8") as fh:
                json.dump({"profile": self._profile,
                           "answered": sorted(self._answered)},
                          fh, indent=2)
        except OSError:
            pass                    # never crash the chat over a disk error

    @property
    def profile(self) -> dict:
        return self._profile

    # -- interview flow -----------------------------------------------------

    def _next_field(self):
        for key in FIELD_ORDER:
            if key == "locations" and self._profile["is_local"] is not True:
                continue            # only asked for local businesses
            if key not in self._answered:
                return key
        return None

    def _question_for(self, key: str) -> str:
        return QUESTIONS[key]

    def start(self) -> str:
        nxt = self._next_field()
        if nxt is None:
            return ("Welcome back! Your business profile is complete.\n\n"
                    + self._summary()
                    + "\n\nType 'help' to see everything I can generate.")
        if self._answered:
            greeting = ("Welcome back! Let's pick up where we left off "
                        "building your business profile.\n\n")
        else:
            greeting = ("Hi! I'm your SEO assistant. I'll ask a few quick "
                        "questions about the business so the audit, site "
                        "package, and location-page tools can use real "
                        "data. You can type 'help' at any time.\n\n")
        return greeting + self._question_for(nxt)

    def handle(self, text: str) -> AssistantReply:
        text = (text or "").strip()
        if not text:
            nxt = self._next_field()
            if nxt is None:
                return AssistantReply(self._summary(), done=True)
            return AssistantReply(self._question_for(nxt), done=False)

        # Out-of-band commands are checked before the interview state machine
        # (but a plain yes/no while a yes/no question is pending is always
        # treated as the answer, so e.g. "yes, we have a GBP" works).
        pending = self._next_field()
        is_answer_to_yes_no = (pending in ("is_local", "has_gbp")
                               and _parse_yes_no(text) is not None)
        if not is_answer_to_yes_no:
            reply = self._check_command(text)
            if reply is not None:
                self._save()
                return reply

        reply = self._handle_interview(text, pending)
        self._save()
        return reply

    # -- out-of-band commands -----------------------------------------------

    def _check_command(self, text: str):
        low = text.lower()

        m = re.search(r"\badd locations?\b(.*)", low)
        if m:
            query = text[m.start(1):].strip(" :,-")
            return self._locations_command(query)
        if "location pages" in low:
            trailing = re.sub(r".*location pages?\b(?:\s*for)?", "", low).strip(" :,-")
            if trailing:
                return self._locations_command(trailing)
            if self._profile["locations"]:
                locs = self._profile["locations"]
                return AssistantReply(
                    "I can build location pages for: "
                    + ", ".join(locs[:8])
                    + (", ..." if len(locs) > 8 else "")
                    + ". Use the button below to generate them.",
                    done=False, action="generate_location_pages",
                    action_params={"locations": locs})
            return AssistantReply(
                "Which areas should the location pages cover? Reply with "
                "'add locations <areas>' (e.g. 'add locations Suffolk "
                "County' or a list of towns).", done=False)

        if "google business" in low or re.search(r"\bgbp\b", low):
            return AssistantReply(
                "Here's your step-by-step Google Business Profile guide - "
                "use the button below to generate it.",
                done=False, action="generate_gbp_guide", action_params={})
        if re.search(r"\bfaqs?\b", low):
            return AssistantReply(
                "I'll put together an SEO-ready FAQ page for "
                + (self._profile["brand"] or "the business")
                + " - use the button below to generate it.",
                done=False, action="generate_faq", action_params={})
        if re.search(r"\bblog\b", low):
            return AssistantReply(
                "I'll draft a 3-month, 12-post blog plan - use the button "
                "below to generate it.",
                done=False, action="generate_blog_plan", action_params={})
        if re.search(r"\bhelp\b", low):
            nxt = self._next_field()
            tail = ("\n\nNext profile question: " + self._question_for(nxt)
                    if nxt else "")
            return AssistantReply(HELP_TEXT + tail, done=False)
        return None

    def _resolve_locations(self, query: str) -> dict:
        try:
            from .locations import resolve_locations
        except ImportError:
            resolve_locations = _fallback_resolve_locations
        try:
            result = resolve_locations(query)
        except Exception:
            result = _fallback_resolve_locations(query)
        if not isinstance(result, dict):
            result = _fallback_resolve_locations(query)
        return result

    def _locations_command(self, query: str) -> AssistantReply:
        if not query:
            return AssistantReply(
                "Which areas? e.g. 'add locations Suffolk County' or "
                "'add locations Huntington, Smithtown, Babylon'.",
                done=False)
        result = self._resolve_locations(query)
        if result.get("status") == "clarify":
            return AssistantReply(
                result.get("message")
                or "Could you clarify which areas you mean?", done=False)
        locs = result.get("locations") or [query]
        self._profile["locations"] = locs
        self._profile["is_local"] = True
        self._answered.update({"locations", "is_local"})
        shown = ", ".join(locs[:8]) + (", ..." if len(locs) > 8 else "")
        return AssistantReply(
            f"Got it - {len(locs)} location pages possible for: {shown}. "
            "Use the button below to generate them.",
            done=False, action="generate_location_pages",
            action_params={"locations": locs})

    # -- per-field answer handling -------------------------------------------

    def _handle_interview(self, text: str, pending) -> AssistantReply:
        if pending is None:
            return AssistantReply(
                "Your profile is complete - type 'help' to see what I can "
                "generate, or ask for the FAQ page, blog plan, GBP guide, "
                "or location pages.", done=True)

        p = self._profile
        extra_action, extra_params, note = "", None, ""

        if pending == "brand":
            p["brand"] = text
        elif pending == "services":
            p["services"] = _split_list(text) or [text]
        elif pending == "description":
            if re.search(r"\byou (write|draft|do) it\b", text.lower()) or \
                    text.lower().strip() in ("write it", "draft it", "you write it"):
                services = ", ".join(p["services"]) or "professional services"
                p["description"] = (f"{p['brand'] or 'The business'} provides "
                                    f"{services} with reliable, professional "
                                    "service and fast turnaround.")
                note = f'Here\'s a draft: "{p["description"]}"\n\n'
            else:
                p["description"] = text
        elif pending == "keywords":
            p["keywords"] = _split_list(text) or [text]
        elif pending == "is_local":
            val = _parse_yes_no(text)
            if val is None:
                return AssistantReply(
                    "Sorry, I didn't catch that - do you serve customers in "
                    "a local area? (yes/no)", done=False)
            p["is_local"] = val
        elif pending == "locations":
            result = self._resolve_locations(text)
            if result.get("status") == "clarify":
                return AssistantReply(
                    result.get("message")
                    or "Could you clarify which areas you serve?",
                    done=False)
            locs = result.get("locations") or [text]
            p["locations"] = locs
            shown = ", ".join(locs[:8]) + (", ..." if len(locs) > 8 else "")
            note = (f"Got it - {len(locs)} location pages possible for: "
                    f"{shown}.\n\n")
            extra_action = "generate_location_pages"
            extra_params = {"locations": locs}
        elif pending == "phone":
            p["phone"] = text
        elif pending == "address":
            self._store_address(text)
        elif pending == "socials":
            p["socials"] = self._parse_socials(text)
            if not p["socials"]:
                note = "No social links recorded - you can add them later.\n\n"
        elif pending == "has_gbp":
            val = _parse_yes_no(text)
            if val is None:
                return AssistantReply(
                    "Sorry - do you have a Google Business Profile? (yes/no)",
                    done=False)
            p["has_gbp"] = val
            if not val:
                note = ("No problem - a Google Business Profile is the #1 "
                        "free local-SEO win. I've prepared a step-by-step "
                        "setup guide for you.\n\n")
                extra_action = "generate_gbp_guide"
                extra_params = {}

        self._answered.add(pending)

        nxt = self._next_field()
        if nxt is None:
            return AssistantReply(
                note + "That's everything I need!\n\n" + self._summary()
                + "\n\nNext steps: run a Complete Audit of your site, use "
                "Build Site Package to generate pages, or let me generate "
                "an FAQ page and blog plan for you (button below).",
                done=True,
                action=extra_action or "generate_faq",
                action_params=extra_params if extra_action else {})
        return AssistantReply(note + self._question_for(nxt), done=False,
                              action=extra_action,
                              action_params=extra_params)

    def _store_address(self, text: str):
        p = self._profile
        p["address_raw"] = text
        parts = [s.strip() for s in text.split(",") if s.strip()]
        if parts:
            p["street"] = parts[0]
        if len(parts) >= 2:
            p["city"] = parts[1]
        tail = parts[2] if len(parts) >= 3 else text
        zm = re.search(r"\b(\d{5})(?:-\d{4})?\b", tail)
        if zm:
            p["zip"] = zm.group(1)
        sm = re.search(r"\b([A-Z]{2})\b", tail.replace(p["zip"], ""))
        if sm:
            p["state"] = sm.group(1)

    @staticmethod
    def _parse_socials(text: str) -> dict:
        if text.strip().lower() in ("none", "no", "n/a", "na", "nope"):
            return {}
        urls = re.findall(r"https?://\S+|(?:www\.)?[\w.-]+\.\w{2,}/\S+", text)
        socials, other = {}, 0
        for url in urls:
            url = url.rstrip(".,;)")
            low = url.lower()
            key = None
            for dom in _SOCIAL_DOMAINS:
                if dom in low:
                    key = "x" if dom == "x.com" else dom
                    break
            if key is None:
                other += 1
                key = f"other{other}"
            socials[key] = url
        return socials

    def _summary(self) -> str:
        p = self._profile
        lines = ["Business profile:",
                 f"  Brand:       {p['brand'] or '-'}",
                 f"  Services:    {', '.join(p['services']) or '-'}",
                 f"  Description: {p['description'] or '-'}",
                 f"  Keywords:    {', '.join(p['keywords']) or '-'}",
                 f"  Local:       "
                 f"{'yes' if p['is_local'] else 'no' if p['is_local'] is False else '-'}"]
        if p["is_local"]:
            locs = ", ".join(p["locations"][:8])
            if len(p["locations"]) > 8:
                locs += ", ..."
            lines.append(f"  Areas:       {locs or '-'}")
        lines += [f"  Phone:       {p['phone'] or '-'}",
                  f"  Address:     {p['address_raw'] or '-'}",
                  f"  Socials:     {', '.join(p['socials']) or '-'}",
                  f"  Google Business Profile: "
                  f"{'yes' if p['has_gbp'] else 'no' if p['has_gbp'] is False else '-'}"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude API enhancement (optional - never required, never crashes offline)
# ---------------------------------------------------------------------------

def ai_enhance(prompt_text: str, api_key: str):
    """Send a prompt to the Claude API. Returns the text response, or None
    when no key is set, the SDK isn't installed, or the call fails."""
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return "".join(b.text for b in response.content if b.type == "text")
    except anthropic.APIError:
        return None


# ---------------------------------------------------------------------------
# Deliverable generators
# ---------------------------------------------------------------------------

def _first(items, default):
    return items[0] if items else default


def _area_of(profile: dict) -> str:
    locations = profile.get("locations") or []
    return _first(locations, profile.get("city") or "your area")


def _template_faq_pairs(profile: dict) -> list:
    brand = profile.get("brand") or "Our company"
    services = profile.get("services") or ["our services"]
    s0 = services[0]
    s1 = services[1] if len(services) > 1 else s0
    area = _area_of(profile)
    phone = profile.get("phone") or "our office"
    locations = profile.get("locations") or []
    served = (", ".join(locations[:8]) + (" and nearby areas"
              if len(locations) > 8 else "")) if locations else area

    pairs = [
        (f"How much does {s0} cost in {area}?",
         f"Pricing for {s0} depends on the size and scope of the job. "
         f"{brand} provides free, no-obligation estimates so you know the "
         f"exact price before any work begins. Call {phone} or request a "
         "quote online for a fast, accurate estimate."),
        (f"Do you offer emergency {s0}?",
         f"Yes. {brand} offers priority scheduling for urgent {s0} needs "
         f"in {area}. Contact us right away and we'll get a technician out "
         "as quickly as possible - often the same day."),
        ("What areas do you serve?",
         f"{brand} proudly serves {served}. If you're close to our service "
         "area but don't see your town listed, give us a call - we can "
         "usually accommodate nearby locations."),
        (f"How quickly can {brand} schedule an appointment?",
         "Most appointments are scheduled within 24-48 hours, and urgent "
         "requests are often handled the same day. We confirm every "
         "appointment window in advance and show up on time."),
        (f"Is {brand} licensed and insured?",
         f"Yes. {brand} is fully licensed and insured for {s0}. We're happy "
         "to provide proof of insurance and license details on request, so "
         "you can hire us with complete confidence."),
        ("Do you offer free estimates?",
         f"Yes - estimates are always free. We'll assess your needs, "
         f"explain your options in plain language, and give you a written "
         f"quote with no pressure and no hidden fees."),
        (f"What does your {s1} service include?",
         f"Our {s1} service includes a full assessment, the work itself "
         "performed by trained professionals, and a follow-up to make sure "
         "everything meets your expectations. We explain exactly what's "
         "included before we start."),
        (f"How do I get started with {brand}?",
         f"Getting started is easy: call {phone} or send us a message "
         "describing what you need. We'll ask a few quick questions, "
         "schedule a convenient time, and take it from there."),
        ("Do you guarantee your work?",
         f"Yes. {brand} stands behind every job. If something isn't right, "
         "let us know and we'll make it right - customer satisfaction is "
         "the foundation of our reputation."),
        (f"Why choose {brand} over other {s0} companies in {area}?",
         f"{brand} combines local experience in {area} with honest "
         "pricing, fast response times, and workmanship we guarantee. "
         "Check our reviews - our customers say it best."),
    ]
    return pairs


def _parse_qa_lines(text: str) -> list:
    """Parse strict 'Q: ... / A: ...' lines from an AI response."""
    pairs, question = [], None
    for line in text.splitlines():
        line = line.strip().lstrip("*-#").strip()
        if line.lower().startswith("q:"):
            question = line[2:].strip()
        elif line.lower().startswith("a:") and question:
            answer = line[2:].strip()
            if answer:
                pairs.append((question, answer))
            question = None
    return pairs


def generate_faq_page(profile: dict, api_key: str = "") -> str:
    """Complete standalone FAQ HTML page with matching FAQPage JSON-LD."""
    brand = profile.get("brand") or "Our Company"
    area = _area_of(profile)
    pairs = _template_faq_pairs(profile)

    if api_key:
        prompt = (
            "You are writing FAQ copy for a small business web page.\n\n"
            "Business profile:\n" + json.dumps(profile, indent=2) +
            "\n\nWrite exactly 10 frequently-asked questions and answers "
            "that this business's customers would search for, including "
            "pricing, service area, scheduling, and trust questions. Keep "
            "each answer 40-60 words, plain language, no fluff.\n\n"
            "STRICT OUTPUT FORMAT - output ONLY lines in this form, nothing "
            "else (no HTML, no JSON, no numbering, no headings):\n"
            "Q: <question>\nA: <answer>\nQ: <question>\nA: <answer>\n..."
        )
        raw = ai_enhance(prompt, api_key)
        if raw:
            ai_pairs = _parse_qa_lines(raw)
            if len(ai_pairs) >= 6:
                pairs = ai_pairs[:10]

    pairs = pairs[:10]

    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in pairs
        ],
    }

    faq_html = "\n".join(
        '    <div class="faq-item">\n'
        f"      <h2>{html.escape(q)}</h2>\n"
        f"      <p>{html.escape(a)}</p>\n"
        "    </div>"
        for q, a in pairs
    )

    title = f"Frequently Asked Questions | {brand}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(
      f'Answers to the most common questions about {brand} - pricing, '
      f'service area, scheduling, and more in {area}.')}">
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0;
           color: #222; background: #f7f8fa; line-height: 1.6; }}
    header {{ background: #1a3c5e; color: #fff; padding: 40px 20px;
             text-align: center; }}
    header h1 {{ margin: 0 0 8px; font-size: 2rem; }}
    header p {{ margin: 0; opacity: .85; }}
    main {{ max-width: 800px; margin: 0 auto; padding: 30px 20px 60px; }}
    .faq-item {{ background: #fff; border-radius: 8px; padding: 20px 24px;
                margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    .faq-item h2 {{ margin: 0 0 10px; font-size: 1.15rem; color: #1a3c5e; }}
    .faq-item p {{ margin: 0; }}
    footer {{ text-align: center; padding: 24px; color: #667;
             font-size: .9rem; }}
  </style>
  <script type="application/ld+json">
{json.dumps(schema, indent=2)}
  </script>
</head>
<body>
  <header>
    <h1>Frequently Asked Questions</h1>
    <p>{html.escape(brand)} &mdash; serving {html.escape(area)}</p>
  </header>
  <main>
{faq_html}
  </main>
  <footer>
    &copy; {date.today().year} {html.escape(brand)}. All rights reserved.
  </footer>
</body>
</html>
"""


def generate_blog_plan(profile: dict, api_key: str = "") -> str:
    """Markdown 12-topic, 3-month blog plan derived from the profile."""
    brand = profile.get("brand") or "the business"
    services = profile.get("services") or ["your main service"]
    keywords = profile.get("keywords") or []
    locations = profile.get("locations") or []
    area = _area_of(profile)
    year = date.today().year

    if api_key:
        prompt = (
            "You are an SEO content strategist. Business profile:\n"
            + json.dumps(profile, indent=2) +
            f"\n\nWrite a 3-month blog plan with exactly 12 posts (4 per "
            "month) in MARKDOWN. Start with a '# ' title line. For each "
            "post use a '### Post N: <title>' heading followed by bullet "
            "lines for 'Target keyword:', 'Search intent:', 'Publish:' "
            f"(Month 1-3, Week 1-4), and an 'Outline:' with 4-5 H2 "
            "headings as sub-bullets. Derive topics from the services, "
            f"keywords, and locations. Use {year} where a year helps the "
            "title. Output only the markdown plan, nothing else."
        )
        raw = ai_enhance(prompt, api_key)
        if raw and "###" in raw:
            return raw.strip() + "\n"

    def svc(i):
        return services[i % len(services)]

    def loc(i):
        return locations[i % len(locations)] if locations else area

    def kw(i, fallback):
        return keywords[i % len(keywords)] if keywords else fallback

    topics = [
        (f"How Much Does {svc(0).title()} Cost in {area}? ({year} Pricing Guide)",
         kw(0, f"{svc(0)} cost {area}"), "commercial",
         [f"Average {svc(0)} prices in {area}",
          "What drives the price up or down",
          "Red flags in cheap quotes",
          "How to get an accurate estimate",
          f"Why locals choose {brand}"]),
        (f"7 Signs You Need {svc(0).title()} (And What to Do Next)",
         kw(1, f"signs you need {svc(0)}"), "informational",
         ["The early warning signs most people miss",
          "What happens if you wait",
          "Quick checks you can do yourself",
          "When to call a professional"]),
        (f"DIY vs Professional {svc(0).title()}: An Honest Comparison",
         kw(2, f"diy {svc(0)}"), "informational",
         ["What DIY can realistically handle",
          "The true cost of DIY (time, tools, risk)",
          "What professionals do differently",
          "How to decide for your situation"]),
        (f"How to Choose a {svc(0).title()} Company in {area}",
         kw(3, f"best {svc(0)} {area}"), "commercial",
         ["Licenses, insurance, and guarantees to ask about",
          "Reviews: what to look for beyond the star rating",
          "Questions to ask before you sign",
          "Local vs national providers"]),
        (f"{svc(1 % len(services)).title()} in {loc(0)}: A Local Guide",
         kw(4, f"{svc(1 % len(services))} {loc(0)}"), "local",
         [f"Common {svc(1 % len(services))} needs in {loc(0)}",
          "Local rules and considerations",
          "Typical timelines and costs",
          f"How {brand} serves {loc(0)}"]),
        (f"The Complete Beginner's Guide to {svc(0).title()}",
         kw(5, f"what is {svc(0)}"), "informational",
         [f"What {svc(0)} actually involves",
          "Key terms explained in plain English",
          "What a typical job looks like start to finish",
          "Costs, timelines, and what to expect",
          "Frequently asked questions"]),
        (f"Seasonal {svc(0).title()} Checklist for {area} Homeowners",
         kw(6, f"{svc(0)} checklist"), "informational",
         ["Spring and summer priorities",
          "Fall and winter priorities",
          "Monthly quick-checks",
          "When to schedule professional help"]),
        (f"5 Common {svc(0).title()} Mistakes That Cost You Money",
         kw(7, f"{svc(0)} mistakes"), "informational",
         ["Mistake 1: waiting too long",
          "Mistake 2: hiring on price alone",
          "Mistake 3: skipping maintenance",
          "Mistake 4: ignoring the small stuff",
          "How to avoid all of them"]),
        (f"{svc(0).title()} in {loc(1)}: What Residents Should Know",
         kw(8, f"{svc(0)} {loc(1)}"), "local",
         [f"Why {loc(1)} properties have unique needs",
          "Local case examples",
          "Costs and scheduling in this area",
          f"Booking {brand} in {loc(1)}"]),
        (f"Questions to Ask Before Hiring Any {svc(0).title()} Pro",
         kw(9, f"hiring {svc(0)} questions"), "commercial",
         ["The 10-question pre-hire checklist",
          "Answers that should raise a red flag",
          "Getting the agreement in writing",
          "How we answer these questions"]),
        (f"Real Results: A {brand} Customer Story",
         kw(10, f"{svc(0)} before and after"), "commercial",
         ["The problem the customer faced",
          "What we found on inspection",
          "The work performed, step by step",
          "The outcome and what it cost"]),
        (f"{svc(0).title()} FAQ: Your Top Questions Answered",
         kw(11, f"{svc(0)} faq"), "informational",
         ["Pricing questions",
          "Scheduling and timing questions",
          "Safety and guarantee questions",
          "How to get a fast answer from us"]),
    ]

    lines = [f"# 3-Month Blog Plan for {brand}", "",
             f"12 posts, 4 per month, built from your services "
             f"({', '.join(services)}), keywords, and service area "
             f"({area}). Publish one post per week.", ""]
    for i, (title, keyword, intent, outline) in enumerate(topics):
        month, week = i // 4 + 1, i % 4 + 1
        lines += [f"### Post {i + 1}: {title}",
                  f"- Target keyword: {keyword}",
                  f"- Search intent: {intent}",
                  f"- Publish: Month {month}, Week {week}",
                  "- Outline:"]
        lines += [f"  - H2: {h2}" for h2 in outline]
        lines.append("")
    return "\n".join(lines)


def generate_gbp_guide(profile: dict) -> str:
    """Markdown step-by-step Google Business Profile setup + optimization."""
    brand = profile.get("brand") or "your business"
    services = ", ".join(profile.get("services") or ["your services"])
    area = _area_of(profile)
    phone = profile.get("phone") or "your business phone number"
    address = profile.get("address_raw") or "your business address"

    return f"""# Google Business Profile Guide for {brand}

A free Google Business Profile (GBP) is the single highest-impact local
SEO asset for {brand}. Follow these steps in order.

## Step 1 - Create or claim your profile
1. Go to https://business.google.com and sign in with the Google account
   you want to own the listing.
2. Search for "{brand}" - if a listing already exists, click
   "Claim this business"; otherwise choose "Add your business".
3. Enter the exact business name: **{brand}** (no keywords stuffed in -
   Google suspends listings for that).

## Step 2 - Verify the business
- Choose postcard, phone, email, or video verification (options vary).
- Verification can take up to 5 business days for postcards - don't edit
  the listing while a postcard is in transit.

## Step 3 - Choose categories
- Pick ONE precise primary category that matches your main money-maker
  ({services}).
- Add 2-5 secondary categories for the rest of your services.

## Step 4 - NAP consistency (Name, Address, Phone)
- Use EXACTLY the same details everywhere online:
  - Name: {brand}
  - Address: {address}
  - Phone: {phone}
- Fix mismatched listings on Yelp, Facebook, Apple Maps, and data
  aggregators - inconsistency erodes local rankings.

## Step 5 - Complete every field
- Hours (plus holiday hours), website link, appointment link,
  services list with descriptions and prices, and the business
  description (750 chars - mention {services} and {area} naturally).

## Step 6 - Photos
- Upload at least 10 real photos: exterior, interior, team, work in
  progress, before/after. Add 1-2 new photos every month.
- Name files descriptively before uploading (e.g. "{area}-job-site.jpg").

## Step 7 - Weekly posts
- Post once a week: offers, recent jobs, tips, seasonal reminders.
- Every post: one photo + 100-300 words + a call-to-action button.

## Step 8 - Review generation
- Ask every happy customer for a review - the day the job finishes is
  the best time. Share your direct review link by text or email.
- Target: 2+ new reviews per month, steadily (a sudden burst looks fake).

### Review response templates
**Positive review:**
> Thank you, [Name]! It was a pleasure helping you with [service].
> We appreciate you choosing {brand} and look forward to helping
> again any time. - The {brand} Team

**Negative review:**
> [Name], thank you for the feedback and we're sorry we missed the
> mark. We'd like to make this right - please call us at {phone}
> so we can resolve it quickly. - The {brand} Team

## Step 9 - Q&A seeding
- Post 5-8 common questions yourself (from the account) and answer
  them: pricing, service area ({area}), scheduling, guarantees.
- Turn on alerts so you can answer new public questions within 24 hours.

## Monthly maintenance checklist
- [ ] 4 posts published
- [ ] 1-2 new photos uploaded
- [ ] All new reviews responded to (within 48 hours)
- [ ] Q&A checked and answered
- [ ] Hours/services still accurate
"""


def generate_ai_integration_guide(profile: dict) -> str:
    """Markdown guide: practical AI adoption for a small business."""
    brand = profile.get("brand") or "your business"
    services = ", ".join(profile.get("services") or ["your services"])
    area = _area_of(profile)

    return f"""# Practical AI Guide for {brand}

How a small business offering {services} in {area} can use AI to win
more customers and save time - without losing the human touch.

## Part 1 - Be visible in AI answers

Customers increasingly ask ChatGPT, Google AI Overviews, Perplexity,
and Claude instead of searching. Make {brand} easy for them to cite:

1. **Publish an llms.txt file** at yoursite.com/llms.txt - a short,
   plain-text summary of who you are, what you do, where you operate,
   and your key pages. (The audit tool generates one for you.)
2. **Add structured data (schema)** - LocalBusiness, Organization, and
   FAQPage JSON-LD tell AI engines your name, services, area, hours,
   and answers with zero ambiguity.
3. **Allow AI answer-engine crawlers in robots.txt** - GPTBot,
   OAI-SearchBot, ClaudeBot, PerplexityBot. Blocking them makes you
   invisible in AI answers. (Blocking pure training bots is optional.)
4. **Answer real questions on your site** - clear, 40-60 word answers
   under question-style headings are what AI engines quote.

## Part 2 - AI in daily operations

1. **AI chat receptionist / booking** - a website chat that answers
   pricing and availability questions 24/7 and captures the lead's
   name, phone, and job details. Missed calls become booked jobs.
2. **Review-response drafting** - paste a new review into an AI
   assistant and ask for a warm, on-brand reply; edit and post.
   Respond to every review within 48 hours with 2 minutes of work.
3. **Content drafting workflow (with human review)** -
   - AI drafts the blog post / service page / social post.
   - You fact-check pricing, claims, and local details.
   - You add one real photo or example from an actual job.
   - Publish only what you'd be proud to say to a customer's face.
4. **Quotes and follow-up emails** - keep a few AI-drafted templates
   for estimates, appointment reminders, and "we missed you" messages.

## Part 3 - The don'ts

- **Don't publish AI text unreviewed.** Errors about pricing, safety,
  or licensing damage trust and can create liability.
- **Don't fake reviews or testimonials with AI.** It violates FTC
  rules and platform policies and can get your listings removed.
- **Don't paste customer personal data into consumer AI tools.**
- **Don't mass-produce thin AI pages.** Ten great pages beat a
  hundred generic ones - search engines actively demote spam.
- **Don't let a chatbot make promises** (exact prices, guarantees)
  you haven't approved - constrain it to what's on your site.

## 30-day starter plan

- Week 1: llms.txt + schema live, robots.txt allows AI crawlers.
- Week 2: FAQ page published with FAQPage schema.
- Week 3: AI chat/booking widget trialled on the site.
- Week 4: review-response and content workflows in use; measure leads.
"""


def generate_outreach_templates(profile: dict) -> str:
    """Markdown outreach email templates filled with profile values."""
    brand = profile.get("brand") or "Our Company"
    services = profile.get("services") or ["our services"]
    s0 = services[0]
    area = _area_of(profile)
    phone = profile.get("phone") or "[phone]"
    description = (profile.get("description")
                   or f"{brand} provides {', '.join(services)} in {area}.")

    return f"""# Link-Building Outreach Templates for {brand}

Personalize the [bracketed] parts before sending - generic blasts get
deleted. Send from a real person's address, keep it short, follow up
once after 5-7 days.

---

## 1. Guest-post pitch

**Subject:** Article idea for [Site Name]: {s0} tips for {area} readers

Hi [First Name],

I'm [Your Name] from {brand} - {description}

I've been reading [Site Name] and think your audience would get real
value from a practical piece like:

- "[Working title 1 - e.g. 5 {s0} mistakes {area} homeowners make]"
- "[Working title 2]"

It would be 100% original, written for your readers (not a sales
pitch), and I'm happy to match your style guide. Would either topic
be a fit?

Thanks,
[Your Name]
{brand} | {phone}

---

## 2. Unlinked brand mention -> link request

**Subject:** Quick thanks for mentioning {brand}

Hi [First Name],

I just came across your piece "[Article Title]" and wanted to say
thanks for mentioning {brand} - much appreciated.

One small ask: would you mind linking the mention to our site
([https://yoursite.com])? It helps readers find us directly and takes
10 seconds. Either way, thanks for the shout-out!

Best,
[Your Name]
{brand} | {phone}

---

## 3. Local sponsorship / PR pitch

**Subject:** {brand} would like to support [Organization/Event]

Hi [First Name],

I'm [Your Name] with {brand}, a local {s0} company serving {area}.
We're looking to give back locally this year and [Organization/Event]
stood out.

We'd love to [sponsor a team / donate services / support the event].
In return, a mention on your sponsors page (with a link to our site)
would mean a lot.

Who's the right person to talk to about this?

Warm regards,
[Your Name]
{brand} | {phone}

---

## 4. Supplier / partner link request

**Subject:** Adding {brand} to your [dealers/partners] page?

Hi [First Name],

We're a proud [customer/certified installer/authorized dealer] of
[Supplier Name] here in {area} - we've used your products on
[rough number] jobs this year.

I noticed you have a "[Where to Buy / Find an Installer / Partners]"
page. Could {brand} be added? Our details:

- Name: {brand}
- Area served: {area}
- Website: [https://yoursite.com]
- Phone: {phone}

Happy to provide anything else you need. Thanks!

[Your Name]
{brand}
"""
