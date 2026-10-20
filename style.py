"""How the Check-Up looks: the colors, the page CSS and the small HTML pieces the page is built from.

Everything here has to read well in both light and dark mode, so neutral text and lines use
opacity or a translucent gray instead of a fixed color. The HTML goes through st.markdown, so each
piece is built on one line with no blank lines in it (a blank line would end the HTML block).
"""

from html import escape

# Status colors: mid-tones that hold up on white and on near-black.
LEVEL_COLOR = {"high": "#e5484d", "medium": "#f0a020", "good": "#30a46c"}
LEVEL_LABEL = {"high": "Needs attention", "medium": "Worth knowing", "good": "Working"}
COUNT_LABEL = {"high": "need attention", "medium": "worth knowing", "good": "working"}
GRADE_LEVEL = {"A": "good", "B": "good", "C": "medium", "D": "high", "F": "high"}
SCORE_LETTER = "FDCBA"
RING_RADIUS = 30

BLUE = "#2f7ae5"
GREEN = "#30a46c"
AMBER = "#f0a020"
VIOLET = "#8e4ec6"
RED = "#e5484d"
TEAL = "#12a594"
GRAY = "#8e8e93"

CSS = """<style>
.stMain h1{letter-spacing:-.028em!important;line-height:1.06!important}
.stMain h2,.stMain h3{letter-spacing:-.018em!important;line-height:1.18!important}
.stMain h4{letter-spacing:-.01em!important}
.lead{font-size:1.15rem;line-height:1.45;opacity:.66;max-width:46rem;margin:-.5rem 0 .5rem}
.stButton button,.stDownloadButton button{transition:transform .1s ease-out}
.stButton button:active,.stDownloadButton button:active{transform:scale(.97)}
@media (prefers-reduced-motion:reduce){.stButton button,.stDownloadButton button{transition:none}.stButton button:active,.stDownloadButton button:active{transform:none}}
.dot{display:inline-block;width:.5rem;height:.5rem;border-radius:50%;flex:none}
.eyebrow{font-size:.78rem;font-weight:600;opacity:.6}
.hero{display:flex;gap:1.5rem;align-items:center}
.grade-tile{flex:none;width:6rem;height:6rem;border-radius:1.5rem;display:flex;align-items:center;justify-content:center;font-size:3.6rem;font-weight:700;letter-spacing:-.04em;line-height:1}
.verdict{font-size:1.45rem;font-weight:650;letter-spacing:-.018em;line-height:1.22;margin:.2rem 0 .9rem;text-wrap:balance}
.stats{display:flex;flex-wrap:wrap;gap:.5rem 2.5rem}
.stat-label{font-size:.78rem;font-weight:500;opacity:.6}
.stat-big{font-size:1.4rem;font-weight:600;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
@media (max-width:640px){.hero{flex-direction:column;align-items:flex-start}}
.rings{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:.75rem;margin:.25rem 0 1rem}
.ring-card{background:rgba(128,128,128,.07);border-radius:1rem;padding:1rem .75rem .9rem;text-align:center}
.ring-label{font-weight:600;margin-top:.35rem}
.ring-short{font-size:.85rem;opacity:.62;line-height:1.3;font-variant-numeric:tabular-nums}
.tip-summary{display:flex;flex-wrap:wrap;gap:.25rem 1.25rem;font-size:.9rem;margin:0 0 .75rem}
.tip-summary span,.tip-tag,.delta,.crash-note{display:inline-flex;align-items:center;gap:.45rem}
.tips{border:1px solid rgba(128,128,128,.22);border-radius:1rem;overflow:hidden}
.tip{padding:1rem 1.25rem}
.tip+.tip{border-top:1px solid rgba(128,128,128,.18)}
.tip-tag{font-size:.8rem;font-weight:600;opacity:.72}
.tip-title{font-weight:600;font-size:1.05rem;letter-spacing:-.008em;margin:.3rem 0}
.tip-why{font-size:.92rem;opacity:.68;margin-bottom:.5rem}
.card{border:1px solid rgba(128,128,128,.22);border-radius:1rem;padding:1.1rem 1.25rem 1.2rem;margin:0 0 .75rem}
.scn-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}
.scn-title{font-size:1.2rem;font-weight:650;letter-spacing:-.014em;line-height:1.25;margin:.25rem 0 .3rem}
.scn-why{opacity:.72}
.grade-change{flex:none;display:flex;align-items:center;gap:.45rem;font-size:1.3rem;font-weight:650;padding:.3rem .9rem;border-radius:999px;background:rgba(128,128,128,.09)}
.grade-change .arrow{opacity:.4;font-weight:400}
.scn-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:.75rem;margin-top:1rem;padding-top:.9rem;border-top:1px solid rgba(128,128,128,.16)}
@media (max-width:640px){.scn-stats{grid-template-columns:repeat(2,1fr)}}
.stat-value{font-size:1.05rem;font-weight:600;font-variant-numeric:tabular-nums;margin:.1rem 0}
.delta{font-size:.82rem}
.stMain table.cmp{width:100%;max-width:40rem;border-collapse:collapse;border:0;font-size:.95rem;margin:.25rem 0 .75rem}
.stMain table.cmp th,.stMain table.cmp td{border:0;border-bottom:1px solid rgba(128,128,128,.14);padding:.55rem .75rem;text-align:right;font-variant-numeric:tabular-nums;background:none}
.stMain table.cmp th{font-size:.8rem;font-weight:500;opacity:.75;border-bottom-color:rgba(128,128,128,.24)}
.stMain table.cmp th:first-child,.stMain table.cmp td:first-child{text-align:left;padding-left:0}
.stMain table.cmp tr:last-child td{border-bottom:0}
.stMain table.cmp td+td{font-weight:600}
.cmp .dot{margin-right:.4rem}
.crashes{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.75rem;margin:.25rem 0 1rem}
.crash{background:rgba(128,128,128,.07);border-radius:1rem;padding:1rem 1.1rem}
.crash-name{font-weight:600}
.crash-dates{font-size:.82rem;opacity:.6;margin-bottom:.7rem}
.crash-row{display:flex;justify-content:space-between;font-variant-numeric:tabular-nums;padding:.12rem 0}
.crash-row b{font-weight:600}
.crash-note{font-size:.85rem;margin-top:.6rem;opacity:.75}
.panel-title{font-weight:600}
.panel-sub{font-size:.85rem;opacity:.6;margin-bottom:.4rem}
.split{display:flex;gap:2px;height:.75rem;border-radius:999px;overflow:hidden;margin:.6rem 0 .5rem}
.split span{display:block;height:100%;min-width:3px}
.legend-row,.bar-head{display:flex;align-items:center;gap:.55rem;font-size:.95rem}
.legend-row{padding:.45rem 0;border-bottom:1px solid rgba(128,128,128,.12)}
.legend-row:last-child{border-bottom:0}
.pct{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:600}
.ref{font-size:.82rem;font-weight:400;opacity:.55;font-variant-numeric:tabular-nums}
.bar-row{padding:.4rem 0}
.track{position:relative;height:.375rem;border-radius:999px;background:rgba(128,128,128,.16);margin-top:.35rem}
.fill{height:100%;border-radius:999px}
.marker{position:absolute;top:-3px;width:2px;height:calc(100% + 6px);margin-left:-1px;border-radius:1px;background:currentColor;opacity:.5}
</style>"""


