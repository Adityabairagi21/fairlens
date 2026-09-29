"""Reports: export CSV/JSON/text reports and import candidates from CSV."""

from __future__ import annotations

import json

import streamlit as st

from modules import file_handler, reports
from modules.exceptions import DataFileError
from ui import state, theme


def render() -> None:
    theme.page_header("Reports and data.", "Export screening and audit results, or import candidates from a spreadsheet.", eyebrow="Reports & data")
    # A keyed control (not st.tabs) so the chosen section survives the rerun a button click causes.
    sections = {
        "Candidate report (CSV)": render_csv_export,
        "Audit results (CSV)": render_audit_export,
        "Competence report": render_competence_report,
        "Individual report": render_text_report,
        "Import & backup": render_import,
    }
    choice = st.segmented_control("Section", list(sections), default=list(sections)[0],
                                  key="reports_section", label_visibility="collapsed")
    st.write("")
    sections[choice or list(sections)[0]]()


def render_csv_export() -> None:
    manager = state.get_manager()
    frame = state.candidate_frame()
    if frame.empty:
        theme.empty_state("No candidates yet. Add your first candidate.", "There is nothing to report on.")
        return

    c1, c2 = st.columns([1.4, 2], vertical_alignment="bottom")
    role = c1.selectbox("Role", ["All roles", *[j.title for j in manager.jobs.values()]], key="report_role")
    include_unscored = c2.toggle("Include candidates without a role", key="report_unscored")

    if role != "All roles":
        frame = frame[frame["target_role"] == role]
    report = reports.build_report_frame(frame, only_screened=not include_unscored)

    if report.empty:
        theme.empty_state("No screened candidates for this selection.")
        return

    st.caption(f"{len(report)} rows · sorted by match score")
    st.dataframe(
        report, hide_index=True, width="stretch",
        column_config={"Match Score": st.column_config.NumberColumn(format="%.1f%%")},
    )

    save_col, download_col, _ = st.columns([1.3, 1.3, 2])
    with save_col:
        if st.button("Save to reports folder", icon=":material/save:", width="stretch", type="primary"):
            try:
                path = reports.export_report_csv(report, state.REPORTS_DIR / "candidate_report.csv")
                st.success(f"Saved {len(report)} rows to {path.relative_to(state.PROJECT_ROOT)}.")
            except DataFileError as error:
                st.error(str(error))
    with download_col:
        st.download_button(
            "Download CSV", report.to_csv(index=False).encode("utf-8"), file_name="candidate_report.csv",
            mime="text/csv", icon=":material/download:", width="stretch",
        )


def render_audit_export() -> None:
    manager = state.get_manager()
    report = state.run_audit()
    if report.empty:
        theme.empty_state("No candidates with a target role yet.", "There is nothing to audit.")
        return
    frame = report.to_csv_frame()
    st.caption(f"All roles · {manager.baseline.name} vs {manager.alternative.name} · {len(frame)} rows. "
               "One row per candidate with every configuration's score, ranks, spread and observations.")
    st.dataframe(frame, hide_index=True, width="stretch")
    save_col, download_col, _ = st.columns([1.3, 1.3, 2])
    with save_col:
        if st.button("Save to reports folder", icon=":material/save:", width="stretch", type="primary",
                     key="save_audit_csv"):
            try:
                path = file_handler.write_csv(frame, state.REPORTS_DIR / "audit_results.csv")
                st.success(f"Saved {len(frame)} rows to {path.relative_to(state.PROJECT_ROOT).as_posix()}.")
            except DataFileError as error:
                st.error(str(error))
    with download_col:
        st.download_button("Download CSV", frame.to_csv(index=False).encode("utf-8"), file_name="audit_results.csv",
                           mime="text/csv", icon=":material/download:", width="stretch")


