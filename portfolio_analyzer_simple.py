import re
from html import escape

import pandas as pd
import altair as alt
import streamlit as st
import brokerage_csv
import engine
import funds
import history
import llm_csv
import optimizer
import regions
import report
import style
import tips

st.set_page_config(page_title="Portfolio Check-Up", page_icon=":material/monitor_heart:", layout="wide", initial_sidebar_state="collapsed")


class IncompleteDownload(Exception):
    """Raised inside the cache so a download missing some tickers isn't kept; carries what did arrive."""

    def __init__(self, prices):
        super().__init__("some tickers came back without prices")
        self.prices = prices


@st.cache_data(ttl="6h", max_entries=100, show_spinner="Downloading price history...")
def _complete_download(tickers, period):
    prices = engine.download_prices(tickers, period)
    if any(t not in prices.columns or prices[t].dropna().empty for t in tickers):
        raise IncompleteDownload(prices)
    return prices


def cached_download(tickers, period):
    """Prices for every ticker that has them. Only complete downloads are cached, so a ticker Yahoo
    failed to send is asked for again next time; if the download fails outright, an empty table."""
    try:
        return _complete_download([tickers] if isinstance(tickers, str) else list(tickers), period)
    except IncompleteDownload as e:
        return e.prices
    except Exception:
        return pd.DataFrame()


LEVEL_MARK = {"high": ":red[Needs attention]", "medium": ":orange[Worth knowing]", "good": ":green[Working]"}
PERIOD = "max"
GRADE_YEARS = 3
GROWTH_WINDOWS = {"1 year": 1, "3 years": 3, "5 years": 5, "10 years": 10, "All history": None}
STEADY_WINDOWS = {"3 years": 3, "5 years": 5, "10 years": 10}
BENCHMARKS = {
    "S&P 500 (the 500 biggest US companies)": {"SPY": 1.0},
    "Nasdaq-100 (big tech)": {"QQQ": 1.0},
    "Whole US market (VTI — every US company, big and small)": {"VTI": 1.0},
    "Bonds (BND)": {"BND": 1.0},
    "60% stocks / 40% bonds": {"SPY": 0.6, "BND": 0.4},
    "Gold (GLD)": {"GLD": 1.0},
}
BENCHMARK_TICKERS = sorted({t for mix in BENCHMARKS.values() for t in mix})
DEFAULT_BENCHMARK = next(iter(BENCHMARKS))
CUSTOM_OPTION = "Another ticker…"
YOU_COLOR = style.BLUE
AFTER_COLOR = style.GREEN
BENCH_COLOR = style.GRAY
SLICE_COLORS = [style.BLUE, style.TEAL, style.AMBER, style.VIOLET, style.RED, style.GREEN, style.GRAY]
ASSET_COLORS = {"Stocks": style.BLUE, "Bonds": style.GREEN, "Gold": style.AMBER, "Cash": style.GRAY}
CASH_NOTE = "Cash is counted as earning nothing; the mix is kept at today's split."

METHOD = [
    ("Data.", "Daily closing prices from Yahoo Finance, adjusted for splits and dividends. The grade, the notes and the scenarios use the last 3 years; each chart says which dates it shows. When a chart reaches back before one of your holdings existed, that holding's share is spread across the others for that stretch, as long as the holdings that did exist make up at least half your money; the chart says so when it happens."),
    ("How spread out.", "Your money is converted to weights at today's prices. Concentration uses the Herfindahl index, a standard measure: square each weight and add them up; one divided by that total is the number of equal-sized holdings your mix behaves like."),
    ("Funds.", "ETFs and mutual funds are looked up on Yahoo Finance and looked inside: their largest holdings, industry split and stock/bond/cash split. The rest of a fund is spread across an estimated number of companies for its category (about 50 for an S&P 500 fund, 60 for a total-market fund), not its exact holdings list. If the lookup fails, a built-in table of common index funds is used."),
    ("Moving together.", "Correlation of daily returns between each pair of holdings — a standard statistic from -1 to 1. Holdings that barely move (such as cash-like funds) are left out. The \"same direction\" figure is the share of days two holdings both rose or both fell; two unrelated holdings land near half."),
    ("Real bets.", "This app's own estimate, not an industry standard: the equal-sized-holdings number divided by (1 + (that number - 1) x the average correlation). With no correlation it equals the number of holdings; as holdings move together it falls toward 1. Companies inside the same fund are assumed to move together with a correlation of 0.35, a typical long-run figure for large companies, because a fund's insides cannot be measured from its price."),
    ("The grade.", "An average of six checks, each scored 0 to 4: spread across companies, across industries, across countries, swings compared with the S&P 500, share of months that ended positive, and near-duplicate holdings. Being all in stocks is not marked down on its own; bonds and gold still help through the swings check. It is discounted when most of the money sits in cash. The cut-offs are judgment calls."),
    ("Scenarios.", "About 100 hypothetical swaps are tried: half or all of each of your five largest holdings, into each of ten common diversifying funds (bond, gold, broad-market, international and single-industry funds). Each new mix is re-graded the same way over the same 3 years, and the three that change the most are shown. A swap counts only if it raises the grade or adds at least half a real bet; when fewer than three do, the rest are smaller tweaks: half of one holding, the grade and real bets not lower, and the yearly swing, worst drop or real bets visibly better."),
    ("Tested on.", "Six large tech stocks grade C (about 2 real bets, one industry). An S&P 500 fund with bonds, gold and stocks from other industries grades A (just at the cut-off), and more firmly A once an international fund is added. A single stock is capped at D. A single total-market index fund grades B: many companies, but one country. Three overlapping U.S. stock funds grade B but count as about 1.3 real bets."),
    ("Limits.", "Everything here looks backward: it describes how this mix behaved, not how it will. Three years is a short sample, and holdings tend to move together more in a crash than in calm years. Country and fund breadth figures are approximate. Taxes, fees and trading costs are ignored. This is an educational tool, not financial advice."),
]


