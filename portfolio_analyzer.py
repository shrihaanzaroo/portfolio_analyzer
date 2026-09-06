
from datetime import date
import pandas as pd
import altair as alt
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
import engine

st.set_page_config(page_title="Portfolio Analyzer", layout="wide")
cached_download = st.cache_data(show_spinner="Downloading price history...")(engine.download_prices)

def holdings_df_to_dict(df):
    holdings = {}
    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()
        shares = row["Shares"]
        if not ticker or pd.isna(shares) or shares <= 0:
            continue
        holdings[ticker] = holdings.get(ticker, 0) + int(shares)
    return holdings


def holdings_to_weights(holdings, prices):
    values = {t: float(prices[t].dropna().iloc[-1]) * shares for t, shares in holdings.items()}
    total = sum(values.values())
    return {t: v / total for t, v in values.items()}, total


if "holdings_df" not in st.session_state:
    st.session_state.holdings_df = pd.DataFrame({
        "Ticker": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD"],
        "Shares": [22, 20, 18, 14, 14, 12],
    })

if "weights" not in st.session_state:
    st.session_state.weights = None
if "cash" not in st.session_state:
    st.session_state.cash = 0.0
cash_input = st.sidebar.number_input("Cash ($)", min_value=0.0, value=st.session_state.cash, step=100.0)


st.sidebar.header("Portfolio Holdings")
holdings_df = st.sidebar.data_editor(
    st.session_state.holdings_df,
    num_rows="dynamic",
    column_config={
        "Ticker": st.column_config.TextColumn("Ticker"),
        "Shares": st.column_config.NumberColumn("Shares", min_value=0, step=1),
    },
    hide_index=True,
)

if not holdings_df.empty:
    ticker_to_delete = st.sidebar.selectbox("Remove a holding", holdings_df["Ticker"].tolist())
    if st.sidebar.button("Delete holding"):
        st.session_state.holdings_df = holdings_df[holdings_df["Ticker"] != ticker_to_delete].reset_index(drop=True)
        st.rerun()

tickers_typed = [str(t).strip().upper() for t in holdings_df["Ticker"] if str(t).strip()]
duplicates = {t for t in tickers_typed if tickers_typed.count(t) > 1}
if duplicates:
    st.sidebar.warning(f"Duplicate ticker(s): {', '.join(duplicates)} — shares will be combined.")


years = st.sidebar.slider("Years of history", min_value=1, max_value=25, value=1)

if "hedge_cutoff" not in st.session_state:
    st.session_state.hedge_cutoff = 0.30
if "redundant_cutoff" not in st.session_state:
    st.session_state.redundant_cutoff = 0.75

if st.session_state.get("active_tab") == "Safety nets":
    st.session_state.hedge_cutoff = st.sidebar.slider("Hedge cutoff", 0.1, 0.5, st.session_state.hedge_cutoff)
if st.session_state.get("active_tab") == "Duplicate bets":
    st.session_state.redundant_cutoff = st.sidebar.slider("Redundant cutoff", 0.6, 0.95, st.session_state.redundant_cutoff)

hedge_cutoff = st.session_state.hedge_cutoff
redundant_cutoff = st.session_state.redundant_cutoff



period = f"{years}y"
if st.sidebar.button("Analyze", type="primary"):
    st.session_state.holdings_df = holdings_df
    st.session_state.cash = cash_input
    holdings = holdings_df_to_dict(holdings_df)
    if not holdings:
        st.error("Add at least one holding before analyzing.")
        st.stop()

    tickers = list(holdings.keys())
    prices = cached_download(tickers + ["SPY"], period)

    missing = [t for t in tickers if prices[t].dropna().empty]
    if missing:
        st.error(f"No price data available for: {', '.join(missing)}. This can happen with an invalid ticker, or Yahoo Finance rate-limiting — try again in a moment.")
        st.stop()

    returns = engine.compute_returns(prices)
    st.session_state.weights, st.session_state.stock_value = holdings_to_weights(holdings, prices)
    st.session_state.returns = returns
    st.session_state.tickers = tickers





st.title("Portfolio Analyzer")

if st.session_state.weights is None:
    st.info("Enter holdings in the sidebar and click **Analyze**.")
