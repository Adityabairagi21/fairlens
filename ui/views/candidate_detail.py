"""Candidate detail: the evidence, the calculation, the observations and the scenarios for one person.

Every section is labelled with what kind of information it holds:
FACT (from the record), CALCULATION (from the scoring engine), RULE-BASED
(the competence audit's evidence statuses), OBSERVATION (from an audit rule),
SCENARIO (a simulation, not a prediction) or REVIEWER NOTE (the human review).
"""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from modules import reports
from modules.candidate import Candidate
from modules.exceptions import ValidationError
from modules.job import JobRole
from modules.screening_engine import COMPONENT_LABELS, ScreeningEngine, ScreeningResult
from modules.validator import EDUCATION_LEVELS, skill_key
from ui import charts, competence_ui, state, theme
from ui.views.candidates import delete_dialog, edit_candidate_dialog


def render() -> None:
    manager = state.get_manager()
    if not manager.candidates:
        theme.page_header("Candidate", eyebrow="Candidates")
        theme.empty_state("No candidates yet.", "Add one on the Candidates page.")
        return

    ids = sorted(manager.candidates, key=lambda cid: manager.candidates[cid].name.casefold())
    wanted = st.session_state.get("detail_candidate")
    if wanted in manager.candidates:
        st.session_state.detail_select = wanted
    elif st.session_state.get("detail_select") not in manager.candidates:
        st.session_state.detail_select = ids[0]

    back, pick, edit, report_col, delete = st.columns([1.1, 2.6, .9, 1, 1], vertical_alignment="bottom")
    if back.button("All candidates", icon=":material/arrow_back:", type="tertiary"):
        state.switch_to("candidates")
    candidate_id = pick.selectbox("Candidate", ids, key="detail_select", label_visibility="collapsed",
                                  format_func=lambda cid: f"{manager.candidates[cid].name} · {cid}")
    st.session_state.detail_candidate = candidate_id
    candidate = manager.candidates[candidate_id]
    job = manager.jobs.get(candidate.target_job_id or "")

    if edit.button("Edit", icon=":material/edit:", width="stretch"):
        edit_candidate_dialog(candidate)
    if delete.button("Delete", icon=":material/delete:", width="stretch"):
        delete_dialog(candidate)

    base = state.baseline_engine().analyze(candidate, job) if job else None
    alt = state.alternative_engine().analyze(candidate, job) if job else None
    if base and alt:
        report_col.download_button(
            "Report", reports.candidate_text_report(candidate, job, base, alt),
            file_name=f"{candidate.candidate_id}_{job.job_id}_report.txt", icon=":material/download:", width="stretch",
        )

    added = pd.to_datetime(candidate.created_at).strftime("%d %b %Y")
    theme.page_header(candidate.name,
                      f"{job.title if job else 'No target role'} · {candidate.degree} · added {added}",
                      eyebrow=f"Candidate {candidate.candidate_id}")

    render_overview(candidate, job)
    if job is None:
        st.write("")
        theme.empty_state("Not screened yet", "Assign a target role with Edit to see the calculation and the audit.")
        render_review(candidate)
        return

    report = state.run_audit(job.job_id)      # screening + competence audit for this role, computed once
    render_evidence(candidate, job, base)
    render_competence(candidate, report)
    render_scores(base, alt)
    render_sensitivity(candidate, job)
    render_observations(candidate, job, report)
    render_what_if(candidate, job)
    render_review(candidate)


# --- FACT ----------------------------------------------------------------------------------------

def render_overview(candidate: Candidate, job: JobRole | None) -> None:
    theme.metric_strip([
        ("Listed skills", str(len(candidate.skills)), "", "As written on the resume"),
        ("Projects", str(len(candidate.projects)), "", "Described with the skills used"),
        ("Experience", f"{candidate.experience_years:g}", " yrs",
         f"Role minimum {job.min_experience:g} yrs" if job else ""),
        ("Education", candidate.education_level, "", f"Role minimum {job.min_education}" if job else ""),
    ])
    with st.expander("Contact and record details", icon=":material/badge:"):
        theme.html(
            f'<div style="margin-bottom:.4rem">{theme.tag("fact")}</div><dl class="rs-kv">'
            f"<dt>Email</dt><dd>{escape(candidate.email)}</dd>"
            f"<dt>Phone</dt><dd>{escape(candidate.phone or '—')}</dd>"
            f"<dt>Degree</dt><dd>{escape(candidate.degree)}</dd>"
            f"<dt>Target role</dt><dd>{escape(job.title) if job else 'Not assigned'}</dd>"
            f"<dt>Record ID</dt><dd>{candidate.candidate_id}</dd></dl>"
        )
        st.caption("Contact details are never used in scoring or in any audit rule.")