def render_competence_report() -> None:
    """The deep audit report for one candidate, generated from the calculated audit."""
    manager = state.get_manager()
    report = state.run_audit()
    if report.empty:
        theme.empty_state("No candidates with a target role yet.")
        return
    ids = sorted(report.competence, key=lambda cid: manager.candidates[cid].name)
    candidate_id = st.selectbox("Candidate", ids, key="competence_report_candidate",
                                format_func=lambda cid: f"{manager.candidates[cid].name} · "
                                                        f"{report.competence[cid].signal}")
    spread = float(report.table.set_index("candidate_id").loc[candidate_id, "score_range"])
    hinted = state.competence_engine(similarity=True).assess(
        manager.candidates[candidate_id], manager.jobs[manager.candidates[candidate_id].target_job_id])
    text = reports.competence_report(manager.candidates[candidate_id], hinted, spread)
    st.code(text, language=None)
    st.download_button("Download audit report", text, file_name=f"{candidate_id}_competence_audit.txt",
                       icon=":material/download:")
    st.caption("The same figures for every candidate are columns in audit_results.csv "
               "(vocabulary_match, normalized_match, evidence_coverage, exact/evidence pass scores, signal).")


def render_text_report() -> None:
    manager = state.get_manager()
    results = state.current_results()
    if not results:
        theme.empty_state("No screened candidates yet", "Assign candidates to a role to generate their report.")
        return
    candidate_id = st.selectbox(
        "Candidate", sorted(results, key=lambda cid: manager.candidates[cid].name),
        format_func=lambda cid: f"{manager.candidates[cid].name} · {results[cid].job_title}",
        key="text_report_candidate",
    )
    candidate = manager.candidates[candidate_id]
    job = manager.jobs[candidate.target_job_id]
    alternative = state.alternative_engine().analyze(candidate, job)
    text = reports.candidate_text_report(candidate, job, results[candidate_id], alternative)
    st.code(text, language=None)
    st.download_button("Download report", text, file_name=f"{candidate_id}_{job.job_id}_report.txt",
                       icon=":material/download:")


def render_import() -> None:
    manager = state.get_manager()
    left, right = st.columns(2, gap="large")

    with left:
        theme.section_title("Import candidates from CSV",
                            "Columns: name, email, phone, experience_years, education_level, degree, skills, "
                            "target_role, and optionally projects. Separate skills with semicolons; write projects "
                            "as 'Title: skill; skill | Title: skill'.")
        upload = st.file_uploader("CSV file", type=["csv"], label_visibility="collapsed")
        import_col, sample_col = st.columns(2)
        run_upload = import_col.button("Import file", disabled=upload is None, width="stretch", type="primary")
        run_sample = sample_col.button("Use sample file", width="stretch",
                                       help="Imports data/sample_candidates.csv")

        source = upload if run_upload else (state.DATA_DIR / "sample_candidates.csv" if run_sample else None)
        if source is not None:
            try:
                summary = manager.import_candidates_csv(source)
            except DataFileError as error:
                st.error(str(error), icon=":material/error:")
            else:
                # No rerun here: a rerun would switch back to the first tab and hide this summary.
                st.session_state.import_summary = summary
                if summary.added:
                    st.toast(f"Imported {len(summary.added)} candidate(s).", icon=":material/check_circle:")

        summary = st.session_state.get("import_summary")
        if summary is not None:
            if summary.added:
                st.success(f"Added {len(summary.added)} candidate(s): {', '.join(summary.added)}.")
            if summary.skipped:
                st.warning(f"Skipped {len(summary.skipped)} row(s) that need fixing:")
                for row, reason in summary.skipped:
                    st.caption(f"Row {row}: {reason}")
            if not summary.added and not summary.skipped:
                st.info("The file had no data rows.")

    with right:
        theme.section_title("Back up all data", "Candidates, roles and screening configurations as one JSON file.")
        backup = json.dumps(manager.export_json(), indent=2, ensure_ascii=False)
        st.download_button("Download backup (.json)", backup, file_name="fairlens_backup.json",
                           mime="application/json", icon=":material/download:")
        st.write("")
        theme.section_title("Where data is stored")
        for key, path in manager.paths.items():
            status = "unreadable" if key in manager.load_errors else ("found" if path.exists() else "not created yet")
            st.caption(f"{path.relative_to(state.PROJECT_ROOT).as_posix()} · {status}")
