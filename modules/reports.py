"""CSV and plain-text report generation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from modules import file_handler
from modules.candidate import Candidate
from modules.job import JobRole
from modules.screening_engine import COMPONENTS, COMPONENT_LABELS, ScreeningResult

REPORT_COLUMNS: dict[str, str] = {
    "candidate_id": "Candidate ID",
    "name": "Name",
    "target_role": "Job Role",
    "match_score": "Match Score",
    "status": "Status",
    "skill_score": "Skill Coverage",
    "project_score": "Project Evidence",
    "experience_score": "Experience Score",
    "education_score": "Education Score",
    "matched_skills": "Matched Skills",
    "missing_skills": "Missing Skills",
    "experience_years": "Experience (Years)",
    "education": "Education",
}


def build_report_frame(frame: pd.DataFrame, only_screened: bool = True) -> pd.DataFrame:
    """Shape the candidate DataFrame into the columns used in candidate_report.csv."""
    report = frame.copy()
    if only_screened:
        report = report.dropna(subset=["match_score"])
    report["education"] = report["education_level"] + " – " + report["degree"]
    # Lists become "; "-separated text so each cell stays a single CSV value.
    for column in ("matched_skills", "missing_skills"):
        report[column] = report[column].map(lambda items: "; ".join(items))
    report = report.sort_values("match_score", ascending=False, na_position="last")
    return report[list(REPORT_COLUMNS)].rename(columns=REPORT_COLUMNS).reset_index(drop=True)


def export_report_csv(report: pd.DataFrame, path: Path) -> Path:
    return file_handler.write_csv(report, path)


def candidate_text_report(candidate: Candidate, job: JobRole, result: ScreeningResult,
                          alternative: ScreeningResult | None = None) -> str:
    """A readable one-page summary for one candidate and one role."""
    width = 64
    line = "-" * width

    def bullet_list(items: tuple[str, ...]) -> str:
        return "\n".join(f"  - {item}" for item in items) if items else "  (none)"

    sections = [
        "CANDIDATE SCREENING REPORT".center(width),
        f"Generated {datetime.now():%d %b %Y, %H:%M}".center(width),
        line,
        f"Candidate    {candidate.name} ({candidate.candidate_id})",
        f"Email        {candidate.email}",
        f"Phone        {candidate.phone or '—'}",
        f"Education    {candidate.education_level} – {candidate.degree}",
        f"Experience   {candidate.experience_years:g} years",
        line,
        f"Role         {job.title} ({job.job_id})",
        f"Requires     {job.min_experience:g}+ yrs, {job.min_education} or higher",
        line,
        *score_block(result),
        *(score_block(alternative) + [f"  Difference {alternative.final_score - result.final_score:+.1f} points", ""]
          if alternative else []),
        "Matched skills",
        bullet_list(result.matched_skills),
        "",
        "Missing skills",
        bullet_list(result.missing_skills),
        "",
        "Other skills",
        bullet_list(result.extra_skills),
        "",
        "Projects",
        bullet_list(tuple(f"{p['project_name']} ({', '.join(p['technologies'])})" for p in candidate.projects)),
        line,
        "Summary",
        f"  {result.explanation}",
        line,
        "FairLens scores are rule-based and every number can be checked by hand.",
        "This is a screening-analysis aid, not a hiring decision.",
    ]
    return "\n".join(sections) + "\n"


def score_block(result: ScreeningResult) -> list[str]:
    """The 'why this score' lines: component percent x weight = points."""
    lines = [f"{result.config_name.upper()}  {result.final_score:.1f}%   [{result.status}]"]
    for component in COMPONENTS:
        weight = result.weights[component]
        if weight:
            lines.append(f"  {COMPONENT_LABELS[component]:<17}{result.components[component]:5.1f}% x {weight:g}% "
                         f"= {result.contributions[component]:4.1f} / {weight:g}")
    lines.append("")
    return lines


def competence_report(candidate: Candidate, competence, spread: float | None = None) -> str:
    """The deep audit report: what the screening captured, what it may miss, and why.

    ``competence`` is a CompetenceResult; ``spread`` is the candidate's score range across
    configurations (from the sensitivity analysis), if available. Every line is generated
    from calculated values.
    """
    width = 72
    line = "-" * width
    by_status = {status: [s.skill for s in competence.skills if s.status == status]
                 for status in ("EXPLICIT", "SUPPORTED", "RELATED", "MISSING")}

    def items(names: list[str]) -> str:
        return ", ".join(names) if names else "none"

    lines = [
        "FAIRLENS COMPETENCE AUDIT REPORT".center(width),
        f"Generated {datetime.now():%d %b %Y, %H:%M}".center(width),
        line,
        f"Candidate            {candidate.name} ({candidate.candidate_id})",
        f"Job role             {competence.job_title}",
        f"Configuration        {competence.config_name}",
        line,
        f"Baseline score       {competence.baseline.final_score:.1f}%",
        f"Exact match          {competence.vocabulary_match:.1f}%   (exact wording in the skills list)",
        f"Normalized match     {competence.normalized_match:.1f}%   (after synonyms and related terms)",
        f"Evidence coverage    {competence.evidence_coverage:.1f}%   (any evidence in the record)",
        f"Sensitivity range    {spread:.1f} points across configurations" if spread is not None
        else "Sensitivity range    not calculated",
        f"Exact-match pass     {competence.exact_pass_score:.1f}%",
        f"Evidence-aware pass  {competence.evidence_pass_score:.1f}%   ({competence.pass_difference:+.1f} points)",
        f"Potential semantic gap  {'Yes' if competence.semantic_gap else 'No'}",
        f"Signal               {competence.signal}: {competence.reason}",
        line,
        "SKILL EVIDENCE",
    ]
    for skill in competence.skills:
        lines.append(f"  {skill.skill:<22}{skill.status:<11}{skill.summary}")
    lines += [
        "",
        f"Explicit skills      {items(by_status['EXPLICIT'])}",
        f"Supported skills     {items(by_status['SUPPORTED'])}",
        f"Related wording      {items(by_status['RELATED'])}",
        f"Missing skills       {items(by_status['MISSING'])}",
        line,
        "AUDIT OBSERVATIONS",
    ]
    lines += [f"  - {o.title}: {o.text}" for o in competence.observations] or ["  - No rule fired."]
    if competence.hints:
        lines += ["", "SIMILARITY HINTS (character similarity only; not counted in any figure)"]
        lines += [f"  - {skill}: closest wording '{term}' (similarity {score:.2f})" for skill, term, score in competence.hints]
    lines += [
        line,
        "Rule-based analysis of how exact keyword matching compares with the evidence in",
        "the record. It is not a hiring recommendation and does not show whether any",
        "real screening process is discriminatory. Reviewer's own assessment: "
        + (candidate.review.get("assessment", "not recorded") if candidate.review else "not recorded") + ".",
    ]
    return "\n".join(lines) + "\n"


def save_text_report(text: str, path: Path) -> Path:
    return file_handler.write_text(text, path)
