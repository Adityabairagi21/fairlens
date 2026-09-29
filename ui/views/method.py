"""Method: how FairLens calculates, which rules produce observations, and what it does not do."""

from __future__ import annotations

import streamlit as st

from modules import __version__, audit
from modules import competence as competence_rules
from modules.competence import EVIDENCE_STATUSES, STATUS_MEANING
from modules.screening_engine import STATUS_THRESHOLDS
from modules.sensitivity import HIGH_SENSITIVITY_POINTS
from ui import state, theme
from ui.competence_ui import status_badge

TEXT = "font-size:.86rem;color:#52514e;line-height:1.65"


def render() -> None:
    manager = state.get_manager()
    theme.page_header(
        "How FairLens works.",
        "FairLens is a screening-analysis and decision-support prototype. It does not make hiring decisions "
        "and does not establish whether a real-world hiring process is discriminatory.",
        eyebrow="Method",
    )

    theme.heading("1 · The score", "Four components, each a percentage, weighted by the chosen configuration.")
    left, right = st.columns(2, gap="medium")
    with left, theme.panel():
        theme.section_title("Components", kind="calc")
        theme.html(
            f'<div style="{TEXT}">'
            "<p><b style='color:#0b0b0b'>Skills</b>: required skills the resume shows (listed, or used in a "
            "project) ÷ required skills. Matching ignores case and understands common short forms "
            "(<i>sklearn</i> = <i>Scikit-learn</i>).</p>"
            "<p><b style='color:#0b0b0b'>Project evidence</b>: required skills used in at least one described "
            "project ÷ required skills.</p>"
            "<p><b style='color:#0b0b0b'>Experience</b>: years ÷ the role's minimum, capped at 100%.</p>"
            "<p style='margin-bottom:0'><b style='color:#0b0b0b'>Education</b>: 100% if the level meets the "
            "minimum, 50% one level below, otherwise 0%.</p></div>")
    with right, theme.panel():
        theme.section_title("Formula", kind="calc")
        theme.html('<div class="rs-explain rs-math">score = skills%     × w_skills\n'
                   '      + projects%   × w_projects\n'
                   '      + experience% × w_experience\n'
                   '      + education%  × w_education   (÷ 100)\n\n'
                   'w_skills + w_projects + w_experience + w_education = 100</div>')
        st.write("")
        bands = ", ".join(f"{label} ≥ {lower:g}%" for lower, label in STATUS_THRESHOLDS)
        theme.html(f'<div style="{TEXT}">Score bands: {bands}. Bands describe the number only. '
                   "The same inputs always give the same score, and every score can be checked by hand.</div>")

    theme.heading("2 · The audit rules", "Each observation comes from one of these fixed rules. "
                                         "Thresholds live in modules/audit.py.")
    rules = [
        ("High evidence / low baseline score", "Potential blind spot",
         f"Skill coverage ≥ {audit.STRONG_COVERAGE:.0f}% and baseline score ≤ coverage − {audit.COVERAGE_GAP:.0f}."),
        ("Score shaped mainly by one criterion", "Potential blind spot",
         f"One non-skill component causes ≥ {audit.DOMINANT_SHARE:.0%} of the points not awarded and "
         f"≥ {audit.DOMINANT_MIN_POINTS:.0f} points."),
        ("Project evidence not weighted", "Potential blind spot",
         f"Projects show ≥ {audit.STRONG_PROJECTS:.0f}% of required skills, the baseline weights projects at 0%, "
         "and the alternative (which weights them) scores the candidate higher."),
        ("High score sensitivity", "Sensitivity",
         f"Highest minus lowest score across all saved configurations ≥ {HIGH_SENSITIVITY_POINTS:.0f} points."),
        ("Ranking changes with configuration", "Ranking",
         f"Rank within the role moves ≥ {audit.RANK_SHIFT} places between baseline and alternative "
         f"(roles with ≥ {audit.MIN_GROUP_FOR_RANKING} candidates)."),
        ("Listed skills without project evidence", "Evidence",
         f"Skill coverage ≥ {audit.UNBACKED_COVERAGE:.0f}% but project evidence < {audit.UNBACKED_PROJECTS:.0f}%."),
    ]
    with theme.panel():
        rows = "".join(f"<tr><td><b style='color:#0b0b0b'>{t}</b></td><td>{k}</td><td>{r}</td></tr>" for t, k, r in rules)
        theme.html('<table class="fl-evidence"><tr><th>Observation</th><th>Kind</th><th>Rule</th></tr>'
                   f'{rows}</table>')

    render_competence_method(manager)

    theme.heading("4 · Responsible design", "What FairLens deliberately does not do.")
    left, right = st.columns(2, gap="medium")
    with left, theme.panel():
        theme.section_title("Never inferred or used")
        theme.html(f'<div style="{TEXT}">FairLens does not infer gender, race, caste, religion, disability or '
                   "socioeconomic status, and it never reads names, locations, colleges, hobbies or languages for any "
                   "rule. Contact details are stored for record-keeping only. Observations are based only on the "
                   "scoring criteria and on controlled comparisons between configurations.</div>")
    with right, theme.panel():
        theme.section_title("How to read the output")
        theme.html(f'<div style="{TEXT}">A potential blind spot means <i>the score is substantially affected by '
                   "a criterion other than the demonstrated skills</i>. High sensitivity means <i>the result depends on "
                   "the configuration chosen</i>. Neither says that a candidate should be selected or rejected, or that "
                   "a process is unfair. Scenario simulations apply the scoring rules to an edited copy of a record; "
                   "they are not predictions.</div>")

    theme.heading("5 · Data", "Stored as JSON in data/; audits are exported as CSV to reports/.")
    with theme.panel():
        st.caption(f"{len(manager.candidates)} candidates · {len(manager.jobs)} roles · "
                   f"{len(manager.configs)} configurations · {len(manager.history)} audit runs")
        if st.button("Reload data from disk", icon=":material/refresh:",
                     help="Use this after editing the JSON files by hand."):
            manager.load()
            if manager.load_errors:
                state.flash("Some files could not be read. See the message at the top.", icon=":material/error:")
            else:
                state.flash("Data reloaded from disk.")
            st.rerun()
        st.caption(f"FairLens {__version__} · Python, NumPy, Pandas, Streamlit · rule-based, no machine-learning model")


