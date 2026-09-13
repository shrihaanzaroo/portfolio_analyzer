import csv
import io
import re

SYMBOL_HEADERS = {"symbol", "ticker", "ticker symbol", "instrument", "stock symbol", "security symbol", "symbol/cusip", "security"}
SHARES_HEADERS = {"quantity", "qty", "shares", "share quantity", "units", "quantity held", "number of shares"}
VALUE_HEADERS = {"current value", "market value", "value", "total value", "position value", "market value ($)", "current value ($)", "equity", "current market value"}
CODE_HEADERS = {"trans code", "transaction code", "action", "transaction type", "type of transaction"}
DESCRIPTION_HEADERS = {"description", "investment name", "name", "security description"}

CASH_WORDS = ("cash", "money market", "sweep", "pending activity", "settled", "core position", "fdic")
CASH_SYMBOLS = {"SPAXX", "FDRXX", "FZFXX", "FCASH", "FDLXX", "SWVXX", "SNVXX", "VMFXX", "VMRXX", "SPRXX", "QACDS"}
BUY_CODES = {"buy", "bought", "reinvest", "reinvestment", "byo"}
SELL_CODES = {"sell", "sold", "sto"}
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")
MAX_POSITIONS = 12


def _clean(cell):
    return (cell or "").strip().strip('"').strip()


def _norm(header):
    return _clean(header).lower().replace("﻿", "")


def _money(cell):
    s = _clean(cell).replace("$", "").replace(",", "").replace("%", "")
    if not s or s in {"--", "-", "n/a"}:
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("+", "")
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def _find(headers, wanted):
    for i, h in enumerate(headers):
        if h in wanted:
            return i
    return None


def _decode(data):
    if isinstance(data, bytes):
        for enc in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore")
    return data


def _rows(text):
    return list(csv.reader(io.StringIO(text)))


def _locate_header(rows):
    for i, row in enumerate(rows):
        headers = [_norm(c) for c in row]
        if _find(headers, SYMBOL_HEADERS) is not None and (_find(headers, SHARES_HEADERS) is not None or _find(headers, VALUE_HEADERS) is not None):
            return i, headers
    return None, None


def _symbol(cell):
    s = _clean(cell).upper()
    s = s.rstrip("*").strip()
    return s


def _is_cash(symbol, description):
    text = f"{symbol} {description}".lower()
    if symbol in CASH_SYMBOLS or symbol.endswith("XX") and "money" in text:
        return True
    return any(word in text for word in CASH_WORDS)


def parse(data):
    text = _decode(data)
    rows = _rows(text)
    header_index, headers = _locate_header(rows)
    if header_index is None:
        raise ValueError("Couldn't find a column for the ticker symbol plus one for shares or value. Export the Positions/Holdings page from your brokerage as a CSV and try again.")

    sym_i = _find(headers, SYMBOL_HEADERS)
    qty_i = _find(headers, SHARES_HEADERS)
    val_i = _find(headers, VALUE_HEADERS)
    code_i = _find(headers, CODE_HEADERS)
    desc_i = _find(headers, DESCRIPTION_HEADERS)

    shares = {}
    values = {}
    cash = 0.0
    skipped = []
    source = "activity report" if code_i is not None and qty_i is not None else "positions export"

    for row in rows[header_index + 1:]:
        if not any(_clean(c) for c in row):
            if shares or values or cash:
                break
            continue
        if len(row) <= sym_i:
            continue
        symbol = _symbol(row[sym_i])
        description = _clean(row[desc_i]) if desc_i is not None and desc_i < len(row) else ""
        qty = _money(row[qty_i]) if qty_i is not None and qty_i < len(row) else None
        val = _money(row[val_i]) if val_i is not None and val_i < len(row) else None

        if _is_cash(symbol, description) or (not symbol and val):
            if val:
                cash += val
            continue
        if not symbol:
            continue
        if symbol.lower().startswith("account total") or symbol.lower() in {"total", "totals"}:
            continue
        if not TICKER_RE.match(symbol):
            skipped.append(symbol or description)
            continue

        if source == "activity report":
            code = _clean(row[code_i]).lower() if code_i < len(row) else ""
            if qty is None:
                continue
            if code in BUY_CODES:
                shares[symbol] = shares.get(symbol, 0.0) + qty
            elif code in SELL_CODES:
                shares[symbol] = shares.get(symbol, 0.0) - qty
            continue

        if qty:
            shares[symbol] = shares.get(symbol, 0.0) + qty
            if val:
                values[symbol] = values.get(symbol, 0.0) + val
        elif val:
            values[symbol] = values.get(symbol, 0.0) + val

    shares = {t: round(q, 4) for t, q in shares.items() if q > 0}
    value_only = {t: v for t, v in values.items() if t not in shares and v > 0}
    notes = []

    if not shares and not value_only:
        raise ValueError("The file was read, but no stock or fund positions were found in it.")

    positions = len(shares) + len(value_only)
    if positions > MAX_POSITIONS:
        ranked = sorted(list(shares) + list(value_only), key=lambda t: -(values.get(t) or 0))
        keep = set(ranked[:MAX_POSITIONS])
        dropped = [t for t in ranked if t not in keep]
        shares = {t: q for t, q in shares.items() if t in keep}
        value_only = {t: v for t, v in value_only.items() if t in keep}
        notes.append(f"Kept your {MAX_POSITIONS} largest positions and left out {len(dropped)} smaller ones ({', '.join(dropped[:6])}{'…' if len(dropped) > 6 else ''}).")
    if skipped:
        notes.append(f"Skipped {len(skipped)} line(s) that aren't stocks or funds (options, CUSIPs, or totals): {', '.join(skipped[:5])}{'…' if len(skipped) > 5 else ''}.")
    if cash:
        notes.append(f"Found ${cash:,.0f} of cash and money-market funds — put it in the Cash box.")
    if value_only:
        notes.append(f"{', '.join(value_only)}: the file had dollar values but no share counts, so shares were worked out from today's price.")

    return {"shares": shares, "value_only": value_only, "cash": round(cash, 2), "notes": notes, "source": source}
