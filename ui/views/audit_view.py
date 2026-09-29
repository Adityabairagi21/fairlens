"""Screening audit: run a role's candidates through two configurations and inspect the result."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from modules import file_handler
from modules.audit import MIN_GROUP_FOR_RANKING
from modules.exceptions import DataFileError
from modules.sensitivity import HIGH_SENSITIVITY_POINTS
from ui import charts, state, theme

ALL_ROLES = "__all__"
OBSERVATION_FILTERS = {
    "All": None,
    "Potential blind spots": "blind_spot",
    "Sensitivity": "sensitivity",
    "Ranking": "ranking",
    "Evidence": "evidence",
    "Competence": "competence",
}


def render() -> None:
    manager = state.get_manager()
    theme.page_header(
        "Run a screening audit.",
        "Choose a role and two configurations. FairLens scores every candidate under both, measures how much "
        "each score moves across all saved configurations, and records rule-based observations. "
        "The audit inspects the screening configuration, not the candidates.",
        eyebrow="Screening audit",
    )
    if not manager.jobs or not manager.candidates:
        theme.empty_state("An audit needs at least one role and one candidate.",
                          "Add them on the Roles and Candidates pages.")
        return

    config_ids = list(manager.configs)
    with theme.panel():
        c1, c2, c3, c4 = st.columns([1.5, 1.3, 1.3, 1], vertical_alignment="bottom")
        role = c1.selectbox("Job role", [ALL_ROLES, *manager.jobs], key="audit_role",
                            format_func=lambda j: "All roles" if j == ALL_ROLES else manager.jobs[j].title)
        baseline_id = c2.selectbox("Baseline configuration", config_ids, key="audit_baseline",
                                   index=config_ids.index(manager.baseline_id),
                                   format_func=lambda c: manager.configs[c].name)
        alternative_id = c3.selectbox("Compare with", config_ids, key="audit_alternative",
                                      index=config_ids.index(manager.alternative_id),
                                      format_func=lambda c: manager.configs[c].name)
        run = c4.button("Run audit", type="primary", icon=":material/play_arrow:", width="stretch")
        st.caption(f"{manager.configs[baseline_id].name}: {manager.configs[baseline_id].short_label}  ·  "
                   f"{manager.configs[alternative_id].name}: {manager.configs[alternative_id].short_label}")

    if run:
        if baseline_id == alternative_id:
            st.error("Choose two different configurations to compare.", icon=":material/error:")
        else:
            st.session_state.audit_params = (role, baseline_id, alternative_id)
            record_run(role, baseline_id, alternative_id)

    params = st.session_state.get("audit_params")
    if not params or params[1] not in manager.configs or params[2] not in manager.configs \
            or (params[0] != ALL_ROLES and params[0] not in manager.jobs):
        st.write("")
        theme.empty_state("Choose a role and two configurations, then select Run audit.",
                          "Each run is saved to screening_history.json and exported to reports/audit_results.csv.")
        render_history(manager)
        return

    role, baseline_id, alternative_id = params
    # Recomputed on every rerun so edits to candidates or configurations are always reflected.
    report = state.audit_engine(baseline_id, alternative_id).run(manager, None if role == ALL_ROLES else role)
    if report.empty:
        theme.empty_state(f"No candidates have applied for {report.scope} yet.")
        return
    render_report(report)
    render_history(manager)


def record_run(role: str, baseline_id: str, alternative_id: str) -> None:
    manager = state.get_manager()
    report = state.audit_engine(baseline_id, alternative_id).run(manager, None if role == ALL_ROLES else role)
    if report.empty:
        return
    try:
        manager.record_audit(report.to_history_record())
        file_handler.write_csv(report.to_csv_frame(), state.REPORTS_DIR / "audit_results.csv")
        st.toast(f"Audit saved · {report.summary['candidates']} candidates", icon=":material/check_circle:")
    except DataFileError as error:
        st.warning(f"The audit is shown below but could not be saved: {error}", icon=":material/warning:")


def render_report(report) -> None:
    s = report.summary
    base, alt = report.baseline.name, report.alternative.name
    st.write("")
    theme.html(f'<div class="rs-kicker" style="margin-bottom:.6rem">Audit · {report.scope} · '
               f'<span class="fl-key" style="background:{theme.DATA_BLUE}"></span>{base} vs '
               f'<span class="fl-key" style="background:{theme.DATA_ORANGE}"></span>{alt}</div>')
    theme.metric_strip([
        ("Candidates analysed", str(s["candidates"]), "", report.scope),
        ("Average baseline score", f"{s['average_score']:.1f}", "", f"Median {s['median_score']:.1f} · std {s['score_std']:.1f}"),
        ("Score range", f"{s['min_score']:.0f}–{s['max_score']:.0f}", "", f"{s['score_range']:.1f} points apart"),
        ("Average skill coverage", f"{s['average_coverage']:.1f}", "%", "Required skills shown"),
        ("High sensitivity", str(s["high_sensitivity"]), "", f"Spread ≥ {HIGH_SENSITIVITY_POINTS:.0f} pts"),
        ("Potential blind spots", str(s["blind_spots"]), "", "Rule-based, see below"),
        ("Ranking changes", str(s["ranking_changes"]), "", f"{base} → {alt}"),
        ("Semantic gaps", str(s["semantic_gaps"]), "", f"Evidence {s['average_evidence']:.0f}% vs exact "
                                                       f"{s['average_vocabulary']:.0f}%"),
    ], accent=[i for i, v in ((4, s["high_sensitivity"]), (5, s["blind_spots"]), (7, s["semantic_gaps"])) if v])
    st.caption(f"Computed with NumPy from the audit table: mean, median, std, min/max and ptp. Average change "
               f"from {base} to {alt}: {s['average_change']:+.1f} points; mean sensitivity spread "
               f"{s['average_sensitivity']:.1f} points.")

    render_ranking(report)
    render_observations(report)
    render_sensitivity(report)
    render_export(report)


def render_ranking(report) -> None:
    base, alt = report.baseline.name, report.alternative.name
    theme.heading("Ranking stability",
                  f"Rank within each role under {base} (left) and {alt} (right). Lines that cross show how "
                  "much the order depends on the configuration. Neither ranking is treated as correct.")
    roles = [r for r, g in report.table.groupby("target_role") if len(g) >= MIN_GROUP_FOR_RANKING]
    if roles:
        columns = st.columns(min(len(roles), 3), gap="medium")
        for i, role in enumerate(roles):
            group = report.table[report.table["target_role"] == role]
            with columns[i % len(columns)], theme.panel():
                moved = int((group["rank_change"] != 0).sum())
                theme.section_title(role, f"{len(group)} candidates · {moved} change rank", kind="calc")
                st.altair_chart(charts.ranking_slope(group, base, alt, height=max(160, 34 * len(group))),
                                width="stretch")

    table = report.table[["name", "target_role", "baseline_rank", "alternative_rank", "rank_change",
                          "baseline_score", "alternative_score", "score_change"]].copy()
    table["movement"] = table["rank_change"].map(lambda c: f"▲ {c}" if c > 0 else (f"▼ {-c}" if c < 0 else "—"))
    with st.expander("Ranking table", icon=":material/table:"):
        st.dataframe(
            table.drop(columns="rank_change"), hide_index=True, width="stretch",
            column_config={
                "name": "Candidate", "target_role": "Role",
                "baseline_rank": st.column_config.NumberColumn(f"{base} rank"),
                "alternative_rank": st.column_config.NumberColumn(f"{alt} rank"),
                "baseline_score": st.column_config.NumberColumn(f"{base} score", format="%.1f"),
                "alternative_score": st.column_config.NumberColumn(f"{alt} score", format="%.1f"),
                "score_change": st.column_config.NumberColumn("Change (pts)", format="%+.1f"),
                "movement": st.column_config.TextColumn("Places moved"),
            },
        )


def render_observations(report) -> None:
    theme.heading("Observations",
                  "Each observation comes from a fixed rule over the calculated scores (see Method). "
                  "They describe how the configuration treats the evidence. They are not hiring recommendations.")
    choice = st.segmented_control("Show", list(OBSERVATION_FILTERS), default="All", key="audit_obs_filter",
                                  label_visibility="collapsed")
    kind = OBSERVATION_FILTERS.get(choice or "All")
    names = report.table.set_index("candidate_id")[["name", "target_role"]].to_dict(orient="index")

    cards = []
    for cid, found in report.observations.items():
        for obs in found:
            if kind is None or obs.kind == kind:
                who = f"{names[cid]['name']} · {names[cid]['target_role']}"
                cards.append(theme.observation_card(obs, who))
    if not cards:
        theme.empty_state("No observations of this kind for this audit.")
        return
    left, right = st.columns(2, gap="medium")
    half = (len(cards) + 1) // 2
    with left:
        theme.html("".join(cards[:half]))
    with right:
        theme.html("".join(cards[half:]))


def render_sensitivity(report) -> None:
    theme.heading("Score sensitivity",
                  f"Every candidate scored under all {len(report.configs)} saved configurations. "
                  "Spread is the highest minus the lowest score (np.ptp); std is np.std across configurations.")
    columns = {c.config_id: c.name for c in report.configs}
    table = report.table[["name", "target_role", *columns, "score_range", "score_std",
                          "lowest_config", "highest_config", "high_sensitivity"]]
    table = table.sort_values("score_range", ascending=False).rename(columns=columns)
    score_format = {name: st.column_config.NumberColumn(name, format="%.1f") for name in columns.values()}
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "name": st.column_config.TextColumn("Candidate", pinned=True), "target_role": "Role",
            **score_format,
            "score_range": st.column_config.ProgressColumn("Spread (pts)", format="%.1f", min_value=0, max_value=50),
            "score_std": st.column_config.NumberColumn("Std", format="%.1f"),
            "lowest_config": "Lowest under", "highest_config": "Highest under",
            "high_sensitivity": st.column_config.CheckboxColumn("High"),
        },
    )


def render_export(report) -> None:
    theme.heading("Export", "The full audit table with one row per candidate, observations included.")
    csv = report.to_csv_frame()
    left, right, _ = st.columns([1.2, 1.2, 2])
    left.download_button("Download audit_results.csv", csv.to_csv(index=False).encode("utf-8"),
                         file_name="audit_results.csv", mime="text/csv", icon=":material/download:", width="stretch")
    right.caption(f"{len(csv)} rows · {len(csv.columns)} columns. The latest run is also written to "
                  "reports/audit_results.csv.")


def render_history(manager) -> None:
    theme.heading("Screening history", "One row per audit run, newest first (screening_history.json).")
    if not manager.history:
        theme.empty_state("No audits have been run yet.")
        return
    frame = pd.DataFrame(manager.history[::-1][:50])
    frame["run_at"] = pd.to_datetime(frame["run_at"], errors="coerce")
    st.dataframe(
        frame[["run_at", "scope", "baseline", "alternative", "candidates", "average_score", "average_coverage",
               "high_sensitivity", "blind_spots", "ranking_changes",
               *[c for c in ("semantic_gaps",) if c in frame.columns]]],
        hide_index=True, width="stretch",
        column_config={
            "run_at": st.column_config.DatetimeColumn("Run", format="DD MMM, HH:mm"),
            "scope": "Role", "baseline": "Baseline", "alternative": "Alternative", "candidates": "Candidates",
            "average_score": st.column_config.NumberColumn("Avg score", format="%.1f"),
            "average_coverage": st.column_config.NumberColumn("Avg coverage", format="%.1f%%"),
            "high_sensitivity": "High sensitivity", "blind_spots": "Blind spots", "ranking_changes": "Rank changes",
            "semantic_gaps": "Semantic gaps",
        },
    )
