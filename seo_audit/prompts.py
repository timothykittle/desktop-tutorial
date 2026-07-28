"""AI-answer (AEO/GEO) prompt research and visibility tracking.

Two jobs:
  1. research_prompts(): what questions do people actually ask AI engines
     (ChatGPT, Perplexity, Google AI Overviews) that your business should be
     the answer to? Built from your services x locations x buyer intent, so
     you know exactly what content to create and what to track.
  2. track_visibility(): for a saved prompt list, check whether your brand /
     domain shows up in the AI answer. With a Claude API key it runs each
     prompt through Claude with live web search and inspects the answer and
     its citations; without a key it hands you one-click browser searches to
     check and log yourself. Every run is timestamped so you can watch your
     AI visibility improve over time.
"""

import csv
import json
import os
from datetime import datetime
from urllib.parse import quote_plus, urlparse

# Buyer-intent buckets and the prompt shapes people use for each. {s}=service,
# {t}=town/area, {b}=brand. Kept natural-language, the way someone talks to an
# AI assistant rather than types into a search box.
INTENT_TEMPLATES = {
    "Informational": [
        "How much does {s} cost in {t}?",
        "How do I choose a good {s} company in {t}?",
        "What should I look for when hiring {s} in {t}?",
        "Is {s} worth it for a home in {t}?",
        "How often should I get {s} in {t}?",
    ],
    "Commercial / near-me": [
        "Who is the best {s} company in {t}?",
        "Recommend a reliable {s} service near {t}.",
        "Top-rated {s} in {t}?",
        "Affordable {s} in {t} with good reviews?",
        "Who offers same-day {s} in {t}?",
    ],
    "Local / urgent": [
        "I need emergency {s} in {t} today - who should I call?",
        "24/7 {s} near {t}?",
        "Licensed and insured {s} serving {t}?",
    ],
    "Comparison": [
        "{s} vs doing it myself - what's better in {t}?",
        "How do {s} companies in {t} compare on price?",
    ],
    "Brand": [
        "Is {b} a good {s} company?",
        "What do people say about {b} in {t}?",
        "Does {b} serve {t}?",
    ],
}


def _services(profile):
    s = profile.get("services") or []
    if isinstance(s, str):
        s = [x.strip() for x in s.split(",") if x.strip()]
    return s or ["your service"]


def _areas(profile):
    locs = profile.get("locations") or []
    if not locs:
        locs = [profile.get("city") or "your area"]
    return locs


def research_prompts(profile, api_key="", max_per_cluster=12):
    """Return {"clusters": {intent: [prompts]}, "flat": [...], "count": N}.

    Deterministic templates by default; if a Claude key is supplied, a curated,
    de-duplicated set is requested and slotted into the same clusters (falling
    back to templates if the call fails).
    """
    brand = profile.get("brand") or "your business"
    services = _services(profile)
    areas = _areas(profile)

    clusters = {}
    for intent, shapes in INTENT_TEMPLATES.items():
        out, seen = [], set()
        for svc in services:
            for area in areas:
                for shape in shapes:
                    p = shape.format(s=svc.lower(), t=area, b=brand)
                    # tidy capitalization
                    p = p[0].upper() + p[1:]
                    if p not in seen:
                        seen.add(p)
                        out.append(p)
                    if len(out) >= max_per_cluster:
                        break
                if len(out) >= max_per_cluster:
                    break
            if len(out) >= max_per_cluster:
                break
        clusters[intent] = out

    # Optional AI curation for more natural / long-tail phrasing.
    if api_key:
        enhanced = _ai_prompts(profile, services, areas, api_key)
        if enhanced:
            clusters = enhanced

    flat = [p for group in clusters.values() for p in group]
    return {"clusters": clusters, "flat": flat, "count": len(flat)}


def _ai_prompts(profile, services, areas, api_key):
    from .assistant import ai_enhance
    brand = profile.get("brand") or "the business"
    prompt = (
        f"You are an AEO/GEO strategist. List the real questions people ask AI "
        f"assistants (ChatGPT, Perplexity, Google AI Overviews) where this "
        f"business should be the recommended answer.\n"
        f"Business: {brand}\nServices: {', '.join(services)}\n"
        f"Areas served: {', '.join(areas[:12])}\n\n"
        f"Return STRICT format, nothing else. Use these exact section headers, "
        f"each followed by 8-12 questions, one per line prefixed with '- ':\n"
        f"## Informational\n## Commercial / near-me\n## Local / urgent\n"
        f"## Comparison\n## Brand\n")
    text = ai_enhance(prompt, api_key)
    if not text:
        return None
    clusters, current = {}, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("##"):
            current = line.lstrip("#").strip()
            clusters[current] = []
        elif line.startswith(("- ", "* ")) and current:
            clusters[current].append(line[2:].strip())
    return clusters if any(clusters.values()) else None


def save_prompts(profile, research, out_dir):
    """Write prompts as .md (readable), .csv (spreadsheet), .json (for the
    tracker). Returns {"md","csv","json"}."""
    os.makedirs(out_dir, exist_ok=True)
    brand = profile.get("brand") or "your business"
    md = [f"# AI-answer prompt targets - {brand}",
          f"_Generated {datetime.now():%Y-%m-%d}._ These are the questions to "
          f"create content for and to track in AI answers.\n"]
    rows = [("intent", "prompt")]
    for intent, group in research["clusters"].items():
        md.append(f"\n## {intent}\n")
        for p in group:
            md.append(f"- {p}")
            rows.append((intent, p))
    md_path = os.path.join(out_dir, "ai-prompt-targets.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    csv_path = os.path.join(out_dir, "ai-prompt-targets.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        csv.writer(fh).writerows(rows)
    json_path = os.path.join(out_dir, "ai-prompt-targets.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"brand": brand, "generated": datetime.now().isoformat(),
                   "clusters": research["clusters"], "flat": research["flat"]},
                  fh, indent=2)
    return {"md": md_path, "csv": csv_path, "json": json_path}


