"""Candidates: searchable table plus add/edit/delete dialogs. Selecting a row opens the evidence page."""

from __future__ import annotations

import hashlib
from html import escape

import pandas as pd
import streamlit as st

from modules.candidate import Candidate
from modules.data_manager import SORT_KEYS, filter_candidates, search_candidates, sort_candidates
from modules.exceptions import DataFileError, DuplicateCandidateError, RecordNotFoundError, ValidationError
from modules.screening_engine import ScreeningResult
from modules.validator import EDUCATION_LEVELS
from ui import state, theme

STATUSES = ["Strong match", "Possible match", "Weak match", "Not screened"]
NO_ROLE = "No role yet"
DIRECTION_LABELS = {
    "Match score": ("Highest first", "Lowest first"),
    "Name": ("A → Z", "Z → A"),
    "Experience": ("Most first", "Least first"),
    "Date added": ("Newest first", "Oldest first"),
}


def render() -> None:
    manager = state.get_manager()
    results = state.current_results()
    alternative = {cid: state.alternative_engine().analyze(manager.candidates[cid], manager.jobs[r.job_id])
                   for cid, r in results.items()}

    head, action = st.columns([4, 1], vertical_alignment="bottom")
    with head:
        theme.page_header("Explore the evidence behind each result.",
                          "Every candidate, scored against the role they applied for under both configurations. "
                          "Select a row to see the evidence, the calculation and the scenarios.",
                          eyebrow="Candidates")
    with action:
        if st.button("Add candidate", type="primary", icon=":material/add:", width="stretch"):
            add_candidate_dialog()

    if not manager.candidates:
        theme.empty_state("No candidates yet. Add your first candidate.",
                          "You can also import sample_candidates.csv from Reports & data.")
        return

    shown = render_toolbar(manager, results)
    selected_id = render_table(manager, shown, results, alternative)
    if selected_id and selected_id in manager.candidates:
        # A fresh table key next time, so returning here does not reopen the same row.
        st.session_state.table_nonce = st.session_state.get("table_nonce", 0) + 1
        state.open_candidate(selected_id)


# --- toolbar: search, filter, sort -------------------------------------------------------------

def render_toolbar(manager, results: dict[str, ScreeningResult]) -> list[Candidate]:
    role_options = {"All roles": None, **{job.title: job.job_id for job in manager.jobs.values()}}
    all_skills = sorted({s for c in manager.candidates.values() for s in c.skills}, key=str.casefold)

    search_col, role_col, sort_col, dir_col, filter_col = st.columns([2.6, 1.6, 1.4, 1.4, 1], vertical_alignment="bottom")
    with search_col:
        query = st.text_input("Search", placeholder="Search by name, email, degree or skill",
                              label_visibility="collapsed", key="cand_query")
    with role_col:
        role = st.selectbox("Role", list(role_options), label_visibility="collapsed", key="cand_role")
    with sort_col:
        sort_by = st.selectbox("Sort by", list(SORT_KEYS), label_visibility="collapsed", key="cand_sort")
    with dir_col:
        labels = DIRECTION_LABELS[sort_by]
        direction = st.selectbox("Order", [0, 1], label_visibility="collapsed", key="cand_dir",
                                 format_func=lambda i: labels[i])
    with filter_col:
        active = sum(bool(st.session_state.get(k)) for k in ("cand_edu", "cand_status", "cand_skills", "cand_minexp"))
        with st.popover(f"Filters{f' · {active}' if active else ''}", width="stretch"):
            education = st.multiselect("Education", EDUCATION_LEVELS, key="cand_edu")
            statuses = st.multiselect("Score band (baseline)", STATUSES, key="cand_status")
            must_have = st.multiselect("Must have all of these skills", all_skills, key="cand_skills")
            min_exp = st.slider("Minimum experience (years)", 0.0, 10.0, step=0.5, key="cand_minexp")

    status_lookup = {cid: r.status for cid, r in results.items()}
    scores = {cid: r.final_score for cid, r in results.items()}

    matches = search_candidates(manager.candidates.values(), query)
    matches = filter_candidates(
        matches, job_id=role_options[role], education_levels=education, min_experience=min_exp,
        must_have_skills=must_have, statuses=statuses, status_lookup=status_lookup,
    )
    # The first option is always the natural default: best score, most experience, newest, or A→Z.
    descending = direction == 0 if sort_by != "Name" else direction == 1
    return sort_candidates(matches, by=sort_by, descending=descending, scores=scores)


