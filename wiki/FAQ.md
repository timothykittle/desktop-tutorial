# FAQ

**Can I audit a site I don't own?**
Yes — the SEO checks read only public pages, so competitor and client audits
are fine. The one exception is the **[[Security Audit]]**, which sends benign
probes and should be run only on a site you own or are authorized to test.

**Do I need to be online?**
Only to audit a live URL or use PageSpeed/Claude. Auditing and repairing a
**local folder or uploaded files** works fully offline.

**Do I need an API key?**
No. Everything works without one. Keys are optional upgrades: an Anthropic key
gives Claude-written content and automatic AI-visibility tracking; a Google
PageSpeed key raises the PageSpeed quota. See
**[[Configuration and Privacy]]**.

**Does it change my website?**
No. Repair writes a **separate copy** to `./site_package/` and never touches
your originals — and it backs originals up first. You review the change log and
upload the files yourself. See **[[Repair, Verify and Backups]]**.

**What's the difference between SEO and AEO/GEO here?**
SEO = ranking in search results (the audit sections). AEO/GEO = being the answer
AI assistants give. The **[[AI Visibility (AEO-GEO)]]** tools research the
prompts and track whether you appear in AI answers.

**Does it need Python?**
Only when running from source. The built **[[.exe|Building the Windows EXE]]**
runs on any Windows PC with nothing else installed.

**Why does the off-page section not show my backlinks?**
Real backlink indexes are paid third-party services. The tool detects visible
off-page signals, scores metrics you supply, and gives you a research action
plan — see **[[Checks Reference]]**.

**Can I automate audits?**
Yes — use the command-line runner, `run_audit_cli.py`. See
**[[GitHub and CLI]]**.

**Which AI crawlers does it check for?**
GPTBot, ClaudeBot, PerplexityBot, Google-Extended, and other 2026-era AI
crawlers — because whether they're allowed determines your visibility in AI
answers. See **[[Checks Reference]]**.

**Where did my business details go / how do I reset them?**
They're saved in `business_profile.json` so you don't re-enter them. Delete that
file to start fresh. See **[[Configuration and Privacy]]**.
