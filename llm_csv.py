import json
import os
import re
from urllib.parse import urlparse

import brokerage_csv
import reference_data as ref

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "qwen/qwen3-32b"
PREFERRED_MODELS = ("qwen", "llama-4", "llama-3.3", "gpt-oss", "kimi", "llama", "deepseek", "mistral", "gemma")
NON_CHAT_WORDS = ("whisper", "tts", "guard", "embed", "audio", "speech", "orpheus", "playai", "moderation", "compound")
MAX_LINES = 300
MIN_UNIT_PRICE, MAX_UNIT_PRICE = 0.5, 5000
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"}
NUMBER_RE = re.compile(r"\(?-?\$?\d[\d,]*(?:\.\d+)?\)?|\(?-?\$?\.\d+\)?")

PROXY_GUIDE = 'US bond / aggregate bond index -> BND; developed ex-US / international index -> VEA; emerging markets -> VWO; US extended market / small-mid cap index -> VXF; S&P 500 or large-cap equity index -> VOO; total US stock market -> VTI; target-date or "Portfolio 20XX" -> the Vanguard Target Retirement fund for the nearest year (2025 VTTVX, 2030 VTHRX, 2035 VTTHX, 2040 VFORX, 2045 VTIVX, 2050 VFIFX, 2055 VFFVX, 2060 VTTSX, 2065 VLXVX).'

SYSTEM_PROMPT = """You read brokerage holdings exports (CSV) and list every position in them as JSON.

Reply with ONLY a JSON object of this exact shape, no other text:
{"positions": [{"raw_symbol": str, "description": str, "kind": "stock"|"etf"|"mutual_fund"|"cash"|"no_ticker_fund"|"other", "ticker": str|null, "proxy_ticker": str|null, "quantity": number|null, "market_value": number|null, "unit_price": number|null, "note": str|null}], "notes": [str]}

Rules:
- One entry per data row. Do not merge rows and do not skip rows; skip only headers, blank lines and account totals.
- Copy quantity and market_value exactly as numbers from the file (drop commas and $). Numbers in parentheses are negative. Use null when the file has no such number. Never estimate or invent numbers.
- ticker: the Yahoo Finance ticker. Remove broker marks such as "@", "*" or trailing spaces (e.g. "NFLX@" -> "NFLX").
- kind "cash": cash, sweep, core position and money-market funds (SPAXX, FDRXX, FZFXX, FCASH, SWVXX, VMFXX, "Cash"...). They are worth $1 per unit.
- kind "no_ticker_fund": a fund with no public ticker, such as 401(k) collective trusts, 529 portfolios and plan-only index funds. Give the closest liquid proxy_ticker:
  """ + PROXY_GUIDE + """ Stable value -> treat as kind "cash".
  Also give unit_price: your best estimate of that fund's current price per unit in US dollars, from what you know about the fund or its share classes (null for other kinds, or if you truly can't tell). Plan trust and 529 units are often priced well away from the proxy's share price.
- kind "other": options, CUSIP-only bonds, or anything you cannot identify. Explain in note.
- notes: short, plain-English remarks about anything unusual in the file (at most 4)."""

ESTIMATE_PROMPT = """These holdings have no price data on Yahoo Finance (often plan-only, closed or renamed funds). For each one, pick the closest liquid public stand-in that Yahoo Finance does price, and estimate its current price per unit.

Reply with ONLY a JSON object of this exact shape, no other text:
{"funds": [{"symbol": str, "proxy_ticker": str, "unit_price": number|null, "why": str}]}

- proxy_ticker: a different, widely traded ETF or mutual fund ticker with the same kind of holdings. For a single stock that was renamed or merged, use its current ticker.
- unit_price: your best estimate of the original holding's current price per unit in US dollars, or null if you truly can't tell.
- why: one short line naming what the holding is.
- Common stand-ins: """ + PROXY_GUIDE + """
"""

