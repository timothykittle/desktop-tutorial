"""Server log file analysis - advanced crawl-budget insight.

Parses common/combined-format access logs (Apache, Nginx, most hosts'
"raw access logs") and reports which bots (Googlebot, Bingbot, AI
crawlers) hit which URLs, how often, and with what status codes.
"""

import re
from collections import Counter

from .issues import SectionResult, WARNING, NOTICE, PASSED

# Common/combined log format:
# 1.2.3.4 - - [10/Jul/2026:06:25:01 +0000] "GET /page HTTP/1.1" 200 1234 "ref" "UA"
LOG_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>\S+)\s+(?P<path>\S+)[^"]*"\s+'
    r'(?P<status>\d{3})\s+(?P<size>\S+)'
    r'(?:\s+"(?P<referrer>[^"]*)"\s+"(?P<ua>[^"]*)")?'
)

BOT_SIGNATURES = {
    "Googlebot": r"googlebot",
    "Googlebot-Image": r"googlebot-image",
    "Bingbot": r"bingbot",
    "GPTBot": r"gptbot",
    "OAI-SearchBot": r"oai-searchbot",
    "ChatGPT-User": r"chatgpt-user",
    "ClaudeBot": r"claudebot",
    "Claude-User": r"claude-user",
    "PerplexityBot": r"perplexitybot",
    "Google-Extended": r"google-extended",
    "CCBot": r"ccbot",
    "Bytespider": r"bytespider",
    "Applebot": r"applebot",
    "AhrefsBot": r"ahrefsbot",
    "SemrushBot": r"semrushbot",
}


def analyze_log_file(path: str, log=None, max_lines: int = 2_000_000) -> SectionResult:
    log = log or (lambda m: None)
    result = SectionResult("Log File Analysis (Crawl Budget)")
    bot_hits = Counter()
    bot_paths: dict[str, Counter] = {}
    bot_statuses: dict[str, Counter] = {}
    total, parsed_count = 0, 0

    bot_patterns = {name: re.compile(pattern, re.I)
                    for name, pattern in BOT_SIGNATURES.items()}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                total += 1
                if total > max_lines:
                    log(f"  Stopping at {max_lines:,} lines.")
                    break
                m = LOG_RE.match(line)
                if not m:
                    continue
                parsed_count += 1
                ua = m.group("ua") or ""
                for name, pattern in bot_patterns.items():
                    if pattern.search(ua):
                        bot_hits[name] += 1
                        bot_paths.setdefault(name, Counter())[m.group("path")] += 1
                        bot_statuses.setdefault(name, Counter())[m.group("status")] += 1
                        break
    except OSError as exc:
        result.add(WARNING, "Log Analysis", f"Could not read log file: {exc}")
        return result

    if parsed_count == 0:
        result.add(WARNING, "Log Analysis",
                   f"No lines matched the common/combined log format "
                   f"({total:,} lines read).",
                   fix="Export the raw access log (Apache/Nginx combined format) "
                       "from your hosting control panel.")
        return result

    result.add(PASSED, "Log Analysis",
               f"Parsed {parsed_count:,} of {total:,} lines; "
               f"{sum(bot_hits.values()):,} bot hits identified.")

    if bot_hits.get("Googlebot", 0) == 0:
        result.add(WARNING, "Crawl Budget",
                   "No Googlebot visits found in this log.",
                   fix="If the log covers several days, Google may not be crawling: "
                       "verify the site in Search Console, submit the sitemap, and "
                       "check robots.txt / firewall rules.")
    ai_bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot",
               "Claude-User", "PerplexityBot", "CCBot", "Bytespider"]
    ai_total = sum(bot_hits.get(b, 0) for b in ai_bots)
    if ai_total:
        top_ai = ", ".join(f"{b}: {bot_hits[b]:,}" for b in ai_bots if bot_hits.get(b))
        result.add(PASSED, "AI Crawlers", f"AI crawlers ARE visiting: {top_ai}.")
    else:
        result.add(NOTICE, "AI Crawlers",
                   "No AI crawler visits found in this log.",
                   fix="If you want AI-answer visibility, confirm AI bots aren't "
                       "blocked in robots.txt, your firewall, or your CDN's bot "
                       "protection (Cloudflare et al. often block them by default).")

    for name, statuses in bot_statuses.items():
        errors = sum(count for status, count in statuses.items()
                     if status.startswith(("4", "5")))
        hits = bot_hits[name]
        if hits >= 10 and errors / hits > 0.10:
            result.add(WARNING, "Crawl Budget",
                       f"{name}: {errors:,} of {hits:,} hits ({errors / hits:.0%}) "
                       f"got 4xx/5xx errors - wasted crawl budget.",
                       fix="Fix or redirect the erroring URLs so bots spend their "
                           "budget on real pages.")

    result.data["bot_hits"] = dict(bot_hits.most_common())
    result.data["top_paths"] = {
        name: dict(paths.most_common(10)) for name, paths in bot_paths.items()
        if name in ("Googlebot", "GPTBot", "ClaudeBot", "PerplexityBot", "Bingbot")
    }
    return result