SHARE_CLASS = re.compile(r"^([A-Z]{1,4})\.([AB])$")


def normalize_ticker(raw):
    """Yahoo's spelling of a typed ticker ("BRK.B" -> "BRK-B"); None for a blank row."""
    try:
        if raw is None or pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    ticker = str(raw).strip().upper()
    if ticker in ("", "NAN", "NONE"):
        return None
    match = SHARE_CLASS.match(ticker)
    return f"{match[1]}-{match[2]}" if match else ticker


def df_tickers(df):
    return df["Ticker"].map(normalize_ticker)


def holdings_df_to_dict(df):
    holdings = {}
    for _, row in df.iterrows():
        ticker = normalize_ticker(row["Ticker"])
        shares = row["Shares"]
        if not ticker or pd.isna(shares) or shares <= 0:
            continue
        holdings[ticker] = holdings.get(ticker, 0) + float(shares)
    return {t: int(s) if s.is_integer() else round(s, 4) for t, s in holdings.items()}


def read_brokerage_file(data, use_ai):
    parsed, problem = None, None
    try:
        parsed = brokerage_csv.parse(data)
    except ValueError as e:
        problem = str(e)
    if llm_csv.available() and (use_ai or parsed is None or parsed["skipped"]):
        try:
            with st.spinner("Reading your file with AI..."):
                return llm_csv.parse(data), None
        except ValueError as e:
            problem = f"The AI reader didn't work: {e}" if parsed is None else f"The AI reader didn't work ({e}), so the standard reader was used."
    return parsed, problem


def add_estimated_funds(df, funds_list):
    latest = cached_download(sorted({f["ticker"] for f in funds_list}), "1mo")
    df = df.copy()
    added, missing = [], []
    for fund in funds_list:
        t = fund["ticker"]
        if t not in latest.columns or latest[t].dropna().empty:
            missing.append(fund["label"])
            continue
        price = float(latest[t].dropna().iloc[-1])
        units = fund.get("units") or 0
        if fund.get("value"):
            dollars, basis = fund["value"], "value from the file"
        elif units and fund.get("unit_price"):
            dollars, basis = units * fund["unit_price"], f"{units:,.0f} units × about ${fund['unit_price']:,.2f}"
        else:
            dollars, basis = units * price, f"{units:,.0f} units at {t}'s price"
        if dollars <= 0:
            missing.append(fund["label"])
            continue
        shares = round(dollars / price, 2)
        match = df["Ticker"].astype(str).str.strip().str.upper() == t
        if match.any():
            df.loc[match.idxmax(), "Shares"] = float(df.loc[match.idxmax(), "Shares"] or 0) + shares
        else:
            df = pd.concat([df, pd.DataFrame({"Ticker": [t], "Shares": [shares]})], ignore_index=True)
        added.append(f"{fund['label']} ≈ ${dollars:,.0f} ({basis}), counted as {t}")
    notes = []
    if added:
        notes.append("Estimated and added as a similar public fund (these have no ticker, or no price data on Yahoo Finance): " + "; ".join(added) + ". These are estimates — if your statement shows different values, change their shares in the table.")
    if missing:
        notes.append(f"Couldn't estimate {', '.join(missing)}, so they were left out.")
    return df, notes


def replace_unpriced(df, holdings, missing):
    keep = ~df_tickers(df).isin(missing)
    df = df[keep].reset_index(drop=True)
    notes = []
    if llm_csv.available():
        try:
            with st.spinner(f"Finding stand-ins for {', '.join(missing)}..."):
                estimates = llm_csv.estimate_funds([{"label": t, "units": holdings[t]} for t in missing])
            df, notes = add_estimated_funds(df, estimates)
        except ValueError as e:
            notes = [f"The AI couldn't suggest stand-ins ({e})."]
    holdings = holdings_df_to_dict(df)
    prices, unconverted = analysis_prices(list(holdings)) if holdings else (None, {})
    recent = history.window(prices, GRADE_YEARS) if holdings else None
    still = [t for t in holdings if t not in unconverted and (t not in prices.columns or recent[t].dropna().empty)]
    if still:
        df = df[~df_tickers(df).isin(still)].reset_index(drop=True)
        holdings = holdings_df_to_dict(df)
    left_out = sorted(set(still) | {t for t in missing if not any(t in n for n in notes)})
    if left_out:
        notes.append(f"Left out {', '.join(left_out)}: Yahoo Finance has no recent price data for {'it' if len(left_out) == 1 else 'them'}.")
    return df, holdings, notes


def holdings_to_weights(holdings, prices):
    values = {t: float(prices[t].dropna().iloc[-1]) * shares for t, shares in holdings.items()}
    total = sum(values.values())
    return {t: v / total for t, v in values.items()}, total


def download_list(tickers):
    return list(dict.fromkeys(sorted(tickers) + ["SPY"] + BENCHMARK_TICKERS + list(optimizer.CANDIDATES)))


def analysis_prices(tickers):
    """Full price history for the holdings plus comparison funds, in US dollars and on US trading days.
    Returns (prices, {ticker: currency} for holdings that couldn't be converted; those are left out of prices)."""
    prices = cached_download(download_list(tickers), PERIOD)
    foreign = {t: funds.currency_of(t) for t in tickers if t in prices.columns}
    foreign = {t: c for t, c in foreign.items() if c != "USD"}
    unconverted = {}
    if foreign:
        fx = cached_download(sorted({history.fx_ticker(c) for c in foreign.values()}), PERIOD)
        prices, unconverted = history.to_usd(prices, foreign, fx)
    return history.align_to_market(prices), unconverted