CLASSIFY_PROMPT = """Yahoo Finance doesn't list an industry sector for these stock tickers. For each one, give the company's sector and the country where it is headquartered.

Reply with ONLY a JSON object of this exact shape, no other text:
{"stocks": [{"ticker": str, "sector": str|null, "country": str|null}]}

- sector: exactly one of: """ + ", ".join(ref.EQUITY_SECTORS) + """.
- country: the country's common English name, such as "United States", "Taiwan" or "Netherlands".
- Use null for a ticker you don't recognize, or one that is a fund or ETF rather than a single company. Never guess.
"""
PLAIN_COUNTRY = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,39}$")

EXAMPLE_CSV = """Symbol,Description,Quantity
VOO*,VANGUARD S&P 500 ETF,"1,250.5"
SPAXX,FIDELITY GOVERNMENT MONEY MARKET,(42.10)
SS US BOND INDEX,,900"""

EXAMPLE_JSON = json.dumps({
    "positions": [
        {"raw_symbol": "VOO*", "description": "VANGUARD S&P 500 ETF", "kind": "etf", "ticker": "VOO", "proxy_ticker": None, "quantity": 1250.5, "market_value": None, "unit_price": None, "note": None},
        {"raw_symbol": "SPAXX", "description": "FIDELITY GOVERNMENT MONEY MARKET", "kind": "cash", "ticker": None, "proxy_ticker": None, "quantity": -42.10, "market_value": None, "unit_price": None, "note": None},
        {"raw_symbol": "SS US BOND INDEX", "description": "", "kind": "no_ticker_fund", "ticker": None, "proxy_ticker": "BND", "quantity": 900, "market_value": None, "unit_price": 14.2, "note": "State Street US bond index trust; no public ticker."},
    ],
    "notes": ["The file has share counts but no dollar values."],
})


def _setting(name, default=None):
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name) or default


def config():
    return {
        "base_url": _setting("LLM_BASE_URL", DEFAULT_BASE_URL),
        "api_key": _setting("LLM_API_KEY"),
        "model": _setting("LLM_MODEL", DEFAULT_MODEL),
    }


def host(cfg=None):
    return urlparse((cfg or config())["base_url"]).hostname or ""


def is_local(cfg=None):
    return host(cfg) in LOCAL_HOSTS


def available():
    cfg = config()
    return bool(cfg["api_key"]) or is_local(cfg)


def _complete(client, model, messages):
    import openai
    try:
        response = client.chat.completions.create(model=model, temperature=0, messages=messages, response_format={"type": "json_object"})
    except openai.BadRequestError:
        response = client.chat.completions.create(model=model, temperature=0, messages=messages)
    return response.choices[0].message.content or ""


def _extract_json(content):
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("no JSON object in reply", content, 0)
    return json.loads(content[start:end + 1])


def _chat_models(client):
    try:
        ids = [m.id for m in client.models.list()]
    except Exception:
        return []
    return sorted(i for i in ids if not any(word in i.lower() for word in NON_CHAT_WORDS))


def _best_model(offered, avoid=()):
    usable = [m for m in offered if m not in avoid]
    for wanted in PREFERRED_MODELS:
        for m in usable:
            if wanted in m.lower():
                return m
    return usable[0] if usable else None


