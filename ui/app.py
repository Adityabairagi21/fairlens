"""Streamlit entry point. Run with ``python main.py`` or ``streamlit run ui/app.py``."""

import sys
from html import escape
from pathlib import Path

# Streamlit runs this file as a script, so make the project root importable.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from modules.exceptions import DataFileError  # noqa: E402
from ui import state, theme  # noqa: E402
from ui.views import (  # noqa: E402
    analytics_view, audit_view, candidate_detail, candidates, compare, competence_view, configurations, dashboard,
    jobs, method, reports_view,
)

st.set_page_config(
    page_title="FairLens",
    page_icon=":material/center_focus_strong:",
    layout="wide",
    initial_sidebar_state="auto",
)
theme.inject_css()
st.session_state["_panel_n"] = 0  # reset the panel key counter each run


def data_file_banner() -> None:
    """Explain corrupted files and offer a safe recovery instead of crashing."""
    manager = state.get_manager()
    for key, message in list(manager.load_errors.items()):
        with theme.panel():
            st.error(message, icon=":material/error:")
            if key == "taxonomy":   # hand-edited reference data: never recreated automatically
                st.caption("Fix or restore data/skills_taxonomy.json, then use Reload data on the Method page.")
                continue
            st.caption(
                f"The rest of the app still works. Starting a fresh {manager.paths[key].name} keeps a copy of "
                "the damaged file next to it so nothing is lost."
            )
            if st.button(f"Start a fresh {manager.paths[key].name}", key=f"reset-{key}"):
                try:
                    backup = manager.reset_file(key)
                    note = f" Old file saved as {backup.name}." if backup else ""
                    state.flash(f"Created a new {manager.paths[key].name}.{note}")
                except DataFileError as error:
                    state.flash(str(error), icon=":material/error:")
                st.rerun()
    if manager.skipped_records:
        with st.expander(f"{len(manager.skipped_records)} record(s) could not be loaded and were skipped"):
            for line in manager.skipped_records:
                st.caption(line)


st.logo(str(ROOT / "ui" / "assets" / "logo.svg"), size="large")

sections = {
    "Analyse": [
        st.Page(dashboard.render, title="Overview", icon=":material/insights:", url_path="overview", default=True),
        st.Page(audit_view.render, title="Screening audit", icon=":material/rule:", url_path="audit"),
        st.Page(competence_view.render, title="Competence audit", icon=":material/manage_search:",
                url_path="competence"),
        st.Page(compare.render, title="Compare strategies", icon=":material/compare_arrows:", url_path="compare"),
    ],
    "Evidence": [
        st.Page(candidates.render, title="Candidates", icon=":material/group:", url_path="candidates"),
        st.Page(candidate_detail.render, title="Candidate", icon=":material/person:", url_path="candidate",
                visibility="hidden"),
        st.Page(jobs.render, title="Roles", icon=":material/work:", url_path="roles"),
        st.Page(analytics_view.render, title="Pool analytics", icon=":material/bar_chart:", url_path="analytics"),
    ],
    "Setup": [
        st.Page(configurations.render, title="Configurations", icon=":material/tune:", url_path="configurations"),
        st.Page(reports_view.render, title="Reports & data", icon=":material/description:", url_path="reports"),
        st.Page(method.render, title="Method", icon=":material/menu_book:", url_path="method"),
    ],
}

st.session_state.pages = {page.url_path: page for pages in sections.values() for page in pages}
navigation = st.navigation(sections, position="sidebar")

state.show_flash()
data_file_banner()
navigation.run()

# Rendered after the page so the counts include any change the page just made.
with st.sidebar:
    manager = state.get_manager()
    theme.html(
        '<div style="margin-top:1.2rem;padding:.8rem .2rem 0;border-top:1px solid #e4e2da;font-size:.74rem;'
        'color:#52514e;line-height:1.7">'
        f'<div><span class="fl-key" style="background:{theme.DATA_BLUE}"></span>Baseline · '
        f'<b style="color:#0b0b0b">{escape(manager.baseline.name)}</b></div>'
        f'<div><span class="fl-key" style="background:{theme.DATA_ORANGE}"></span>Alternative · '
        f'<b style="color:#0b0b0b">{escape(manager.alternative.name)}</b></div>'
        f'<div style="color:#898781;margin-top:.3rem">{len(manager.candidates)} candidates · '
        f'{len(manager.jobs)} roles</div></div>'
    )
