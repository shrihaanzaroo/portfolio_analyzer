import pandas as pd
import altair as alt
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
import engine
import tips

st.set_page_config(page_title="Portfolio Check-Up", page_icon="🩺", layout="wide")
cached_download = st.cache_data(show_spinner="Downloading price history...")(engine.download_prices)

LEVEL_BOX = {"high": st.error, "medium": st.warning, "good": st.success}


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

st.sidebar.header("What you own")
holdings_df = st.sidebar.data_editor(
    st.session_state.holdings_df,
    num_rows="dynamic",
    column_config={
        "Ticker": st.column_config.TextColumn("Ticker"),
        "Shares": st.column_config.NumberColumn("Shares", min_value=0, step=1),
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

st.sidebar.divider()
years = st.sidebar.slider("Years of history to look at", min_value=1, max_value=25, value=3, help="More years give steadier numbers, but newer companies won't have that much history.")
period = f"{years}y"

if st.sidebar.button("Analyze", type="primary", use_container_width=True):
    st.session_state.holdings_df = holdings_df
    st.session_state.cash = cash_input
    holdings = holdings_df_to_dict(holdings_df)
    if not holdings:
        st.error("Add at least one holding before analyzing.")
        st.stop()

    tickers = list(holdings.keys())
    prices = cached_download(list(dict.fromkeys(tickers + ["SPY"])), period)

    missing = [t for t in tickers if prices[t].dropna().empty]
    if missing:
        st.error(f"No price data available for: {', '.join(missing)}. This can happen with a mistyped ticker, or if Yahoo Finance is rate-limiting — try again in a moment.")
        st.stop()

    returns = engine.compute_returns(prices)
    st.session_state.weights, st.session_state.stock_value = holdings_to_weights(holdings, prices)
    st.session_state.returns = returns
    st.session_state.tickers = tickers


st.title("Portfolio Check-Up")
st.caption("A plain-English look at whether your investments are really spread out — and what to do about it.")

if st.session_state.weights is None:
    st.info(
        "**What this does:** you tell it what you own, and it tells you whether those holdings are actually "
        "different from each other — or secretly one big bet — and gives you concrete things to try. "
        "Your holdings live in the **sidebar** (on a phone, tap the **›** arrow at the top-left to open it). "
        "The defaults there are just an example: edit them, then tap **Analyze**."
    )
else:
    weights = st.session_state.weights
    returns = st.session_state.returns
    tickers = st.session_state.tickers
    total_value = st.session_state.stock_value + st.session_state.cash
    invested_share = st.session_state.stock_value / total_value if total_value > 0 else 1.0

    advice = tips.build_tips(weights, returns, invested_share)
    facts = advice["facts"]

    with st.container(border=True):
        g, v = st.columns([1, 4])
        g.metric("Grade", advice["grade"], help="A to F, based on how spread out your money is, how much your holdings move together, and how bumpy the ride is. Discounted if most of your money is sitting in cash.")
        v.markdown(f"#### {advice['verdict']}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Holdings", facts["holdings"], help="How many different tickers you own.")
        m2.metric("Real bets", f"{facts['true_bets']:.1f}", help="How many genuinely separate bets your holdings add up to, once you account for the ones that move together. If this is much lower than your holdings count, they're mostly the same bet.")
        m3.metric("Biggest holding", f"{facts['biggest']} · {facts['biggest_pct']:.0f}%", help="Your largest single position, as a share of everything you own including cash.")

    st.subheader("What to do first")
    st.caption("Ordered by how much they matter. Red = worth fixing, yellow = worth knowing, green = already working.")
    for tip in advice["tips"]:
        with st.container(border=True):
            LEVEL_BOX[tip["level"]](f"**{tip['title']}**")
            st.write(f"**Why it matters:** {tip['why']}")
            st.write(f"**Try this:** {tip['action']}")

    st.subheader("Where your money really is")
    left, right = st.columns(2)
    with left:
        st.write("**By holding** — share of everything you own, including cash")
        for t, w in sorted(facts["total_weights"].items(), key=lambda kv: -kv[1]):
            st.write(f"{t} — {w*100:.0f}%")
            st.progress(min(1.0, max(0.0, w)))
        if facts["cash_share"] > 0:
            st.write(f"Cash — {facts['cash_share']*100:.0f}%")
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
            st.caption(f"Bonds, gold, or other non-stock funds: {facts['non_eq']*100:.0f}% of your invested money.")

    with st.expander("Under the hood — the numbers behind the tips"):
        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Effective bets", f"{facts['effective_bets']:.2f}", help="How many separate positions your portfolio adds up to based on size alone (a fund counts as many). Ignores whether they move together.")
        n2.metric("True bets", f"{facts['true_bets']:.2f}", help="Effective bets, discounted for holdings that move together. The more honest number.")
        n3.metric("Avg correlation", f"{facts['avg_corr']:.2f}" if facts["avg_corr"] is not None else "—", help="On average, how much your holdings move together. 1 = always together, 0 = unrelated, negative = opposite.")
        n4.metric("Swings: you vs. S&P 500", f"{facts['port_vol']*100:.0f}% vs {facts['spy_vol']*100:.0f}%", help="How much each moves in a typical year. Higher = bumpier ride.")

        st.write("**How much each pair of holdings moves together** — 1 = always together, 0 = unrelated")
        corr = engine.correlation_matrix(returns[tickers])
        fig, ax = plt.subplots(figsize=(7, 5))
        sns.heatmap(corr, annot=True, cmap="coolwarm", vmin=-1, vmax=1, fmt=".2f", ax=ax)
        st.pyplot(fig)

        st.write("**How bumpy each holding is** — dashed line is the S&P 500")
        vols = {t: engine.ann_vol(returns[t]) for t in tickers}
        vol_df = pd.DataFrame({"Ticker": list(vols.keys()), "Volatility": list(vols.values())})
        bars = alt.Chart(vol_df).mark_bar().encode(
            x=alt.X("Volatility:Q", title="Typical yearly swing", axis=alt.Axis(format="%")),
            y=alt.Y("Ticker:N", sort="-x", title=None),
            tooltip=[alt.Tooltip("Ticker:N"), alt.Tooltip("Volatility:Q", title="Swing", format=".1%")]
        ).properties(height=max(150, 30 * len(vol_df)))
        spy_line = alt.Chart(pd.DataFrame({"Volatility": [facts["spy_vol"]]})).mark_rule(color="gray", strokeDash=[4, 4]).encode(x="Volatility:Q")
        st.altair_chart(bars + spy_line, use_container_width=True)

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

    st.caption("Educational tool only — not financial advice. Prices from Yahoo Finance. Want every detail? The full Portfolio Analyzer has 12 sections covering the same portfolio.")
