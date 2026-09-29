"""Altair chart builders with one consistent visual style.

Colour has one job per chart:
- blue   = the baseline configuration (or the only series)
- orange = the alternative configuration, or the "Review" emphasis
- neutral grey = context (ranges, unchanged rows, other candidates)
Every chart with two or more series has a legend, and every mark has a tooltip.
All data comes from the screening engine; nothing here computes a score.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from ui.theme import (
    DATA_AQUA, DATA_BLUE, DATA_NEUTRAL, DATA_ORANGE, DATA_YELLOW, INK, INK_2, MUTED,
)

GRID = "#ebe9e2"
AXIS = "#c3c2b7"
SURFACE_RING = "#ffffff"
FONT = "Inter, Segoe UI, sans-serif"


def _style(chart: alt.Chart, height: int | None) -> alt.Chart:
    if height is not None:
        chart = chart.properties(height=height, width="container")
    return (
        chart
        .configure(font=FONT, background="transparent")
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=INK_2, titleColor=MUTED, labelFontSize=11, titleFontSize=11,
            titleFontWeight=500, gridColor=GRID, domainColor=AXIS, tickColor=AXIS,
            labelPadding=6, titlePadding=10,
        )
        .configure_legend(
            orient="top", direction="horizontal", title=None, labelColor=INK_2, labelFontSize=11,
            symbolSize=80, columnPadding=16, offset=6,
        )
    )


# --- general purpose -----------------------------------------------------------------------------

def vertical_bars(frame: pd.DataFrame, x: str, y: str, x_title: str, y_title: str,
                  height: int = 240, sort: list[str] | None = None) -> alt.Chart:
    """Column chart for ordered buckets (score ranges, experience bands)."""
    base = alt.Chart(frame).encode(
        x=alt.X(f"{x}:N", title=x_title, sort=sort or None, axis=alt.Axis(labelAngle=0, grid=False)),
        y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(tickMinStep=1, grid=True, domain=False, ticks=False)),
        tooltip=[alt.Tooltip(f"{x}:N", title=x_title), alt.Tooltip(f"{y}:Q", title=y_title)],
    )
    bars = base.mark_bar(color=DATA_BLUE, size=22, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
    labels = base.mark_text(dy=-8, color=INK_2, fontSize=11).encode(text=alt.Text(f"{y}:Q"))
    return _style(alt.layer(bars, labels), height)


def horizontal_bars(frame: pd.DataFrame, category: str, value: str, category_title: str,
                    value_title: str, row_height: int = 26, value_format: str = "d",
                    domain_max: float | None = None, color: str = DATA_BLUE) -> alt.Chart:
    """Ranked bar chart. Sorted largest first, one fixed-height row per bar."""
    # Leave room past the longest bar for its value label.
    top = domain_max or float(frame[value].max() or 1) * 1.18
    scale = alt.Scale(domain=[0, top], nice=False) if domain_max is None else alt.Scale(domain=[0, domain_max])
    base = alt.Chart(frame).encode(
        y=alt.Y(f"{category}:N", title=None, sort="-x",
                axis=alt.Axis(grid=False, ticks=False, domain=False, labelLimit=190, labelOverlap=False)),
        x=alt.X(f"{value}:Q", title=value_title, scale=scale,
                axis=alt.Axis(grid=True, tickMinStep=1, domain=False, ticks=False, format="d")),
        tooltip=[alt.Tooltip(f"{category}:N", title=category_title),
                 alt.Tooltip(f"{value}:Q", title=value_title, format=value_format)],
    )
    bars = base.mark_bar(color=color, size=14, cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
    labels = base.mark_text(align="left", dx=5, color=INK_2, fontSize=11).encode(
        text=alt.Text(f"{value}:Q", format=value_format)
    )
    chart = alt.layer(bars, labels).properties(height=alt.Step(row_height), width="container")
    return _style(chart, None)


def experience_vs_score(frame: pd.DataFrame, height: int = 260) -> alt.Chart:
    scored = frame.dropna(subset=["match_score"])[["name", "target_role", "experience_years", "match_score"]]
    points = alt.Chart(scored).mark_circle(size=90, color=DATA_BLUE, opacity=.9, stroke=SURFACE_RING, strokeWidth=2).encode(
        x=alt.X("experience_years:Q", title="Experience (years)", axis=alt.Axis(grid=True, domain=False, ticks=False)),
        y=alt.Y("match_score:Q", title="Baseline score (%)", scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(grid=True, domain=False, ticks=False)),
        tooltip=[
            alt.Tooltip("name:N", title="Candidate"),
            alt.Tooltip("target_role:N", title="Role"),
            alt.Tooltip("experience_years:Q", title="Experience (yrs)"),
            alt.Tooltip("match_score:Q", title="Baseline score", format=".1f"),
        ],
    )
    return _style(points, height)


# --- FairLens views ----------------------------------------------------------------------------------

REVIEW = "Review"
OTHER = "Other candidates"


def coverage_vs_score(frame: pd.DataFrame, review_mask: pd.Series, min_coverage: float, gap: float,
                      height: int = 380) -> alt.Chart:
    """The signature view: skill coverage (x) against the baseline score (y).

    The diagonal is 'score equals coverage'. The shaded wedge holds candidates
    whose coverage is strong but whose score sits well below it.
    """
    data = frame.dropna(subset=["match_score"]).copy()
    data["group"] = [REVIEW if flag else OTHER for flag in review_mask.loc[data.index]]
    data["first_name"] = data["name"].str.split().str[0]
    scale = alt.Scale(domain=[REVIEW, OTHER], range=[DATA_ORANGE, DATA_BLUE])
    axis = dict(grid=True, domain=False, ticks=False, tickCount=5)

    # The review zone: coverage >= min_coverage and score <= coverage - gap.
    zone = pd.DataFrame({"x": [min_coverage, 100], "y": [min_coverage - gap, 100 - gap]})
    wedge = alt.Chart(zone).mark_area(color=DATA_ORANGE, opacity=.08).encode(x="x:Q", y="y:Q", y2=alt.datum(0))
    diagonal = alt.Chart(pd.DataFrame({"x": [0, 100], "y": [0, 100]})).mark_line(
        color=AXIS, strokeWidth=1
    ).encode(x="x:Q", y="y:Q")
    diag_label = alt.Chart(pd.DataFrame({"x": [97], "y": [99], "t": ["score = coverage"]})).mark_text(
        align="right", baseline="bottom", color=MUTED, fontSize=10, angle=0
    ).encode(x="x:Q", y="y:Q", text="t:N")
    zone_label = alt.Chart(pd.DataFrame({"x": [99], "y": [3], "t": ["Review zone"]})).mark_text(
        align="right", baseline="bottom", color="#b8481c", fontSize=10, fontWeight=600
    ).encode(x="x:Q", y="y:Q", text="t:N")

    tooltip = [
        alt.Tooltip("name:N", title="Candidate"),
        alt.Tooltip("target_role:N", title="Role"),
        alt.Tooltip("skill_score:Q", title="Skill coverage (%)", format=".0f"),
        alt.Tooltip("match_score:Q", title="Baseline score (%)", format=".1f"),
        alt.Tooltip("experience_years:Q", title="Experience (yrs)"),
        alt.Tooltip("group:N", title="Group"),
    ]
    points = alt.Chart(data).mark_circle(size=110, opacity=1, stroke=SURFACE_RING, strokeWidth=2).encode(
        x=alt.X("skill_score:Q", title="Skill coverage (%)", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(**axis)),
        y=alt.Y("match_score:Q", title="Baseline score (%)", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(**axis)),
        color=alt.Color("group:N", scale=scale, legend=alt.Legend(labelLimit=260)),
        tooltip=tooltip,
    )
    # Direct labels only on the points the chart is about.
    # Points often share a coverage value, so nudge labels apart vertically (in score units).
    review = data[data["group"] == REVIEW].sort_values("match_score", ascending=False).copy()
    label_y, last = [], None
    for score in review["match_score"]:
        y = score if last is None or last - score >= 5 else last - 5
        label_y.append(y)
        last = y
    review["label_y"] = label_y
    labels = alt.Chart(review).mark_text(
        align="right", dx=-10, baseline="middle", fontSize=11, color=INK, fontWeight=500
    ).encode(x="skill_score:Q", y="label_y:Q", text="first_name:N")
    return _style(alt.layer(wedge, diagonal, diag_label, zone_label, points, labels), height)


def sensitivity_dumbbell(table: pd.DataFrame, baseline_name: str, alternative_name: str,
                         limit: int = 12) -> alt.Chart:
    """One row per candidate: grey line = lowest to highest score across every
    configuration; blue dot = baseline; orange dot = alternative."""
    data = table.nlargest(limit, "score_range").copy()
    data["label"] = data["name"]
    order = data.sort_values("score_range", ascending=False)["label"].tolist()
    y = alt.Y("label:N", sort=order, title=None,
              axis=alt.Axis(grid=False, ticks=False, domain=False, labelLimit=160, labelPadding=8))
    x_axis = alt.Axis(grid=True, domain=False, ticks=False, tickCount=5)
    common_tt = [alt.Tooltip("name:N", title="Candidate"), alt.Tooltip("target_role:N", title="Role")]

    span = alt.Chart(data).mark_rule(color=DATA_NEUTRAL, strokeWidth=6, strokeCap="round", opacity=.55).encode(
        y=y,
        x=alt.X("min_score:Q", title="Score (%) under each configuration", scale=alt.Scale(domain=[0, 100]), axis=x_axis),
        x2="max_score:Q",
        tooltip=[*common_tt,
                 alt.Tooltip("min_score:Q", title="Lowest", format=".1f"),
                 alt.Tooltip("lowest_config:N", title="Lowest under"),
                 alt.Tooltip("max_score:Q", title="Highest", format=".1f"),
                 alt.Tooltip("highest_config:N", title="Highest under"),
                 alt.Tooltip("score_range:Q", title="Spread (pts)", format=".1f")],
    )
    long = data.melt(id_vars=["label", "name", "target_role", "score_range"],
                     value_vars=["baseline_score", "alternative_score"], var_name="series", value_name="score")
    long["series"] = long["series"].map({"baseline_score": baseline_name, "alternative_score": alternative_name})
    dots = alt.Chart(long).mark_circle(size=95, opacity=1, stroke=SURFACE_RING, strokeWidth=2).encode(
        y=y, x="score:Q",
        color=alt.Color("series:N", scale=alt.Scale(domain=[baseline_name, alternative_name],
                                                     range=[DATA_BLUE, DATA_ORANGE])),
        tooltip=[*common_tt, alt.Tooltip("series:N", title="Configuration"),
                 alt.Tooltip("score:Q", title="Score (%)", format=".1f")],
    )
    spread = alt.Chart(data).mark_text(align="left", dx=10, fontSize=11, color=INK_2).encode(
        y=y, x="max_score:Q", text=alt.Text("score_range:Q", format=".0f"),
    )
    chart = alt.layer(span, dots, spread).properties(height=alt.Step(30), width="container")
    return _style(chart, None)


def ranking_slope(table: pd.DataFrame, baseline_name: str, alternative_name: str, height: int = 260) -> alt.Chart:
    """Baseline rank on the left, alternative rank on the right, one line per candidate."""
    data = table[["name", "baseline_rank", "alternative_rank", "rank_change"]].copy()
    data["moved"] = ["Rank changed" if c else "Rank unchanged" for c in data["rank_change"]]
    long = data.melt(id_vars=["name", "rank_change", "moved"], value_vars=["baseline_rank", "alternative_rank"],
                     var_name="config", value_name="rank")
    long["config"] = long["config"].map({"baseline_rank": baseline_name, "alternative_rank": alternative_name})
    long["first_name"] = long["name"].str.split().str[0]
    # Tied ranks share a number but get their own row, so labels never sit on top of each other.
    long = long.sort_values(["config", "rank", "name"])
    long["position"] = long.groupby("config").cumcount() + 1
    n = int(long["position"].max())

    x = alt.X("config:N", sort=[baseline_name, alternative_name], title=None,
              axis=alt.Axis(labelAngle=0, grid=False, domain=False, ticks=False, orient="top", labelFontWeight=600,
                            labelColor=INK), scale=alt.Scale(padding=70))
    y = alt.Y("position:Q", scale=alt.Scale(domain=[n + .5, .5]), title=None,
              axis=alt.Axis(values=list(range(1, n + 1)), grid=False, domain=False, ticks=False, labels=False))
    color = alt.Color("moved:N", scale=alt.Scale(domain=["Rank changed", "Rank unchanged"],
                                                 range=[DATA_ORANGE, DATA_NEUTRAL]))
    tooltip = [alt.Tooltip("name:N", title="Candidate"), alt.Tooltip("config:N", title="Configuration"),
               alt.Tooltip("rank:Q", title="Rank (ties share a rank)"), alt.Tooltip("rank_change:Q", title="Places moved (+ = up)")]
    lines = alt.Chart(long).mark_line(strokeWidth=2).encode(x=x, y=y, color=color, detail="name:N", tooltip=tooltip)
    dots = alt.Chart(long).mark_circle(size=70, opacity=1, stroke=SURFACE_RING, strokeWidth=2).encode(
        x=x, y=y, color=color, tooltip=tooltip)
    left = alt.Chart(long[long["config"] == baseline_name]).mark_text(align="right", dx=-10, fontSize=11, color=INK_2).encode(
        x=x, y=y, text=alt.Text("label:N")).transform_calculate(label="datum.rank + '  ' + datum.first_name")
    right = alt.Chart(long[long["config"] == alternative_name]).mark_text(align="left", dx=10, fontSize=11, color=INK_2).encode(
        x=x, y=y, text=alt.Text("label:N")).transform_calculate(label="datum.first_name + '  ' + datum.rank")
    return _style(alt.layer(lines, dots, left, right), height)


COMPONENT_COLORS = {"Skills": DATA_BLUE, "Project evidence": DATA_ORANGE,
                    "Experience": DATA_AQUA, "Education": DATA_YELLOW, "Not awarded": "#e6e4dc"}


def contribution_bars(frame: pd.DataFrame, height_per_row: int = 44) -> alt.Chart:
    """Stacked points per component for each configuration, plus the points not awarded.

    frame columns: config, component, points (rows in stacking order).
    """
    order = list(COMPONENT_COLORS)
    data = frame.copy()
    data["order"] = data["component"].map(order.index)
    configs = list(dict.fromkeys(data["config"]))
    bars = alt.Chart(data).mark_bar(size=22, stroke=SURFACE_RING, strokeWidth=2).encode(
        y=alt.Y("config:N", sort=configs, title=None,
                axis=alt.Axis(grid=False, ticks=False, domain=False, labelLimit=170, labelFontWeight=500, labelColor=INK)),
        x=alt.X("sum(points):Q", title="Points out of 100", scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(grid=True, domain=False, ticks=False, tickCount=5)),
        color=alt.Color("component:N", scale=alt.Scale(domain=order, range=list(COMPONENT_COLORS.values())),
                        sort=order, legend=alt.Legend(columns=3, labelLimit=140)),
        order=alt.Order("order:Q"),
        tooltip=[alt.Tooltip("config:N", title="Configuration"), alt.Tooltip("component:N", title="Component"),
                 alt.Tooltip("points:Q", title="Points", format=".1f")],
    )
    chart = bars.properties(height=alt.Step(height_per_row), width="container")
    return _style(chart, None)


def config_strip(frame: pd.DataFrame, baseline_name: str, alternative_name: str, height: int = 120) -> alt.Chart:
    """One candidate's score under every configuration, on a single 0-100 line.

    frame columns: config, score.
    """
    data = frame.copy()
    data["role"] = [baseline_name if c == baseline_name else alternative_name if c == alternative_name
                    else "Other configurations" for c in data["config"]]
    domain = [baseline_name, alternative_name, "Other configurations"]
    lo, hi = data["score"].min(), data["score"].max()
    span = alt.Chart(pd.DataFrame({"lo": [lo], "hi": [hi], "y": [0]})).mark_rule(
        color=DATA_NEUTRAL, strokeWidth=6, strokeCap="round", opacity=.5
    ).encode(x=alt.X("lo:Q", scale=alt.Scale(domain=[0, 100]), title="Score (%)",
                     axis=alt.Axis(grid=True, domain=False, ticks=False, tickCount=5)),
             x2="hi:Q", y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-1, 1])))
    dots = alt.Chart(data.assign(y=0)).mark_circle(size=130, opacity=1, stroke=SURFACE_RING, strokeWidth=2).encode(
        x="score:Q", y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-1, 1])),
        color=alt.Color("role:N", scale=alt.Scale(domain=domain, range=[DATA_BLUE, DATA_ORANGE, "#8f8d85"])),
        tooltip=[alt.Tooltip("config:N", title="Configuration"), alt.Tooltip("score:Q", title="Score (%)", format=".1f")],
    )
    return _style(alt.layer(span, dots), height)


def experience_curve(curve: pd.DataFrame, current_years: float, current_score: float, height: int = 220) -> alt.Chart:
    """Scenario simulation: projected score at each experience value, with 'now' marked."""
    line = alt.Chart(curve).mark_line(color=DATA_BLUE, strokeWidth=2, interpolate="step-after").encode(
        x=alt.X("experience_years:Q", title="Experience (years) — simulated", axis=alt.Axis(grid=True, domain=False, ticks=False)),
        y=alt.Y("score:Q", title="Projected score (%)", scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(grid=True, domain=False, ticks=False, tickCount=5)),
        tooltip=[alt.Tooltip("experience_years:Q", title="Experience (yrs)"),
                 alt.Tooltip("score:Q", title="Projected score", format=".1f")],
    )
    hover = alt.Chart(curve).mark_circle(size=40, color=DATA_BLUE, opacity=.001).encode(
        x="experience_years:Q", y="score:Q",
        tooltip=[alt.Tooltip("experience_years:Q", title="Experience (yrs)"),
                 alt.Tooltip("score:Q", title="Projected score", format=".1f")],
    )
    now = pd.DataFrame({"x": [current_years], "y": [current_score], "t": [f"Now · {current_score:.1f}%"]})
    marker = alt.Chart(now).mark_circle(size=110, color=INK, stroke=SURFACE_RING, strokeWidth=2).encode(x="x:Q", y="y:Q")
    label = alt.Chart(now).mark_text(align="left", dx=9, dy=-9, fontSize=11, color=INK, fontWeight=600).encode(
        x="x:Q", y="y:Q", text="t:N")
    return _style(alt.layer(line, hover, marker, label), height)


# --- competence audit ---------------------------------------------------------------------------

EXACT_PASS_COLOR = "#8f8d85"


def vocabulary_vs_evidence(frame: pd.DataFrame, low_vocabulary: float, gap: float, height: int = 380) -> alt.Chart:
    """Signature view: exact vocabulary match (x) against evidence coverage (y).

    Evidence coverage can never be below the vocabulary match, so every point sits on or
    above the diagonal. The higher above it, the more evidence exact matching does not see.
    Candidates at the same position are drawn as one larger point (size = count).
    """
    data = frame.copy()
    data["group"] = [REVIEW if gap_flag else OTHER for gap_flag in data["semantic_gap"]]
    data["first_name"] = data["name"].str.split().str[0]
    points = (data.groupby(["vocabulary_match", "evidence_coverage", "group"], as_index=False)
              .agg(count=("name", "size"), names=("name", ", ".join), first_names=("first_name", ", ".join)))
    axis = dict(grid=True, domain=False, ticks=False, tickCount=5)
    zone = pd.DataFrame({"x": [0, low_vocabulary], "y": [gap, low_vocabulary + gap]})
    wedge = alt.Chart(zone).mark_area(color=DATA_ORANGE, opacity=.08).encode(x="x:Q", y="y:Q", y2=alt.datum(100))
    diagonal = alt.Chart(pd.DataFrame({"x": [0, 100], "y": [0, 100]})).mark_line(color=AXIS, strokeWidth=1).encode(
        x="x:Q", y="y:Q")
    notes = alt.layer(
        alt.Chart(pd.DataFrame({"x": [98], "y": [93], "t": ["evidence = vocabulary"]})).mark_text(
            align="right", fontSize=10, color=MUTED).encode(x="x:Q", y="y:Q", text="t:N"),
        alt.Chart(pd.DataFrame({"x": [2], "y": [98], "t": ["Review zone"]})).mark_text(
            align="left", baseline="top", fontSize=10, fontWeight=600, color="#b8481c").encode(x="x:Q", y="y:Q", text="t:N"),
    )
    dots = alt.Chart(points).mark_circle(opacity=1, stroke=SURFACE_RING, strokeWidth=2).encode(
        x=alt.X("vocabulary_match:Q", title="Vocabulary match — exact wording (%)", scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(**axis)),
        y=alt.Y("evidence_coverage:Q", title="Evidence coverage (%)", scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(**axis)),
        size=alt.Size("count:Q", scale=alt.Scale(range=[110, 420]), legend=None),
        color=alt.Color("group:N", scale=alt.Scale(domain=[REVIEW, OTHER], range=[DATA_ORANGE, DATA_BLUE]),
                        legend=alt.Legend(labelLimit=260)),
        tooltip=[alt.Tooltip("names:N", title="Candidates"),
                 alt.Tooltip("vocabulary_match:Q", title="Vocabulary match (%)", format=".0f"),
                 alt.Tooltip("evidence_coverage:Q", title="Evidence coverage (%)", format=".0f"),
                 alt.Tooltip("group:N", title="Group")],
    )
    labels = alt.Chart(points[points["group"] == REVIEW]).mark_text(
        align="left", dx=11, fontSize=11, color=INK, fontWeight=500).encode(
        x="vocabulary_match:Q", y="evidence_coverage:Q", text="first_names:N")
    return _style(alt.layer(wedge, diagonal, notes, dots, labels), height)


def two_pass(frame: pd.DataFrame, limit: int = 15) -> alt.Chart:
    """Exact-match pass vs evidence-aware pass per candidate, largest difference first."""
    data = frame.nlargest(limit, "pass_difference").copy()
    order = data.sort_values(["pass_difference", "name"], ascending=[False, True])["name"].tolist()
    y = alt.Y("name:N", sort=order, title=None,
              axis=alt.Axis(grid=False, ticks=False, domain=False, labelLimit=160, labelPadding=8))
    span = alt.Chart(data).mark_rule(color=DATA_NEUTRAL, strokeWidth=6, strokeCap="round", opacity=.55).encode(
        y=y, x=alt.X("exact_pass_score:Q", title="Score (%) with the baseline weights",
                     scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(grid=True, domain=False, ticks=False, tickCount=5)),
        x2="evidence_pass_score:Q")
    long = data.melt(id_vars=["name", "target_role", "pass_difference"],
                     value_vars=["exact_pass_score", "evidence_pass_score"], var_name="pass", value_name="score")
    long["pass"] = long["pass"].map({"exact_pass_score": "Pass 1 · exact match",
                                     "evidence_pass_score": "Pass 2 · evidence-aware"})
    dots = alt.Chart(long).mark_circle(size=95, opacity=1, stroke=SURFACE_RING, strokeWidth=2).encode(
        y=y, x="score:Q",
        color=alt.Color("pass:N", scale=alt.Scale(domain=["Pass 1 · exact match", "Pass 2 · evidence-aware"],
                                                  range=[EXACT_PASS_COLOR, DATA_AQUA])),
        tooltip=[alt.Tooltip("name:N", title="Candidate"), alt.Tooltip("target_role:N", title="Role"),
                 alt.Tooltip("pass:N", title="Pass"), alt.Tooltip("score:Q", title="Score (%)", format=".1f"),
                 alt.Tooltip("pass_difference:Q", title="Difference (pts)", format="+.1f")],
    )
    diff = alt.Chart(data).mark_text(align="left", dx=10, fontSize=11, color=INK_2).encode(
        y=y, x="evidence_pass_score:Q", text=alt.Text("pass_difference:Q", format="+.0f"))
    return _style(alt.layer(span, dots, diff).properties(height=alt.Step(30), width="container"), None)
