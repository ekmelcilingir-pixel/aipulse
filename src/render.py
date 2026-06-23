"""
render.py — merge data.json (authoritative numbers) + model.json (Claude's
narrative/scores) into the styled template -> public/index.html.

All numeric labels and red/green classes are computed HERE from data.json,
so the rendered numbers always match the source data regardless of the LLM.

Runs standalone:  python src/render.py
Optionally point at samples:  python src/render.py --data data/data.json --model data/model.json
"""
import os, json, math, argparse, datetime

from jinja2 import Environment, FileSystemLoader

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
BRAND = os.environ.get("AIPULSE_BRAND", "AiPulse")
TAGLINE = "AI market health barometer — daily"

MINUS = "\u2212"  # proper minus sign, matches the original report


# ---------- formatting helpers ----------
def pct(v, dp=1):
    if v is None:
        return "—"
    s = f"{abs(v):.{dp}f}%"
    return ("+" + s) if v >= 0 else (MINUS + s)


def money(v, dp=2):
    if v is None:
        return "—"
    return f"${v:,.{dp}f}"


def cls(v):
    if v is None:
        return ""
    return "pos" if v >= 0 else "neg"


def arc(score):
    """SVG arc-fill path + color for a 0-100 gauge over the half-circle
    M20,110 A80,80 ... to 180,110 (center 100,110, r80)."""
    s = max(0, min(100, score))
    ang = math.radians(180 - 1.8 * s)
    x = 100 + 80 * math.cos(ang)
    y = 110 - 80 * math.sin(ang)
    path = f"M 20 110 A 80 80 0 0 1 {x:.2f} {y:.2f}"
    color = ("#ef4444" if s < 41 else "#f59e0b" if s < 61
             else "#a78bfa" if s < 81 else "#22c55e")
    return path, color


# ---------- merge ----------
def build_context(data, model):
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))  # TRT
    date_long = now.strftime("%B %-d, %Y")
    date_short = now.strftime("%b %-d")
    weekday = now.strftime("%A")
    time_label = now.strftime("%H:%M") + " TRT"

    # --- health score: weighted from components (auditable) ---
    comps = model["health"]["components"]
    total = sum(c["weight"] * c["score"] for c in comps)
    score = round(total)
    for c in comps:
        c["cls"] = ("pos" if c["score"] >= 61 else "neg" if c["score"] < 41 else "")
    arc_path, arc_color = arc(score)

    # --- core stock cards ---
    snotes = model.get("stock_notes", {})
    core = json.load(open(os.path.join(ROOT, "config", "universe.json")))["stocks"]
    stocks = []
    for t in core:
        d = data["stocks"].get(t, {})
        a50 = d.get("above_50d")
        stocks.append({
            "ticker": t,
            "price_label": money(d.get("price")),
            "chg_1d_label": pct(d.get("chg_1d")), "chg_cls": cls(d.get("chg_1d")),
            "chg_1w_label": pct(d.get("chg_1w")), "w_cls": cls(d.get("chg_1w")),
            "sma_label": ("above" if a50 else "below" if a50 is not None else "—"),
            "sma_cls": ("pos" if a50 else "neg" if a50 is not None else ""),
            "fwd_pe_label": (f"{d.get('pe'):.1f}" if d.get("pe") else "—"),
            "note": snotes.get(t, ""),
        })

    # --- indices ---
    inotes = model.get("indices_notes", {})
    indices = []
    for ix in data["indices"]:
        indices.append({
            "name": ix["name"],
            "chg_1d_label": pct(ix.get("chg_1d")), "d_cls": cls(ix.get("chg_1d")),
            "chg_1w_label": pct(ix.get("chg_1w")), "w_cls": cls(ix.get("chg_1w")),
            "note": inotes.get(ix["ticker"], ""),
        })

    # --- thesis / portfolio ---
    verdicts = model["thesis"].get("verdicts", {})
    vlabel = {"hold": "Hold", "add": "Add", "trim": "Trim"}
    positions = []
    for p in data["portfolio"]:
        t = p["ticker"]
        last = data["stocks"].get(t, {}).get("price")
        cost = p.get("cost")
        pnl = ((last - cost) / cost * 100) if (last and cost) else None
        v = verdicts.get(t, {"verdict": "hold", "note": ""})
        positions.append({
            "ticker": t, "lots": p.get("lots"),
            "cost_label": money(cost), "last_label": money(last),
            "pnl_label": pct(pnl), "pnl_cls": cls(pnl),
            "verdict": v.get("verdict", "hold"),
            "verdict_label": vlabel.get(v.get("verdict", "hold"), "Hold"),
            "note": v.get("note", ""),
        })

    # --- glossary + ticker links ---
    glossary, seen = [], set()
    for g in model.get("glossary", []):
        k = g.get("k")
        if k and k not in seen:
            seen.add(k); glossary.append(g)
    link_set = sorted({p["ticker"] for p in data["portfolio"]} | set(core)
                      | {ix["ticker"] for ix in data["indices"]})

    h = model["health"]
    return {
        "brand": BRAND, "tagline": TAGLINE,
        "date_long": date_long, "date_short": date_short,
        "weekday": weekday, "time_label": time_label,
        "basis": f"based on the {date_long} close",
        "data_sources": "FMP (live) · Claude (synthesis)",
        "generated_at": now.strftime("%Y-%m-%d %H:%M TRT"),
        "intro": model["intro"],
        "health": {
            "score": score, "label": h.get("label", ""),
            "delta_label": " · first run (no Δ)",
            "arc_path": arc_path, "arc_color": arc_color,
            "components": comps, "commentary": h.get("commentary", ""),
        },
        "stocks": stocks,
        "indices": indices,
        "value_chain": model["value_chain"],
        "positioning": model.get("positioning", ""),
        "news": [dict(n, impact_label=n["impact"].upper()) for n in model.get("news", [])],
        "earnings": {"hyperscaler_capex_yoy": data.get("hyperscaler_capex_yoy") or "—",
                     "note": model.get("earnings_note", ""), "rows": []},
        "thesis": {"overall": model["thesis"].get("overall", ""), "positions": positions},
        "trade_ideas": model.get("trade_ideas", []),
        "self_audit": model.get("self_audit", []),
        "glossary_json": json.dumps(glossary, ensure_ascii=False),
        "ticker_links_json": json.dumps(link_set),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "data.json"))
    ap.add_argument("--model", default=os.path.join(ROOT, "data", "model.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "public", "index.html"))
    args = ap.parse_args()

    data = json.load(open(args.data))
    model = json.load(open(args.model))
    env = Environment(loader=FileSystemLoader(HERE), autoescape=False)
    tpl = env.get_template("template.html")
    html = tpl.render(**build_context(data, model))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out, "w", encoding="utf-8").write(html)
    print(f"Wrote {args.out} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