@st.cache_data(ttl="6h", max_entries=50, show_spinner="Trying what-if scenarios...")
def cached_swaps(holdings_items, cash, years):
    holdings = dict(holdings_items)
    prices, _ = analysis_prices(list(holdings))
    returns = history.window(engine.compute_returns(prices), years)
    return optimizer.suggest_swaps(holdings, prices, returns, cash, k=3)


@st.cache_data(show_spinner="Looking inside your funds...", ttl=3600)
def cached_funds(tickers):
    return funds.register(list(tickers))


AI_CLASSIFY_LIMIT = 30  # most tickers sent to the AI in one call


@st.cache_data(show_spinner="Looking up industries...", ttl=86400)
def cached_classify(tickers):
    return llm_csv.classify_stocks(list(tickers))


def look_up_holdings(tickers):
    funds.expire_ai()
    looked_up = cached_funds(tuple(tickers))
    funds.apply(looked_up["funds"])
    funds.apply_stocks(looked_up["stocks"])
    st.session_state.fund_info = looked_up["funds"]


def classify_unknown(tickers, prices):
    """Asks the AI for the sectors Yahoo didn't list, only for tickers that have real prices to grade."""
    recent = history.window(prices, GRADE_YEARS)
    priced = [t for t in funds.unknown_sector(tickers) if t in recent.columns and not recent[t].dropna().empty]
    if priced and llm_csv.available():
        st.write("Looking up industries")
        try:
            funds.apply_stocks(cached_classify(tuple(sorted(priced)[:AI_CLASSIFY_LIMIT])), source="ai")
        except Exception:
            pass
    st.session_state.ai_sectors = [t for t in tickers if funds.estimated_by(t) == "ai"]
    st.session_state.unknown_sectors = funds.unknown_sector(tickers)


def sector_notes():
    notes = []
    if st.session_state.get("ai_sectors"):
        notes.append(f"Industry and country for {', '.join(st.session_state.ai_sectors)} were estimated by AI because Yahoo Finance didn't list them.")
    unknown = st.session_state.get("unknown_sectors")
    if unknown:
        they = "it's" if len(unknown) == 1 else "they're"
        notes.append(f"Couldn't find the industry for {', '.join(unknown)}, so {they} counted as \"Other\".")
    return notes


def pct(x):
    return "n/a" if x != x else f"{round(x * 100):.0f}%"


def signed_pct(x):
    return "n/a" if x != x else f"{round(x * 100):+.0f}%"


def late_start_note(frame, tickers, daily, requested_start, then="so the chart starts there", extra=None):
    firsts = {t: frame[t].first_valid_index() for t in tickers}
    firsts.update(extra or {})
    culprit = history.late_starter(firsts, daily.index[0], requested_start)
    if culprit is None:
        return ""
    return f" — {culprit} didn't exist before then, {then}"


def window_note(frame, tickers, shown, requested_start, bench=None):
    notes = []
    start = shown.index[0]
    if start > requested_start + pd.Timedelta(days=30):
        if bench and bench[1] >= start - pd.Timedelta(days=5):
            notes.append(f"{bench[0]} didn't exist before then, so the chart starts there")
        else:
            notes.append("most of your money is in holdings that didn't exist before then, so the chart starts there")
    late = [t for t in tickers if frame[t].first_valid_index() is None or frame[t].first_valid_index() > start + pd.Timedelta(days=30)]
    if late:
        names = " and ".join(late) if len(late) <= 2 else ", ".join(late[:-1]) + " and " + late[-1]
        notes.append(f"before {names} existed, {'its' if len(late) == 1 else 'their'} share is spread across your other holdings")
    return " — " + "; ".join(notes) if notes else ""


SCENARIO_STATS = [
    ("Real bets", "true_bets", lambda x: f"{x:.1f}", True),
    ("Typical yearly swing", "volatility", pct, False),
    ("Worst drop", "max_drawdown", pct, True),
    ("Return per year", "annual_return", pct, True),
]


