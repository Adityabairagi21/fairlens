"""Visual system and small reusable HTML components for the FairLens UI.

Streamlit's default look is restyled with one CSS block so the app reads
as a single product. Every component that renders user data escapes it
with ``html.escape`` before inserting it into markup.

Design notes
- Editorial headings (serif) over a quiet sans UI; numbers stay in the sans.
- Two data hues only: blue = baseline configuration, orange = alternative.
- Every piece of information is labelled as FACT, CALCULATION, OBSERVATION
  or SCENARIO, always as text so the label never depends on colour.
"""

from __future__ import annotations

from html import escape
from typing import Iterable

import streamlit as st

# --- design tokens ---------------------------------------------------------------------------------
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
BORDER = "#e4e2da"
HAIRLINE = "#efede6"
CANVAS = "#f6f5f1"
SURFACE = "#ffffff"
DATA_BLUE = "#2a78d6"        # baseline configuration (categorical slot 1)
DATA_ORANGE = "#eb6834"      # alternative configuration (categorical slot 2)
DATA_AQUA = "#1baf7a"        # third series (categorical slot 3)
DATA_YELLOW = "#eda100"      # fourth series (stacked components only)
DATA_NEUTRAL = "#c3c2b7"     # context marks
DATA_BLUE_SOFT = "#cde2fb"

STATUS_STYLES: dict[str, tuple[str, str, str]] = {
    # score band: (dot colour, text colour, background)
    "Strong match": ("#0ca30c", "#006300", "#e9f6e9"),
    "Possible match": ("#fab219", "#7a5200", "#fdf4de"),
    "Weak match": ("#d03b3b", "#9f2323", "#fbeaea"),
    "Not screened": ("#b5b3ac", "#52514e", "#f1f0ec"),
}

TAGS: dict[str, str] = {
    "fact": "Fact",
    "calc": "Calculation",
    "obs": "Observation",
    "scenario": "Scenario",
    "note": "Reviewer note",
    "rule": "Rule-based",
    "sim": "Similarity-based",
}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@500;600&display=swap');

html, body, .stApp, .stMarkdown, p, h1, h2, h3, h4, label, button, input, textarea, select, li, td, th {{
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
    font-feature-settings: "cv11", "ss01";
}}
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
.stApp {{ background: {CANVAS}; color: {INK}; }}

#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stToolbar"] {{ display: none; }}

[data-testid="stMainBlockContainer"], .block-container {{
    padding-top: 2.6rem; padding-bottom: 5rem; max-width: 1220px;
}}

