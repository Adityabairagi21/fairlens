"""Compare screening strategies: one candidate, two configurations, side by side."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from modules.screening_engine import COMPONENT_LABELS, ScreeningEngine
from ui import charts, state, theme


def render() -> None:
    manager = state.get_manager()
    theme.page_header(
        "Compare screening configurations.",
        "The same stored evidence, scored two ways. The difference is fully explained by the weights; "
        "neither configuration is presented as the right one.",
        eyebrow="Compare strategies",
    )
    screenable = {cid: c for cid, c in manager.candidates.items() if c.target_job_id in manager.jobs}
    if not screenable:
        theme.empty_state("No candidates with a target role yet.", "Assign candidates to a role first.")
        return

    ids = sorted(screenable, key=lambda cid: screenable[cid].name.casefold())
    config_ids = list(manager.configs)
    if st.session_state.get("compare_candidate") not in screenable:
        st.session_state.compare_candidate = st.session_state.get("detail_candidate") \
            if st.session_state.get("detail_candidate") in screenable else ids[0]

    with theme.panel():
        c1, c2, c3 = st.columns([1.6, 1.2, 1.2], vertical_alignment="bottom")
        candidate_id = c1.selectbox("Candidate", ids, key="compare_candidate",
                                    format_func=lambda cid: f"{screenable[cid].name} · {manager.jobs[screenable[cid].target_job_id].title}")
        a_id = c2.selectbox("Configuration A", config_ids, index=config_ids.index(manager.baseline_id),
                            format_func=lambda c: manager.configs[c].name, key="compare_a")
        b_id = c3.selectbox("Configuration B", config_ids, index=config_ids.index(manager.alternative_id),
                            format_func=lambda c: manager.configs[c].name, key="compare_b")

    candidate = screenable[candidate_id]
    job = manager.jobs[candidate.target_job_id]
    a = ScreeningEngine(manager.configs[a_id]).analyze(candidate, job)
    b = ScreeningEngine(manager.configs[b_id]).analyze(candidate, job)
    diff = b.final_score - a.final_score

    st.write("")
    left, mid, right = st.columns([1, 1, 1.25], gap="medium")
    with left, theme.panel():
        theme.html(theme.score_hero(a.final_score, f"A · {a.config_name}", theme.DATA_BLUE, meta=a.status))
    with mid, theme.panel():
        theme.html(theme.score_hero(b.final_score, f"B · {b.config_name}", theme.DATA_ORANGE, meta=b.status))
    with right, theme.panel():
        theme.html(f'<div class="rs-kicker">Difference {theme.tag("calc")}</div>'
                   f'<div class="fl-score rs-fade" style="margin-top:.35rem"><div class="fl-score-num">'
                   f'{"+" if diff > 0 else "−" if diff < 0 else "±"}{abs(diff):.1f}<span> pts</span></div></div>'
                   f'<div class="fl-score-meta" style="margin-top:.4rem">{escape(explain_difference(a, b))}</div>')

    theme.heading("Where the difference comes from",
                  "Points per component under each configuration. The component rows below add up exactly to "
                  "the difference above.")
    rows = []
    for component, label in COMPONENT_LABELS.items():
        rows.append({
            "Component": label,
            "Evidence (%)": a.components[component],
            "A weight": a.weights[component],
            "A points": a.contributions[component],
            "B weight": b.weights[component],
            "B points": b.contributions[component],
            "Change (pts)": b.contributions[component] - a.contributions[component],
        })
    table = pd.DataFrame(rows)
    left, right = st.columns([1.15, 1], gap="medium")
    with left, theme.panel():
        theme.section_title("Component by component", "Evidence % is the same under both; only the weight changes.",
                            kind="calc")
        st.dataframe(table, hide_index=True, width="stretch", column_config={
            "Evidence (%)": st.column_config.NumberColumn(format="%.0f%%"),
            "A weight": st.column_config.NumberColumn(format="%g%%"),
            "B weight": st.column_config.NumberColumn(format="%g%%"),
            "A points": st.column_config.NumberColumn(format="%.1f"),
            "B points": st.column_config.NumberColumn(format="%.1f"),
            "Change (pts)": st.column_config.NumberColumn(format="%+.1f"),
        })
    with right, theme.panel():
        theme.section_title("Points stacked", "Grey is the part of 100 not awarded.", kind="calc")
        stacked = []
        for result in (a, b):
            label = f"{'A' if result is a else 'B'} · {result.config_name}"
            for component, points in result.contributions.items():
                stacked.append({"config": label, "component": COMPONENT_LABELS[component], "points": points})
            stacked.append({"config": label, "component": "Not awarded", "points": 100 - result.final_score})
        st.altair_chart(charts.contribution_bars(pd.DataFrame(stacked), height_per_row=52), width="stretch")

    theme.heading("Why each score?", "The full calculation for each configuration.")
    left, right = st.columns(2, gap="medium")
    for column, result, color in ((left, a, theme.DATA_BLUE), (right, b, theme.DATA_ORANGE)):
        with column, theme.panel():
            theme.section_title(f"Why {result.final_score:.0f}% under {result.config_name}?", kind="calc")
            theme.html(theme.why_breakdown(result, COMPONENT_LABELS, color))

    theme.heading("Every configuration", "This candidate under all saved configurations, highest first.")
    all_scores = pd.DataFrame([{
        "Configuration": config.name, "Weights": config.short_label,
        "Score": ScreeningEngine(config).analyze(candidate, job).final_score,
    } for config in manager.configs.values()]).sort_values("Score", ascending=False)
    st.dataframe(all_scores, hide_index=True, width="stretch", column_config={
        "Score": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100)})
    if st.button("Open this candidate's evidence page", icon=":material/arrow_forward:"):
        state.open_candidate(candidate_id)


def explain_difference(a, b) -> str:
    """A sentence naming the components that account for the gap, from the numbers only."""
    changes = sorted(((COMPONENT_LABELS[c], b.contributions[c] - a.contributions[c]) for c in COMPONENT_LABELS),
                     key=lambda item: abs(item[1]), reverse=True)
    changes = [(label, v) for label, v in changes if abs(v) >= 0.05]
    if not changes:
        return "Both configurations give the same score."
    named = ", ".join(f"{label} ({v:+.1f})" for label, v in changes[:2])
    return f"B relative to A. Mostly from {named}."