def compare_chart(wide, kind, y_title, y_format, height, zero, colors=None):
    names = list(wide.columns)
    long = wide.rename_axis("Date").reset_index().melt("Date", var_name="Series", value_name="Value")
    hover = alt.selection_point(fields=["Date"], nearest=True, on="mouseover", empty=False)
    base = alt.Chart(long).encode(
        x=alt.X("Date:T", title=None),
        y=alt.Y("Value:Q", title=y_title, axis=alt.Axis(format=y_format), scale=alt.Scale(zero=zero)),
        color=alt.Color("Series:N", scale=alt.Scale(domain=names, range=colors or [YOU_COLOR, BENCH_COLOR]), legend=alt.Legend(title=None, orient="top")),
    )
    body = base.mark_area(fillOpacity=0.35, line=True) if kind == "area" else base.mark_line(strokeWidth=1.75)
    dots = base.mark_point(size=45, filled=True).encode(opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    rule = alt.Chart(long).transform_pivot("Series", value="Value", groupby=["Date"]).mark_rule(color="rgba(128,128,128,.45)").encode(
        x="Date:T",
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Date:T", title="Date", format="%b %d, %Y")]
        + [alt.Tooltip(field=n.replace(".", "\\."), type="quantitative", title=n, format=y_format) for n in names],
    ).add_params(hover)
    return alt.layer(body, dots, rule).properties(height=height)


if "holdings_df" not in st.session_state:
    st.session_state.holdings_df = pd.DataFrame({
        "Ticker": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD"],
        "Shares": [22, 20, 18, 14, 14, 12],
    })
if "weights" not in st.session_state:
    st.session_state.weights = None
if "cash" not in st.session_state:
    st.session_state.cash = 0.0

st.markdown(style.CSS, unsafe_allow_html=True)
st.title("Portfolio Check-Up")
st.markdown("<div class='lead'>A plain-English look at whether your investments are really spread out — and what is behind the result.</div>", unsafe_allow_html=True)
analyzed = st.session_state.weights is not None

if not analyzed:
    st.write(
        "Type what you own below and tap **Analyze** for a grade, what's holding it back, "
        "and what-if scenarios showing how a different mix would have behaved. The list below is just an example — change it to what you own."
    )

with st.container(border=True):
    st.subheader("Step 1 — What you own" if not analyzed else "Your holdings")
    if analyzed:
        st.caption("Change anything here and tap Analyze again to refresh the results below.")
    st.write("Type a ticker and how many shares you own, one per row. Use the **+** row at the bottom to add more. An estimate is fine — this is about patterns, not exact accounting.")
    holdings_df = st.data_editor(
        st.session_state.holdings_df,
        num_rows="dynamic",
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker (e.g. AAPL, VOO)"),
            "Shares": st.column_config.NumberColumn("Shares you own", min_value=0),
        },
        hide_index=True,
        width="stretch",
    )
    tickers_typed = [str(t).strip().upper() for t in holdings_df["Ticker"] if str(t).strip()]
    duplicates = {t for t in tickers_typed if tickers_typed.count(t) > 1}
    if duplicates:
        st.warning(f"Duplicate ticker(s): {', '.join(duplicates)} — shares will be combined.")

    left, right = st.columns(2)
    if not holdings_df.empty:
        ticker_to_delete = left.selectbox("Remove a holding", holdings_df["Ticker"].tolist())
        if left.button("Delete holding", width="stretch"):
            st.session_state.holdings_df = holdings_df[holdings_df["Ticker"] != ticker_to_delete].reset_index(drop=True)
            st.rerun()
    cash_input = right.number_input("Cash ($) you're keeping uninvested", min_value=0.0, value=st.session_state.cash, step=100.0, help="Money you've set aside but not invested. Leave at 0 if none.")

    with st.expander("Or upload a file from your brokerage (Fidelity, Schwab, Robinhood, Vanguard…)"):
        uploaded = st.file_uploader("CSV file", type=["csv"], help="Export the Positions or Holdings page as a CSV. For Robinhood, use the account activity report.")
        use_ai = False
        if llm_csv.available():
            ai_config = llm_csv.config()
            use_ai = st.checkbox("Use AI to read this file", help="An open AI model reads the file. Good for 401(k), 529 and other unusual exports. It is also used automatically when the standard reader can't match every line.")
            where = "runs on this computer" if llm_csv.is_local(ai_config) else f"file contents are sent to {llm_csv.host(ai_config)}"
            st.caption(f"AI model: {ai_config['model']} — {where}.")
        if uploaded is not None:
            file_key = f"{uploaded.name}:{uploaded.size}:{use_ai}"
            if st.session_state.get("csv_applied") != file_key:
                parsed, problem = read_brokerage_file(uploaded.getvalue(), use_ai)
                if parsed is None:
                    st.error(problem)
                else:
                    shares = dict(parsed["shares"])
                    if parsed["value_only"]:
                        latest = cached_download(list(parsed["value_only"]), "1mo")
                        for t, dollars in parsed["value_only"].items():
                            if t in latest.columns and not latest[t].dropna().empty:
                                shares[t] = round(dollars / float(latest[t].dropna().iloc[-1]), 2)
                    loaded_df = pd.DataFrame({"Ticker": list(shares), "Shares": list(shares.values())})
                    fund_notes = []
                    if parsed.get("estimated_funds"):
                        loaded_df, fund_notes = add_estimated_funds(loaded_df, parsed["estimated_funds"])
                    st.session_state.holdings_df = loaded_df
                    if parsed["cash"] > 0:
                        st.session_state.cash = float(parsed["cash"])
                    st.session_state.csv_applied = file_key
                    st.session_state.csv_notes = ([problem] if problem else []) + parsed["notes"] + fund_notes
                    st.rerun()
            if st.session_state.get("csv_notes") is not None:
                st.success("Loaded your holdings from the file. Check them above, then tap Analyze.")
                for note in st.session_state.csv_notes:
                    st.caption(note.replace("$", "\\$"))

    if not analyzed:
        st.subheader("Step 2 — Analyze")
    if st.button("Analyze my portfolio", type="primary", width="stretch"):
        st.session_state.holdings_df = holdings_df
        st.session_state.cash = cash_input
        holdings = holdings_df_to_dict(holdings_df)
        if not holdings:
            st.error("Add at least one holding before analyzing.")
            st.stop()

        with st.status("Checking your portfolio...", expanded=False) as status:
            tickers = list(holdings.keys())
            st.write("Looking inside your funds")
            look_up_holdings(tickers)
            st.write("Downloading prices")
            prices, unconverted = analysis_prices(tickers)
            recent = history.window(prices, GRADE_YEARS)

            missing = [t for t in tickers if t not in unconverted and (t not in prices.columns or recent[t].dropna().empty)]
            analyze_notes = []
            if missing:
                st.write(f"Rechecking {', '.join(missing)}")
                holdings_df, holdings, analyze_notes = replace_unpriced(holdings_df, holdings, missing)
                st.session_state.holdings_df = holdings_df
                if not holdings:
                    status.update(label="Couldn't finish", state="error", expanded=True)
                    st.error(f"No price data available for: {', '.join(missing)}. This can happen with a mistyped ticker, or if Yahoo Finance is busy — try again in a moment.")
                    st.stop()
                tickers = list(holdings.keys())
                look_up_holdings(tickers)
                prices, unconverted = analysis_prices(tickers)
            if unconverted:
                analyze_notes = analyze_notes + [f"Couldn't convert {t} from {c} to dollars, so it was left out." for t, c in unconverted.items()]
                holdings_df = holdings_df[~df_tickers(holdings_df).isin(list(unconverted))].reset_index(drop=True)
                st.session_state.holdings_df = holdings_df
                holdings = holdings_df_to_dict(holdings_df)
                tickers = list(holdings.keys())
                if not holdings:
                    status.update(label="Couldn't finish", state="error", expanded=True)
                    for note in analyze_notes:
                        st.warning(note.replace("$", "\\$"))
                    st.stop()
            st.session_state.analyze_notes = analyze_notes
            classify_unknown(tickers, prices)
            st.write("Working out your mix")

            st.session_state.holdings = holdings
            st.session_state.prices = prices
            st.session_state.returns = engine.compute_returns(prices)
            st.session_state.weights, st.session_state.stock_value = holdings_to_weights(holdings, prices)
            status.update(label="Done", state="complete")
        st.rerun()


