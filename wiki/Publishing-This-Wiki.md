# Publishing This Wiki

These pages live in the repo's `wiki/` folder so they're versioned alongside the
code and readable on GitHub. To turn them into the repository's **GitHub Wiki**
(the "Wiki" tab), publish them to the wiki's own git repo.

## One-time: enable the wiki

On GitHub: **repo → Settings → Features → Wikis** (tick it). Then open the
**Wiki** tab and click **Create the first page** once, so the wiki git repo
exists.

## Publish the pages

The GitHub Wiki is a separate git repository at
`https://github.com/<owner>/<repo>.wiki.git`. Push these files into it:

```bash
# from the repo root
git clone https://github.com/<owner>/<repo>.wiki.git wiki-remote
cp wiki/*.md wiki-remote/
cd wiki-remote
git add .
git commit -m "Publish SEO Audit Pro wiki"
git push origin master   # wiki repos use the 'master' branch
```

That's it — the pages appear under the repo's **Wiki** tab, with the sidebar
(`_Sidebar.md`) and footer (`_Footer.md`) applied automatically.

## Page-name conventions (already followed here)

- **Home.md** is the landing page.
- **_Sidebar.md** / **_Footer.md** render on every page.
- Spaces in links map to hyphens in filenames — GitHub handles
  `[[AI Visibility (AEO-GEO)]]` → `AI-Visibility-(AEO-GEO).md` automatically.

## Keeping them in sync

Edit the pages in `wiki/` in the main repo (so changes are reviewed with the
code), then re-run the copy-and-push above to update the published wiki. You
could also automate this with a small GitHub Action on pushes that touch
`wiki/**`.