def tint(hex_color, alpha):
    """A see-through version of a #rrggbb color, so a tinted surface works on light and dark pages."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def dot(color):
    return f"<span class='dot' style='background:{color}'></span>"


def hero(grade, verdict, stats):
    """The overall grade as a tinted tile, the one-line verdict, and a row of (label, value) figures."""
    color = LEVEL_COLOR[GRADE_LEVEL.get(grade, "medium")]
    figures = "".join(
        f"<div><div class='stat-label'>{escape(label)}</div><div class='stat-big'>{escape(value)}</div></div>"
        for label, value in stats
    )
    return (
        "<div class='hero'>"
        f"<div class='grade-tile' style='color:{color};background:{tint(color, .13)}' aria-label='Grade {grade}'>{escape(grade)}</div>"
        f"<div><div class='eyebrow'>Overall grade</div><div class='verdict'>{escape(verdict)}</div><div class='stats'>{figures}</div></div>"
        "</div>"
    )


def score_rings(dimensions):
    circumference = 2 * 3.14159 * RING_RADIUS
    cards = []
    for d in dimensions:
        color = LEVEL_COLOR[d["level"]]
        filled = max(d["score"], 0.25) / 4 * circumference  # a sliver even at 0, so an empty ring doesn't look broken
        cards.append(
            f"<div class='ring-card' title='{escape(d['text'])}'>"
            "<svg viewBox='0 0 72 72' width='72' height='72'>"
            f"<circle cx='36' cy='36' r='{RING_RADIUS}' fill='none' stroke='rgba(128,128,128,.18)' stroke-width='6'/>"
            f"<circle cx='36' cy='36' r='{RING_RADIUS}' fill='none' stroke='{color}' stroke-width='6' stroke-linecap='round' "
            f"stroke-dasharray='{filled:.1f} {circumference:.1f}' transform='rotate(-90 36 36)'/>"
            f"<text x='36' y='37' text-anchor='middle' dominant-baseline='middle' font-size='22' font-weight='650' fill='currentColor'>{SCORE_LETTER[d['score']]}</text>"
            "</svg>"
            f"<div class='ring-label'>{escape(d['label'])}</div>"
            f"<div class='ring-short'>{escape(d['short'])}</div>"
            "</div>"
        )
    return "<div class='rings'>" + "".join(cards) + "</div>"


def tip_cards(tips_list):
    """A count of each kind of note, then the notes as one grouped list, most important first."""
    counts = [(lvl, sum(t["level"] == lvl for t in tips_list)) for lvl in ("high", "medium", "good")]
    summary = "".join(f"<span>{dot(LEVEL_COLOR[lvl])}{n} {COUNT_LABEL[lvl]}</span>" for lvl, n in counts if n)
    rows = "".join(
        "<div class='tip'>"
        f"<div class='tip-tag'>{dot(LEVEL_COLOR[t['level']])}{LEVEL_LABEL[t['level']]}</div>"
        f"<div class='tip-title'>{escape(t['title'])}</div>"
        f"<div class='tip-why'>{escape(t['why'])}</div>"
        f"<div class='tip-help'><b>What usually changes this:</b> {escape(t['action'])}</div>"
        "</div>"
        for t in tips_list
    )
    return f"<div class='tip-summary'>{summary}</div><div class='tips'>{rows}</div>"


def stat_change(label, before, after, fmt, higher_is_better):
    if fmt(after) == fmt(before):
        verdict, color = "About the same", GRAY
    elif (after > before) == higher_is_better:
        verdict, color = "Better", GREEN
    else:
        verdict, color = "Worse", RED
    return (
        f"<div><div class='stat-label'>{escape(label)}</div>"
        f"<div class='stat-value'>{escape(fmt(before))} → {escape(fmt(after))}</div>"
        f"<div class='delta'>{dot(color)}{verdict}</div></div>"
    )


def scenario_card(number, swap, stats):
    """One what-if swap: what changes, why, the grade before and after, and how each figure moves."""
    kind = f"Scenario {number} · Smaller tweak" if swap.get("tweak") else f"Scenario {number}"
    before, after = swap["before"]["grade"], swap["after"]["grade"]
    after_color = LEVEL_COLOR[GRADE_LEVEL.get(after, "medium")]
    figures = "".join(
        stat_change(label, swap["before"][key], swap["after"][key], fmt, higher)
        for label, key, fmt, higher in stats
    )
    return (
        "<div class='card'><div class='scn-head'>"
        f"<div><div class='eyebrow'>{kind}</div><div class='scn-title'>{escape(swap['text'])}</div>"
        f"<div class='scn-why'>{escape(swap['why'])}</div></div>"
        f"<div class='grade-change' title='Grade before and after'><span>{escape(before)}</span><span class='arrow'>→</span>"
        f"<span style='color:{after_color}'>{escape(after)}</span></div>"
        f"</div><div class='scn-stats'>{figures}</div></div>"
    )


def compare_table(columns, rows):
    """A small figures table. columns: [(name, color)]; rows: [(label, [value per column])]."""
    head = "".join(f"<th>{dot(color)}{escape(name)}</th>" for name, color in columns)
    body = "".join(
        f"<tr><td>{escape(label)}</td>" + "".join(f"<td>{escape(v)}</td>" for v in values) + "</tr>"
        for label, values in rows
    )
    return f"<table class='cmp'><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>"


def crash_cards(cards):
    """cards: dicts with name, dates, rows [(label, value)], and an optional note and note_color."""
    out = []
    for c in cards:
        rows = "".join(f"<div class='crash-row'><span>{escape(k)}</span><b>{escape(v)}</b></div>" for k, v in c["rows"])
        note = ""
        if c.get("note"):
            note = f"<div class='crash-note'>{dot(c['note_color']) if c.get('note_color') else ''}{escape(c['note'])}</div>"
        out.append(
            f"<div class='crash'><div class='crash-name'>{escape(c['name'])}</div>"
            f"<div class='crash-dates'>{escape(c['dates'])}</div>{rows}{note}</div>"
        )
    return "<div class='crashes'>" + "".join(out) + "</div>"


def split_bar(title, rows, colors):
    """A single bar split into shares, with a legend underneath. rows: [(name, percent)]."""
    total = sum(p for _, p in rows) or 1
    segments = "".join(
        f"<span style='flex:{p / total:.4f} 1 0;background:{color}' title='{escape(name)} {p:.0f}%'></span>"
        for (name, p), color in zip(rows, colors) if p > 0
    )
    legend = "".join(
        f"<div class='legend-row'>{dot(color)}<span>{escape(name)}</span><span class='pct'>{p:.0f}%</span></div>"
        for (name, p), color in zip(rows, colors)
    )
    return f"<div class='panel-title'>{escape(title)}</div><div class='split'>{segments}</div>{legend}"


def bar_list(title, subtitle, rows, color=BLUE):
    """One labeled bar per row. rows: [(name, percent, reference percent or None)]; the reference is a tick."""
    items = []
    for name, p, ref in rows:
        marker = f"<span class='marker' style='left:{min(max(ref, 0), 100):.1f}%'></span>" if ref is not None else ""
        ref_text = f"<span class='ref'>S&amp;P 500 {ref:.0f}%</span>" if ref is not None else ""
        items.append(
            f"<div class='bar-row'><div class='bar-head'><span>{escape(name)}</span><span class='pct'>{p:.0f}%</span>{ref_text}</div>"
            f"<div class='track'><div class='fill' style='width:{min(max(p, 0), 100):.1f}%;background:{color}'></div>{marker}</div></div>"
        )
    sub = f"<div class='panel-sub'>{escape(subtitle)}</div>" if subtitle else ""
    return f"<div class='panel-title'>{escape(title)}</div>{sub}" + "".join(items)
