"""Analytics: NumPy statistics and Pandas breakdowns of the candidate pool."""

from __future__ import annotations

import streamlit as st

from modules import analytics
from ui import charts, state, theme


def render() -> None:
    manager = state.get_manager()
    frame = state.candidate_frame()

    head, role_col = st.columns([3, 1.3], vertical_alignment="bottom")
    with head:
        theme.page_header("The candidate pool in numbers.", "Score statistics, skill trends and gaps under the baseline configuration, computed with NumPy and Pandas.", eyebrow="Pool analytics")
    if frame.empty:
        theme.empty_state("No candidates yet. Add your first candidate.", "Analytics appear once there is data to analyse.")
        return

    roles = ["All roles", *[job.title for job in manager.jobs.values()]]
    with role_col:
        role = st.selectbox("Role", roles, label_visibility="collapsed", key="analytics_role")
    if role != "All roles":
        frame = frame[frame["target_role"] == role]  # Pandas boolean-mask filtering
        if frame.empty:
            theme.empty_state(f"No candidates have applied for {role} yet.")
            return

    render_numpy_stats(frame)
    st.write("")

    left, right = st.columns(2, gap="medium")
    with left, theme.panel():
        theme.section_title("Match score distribution", "Candidates per 20-point score range (np.histogram).")
        st.altair_chart(charts.vertical_bars(analytics.score_distribution(frame["match_score"]), "range",
                                             "candidates", "Match score (%)", "Candidates"), width="stretch")
    with right, theme.panel():
        if role == "All roles":
            theme.section_title("Average score by role", "Mean match score of each role's applicants (groupby).")
            by_role = analytics.average_score_by_role(frame)
            st.altair_chart(charts.horizontal_bars(by_role, "target_role", "avg_score", "Role", "Average score (%)",
                                                   value_format=".1f", domain_max=100), width="stretch")
        else:
            theme.section_title("Most common missing skills", f"Required for {role} but absent from applicants' profiles.")
            gaps = analytics.missing_skill_frequency(frame)
            if gaps.empty:
                theme.empty_state("No gaps", "Every applicant has every required skill.")
            else:
                st.altair_chart(charts.horizontal_bars(gaps, "skill", "candidates", "Skill", "Candidates missing it"),
                                width="stretch")

    left, right = st.columns(2, gap="medium")
    with left, theme.panel():
        theme.section_title("Skill frequency", "Top skills listed by candidates (explode + value_counts).")
        st.altair_chart(charts.horizontal_bars(analytics.skill_frequency(frame, top=12), "skill", "candidates",
                                               "Skill", "Candidates"), width="stretch")
    with right, theme.panel():
        theme.section_title("Experience vs match score", correlation_note(frame))
        st.altair_chart(charts.experience_vs_score(frame), width="stretch")

    left, right = st.columns(2, gap="medium")
    with left, theme.panel():
        theme.section_title("Experience distribution", "Candidates per experience band (pd.cut).")
        st.altair_chart(charts.vertical_bars(analytics.experience_distribution(frame), "experience", "candidates",
                                             "Experience", "Candidates", sort=list(analytics.EXPERIENCE_LABELS)),
                        width="stretch")
    with right, theme.panel():
        if role == "All roles":
            theme.section_title("Candidates per role", "Applicants for each open role (value_counts).")
            per_role = analytics.candidates_per_role(frame)
            st.altair_chart(charts.horizontal_bars(per_role, "target_role", "candidates", "Role", "Candidates"),
                            width="stretch")
        else:
            theme.section_title("Education levels", "Highest qualification of applicants.")
            st.altair_chart(charts.vertical_bars(analytics.education_breakdown(frame), "education_level", "candidates",
                                                 "Education", "Candidates", sort=list(analytics.EDUCATION_LEVELS)),
                            width="stretch")

    st.write("")
    theme.section_title("Tables", "The same numbers as tables, computed with Pandas.")
    tab_summary, tab_roles, tab_status, tab_top = st.tabs(
        ["Descriptive statistics", "By role", "By status", "Top candidates"]
    )
    with tab_summary:
        st.caption("DataFrame.describe() on the numeric columns. Its std is the sample standard deviation "
                   "(ddof=1), so it is slightly higher than the NumPy population figure (ddof=0) in the cards above.")
        st.dataframe(analytics.numeric_summary(frame), width="stretch")
    with tab_roles:
        st.dataframe(
            analytics.average_score_by_role(frame), hide_index=True, width="stretch",
            column_config={
                "target_role": "Role", "candidates": "Candidates",
                "avg_score": st.column_config.NumberColumn("Average score", format="%.1f%%"),
                "best_score": st.column_config.NumberColumn("Best score", format="%.1f%%"),
                "avg_experience": st.column_config.NumberColumn("Average experience", format="%.1f yrs"),
            },
        )
    with tab_status:
        st.dataframe(analytics.status_breakdown(frame), hide_index=True, width="stretch",
                     column_config={"status": "Status", "candidates": "Candidates"})
    with tab_top:
        top = analytics.top_candidates(frame, n=10)
        st.dataframe(
            top[["name", "target_role", "match_score", "experience_years", "missing_skills"]],
            hide_index=True, width="stretch",
            column_config={
                "name": "Candidate", "target_role": "Role",
                "match_score": st.column_config.ProgressColumn("Match score", format="%.0f%%", min_value=0, max_value=100),
                "experience_years": st.column_config.NumberColumn("Experience", format="%.1f yrs"),
                "missing_skills": st.column_config.ListColumn("Missing skills"),
            },
        )


def render_numpy_stats(frame) -> None:
    stats = analytics.score_statistics(frame["match_score"])
    if stats is None:
        theme.empty_state("No scored candidates", "Assign candidates to a role to see score statistics.")
        return
    cards = [
        ("Mean", f"{stats['mean']:.1f}", "%", f"{stats['count']} scored candidates"),
        ("Median", f"{stats['median']:.1f}", "%", "Middle score"),
        ("Std. deviation", f"{stats['std']:.1f}", "", "How spread out scores are"),
        ("Range", f"{stats['min']:.0f}–{stats['max']:.0f}", "%", "Lowest to highest"),
        ("Middle 50%", f"{stats['p25']:.0f}–{stats['p75']:.0f}", "%", "25th to 75th percentile"),
    ]
    columns = st.columns(len(cards), gap="small")
    for column, (label, value, unit, note) in zip(columns, cards):
        with column:
            theme.html(theme.stat_card(label, value, note, unit=unit))
    st.caption("Computed with NumPy: np.mean, np.median, np.std, np.min/np.max and np.percentile.")


def correlation_note(frame) -> str:
    r = analytics.experience_score_correlation(frame)
    if r is None:
        return "Not enough varied data to measure a correlation."
    strength = "strong" if abs(r) >= 0.7 else "moderate" if abs(r) >= 0.4 else "weak"
    direction = "positive" if r > 0 else "negative"
    return f"Pearson r = {r:.2f} ({strength} {direction}), from np.corrcoef."