def render_evidence(candidate: Candidate, job: JobRole, base: ScreeningResult) -> None:
    theme.heading("Evidence", f"What the resume shows against the {len(job.required_skills)} skills "
                              f"{job.title} requires, before any weighting.")
    left, right = st.columns([1.25, 1], gap="medium")
    listed = candidate.skill_keys
    in_projects = candidate.project_skill_keys
    with left, theme.panel():
        theme.section_title("Skills evidence", f"{len(base.matched_skills)} of {len(job.required_skills)} required "
                            f"skills shown · {len(base.evidenced_skills)} used in a project", kind="fact")
        rows = []
        for key, name in job.required_skill_map.items():
            mark = lambda present: '<span class="fl-yes">✓ yes</span>' if present else '<span class="fl-no">— no</span>'
            rows.append(f"<tr><td>{escape(name)}</td><td class='c'>{mark(key in listed)}</td>"
                        f"<td class='c'>{mark(key in in_projects)}</td></tr>")
        theme.html('<table class="fl-evidence"><tr><th>Required skill</th><th class="c">Listed</th>'
                   f'<th class="c">In a project</th></tr>{"".join(rows)}</table>')
        st.write("")
        theme.section_title("Other listed skills", "Not required for this role and not scored.")
        theme.html(theme.chips(base.extra_skills, "extra", empty="None"))

    with right:
        with theme.panel():
            theme.section_title("Experience", kind="fact")
            ratio = min(candidate.experience_years / job.min_experience, 1) * 100 if job.min_experience else 100
            theme.html(
                f'<div class="fl-score-meta" style="margin-bottom:.45rem"><b style="color:#0b0b0b">'
                f'{candidate.experience_years:g} years</b> against a {job.min_experience:g}-year minimum</div>'
                + theme.bar(ratio, theme.DATA_NEUTRAL if ratio < 100 else theme.DATA_BLUE)
            )
            st.write("")
            theme.section_title("Education", kind="fact")
            gap = job.min_education_rank - candidate.education_rank
            relation = "meets the minimum" if gap <= 0 else f"{gap} level{'s' if gap > 1 else ''} below the minimum"
            theme.html(f'<div class="fl-score-meta"><b style="color:#0b0b0b">{escape(candidate.education_level)}</b> '
                       f'· {escape(job.min_education)} required · {relation}</div>')
        with theme.panel():
            theme.section_title("Projects", f"{len(candidate.projects)} described", kind="fact")
            if not candidate.projects:
                theme.html('<div class="rs-none">No projects described. Project evidence scores 0% for this role.</div>')
            required = set(job.required_skill_map)
            blocks = []
            for project in candidate.projects:
                technologies = "".join(
                    f'<span class="rs-chip {"req" if skill_key(s) in required else ""}">{escape(s)}</span>'
                    for s in project["technologies"])
                text = "".join(f'<div class="fl-project-sum"><b style="color:#52514e">{label}.</b> {escape(value)}</div>'
                               for label, value in (("Description", project["description"]),
                                                    ("Outcomes", project["outcomes"])) if value)
                blocks.append(f'<div class="fl-project"><div class="fl-project-title">{escape(project["project_name"])}'
                              f'</div>{text or "<div style=height:.4rem></div>"}'
                              f'<div class="rs-chips" style="margin-top:.35rem">{technologies}</div></div>')
            theme.html("".join(blocks))
            if candidate.projects:
                st.caption("Blue-outlined technologies are required for this role.")
        with theme.panel():
            theme.section_title("Experience summary", kind="fact")
            theme.html(f'<div class="fl-score-meta">{escape(candidate.experience_summary)}</div>'
                       if candidate.experience_summary else '<div class="rs-none">Not provided.</div>')


# --- CALCULATION ---------------------------------------------------------------------------------