else:
    weights = st.session_state.weights
    returns = st.session_state.returns
    tickers = st.session_state.tickers

    tb = engine.true_bets(weights, returns)
    eb = engine.effective_bets(weights)
    total_portfolio_value = st.session_state.stock_value + st.session_state.cash
    weights_with_cash = {t: w * st.session_state.stock_value / total_portfolio_value for t, w in weights.items()}
    if st.session_state.cash > 0:
        weights_with_cash["CASH"] = st.session_state.cash / total_portfolio_value
    sec = engine.sector_concentration(weights_with_cash)

    corr = engine.correlation_matrix(returns[tickers])

    tab_names = [
        "Overview", "Position sizes", "Sector mix", "Correlation",
        "Duplicate bets", "Safety nets", "Swings", "Consistency",
        "Crash test", "What if", "Report card", "Learn",
    ]
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = tab_names[0]
    active_tab = st.radio("Section", tab_names, horizontal=True, key="active_tab", label_visibility="collapsed")

    if active_tab == "Overview":
        st.subheader("Overview")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Holdings", len(tickers))
        c2.metric("Effective bets", f"{eb:.2f}")
        c3.metric("True bets", f"{tb['true_bets']:.2f}")
        c4.metric("Avg correlation", f"{tb['avg_corr']:.2f}" if tb["avg_corr"] is not None else "—")

        total_value = st.session_state.stock_value + st.session_state.cash
        cash_pct = st.session_state.cash / total_value if total_value > 0 else 0
        st.write(f"**Cash: {cash_pct*100:.1f}% of portfolio**")
        st.progress(cash_pct)


    elif active_tab == "Position sizes":
        st.subheader("Position sizes")
        c1, c2, c3 = st.columns(3)
        c1.metric("Holdings", len(tickers))
        c2.metric("HHI", f"{1/eb:.3f}")
        c3.metric("Effective bets", f"{eb:.2f}")

    elif active_tab == "Sector mix":
        st.subheader("Sector mix")
        if sec["sectors"]:
            for row in sec["sectors"]:
                pct_of_total = row["pct"] * (1 - sec["non_eq"])
                st.write(f"**{row['sector']}**: {pct_of_total:.1f}% of total portfolio ({row['pct']:.1f}% of equity — S&P 500: {row['sp']:.1f}%)")
        else:
            st.info("No equity sector data for this portfolio.")

        st.caption(f"Non-equity (bonds/gold/cash): {sec['non_eq']*100:.1f}%")

    elif active_tab == "Correlation":
        st.subheader("Correlation")
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.heatmap(corr, annot=True, cmap="coolwarm", vmin=-1, vmax=1, fmt=".2f", ax=ax)
        st.pyplot(fig)

    elif active_tab == "Duplicate bets":
        st.subheader("Duplicate bets")
        rp = engine.redundant_pairs(weights, returns, redundant_cutoff)
        if rp:
            for a, b, c, w in rp:
                st.write(f"**{a}** & **{b}**: correlated {c:.2f}, {w*100:.1f}% of your portfolio overlapping")
        else:
            st.info("No redundant pairs at this cutoff.")

        lt = engine.look_through_overlap_pairs(weights)
        for stock, fund, implied, overlap in lt:
            st.write(f"**{stock}** — you hold it directly, but also get {implied*100:.1f}% of it through **{fund}** ({overlap*100:.1f}% of portfolio overlapping)")

        fo = engine.fund_overlap_pairs(weights)
        for stock, f1, f2, overlap in fo:
            st.write(f"**{stock}** shows up in both **{f1}** and **{f2}** ({overlap*100:.1f}% overlapping)")

    elif active_tab == "Safety nets":
        st.subheader("Safety nets")
        is_hedge, hedge_corr = engine.hedge_detection(weights, returns, hedge_cutoff)
        hedges = [t for t in is_hedge if is_hedge[t]]
        if hedges:
            for t in hedges:
                st.write(f"**{t}**: correlation to the rest of your portfolio is {hedge_corr[t]:.2f}")
        else:
            st.warning("Nothing currently qualifies as a safety net. Bonds, gold, or cash tend to fill this role.")

    elif active_tab == "Swings":
        st.subheader("Swings")
        port_vol = engine.portfolio_vol(weights, returns[tickers])
        spy_vol = engine.ann_vol(returns["SPY"])
        c1, c2 = st.columns(2)
        c1.metric("Your portfolio (annualized)", f"{port_vol*100:.1f}%")
        c2.metric("S&P 500 / SPY (annualized)", f"{spy_vol*100:.1f}%")

        st.write("**Per-holding volatility**")
        vols = {t: engine.ann_vol(returns[t]) for t in tickers}
        for t, v in sorted(vols.items(), key=lambda x: -x[1]):
            st.write(f"**{t}**: {v*100:.1f}%")
    elif active_tab == "Consistency":
        st.subheader("Consistency")
        result = engine.rolling_win_rate(weights, returns[tickers])
        st.metric("Positive gain months", f"{result['win_rate']*100:.0f}%")
        st.dataframe((result["monthly"] * 100).round(1).astype(str) + "%")

        monthly_df = result["monthly"].reset_index()

        monthly_df.columns = ["Month", "Return"]
        monthly_df["Direction"] = monthly_df["Return"].apply(lambda r: "Up" if r >= 0 else "Down")

        chart = alt.Chart(monthly_df).mark_bar().encode(
            x=alt.X("Month:T", title="Month"),
            y=alt.Y("Return:Q", title="Monthly return", axis=alt.Axis(format="%")),
            color=alt.Color("Direction:N",
                            scale=alt.Scale(domain=["Up", "Down"], range=["#2ecc71", "#e74c3c"]),
                            legend=None),
            tooltip=[alt.Tooltip("Month:T", title="Month", format="%b %Y"),
                    alt.Tooltip("Return:Q", title="Return", format=".1%")]
        ).properties(height=300)

        st.altair_chart(chart, use_container_width=True)
    elif active_tab == "Learn":
        st.subheader("Learn")
        st.write("### Correlation measures when, not what")
        st.write("Correlation tells you whether two things tend to move **at the same time** — not whether they're the same *kind* of investment. AAPL and MSFT can be highly correlated because they both react to the same tech-sector news, even though one makes phones and the other makes software. Two totally different industries — like an airline and an oil company — can also be highly correlated, just for the opposite reason: oil is one of the airline's biggest costs, so when oil moves, both tend to move together (in opposite directions). Correlation is about timing, not identity.")

        st.write("### Looking diversified isn't the same as being diversified")
        st.write("Owning 20 different tickers *feels* diversified because it's a big number. But if all 20 are large tech companies, they'll tend to rise and fall together in a downturn — you're really making one big bet (\"tech will do well\") spread across 20 tickers, not 20 independent bets. That's exactly what **effective bets** and **true bets** are built to catch: how many genuinely independent bets you're actually making, not how many tickers are on the list.")

        st.write("### Correlations spike toward 1 during real crashes")
        st.write("In calm markets, different sectors and asset classes often move somewhat independently. In a real crash, correlations tend to jump toward 1 — everything sells off together, because the driving force (panic, forced selling, a liquidity crunch) hits nearly everything at once. This is why diversification that looks solid in normal times can quietly fail exactly when you need it most: holdings you thought were uncorrelated turn out not to be, right when it matters.")

        st.write("### A simple structure: core-satellite investing")
        st.write("One common way to organize a portfolio around these ideas:")
        core_satellite = {
            "Core (broad index funds)": 55,
            "Satellites (individual stock bets)": 20,
            "Hedges (bonds, gold, uncorrelated assets)": 20,
            "Cash": 5,
        }
        for label, pct in core_satellite.items():
            st.write(f"**{label}**: {pct}%")
            st.progress(pct / 100)

    elif active_tab == "Crash test":
        st.subheader("Crash test")
        crash_options = {
            "2022 Bear Market (Jan–Oct 2022)": ("2022-01-03", "2022-10-13"),
            "COVID Crash (Feb–Mar 2020)": ("2020-02-19", "2020-03-23"),
            "2018 Q4 Selloff (Oct–Dec 2018)": ("2018-10-01", "2018-12-24"),
            "Jan–Feb 2016 Selloff (oil/China)": ("2016-01-04", "2016-02-11"),
            "China Black Monday 2015": ("2015-08-17", "2015-08-25"),
            "US Downgrade / Europe Debt Crisis 2011": ("2011-07-22", "2011-10-03"),
            "Global Financial Crisis (2007–2009)": ("2007-10-09", "2009-03-09"),
            "Dot-com Crash (2000–2002)": ("2000-03-24", "2002-10-09"),
            "Black Monday 1987": ("1987-10-14", "1987-10-19"),
        }

        choice = st.selectbox("Historical period", list(crash_options.keys()) + ["Custom range"])
        if choice == "Custom range":
            c1, c2 = st.columns(2)
            start = c1.date_input("Start date", value=date(2020, 1, 1)).isoformat()
            end = c2.date_input("End date", value=date(2020, 12, 31)).isoformat()
        else:
            start, end = crash_options[choice]


        crash_prices = cached_download(tickers + ["SPY"], "max")
        crash_returns = engine.compute_returns(crash_prices)

        result = engine.crash_test(weights, crash_returns[tickers], start, end)
        spy_result = engine.crash_test({"SPY": 1.0}, crash_returns[["SPY"]], start, end)

        if result is None:
            st.warning(
                f"No overlapping price history for {start} to {end}. "
                "This can happen if 'Years of history' is set too low, or if one of your "
                "holdings didn't exist yet during this period (a recent IPO has no data for older crash windows)."
            )
        else:
            c1, c2 = st.columns(2)
            c1.metric("Your portfolio", f"{result['total_return']*100:.1f}%")
            if spy_result:
                c2.metric("S&P 500 (SPY)", f"{spy_result['total_return']*100:.1f}%")

            compare_df = result["path"].rename("Portfolio").to_frame()
            if spy_result:
                compare_df["S&P 500"] = spy_result["path"]
            st.line_chart(compare_df)
    elif active_tab == "What if":
        st.subheader("What if")
        st.write("Swap one holding for another and see how your metrics would change before you actually trade.")

        remove_ticker = st.selectbox("Remove", tickers)
        add_ticker = st.text_input("Add ticker").strip().upper()
        add_shares = st.number_input("Shares to add", min_value=0, value=0, step=1)

        if add_ticker and add_shares > 0:
            new_prices = cached_download([add_ticker], period)
            if new_prices[add_ticker].dropna().empty:
                st.error(f"No price data for {add_ticker}.")
            else:
                new_price = float(new_prices[add_ticker].dropna().iloc[-1])
                new_returns = engine.compute_returns(new_prices)[add_ticker]

                dollar_values = {t: weights[t] * st.session_state.stock_value for t in tickers}
                del dollar_values[remove_ticker]
                dollar_values[add_ticker] = add_shares * new_price
                new_total = sum(dollar_values.values())
                hypo_weights = {t: v / new_total for t, v in dollar_values.items()}

                hypo_returns = returns[[t for t in tickers if t != remove_ticker]].copy()
                hypo_returns[add_ticker] = new_returns

                hypo_eb = engine.effective_bets(hypo_weights)
                hypo_tb = engine.true_bets(hypo_weights, hypo_returns)
                hypo_sec = engine.sector_concentration(hypo_weights)

                c1, c2 = st.columns(2)
                c1.metric("Effective bets (current)", f"{eb:.2f}")
                c2.metric("Effective bets (if swapped)", f"{hypo_eb:.2f}")

                c3, c4 = st.columns(2)
                c3.metric("True bets (current)", f"{tb['true_bets']:.2f}")
                c4.metric("True bets (if swapped)", f"{hypo_tb['true_bets']:.2f}")

                st.write("**Sector mix if swapped**")
                if hypo_sec["sectors"]:
                    for row in hypo_sec["sectors"]:
                        st.write(f"**{row['sector']}**: {row['pct']:.1f}% of equity")
                st.caption(f"Non-equity (if swapped): {hypo_sec['non_eq']*100:.1f}%")
        else:
            st.info("Pick a holding to remove, then enter a ticker and share count to add.")


    elif active_tab == "Report card":
        st.subheader("Report card")
        invested_share = st.session_state.stock_value / (st.session_state.stock_value + st.session_state.cash)
        card = engine.report_card(weights, returns, invested_share)
        if invested_share < 0.75:
            st.warning(f"Only {invested_share*100:.0f}% of your portfolio is actually invested — your overall grade is discounted for this.")


        st.metric("Overall grade", card["overall"])

        descriptions = {
            "Diversification": "How many genuinely different bets your effective bets number represents",
            "Sector balance": "How concentrated your equity is in one sector",
            "Volatility": "Your portfolio's swings compared to the S&P 500",
            "Consistency": "How often your monthly returns have been positive",
            "No duplicate bets": "Whether any holdings are highly correlated with each other",
        }
        for category, grade in card["grades"].items():
            st.write(f"**{category}**: {grade} — {descriptions.get(category, '')}")