@st.fragment
def growth_section(weights, returns, prices, tickers, holdings, invested_share, swaps):
    """The 'How it has grown' picker, window and chart. A fragment, so changing them reruns only this part."""
    pick, custom_col = st.columns(2)
    choice = pick.selectbox("Compare with", list(BENCHMARKS) + [CUSTOM_OPTION])
    bench_label, bench_weights, bench_returns = DEFAULT_BENCHMARK, BENCHMARKS[DEFAULT_BENCHMARK], returns
    if choice in BENCHMARKS:
        bench_label, bench_weights = choice, BENCHMARKS[choice]
    else:
        custom = custom_col.text_input("Ticker to compare with", value="").strip().upper()
        if custom:
            try:
                custom_prices = cached_download([custom], PERIOD)
                if custom in custom_prices.columns:
                    custom_prices = history.align_to_dates(custom_prices, prices.index)
            except Exception:
                custom_prices = pd.DataFrame()
            if custom_prices.empty or custom not in custom_prices.columns or custom_prices[custom].dropna().empty:
                st.error(f"No price data for {custom} — comparing with the S&P 500 instead.")
            else:
                bench_label, bench_weights, bench_returns = custom, {custom: 1.0}, engine.compute_returns(custom_prices)
    bench_name = bench_label.split(" (")[0]
    growth_choice = st.radio("Time window", list(GROWTH_WINDOWS), index=1, horizontal=True, label_visibility="collapsed", key="growth_years")
    growth_years = GROWTH_WINDOWS[growth_choice]
    returns_growth = history.window(returns, growth_years)

    your_daily = history.with_cash(history.filled_daily(weights, returns_growth), invested_share)
    bench_daily = history.portfolio_daily(bench_weights, history.window(bench_returns, growth_years))
    both = pd.concat([your_daily.rename("You"), bench_daily.rename(bench_name)], axis=1, join="inner")
    if both.empty:
        st.warning(f"You and {bench_name} don't share enough price history to compare.")
    else:
        st.altair_chart(compare_chart(both.apply(history.growth_of), "line", "Value of $10,000", "$,.0f", 300, zero=False), width="stretch")
        yours, bench = history.summary(both["You"]), history.summary(both[bench_name])
        st.markdown(style.compare_table([("You", YOU_COLOR), (bench_name, BENCH_COLOR)], [
            (f"Total return since {both.index[0]:%b %Y}", [signed_pct(yours["total_return"]), signed_pct(bench["total_return"])]),
            ("Worst drop along the way", [pct(yours["max_drawdown"]), pct(bench["max_drawdown"])]),
            ("Typical yearly swing", [pct(yours["volatility"]), pct(bench["volatility"])]),
        ]), unsafe_allow_html=True)
        st.caption(f"Showing {history.date_range_text(both)}{window_note(returns_growth, tickers, both, history.window_start(returns, growth_years), bench=(bench_name, bench_daily.index[0]))}.")

        if swaps:
            st.space("medium")
            st.markdown("##### See a scenario play out")
            move = st.selectbox("Scenario to replay", [s["text"] for s in swaps], label_visibility="collapsed", key="whatif_move")
            swap = next(s for s in swaps if s["text"] == move)
            after_holdings = dict(holdings)
            after_holdings[swap["sell_ticker"]] = after_holdings[swap["sell_ticker"]] - swap["sell_shares"]
            if after_holdings[swap["sell_ticker"]] <= 0:
                del after_holdings[swap["sell_ticker"]]
            after_holdings[swap["buy_ticker"]] = after_holdings.get(swap["buy_ticker"], 0) + swap["buy_shares"]
            after_weights, _ = holdings_to_weights(after_holdings, prices)
            after_daily = history.with_cash(history.filled_daily(after_weights, returns_growth), invested_share)  # the scenario keeps the same cash
            trio = pd.concat([your_daily.rename("You now"), after_daily.rename("In the scenario"), bench_daily.rename(bench_name)], axis=1, join="inner")
            st.altair_chart(compare_chart(trio.apply(history.growth_of), "line", "Value of $10,000", "$,.0f", 300, zero=False, colors=[YOU_COLOR, AFTER_COLOR, BENCH_COLOR]), width="stretch")
            now, after = history.summary(trio["You now"]), history.summary(trio["In the scenario"])
            st.markdown(style.compare_table([("You now", YOU_COLOR), ("In the scenario", AFTER_COLOR)], [
                (f"Total return since {trio.index[0]:%b %Y}", [signed_pct(now["total_return"]), signed_pct(after["total_return"])]),
                ("Worst drop along the way", [pct(now["max_drawdown"]), pct(after["max_drawdown"])]),
                ("Typical yearly swing", [pct(now["volatility"]), pct(after["volatility"])]),
            ]), unsafe_allow_html=True)
            st.caption("Past prices, not a prediction — this is how the scenario's mix would have behaved over the same stretch.")


