"""Headless command-line runner - same engine as the GUI.

Examples:
  python run_audit_cli.py https://example.com
  python run_audit_cli.py example.com --max-pages 50 --keywords "blue widgets, widget repair"
  python run_audit_cli.py example.com --skip-pagespeed
  python run_audit_cli.py --log-file access.log
"""

import argparse
import sys

from seo_audit.audit import AuditRunner
from seo_audit.logfile import analyze_log_file
from seo_audit.report import make_output_dir, save_reports


def main():
    parser = argparse.ArgumentParser(description="SEO Audit Pro (CLI)")
    parser.add_argument("url", nargs="?", help="Site URL to audit")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--keywords", default="",
                        help="Comma-separated target keywords")
    parser.add_argument("--psi-key", default="", help="PageSpeed API key")
    parser.add_argument("--skip-pagespeed", action="store_true")
    parser.add_argument("--skip-onpage", action="store_true")
    parser.add_argument("--skip-technical", action="store_true")
    parser.add_argument("--skip-offpage", action="store_true")
    parser.add_argument("--brand", default="")
    parser.add_argument("--backlinks", default="")
    parser.add_argument("--referring-domains", default="")
    parser.add_argument("--domain-authority", default="")
    parser.add_argument("--local", action="store_true",
                        help="Treat as local business")
    parser.add_argument("--log-file", default="",
                        help="Analyze a server access log instead of crawling")
    parser.add_argument("--output", default="audits", help="Output base folder")
    args = parser.parse_args()

    if args.log_file:
        section = analyze_log_file(args.log_file, log=print)
        out = make_output_dir(args.output, args.url or "logfile-analysis")
        paths = save_reports(out, args.url or "logfile-analysis", [section],
                             [f"Log file analyzed: {args.log_file}"])
        print(f"\nScore: {section.score}/100")
        print(f"HTML report: {paths['html']}")
        return

    if not args.url:
        parser.error("provide a URL or --log-file")

    runner = AuditRunner(
        args.url, max_pages=args.max_pages,
        keywords=args.keywords.split(",") if args.keywords else [],
        psi_api_key=args.psi_key,
        offpage_manual={
            "brand_name": args.brand,
            "backlinks": args.backlinks,
            "referring_domains": args.referring_domains,
            "domain_authority": args.domain_authority,
            "is_local_business": args.local,
        },
        output_base=args.output, log=print)
    result = runner.run(do_onpage=not args.skip_onpage,
                        do_technical=not args.skip_technical,
                        do_offpage=not args.skip_offpage,
                        do_pagespeed=not args.skip_pagespeed)
    sys.exit(0 if result["overall"] >= 0 else 1)


if __name__ == "__main__":
    main()
