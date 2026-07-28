# AI Visibility (AEO / GEO)

**AEO** (Answer Engine Optimization) / **GEO** (Generative Engine Optimization)
is about being the answer AI assistants give — ChatGPT, Perplexity, Google AI
Overviews — not just ranking on a results page. SEO Audit Pro gives you two
tools for it, in the **AI visibility (AEO/GEO)** button group.

## 1. Prompt research

Click **🔎 Prompt research**. From the loaded business's services, service
areas, and buyer intent, it generates the real questions people ask AI
assistants that this business should be the answer to — grouped into clusters:

- **Informational** — "How much does <service> cost in <town>?"
- **Commercial / near-me** — "Who is the best <service> company in <town>?"
- **Local / urgent** — "I need emergency <service> in <town> today…"
- **Comparison** — "<service> vs doing it myself…"
- **Brand** — "Is <brand> a good <service> company?"

Output is saved to `site_package/ai-visibility/` in three formats:

| File | Use |
|------|-----|
| `ai-prompt-targets.md` | Readable list to plan content around |
| `ai-prompt-targets.csv` | Spreadsheet (intent + prompt columns) |
| `ai-prompt-targets.json` | Feeds the tracker |

With an Anthropic API key set, the phrasing is AI-curated and more natural;
without one, it uses solid templates.

## 2. Track AI visibility

Click **📊 Track AI visibility**. For your saved prompt list, it checks whether
the brand / domain actually shows up in AI answers.

- **With an Anthropic API key** — each prompt is run through Claude with **live
  web search**, and the answer is classified:
  - **Cited** — your domain appears in the answer's sources.
  - **Mentioned** — your brand/domain appears in the answer text.
  - **Absent** — not present.
- **Without a key** — it opens browser searches (Google, Perplexity) for each
  prompt so you can check and log manually.

### Tracking over time

Every run is **timestamped** and saved under
`site_package/ai-visibility/tracking/`:

- One JSON record per run (with the citations found).
- A rolling `tracking-history.csv` — one row per run — so you can chart your
  visibility trend.
- The summary reports the **change since your last run** (e.g. "+3 visible"),
  so you can see content and outreach paying off.

## How to improve the numbers

1. **Let AI crawlers in.** The technical audit flags blocked AI crawlers — fix
   those first (see **[[Checks Reference]]**).
2. **Answer the prompts on your site.** Turn the prompt list into FAQ entries,
   blog posts, and service pages — see **[[Content Creation]]**.
3. **Add `llms.txt` and schema.** The repair engine and fix files generate
   these — see **[[Repair, Verify and Backups]]**.
4. **Re-track** every few weeks and watch the trend.
