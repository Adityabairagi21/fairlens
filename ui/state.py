"""Session state helpers shared by every view."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from modules import analytics
from modules.analytics import AnalyticsEngine
from modules.audit import AuditEngine, AuditReport
from modules.competence import CompetenceAuditEngine, CompetenceResult
from modules.data_manager import DataManager
from modules.screening_engine import ScreeningEngine, ScreeningResult
from modules.semantic_matcher import SemanticMatcher
from modules.sensitivity import SensitivityAnalyzer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"


def get_manager() -> DataManager:
    """One DataManager per browser session, loaded from disk on first use."""
    if "manager" not in st.session_state:
        st.session_state.manager = DataManager(DATA_DIR)
    return st.session_state.manager


# Engines are cheap to build, so they are created per call and always reflect
# the configurations currently saved; nothing stale is cached between reruns.

def baseline_engine() -> ScreeningEngine:
    return ScreeningEngine(get_manager().baseline)


def alternative_engine() -> ScreeningEngine:
    return ScreeningEngine(get_manager().alternative)


def sensitivity_analyzer() -> SensitivityAnalyzer:
    return SensitivityAnalyzer(list(get_manager().configs.values()))


def audit_engine(baseline_id: str | None = None, alternative_id: str | None = None) -> AuditEngine:
    manager = get_manager()
    baseline = manager.configs.get(baseline_id or "", manager.baseline)
    alternative = manager.configs.get(alternative_id or "", manager.alternative)
    return AuditEngine(baseline, alternative, list(manager.configs.values()))


def run_audit(job_id: str | None = None) -> AuditReport:
    return audit_engine().run(get_manager(), job_id)


def competence_engine(similarity: bool = False) -> CompetenceAuditEngine:
    """The competence audit under the baseline configuration; similarity hints only when asked for."""
    manager = get_manager()
    return CompetenceAuditEngine(manager.taxonomy, manager.baseline, SemanticMatcher() if similarity else None)


def competence_results(job_id: str | None = None) -> list[CompetenceResult]:
    return competence_engine().assess_many(analytics.screening_pairs(get_manager(), job_id))


def current_results() -> dict[str, ScreeningResult]:
    """Every candidate scored against their target role under the baseline configuration."""
    return AnalyticsEngine(get_manager(), get_manager().baseline).results


def candidate_frame():
    return AnalyticsEngine(get_manager(), get_manager().baseline).candidate_frame()


# --- one-shot messages that survive a rerun -------------------------------------------------

def flash(message: str, icon: str = ":material/check_circle:") -> None:
    st.session_state.setdefault("flash", []).append((message, icon))


def show_flash() -> None:
    for message, icon in st.session_state.pop("flash", []):
        st.toast(message, icon=icon)


def switch_to(page_name: str) -> None:
    """Navigate to a page registered by app.py (e.g. "candidates")."""
    st.switch_page(st.session_state.pages[page_name])


def open_candidate(candidate_id: str) -> None:
    st.session_state.detail_candidate = candidate_id
    switch_to("candidate")
