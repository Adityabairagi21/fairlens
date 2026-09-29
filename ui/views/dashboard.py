"""Overview: what drives the screening results, at a glance."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from modules import analytics, audit
from modules import competence as competence_rules
from modules.competence import CompetenceAuditEngine
from modules.screening_engine import COMPONENT_LABELS
from modules.sensitivity import HIGH_SENSITIVITY_POINTS
from ui import charts, state, theme


def render() -> None:
    manager = state.get_manager()
    theme.page_header(
        "Understand what drives your screening results.",
        "FairLens examines what a screening process captures, what it may miss, and how results change "
        f"under different evaluation criteria. {manager.baseline.name} (baseline) is compared with "
        f"{manager.alternative.name}, every candidate is scored under {len(manager.configs)} configurations, and "
        "exact keyword matching is compared with the evidence in each record.",
        eyebrow=f"Overview · {datetime.now():%d %B %Y}",
    )

    report = state.run_audit()
    if report.empty:
        theme.empty_state("No candidates with a target role yet.",
                          "Add roles and candidates, or import data/sample_candidates.csv from Reports & data.")
        if st.button("Go to Candidates", type="primary"):
            state.switch_to("candidates")
        return

    frame = state.candidate_frame()
    summary = report.summary
    render_metrics(manager, summary, report.table["score_range"])

    # --- signature view -----------------------------------------------------------------------
    theme.heading("Skill coverage vs screening score",
                  "Each point is one candidate. The diagonal is where the score equals skill coverage. "
                  "Points in the shaded review zone show strong skill evidence but a baseline score well below it. "
                  "They are marked for review, not judged.")
    chart_col, list_col = st.columns([1.75, 1], gap="medium")
    scored = frame.dropna(subset=["match_score"])
    mask = analytics.high_evidence_low_score(scored, audit.STRONG_COVERAGE, audit.COVERAGE_GAP)
    with chart_col, theme.panel():
        theme.section_title(f"Baseline: {manager.baseline.name}",
                            f"{manager.baseline.short_label}. Review = high evidence / low baseline score.",
                            kind="calc")
        st.altair_chart(charts.coverage_vs_score(scored, mask, audit.STRONG_COVERAGE, audit.COVERAGE_GAP),
                        width="stretch")
    with list_col, theme.panel():
        review = scored[mask].sort_values("skill_score", ascending=False)
        theme.section_title("High evidence / low baseline score",
                            f"Skill coverage ≥ {audit.STRONG_COVERAGE:.0f}% and a score at least "
                            f"{audit.COVERAGE_GAP:.0f} points below it.", kind="obs")
        if review.empty:
            theme.html('<div class="rs-none">No candidates fall in the review zone under this configuration.</div>')
        for _, row in review.iterrows():
            name_col, btn_col = st.columns([3, 1], vertical_alignment="center")
            with name_col:
                theme.html(theme.person_row(
                    row["name"], f"{row.target_role}",
                    meta_html=f'<div class="rs-row-meta">{row.skill_score:.0f}% → <b style="color:#0b0b0b">'
                              f'{row.match_score:.0f}%</b></div>'))
            with btn_col:
                if st.button("Open", key=f"open_{row.candidate_id}", type="tertiary", icon=":material/arrow_forward:"):
                    state.open_candidate(row.candidate_id)
        st.write("")
        theme.html('<div class="fl-callout">Read as <b>coverage → score</b>. The gap comes from the other '
                   'components, see <b>Where the points go</b> below.</div>')

    # --- sensitivity ------------------------------------------------------------------------------
    theme.heading("Screening sensitivity",
                  f"The grey bar spans each candidate's lowest to highest score across all {len(manager.configs)} "
                  f"configurations; the number is the spread in points. A spread of {HIGH_SENSITIVITY_POINTS:.0f}+ "
                  "points means the evaluation depends heavily on which configuration is chosen.")
    with theme.panel():
        top = min(12, len(report.table))
        theme.section_title(f"Largest spreads ({top} of {len(report.table)} candidates)", kind="calc")
        st.altair_chart(charts.sensitivity_dumbbell(report.table, manager.baseline.name, manager.alternative.name,
                                                    limit=top), width="stretch")

    render_missed_evidence(report)

    # --- drivers --------------------------------------------------------------------------------------
    theme.heading("Where the points go",
                  "Average points each component awards, and loses, under the baseline configuration.")
    left, right = st.columns(2, gap="medium")
    drivers = points_by_component(report.baseline_results.values())
    with left, theme.panel():
        theme.section_title("Points not awarded, by component", "Mean across candidates. The component "
                            "costing the most points drives the ranking most.", kind="calc")
        lost = drivers[drivers["weight"] > 0]
        st.altair_chart(charts.horizontal_bars(lost, "component", "points_lost", "Component", "Mean points lost",
                                               value_format=".1f", color=theme.DATA_BLUE), width="stretch")
    with right, theme.panel():
        theme.section_title("Recent audits", "Saved to screening_history.json each time an audit is run.", kind="fact")
        render_history(manager)
        if st.button("Run a screening audit", type="primary", icon=":material/rule:"):
            state.switch_to("audit")


def render_missed_evidence(report) -> None:
    """Where exact keyword matching may not see the evidence that is in the record."""
    frame = CompetenceAuditEngine.frame(report.competence.values()).merge(
        report.table[["candidate_id", "score_range", "high_sensitivity"]], on="candidate_id")
    stats = CompetenceAuditEngine.statistics(frame)
    theme.heading("Where screening may miss evidence",
                  "Exact keyword matching compared with the evidence in each record: listed synonyms, related terms, "
                  "project technologies, descriptions and outcomes. Figures are rule-based and calculated from the data.")
    theme.metric_strip([
        ("Potential semantic gaps", str(stats["semantic_gaps"]), "",
         f"Evidence ≥ exact wording + {competence_rules.SEMANTIC_GAP_POINTS:.0f} pts"),
        ("High evidence coverage", str(stats["high_evidence"]), "", "Evidence for ≥ 80% of required skills"),
        ("High score sensitivity", str(int(frame["high_sensitivity"].sum())), "", "Spread across configurations"),
        ("Large exact-vs-evidence difference", str(stats["large_pass_difference"]), "",
         f"Two-pass difference ≥ {competence_rules.LARGE_PASS_DIFFERENCE:.0f} pts"),
    ], accent=[0] if stats["semantic_gaps"] else [])
    st.write("")
    chart_col, table_col = st.columns([1.5, 1], gap="medium")
    with chart_col, theme.panel():
        theme.section_title("Vocabulary match vs evidence coverage",
                            "Review = high relevant evidence with low exact-match coverage.", kind="calc")
        st.altair_chart(charts.vocabulary_vs_evidence(frame, competence_rules.LOW_VOCABULARY,
                                                      competence_rules.SEMANTIC_GAP_POINTS, height=320),
                        width="stretch")
    with table_col, theme.panel():
        theme.section_title("Largest exact-vs-evidence differences", "Two-pass screening, baseline weights.",
                            kind="calc")
        top = frame.nlargest(6, "pass_difference")
        rows = [theme.person_row(
            r["name"], f"{r.signal} · spread {r.score_range:.0f} pts",
            meta_html=f'<div class="rs-row-meta">{r.exact_pass_score:.0f} → <b style="color:#0b0b0b">'
                      f'{r.evidence_pass_score:.0f}</b> ({r.pass_difference:+.0f})</div>') for _, r in top.iterrows()]
        theme.html("".join(rows))
        st.write("")
        if st.button("Open the competence audit", icon=":material/manage_search:"):
            state.switch_to("competence")


def render_metrics(manager, summary: dict, ranges: pd.Series) -> None:
    stats = analytics.sensitivity_statistics(ranges)
    theme.metric_strip([
        ("Candidates analysed", str(summary["candidates"]),
         "", f"{len(manager.candidates) - summary['candidates']} without a role" if
         len(manager.candidates) > summary["candidates"] else "Everyone with a target role"),
        ("Active roles", str(len(manager.jobs)), "",
         f"{sum(len(j.required_skills) for j in manager.jobs.values())} required skills in total"),
        ("Average match score", f"{summary['average_score']:.1f}", "%",
         f"Median {summary['median_score']:.1f} · std {summary['score_std']:.1f} · {manager.baseline.name}"),
        ("High-sensitivity cases", str(summary["high_sensitivity"]), "",
         f"Spread ≥ {HIGH_SENSITIVITY_POINTS:.0f} pts · mean spread {stats['mean_range']:.1f}" if stats else ""),
    ], accent=[3] if summary["high_sensitivity"] else [])


def points_by_component(results) -> pd.DataFrame:
    rows = [{"component": COMPONENT_LABELS[c], "weight": r.weights[c], "points": r.contributions[c],
             "points_lost": r.points_lost[c]} for r in results for c in r.weights]
    frame = pd.DataFrame(rows)
    return frame.groupby("component", as_index=False).mean().round(1)


def render_history(manager) -> None:
    if not manager.history:
        theme.html('<div class="rs-none" style="margin-bottom:.8rem">No audits yet.</div>')
        return
    rows = []
    for record in manager.history[-4:][::-1]:
        when = pd.to_datetime(record.get("run_at"), errors="coerce")
        rows.append(theme.person_row(
            record.get("scope", "?"),
            f"{record.get('baseline')} vs {record.get('alternative')} · "
            f"{when:%d %b, %H:%M}" if pd.notna(when) else "",
            meta_html=f'<div class="rs-row-meta">{record.get("candidates", 0)} cand. · '
                      f'{record.get("blind_spots", 0)} blind spots</div>',
        ))
    theme.html("".join(rows))
    st.write("")