# --- table ---------------------------------------------------------------------------------------

def render_table(manager, shown: list[Candidate], results: dict[str, ScreeningResult],
                 alternative: dict[str, ScreeningResult]) -> str | None:
    total = len(manager.candidates)
    base_name, alt_name = manager.baseline.name, manager.alternative.name
    st.caption(f"Showing {len(shown)} of {total} candidates" if len(shown) != total else f"{total} candidates")

    if not shown:
        theme.empty_state("No candidates match these filters", "Try a different search or clear some filters.")
        return None

    rows = []
    for c in shown:
        result, alt = results.get(c.candidate_id), alternative.get(c.candidate_id)
        job = manager.jobs.get(c.target_job_id or "")
        rows.append({
            "ID": c.candidate_id,
            "Name": c.name,
            "Target role": job.title if job else "—",
            "Skill coverage": result.skill_score if result else None,
            base_name: result.final_score if result else None,
            alt_name: alt.final_score if alt else None,
            "Change": (alt.final_score - result.final_score) if result else None,
            "Experience": c.experience_years,
            "Projects": len(c.projects),
            "Education": c.education_level,
            "Skills": list(c.skills),
        })
    table = pd.DataFrame(rows)

    # A new key whenever the visible rows change, so a stale row selection is never applied
    # to a different candidate after searching or re-sorting.
    signature = hashlib.md5(",".join(table["ID"]).encode()).hexdigest()[:10]
    signature += str(st.session_state.get("table_nonce", 0))
    event = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=f"cand_table_{signature}",
        height=min(38 + 35 * len(table), 640),     # show every row without an inner scroll (up to ~17)
        column_config={
            "ID": st.column_config.TextColumn(width="small"),
            "Name": st.column_config.TextColumn(width="medium", pinned=True),
            "Skill coverage": st.column_config.ProgressColumn("Coverage", format="%.0f%%", min_value=0, max_value=100,
                                                              width="small"),
            base_name: st.column_config.NumberColumn(base_name, format="%.1f", width="small",
                                                     help=f"Score under {base_name} (baseline)"),
            alt_name: st.column_config.NumberColumn(alt_name, format="%.1f", width="small",
                                                    help=f"Score under {alt_name} (alternative)"),
            "Change": st.column_config.NumberColumn("Change", format="%+.1f", width="small",
                                                 help="Alternative minus baseline, in points"),
            "Experience": st.column_config.NumberColumn(format="%.1f yrs", width="small"),
            "Projects": st.column_config.NumberColumn(width="small"),
            "Skills": st.column_config.ListColumn(width="large"),
            "Target role": st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption("Select a row to open the candidate's evidence page.")
    selected_rows = event.selection.rows if event else []
    return table.iloc[selected_rows[0]]["ID"] if selected_rows else None


# --- dialogs ---------------------------------------------------------------------------------------

@st.dialog("Add candidate", width="large")
def add_candidate_dialog() -> None:
    candidate_form(None)


@st.dialog("Edit candidate", width="large")
def edit_candidate_dialog(candidate: Candidate) -> None:
    candidate_form(candidate)


def candidate_form(candidate: Candidate | None) -> None:
    manager = state.get_manager()
    editing = candidate is not None
    theme.html(f'<p class="rs-section-sub" style="margin-top:-.6rem">'
               f'{"Update the details for " + escape(candidate.name) if editing else "Fields marked optional can be left empty."}</p>')

    role_names = {NO_ROLE: None, **{job.title: job.job_id for job in manager.jobs.values()}}
    current_role = next((t for t, jid in role_names.items() if editing and jid == candidate.target_job_id), NO_ROLE)

    with st.form("candidate_form", border=False):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name", value=candidate.name if editing else "", placeholder="e.g. Aarav Sharma")
        email = c2.text_input("Email", value=candidate.email if editing else "", placeholder="name@example.com")
        c3, c4 = st.columns(2)
        phone = c3.text_input("Phone (optional)", value=candidate.phone if editing else "", placeholder="+91 98765 43210")
        experience = c4.text_input("Experience (years)", value=f"{candidate.experience_years:g}" if editing else "",
                                   placeholder="e.g. 2.5 — use 0 for freshers")
        c5, c6 = st.columns(2)
        education = c5.selectbox("Education level", EDUCATION_LEVELS,
                                 index=EDUCATION_LEVELS.index(candidate.education_level) if editing else 2)
        degree = c6.text_input("Degree / course", value=candidate.degree if editing else "",
                               placeholder="e.g. B.Tech in Computer Science")
        skills = st.text_area("Listed skills", value=", ".join(candidate.skills) if editing else "",
                              placeholder="Python, SQL, Pandas, Power BI", height=70,
                              help="Separate skills with commas. Duplicates are removed automatically.")
        summary = st.text_area("Experience summary (optional)", value=candidate.experience_summary if editing else "",
                               height=68, placeholder="e.g. Two years maintaining Django services at a logistics firm.",
                               help="Free text. The competence audit looks for required skills named here.")
        st.caption("Projects (optional). Separate technologies with semicolons. Required skills named in the "
                   "technologies, description or outcomes count as evidence.")
        projects = st.data_editor(
            project_rows(candidate.projects if editing else ()), num_rows="dynamic", hide_index=True,
            width="stretch", key=f"projects_{candidate.candidate_id if editing else 'new'}",
            column_config={
                "project_name": st.column_config.TextColumn("Project name", width="medium"),
                "technologies": st.column_config.TextColumn("Technologies", width="medium"),
                "description": st.column_config.TextColumn("Description", width="large"),
                "outcomes": st.column_config.TextColumn("Outcomes", width="medium"),
            },
        )
        role = st.selectbox("Target role", list(role_names), index=list(role_names).index(current_role))
        submitted = st.form_submit_button("Save changes" if editing else "Add candidate", type="primary")

    if not submitted:
        return
    fields = dict(name=name, email=email, phone=phone, experience_years=experience, education_level=education,
                  degree=degree, skills=skills, projects=editor_projects(projects), experience_summary=summary,
                  target_job_id=role_names[role])
    try:
        if editing:
            manager.update_candidate(candidate.candidate_id, **fields)
            state.flash("Candidate updated.")
        else:
            created = manager.create_candidate(**fields)
            st.session_state.detail_candidate = created.candidate_id
            state.flash("Candidate added.")
    except ValidationError as error:
        st.error(error.message, icon=":material/error:")
    except (DuplicateCandidateError, RecordNotFoundError) as error:
        st.error(str(error), icon=":material/error:")
    except DataFileError as error:
        st.error(f"Saved in memory but not on disk: {error}", icon=":material/error:")
    else:
        st.rerun()


PROJECT_COLUMNS = ["project_name", "technologies", "description", "outcomes"]


def project_rows(projects) -> pd.DataFrame:
    """Projects as editable rows; technologies shown as 'A; B'."""
    rows = [{**p, "technologies": "; ".join(p["technologies"])} for p in projects]
    return pd.DataFrame(rows, columns=PROJECT_COLUMNS).astype(str)


def editor_projects(frame: pd.DataFrame) -> list[dict[str, str]]:
    """Edited rows back to project dicts; fully blank rows are ignored. Validation happens in Candidate."""
    records = [{k: "" if v in ("None", "nan") else v.strip() for k, v in row.items()}
               for row in frame.fillna("").astype(str).to_dict(orient="records")]
    return [r for r in records if any(r.values())]


@st.dialog("Remove candidate")
def delete_dialog(candidate: Candidate) -> None:
    st.write(f"Are you sure you want to remove **{candidate.name}** ({candidate.candidate_id})? "
             "This cannot be undone. Past audit summaries are kept.")
    cancel, confirm = st.columns(2)
    if cancel.button("Cancel", width="stretch"):
        st.rerun()
    if confirm.button("Remove candidate", type="primary", width="stretch"):
        try:
            state.get_manager().delete_candidate(candidate.candidate_id)
        except (RecordNotFoundError, DataFileError) as error:
            st.error(str(error))
            return
        st.session_state.pop("detail_candidate", None)
        state.flash(f"{candidate.name} was removed.")
        state.switch_to("candidates")
