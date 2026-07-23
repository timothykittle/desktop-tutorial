"""Google PageSpeed Insights API integration - performance scores and
Core Web Vitals (LCP, INP, CLS) for mobile and desktop.

Works without an API key for occasional use (Google allows keyless
requests with tight rate limits); an API key raises the quota. Free keys:
https://developers.google.com/speed/docs/insights/v5/get-started
"""

import requests

from .issues import SectionResult, CRITICAL, WARNING, NOTICE, PASSED

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Core Web Vitals thresholds (good / needs improvement)
CWV_THRESHOLDS = {
    "LARGEST_CONTENTFUL_PAINT_MS": (2500, 4000, "LCP", "ms"),
    "INTERACTION_TO_NEXT_PAINT": (200, 500, "INP", "ms"),
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": (10, 25, "CLS", "/100"),  # PSI reports CLS*100
}


def run_pagespeed_audit(url: str, api_key: str = "", log=None,
                        timeout=90) -> SectionResult:
    log = log or (lambda m: None)
    result = SectionResult("Page Speed & Core Web Vitals")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    for strategy in ("mobile", "desktop"):
        log(f"  Running PageSpeed Insights ({strategy})... this can take ~30s")
        params = {
            "url": url,
            "strategy": strategy,
            "category": ["performance", "seo"],
        }
        if api_key:
            params["key"] = api_key
        try:
            resp = requests.get(PSI_ENDPOINT, params=params, timeout=timeout)
            data = resp.json()
        except requests.RequestException as exc:
            result.add(WARNING, "PageSpeed",
                       f"Could not reach PageSpeed Insights API ({strategy}): {exc}",
                       fix="Check your internet connection, or add an API key in "
                           "Settings if you hit rate limits.")
            continue
        if "error" in data:
            result.add(WARNING, "PageSpeed",
                       f"PageSpeed API error ({strategy}): "
                       f"{data['error'].get('message', 'unknown')}",
                       fix="Add a free API key in Settings to avoid rate limits: "
                           "https://developers.google.com/speed/docs/insights/v5/get-started")
            continue

        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        perf = categories.get("performance", {}).get("score")
        seo_score = categories.get("seo", {}).get("score")
        strategy_data = {"strategy": strategy}

        if perf is not None:
            perf100 = round(perf * 100)
            strategy_data["performance_score"] = perf100
            severity = (PASSED if perf100 >= 90 else
                        WARNING if perf100 >= 50 else CRITICAL)
            result.add(severity, "Performance Score",
                       f"[{strategy.title()}] Lighthouse performance: {perf100}/100.",
                       url,
                       fix="" if perf100 >= 90 else
                       "See the specific opportunities below; biggest wins usually: "
                       "compress/lazy-load images, remove unused JS/CSS, enable "
                       "caching + CDN, upgrade hosting.")
        if seo_score is not None:
            strategy_data["seo_score"] = round(seo_score * 100)

        # Lab metrics
        audits = lighthouse.get("audits", {})
        for audit_id, label in (("largest-contentful-paint", "LCP"),
                                ("cumulative-layout-shift", "CLS"),
                                ("total-blocking-time", "TBT"),
                                ("first-contentful-paint", "FCP"),
                                ("speed-index", "Speed Index")):
            a = audits.get(audit_id, {})
            if a.get("displayValue"):
                strategy_data[label] = a["displayValue"]

        # Field data (real-user Core Web Vitals) when available
        field = data.get("loadingExperience", {}).get("metrics", {})
        for metric_key, (good, poor, label, unit) in CWV_THRESHOLDS.items():
            m = field.get(metric_key)
            if not m:
                continue
            value = m.get("percentile", 0)
            display = f"{value / 100:.2f}" if label == "CLS" else f"{value} ms"
            strategy_data[f"CWV_{label}"] = display
            severity = (PASSED if value <= good else
                        WARNING if value <= poor else CRITICAL)
            result.add(severity, "Core Web Vitals",
                       f"[{strategy.title()}] Real-user {label}: {display} "
                       f"({'good' if severity == PASSED else 'needs improvement' if severity == WARNING else 'poor'}).",
                       url,
                       fix="" if severity == PASSED else {
                           "LCP": "Optimize the largest element: compress the hero "
                                  "image, preload it, use a CDN, cut render-blocking "
                                  "resources, improve server response time.",
                           "INP": "Reduce JavaScript work: split long tasks, defer "
                                  "non-critical JS, minimize third-party scripts.",
                           "CLS": "Set width/height on images/ads/embeds, avoid "
                                  "inserting content above existing content, "
                                  "preload fonts.",
                       }[label])

        # Top improvement opportunities
        opportunities = []
        for audit_id, a in audits.items():
            details = a.get("details", {})
            if details.get("type") == "opportunity" and a.get("score", 1) is not None \
                    and a.get("score", 1) < 0.9:
                savings = details.get("overallSavingsMs", 0)
                if savings and savings > 100:
                    opportunities.append((savings, a.get("title", audit_id)))
        opportunities.sort(reverse=True)
        for savings, title in opportunities[:5]:
            result.add(NOTICE, "Speed Opportunities",
                       f"[{strategy.title()}] {title} (est. savings "
                       f"{savings / 1000:.1f}s).", url,
                       fix="Details in the PageSpeed Insights report - use the "
                           "'Open PageSpeed' button.")

        result.data[strategy] = strategy_data
    return result