def _ask(messages, cfg):
    import openai
    client = openai.OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"] or "none", timeout=90, max_retries=1)
    model = cfg["model"]
    try:
        try:
            content = _complete(client, model, messages)
        except openai.NotFoundError:
            offered = _chat_models(client)
            replacement = _best_model(offered, avoid={model})
            if not replacement:
                raise ValueError(f"The AI service doesn't have the model '{model}'" + (f". It offers: {', '.join(offered[:8])}. Set LLM_MODEL to one of them." if offered else ". Set LLM_MODEL to one it offers."))
            model = replacement
            content = _complete(client, model, messages)
        try:
            return _extract_json(content), model
        except json.JSONDecodeError as e:
            retry = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That was not valid JSON ({e.msg}). Reply with only the JSON object."},
            ]
            try:
                return _extract_json(_complete(client, model, retry)), model
            except json.JSONDecodeError:
                raise ValueError("The AI model's answer couldn't be read. Try again, or type your holdings in by hand.")
    except openai.APIConnectionError:
        raise ValueError(f"Couldn't reach the AI model at {host(cfg)}. Check LLM_BASE_URL (and that Ollama is running, if you use it locally).")
    except openai.AuthenticationError:
        raise ValueError("The AI service rejected the key. Check LLM_API_KEY in the app's secrets.")
    except openai.RateLimitError:
        raise ValueError("The AI service is busy (rate limit). Wait a minute and try again.")
    except openai.NotFoundError:
        raise ValueError(f"The AI service doesn't have the model '{model}'. Set LLM_MODEL to one it offers.")
    except openai.APIStatusError as e:
        raise ValueError(f"The AI service returned an error ({e.status_code}). Try again in a moment.")


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return brokerage_csv._money(str(value))


def _ticker(value):
    t = str(value or "").strip().upper().rstrip("*@").strip()
    return t if brokerage_csv.TICKER_RE.match(t) else None


def _numbers_in(text):
    found = set()
    for token in NUMBER_RE.findall(text):
        value = brokerage_csv._money(token)
        if value is not None:
            found.add(round(abs(value), 2))
    return found


def _in_file(value, numbers):
    return value is None or round(abs(value), 2) in numbers


def _list(items, limit=5):
    return f"{', '.join(items[:limit])}{'…' if len(items) > limit else ''}"


def parse(data):
    text = brokerage_csv._decode(data)
    lines = [line for line in text.splitlines() if line.strip()]
    truncated = len(lines) > MAX_LINES
    text = "\n".join(lines[:MAX_LINES])
    if not text:
        raise ValueError("The file is empty.")

    cfg = config()
    reply, model = _ask([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": EXAMPLE_CSV},
        {"role": "assistant", "content": EXAMPLE_JSON},
        {"role": "user", "content": text},
    ], cfg)
    positions = reply.get("positions") if isinstance(reply, dict) else None
    if not isinstance(positions, list):
        raise ValueError("The AI model didn't return a list of positions. Try again, or type your holdings in by hand.")

    numbers = _numbers_in(text)
    shares, values, estimated_funds = {}, {}, []
    cash = 0.0
    skipped, unverified, row_notes = [], [], []

    for p in positions:
        if not isinstance(p, dict):
            continue
        kind = str(p.get("kind") or "").strip().lower()
        label = str(p.get("raw_symbol") or p.get("description") or "?").strip()
        qty, val = _num(p.get("quantity")), _num(p.get("market_value"))
        if not _in_file(qty, numbers) or not _in_file(val, numbers):
            unverified.append(label)
            continue
        if kind == "cash":
            cash += val if val is not None else (qty or 0.0)
            continue

        ticker, proxy = _ticker(p.get("ticker")), _ticker(p.get("proxy_ticker"))
        note = str(p.get("note") or "").strip()
        if kind == "no_ticker_fund" or (not ticker and proxy):
            if proxy and ((qty or 0) > 0 or (val or 0) > 0):
                unit_price = _num(p.get("unit_price"))
                estimated_funds.append({
                    "label": label, "ticker": proxy, "units": qty, "why": note,
                    "value": val if (val or 0) > 0 else None,
                    "unit_price": unit_price if unit_price and MIN_UNIT_PRICE <= unit_price <= MAX_UNIT_PRICE else None,
                })
            else:
                skipped.append(label)
            continue
        if kind == "other" or not ticker:
            skipped.append(label)
            continue

        if qty:
            shares[ticker] = shares.get(ticker, 0.0) + qty
            if val:
                values[ticker] = values.get(ticker, 0.0) + val
        elif val:
            values[ticker] = values.get(ticker, 0.0) + val
        if note:
            row_notes.append(f"{label}: {note}")

    shares = {t: round(q, 4) for t, q in shares.items() if q > 0}
    value_only = {t: v for t, v in values.items() if t not in shares and v > 0}
    if not shares and not value_only and not estimated_funds:
        raise ValueError("The AI model read the file but found no stock or fund positions in it.")

    notes = [str(n) for n in (reply.get("notes") or []) if isinstance(n, str) and n.strip()][:4]
    shares, value_only, trim_note = brokerage_csv.trim(shares, value_only, values, brokerage_csv.MAX_POSITIONS - len(estimated_funds))
    if trim_note:
        notes.append(trim_note)
    if model != cfg["model"]:
        notes.append(f"Read with the AI model {model}, because the service doesn't offer {cfg['model']}.")
    if truncated:
        notes.append(f"The file was long, so only its first {MAX_LINES} lines were read.")
    if unverified:
        notes.append(f"Left out {len(unverified)} line(s) whose numbers the AI got wrong (they don't appear in the file): {_list(unverified)}. Add them by hand.")
    if skipped:
        notes.append(f"Skipped {len(skipped)} line(s) that couldn't be matched to a stock or fund: {_list(skipped)}.")
    if cash > 0:
        notes.append(f"Found ${cash:,.0f} of cash and money-market funds — put it in the Cash box.")
    if value_only:
        notes.append(f"{', '.join(value_only)}: the file had dollar values but no share counts, so shares were worked out from today's price.")
    notes.extend(row_notes[:3])

    return {
        "shares": shares,
        "value_only": value_only,
        "cash": round(max(cash, 0.0), 2),
        "notes": notes,
        "source": f"AI ({model})",
        "skipped": skipped,
        "estimated_funds": estimated_funds,
    }