for note in st.session_state.get("analyze_notes") or []:
    st.warning(note.replace("$", "\\$"))

if st.session_state.weights is None:
    st.caption("Your results will appear here after you tap Analyze.")
else:
    weights = st.session_state.weights
    returns = st.session_state.returns
    tickers = list(weights)
    holdings = st.session_state.holdings
    prices = st.session_state.prices
    cash = st.session_state.cash
    total_value = st.session_state.stock_value + cash
    invested_share = st.session_state.stock_value / total_value if total_value > 0 else 1.0
    mix_words = "your current mix, including cash," if cash > 0 else "your current mix"  # used mid-sentence

    returns_3y = history.window(returns, GRADE_YEARS)
    advice = tips.build_tips(weights, returns_3y, invested_share)
    facts = advice["facts"]
    weights_with_cash = dict(facts["total_weights"])
    if facts["cash_share"] > 0:
        weights_with_cash["CASH"] = facts["cash_share"]
    grade_daily = history.portfolio_daily(weights, returns_3y[tickers])

    st.space("medium")
    st.markdown(style.hero(advice["grade"], advice["verdict"], [
        ("Holdings", str(facts["holdings"])),
        ("Real bets", f"{facts['true_bets']:.1f}"),
        ("Biggest holding", f"{facts['biggest']} · {facts['biggest_pct']:.0f}%"),
    ]), unsafe_allow_html=True)
    st.caption("Grades run A to F. They average the six rings below: spread across companies, industries and countries, plus how steady, how consistent and how free of near-duplicates the mix has been.")
    grade_note = late_start_note(returns_3y, tickers, grade_daily, history.window_start(returns, GRADE_YEARS), "so the grade only covers that stretch")
    if grade_note:
        st.caption(f"Based on prices from {history.date_range_text(grade_daily)}{grade_note}.")
    else:
        st.caption(f"Based on the last {GRADE_YEARS} years of prices ({history.date_range_text(grade_daily)}).")
    if st.session_state.get("fund_info"):
        st.caption("Looked inside your funds: " + "; ".join(funds.describe(t, e) for t, e in st.session_state.fund_info.items()) + ".")
    for note in sector_notes():
        st.caption(note)

    report_slot = st.empty()

    st.markdown("#### What your grade is made of")
    st.caption("Your letter grade is the average of these rings (lowered when much of your money sits in cash). A fuller ring scores higher.")
    for group in dict.fromkeys(dim["group"] for dim in advice["dimensions"]):
        st.caption(f"**{group}**")
        st.markdown(style.score_rings([dim for dim in advice["dimensions"] if dim["group"] == group]), unsafe_allow_html=True)
    with st.expander("What each ring means"):
        for dim in advice["dimensions"]:
            st.markdown(f"**{dim['name']}** — {LEVEL_MARK[dim['level']]}  \n{dim['text']}")
    with st.expander("What does “real bets” mean?"):
        st.write(
            "Real bets estimates how many genuinely separate sources of risk your money has — not how many tickers you own, but how many "
            "*independent* ones. If several holdings usually rise and fall together, they count as fewer independent bets — so six tech stocks "
            "may behave more like two. A broad fund counts as several, because it holds many companies — though fewer than you might expect, "
            "since companies in the same fund tend to move together. It is this app's own measure, built from two standard ones: how evenly "
            "your money is spread, and how closely your holdings' daily moves have matched over the last 3 years."
        )
        st.write(
            "One limit worth knowing: real bets only measures overlap *within* your holdings. It doesn't erase risk everyone shares — a fund "
            "spread across 500 companies is still one big bet on the stock market as a whole. Being spread across companies and being spread "
            "across types of investment are two different things; the **By type of investment** chart further down shows the second."
        )

    st.space("medium")
    st.subheader("What stands out")
    st.caption("Most important first.")
    st.markdown(style.tip_cards(advice["tips"]), unsafe_allow_html=True)

    st.space("medium")
    st.subheader("What-if scenarios")
    st.info("These are hypothetical educational scenarios, not recommendations to buy or sell. They show how historical risk and diversification would have changed under a different mix. Only a short fixed list of broad funds is tried; other investments not considered may have similar or better characteristics.")
    swaps = cached_swaps(tuple(sorted(holdings.items())), cash, GRADE_YEARS)
    if any(s.get("tweak") for s in swaps):
        st.caption("Smaller tweaks keep your grade where it is but make at least one number below better — useful when a mix already grades well.")
    for i, swap in enumerate(swaps, 1):
        st.markdown(style.scenario_card(i, swap, SCENARIO_STATS), unsafe_allow_html=True)
    if not swaps and advice["grade"] in ("A", "B"):
        st.write("None of the tested swaps would have clearly raised the grade or real bets for this mix — that's a good sign.")
    elif not swaps:
        st.write("None of the tested swaps would have clearly raised the grade or real bets for this mix. The notes above explain what is holding the grade down.")
    st.caption(f"Each scenario swaps part or all of one large holding for one of ten common diversifying funds, then re-grades the mix over the last {GRADE_YEARS} years; the ones that change the most are shown, topped up with smaller tweaks when fewer than three clearly raise the grade or real bets. Typical yearly swing = how much a normal year moves this mix up or down. Worst drop = the biggest fall from a high point before it recovered. A steadier mix usually earns a bit less per year — that trade-off is the point. Share counts use today's prices and are rounded.")

    st.space("medium")
    st.subheader("How it has grown")
    st.caption(f"What $10,000 in {mix_words} would be worth today, next to whatever you pick to compare it with.")
    if cash > 0:
        st.caption(CASH_NOTE)
    growth_section(weights, returns, prices, tickers, holdings, invested_share, swaps)

    st.space("medium")
    st.subheader("How it would have held up in past crashes")
    st.caption(f"What {mix_words} would have done, compared with the S&P 500.")
    crashes = [
        ("2022 downturn", "2022-01-03", "2022-10-13"),
        ("COVID crash, 2020", "2020-02-19", "2020-03-23"),
        ("Late-2018 drop", "2018-10-01", "2018-12-24"),
    ]
    worse_count = 0
    compared = 0
    crash_rows = []
    crash_cards = []
    all_daily = history.with_cash(history.filled_daily(weights, returns), invested_share)
    for name, start, end in crashes:
        window = all_daily.loc[start:end]
        yours = {"total_return": history.total_return(window)} if len(window) and all_daily.index[0] <= pd.Timestamp(start) else None
        absent = [t for t in tickers if returns[t].first_valid_index() is None or returns[t].first_valid_index() > pd.Timestamp(start)]
        spy = engine.crash_test({"SPY": 1.0}, returns[["SPY"]], start, end)
        crash_rows.append({
            "name": name, "dates": history.short_range_text(start, end),
            "you": pct(yours["total_return"]) if yours else "not enough history",
            "spy": pct(spy["total_return"]) if spy else "n/a",
        })
        card = {"name": name, "dates": history.short_range_text(start, end), "rows": []}
        if yours is None:
            card["note"] = "Not enough history — most of your money is in holdings that didn't exist yet."
        else:
            card["rows"].append(("You", pct(yours["total_return"])))
            if spy is not None:
                card["rows"].append(("S&P 500", pct(spy["total_return"])))
                compared += 1
                if yours["total_return"] < spy["total_return"]:
                    worse_count += 1
                    card["note"], card["note_color"] = "Fell harder than the market", style.RED
                else:
                    card["note"], card["note_color"] = "Held up better than the market", style.GREEN
            if absent:
                card["rows"].append(("Without", ", ".join(absent)))
        crash_cards.append(card)
    st.markdown(style.crash_cards(crash_cards), unsafe_allow_html=True)
    if compared:
        if worse_count == 0:
            st.success(f"This mix would have dropped **less** than the market in every crash we could check ({compared} of {compared}).")
        elif worse_count == compared:
            st.warning(f"This mix would have dropped **more** than the market in every crash we could check ({compared} of {compared}). The what-if scenarios above show what would have softened that.")
        else:
            st.info(f"This mix would have dropped more than the market in {worse_count} of the {compared} crashes we could check.")

    st.space("medium")
    st.subheader("How steady it has been")
    steady_choice = st.radio("Time window", list(STEADY_WINDOWS), horizontal=True, label_visibility="collapsed", key="steady_years")
    steady_years = STEADY_WINDOWS[steady_choice]
    returns_steady = history.window(returns, steady_years)
    steady_daily = history.filled_daily(weights, returns_steady)
    monthly = history.monthly_returns(steady_daily)
    ups = int((monthly > 0).sum())
    total_months = len(monthly)
    st.markdown(f"#### {ups} of the last {total_months} months ended positive")
    st.caption("How many calendar months this mix gained value. Around 6 in 10 is typical for the overall market.")
    monthly_df = monthly.reset_index()
    monthly_df.columns = ["Month", "Return"]
    monthly_df["Direction"] = monthly_df["Return"].apply(lambda r: "Up" if r >= 0 else "Down")
    chart = alt.Chart(monthly_df).mark_bar(cornerRadiusEnd=2).encode(
        x=alt.X("Month:T", title=None),
        y=alt.Y("Return:Q", title="Monthly change", axis=alt.Axis(format="%")),
        color=alt.Color("Direction:N", scale=alt.Scale(domain=["Up", "Down"], range=[style.GREEN, style.RED]), legend=None),
        tooltip=[alt.Tooltip("Month:T", title="Month", format="%b %Y"), alt.Tooltip("Return:Q", title="Change", format=".1%")]
    ).properties(height=240)
    st.altair_chart(chart, width="stretch")
    st.caption(f"Showing {history.date_range_text(steady_daily)}{window_note(returns_steady, tickers, steady_daily, history.window_start(returns, steady_years))}.")

    st.space("medium")
    st.subheader("Where your money really is")
    st.caption("As of today's prices.")
    left, right = st.columns(2, gap="large")
    rows = regions.asset_mix(weights_with_cash)
    left.markdown(style.split_bar("By type of investment", [(r["asset"], r["pct"]) for r in rows],
                                  [ASSET_COLORS.get(r["asset"], SLICE_COLORS[-1]) for r in rows]), unsafe_allow_html=True)
    rows = regions.country_mix(weights_with_cash)
    right.markdown(style.split_bar("By country", [(r["country"], r["pct"]) for r in rows], SLICE_COLORS), unsafe_allow_html=True)
    st.space("medium")
    left, right = st.columns(2, gap="large")
    by_holding = [(t, w * 100, None) for t, w in sorted(facts["total_weights"].items(), key=lambda kv: -kv[1])]
    if facts["cash_share"] > 0:
        by_holding.append(("Cash", facts["cash_share"] * 100, None))
    left.markdown(style.bar_list("By holding", "Share of everything you own, including cash.", by_holding), unsafe_allow_html=True)
    with right:
        if facts["sectors"]:
            st.markdown(style.bar_list("By industry", "Share of your invested money. The tick marks the S&P 500.",
                                       [(r["sector"], r["pct"], r["sp"]) for r in facts["sectors"]]), unsafe_allow_html=True)
        else:
            st.markdown(style.bar_list("By industry", "None of your holdings are individual stocks or stock funds, so there's no industry split to show.", []), unsafe_allow_html=True)
        if facts["non_eq"] > 0.005:
            st.caption(f"Bonds, gold, or other non-stock funds: {pct(facts['non_eq'])} of your invested money.")

    st.space("medium")
    with st.expander("Learn the ideas — a 5-minute read"):
        st.write("#### Owning more stocks isn't the same as being spread out")
        st.write("Owning 20 different tickers *feels* diversified because it's a big number. But if all 20 are large tech companies, they'll rise and fall together in a downturn — you're really making one big bet (\"tech will do well\") spread across 20 names. That's what **real bets** measures: how many genuinely separate bets you're making, not how many tickers are on the list.")

        st.write("#### \"Moving together\" is about timing, not what a company does")
        st.write("Two holdings move together when they tend to go up and down on the same days. AAPL and MSFT do, because the same tech-sector news hits both. An airline and an oil company can too, for the opposite reason: oil is the airline's biggest cost, so when oil moves, both react at once. The number that captures this is called correlation — 1 means always together, 0 means unrelated.")

        st.write("#### Crashes are when 'spread out' matters most — and when it quietly fails")
        st.write("In calm markets, different industries move somewhat independently. In a real crash, almost everything sells off together, because the cause (panic, forced selling) hits everything at once. Holdings you thought were unrelated turn out to be related right when it matters. That's why a **safety net** — something like bonds or gold that genuinely behaves differently — is worth more than it looks on a normal day.")

        st.write("#### \"Core\" and \"satellites\"")
        st.write("Many investors describe a mix as a **core** of broad funds (such as VTI or SPY) plus **satellites**: individual stocks or narrower funds picked one by one. It is a way of describing a portfolio, not a recipe — this tool doesn't suggest any particular split.")

    with st.expander("About this project"):
        st.write(
            "**Portfolio Check-Up** takes a list of holdings and explains, in plain English, whether they're actually spread out — "
            "not just how many tickers there are, but how many genuinely independent risks they add up to. It grades the mix, looks "
            "inside any ETF or mutual fund to see what it really holds, and shows what-if scenarios for how a few common changes would have affected it."
        )
        st.write(
            "**Designed and built by Shrihaan Zaroo**, as an independent project. The main ideas behind it — real bets, the grade, "
            "and fund look-through — are explained above and in the method notes below; the short version is that they're built from "
            "standard statistics (concentration and correlation) combined into estimates that are this app's own, not an industry standard."
        )
        st.write(
            "**Limits worth knowing:** everything here looks backward, three years is a short sample, and holdings tend to move "
            "together more in a crash than in calm years. Country and fund breadth figures are approximate, and taxes, fees and "
            "trading costs are ignored. This is an educational tool, not financial advice."
        )
        st.write("**Contact:** [github.com/shrihaanzaroo/portfolio_analyzer](https://github.com/shrihaanzaroo/portfolio_analyzer) · shrihaanzaroo@gmail.com")

    with st.expander("How this works — data, method and limits"):
        for heading, body in METHOD:
            st.write(f"**{heading}** {body}")

    spy_daily = history.portfolio_daily({"SPY": 1.0}, returns_3y[["SPY"]])
    pair = pd.concat([history.with_cash(grade_daily, invested_share).rename("you"), spy_daily.rename("spy")], axis=1, join="inner")
    mine, market = history.summary(pair["you"]), history.summary(pair["spy"])
    steady_3y = history.monthly_returns(history.filled_daily(weights, returns_3y))
    report_slot.download_button(
        "Download this check-up as a report",
        report.build_html({
            "date": history.date_text(pd.Timestamp.today()),
            "basis": f"Prices from {history.date_range_text(grade_daily)}, Yahoo Finance",
            "grade": advice["grade"], "verdict": advice["verdict"], "holdings": facts["holdings"], "true_bets": facts["true_bets"],
            "biggest": facts["biggest"], "biggest_pct": facts["biggest_pct"], "dimensions": advice["dimensions"], "tips": advice["tips"],
            "weights": sorted(weights_with_cash.items(), key=lambda kv: -kv[1]),
            "assets": regions.asset_mix(weights_with_cash), "countries": regions.country_mix(weights_with_cash), "sectors": facts["sectors"],
            "funds": [funds.describe(t, e) for t, e in (st.session_state.get("fund_info") or {}).items()],
            "sector_notes": sector_notes(),
            "performance": [
                ("Total return", signed_pct(mine["total_return"]), signed_pct(market["total_return"])),
                ("Return per year", pct(mine["annual_return"]), pct(market["annual_return"])),
                ("Typical yearly swing", pct(mine["volatility"]), pct(market["volatility"])),
                ("Worst drop", pct(mine["max_drawdown"]), pct(market["max_drawdown"])),
            ],
            "performance_range": history.date_range_text(pair),
            "cash_note": CASH_NOTE if cash > 0 else "",
            "steady": f"{int((steady_3y > 0).sum())} of {len(steady_3y)} months ended positive",
            "crashes": crash_rows, "scenarios": swaps, "method": METHOD,
        }),
        file_name="portfolio-check-up.html", mime="text/html", icon=":material/download:",
        help="Opens in any browser. Use the browser's Print to save it as a PDF.",
    )

    st.caption("Educational tool only — not financial advice. Prices from Yahoo Finance. Want every detail? The full Portfolio Analyzer has 12 sections covering the same portfolio.")