def render_competence_method(manager) -> None:
    theme.heading("3 · The competence audit",
                  "Resume → extract evidence → normalize skills → exact match → evidence match → baseline score → "
                  "alternative score → sensitivity → competence audit → human review.")
    left, right = st.columns([1, 1.2], gap="medium")
    with left, theme.panel():
        theme.section_title("Evidence statuses", "One per required skill, checked in this order.", kind="rule")
        theme.html("".join(f'<div style="display:flex;gap:.6rem;align-items:center;margin:.35rem 0">'
                           f'{status_badge(s)}<span class="fl-score-meta">{STATUS_MEANING[s]}</span></div>'
                           for s in EVIDENCE_STATUSES))
        st.write("")
        theme.html(
            f'<div style="{TEXT}"><b style="color:#0b0b0b">Vocabulary match</b> = EXPLICIT ÷ required. '
            "<b style='color:#0b0b0b'>Normalized match</b> = listed under any wording ÷ required. "
            "<b style='color:#0b0b0b'>Evidence coverage</b> = anything but MISSING ÷ required. "
            "Always vocabulary ≤ normalized ≤ evidence. The two-pass comparison re-scores the skills component "
            "with the vocabulary and evidence figures, keeping the baseline weights.</div>")
    with right, theme.panel():
        theme.section_title("Rules", kind="rule")
        rules = [
            ("Potential semantic gap", f"vocabulary ≤ {competence_rules.LOW_VOCABULARY:.0f}% and evidence ≥ "
                                       f"vocabulary + {competence_rules.SEMANTIC_GAP_POINTS:.0f} → signal "
                                       "<i>Review recommended</i>"),
            ("Possible semantic mismatch", f"normalized ≥ vocabulary + {competence_rules.WORDING_GAP_POINTS:.0f}"),
            ("Evidence outside the skills list", "a required skill appears only in projects or experience"),
            ("Required skills without evidence", "any skill with status MISSING"),
            ("Signals", f"Limited evidence (< {competence_rules.LIMITED_EVIDENCE:.0f}%), Consistent "
                        f"(within {competence_rules.CONSISTENT_POINTS:.0f} pts), otherwise Partial gap"),
        ]
        rows = "".join(f"<tr><td><b style='color:#0b0b0b'>{t}</b></td><td>{r}</td></tr>" for t, r in rules)
        theme.html(f'<table class="fl-evidence"><tr><th>Observation</th><th>Rule</th></tr>{rows}</table>')
    with theme.panel():
        loaded = "loaded" if manager.taxonomy_loaded else "not loaded: exact wording and spelling aliases only"
        theme.section_title("Skills taxonomy", f"data/skills_taxonomy.json · {len(manager.taxonomy)} concepts · "
                                               f"{loaded}. Edit the JSON to extend it.", kind="fact")
        st.dataframe(manager.taxonomy.to_frame(), hide_index=True, width="stretch", height=260,
                     column_config={"concept": "Concept", "synonyms": "Synonyms (same skill)",
                                    "related": "Related terms (count as related evidence)"})
    theme.html(f'<div class="fl-callout">{theme.tag("rule")}&nbsp; The core audit is rule-based: a taxonomy plus '
               f'whole-word text search. It is not a language model and does not understand meaning. '
               f'{theme.tag("sim")}&nbsp; An optional similarity layer (character-trigram TF-IDF with cosine '
               "similarity in NumPy) suggests close spellings for missing skills. It runs locally, needs no API, "
               "and never changes a figure.</div>")