def estimate_funds(items):
    lines = "\n".join(f"{item['label']}: {item['units']:,.4f} units" for item in items)
    reply, _ = _ask([
        {"role": "system", "content": ESTIMATE_PROMPT},
        {"role": "user", "content": lines},
    ], config())
    rows = reply.get("funds") if isinstance(reply, dict) else None
    by_symbol = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            by_symbol[str(row.get("symbol") or "").strip().upper()] = row
    estimates = []
    for item in items:
        row = by_symbol.get(item["label"].upper())
        proxy = _ticker(row.get("proxy_ticker")) if row else None
        if not proxy or proxy == item["label"].upper():
            continue
        unit_price = _num(row.get("unit_price"))
        estimates.append({
            "label": item["label"], "ticker": proxy, "units": item["units"], "value": None,
            "unit_price": unit_price if unit_price and MIN_UNIT_PRICE <= unit_price <= MAX_UNIT_PRICE else None,
            "why": str(row.get("why") or "").strip(),
        })
    return estimates


def _country(value):
    country = str(value or "").strip()
    return country if PLAIN_COUNTRY.match(country) and len(country.split()) <= 4 else None


def classify_stocks(tickers):
    """{ticker: {"sector": one of ref.EQUITY_SECTORS, "country": str or None}} for the tickers the AI could place."""
    wanted = {str(t).strip().upper() for t in tickers if str(t).strip()}
    if not wanted:
        return {}
    reply, _ = _ask([
        {"role": "system", "content": CLASSIFY_PROMPT},
        {"role": "user", "content": "\n".join(sorted(wanted))},
    ], config())
    rows = reply.get("stocks") if isinstance(reply, dict) else None
    sectors = {s.lower(): s for s in ref.EQUITY_SECTORS}
    found = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        sector = sectors.get(str(row.get("sector") or "").strip().lower())
        if ticker in wanted and sector:
            found[ticker] = {"sector": sector, "country": _country(row.get("country"))}
    return found
