"""Screening configurations: named weight sets, and which two the product compares."""

from __future__ import annotations

from html import escape

import streamlit as st

from modules.data_manager import MAX_CONFIGS
from modules.exceptions import DataFileError, RecordNotFoundError, ValidationError
from modules.screening_engine import COMPONENT_LABELS, COMPONENTS, ScreeningConfig
from ui import charts, state, theme

SEGMENT_COLORS = [charts.COMPONENT_COLORS[COMPONENT_LABELS[c]] for c in COMPONENTS]


def render() -> None:
    manager = state.get_manager()
    head, action = st.columns([4, 1], vertical_alignment="bottom")
    with head:
        theme.page_header(
            "Simulate a different screening configuration.",
            "A configuration is a set of weights over four components that add up to 100%. Every saved "
            "configuration is part of the sensitivity test, and two of them are compared throughout the product.",
            eyebrow="Configurations",
        )
    with action:
        if st.button("New configuration", type="primary", icon=":material/add:", width="stretch",
                     disabled=len(manager.configs) >= MAX_CONFIGS):
            config_dialog(None)

    render_comparison_picker(manager)
    theme.heading("Saved configurations", f"{len(manager.configs)} of at most {MAX_CONFIGS}. "
                                          "Each bar shows how the 100 points are split.")
    legend = "".join(f'<span style="margin-right:1rem"><span class="fl-key" style="background:{color};border-radius:2px">'
                     f'</span>{escape(COMPONENT_LABELS[c])}</span>' for c, color in zip(COMPONENTS, SEGMENT_COLORS))
    theme.html(f'<div class="fl-score-meta" style="margin-bottom:.8rem">{legend}</div>')
    for config in manager.configs.values():
        render_config(manager, config)


def render_comparison_picker(manager) -> None:
    ids = list(manager.configs)
    with theme.panel():
        theme.section_title("Compared configurations",
                            "The baseline is the reference; the alternative is shown next to it on every page.")
        c1, c2, c3 = st.columns([1.3, 1.3, 1], vertical_alignment="bottom")
        baseline = c1.selectbox("Baseline", ids, index=ids.index(manager.baseline_id),
                                format_func=lambda c: manager.configs[c].name, key="pick_baseline")
        alternative = c2.selectbox("Alternative", ids, index=ids.index(manager.alternative_id),
                                   format_func=lambda c: manager.configs[c].name, key="pick_alternative")
        if c3.button("Save comparison", width="stretch"):
            try:
                manager.set_comparison(baseline, alternative)
            except ValidationError as error:
                st.error(error.message, icon=":material/error:")
            except (RecordNotFoundError, DataFileError) as error:
                st.error(str(error), icon=":material/error:")
            else:
                state.flash(f"Now comparing {manager.baseline.name} with {manager.alternative.name}.")
                st.rerun()


def weight_bar(config: ScreeningConfig) -> str:
    segments = "".join(
        f'<div title="{escape(COMPONENT_LABELS[c])} {w:g}%" style="width:{w}%;background:{color};height:100%;'
        f'border-right:2px solid #fdfdfb"></div>'
        for c, w, color in zip(COMPONENTS, config.weights, SEGMENT_COLORS) if w)
    return f'<div style="display:flex;height:10px;border-radius:3px;overflow:hidden;margin:.55rem 0 .45rem">{segments}</div>'


def render_config(manager, config: ScreeningConfig) -> None:
    role = ("Baseline" if config.config_id == manager.baseline_id
            else "Alternative" if config.config_id == manager.alternative_id else "")
    color = theme.DATA_BLUE if role == "Baseline" else theme.DATA_ORANGE if role == "Alternative" else None
    with theme.panel():
        main, buttons = st.columns([4, 1.2], vertical_alignment="center")
        with main:
            badge = (f'<span class="rs-badge" style="background:#f3f2ed;color:#0b0b0b">'
                     f'<i style="background:{color}"></i>{role}</span>') if role else ""
            numbers = " · ".join(f"{COMPONENT_LABELS[c]} <b style='color:#0b0b0b'>{w:g}</b>"
                                 for c, w in config.weight_map.items())
            theme.html(
                f'<div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap">'
                f'<span style="font-size:1.02rem;font-weight:600;color:#0b0b0b">{escape(config.name)}</span>'
                f'<span class="rs-mono">{escape(config.config_id)}</span>{badge}</div>'
                f'{weight_bar(config)}<div class="fl-score-meta">{numbers}</div>'
                + (f'<div class="fl-score-meta" style="color:#898781;margin-top:.25rem">{escape(config.description)}</div>'
                   if config.description else "")
            )
        with buttons:
            edit_col, delete_col = st.columns(2, gap="small")
            if edit_col.button("Edit", key=f"cfg_edit_{config.config_id}", icon=":material/edit:", width="stretch"):
                config_dialog(config)
            if delete_col.button("Delete", key=f"cfg_del_{config.config_id}", icon=":material/delete:",
                                 width="stretch", disabled=bool(role), help="Choose another baseline/alternative first."
                                 if role else None):
                delete_config_dialog(config)


@st.dialog("Screening configuration", width="large")
def config_dialog(config: ScreeningConfig | None) -> None:
    manager = state.get_manager()
    editing = config is not None
    current = config.weight_map if editing else {"skills": 50, "projects": 20, "experience": 15, "education": 15}
    name = st.text_input("Name", value=config.name if editing else "", placeholder="e.g. Projects-heavy")
    description = st.text_input("Description (optional)", value=config.description if editing else "", max_chars=200)
    columns = st.columns(4)
    weights = {c: columns[i].number_input(f"{COMPONENT_LABELS[c]} %", 0, 100, int(current[c]), step=5,
                                          key=f"cfg_w_{config.config_id if editing else 'new'}_{c}")
               for i, c in enumerate(COMPONENTS)}
    total = sum(weights.values())
    theme.html(f'<div class="fl-score-meta">Total <b style="color:{"#0b0b0b" if total == 100 else "#b42f2f"}">'
               f'{total}%</b>{"" if total == 100 else " — must be exactly 100%"}</div>')
    if st.button("Save changes" if editing else "Create configuration", type="primary", disabled=total != 100):
        try:
            if editing:
                manager.update_config(config.config_id, name, weights, description)
            else:
                manager.create_config(name, weights, description)
        except ValidationError as error:
            st.error(error.message, icon=":material/error:")
        except (RecordNotFoundError, DataFileError) as error:
            st.error(str(error), icon=":material/error:")
        else:
            state.flash("Configuration saved. All scores have been recalculated.")
            st.rerun()


@st.dialog("Delete configuration")
def delete_config_dialog(config: ScreeningConfig) -> None:
    st.write(f"Delete **{config.name}**? It will no longer be part of the sensitivity test. "
             "Past audit summaries are kept.")
    cancel, confirm = st.columns(2)
    if cancel.button("Cancel", width="stretch"):
        st.rerun()
    if confirm.button("Delete", type="primary", width="stretch"):
        try:
            state.get_manager().delete_config(config.config_id)
        except ValidationError as error:
            st.error(error.message)
            return
        except (RecordNotFoundError, DataFileError) as error:
            st.error(str(error))
            return
        state.flash(f"{config.name} was deleted.")
        st.rerun()