/* Sidebar */
[data-testid="stSidebar"] {{ background: #f1f0eb; border-right: 1px solid {BORDER}; }}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: .4rem; }}
[data-testid="stSidebarNav"] a {{ border-radius: 6px; padding: .26rem .6rem; margin: 1px 0; }}
[data-testid="stSidebarNav"] a span {{ font-size: .86rem; color: {INK_2}; font-weight: 500; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: {SURFACE}; box-shadow: 0 0 0 1px {BORDER}; }}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{ color: {INK}; font-weight: 600; }}
[data-testid="stSidebarNav"] a:hover {{ background: #e9e8e2; }}
[data-testid="stNavSectionHeader"] {{ font-size: .68rem !important; letter-spacing: .09em; text-transform: uppercase;
    color: {MUTED} !important; font-weight: 600 !important; margin-top: .9rem; }}
[data-testid="stSidebarNavSeparator"] {{ display: none; }}

/* Typography */
h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -0.015em; }}
[data-testid="stMarkdownContainer"] p {{ color: {INK_2}; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: {MUTED} !important; }}

/* Buttons */
button[kind="primary"], [data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {{
    background: {INK} !important; border: 1px solid {INK} !important; color: #fff !important;
    border-radius: 6px; font-weight: 500; transition: background .15s ease, transform .15s ease;
}}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {{ background: #2b2b2a !important; }}
button[kind="primary"]:active {{ transform: translateY(1px); }}
button[kind="secondary"], [data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stDownloadButton"] button,
[data-testid="stPopover"] button {{
    background: {SURFACE} !important; border: 1px solid {BORDER} !important; color: {INK} !important;
    border-radius: 6px; font-weight: 500; transition: border-color .15s ease, background .15s ease;
}}
button[kind="secondary"]:hover, [data-testid="stBaseButton-secondary"]:hover,
[data-testid="stDownloadButton"] button:hover {{ border-color: #c9c7bf !important; background: #fff !important; }}
[data-testid="stBaseButton-tertiary"] {{ color: {INK_2} !important; }}
button:disabled, button[disabled] {{ opacity: .42; cursor: not-allowed; }}

/* Inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
    border-radius: 6px !important; background: {SURFACE} !important; border-color: {BORDER} !important;
}}
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
[data-testid="stNumberInputContainer"] {{ background: {SURFACE} !important; }}
button p, [data-testid="stWidgetLabel"] button p {{ color: inherit !important; }}
[data-testid="stWidgetLabel"] p {{ font-size: .78rem; font-weight: 500; color: {INK_2}; }}
[data-baseweb="tag"] {{ background: #ecebe5 !important; border-radius: 4px !important; }}
[data-baseweb="tag"] span {{ color: {INK} !important; }}

/* Containers */
[class*="st-key-panel_"] {{ background: {SURFACE}; border-color: {BORDER} !important; border-radius: 8px !important; }}
[data-testid="stExpander"] details {{ border-radius: 8px; border-color: {BORDER}; background: {SURFACE}; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 8px; overflow: hidden; }}
[data-testid="stAlert"] {{ border-radius: 6px; }}
hr {{ border-color: {BORDER} !important; }}

/* ---------- FairLens components ---------- */
.rs-fade {{ animation: rsFade .3s ease both; }}
@keyframes rsFade {{ from {{ opacity: 0; transform: translateY(3px); }} to {{ opacity: 1; transform: none; }} }}
@media (prefers-reduced-motion: reduce) {{ .rs-fade, .rs-bar-fill {{ animation: none !important; }} }}

.rs-page-head {{ margin-bottom: 1.8rem; max-width: 820px; }}
.rs-eyebrow {{ font-family:'JetBrains Mono', ui-monospace, monospace; font-size:.68rem; font-weight:600;
    letter-spacing:.08em; text-transform:uppercase; color:{MUTED}; margin-bottom:.55rem; }}
h1.rs-title, .rs-title {{ font-family:'Instrument Serif', Georgia, serif !important; font-weight:400 !important; font-size: 2.75rem;
    letter-spacing: -0.012em; color: {INK}; margin: 0; line-height:1.06; }}
.rs-title em {{ font-style: italic; color: {INK_2}; }}
.rs-subtitle {{ color: {INK_2}; font-size: .95rem; margin-top: .7rem; line-height:1.55; }}

[data-testid="stMarkdownContainer"] p.rs-section-title {{ font-size:.92rem; font-weight:600; color:{INK}; margin:0 0 .15rem;
    display:flex; align-items:center; gap:.55rem; flex-wrap:wrap; }}
[data-testid="stMarkdownContainer"] p.rs-section-sub {{ font-size:.8rem; color:{MUTED}; margin:0 0 .85rem; line-height:1.5; }}
.fl-h2 {{ font-family:'Instrument Serif', Georgia, serif; font-size:1.65rem; line-height:1.15; color:{INK};
    margin: 1.6rem 0 .25rem; letter-spacing:-.005em; }}
.fl-h2-sub {{ font-size:.85rem; color:{INK_2}; margin:0 0 1rem; max-width: 760px; line-height:1.55; }}

/* Evidence tags: text labels, colour is secondary */
.fl-tag {{ font-family:'JetBrains Mono', ui-monospace, monospace; font-size:.6rem; font-weight:600; letter-spacing:.07em;
    text-transform:uppercase; padding:.12rem .42rem; border-radius:3px; border:1px solid; white-space:nowrap;
    line-height:1.3; vertical-align: middle; }}
.fl-tag-fact {{ color:{INK_2}; border-color:#d9d7cf; background:#f3f2ed; }}
.fl-tag-calc {{ color:#1c5cab; border-color:#b7d3f6; background:#eef5fd; }}
.fl-tag-obs {{ color:#7a4a00; border-color:#f2d59a; background:#fdf6e6; }}
.fl-tag-scenario {{ color:#4a3aa7; border-color:#cfc9f2; background:#f3f1fd; }}
.fl-tag-note {{ color:{INK}; border-color:{INK}; background:transparent; }}
.fl-tag-rule {{ color:#0d6b4b; border-color:#9fd9c2; background:#e3f5ee; }}
.fl-tag-sim {{ color:#8f3510; border-color:#f0b393; background:#fbe3d6; border-style:dashed; }}

/* Metric strip: one hairline panel, cells divided by rules */
.fl-metrics {{ display:grid; grid-template-columns: repeat(var(--n, 4), minmax(0, 1fr)); background:{SURFACE};
    border:1px solid {BORDER}; border-radius:8px; overflow:hidden; }}
.fl-metric {{ padding: 1rem 1.15rem 1rem; border-left:1px solid {HAIRLINE}; min-width:0; }}
.fl-metric:first-child {{ border-left:none; }}
.fl-metric-label {{ font-size:.74rem; color:{INK_2}; font-weight:500; }}
.fl-metric-value {{ font-size:1.85rem; font-weight:600; letter-spacing:-.03em; color:{INK}; margin-top:.35rem; line-height:1.05; }}
.fl-metric-value small {{ font-size:.95rem; color:{MUTED}; font-weight:500; margin-left:.12rem; letter-spacing:0; }}
.fl-metric-note {{ font-size:.72rem; color:{MUTED}; margin-top:.4rem; line-height:1.4; }}
.fl-metric.accent .fl-metric-value {{ color:#b8481c; }}

/* Why X%? breakdown */
.fl-why {{ font-size:.84rem; }}
.fl-why-row {{ display:grid; grid-template-columns: 8.2rem 1fr 4.6rem 4.4rem; align-items:center; gap:.75rem;
    padding:.5rem 0; border-top:1px solid {HAIRLINE}; }}
.fl-why-row:first-child {{ border-top:none; }}
.fl-why-row.head {{ font-size:.66rem; color:{MUTED}; text-transform:uppercase; letter-spacing:.07em; font-weight:600; padding-bottom:.3rem; }}
.fl-why-row.total {{ border-top:1px solid {INK}; font-weight:600; color:{INK}; }}
.fl-why-row.zero {{ color:{MUTED}; }}
.fl-why-label {{ color:{INK}; font-weight:500; }}
.fl-why-label small {{ display:block; color:{MUTED}; font-weight:400; font-size:.7rem; }}
.fl-why-num {{ text-align:right; font-variant-numeric: tabular-nums; color:{INK}; }}
.fl-why-num small {{ color:{MUTED}; }}
.fl-points {{ height:8px; background:#eeede7; border-radius:2px; position:relative; overflow:hidden; }}
.fl-points i {{ position:absolute; left:0; top:0; bottom:0; border-radius:2px; }}

.fl-score {{ display:flex; align-items:baseline; gap:.6rem; flex-wrap:wrap; }}
.fl-score-num {{ font-size:3.1rem; font-weight:600; letter-spacing:-.045em; line-height:1; color:{INK}; }}
.fl-score-num span {{ font-size:1.35rem; color:{MUTED}; font-weight:500; margin-left:.08rem; }}
.fl-score-meta {{ font-size:.8rem; color:{INK_2}; }}
.fl-key {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:.4rem; vertical-align:baseline; }}
.fl-delta {{ font-weight:600; font-variant-numeric: tabular-nums; }}

/* Observation card */
.fl-obs {{ border:1px solid {BORDER}; border-left:3px solid #e0a526; background:{SURFACE}; border-radius:6px;
    padding:.75rem .95rem .8rem; margin-bottom:.6rem; }}
.fl-obs.kind-sensitivity {{ border-left-color:{DATA_BLUE}; }}
.fl-obs.kind-ranking {{ border-left-color:{DATA_ORANGE}; }}
.fl-obs.kind-evidence {{ border-left-color:{DATA_NEUTRAL}; }}
.fl-obs-head {{ display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }}
.fl-obs-title {{ font-size:.86rem; font-weight:600; color:{INK}; }}
.fl-obs-who {{ font-size:.76rem; color:{MUTED}; flex-basis:100%; }}
.fl-obs-text {{ font-size:.84rem; color:{INK_2}; line-height:1.55; margin-top:.3rem; }}

/* Required-skill evidence grid */
.fl-evidence {{ width:100%; border-collapse:collapse; font-size:.84rem; }}
.fl-evidence th {{ text-align:left; font-size:.66rem; color:{MUTED}; text-transform:uppercase; letter-spacing:.07em;
    font-weight:600; padding:0 0 .4rem; border-bottom:1px solid {BORDER}; }}
.fl-evidence th.c, .fl-evidence td.c {{ text-align:center; width:5.2rem; }}
.fl-evidence td {{ padding:.42rem 0; border-bottom:1px solid {HAIRLINE}; color:{INK}; }}
.fl-yes {{ color:#006300; font-weight:600; }}
.fl-no {{ color:#b8b6ae; }}

.fl-project {{ padding:.65rem 0; border-top:1px solid {HAIRLINE}; }}
.fl-project:first-child {{ border-top:none; padding-top:.1rem; }}
.fl-project-title {{ font-size:.88rem; font-weight:600; color:{INK}; }}
.fl-project-sum {{ font-size:.8rem; color:{INK_2}; margin:.15rem 0 .45rem; }}

.fl-scen {{ display:grid; grid-template-columns: 1fr 4rem 4.2rem; gap:.6rem; padding:.45rem 0;
    border-top:1px solid {HAIRLINE}; font-size:.84rem; align-items:center; }}
.fl-scen:first-child {{ border-top:none; }}
.fl-scen .n {{ text-align:right; font-variant-numeric: tabular-nums; color:{INK}; }}

.fl-callout {{ background:#f3f2ed; border-radius:6px; padding:.75rem .95rem; font-size:.82rem; color:{INK_2}; line-height:1.55; }}
.fl-callout b {{ color:{INK}; }}

/* Competence audit */
.fl-status {{ font-family:'JetBrains Mono', ui-monospace, monospace; font-size:.62rem; font-weight:600; letter-spacing:.06em;
    padding:.14rem .45rem; border-radius:3px; white-space:nowrap; display:inline-block; min-width:5.6rem; text-align:center; }}
.fl-status-EXPLICIT {{ background:{DATA_BLUE}; color:#fff; }}
.fl-status-SUPPORTED {{ background:#e3f5ee; color:#0d6b4b; box-shadow:inset 0 0 0 1px #9fd9c2; }}
.fl-status-RELATED {{ background:#fdf3e1; color:#7a4a00; box-shadow:inset 0 0 0 1px #f0cf8f; }}
.fl-status-MISSING {{ background:transparent; color:{MUTED}; box-shadow:inset 0 0 0 1px #d4d2c9; }}

.fl-scorecard {{ border:1px solid {INK}; border-radius:8px; background:{SURFACE}; overflow:hidden; }}
.fl-scorecard-head {{ display:flex; justify-content:space-between; align-items:center; padding:.7rem 1rem;
    background:{INK}; color:#fff; font-family:'JetBrains Mono', ui-monospace, monospace; font-size:.68rem;
    letter-spacing:.1em; font-weight:600; }}
.fl-scorecard-row {{ display:grid; grid-template-columns: 1fr 5.6rem 38%; gap:.8rem; align-items:center;
    padding:.62rem 1rem; border-top:1px solid {HAIRLINE}; }}
.fl-scorecard-row:first-of-type {{ border-top:none; }}
.fl-scorecard-row .k {{ font-size:.84rem; color:{INK}; font-weight:500; }}
.fl-scorecard-row .k small {{ display:block; color:{MUTED}; font-weight:400; font-size:.7rem; }}
.fl-scorecard-row .v {{ font-size:1.35rem; font-weight:600; letter-spacing:-.02em; text-align:right; color:{INK}; }}
.fl-scorecard-signal {{ padding:.85rem 1rem; border-top:1px solid {BORDER}; background:#f7f6f1; }}
.fl-signal {{ display:inline-block; font-family:'JetBrains Mono', ui-monospace, monospace; font-weight:600; font-size:.72rem;
    letter-spacing:.08em; text-transform:uppercase; padding:.2rem .55rem; border-radius:3px; }}
.fl-signal-review {{ background:#fbe3d6; color:#8f3510; box-shadow:inset 0 0 0 1px #f0b393; }}
.fl-signal-partial {{ background:#fdf3e1; color:#7a4a00; box-shadow:inset 0 0 0 1px #f0cf8f; }}
.fl-signal-consistent {{ background:#eef5fd; color:#1c5cab; box-shadow:inset 0 0 0 1px #b7d3f6; }}
.fl-signal-limited {{ background:#f1f0ec; color:{INK_2}; box-shadow:inset 0 0 0 1px #d4d2c9; }}

.fl-miss {{ display:grid; grid-template-columns: 1fr 1.3rem 1fr 1.3rem 1fr; align-items:stretch; gap:.4rem; }}
.fl-miss-col {{ border:1px solid {BORDER}; border-radius:8px; background:{SURFACE}; padding:.85rem .9rem; }}
.fl-miss-col.missed {{ border-top:3px solid {DATA_ORANGE}; }}
.fl-miss-col.recovered {{ border-top:3px solid {DATA_AQUA}; }}
.fl-miss-col.unsupported {{ border-top:3px solid {DATA_NEUTRAL}; }}
.fl-miss-n {{ font-size:2rem; font-weight:600; letter-spacing:-.03em; line-height:1; color:{INK}; }}
.fl-miss-label {{ font-size:.78rem; font-weight:600; color:{INK}; margin:.35rem 0 .15rem; }}
.fl-miss-sub {{ font-size:.72rem; color:{MUTED}; margin-bottom:.6rem; line-height:1.4; }}
.fl-miss-arrow {{ display:grid; place-items:center; color:{MUTED}; font-size:1.1rem; }}
.fl-miss-item {{ font-size:.8rem; color:{INK}; padding:.3rem 0; border-top:1px solid {HAIRLINE}; }}
.fl-miss-item small {{ display:block; color:{MUTED}; font-size:.7rem; line-height:1.35; }}

.fl-ev {{ width:100%; border-collapse:collapse; font-size:.83rem; }}
.fl-ev th {{ text-align:left; font-size:.64rem; color:{MUTED}; text-transform:uppercase; letter-spacing:.07em;
    font-weight:600; padding:0 .4rem .45rem 0; border-bottom:1px solid {BORDER}; }}
.fl-ev td {{ padding:.5rem .4rem .5rem 0; border-bottom:1px solid {HAIRLINE}; vertical-align:top; color:{INK}; }}
.fl-ev td.src {{ color:{INK_2}; font-size:.78rem; line-height:1.45; }}

.fl-trail {{ position:relative; padding-left:1.5rem; }}
.fl-trail::before {{ content:""; position:absolute; left:.42rem; top:.4rem; bottom:.4rem; width:1px; background:{BORDER}; }}
.fl-step {{ position:relative; padding:.1rem 0 1rem; }}
.fl-step::before {{ content:attr(data-n); position:absolute; left:-1.5rem; top:0; width:.9rem; height:.9rem; border-radius:50%;
    background:{INK}; color:#fff; font-size:.55rem; display:grid; place-items:center; font-weight:600; }}
.fl-step-title {{ font-size:.82rem; font-weight:600; color:{INK}; }}
.fl-step-body {{ font-size:.8rem; color:{INK_2}; margin-top:.25rem; line-height:1.55; }}

@media (max-width: 760px) {{
    .fl-miss {{ grid-template-columns: 1fr; }}
    .fl-miss-arrow {{ transform: rotate(90deg); height:1rem; }}
    .fl-scorecard-row {{ grid-template-columns: 1fr 4.6rem; }}
    .fl-scorecard-row .bar {{ grid-column: 1 / -1; }}
}}

/* Older primitives, still used across pages */
.rs-stat {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px; padding:1rem 1.1rem .95rem; height:100%; }}
.rs-stat-label {{ font-size:.76rem; color:{INK_2}; font-weight:500; }}
.rs-stat-value {{ font-size:1.8rem; font-weight:600; letter-spacing:-.03em; color:{INK}; margin-top:.3rem; line-height:1.1; }}
.rs-stat-value small {{ font-size:.95rem; color:{MUTED}; font-weight:500; margin-left:.15rem; }}
.rs-stat-note {{ font-size:.74rem; color:{MUTED}; margin-top:.35rem; }}

.rs-badge {{ display:inline-flex; align-items:center; gap:.38rem; font-size:.72rem; font-weight:550;
    padding:.14rem .5rem .14rem .45rem; border-radius:999px; white-space:nowrap; }}
.rs-badge i {{ width:6px; height:6px; border-radius:50%; display:inline-block; }}

.rs-chips {{ display:flex; flex-wrap:wrap; gap:.3rem; }}
.rs-chip {{ font-size:.76rem; padding:.16rem .5rem; border-radius:4px; border:1px solid {BORDER};
    background:#f7f6f2; color:{INK}; white-space:nowrap; }}
.rs-chip.ok {{ border-color:#cfe8cf; background:#f3faf3; }}
.rs-chip.ok::before {{ content:"✓"; color:#0a7d0a; margin-right:.3rem; font-weight:700; }}
.rs-chip.miss {{ border-color:#f1d0d0; background:#fdf6f6; }}
.rs-chip.miss::before {{ content:"✕"; color:#b42f2f; margin-right:.3rem; font-weight:700; font-size:.68rem; }}
.rs-chip.req {{ border-color:#b7d3f6; background:#eef5fd; }}
.rs-chip.extra {{ color:{INK_2}; }}
.rs-none {{ font-size:.8rem; color:{MUTED}; }}

.rs-row {{ display:flex; align-items:center; gap:.8rem; padding:.6rem 0; border-top:1px solid {HAIRLINE}; }}
.rs-row:first-child {{ border-top:none; }}
.rs-avatar {{ width:30px; height:30px; flex:none; border-radius:50%; background:#ecebe5; color:{INK_2};
    display:grid; place-items:center; font-size:.7rem; font-weight:600; }}
.rs-row-main {{ flex:1; min-width:0; }}
.rs-row-title {{ font-size:.86rem; font-weight:550; color:{INK}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.rs-row-sub {{ font-size:.75rem; color:{MUTED}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.rs-row-meta {{ font-size:.8rem; color:{INK_2}; font-variant-numeric: tabular-nums; white-space:nowrap; }}

.rs-bar {{ height:6px; background:#eeede7; border-radius:3px; overflow:hidden; }}
.rs-bar-fill {{ height:100%; background:{DATA_BLUE}; border-radius:3px; transform-origin:left;
    animation: rsGrow .6s cubic-bezier(.2,.7,.2,1) both; }}
@keyframes rsGrow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}

.rs-kicker {{ font-family:'JetBrains Mono', ui-monospace, monospace; font-size:.66rem; font-weight:600;
    letter-spacing:.08em; text-transform:uppercase; color:{MUTED}; }}
.rs-explain {{ background:#f3f2ed; border-radius:6px; padding:.75rem .9rem; font-size:.84rem; color:{INK_2}; line-height:1.55; }}
.rs-math {{ font-family:'JetBrains Mono', ui-monospace, monospace; font-size:.74rem; color:{INK_2}; line-height:1.7;
    white-space:pre; overflow-x:auto; }}

[data-testid="stMarkdownContainer"] .rs-kv, .rs-kv {{ display:grid; grid-template-columns: 7.5rem 1fr; gap:.4rem .8rem; font-size:.85rem; margin:0; }}
.rs-kv dt {{ color:{MUTED}; font-size:.84rem; font-weight:400; }}
.rs-kv dd {{ margin:0; color:{INK}; overflow-wrap:anywhere; font-size:.84rem; }}

.rs-empty {{ border:1px dashed #d4d2c9; border-radius:8px; padding:2.2rem 1.2rem; text-align:center; background:{SURFACE}; }}
.rs-empty-title {{ font-weight:600; color:{INK}; font-size:.93rem; }}
.rs-empty-text {{ color:{MUTED}; font-size:.84rem; margin-top:.3rem; }}

.rs-job-meta {{ display:flex; gap:1.1rem; flex-wrap:wrap; font-size:.8rem; color:{INK_2}; margin:.35rem 0 .75rem; }}
.rs-job-meta b {{ color:{INK}; font-weight:600; }}
.rs-mono {{ font-family:'JetBrains Mono', ui-monospace, monospace; font-size:.72rem; color:{MUTED}; }}

@media (max-width: 900px) {{
    .fl-metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .fl-metric {{ border-top:1px solid {HAIRLINE}; }}
    .fl-metric:nth-child(odd) {{ border-left:none; }}
    .fl-metric:nth-child(-n+2) {{ border-top:none; }}
}}
@media (max-width: 640px) {{
    .rs-title {{ font-size:2rem; }}
    .fl-score-num {{ font-size:2.6rem; }}
    .fl-why-row {{ grid-template-columns: 6.4rem 1fr 3.8rem 3.6rem; gap:.5rem; }}
    .rs-kv {{ grid-template-columns: 6.2rem 1fr; }}
    .fl-metric-value {{ font-size:1.5rem; }}
}}
</style>
"""


def panel():
    """A bordered surface panel. Keys are numbered per run so they stay stable across reruns."""
    st.session_state["_panel_n"] = st.session_state.get("_panel_n", 0) + 1
    return st.container(border=True, key=f"panel_{st.session_state['_panel_n']}")


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def tag(kind: str) -> str:
    return f'<span class="fl-tag fl-tag-{kind}">{escape(TAGS[kind])}</span>'


def page_header(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    eyebrow_html = f'<div class="rs-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    sub_html = f'<div class="rs-subtitle">{escape(subtitle)}</div>' if subtitle else ""
    html(f'<div class="rs-page-head rs-fade">{eyebrow_html}<h1 class="rs-title">{escape(title)}</h1>{sub_html}</div>')


def heading(title: str, subtitle: str = "") -> None:
    """A serif section heading that divides a long page into chapters."""
    sub = f'<p class="fl-h2-sub">{escape(subtitle)}</p>' if subtitle else ""
    html(f'<div class="fl-h2">{escape(title)}</div>{sub}')


def section_title(title: str, subtitle: str = "", kind: str | None = None) -> None:
    label = tag(kind) if kind else ""
    sub = f'<p class="rs-section-sub">{escape(subtitle)}</p>' if subtitle else '<div style="height:.6rem"></div>'
    html(f'<p class="rs-section-title">{escape(title)}{label}</p>{sub}')


def metric_strip(items: list[tuple[str, str, str, str]], accent: Iterable[int] = ()) -> None:
    """items: (label, value, unit, note). ``accent`` marks cells that need review."""
    accent = set(accent)
    cells = []
    for i, (label, value, unit, note) in enumerate(items):
        unit_html = f"<small>{escape(unit)}</small>" if unit else ""
        note_html = f'<div class="fl-metric-note">{escape(note)}</div>' if note else ""
        cls = "fl-metric accent" if i in accent else "fl-metric"
        cells.append(f'<div class="{cls}"><div class="fl-metric-label">{escape(label)}</div>'
                     f'<div class="fl-metric-value">{escape(value)}{unit_html}</div>{note_html}</div>')
    html(f'<div class="fl-metrics rs-fade" style="--n:{len(items)}">{"".join(cells)}</div>')


def stat_card(label: str, value: str, note: str = "", unit: str = "") -> str:
    unit_html = f"<small>{escape(unit)}</small>" if unit else ""
    note_html = f'<div class="rs-stat-note">{escape(note)}</div>' if note else ""
    return (
        f'<div class="rs-stat rs-fade"><div class="rs-stat-label">{escape(label)}</div>'
        f'<div class="rs-stat-value">{escape(value)}{unit_html}</div>{note_html}</div>'
    )


def status_badge(status: str) -> str:
    dot, text, bg = STATUS_STYLES.get(status, STATUS_STYLES["Not screened"])
    return (
        f'<span class="rs-badge" style="color:{text};background:{bg}">'
        f'<i style="background:{dot}"></i>{escape(status)}</span>'
    )


def chips(items: Iterable[str], kind: str = "", empty: str = "None") -> str:
    items = list(items)
    if not items:
        return f'<span class="rs-none">{escape(empty)}</span>'
    inner = "".join(f'<span class="rs-chip {kind}">{escape(item)}</span>' for item in items)
    return f'<div class="rs-chips">{inner}</div>'


def bar(percent: float, color: str = DATA_BLUE) -> str:
    width = max(0.0, min(100.0, percent))
    return f'<div class="rs-bar"><div class="rs-bar-fill" style="width:{width:.1f}%;background:{color}"></div></div>'


def initials(name: str) -> str:
    parts = name.split()
    return escape((parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper())


def person_row(name: str, subtitle: str, meta: str = "", meta_html: str = "") -> str:
    right = meta_html or (f'<div class="rs-row-meta">{escape(meta)}</div>' if meta else "")
    return (
        f'<div class="rs-row"><div class="rs-avatar">{initials(name)}</div>'
        f'<div class="rs-row-main"><div class="rs-row-title">{escape(name)}</div>'
        f'<div class="rs-row-sub">{escape(subtitle)}</div></div>{right}</div>'
    )


def empty_state(title: str, text: str = "") -> None:
    text_html = f'<div class="rs-empty-text">{escape(text)}</div>' if text else ""
    html(f'<div class="rs-empty rs-fade"><div class="rs-empty-title">{escape(title)}</div>{text_html}</div>')


def score_hero(score: float, label: str, color: str, meta: str = "") -> str:
    meta_html = f'<span class="fl-score-meta">{escape(meta)}</span>' if meta else ""
    return (
        f'<div class="rs-kicker"><span class="fl-key" style="background:{color}"></span>{escape(label)}</div>'
        f'<div class="fl-score rs-fade" style="margin-top:.35rem"><div class="fl-score-num">{score:.1f}<span>%</span></div>'
        f'{meta_html}</div>'
    )


def delta(value: float, unit: str = " pts") -> str:
    """A signed change. Direction is shown by the sign, not by colour alone."""
    sign = "+" if value > 0.05 else ("−" if value < -0.05 else "±")
    return f'<span class="fl-delta">{sign}{abs(value):.1f}{escape(unit)}</span>'


def why_breakdown(result, labels: dict[str, str], color: str = DATA_BLUE) -> str:
    """'Why 68%?': each component's percent, weight and points, summing to the score."""
    rows = ['<div class="fl-why-row head"><span>Component</span><span>Points earned of weight</span>'
            '<span style="text-align:right">Earned</span><span style="text-align:right">Weight</span></div>']
    for component, label in labels.items():
        weight = result.weights[component]
        points = result.contributions[component]
        pct = result.components[component]
        fill = (points / weight * 100) if weight else 0
        width = weight  # the track is as wide as the weight, out of 100
        rows.append(
            f'<div class="fl-why-row{" zero" if not weight else ""}">'
            f'<span class="fl-why-label">{escape(label)}<small>{pct:.0f}% of this component</small></span>'
            f'<div class="fl-points" style="width:{max(width, 2):.0f}%"><i style="width:{fill:.1f}%;background:{color}"></i></div>'
            f'<span class="fl-why-num">{points:.1f}</span>'
            f'<span class="fl-why-num"><small>/</small> {weight:g}</span></div>'
        )
    rows.append(f'<div class="fl-why-row total"><span>Total</span><span></span>'
                f'<span class="fl-why-num">{result.final_score:.1f}</span><span class="fl-why-num"><small>/</small> 100</span></div>')
    return f'<div class="fl-why">{"".join(rows)}</div>'


def observation_card(obs, who: str = "") -> str:
    who_html = f'<span class="fl-obs-who">{escape(who)}</span>' if who else ""
    return (
        f'<div class="fl-obs kind-{escape(obs.kind)} rs-fade"><div class="fl-obs-head">{tag("obs")}'
        f'<span class="fl-obs-title">{escape(obs.title)}</span>{who_html}</div>'
        f'<div class="fl-obs-text">{escape(obs.text)}</div></div>'
    )
