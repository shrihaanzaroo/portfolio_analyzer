from html import escape

LEVEL_LABEL = {"high": "Needs attention", "medium": "Worth knowing", "good": "Working"}
LEVEL_COLOR = {"high": "#b3261e", "medium": "#9a6700", "good": "#1a7f37"}

CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#1f2328;max-width:820px;margin:32px auto;padding:0 24px;line-height:1.5}
h1{margin:0 0 4px;font-size:28px} h2{margin:32px 0 8px;font-size:19px;border-bottom:1px solid #d1d9e0;padding-bottom:4px}
.sub{color:#59636e;font-size:14px;margin:0}
.grade{display:flex;gap:20px;align-items:center;border:1px solid #d1d9e0;border-radius:10px;padding:16px 20px;margin-top:20px}
.letter{font-size:56px;font-weight:700;line-height:1;min-width:56px;text-align:center}
.verdict{font-size:17px;font-weight:600;margin:0 0 4px}
table{border-collapse:collapse;width:100%;font-size:14px} th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #e6eaef;vertical-align:top}
th{color:#59636e;font-weight:600} td.num,th.num{text-align:right;white-space:nowrap}
.tag{font-weight:600;white-space:nowrap} .card{border:1px solid #d1d9e0;border-radius:8px;padding:12px 16px;margin:10px 0;break-inside:avoid}
.card p{margin:4px 0} .small{color:#59636e;font-size:13px} .disclaimer{border-left:4px solid #9a6700;background:#fff8e6;padding:10px 14px;font-size:14px;margin:16px 0}
@media print{body{margin:0;max-width:none} h2{break-after:avoid}}
"""


def pct(x):
    return f"{round(x * 100):.0f}%"


def rows(items, cells):
    return "".join("<tr>" + "".join(cells(i)) + "</tr>" for i in items)


def td(text, cls=""):
    return f'<td class="{cls}">{escape(str(text))}</td>'


def tag(level):
    return f'<td class="tag" style="color:{LEVEL_COLOR[level]}">{LEVEL_LABEL[level]}</td>'


def build_html(d):
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Portfolio Check-Up — {escape(d['date'])}</title><style>{CSS}</style></head><body>"]
    parts.append(f"<h1>Portfolio Check-Up</h1><p class='sub'>{escape(d['date'])} · {escape(d['basis'])}</p>")
    parts.append("<div class='disclaimer'><b>Educational tool — not financial advice.</b> Everything here describes how this mix of holdings behaved in the past. It is not a recommendation to buy or sell anything.</div>")
    parts.append(
        f"<div class='grade'><div class='letter'>{escape(d['grade'])}</div><div><p class='verdict'>{escape(d['verdict'])}</p>"
        f"<p class='sub'>{d['holdings']} holding{'' if d['holdings'] == 1 else 's'} · acting like {d['true_bets']:.1f} real bets · biggest: {escape(d['biggest'])} ({d['biggest_pct']:.0f}% of your money)</p></div></div>"
    )

    parts.append("<h2>Five ways to be spread out</h2><table>")
    parts.append(rows(d["dimensions"], lambda x: [td(x["name"]), tag(x["level"]), td(x["text"])]))
    parts.append("</table>")

    parts.append("<h2>What is holding the grade up or down</h2>")
    for t in d["tips"]:
        parts.append(
            f"<div class='card'><p><span class='tag' style='color:{LEVEL_COLOR[t['level']]}'>{LEVEL_LABEL[t['level']]}</span> — <b>{escape(t['title'])}</b></p>"
            f"<p>{escape(t['why'])}</p><p class='small'>What would help: {escape(t['action'])}</p></div>"
        )

    parts.append("<h2>Where the money is</h2><table><tr><th>Holding</th><th class='num'>Share of everything you own</th></tr>")
    parts.append(rows(d["weights"], lambda x: [td(x[0]), td(pct(x[1]), "num")]))
    parts.append("</table>")
    for title, key, field in (("By type of investment", "assets", "asset"), ("By country", "countries", "country")):
        parts.append(f"<p class='small'><b>{title}:</b> " + escape(" · ".join(f"{r[field]} {r['pct']:.0f}%" for r in d[key])) + "</p>")
    if d["sectors"]:
        parts.append("<table><tr><th>Industry</th><th class='num'>Your stock money</th><th class='num'>S&amp;P 500</th></tr>")
        parts.append(rows(d["sectors"], lambda r: [td(r["sector"]), td(f"{r['pct']:.0f}%", "num"), td(f"{r['sp']:.0f}%", "num")]))
        parts.append("</table>")
    if d["funds"]:
        parts.append("<p class='small'><b>Funds looked inside:</b> " + escape("; ".join(d["funds"])) + "</p>")

    parts.append("<h2>How it has behaved</h2><table><tr><th></th><th class='num'>You</th><th class='num'>S&amp;P 500</th></tr>")
    parts.append(rows(d["performance"], lambda r: [td(r[0]), td(r[1], "num"), td(r[2], "num")]))
    parts.append(f"</table><p class='small'>{escape(d['performance_range'])} · {escape(d['steady'])}</p>")

    parts.append("<h2>Past crashes</h2><table><tr><th>Crash</th><th>Dates</th><th class='num'>You</th><th class='num'>S&amp;P 500</th></tr>")
    parts.append(rows(d["crashes"], lambda c: [td(c["name"]), td(c["dates"]), td(c["you"], "num"), td(c["spy"], "num")]))
    parts.append("</table>")

    parts.append("<h2>What-if scenarios</h2><p class='small'>Hypothetical educational scenarios, not recommendations to buy or sell. They show how risk and diversification would have changed over the last 3 years under a different mix.</p>")
    if not d["scenarios"]:
        parts.append("<p>No single swap from the tested list would have clearly improved this mix.</p>")
    for i, s in enumerate(d["scenarios"], 1):
        b, a = s["before"], s["after"]
        parts.append(
            f"<div class='card'><p><b>Scenario {i}: {escape(s['text'])}</b></p><p class='small'>{escape(s['why'])}</p><table>"
            "<tr><th></th><th class='num'>Now</th><th class='num'>In this scenario</th></tr>"
            + rows([("Grade", b["grade"], a["grade"]), ("Real bets", f"{b['true_bets']:.1f}", f"{a['true_bets']:.1f}"),
                    ("Typical yearly swing", pct(b["volatility"]), pct(a["volatility"])), ("Worst drop", pct(b["max_drawdown"]), pct(a["max_drawdown"])),
                    ("Return per year", pct(b["annual_return"]), pct(a["annual_return"]))],
                   lambda r: [td(r[0]), td(r[1], "num"), td(r[2], "num")])
            + "</table></div>"
        )

    parts.append("<h2>How this works</h2>")
    parts.append("".join(f"<p><b>{escape(h)}</b> {escape(b)}</p>" for h, b in d["method"]))
    parts.append("</body></html>")
    return "".join(parts)
