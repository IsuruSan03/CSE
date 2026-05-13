"""
CSE Market Data Proxy v4.0
-----------------------------------------------------------
Install:
    pip install flask flask-cors requests

Run:
    python proxy.py

Server:
    http://localhost:5000

Features:
    • /api/bulkScan
    • /api/historicalData?symbol=LOLC.N0000&period=3M
    • /api/graphData (alias)
    • /api/companyInfoSummery
    • /api/tradeSummary
    • /api/dailyMarketSummery
    • /api/todaySharePrice
    • /api/approvedAnnouncement
    • /api/allSymbols

New:
    • Retry support
    • Better error handling
    • Session pooling
    • Health check endpoint
    • Cleaner historical data normalization
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# FLASK
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

CSE_BASE = "https://www.cse.lk/api"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.cse.lk",
    "Referer": "https://www.cse.lk/",
    "Content-Type": "application/x-www-form-urlencoded",
}

# ─────────────────────────────────────────────────────────────
# SESSION + RETRY
# ─────────────────────────────────────────────────────────────

session = requests.Session()

retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST"]
)

adapter = HTTPAdapter(max_retries=retry_strategy)

session.mount("http://", adapter)
session.mount("https://", adapter)

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _f(value):
    """
    Safe float converter
    """
    try:
        if value is None or value == "":
            return 0.0
        return float(str(value).replace(",", ""))
    except:
        return 0.0


def cse_post(endpoint, data=None):
    """
    POST request helper
    """
    url = f"{CSE_BASE}/{endpoint}"

    response = session.post(
        url,
        data=data or {},
        headers=HEADERS,
        timeout=25
    )

    if response.status_code != 200:
        raise Exception(
            f"CSE HTTP {response.status_code}: "
            f"{response.text[:200]}"
        )

    try:
        return response.json()
    except Exception:
        raise Exception(
            f"Non-JSON response: {response.text[:200]}"
        )


def success(data):
    return jsonify({
        "success": True,
        "timestamp": datetime.now().isoformat(),
        **data
    })


def error_response(message, code=500):
    return jsonify({
        "success": False,
        "error": str(message),
        "timestamp": datetime.now().isoformat()
    }), code


# ─────────────────────────────────────────────────────────────
# ROOT
# ─────────────────────────────────────────────────────────────

@app.route("/")
def root():
    return success({
        "name": "CSE Proxy API",
        "version": "4.0",
        "status": "running"
    })


# ─────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return success({
        "status": "healthy"
    })


# ─────────────────────────────────────────────────────────────
# BULK SCAN
# ─────────────────────────────────────────────────────────────

@app.route("/api/bulkScan")
def bulk_scan():
    try:
        raw = cse_post("tradeSummary")

        rows = raw.get("reqTradeSummery") or []

        result = []

        for row in rows:

            symbol = row.get("symbol")

            if not symbol:
                continue

            result.append({
                "symbol": symbol,
                "name": row.get("name", ""),

                "lastPrice":
                    _f(row.get("price")
                    or row.get("lastTradedPrice")),

                "open":
                    _f(row.get("open")),

                "high":
                    _f(row.get("high")),

                "low":
                    _f(row.get("low")),

                "close":
                    _f(row.get("closingPrice")
                    or row.get("previousClose")),

                "prevClose":
                    _f(row.get("previousClose")),

                "volume":
                    _f(row.get("sharevolume")
                    or row.get("crossingVolume")),

                "turnover":
                    _f(row.get("turnover")),

                "marketCap":
                    _f(row.get("marketCap")),

                "change":
                    _f(row.get("change")),

                "changePct":
                    _f(row.get("percentageChange")),
            })

        return success({
            "count": len(result),
            "data": result
        })

    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# HISTORICAL DATA
# ─────────────────────────────────────────────────────────────

@app.route("/api/historicalData")
@app.route("/api/graphData")
def historical_data():

    symbol = request.args.get("symbol", "").strip()
    period = request.args.get("period", "3M").strip()

    if not symbol:
        return error_response("symbol required", 400)

    try:

        raw = cse_post("graphData", {
            "symbol": symbol,
            "period": period
        })

        # Normalize possible response formats
        if isinstance(raw, list):
            arr = raw

        elif isinstance(raw, dict):
            arr = (
                raw.get("graphData")
                or raw.get("reqData")
                or raw.get("data")
                or raw.get("candles")
                or []
            )

            if arr and isinstance(arr[0], list):
                arr = arr[0]

        else:
            arr = []

        candles = []

        for item in arr:

            # DICT FORMAT
            if isinstance(item, dict):

                candle = {
                    "date":
                        item.get("date")
                        or item.get("tradeDate")
                        or item.get("d")
                        or "",

                    "open":
                        _f(item.get("open")
                        or item.get("o")),

                    "high":
                        _f(item.get("high")
                        or item.get("h")),

                    "low":
                        _f(item.get("low")
                        or item.get("l")),

                    "close":
                        _f(item.get("close")
                        or item.get("c")
                        or item.get("lastTradedPrice")
                        or item.get("price")),

                    "volume":
                        _f(item.get("volume")
                        or item.get("sharevolume")
                        or item.get("v")
                        or item.get("crossingVolume")),
                }

                if candle["close"] > 0:
                    candles.append(candle)

            # ARRAY FORMAT
            elif isinstance(item, list) and len(item) >= 5:

                candles.append({
                    "date": item[0],
                    "open": _f(item[1]),
                    "high": _f(item[2]),
                    "low": _f(item[3]),
                    "close": _f(item[4]),
                    "volume": _f(item[5]) if len(item) > 5 else 0,
                })

        # SORT OLDEST FIRST
        candles.sort(key=lambda x: str(x["date"]))

        return success({
            "symbol": symbol,
            "period": period,
            "count": len(candles),
            "candles": candles
        })

    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────

@app.route("/api/dailyMarketSummery")
def daily_market_summary():
    try:
        raw = cse_post("dailyMarketSummery")
        if isinstance(raw, list):
            return jsonify({
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "reqData": raw
            })
        return success(raw)
    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# TODAY SHARE PRICE
# ─────────────────────────────────────────────────────────────

@app.route("/api/todaySharePrice")
def today_share_price():
    try:
        return success(cse_post("todaySharePrice"))
    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# COMPANY INFO
# ─────────────────────────────────────────────────────────────

@app.route("/api/companyInfoSummery")
def company_info():

    symbol = request.args.get("symbol", "").strip()

    if not symbol:
        return error_response("symbol required", 400)

    try:

        raw = cse_post("companyInfoSummery", {
            "symbol": symbol
        })

        info = raw.get("reqSymbolInfo") or {}

        return success({
            "symbol":
                info.get("symbol", symbol),

            "name":
                info.get("name", ""),

            "lastTradedPrice":
                _f(info.get("lastTradedPrice")),

            "change":
                _f(info.get("change")),

            "changePercentage":
                _f(info.get("changePercentage")),

            "high":
                _f(info.get("hiTrade")),

            "low":
                _f(info.get("lowTrade")),

            "open":
                _f(info.get("open")),

            "volume":
                _f(info.get("tdyShareVolume")),

            "turnover":
                _f(info.get("tdyTurnover")),

            "marketCap":
                _f(info.get("marketCap")),

            "previousClose":
                _f(info.get("previousClose")),

            "52WeekHigh":
                _f(info.get("p12HiPrice")),

            "52WeekLow":
                _f(info.get("p12LowPrice")),

            "allTimeHigh":
                _f(info.get("allHiPrice")),

            "allTimeLow":
                _f(info.get("allLowPrice")),

            "isin":
                info.get("isin", "")
        })

    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# ANNOUNCEMENTS
# ─────────────────────────────────────────────────────────────

@app.route("/api/approvedAnnouncement")
def announcements():
    try:
        return success(cse_post("approvedAnnouncement"))
    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# TRADE SUMMARY
# ─────────────────────────────────────────────────────────────

@app.route("/api/tradeSummary")
def trade_summary():

    symbol = request.args.get("symbol", "").strip()

    try:

        if symbol:
            raw = cse_post("tradeSummary", {
                "symbol": symbol
            })
        else:
            raw = cse_post("tradeSummary")

        return success(raw)

    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# ALL SYMBOLS
# ─────────────────────────────────────────────────────────────

@app.route("/api/allSymbols")
def all_symbols():

    try:

        raw = cse_post("tradeSummary")

        arr = raw.get("reqTradeSummery") or []

        symbols = []

        for row in arr:

            symbol = row.get("symbol")

            if symbol:
                symbols.append({
                    "symbol": symbol,
                    "name": row.get("name", "")
                })

        symbols.sort(key=lambda x: x["symbol"])

        return success({
            "count": len(symbols),
            "symbols": symbols
        })

    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# TOP GAINERS
# ─────────────────────────────────────────────────────────────

@app.route("/api/topGainers")
def top_gainers():

    try:

        raw = cse_post("tradeSummary")

        arr = raw.get("reqTradeSummery") or []

        cleaned = []

        for row in arr:

            symbol = row.get("symbol")

            if not symbol:
                continue

            cleaned.append({
                "symbol": symbol,
                "name": row.get("name", ""),
                "price": _f(row.get("price")),
                "changePct": _f(row.get("percentageChange"))
            })

        cleaned.sort(
            key=lambda x: x["changePct"],
            reverse=True
        )

        return success({
            "count": 20,
            "data": cleaned[:20]
        })

    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# TOP LOSERS
# ─────────────────────────────────────────────────────────────

@app.route("/api/topLosers")
def top_losers():

    try:

        raw = cse_post("tradeSummary")

        arr = raw.get("reqTradeSummery") or []

        cleaned = []

        for row in arr:

            symbol = row.get("symbol")

            if not symbol:
                continue

            cleaned.append({
                "symbol": symbol,
                "name": row.get("name", ""),
                "price": _f(row.get("price")),
                "changePct": _f(row.get("percentageChange"))
            })

        cleaned.sort(
            key=lambda x: x["changePct"]
        )

        return success({
            "count": 20,
            "data": cleaned[:20]
        })

    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# SEARCH SYMBOLS
# ─────────────────────────────────────────────────────────────

@app.route("/api/search")
def search():

    query = request.args.get("q", "").lower().strip()

    if not query:
        return error_response("q parameter required", 400)

    try:

        raw = cse_post("tradeSummary")

        arr = raw.get("reqTradeSummery") or []

        results = []

        for row in arr:

            symbol = row.get("symbol", "")
            name = row.get("name", "")

            if (
                query in symbol.lower()
                or query in name.lower()
            ):
                results.append({
                    "symbol": symbol,
                    "name": name
                })

        return success({
            "count": len(results),
            "results": results[:50]
        })

    except Exception as e:
        return error_response(e)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("=" * 60)
    print("   CSE MARKET DATA PROXY v4.0")
    print("=" * 60)
    print("   Server : http://localhost:5000")
    print("   Health : http://localhost:5000/api/health")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