def render_scores(base: ScreeningResult, alt: ScreeningResult) -> None:
    theme.heading(f"Why {base.final_score:.0f}%?",
                  "Each component's percentage times its weight gives the points it contributes. "
                  "The points add up to the score. Nothing else is involved.")
    left, right = st.columns(2, gap="medium")
    for column, result, color, label in ((left, base, theme.DATA_BLUE, "Baseline"),
                                         (right, alt, theme.DATA_ORANGE, "Alternative")):
        with column, theme.panel():
            meta = theme.status_badge(result.status)
            if result is alt:
                meta = f'{theme.delta(alt.final_score - base.final_score)} vs {escape(base.config_name)}'
            theme.html(f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem">'
                       f'<div>{theme.score_hero(result.final_score, f"{label} · {result.config_name}", color)}</div>'
                       f'<div style="padding-top:.2rem">{theme.tag("calc")}</div></div>'
                       f'<div class="fl-score-meta" style="margin:.35rem 0 1rem">{meta}</div>')
            theme.html(theme.why_breakdown(result, COMPONENT_LABELS, color))
            st.write("")
            drivers = " ".join(
                f'<span class="rs-chip">{i}. {escape(COMPONENT_LABELS[c])} · {pts:.1f}</span>'
                for i, (c, pts) in enumerate(result.drivers, start=1))
            shortfall = result.largest_shortfall
            short = (f"Largest shortfall: <b>{escape(COMPONENT_LABELS[shortfall[0]])}</b>, "
                     f"{shortfall[1]:.1f} of {result.weights[shortfall[0]]:g} points not awarded."
                     if shortfall else "No points were lost.")
            theme.html(f'<div class="rs-kicker" style="margin-bottom:.4rem">Primary score drivers</div>'
                       f'<div class="rs-chips">{drivers}</div>'
                       f'<div class="fl-score-meta" style="margin-top:.7rem">{short}</div>')

    changes = sorted(((c, alt.contributions[c] - base.contributions[c]) for c in COMPONENT_LABELS),
                     key=lambda item: abs(item[1]), reverse=True)
    parts = [f"{COMPONENT_LABELS[c]} {theme.delta(v)}" for c, v in changes if abs(v) >= 0.05]
    theme.html(f'<div class="fl-callout" style="margin-top:.2rem">{theme.tag("calc")}&nbsp; '
               f'<b>{escape(base.config_name)} → {escape(alt.config_name)}: '
               f'{theme.delta(alt.final_score - base.final_score)}</b>. By component: {", ".join(parts) or "no change"}.</div>')


def render_sensitivity(candidate: Candidate, job: JobRole) -> None:
    manager = state.get_manager()
    analyzer = state.sensitivity_analyzer()
    scores = analyzer.scores_for(candidate, job)
    frame = pd.DataFrame({"config": [manager.configs[c].name for c in scores], "score": list(scores.values())})
    spread = frame["score"].max() - frame["score"].min()
    theme.heading("Sensitivity",
                  f"The same evidence scored under all {len(scores)} saved configurations. "
                  f"The spread here is {spread:.1f} points.")
    left, right = st.columns([1.5, 1], gap="medium")
    with left, theme.panel():
        theme.section_title("Score under each configuration", kind="calc")
        st.altair_chart(charts.config_strip(frame, manager.baseline.name, manager.alternative.name), width="stretch")
    with right, theme.panel():
        theme.section_title("Points by configuration", kind="calc")
        rows = []
        for config_id, score in sorted(scores.items(), key=lambda item: -item[1]):
            config = manager.configs[config_id]
            rows.append(f'<div class="fl-scen"><span>{escape(config.name)}<br><small class="rs-mono">'
                        f'{escape(config.short_label)}</small></span><span></span><span class="n">{score:.1f}</span></div>')
        theme.html("".join(rows))
    contributions = []
    for config in manager.configs.values():
        result = ScreeningEngine(config).analyze(candidate, job)
        for component, points in result.contributions.items():
            contributions.append({"config": config.name, "component": COMPONENT_LABELS[component], "points": points})
        contributions.append({"config": config.name, "component": "Not awarded", "points": 100 - result.final_score})
    with theme.panel():
        theme.section_title("Where each configuration's points come from",
                            "Stacked points per component; the grey end is what was not awarded.", kind="calc")
        st.altair_chart(charts.contribution_bars(pd.DataFrame(contributions)), width="stretch")


# --- OBSERVATION ---------------------------------------------------------------------------------

def render_observations(candidate: Candidate, job: JobRole, report) -> None:
    found = [o for o in report.observations.get(candidate.candidate_id, []) if o.kind != "competence"]
    row = report.table.set_index("candidate_id").loc[candidate.candidate_id]
    theme.heading("Potential blind spots",
                  f"Rule-based observations from an audit of all {len(report.table)} {job.title} candidates. "
                  f"Rank {int(row.baseline_rank)} under {report.baseline.name}, {int(row.alternative_rank)} under "
                  f"{report.alternative.name}.")
    if not found:
        theme.html(f'<div class="fl-callout">{theme.tag("obs")}&nbsp; No audit rule fired for this candidate. '
                   'The score is consistent across configurations and with the skill evidence.</div>')
        return
    left, right = st.columns(2, gap="medium")
    cards = [theme.observation_card(o) for o in found]
    half = (len(cards) + 1) // 2
    with left:
        theme.html("".join(cards[:half]))
    with right:
        theme.html("".join(cards[half:]))
        theme.html('<div class="fl-callout">These are observations about the configuration, not a verdict on the '
                   'candidate. They do not say whether anyone should be selected.</div>')


# --- SCENARIO ------------------------------------------------------------------------------------

