"""
fetch_data.py — pull the quantitative backbone of the AiPulse report from
Financial Modeling Prep (FMP). Numbers come from here (deterministic);
narrative/scoring is added later by generate.py via Claude.

Env:
  FMP_API_KEY   required

Output:
  data/data.json  — the day's raw quantitative snapshot
"""
import os, json, time, datetime, sys, urllib.parse
import urllib.request

FMP_KEY = os.environ.get("FMP_API_KEY", "").strip()
BASE = "https://financialmodelingprep.com"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")


def _get(path, params=None):
    params = dict(params or {})
    params["apikey"] = FMP_KEY
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt == 2:
                print(f"  ! {path} failed: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))


def quote(tickers):
    """Batch quote. Returns {ticker: {...}}."""
    if not tickers:
        return {}
    syms = ",".join(tickers)
    rows = _get(f"/api/v3/quote/{syms}") or []
    return {r["symbol"]: r for r in rows if "symbol" in r}


def sma50(ticker):
    rows = _get(f"/api/v3/technical_indicator/1day/{ticker}",
                {"type": "sma", "period": 50}) or []
    return rows[0].get("sma") if rows else None


def week_ago_close(ticker):
    rows = _get(f"/api/v3/historical-price-full/{ticker}",
                {"timeseries": 8}) or {}
    hist = rows.get("historical", []) if isinstance(rows, dict) else []
    return hist[-1]["close"] if hist else None


def ratios(ticker):
    rows = _get(f"/api/v3/ratios-ttm/{ticker}") or []
    return rows[0] if rows else {}


def stock_block(tickers):
    q = quote(tickers)
    out = {}
    for t in tickers:
        d = q.get(t, {})
        price = d.get("price")
        wk = week_ago_close(t)
        s50 = d.get("priceAvg50") or sma50(t)
        chg_1w = ((price - wk) / wk * 100) if (price and wk) else None
        out[t] = {
            "price": price,
            "chg_1d": d.get("changesPercentage"),
            "chg_1w": chg_1w,
            "sma50": s50,
            "above_50d": (price > s50) if (price and s50) else None,
            "pe": d.get("pe"),
            "eps": d.get("eps"),
        }
        time.sleep(0.2)  # be polite to the API
    return out


def index_block(indices):
    q = quote([i["ticker"] for i in indices])
    out = []
    for i in indices:
        t = i["ticker"]
        d = q.get(t, {})
        price = d.get("price")
        wk = week_ago_close(t)
        out.append({
            "ticker": t, "name": i["name"],
            "chg_1d": d.get("changesPercentage"),
            "chg_1w": ((price - wk) / wk * 100) if (price and wk) else None,
        })
        time.sleep(0.2)
    return out


def hyperscaler_capex_yoy(tickers):
    """Crude YoY capex growth from the latest two annual cash-flow statements,
    summed across the named hyperscalers."""
    cur = prev = 0.0
    ok = False
    for t in tickers:
        rows = _get(f"/api/v3/cash-flow-statement/{t}",
                    {"period": "annual", "limit": 2}) or []
        if len(rows) >= 2:
            c = abs(rows[0].get("capitalExpenditure") or 0)
            p = abs(rows[1].get("capitalExpenditure") or 0)
            if c and p:
                cur += c; prev += p; ok = True
        time.sleep(0.2)
    return round((cur - prev) / prev * 100, 1) if (ok and prev) else None


def news(tickers, limit=12):
    syms = ",".join(tickers)
    rows = _get("/api/v3/stock_news", {"tickers": syms, "limit": limit}) or []
    return [{"title": r.get("title"), "site": r.get("site"),
             "url": r.get("url"), "date": r.get("publishedDate")}
            for r in rows]


def main():
    if not FMP_KEY:
        print("ERROR: FMP_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    cfg_dir = os.path.join(os.path.dirname(__file__), "..", "config")
    uni = json.load(open(os.path.join(cfg_dir, "universe.json")))
    pf = json.load(open(os.path.join(cfg_dir, "portfolio.json")))

    pf_tickers = [p["ticker"] for p in pf["positions"]]
    chain_tickers = sorted({t for L in uni["value_chain"] for t in L["tickers"]})
    all_stock = sorted(set(uni["stocks"]) | set(pf_tickers) | set(chain_tickers))

    print(f"Fetching {len(all_stock)} stocks, {len(uni['indices'])} indices ...")
    stocks = stock_block(all_stock)
    indices = index_block(uni["indices"])
    capex = hyperscaler_capex_yoy(uni["hyperscalers"])
    headlines = news(uni["stocks"][:6])

    data = {
        "as_of": datetime.datetime.utcnow().isoformat() + "Z",
        "stocks": stocks,
        "indices": indices,
        "value_chain": uni["value_chain"],
        "hyperscaler_capex_yoy": capex,
        "news": headlines,
        "portfolio": pf["positions"],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w"), indent=2)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
