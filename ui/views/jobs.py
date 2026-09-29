"""Jobs: define roles and see which candidates fit each one."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from modules.exceptions import DataFileError, DuplicateJobError, RecordNotFoundError, ValidationError
from modules.job import JobRole
from modules.validator import EDUCATION_LEVELS
from ui import state, theme


def render() -> None:
    manager = state.get_manager()

    head, action = st.columns([4, 1], vertical_alignment="bottom")
    with head:
        theme.page_header("Roles and their requirements.", "Each role lists the skills, experience and education candidates are measured against. Ranking uses the baseline configuration.", eyebrow="Roles")
    with action:
        if st.button("Add job role", type="primary", icon=":material/add:", width="stretch"):
            add_job_dialog()

    if not manager.jobs:
        theme.empty_state("No job roles yet. Add your first role.",
                          "Candidates can only be scored once there is a role to compare them with.")
        return

    analyzer = state.baseline_engine()
    for job in manager.jobs.values():
        render_job(job, analyzer)


def render_job(job: JobRole, analyzer) -> None:
    manager = state.get_manager()
    applicants = [c for c in manager.candidates.values() if c.target_job_id == job.job_id]
    ranked = analyzer.rank_candidates(applicants, job)
    average = sum(r.final_score for r in ranked) / len(ranked) if ranked else None

    with theme.panel():
        title_col, buttons_col = st.columns([4, 1.3], vertical_alignment="top")
        with title_col:
            description = f'<div style="font-size:.86rem;color:#52514e;margin-top:.2rem">{escape(job.description)}</div>' \
                if job.description else ""
            theme.html(
                f'<div class="rs-fade"><div style="display:flex;align-items:baseline;gap:.6rem">'
                f'<span style="font-size:1.08rem;font-weight:650;color:#0b0b0b">{escape(job.title)}</span>'
                f'<span class="rs-mono">{job.job_id}</span></div>{description}'
                f'<div class="rs-job-meta">'
                f'<span>Min. experience <b>{job.min_experience:g} {"yr" if job.min_experience == 1 else "yrs"}</b></span>'
                f'<span>Min. education <b>{escape(job.min_education)}</b></span>'
                f'<span>Applicants <b>{len(applicants)}</b></span>'
                f'<span>Average score <b>{f"{average:.1f}%" if average is not None else "—"}</b></span>'
                f'</div></div>'
            )
            theme.html(theme.chips(job.required_skills))
        with buttons_col:
            edit_col, delete_col = st.columns(2, gap="small")
            if edit_col.button("Edit", key=f"edit_{job.job_id}", icon=":material/edit:", width="stretch"):
                edit_job_dialog(job)
            if delete_col.button("Delete", key=f"del_{job.job_id}", icon=":material/delete:", width="stretch"):
                delete_job_dialog(job)

        st.write("")
        with st.expander(f"Candidates for this role ({len(applicants)})"):
            include_pool = st.toggle(
                "Also rank candidates who applied for other roles", key=f"pool_{job.job_id}",
                help="Useful for spotting people in the pool who would suit this role better.",
            )
            pool = manager.candidates.values() if include_pool else applicants
            results = analyzer.rank_candidates(pool, job)
            if not results:
                theme.empty_state("Nobody has applied for this role yet",
                                  "Turn on the toggle above to rank everyone in the pool against it.")
            else:
                render_ranking(results, show_applied_for=include_pool)


def render_ranking(results, show_applied_for: bool) -> None:
    manager = state.get_manager()

    def applied_for(candidate_id: str) -> str:
        job = manager.jobs.get(manager.candidates[candidate_id].target_job_id or "")
        return job.title if job else "—"

    table = pd.DataFrame([{
        "Candidate": r.candidate_name,
        "Applied for": applied_for(r.candidate_id),
        "Baseline score": r.final_score,
        "Skills": r.skill_score,
        "Projects": r.project_score,
        "Experience": r.experience_score,
        "Education": r.education_score,
        "Missing skills": list(r.missing_skills),
    } for r in results])
    if not show_applied_for:
        table = table.drop(columns="Applied for")

    percent = st.column_config.NumberColumn(format="%.0f%%", width="small")
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "Baseline score": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Skills": percent, "Projects": percent, "Experience": percent, "Education": percent,
            "Missing skills": st.column_config.ListColumn(width="medium"),
        },
    )


@st.dialog("Add job role", width="large")
def add_job_dialog() -> None:
    job_form(None)


@st.dialog("Edit job role", width="large")
def edit_job_dialog(job: JobRole) -> None:
    job_form(job)


def job_form(job: JobRole | None) -> None:
    manager = state.get_manager()
    editing = job is not None
    with st.form("job_form", border=False):
        title = st.text_input("Job title", value=job.title if editing else "", placeholder="e.g. Data Analyst")
        skills = st.text_area("Required skills", value=", ".join(job.required_skills) if editing else "",
                              placeholder="Python, SQL, Excel, Power BI", height=80,
                              help="Separate skills with commas. Each required skill carries equal weight.")
        c1, c2 = st.columns(2)
        min_exp = c1.text_input("Minimum experience (years)", value=f"{job.min_experience:g}" if editing else "",
                                placeholder="e.g. 2 — use 0 for entry level")
        min_edu = c2.selectbox("Minimum education", EDUCATION_LEVELS,
                               index=EDUCATION_LEVELS.index(job.min_education) if editing else 2)
        description = st.text_input("Short description (optional)", value=job.description if editing else "",
                                    placeholder="What will this person work on?", max_chars=300)
        submitted = st.form_submit_button("Save changes" if editing else "Add job role", type="primary")

    if not submitted:
        return
    fields = dict(title=title, required_skills=skills, min_experience=min_exp,
                  min_education=min_edu, description=description)
    try:
        if editing:
            manager.update_job(job.job_id, **fields)
            state.flash("Job role updated.")
        else:
            manager.create_job(**fields)
            state.flash("Job role added successfully.")
    except ValidationError as error:
        st.error(error.message, icon=":material/error:")
    except (DuplicateJobError, DataFileError) as error:
        st.error(str(error), icon=":material/error:")
    else:
        st.rerun()


@st.dialog("Delete job role")
def delete_job_dialog(job: JobRole) -> None:
    manager = state.get_manager()
    affected = sum(1 for c in manager.candidates.values() if c.target_job_id == job.job_id)
    note = f" {affected} candidate(s) who applied for it will be kept but left without a role." if affected else ""
    st.write(f"Are you sure you want to delete **{job.title}**?{note}")
    cancel, confirm = st.columns(2)
    if cancel.button("Cancel", width="stretch"):
        st.rerun()
    if confirm.button("Delete role", type="primary", width="stretch"):
        try:
            manager.delete_job(job.job_id)
        except (RecordNotFoundError, DataFileError) as error:
            st.error(str(error))
            return
        state.flash(f"{job.title} was deleted.")
        st.rerun()
