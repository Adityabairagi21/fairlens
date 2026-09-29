"""Competence audit: does the screening see the evidence, or only the vocabulary?"""

from __future__ import annotations

import streamlit as st

from modules import competence as rules
from modules.competence import CompetenceAuditEngine
from modules.sensitivity import HIGH_SENSITIVITY_POINTS
from ui import charts, competence_ui, state, theme

ALL_ROLES = "__all__"


def render() -> None:
    manager = state.get_manager()
    theme.page_header(
        "What did the screening capture, and what may it miss?",
        "Exact keyword matching compared with taxonomy-normalized matching and with the evidence in each record "
        "(listed skills, project technologies, descriptions, outcomes and experience). Rule-based: a skills taxonomy "
        "plus text search. No language model is used.",
        eyebrow="Competence audit",
    )
    if not manager.taxonomy_loaded:
        st.warning("skills_taxonomy.json is not loaded, so only exact wording and built-in spelling aliases are "
                   "recognised. See the message at the top or the Method page.", icon=":material/warning:")

    role = st.selectbox("Job role", [ALL_ROLES, *manager.jobs], key="comp_role",
                        format_func=lambda j: "All roles" if j == ALL_ROLES else manager.jobs[j].title)
    job_id = None if role == ALL_ROLES else role
    report = state.run_audit(job_id)
    if report.empty:
        theme.empty_state("No candidates with a target role for this selection.")
        return
    results = list(report.competence.values())
    frame = CompetenceAuditEngine.frame(results)
    stats = CompetenceAuditEngine.statistics(frame)

    theme.metric_strip([
        ("Vocabulary match", f"{stats['mean_vocabulary']:.1f}", "%", "Mean exact-wording coverage"),
        ("Evidence coverage", f"{stats['mean_evidence']:.1f}", "%",
         f"Mean gap {stats['mean_gap']:.1f} pts · median {stats['median_gap']:.1f}"),
        ("Potential semantic gaps", str(stats["semantic_gaps"]), "",
         f"Vocabulary ≤ {rules.LOW_VOCABULARY:.0f}% and evidence ≥ +{rules.SEMANTIC_GAP_POINTS:.0f} pts"),
        ("Large pass differences", str(stats["large_pass_difference"]), "",
         f"Evidence-aware pass ≥ exact pass + {rules.LARGE_PASS_DIFFERENCE:.0f} pts"),
    ], accent=[2] if stats["semantic_gaps"] else [])
    st.caption(f"{len(manager.taxonomy)} taxonomy concepts · statistics with NumPy (mean, median, max over "
               f"evidence − vocabulary) · table built with Pandas.")

    theme.heading("Vocabulary match vs evidence coverage",
                  "Each point is a candidate. On the diagonal, exact wording already captures all the evidence. "
                  "Points higher up hold relevant evidence that exact matching does not count. Points in the shaded "
                  "zone are marked Review. That is a prompt to read the record, not a verdict.")
    chart_col, list_col = st.columns([1.75, 1], gap="medium")
    with chart_col, theme.panel():
        theme.section_title("Exact wording vs evidence", "Larger points = several candidates at the same position.",
                            kind="calc")
        st.altair_chart(charts.vocabulary_vs_evidence(frame, rules.LOW_VOCABULARY, rules.SEMANTIC_GAP_POINTS),
                        width="stretch")
    with list_col, theme.panel():
        theme.section_title("High relevant evidence with low exact-match coverage",
                            "Candidates with a potential semantic gap.", kind="obs")
        flagged = frame[frame["semantic_gap"]].sort_values("pass_difference", ascending=False)
        if flagged.empty:
            theme.html('<div class="rs-none">No potential semantic gaps for this selection.</div>')
        for _, row in flagged.iterrows():
            name_col, btn_col = st.columns([2.6, 1], vertical_alignment="center")
            with name_col:
                theme.html(theme.person_row(
                    row["name"], row.target_role,
                    meta_html=f'<div class="rs-row-meta">{row.vocabulary_match:.0f}% → '
                              f'<b style="color:#0b0b0b">{row.evidence_coverage:.0f}%</b></div>'))
            if btn_col.button("View", key=f"inspect_{row.candidate_id}", type="tertiary",
                              help="Show this candidate in 'Inspect a candidate' below"):
                st.session_state.comp_candidate = row.candidate_id

    theme.heading("Two-pass screening",
                  f"Pass 1 counts only exact wording; pass 2 counts any evidence. Both use the {manager.baseline.name} "
                  "weights, so the difference comes only from the matching method. Neither pass is the correct score.")
    left, right = st.columns([1.2, 1], gap="medium")
    with left, theme.panel():
        theme.section_title("Exact-match pass vs evidence-aware pass", "Largest difference first.", kind="calc")
        st.altair_chart(charts.two_pass(frame), width="stretch")
    with right:
        st.dataframe(
            frame[["name", "exact_pass_score", "evidence_pass_score", "pass_difference", "signal"]]
            .sort_values("pass_difference", ascending=False),
            hide_index=True, width="stretch", height=min(38 + 35 * len(frame), 560),
            column_config={
                "name": st.column_config.TextColumn("Candidate", pinned=True),
                "exact_pass_score": st.column_config.NumberColumn("Pass 1 · exact", format="%.1f"),
                "evidence_pass_score": st.column_config.NumberColumn("Pass 2 · evidence", format="%.1f"),
                "pass_difference": st.column_config.NumberColumn("Difference", format="%+.1f"),
                "signal": "Signal",
            },
        )

    render_drilldown(report, frame)


def render_drilldown(report, frame) -> None:
    manager = state.get_manager()
    theme.heading("Inspect a candidate", "The competence scorecard, what exact matching missed, the evidence per "
                                         "skill and the full audit trail.")
    ids = frame.sort_values(["semantic_gap", "pass_difference"], ascending=False)["candidate_id"].tolist()
    if st.session_state.get("comp_candidate") not in ids:
        st.session_state.comp_candidate = ids[0]
    pick, legend = st.columns([1.4, 2], vertical_alignment="center")
    candidate_id = pick.selectbox(
        "Candidate", ids, key="comp_candidate", label_visibility="collapsed",
        format_func=lambda cid: f"{manager.candidates[cid].name} · {report.competence[cid].signal}")
    with legend:
        with st.popover("What the evidence statuses mean", icon=":material/info:"):
            theme.html(competence_ui.status_legend())
    candidate = manager.candidates[candidate_id]
    spread = float(report.table.set_index("candidate_id").loc[candidate_id, "score_range"])
    if spread >= HIGH_SENSITIVITY_POINTS:
        theme.html(f'<div class="fl-callout" style="margin-bottom:.8rem">{theme.tag("calc")}&nbsp; This candidate '
                   f'also has high score sensitivity: a {spread:.0f}-point spread across configurations.</div>')
    competence_ui.render_candidate_competence(candidate, report.competence[candidate_id], spread, key="page_")
    if st.button("Open the full evidence page", icon=":material/arrow_forward:"):
        state.open_candidate(candidate_id)
