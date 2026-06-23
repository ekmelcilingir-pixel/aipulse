# AiPulse — your own daily AI-market report

A self-hosted, auto-updating version of the AiPulse report. Every weekday a
GitHub Actions cron job pulls market data, has Claude write the analysis, renders
a styled HTML page, and publishes it to GitHub Pages.

```
fetch_data.py   →  data/data.json     (numbers: FMP)
generate.py     →  data/model.json    (narrative + scores: Claude)
render.py       →  public/index.html  (numbers + narrative → styled page)
```

**Design principle:** every price/percentage on the page is computed in
`render.py` from `data.json`. Claude only supplies judgment (0–100 component
scores, verdicts, prose). The model never invents numbers, so the page stays
auditable.

---

## 1. One-time setup

1. Create a new GitHub repo and drop these files in.
2. **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `FMP_API_KEY` — your Financial Modeling Prep key
   - `ANTHROPIC_API_KEY` — your Anthropic key
3. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
4. Edit `config/portfolio.json` with your real positions (lots + average cost).
5. Edit `config/universe.json` if you want different tracked stocks/indices.

## 2. Run it

- **Automatic:** weekdays at 22:00 UTC (after the U.S. close). Adjust the `cron`
  line in `.github/workflows/daily.yml` if you prefer pre-market.
- **Manual:** Actions tab → *AiPulse Daily* → *Run workflow*.

Your report lives at `https://<username>.github.io/<repo>/`.

## 3. Run locally

```bash
pip install -r requirements.txt
export FMP_API_KEY=...        # for live data
export ANTHROPIC_API_KEY=...  # for the narrative
python src/fetch_data.py      # → data/data.json
python src/generate.py        # → data/model.json
python src/render.py          # → public/index.html
```

No keys handy? The repo ships with sample `data/data.json` + `data/model.json`,
so `python src/render.py` alone produces a full demo page immediately.

## 4. What's in the report

01 AI Health Score (7 weighted components, gauge) · 02 Core AI Stocks ·
03 Infrastructure Indices · 04 Value-Chain Layers · 05 Institutional Positioning ·
06 Critical News · 07 Earnings Conversion (hyperscaler capex YoY) ·
08 Thesis Check (your portfolio) · 09 Compute RV & Trade Ideas · 10 Self-Audit.

Plus the glossary-balloon engine (hover/tap underlined terms), the ticker
auto-linker, and the floating toolbar (Open / Print / Copy / Fullscreen) — all
carried over from the original.

## 5. Customizing

- **Branding:** set env `AIPULSE_BRAND` (default `AiPulse`).
- **Model:** set env `AIPULSE_MODEL` (default `claude-haiku-4-5`; use a larger
  model for richer prose).
- **Scoring weights / component set:** edit the `SCHEMA` block in
  `src/generate.py` and the weighting reads straight through to `render.py`.
- **Panels / layout:** `src/template.html` (Jinja). The CSS + JS engines are the
  originals, preserved verbatim.
- **Deploy elsewhere (Netlify/Vercel):** skip the Pages steps and point your host
  at the generated `public/` folder, or run the three scripts in their build step.

## 6. Notes

- GitHub Actions cron runs in UTC and can be delayed several minutes under load.
- FMP free tier rate-limits some endpoints; `fetch_data.py` already paces calls
  and degrades gracefully (missing fields render as `—`).
- Personal decision aid — not investment advice.
