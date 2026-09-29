"""Competence-audit building blocks shared by the Competence audit page and the candidate page."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from modules import reports
from modules.candidate import Candidate
from modules.competence import EVIDENCE_STATUSES, STATUS_MEANING, CompetenceResult
from modules.exceptions import DataFileError, DuplicateCandidateError, ValidationError
from modules.validator import REVIEW_ASSESSMENTS
from ui import state, theme

SIGNAL_CLASS = {"Review recommended": "review", "Partial gap": "partial",
                "Consistent": "consistent", "Limited evidence": "limited"}


def status_badge(status: str) -> str:
    return f'<span class="fl-status fl-status-{status}">{status}</span>'


def signal_badge(signal: str) -> str:
    return f'<span class="fl-signal fl-signal-{SIGNAL_CLASS[signal]}">{escape(signal)}</span>'


# --- scorecard ---------------------------------------------------------------------------------------

def scorecard(result: CompetenceResult) -> str:
    n = len(result.skills)
    counts = result.status_counts
    rows = [
        ("Vocabulary match", "Exact wording in the skills list", result.vocabulary_match,
         f"{counts['EXPLICIT']} of {n}", "#8f8d85"),
        ("Normalized match", "After synonyms and related terms", result.normalized_match,
         f"{sum(s.listed for s in result.skills)} of {n}", theme.DATA_YELLOW),
        ("Evidence coverage", "Listed, related, or shown in projects/experience", result.evidence_coverage,
         f"{n - counts['MISSING']} of {n}", theme.DATA_AQUA),
        ("Baseline score", f"{result.config_name} configuration", result.baseline.final_score,
         "screening score", theme.DATA_BLUE),
    ]
    body = "".join(
        f'<div class="fl-scorecard-row"><div class="k">{escape(k)}<small>{escape(sub)} · {escape(note)}</small></div>'
        f'<div class="v">{value:.0f}<span style="font-size:.8rem;color:#898781">%</span></div>'
        f'<div class="bar">{theme.bar(value, color)}</div></div>'
        for k, sub, value, note, color in rows)
    return (
        f'<div class="fl-scorecard rs-fade"><div class="fl-scorecard-head"><span>COMPETENCE AUDIT</span>'
        f'<span>{escape(result.candidate_name.upper())}</span></div>{body}'
        f'<div class="fl-scorecard-signal"><div class="rs-kicker" style="margin-bottom:.4rem">Signal</div>'
        f'{signal_badge(result.signal)}<div class="fl-score-meta" style="margin-top:.5rem">'
        f'<b style="color:#0b0b0b">Reason.</b> {escape(result.reason)}</div></div></div>'
    )


# --- what did the screening miss? --------------------------------------------------------------

def missed_panel(result: CompetenceResult) -> str:
    def items(skills, detail) -> str:
        if not skills:
            return '<div class="fl-miss-item" style="color:#898781">None</div>'
        return "".join(f'<div class="fl-miss-item">{escape(s.skill)}<small>{escape(detail(s))}</small></div>'
                       for s in skills)

    missed, recovered, unsupported = result.missed_by_exact, result.recovered, result.unsupported
    n = len(result.skills)
    columns = [
        ("missed", len(missed), "Missed by exact matching",
         f"of {n} required skills are not written with the exact wording",
         items(missed, lambda s: s.status.title())),
        ("recovered", len(recovered), "Recovered through evidence",
         "found as a synonym, a related term, or in projects/experience",
         items(recovered, lambda s: s.summary)),
        ("unsupported", len(unsupported), "Still unsupported",
         "no evidence anywhere in the record",
         items(unsupported, lambda s: "Nothing found")),
    ]
    cells = []
    for i, (cls, count, label, sub, body) in enumerate(columns):
        if i:
            cells.append('<div class="fl-miss-arrow">→</div>')
        cells.append(f'<div class="fl-miss-col {cls}"><div class="fl-miss-n">{count}</div>'
                     f'<div class="fl-miss-label">{label}</div><div class="fl-miss-sub">{sub}</div>{body}</div>')
    return f'<div class="fl-miss rs-fade">{"".join(cells)}</div>'


# --- skill evidence --------------------------------------------------------------------------------

def evidence_table(result: CompetenceResult) -> str:
    rows = []
    for skill in result.skills:
        sources = "<br>".join(escape(s.describe()) for s in skill.sources) or "No evidence found"
        rows.append(f"<tr><td style='width:28%'><b>{escape(skill.skill)}</b></td>"
                    f"<td style='width:7.2rem'>{status_badge(skill.status)}</td><td class='src'>{sources}</td></tr>")
    return ('<table class="fl-ev"><tr><th>Required skill</th><th>Status</th><th>Evidence found</th></tr>'
            f'{"".join(rows)}</table>')


def status_legend() -> str:
    return "".join(f'<div style="display:flex;gap:.6rem;align-items:center;margin:.25rem 0">{status_badge(s)}'
                   f'<span class="fl-score-meta">{escape(STATUS_MEANING[s])}</span></div>' for s in EVIDENCE_STATUSES)


# --- audit trail ------------------------------------------------------------------------------------

def audit_trail(candidate: Candidate, result: CompetenceResult) -> str:
    tax = state.get_manager().taxonomy
    n = len(result.skills)
    exact = [s.skill for s in result.skills if s.exact]
    related = [f"{s.skill} ← '{s.listed_term}'" for s in result.skills if s.listed and not s.exact]
    supported = [f"{s.skill} ← {s.sources[0].place.lower()}" for s in result.skills if s.status == "SUPPORTED"]

    def mapping(term: str) -> str:
        return f"{term} → {tax.label(tax.concept_of(term))}" if tax.is_known(term) else f"{term} → (not in taxonomy)"

    b = result.baseline
    w = b.weights
    steps = [
        ("Input evidence",
         f"{len(candidate.skills)} listed skills · {len(candidate.projects)} projects "
         f"({', '.join(p['project_name'] for p in candidate.projects) or 'none'}) · experience summary "
         f"{'present' if candidate.experience_summary else 'not provided'}."),
        ("Normalized skills", "; ".join(mapping(t) for t in candidate.skills)),
        ("Exact matches", f"{len(exact)} of {n}: {', '.join(exact) or 'none'}."),
        ("Related matches", f"{len(related)}: {'; '.join(related) or 'none'}."),
        ("Evidence matches", f"{len(supported)} supported by projects or experience: {'; '.join(supported) or 'none'}."),
        ("Score calculation",
         f"Vocabulary {len(exact)}/{n} = {result.vocabulary_match:.1f}% · normalized {result.normalized_match:.1f}% · "
         f"evidence {result.evidence_coverage:.1f}%. With {result.config_name} weights "
         f"(skills {w['skills']:g}, projects {w['projects']:g}, experience {w['experience']:g}, "
         f"education {w['education']:g}): exact pass {result.exact_pass_score:.1f}%, evidence-aware pass "
         f"{result.evidence_pass_score:.1f}%, baseline {b.final_score:.1f}% "
         f"(its own skills component {b.skill_score:.1f}%)."),
        ("Final audit observation",
         f"{result.signal}. " + (" ".join(o.title + "." for o in result.observations) or "No rule fired.")),
    ]
    body = "".join(f'<div class="fl-step" data-n="{i}"><div class="fl-step-title">{escape(title)}</div>'
                   f'<div class="fl-step-body">{escape(text)}</div></div>' for i, (title, text) in enumerate(steps, 1))
    return f'<div class="fl-trail">{body}</div>'


# --- the full block -----------------------------------------------------------------------------------

def render_candidate_competence(candidate: Candidate, result: CompetenceResult, spread: float | None = None,
                                key: str = "") -> None:
    """Scorecard, 'what did the screening miss', evidence table, trail, hints and report download."""
    left, right = st.columns([1, 1.35], gap="medium")
    with left:
        theme.html(scorecard(result))
        st.write("")
        theme.html(f'<div class="fl-callout">{theme.tag("rule")}&nbsp; Two-pass screening with the '
                   f'{escape(result.config_name)} weights: <b>exact-match pass {result.exact_pass_score:.1f}%</b>, '
                   f'<b>evidence-aware pass {result.evidence_pass_score:.1f}%</b> '
                   f'({theme.delta(result.pass_difference)}). Neither pass is presented as the correct score; '
                   'the difference shows how much the matching method matters.</div>')
    with right, theme.panel():
        theme.section_title("What did the screening miss?",
                            "Exact keyword matching compared with the evidence in the record.", kind="calc")
        theme.html(missed_panel(result))
    with theme.panel():
        theme.section_title("Skill evidence", "One status per required skill, with where the evidence was found.",
                            kind="rule")
        theme.html(evidence_table(result))
    obs_col, trail_col = st.columns([1, 1.2], gap="medium")
    with obs_col:
        for obs in result.observations:
            theme.html(theme.observation_card(obs))
        if not result.observations:
            theme.html(f'<div class="fl-callout">{theme.tag("obs")}&nbsp; No competence rule fired.</div>')
        # Same audit plus the optional similarity layer; its hints never change a figure.
        hinted = state.competence_engine(similarity=True).assess(candidate, _job_of(candidate))
        with st.expander("Similarity-based hints (optional)", icon=":material/science:"):
            theme.html(f'{theme.tag("sim")}&nbsp;<span class="fl-score-meta">Character-trigram TF-IDF and cosine '
                       "similarity (NumPy). Measures spelling similarity, not meaning, and is never counted in any "
                       "figure above.</span>")
            if hinted.hints:
                for skill, term, score in hinted.hints:
                    st.caption(f"{skill}: closest wording in the record is '{term}' (similarity {score:.2f}).")
            else:
                st.caption("No wording in the record is close to a missing skill.")
        st.download_button("Generate audit report", reports.competence_report(candidate, hinted, spread),
                           file_name=f"{candidate.candidate_id}_competence_audit.txt", icon=":material/download:",
                           key=f"comp_report_{key}{candidate.candidate_id}")
    with trail_col, theme.panel():
        theme.section_title("Audit trail", "From the input evidence to the final observation.", kind="calc")
        theme.html(audit_trail(candidate, result))


def _job_of(candidate: Candidate):
    return state.get_manager().jobs[candidate.target_job_id]


# --- human review ------------------------------------------------------------------------------------

def render_review(candidate: Candidate) -> None:
    """The reviewer's own assessment and notes. FairLens records it; it never suggests one."""
    with theme.panel():
        top, when = st.columns([2, 1])
        with top:
            theme.section_title("Review finding", "Your assessment after reading the audit. FairLens does not "
                                                  "recommend hire, reject or shortlist.", kind="note")
        with when:
            if candidate.review:
                reviewed = pd.to_datetime(candidate.review.get("reviewed_at"), errors="coerce")
                stamp = f" · {reviewed:%d %b %Y, %H:%M}" if pd.notna(reviewed) else ""
                theme.html(f'<div class="fl-score-meta" style="text-align:right">Recorded: <b style="color:#0b0b0b">'
                           f'{escape(candidate.review["assessment"])}</b>{stamp}</div>')
        with st.form(f"review_{candidate.candidate_id}", border=False):
            current = candidate.review.get("assessment") if candidate.review else None
            assessment = st.radio("Initial assessment", REVIEW_ASSESSMENTS, horizontal=True,
                                  index=REVIEW_ASSESSMENTS.index(current) if current in REVIEW_ASSESSMENTS else None)
            notes = st.text_area("Reviewer notes", value=candidate.notes, height=100,
                                 placeholder="e.g. Portfolio checked; Docker experience confirmed in the project repo.")
            saved = st.form_submit_button("Record review", type="primary", icon=":material/rate_review:")
        if saved:
            if assessment is None:
                st.error("Choose an initial assessment first.", icon=":material/error:")
                return
            try:
                state.get_manager().record_review(candidate.candidate_id, assessment, notes)
            except ValidationError as error:
                st.error(error.message, icon=":material/error:")
            except (DuplicateCandidateError, DataFileError) as error:
                st.error(str(error), icon=":material/error:")
            else:
                state.flash("Review recorded.")
                st.rerun()
