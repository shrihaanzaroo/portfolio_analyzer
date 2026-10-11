import json
import os
import re
from urllib.parse import urlparse

import brokerage_csv

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "qwen/qwen3-32b"
PREFERRED_MODELS = ("qwen", "llama-4", "llama-3.3", "gpt-oss", "kimi", "llama", "deepseek", "mistral", "gemma")
NON_CHAT_WORDS = ("whisper", "tts", "guard", "embed", "audio", "speech", "orpheus", "playai", "moderation", "compound")
MAX_LINES = 300
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"}
NUMBER_RE = re.compile(r"\(?-?\$?\d[\d,]*(?:\.\d+)?\)?|\(?-?\$?\.\d+\)?")

SYSTEM_PROMPT = """You read brokerage holdings exports (CSV) and list every position in them as JSON.

Reply with ONLY a JSON object of this exact shape, no other text:
{"positions": [{"raw_symbol": str, "description": str, "kind": "stock"|"etf"|"mutual_fund"|"cash"|"no_ticker_fund"|"other", "ticker": str|null, "proxy_ticker": str|null, "quantity": number|null, "market_value": number|null, "note": str|null}], "notes": [str]}

Rules:
- One entry per data row. Do not merge rows and do not skip rows; skip only headers, blank lines and account totals.
- Copy quantity and market_value exactly as numbers from the file (drop commas and $). Numbers in parentheses are negative. Use null when the file has no such number. Never estimate or invent numbers.
- ticker: the Yahoo Finance ticker. Remove broker marks such as "@", "*" or trailing spaces (e.g. "NFLX@" -> "NFLX").
- kind "cash": cash, sweep, core position and money-market funds (SPAXX, FDRXX, FZFXX, FCASH, SWVXX, VMFXX, "Cash"...). They are worth $1 per unit.
- kind "no_ticker_fund": a fund with no public ticker, such as 401(k) collective trusts, 529 portfolios and plan-only index funds. Give the closest liquid proxy_ticker:
  US bond / aggregate bond index -> BND; developed ex-US / international index -> VEA; emerging markets -> VWO; US extended market / small-mid cap index -> VXF; S&P 500 or large-cap equity index -> VOO; total US stock market -> VTI; target-date or "Portfolio 20XX" -> the Vanguard Target Retirement fund for the nearest year (2025 VTTVX, 2030 VTHRX, 2035 VTTHX, 2040 VFORX, 2045 VTIVX, 2050 VFIFX, 2055 VFFVX, 2060 VTTSX, 2065 VLXVX); stable value -> treat as kind "cash".
- kind "other": options, CUSIP-only bonds, or anything you cannot identify. Explain in note.
- notes: short, plain-English remarks about anything unusual in the file (at most 4)."""

EXAMPLE_CSV = """Symbol,Description,Quantity
VOO*,VANGUARD S&P 500 ETF,"1,250.5"
SPAXX,FIDELITY GOVERNMENT MONEY MARKET,(42.10)
SS US BOND INDEX,,900"""

EXAMPLE_JSON = json.dumps({
    "positions": [
        {"raw_symbol": "VOO*", "description": "VANGUARD S&P 500 ETF", "kind": "etf", "ticker": "VOO", "proxy_ticker": None, "quantity": 1250.5, "market_value": None, "note": None},
        {"raw_symbol": "SPAXX", "description": "FIDELITY GOVERNMENT MONEY MARKET", "kind": "cash", "ticker": None, "proxy_ticker": None, "quantity": -42.10, "market_value": None, "note": None},
        {"raw_symbol": "SS US BOND INDEX", "description": "", "kind": "no_ticker_fund", "ticker": None, "proxy_ticker": "BND", "quantity": 900, "market_value": None, "note": "State Street US bond index trust; no public ticker."},
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


def _ask(text, cfg):
    import openai
    client = openai.OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"] or "none", timeout=90, max_retries=1)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": EXAMPLE_CSV},
        {"role": "assistant", "content": EXAMPLE_JSON},
        {"role": "user", "content": text},
    ]
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
    reply, model = _ask(text, cfg)
    positions = reply.get("positions") if isinstance(reply, dict) else None
    if not isinstance(positions, list):
        raise ValueError("The AI model didn't return a list of positions. Try again, or type your holdings in by hand.")

    numbers = _numbers_in(text)
    shares, values, needs_value = {}, {}, []
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
                needs_value.append({"label": label, "ticker": proxy, "units": qty, "value": val if (val or 0) > 0 else None, "why": note})
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
    if not shares and not value_only and not needs_value:
        raise ValueError("The AI model read the file but found no stock or fund positions in it.")

    notes = [str(n) for n in (reply.get("notes") or []) if isinstance(n, str) and n.strip()][:4]
    shares, value_only, trim_note = brokerage_csv.trim(shares, value_only, values, brokerage_csv.MAX_POSITIONS - len(needs_value))
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
        "needs_value": needs_value,
    }