# ---------------------------------------------------------------------------
# Visibility tracking
# ---------------------------------------------------------------------------

def _classify(answer_text, citations, brand, domain):
    """Return 'cited' | 'mentioned' | 'absent' for one AI answer."""
    text_l = (answer_text or "").lower()
    brand_l = (brand or "").lower().strip()
    dom_l = (domain or "").lower().strip()
    for url in citations or []:
        if dom_l and dom_l in (url or "").lower():
            return "cited"
    if brand_l and brand_l in text_l:
        return "mentioned"
    if dom_l and dom_l in text_l:
        return "mentioned"
    return "absent"


def _ask_with_search(client, prompt):
    """One Claude call with live web search. Returns (answer_text, [citation
    urls]). Best-effort; raises on hard API errors for the caller to handle."""
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4000,
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    texts, cites = [], []
    for block in resp.content:
        btype = getattr(block, "type", "")
        if btype == "text":
            texts.append(block.text)
            for c in (getattr(block, "citations", None) or []):
                u = getattr(c, "url", None)
                if u:
                    cites.append(u)
        elif btype == "web_search_tool_result":
            content = getattr(block, "content", None)
            if isinstance(content, list):
                for item in content:
                    u = getattr(item, "url", None)
                    if u:
                        cites.append(u)
    return " ".join(texts), cites


def track_visibility(prompts, profile, api_key="", history_dir=None,
                     log=None, max_prompts=40):
    """Check AI-answer visibility for a list of prompts.

    With api_key: runs each prompt through Claude + web search, classifying the
    answer as cited / mentioned / absent for your brand+domain.
    Without api_key: returns manual-check rows with one-click browser search
    URLs (Google, Perplexity) and status 'manual'.

    Saves a timestamped run to history_dir and reports the change vs the
    previous run. Returns {"rows", "summary", "saved", "delta", "mode"}.
    """
    log = log or (lambda m: None)
    brand = profile.get("brand") or ""
    base = profile.get("base_url") or profile.get("website") or ""
    domain = urlparse(base if "//" in base else "//" + base).netloc if base else ""
    domain = domain.replace("www.", "")
    prompts = [p for p in prompts if p][:max_prompts]

    rows = []
    mode = "manual"
    client = None
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            mode = "ai"
        except Exception:
            client = None

    for i, prompt in enumerate(prompts, 1):
        if client:
            try:
                log(f"  [{i}/{len(prompts)}] asking AI: {prompt[:60]}")
                answer, cites = _ask_with_search(client, prompt)
                status = _classify(answer, cites, brand, domain)
                rows.append({"prompt": prompt, "status": status,
                             "citations": cites[:5]})
            except Exception as exc:
                log(f"    (AI check failed, falling back to manual: {exc})")
                rows.append({"prompt": prompt, "status": "manual",
                             "google": f"https://www.google.com/search?q={quote_plus(prompt)}",
                             "perplexity": f"https://www.perplexity.ai/search?q={quote_plus(prompt)}"})
        else:
            rows.append({"prompt": prompt, "status": "manual",
                         "google": f"https://www.google.com/search?q={quote_plus(prompt)}",
                         "perplexity": f"https://www.perplexity.ai/search?q={quote_plus(prompt)}"})

    summary = {"cited": 0, "mentioned": 0, "absent": 0, "manual": 0}
    for r in rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    summary["visible"] = summary["cited"] + summary["mentioned"]
    summary["total"] = len(rows)

    saved, delta = "", {}
    if history_dir:
        saved, delta = _save_tracking(history_dir, brand, domain, summary, rows)
    log(f"Visibility: {summary['visible']}/{summary['total']} prompts where "
        f"{brand or 'you'} appears ({summary['cited']} cited, "
        f"{summary['mentioned']} mentioned).")
    return {"rows": rows, "summary": summary, "saved": saved, "delta": delta,
            "mode": mode}


def _save_tracking(history_dir, brand, domain, summary, rows):
    os.makedirs(history_dir, exist_ok=True)
    # delta vs the most recent prior run
    prior = None
    runs = sorted(f for f in os.listdir(history_dir)
                  if f.startswith("tracking-") and f.endswith(".json"))
    if runs:
        try:
            with open(os.path.join(history_dir, runs[-1]), encoding="utf-8") as fh:
                prior = json.load(fh).get("summary")
        except (OSError, json.JSONDecodeError):
            prior = None
    delta = {}
    if prior:
        delta = {"visible": summary["visible"] - prior.get("visible", 0),
                 "cited": summary["cited"] - prior.get("cited", 0)}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rec = {"timestamp": datetime.now().isoformat(), "brand": brand,
           "domain": domain, "summary": summary, "rows": rows, "delta": delta}
    path = os.path.join(history_dir, f"tracking-{stamp}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    # running history CSV (one row per run) for a quick trend line
    hist_csv = os.path.join(history_dir, "tracking-history.csv")
    new = not os.path.exists(hist_csv)
    with open(hist_csv, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["timestamp", "visible", "cited", "mentioned",
                        "absent", "manual", "total"])
        w.writerow([rec["timestamp"], summary["visible"], summary["cited"],
                    summary["mentioned"], summary["absent"],
                    summary.get("manual", 0), summary["total"]])
    return path, delta