def render_what_if(candidate: Candidate, job: JobRole) -> None:
    manager = state.get_manager()
    analyzer = state.sensitivity_analyzer()
    theme.heading("What-if analysis",
                  "Scenario simulation: the real scoring engine applied to an edited copy of this record. "
                  "The stored record never changes. These are not predictions about the person.")

    config_ids = list(manager.configs)
    with theme.panel():
        theme.section_title("Simulate a different profile", kind="scenario")
        c1, c2, c3 = st.columns([1.2, 1, 1])
        config_id = c1.selectbox("Configuration", config_ids, index=config_ids.index(manager.baseline_id),
                                 format_func=lambda c: manager.configs[c].name, key=f"wi_cfg_{candidate.candidate_id}")
        years = c2.number_input("Experience (years)", 0.0, 50.0, float(candidate.experience_years), step=0.5,
                                key=f"wi_years_{candidate.candidate_id}")
        education = c3.selectbox("Education", EDUCATION_LEVELS, index=EDUCATION_LEVELS.index(candidate.education_level),
                                 key=f"wi_edu_{candidate.candidate_id}")
        engine = ScreeningEngine(manager.configs[config_id])
        current = engine.analyze(candidate, job)
        c4, c5 = st.columns([2.2, 1], vertical_alignment="bottom")
        add = c4.multiselect("Add required skills", list(current.missing_skills), key=f"wi_add_{candidate.candidate_id}",
                             placeholder="Nothing missing" if not current.missing_skills else "Choose skills")
        in_project = c5.checkbox("…and show them in a project", key=f"wi_proj_{candidate.candidate_id}",
                                 disabled=not add)

        changes = {"experience_years": years, "education_level": education}
        if add:
            changes["skills"] = [*candidate.skills, *add]
            if in_project:
                changes["projects"] = [*candidate.projects, {"project_name": "Simulated project", "technologies": add}]
        try:
            scenario = analyzer.simulate(engine, candidate, job, "Custom", **changes)
        except ValidationError as error:
            st.error(error.message, icon=":material/error:")
            return

        st.write("")
        now_col, then_col, why_col = st.columns([1, 1, 1.6], gap="medium")
        with now_col:
            theme.html(theme.score_hero(current.final_score, f"Current · {current.config_name}", theme.DATA_NEUTRAL))
        with then_col:
            theme.html(theme.score_hero(scenario.score, "Scenario", theme.DATA_BLUE)
                       + f'<div class="fl-score-meta" style="margin-top:.3rem">{theme.delta(scenario.change)}</div>')
        with why_col:
            moved = [f"{COMPONENT_LABELS[c]} {theme.delta(scenario.result.contributions[c] - current.contributions[c])}"
                     for c in COMPONENT_LABELS
                     if abs(scenario.result.contributions[c] - current.contributions[c]) >= 0.05]
            theme.html(f'<div class="fl-callout">{theme.tag("scenario")}&nbsp; '
                       f'{"Change by component: " + ", ".join(moved) if moved else "These changes do not move the score under this configuration."}'
                       '</div>')

    left, right = st.columns([1, 1.2], gap="medium")
    with left, theme.panel():
        theme.section_title("Single changes", f"Each change applied alone under {engine.config.name}.", kind="scenario")
        scenarios = analyzer.experience_scenarios(engine, candidate, job) + analyzer.skill_scenarios(engine, candidate, job)
        rows = [f'<div class="fl-scen"><span>{escape(s.label)}</span><span class="n">{s.score:.1f}</span>'
                f'<span class="n">{theme.delta(s.change, "")}</span></div>' for s in scenarios]
        theme.html('<div class="fl-scen" style="border-top:none;font-size:.66rem;color:#898781;text-transform:uppercase;'
                   'letter-spacing:.07em;font-weight:600"><span>Scenario</span><span class="n">Score</span>'
                   '<span class="n">Change</span></div>' + "".join(rows))
    with right, theme.panel():
        theme.section_title("Projected score by years of experience", f"Under {engine.config.name}; everything else "
                            "held as recorded.", kind="scenario")
        curve = analyzer.experience_curve(engine, candidate, job)
        st.altair_chart(charts.experience_curve(curve, candidate.experience_years, current.final_score), width="stretch")


# --- COMPETENCE AUDIT & HUMAN REVIEW ----------------------------------------------------------------

def render_competence(candidate: Candidate, report) -> None:
    result = report.competence[candidate.candidate_id]
    spread = float(report.table.set_index("candidate_id").loc[candidate.candidate_id, "score_range"])
    theme.heading("Competence audit",
                  "Did the screening capture the evidence, or only the vocabulary? Exact wording, taxonomy-normalized "
                  "wording and all evidence in the record, compared side by side.")
    competence_ui.render_candidate_competence(candidate, result, spread, key="detail_")


def render_review(candidate: Candidate) -> None:
    theme.heading("Human review", "FairLens stops at the audit. The assessment below is yours and is stored with "
                                  "the record; it is never used in any calculation.")
    competence_ui.render_review(candidate)
