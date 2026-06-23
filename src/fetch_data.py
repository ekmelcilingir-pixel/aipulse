"""
fetch_data.py — pull the quantitative backbone of the AiPulse report from
Financial Modeling Prep (FMP) using the current /stable/ API.

Numbers come from here (deterministic); narrative/scoring is added later by
generate.py via Claude.

Env:
  FMP_API_KEY   required

Output:
  data/data.json  — the day's raw quantitative snapshot
"""
import os, json, time, datetime, sys, urllib.parse, urllib.request

FMP_KEY = os.environ.get("FMP_API_KEY", "").strip()
BASE = "https://financialmodelingprep.com/stable"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")


def _get(path, params=None):
    params = dict(params or {})
    params["apikey"] = FMP_KEY
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, dict) and ("Error Message" in data or "error" in data):
                print(f"  ! {path}: {data}", file=sys.stderr)
                return None
            return data
        except Exception as e:
            if attempt == 2:
                print(f"  ! {path} failed: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))


def quote(ticker):
    rows = _get("quote", {"symbol": ticker})
    return rows[0] if isinstance(rows, list) and rows else {}


def week_ago_close(ticker):
    today = datetime.date.today()
    frm = today - datetime.timedelta(days=12)
    rows = _get("historical-price-eod/light",
                {"symbol": ticker, "from": frm.isoformat(), "to": today.isoformat()})
    if not isinstance(rows, list) or not rows:
        return None
    last = rows[-1]
    return last.get("close", last.get("price"))


def stock_block(tickers, with_week=True):
    out = {}
    for t in tickers:
        q = quote(t)
        price = q.get("price")
        s50 = q.get("priceAvg50")
        wk = week_ago_close(t) if with_week else None
        out[t] = {
            "price": price,
            "chg_1d": q.get("changePercentage"),
            "chg_1w": ((price - wk) / wk * 100) if (price and wk) else None,
            "sma50": s50,
            "above_50d": (price > s50) if (price and s50) else None,
            "pe": q.get("pe"),
            "eps": q.get("eps"),
        }
        time.sleep(0.18)
    return out


def index_block(indices):
    out = []
    for i in indices:
        t = i["ticker"]
        q = quote(t)
        price = q.get("price")
        wk = week_ago_close(t)
        out.append({
            "ticker": t, "name": i["name"],
            "chg_1d": q.get("changePercentage"),
            "chg_1w": ((price - wk) / wk * 100) if (price and wk) else None,
        })
        time.sleep(0.18)
    return out


def hyperscaler_capex_yoy(tickers):
    cur = prev = 0.0
    ok = False
    for t in tickers:
        rows = _get("cash-flow-statement", {"symbol": t, "period": "annual", "limit": 2})
        if isinstance(rows, list) and len(rows) >= 2:
            c = abs(rows[0].get("capitalExpenditure") or 0)
            p = abs(rows[1].get("capitalExpenditure") or 0)
            if c and p:
                cur += c; prev += p; ok = True
        time.sleep(0.18)
    return round((cur - prev) / prev * 100, 1) if (ok and prev) else None


def news(tickers, limit=12):
    rows = _get("news/stock", {"symbols": ",".join(tickers), "limit": limit})
    rows = rows if isinstance(rows, list) else []
    return [{"title": r.get("title"), "site": r.get("publisher") or r.get("site"),
             "url": r.get("url"), "date": r.get("publishedDate") or r.get("date")}
            for r in rows]


def main():
    if not FMP_KEY:
        print("ERROR: FMP_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    cfg = os.path.join(os.path.dirname(__file__), "..", "config")
    uni = json.load(open(os.path.join(cfg, "universe.json")))
    pf = json.load(open(os.path.join(cfg, "portfolio.json")))

    pf_tickers = [p["ticker"] for p in pf["positions"]]
    chain = sorted({t for L in uni["value_chain"] for t in L["tickers"]})
    week_set = set(uni["stocks"]) | set(pf_tickers)
    all_stock = sorted(set(uni["stocks"]) | set(pf_tickers) | set(chain))

    print(f"Fetching {len(all_stock)} stocks + {len(uni['indices'])} indices via /stable ...")
    stocks = {}
    for t in all_stock:
        stocks.update(stock_block([t], with_week=(t in week_set)))
    indices = index_block(uni["indices"])
    capex = hyperscaler_capex_yoy(uni["hyperscalers"])
    headlines = news(uni["stocks"][:6])

    got = sum(1 for v in stocks.values() if v.get("price"))
    print(f"  prices resolved: {got}/{len(stocks)} - capex_yoy: {capex} - news: {len(headlines)}")

    data = {
        "as_of": datetime.datetime.utcnow().isoformat() + "Z",
        "stocks": stocks, "indices": indices,
        "value_chain": uni["value_chain"],
        "hyperscaler_capex_yoy": capex, "news": headlines,
        "portfolio": pf["positions"],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w"), indent=2)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
