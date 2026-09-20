import pandas as pd
import altair as alt
import streamlit as st
import brokerage_csv
import engine
import funds
import history
import optimizer
import regions
import report
import tips

st.set_page_config(page_title="Portfolio Check-Up", page_icon="🩺", layout="wide")
cached_download = st.cache_data(show_spinner="Downloading price history...")(engine.download_prices)

LEVEL_BOX = {"high": st.error, "medium": st.warning, "good": st.success}
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
YOU_COLOR = "#2a78d6"
AFTER_COLOR = "#1baf7a"
BENCH_COLOR = "#898781"
SLICE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]
ASSET_COLORS = {"Stocks": "#2a78d6", "Bonds": "#1baf7a", "Gold": "#eda100", "Cash": "#008300"}

METHOD = [
    ("Data.", "Daily closing prices from Yahoo Finance, adjusted for splits and dividends. The grade, the notes and the scenarios use the last 3 years; each chart says which dates it shows. When a chart reaches back before one of your holdings existed, that holding's share is spread across the others for that stretch, as long as the holdings that did exist make up at least half your money; the chart says so when it happens."),
    ("How spread out.", "Your money is converted to weights at today's prices. Concentration uses the Herfindahl index, a standard measure: square each weight and add them up; one divided by that total is the number of equal-sized holdings your mix behaves like."),
    ("Funds.", "ETFs and mutual funds are looked up on Yahoo Finance and looked inside: their largest holdings, industry split and stock/bond/cash split. The rest of a fund is spread across an estimated number of companies for its category (about 50 for an S&P 500 fund, 60 for a total-market fund), not its exact holdings list. If the lookup fails, a built-in table of common index funds is used."),
    ("Moving together.", "Correlation of daily returns between each pair of holdings — a standard statistic from -1 to 1. Holdings that barely move (such as cash-like funds) are left out."),
    ("Real bets.", "This app's own estimate, not an industry standard: the equal-sized-holdings number divided by (1 + (that number - 1) x the average correlation). With no correlation it equals the number of holdings; as holdings move together it falls toward 1. Companies inside the same fund are assumed to move together with a correlation of 0.35, a typical long-run figure for large companies, because a fund's insides cannot be measured from its price."),
    ("The grade.", "An average of seven checks, each scored 0 to 4: spread across companies, across industries, across countries, across types of investment, swings compared with the S&P 500, share of months that ended positive, and near-duplicate holdings. It is discounted when most of the money sits in cash. The cut-offs are judgment calls."),
    ("Scenarios.", "About 100 hypothetical swaps are tried: half or all of each of your five largest holdings, into each of ten common diversifiers (bond, gold, broad-market, international, and steady-industry holdings). Each new mix is re-graded the same way over the same 3 years, and the three that change the most are shown."),
    ("Tested on.", "Six large tech stocks grade C (about 2 real bets, one industry). An S&P 500 fund with bonds, gold and stocks from other industries grades B, and A once an international fund is added. A single stock is capped at D. A single total-market index fund grades B: many companies, but one country and one type of investment. Three overlapping U.S. stock funds grade B but count as about 1.3 real bets."),
    ("Limits.", "Everything here looks backward: it describes how this mix behaved, not how it will. Three years is a short sample, and holdings tend to move together more in a crash than in calm years. Country and fund breadth figures are approximate. Taxes, fees and trading costs are ignored. This is an educational tool, not financial advice."),
]


def holdings_df_to_dict(df):
    holdings = {}
    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()
        shares = row["Shares"]
        if not ticker or pd.isna(shares) or shares <= 0:
            continue
        holdings[ticker] = holdings.get(ticker, 0) + float(shares)
    return {t: int(s) if s.is_integer() else round(s, 4) for t, s in holdings.items()}


def holdings_to_weights(holdings, prices):
    values = {t: float(prices[t].dropna().iloc[-1]) * shares for t, shares in holdings.items()}
    total = sum(values.values())
    return {t: v / total for t, v in values.items()}, total


