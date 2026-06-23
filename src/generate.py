"""
generate.py — feed the quantitative snapshot (data.json) to Claude and get back
the narrative "report model" (model.json): intro, component scores + commentary,
value-chain health, positioning, news framing, thesis verdicts, trade ideas,
self-audit, and glossary additions.

Design rule: Claude provides JUDGMENT (scores 0-100, verdicts, prose).
It must NOT invent prices/percentages — those are rendered from data.json by
render.py. This keeps every number auditable.

Env:
  ANTHROPIC_API_KEY  required
  AIPULSE_MODEL      optional (default: claude-haiku-4-5)
"""
import os, json, sys, re

import anthropic

MODEL = os.environ.get("AIPULSE_MODEL", "claude-haiku-4-5")
HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data", "data.json")
OUT = os.path.join(HERE, "..", "data", "model.json")

SCHEMA = """Return ONLY a JSON object (no markdown, no prose outside JSON) with EXACTLY these keys:
{
  "intro": [ {"lead": "<bold lead-in>", "text": "<one sentence>"}, ... 2-3 items, last lead MUST be "Bottom line:" ],
  "health": {
    "label": "<Weak|Mixed|Moderate|Strong|Very strong>",
    "commentary": "<2-4 sentence read of overall AI-market health>",
    "components": [
      {"id":"C1","name":"Price momentum","weight":0.20,"score":<0-100>,"note":"<short>"},
      {"id":"C2","name":"Breadth (above 50D)","weight":0.15,"score":<0-100>,"note":"<short>"},
      {"id":"C3","name":"Memory / HBM cycle","weight":0.15,"score":<0-100>,"note":"<short>"},
      {"id":"C4","name":"Hyperscaler capex","weight":0.20,"score":<0-100>,"note":"<short>"},
      {"id":"C5","name":"Valuation vs growth","weight":0.10,"score":<0-100>,"note":"<short>"},
      {"id":"C6","name":"Networking / interconnect","weight":0.10,"score":<0-100>,"note":"<short>"},
      {"id":"C7","name":"Software / application","weight":0.10,"score":<0-100>,"note":"<short>"}
    ]
  },
  "stock_notes": { "<TICKER>": "<<=12-word note>", ... only for the core stocks },
  "indices_notes": { "<TICKER>": "<<=8-word note>", ... },
  "value_chain": [ {"layer":"<exact layer name from data>","health":"green|amber|red","note":"<short>"}, ... one per layer ],
  "positioning": "<2-3 sentences on institutional positioning / flows>",
  "news": [ {"headline":"<short>","impact":"high|med|low","note":"<one clause>"}, ... 3-6 items, base them on the provided headlines ],
  "earnings_note": "<1-2 sentences interpreting hyperscaler capex YoY>",
  "thesis": {
    "overall": "<2-3 sentence portfolio-level read>",
    "verdicts": { "<TICKER>": {"verdict":"hold|add|trim","note":"<<=14-word note>"}, ... one per portfolio ticker }
  },
  "trade_ideas": [ {"title":"<short>","rationale":"<1-2 sentences>"}, ... 2-3 items ],
  "self_audit": [ "<assumption/risk/limitation>", ... 2-4 bullets ],
  "glossary": [ {"k":"<TERM or TICKER>","t":"<title>","d":"<plain-English 1 sentence>"}, ... 6-12 items for jargon you used ]
}
Scores: 0-40 weak, 41-60 mixed, 61-80 strong, 81-100 very strong. Weights are fixed as given. Be specific and sober; this is a personal decision aid, not hype."""


def strip_json(txt):
    txt = txt.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?", "", txt)
        txt = re.sub(r"\n?```$", "", txt)
    # grab outermost { ... }
    a, b = txt.find("{"), txt.rfind("}")
    return txt[a:b + 1] if a >= 0 and b > a else txt


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    data = json.load(open(DATA))

    # compact the data so the prompt stays small
    compact = {
        "stocks": {t: {k: v.get(k) for k in ("price", "chg_1d", "chg_1w", "above_50d", "pe")}
                   for t, v in data["stocks"].items()},
        "indices": data["indices"],
        "value_chain": data["value_chain"],
        "hyperscaler_capex_yoy": data["hyperscaler_capex_yoy"],
        "news": [{"title": n["title"], "site": n["site"]} for n in data["news"]],
        "portfolio": data["portfolio"],
    }

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system="You are an AI-equity market analyst producing a structured daily report model. "
               "You output strict JSON only. You never fabricate prices or percentages; "
               "you judge, score, and explain using the data provided.",
        messages=[{
            "role": "user",
            "content": f"DATA (today's snapshot):\n{json.dumps(compact)}\n\n{SCHEMA}"
        }],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text")
    model = json.loads(strip_json(raw))
    json.dump(model, open(OUT, "w"), indent=2)
    print(f"Wrote {OUT} (model: {MODEL})")


if __name__ == "__main__":
    main()