def download_list(tickers):
    return list(dict.fromkeys(sorted(tickers) + ["SPY"] + BENCHMARK_TICKERS + list(optimizer.CANDIDATES)))


@st.cache_data(show_spinner="Looking for better mixes...")
def cached_swaps(holdings_items, cash, years):
    holdings = dict(holdings_items)
    prices = cached_download(download_list(list(holdings)), PERIOD)
    returns = history.window(engine.compute_returns(prices), years)
    return optimizer.suggest_swaps(holdings, prices, returns, cash, k=3)


@st.cache_data(show_spinner="Looking inside your funds...", ttl=3600)
def cached_funds(tickers):
    return funds.register(list(tickers))


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


def stat_chip(col, label, before, after, fmt, higher_is_better):
    if fmt(after) == fmt(before):
        verdict = "about the same"
    elif (after > before) == higher_is_better:
        verdict = ":green[better]"
    else:
        verdict = ":red[worse]"
    col.markdown(f"**{label}**  \n{fmt(before)} → {fmt(after)}  \n{verdict}")


def compare_chart(wide, kind, y_title, y_format, height, zero, colors=None):
    names = list(wide.columns)
    long = wide.rename_axis("Date").reset_index().melt("Date", var_name="Series", value_name="Value")
    hover = alt.selection_point(fields=["Date"], nearest=True, on="mouseover", empty=False)
    base = alt.Chart(long).encode(
        x=alt.X("Date:T", title=None),
        y=alt.Y("Value:Q", title=y_title, axis=alt.Axis(format=y_format), scale=alt.Scale(zero=zero)),
        color=alt.Color("Series:N", scale=alt.Scale(domain=names, range=colors or [YOU_COLOR, BENCH_COLOR]), legend=alt.Legend(title=None, orient="top")),
    )
    body = base.mark_area(fillOpacity=0.35, line=True) if kind == "area" else base.mark_line(strokeWidth=2)
    dots = base.mark_point(size=50, filled=True).encode(opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    rule = alt.Chart(long).transform_pivot("Series", value="Value", groupby=["Date"]).mark_rule(color="#c3c2b7").encode(
        x="Date:T",
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Date:T", title="Date", format="%b %d, %Y")]
        + [alt.Tooltip(field=n.replace(".", "\\."), type="quantitative", title=n, format=y_format) for n in names],
    ).add_params(hover)
    return alt.layer(body, dots, rule).properties(height=height)


def donut(rows, field, title, colors):
    df = pd.DataFrame(rows)
    df["share"] = df["pct"] / 100
    names = df[field].tolist()
    return alt.Chart(df).mark_arc(innerRadius=60).encode(
        theta=alt.Theta("pct:Q"),
        order=alt.Order("pct:Q", sort="descending"),
        color=alt.Color(f"{field}:N", scale=alt.Scale(domain=names, range=colors), legend=alt.Legend(title=None, orient="bottom", columns=3)),
        tooltip=[alt.Tooltip(f"{field}:N", title=title), alt.Tooltip("share:Q", title="Share", format=".0%")],
    ).properties(height=260)


if "holdings_df" not in st.session_state:
    st.session_state.holdings_df = pd.DataFrame({
        "Ticker": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD"],
        "Shares": [22, 20, 18, 14, 14, 12],
    })
if "weights" not in st.session_state:
    st.session_state.weights = None
if "cash" not in st.session_state:
    st.session_state.cash = 0.0

st.sidebar.header("What you own")
uploaded = st.sidebar.file_uploader(
    "Upload a CSV from your brokerage (Fidelity, Schwab, Robinhood, Vanguard…)",
    type=["csv"],
    help="Export the Positions or Holdings page as a CSV. For Robinhood, use the account activity report.",
)
if uploaded is not None:
    file_key = f"{uploaded.name}:{uploaded.size}"
    if st.session_state.get("csv_applied") != file_key:
        try:
            parsed = brokerage_csv.parse(uploaded.getvalue())
        except ValueError as e:
            st.sidebar.error(str(e))
        else:
            shares = dict(parsed["shares"])
            if parsed["value_only"]:
                latest = cached_download(list(parsed["value_only"]), "1mo")
                for t, dollars in parsed["value_only"].items():
                    if t in latest.columns and not latest[t].dropna().empty:
                        shares[t] = round(dollars / float(latest[t].dropna().iloc[-1]), 2)
            st.session_state.holdings_df = pd.DataFrame({"Ticker": list(shares), "Shares": list(shares.values())})
            if parsed["cash"] > 0:
                st.session_state.cash = float(parsed["cash"])
            st.session_state.csv_applied = file_key
            st.session_state.csv_notes = parsed["notes"]
            st.rerun()
    if st.session_state.get("csv_notes") is not None:
        st.sidebar.success("Loaded your holdings from the file. Check them below, then tap Analyze.")
        for note in st.session_state.csv_notes:
            st.sidebar.caption(note)
holdings_df = st.sidebar.data_editor(
    st.session_state.holdings_df,
    num_rows="dynamic",
    column_config={
        "Ticker": st.column_config.TextColumn("Ticker"),
        "Shares": st.column_config.NumberColumn("Shares", min_value=0),
    },
    hide_index=True,
)
st.sidebar.caption("Shares = how many you own. An estimate is fine — this is about patterns, not exact accounting.")

if not holdings_df.empty:
    ticker_to_delete = st.sidebar.selectbox("Remove a holding", holdings_df["Ticker"].tolist())
    if st.sidebar.button("Delete holding", use_container_width=True):
        st.session_state.holdings_df = holdings_df[holdings_df["Ticker"] != ticker_to_delete].reset_index(drop=True)
        st.rerun()

tickers_typed = [str(t).strip().upper() for t in holdings_df["Ticker"] if str(t).strip()]
duplicates = {t for t in tickers_typed if tickers_typed.count(t) > 1}
if duplicates:
    st.sidebar.warning(f"Duplicate ticker(s): {', '.join(duplicates)} — shares will be combined.")

cash_input = st.sidebar.number_input("Cash ($)", min_value=0.0, value=st.session_state.cash, step=100.0, help="Money you've set aside but not invested.")

if st.sidebar.button("Analyze", type="primary", use_container_width=True):
    st.session_state.holdings_df = holdings_df
    st.session_state.cash = cash_input
    holdings = holdings_df_to_dict(holdings_df)
    if not holdings:
        st.error("Add at least one holding before analyzing.")
        st.stop()

    tickers = list(holdings.keys())
    fund_info = cached_funds(tuple(tickers))
    funds.apply(fund_info)
    st.session_state.fund_info = fund_info
    prices = cached_download(download_list(tickers), PERIOD)
    recent = history.window(prices, GRADE_YEARS)

    missing = [t for t in tickers if t not in prices.columns or recent[t].dropna().empty]
    if missing:
        st.error(f"No price data available for: {', '.join(missing)}. This can happen with a mistyped ticker, or if Yahoo Finance is busy — try again in a moment.")
        st.stop()

    st.session_state.holdings = holdings
    st.session_state.prices = prices
    st.session_state.returns = engine.compute_returns(prices)
    st.session_state.weights, st.session_state.stock_value = holdings_to_weights(holdings, prices)


st.title("Portfolio Check-Up")
st.caption("A plain-English look at whether your investments are really spread out — and what to do about it.")

if st.session_state.weights is None:
    st.info(
        "**What this does:** you tell it what you own, and it gives you a grade, what is holding it back, "
        "what-if scenarios that show what would change it, how your money has grown compared with the market, and where it really is — by type, "
        "by country, and by industry. "
        "Your holdings live in the **sidebar** (on a phone, tap the **›** arrow at the top-left to open it). "
        "The defaults there are just an example: edit them, then tap **Analyze**."
    )
else:
    weights = st.session_state.weights
    returns = st.session_state.returns
    tickers = list(weights)
    holdings = st.session_state.holdings
    prices = st.session_state.prices
    cash = st.session_state.cash
    total_value = st.session_state.stock_value + cash
    invested_share = st.session_state.stock_value / total_value if total_value > 0 else 1.0

    returns_3y = history.window(returns, GRADE_YEARS)
    advice = tips.build_tips(weights, returns_3y, invested_share)
    facts = advice["facts"]
    weights_with_cash = dict(facts["total_weights"])
    if facts["cash_share"] > 0:
        weights_with_cash["CASH"] = facts["cash_share"]
    grade_daily = history.portfolio_daily(weights, returns_3y[tickers])

    with st.container(border=True):
        g, v = st.columns([1, 5])
        g.markdown(f"# {advice['grade']}")
        g.caption("Grade")
        v.markdown(f"#### {advice['verdict']}")
        v.markdown(
            f"**{facts['holdings']} holding{'' if facts['holdings'] == 1 else 's'}** · acting like **{facts['true_bets']:.1f} real bets** · "
            f"biggest: **{facts['biggest']} ({facts['biggest_pct']:.0f}% of your money)**"
        )
        v.caption("Grades run A to F. They reward being spread across companies, industries, countries and types of investment, and holdings that don't all move together.")
    grade_note = late_start_note(returns_3y, tickers, grade_daily, history.window_start(returns, GRADE_YEARS), "so the grade only covers that stretch")
    if grade_note:
        st.caption(f"Based on prices from {history.date_range_text(grade_daily)}{grade_note}.")
    else:
        st.caption(f"Based on the last {GRADE_YEARS} years of prices ({history.date_range_text(grade_daily)}).")
    if st.session_state.get("fund_info"):
        st.caption("Looked inside your funds: " + "; ".join(funds.describe(t, e) for t, e in st.session_state.fund_info.items()) + ".")

    report_slot = st.empty()

    st.markdown("**Five ways to be spread out**")
    for dim in advice["dimensions"]:
        name_col, text_col = st.columns([1, 3])
        name_col.markdown(f"{dim['name']}  \n{LEVEL_MARK[dim['level']]}")
        text_col.write(dim["text"])
    with st.expander("What does “real bets” mean?"):
        st.write(
            "Real bets estimates how many genuinely separate sources of risk your money has. If several holdings usually rise and fall "
            "together, they count as fewer independent bets — so six tech stocks may behave more like two. A broad fund counts as several, "
            "because it holds many companies — though fewer than you might expect, since companies in the same fund tend to move together. It is this app's own measure, built from two standard ones: how evenly your money is spread, "
            "and how closely your holdings' daily moves have matched over the last 3 years."
        )

    st.divider()
    st.subheader("What stands out")
    st.caption("Ordered by how much they matter. Red = needs attention, yellow = worth knowing, green = already working.")
    for tip in advice["tips"]:
        with st.container(border=True):
            LEVEL_BOX[tip["level"]](f"**{tip['title']}**")
            st.write(f"**Why it matters:** {tip['why']}")
            st.write(f"**What would help:** {tip['action']}")

    st.divider()
    st.subheader("What-if scenarios")
    st.info("These are hypothetical educational scenarios, not recommendations to buy or sell. They show how historical risk and diversification would have changed under a different mix.")
    swaps = cached_swaps(tuple(sorted(holdings.items())), cash, GRADE_YEARS)
    for i, swap in enumerate(swaps, 1):
        with st.container(border=True):
            head, grade_col = st.columns([4, 1])
            head.caption(f"SCENARIO {i}")
            head.markdown(f"### {swap['text']}")
            head.write(swap["why"])
            grade_col.caption("Grade")
            grade_col.markdown(f"## {swap['before']['grade']} → {swap['after']['grade']}")
            for col, (label, key, fmt, higher_is_better) in zip(st.columns(4), SCENARIO_STATS):
                stat_chip(col, label, swap["before"][key], swap["after"][key], fmt, higher_is_better)
    if not swaps and advice["grade"] in ("A", "B"):
        st.write("No single swap from the tested list would have clearly improved this mix — that's a good sign.")
    elif not swaps:
        st.write("No single swap from the tested list would have clearly improved this mix. The notes above explain what is holding the grade down.")
    st.caption(f"Each scenario swaps part or all of one large holding for one of ten common diversifiers, then re-grades the mix over the last {GRADE_YEARS} years; the three that change the most are shown. Typical yearly swing = how much a normal year moves this mix up or down. Worst drop = the biggest fall from a high point before it recovered. A steadier mix usually earns a bit less per year — that trade-off is the point. Share counts use today's prices and are rounded.")

    st.divider()
    st.subheader("How it has grown")
    st.caption("What $10,000 in this exact mix would be worth today, next to whatever you pick to compare it with.")
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

    your_daily = history.filled_daily(weights, returns_growth)
    bench_daily = history.portfolio_daily(bench_weights, history.window(bench_returns, growth_years))
    both = pd.concat([your_daily.rename("You"), bench_daily.rename(bench_name)], axis=1, join="inner")
    if both.empty:
        st.warning(f"You and {bench_name} don't share enough price history to compare.")
    else:
        st.altair_chart(compare_chart(both.apply(history.growth_of), "line", "Value of $10,000", "$,.0f", 300, zero=False), use_container_width=True)
        yours, bench = history.summary(both["You"]), history.summary(both[bench_name])
        st.markdown(f"Total return since {both.index[0]:%b %Y}: you **{signed_pct(yours['total_return'])}** · {bench_name} **{signed_pct(bench['total_return'])}**")
        st.markdown(f"Worst drop along the way: you **{pct(yours['max_drawdown'])}** · {bench_name} **{pct(bench['max_drawdown'])}**")
        st.markdown(f"Typical yearly swing: you **{pct(yours['volatility'])}** · {bench_name} **{pct(bench['volatility'])}**")
        st.caption(f"Showing {history.date_range_text(both)}{window_note(returns_growth, tickers, both, history.window_start(returns, growth_years), bench=(bench_name, bench_daily.index[0]))}.")

        if swaps:
            st.markdown("**See a scenario play out**")
            move = st.selectbox("Scenario to replay", [s["text"] for s in swaps], label_visibility="collapsed", key="whatif_move")
            swap = next(s for s in swaps if s["text"] == move)
            after_holdings = dict(holdings)
            after_holdings[swap["sell_ticker"]] = after_holdings[swap["sell_ticker"]] - swap["sell_shares"]
            if after_holdings[swap["sell_ticker"]] <= 0:
                del after_holdings[swap["sell_ticker"]]
            after_holdings[swap["buy_ticker"]] = after_holdings.get(swap["buy_ticker"], 0) + swap["buy_shares"]
            after_weights, _ = holdings_to_weights(after_holdings, prices)
            after_daily = history.filled_daily(after_weights, returns_growth)
            trio = pd.concat([your_daily.rename("You now"), after_daily.rename("In the scenario"), bench_daily.rename(bench_name)], axis=1, join="inner")
            st.altair_chart(compare_chart(trio.apply(history.growth_of), "line", "Value of $10,000", "$,.0f", 300, zero=False, colors=[YOU_COLOR, AFTER_COLOR, BENCH_COLOR]), use_container_width=True)
            now, after = history.summary(trio["You now"]), history.summary(trio["In the scenario"])
            st.markdown(f"Total return since {trio.index[0]:%b %Y}: now **{signed_pct(now['total_return'])}** · in the scenario **{signed_pct(after['total_return'])}**")
            st.markdown(f"Worst drop along the way: now **{pct(now['max_drawdown'])}** · in the scenario **{pct(after['max_drawdown'])}**")
            st.markdown(f"Typical yearly swing: now **{pct(now['volatility'])}** · in the scenario **{pct(after['volatility'])}**")
            st.caption("Past prices, not a prediction — this is how the scenario's mix would have behaved over the same stretch.")

    st.divider()
    st.subheader("How it would have held up in past crashes")
    st.caption("What this exact mix would have done, compared with the S&P 500.")
    crashes = [
        ("2022 downturn", "2022-01-03", "2022-10-13"),
        ("COVID crash, 2020", "2020-02-19", "2020-03-23"),
        ("Late-2018 drop", "2018-10-01", "2018-12-24"),
    ]
    worse_count = 0
    compared = 0
    crash_rows = []
    all_daily = history.filled_daily(weights, returns)
    cols = st.columns(3, gap="medium")
    for col, (name, start, end) in zip(cols, crashes):
        window = all_daily.loc[start:end]
        yours = {"total_return": history.total_return(window)} if len(window) and all_daily.index[0] <= pd.Timestamp(start) else None
        absent = [t for t in tickers if returns[t].first_valid_index() is None or returns[t].first_valid_index() > pd.Timestamp(start)]
        spy = engine.crash_test({"SPY": 1.0}, returns[["SPY"]], start, end)
        crash_rows.append({
            "name": name, "dates": history.short_range_text(start, end),
            "you": pct(yours["total_return"]) if yours else "not enough history",
            "spy": pct(spy["total_return"]) if spy else "n/a",
        })
        with col:
            with st.container(border=True):
                st.markdown(f"**{name}**")
                st.caption(history.short_range_text(start, end))
                if yours is None:
                    st.caption("Not enough history — most of your money is in holdings that didn't exist yet.")
                else:
                    st.markdown(f"You: **{pct(yours['total_return'])}**")
                    if spy is not None:
                        st.markdown(f"S&P 500: **{pct(spy['total_return'])}**")
                        compared += 1
                        if yours["total_return"] < spy["total_return"]:
                            worse_count += 1
                            st.caption("Fell harder than the market")
                        else:
                            st.caption("Held up better than the market")
                    if absent:
                        st.caption(f"Without {', '.join(absent)}, which didn't exist yet.")
    if compared:
        if worse_count == 0:
            st.success(f"This mix would have dropped **less** than the market in every crash we could check ({compared} of {compared}).")
        elif worse_count == compared:
            st.warning(f"This mix would have dropped **more** than the market in every crash we could check ({compared} of {compared}). The what-if scenarios above show what would have softened that.")
        else:
            st.info(f"This mix would have dropped more than the market in {worse_count} of the {compared} crashes we could check.")

    st.divider()
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
    chart = alt.Chart(monthly_df).mark_bar().encode(
        x=alt.X("Month:T", title=None),
        y=alt.Y("Return:Q", title="Monthly change", axis=alt.Axis(format="%")),
        color=alt.Color("Direction:N", scale=alt.Scale(domain=["Up", "Down"], range=["#2ecc71", "#e74c3c"]), legend=None),
        tooltip=[alt.Tooltip("Month:T", title="Month", format="%b %Y"), alt.Tooltip("Return:Q", title="Change", format=".1%")]
    ).properties(height=240)
    st.altair_chart(chart, use_container_width=True)
    st.caption(f"Showing {history.date_range_text(steady_daily)}{window_note(returns_steady, tickers, steady_daily, history.window_start(returns, steady_years))}.")

    st.divider()
    st.subheader("Where your money really is")
    st.caption("As of today's prices.")
    left, right = st.columns(2)
    with left:
        st.write("**By type of investment**")
        rows = regions.asset_mix(weights_with_cash)
        st.altair_chart(donut(rows, "asset", "Type", [ASSET_COLORS.get(r["asset"], SLICE_COLORS[-1]) for r in rows]), use_container_width=True)
        st.caption(" · ".join(f"{r['asset']} {r['pct']:.0f}%" for r in rows))
    with right:
        st.write("**By country**")
        rows = regions.country_mix(weights_with_cash)
        st.altair_chart(donut(rows, "country", "Country", SLICE_COLORS[:len(rows)]), use_container_width=True)
        st.caption(" · ".join(f"{r['country']} {r['pct']:.0f}%" for r in rows))
    left, right = st.columns(2)
    with left:
        st.write("**By holding** — share of everything you own, including cash")
        for t, w in sorted(facts["total_weights"].items(), key=lambda kv: -kv[1]):
            st.write(f"{t} — {pct(w)}")
            st.progress(min(1.0, max(0.0, w)))
        if facts["cash_share"] > 0:
            st.write(f"Cash — {pct(facts['cash_share'])}")
            st.progress(min(1.0, max(0.0, facts["cash_share"])))
    with right:
        st.write("**By industry** — share of your invested money, with the S&P 500 for comparison")
        if facts["sectors"]:
            for row in facts["sectors"]:
                st.write(f"{row['sector']} — {row['pct']:.0f}% (S&P 500: {row['sp']:.0f}%)")
                st.progress(min(1.0, max(0.0, row["pct"] / 100)))
        else:
            st.info("None of your holdings are individual stocks or stock funds, so there's no industry split to show.")
        if facts["non_eq"] > 0.005:
            st.caption(f"Bonds, gold, or other non-stock funds: {pct(facts['non_eq'])} of your invested money.")

    st.divider()
    with st.expander("Learn the ideas — a 5-minute read"):
        st.write("#### Owning more stocks isn't the same as being spread out")
        st.write("Owning 20 different tickers *feels* diversified because it's a big number. But if all 20 are large tech companies, they'll rise and fall together in a downturn — you're really making one big bet (\"tech will do well\") spread across 20 names. That's what **real bets** measures: how many genuinely separate bets you're making, not how many tickers are on the list.")

        st.write("#### \"Moving together\" is about timing, not what a company does")
        st.write("Two holdings move together when they tend to go up and down on the same days. AAPL and MSFT do, because the same tech-sector news hits both. An airline and an oil company can too, for the opposite reason: oil is the airline's biggest cost, so when oil moves, both react at once. The number that captures this is called correlation — 1 means always together, 0 means unrelated.")

        st.write("#### Crashes are when 'spread out' matters most — and when it quietly fails")
        st.write("In calm markets, different industries move somewhat independently. In a real crash, almost everything sells off together, because the cause (panic, forced selling) hits everything at once. Holdings you thought were unrelated turn out to be related right when it matters. That's why a **safety net** — something like bonds or gold that genuinely behaves differently — is worth more than it looks on a normal day.")

        st.write("#### A simple structure many people use")
        core_satellite = {
            "Core — broad index funds like VTI or SPY": 55,
            "Satellites — individual stocks you believe in": 20,
            "Safety net — bonds, gold, things that move differently": 20,
            "Cash — a cushion for real life": 5,
        }
        for label, share in core_satellite.items():
            st.write(f"**{label}** — about {share}%")
            st.progress(share / 100)

    with st.expander("How this works — data, method and limits"):
        for heading, body in METHOD:
            st.write(f"**{heading}** {body}")

    spy_daily = history.portfolio_daily({"SPY": 1.0}, returns_3y[["SPY"]])
    pair = pd.concat([grade_daily.rename("you"), spy_daily.rename("spy")], axis=1, join="inner")
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
            "performance": [
                ("Total return", signed_pct(mine["total_return"]), signed_pct(market["total_return"])),
                ("Return per year", pct(mine["annual_return"]), pct(market["annual_return"])),
                ("Typical yearly swing", pct(mine["volatility"]), pct(market["volatility"])),
                ("Worst drop", pct(mine["max_drawdown"]), pct(market["max_drawdown"])),
            ],
            "performance_range": history.date_range_text(pair),
            "steady": f"{int((steady_3y > 0).sum())} of {len(steady_3y)} months ended positive",
            "crashes": crash_rows, "scenarios": swaps, "method": METHOD,
        }),
        file_name="portfolio-check-up.html", mime="text/html",
        help="Opens in any browser. Use the browser's Print to save it as a PDF.",
    )

    st.caption("Educational tool only — not financial advice. Prices from Yahoo Finance. Want every detail? The full Portfolio Analyzer has 12 sections covering the same portfolio.")
