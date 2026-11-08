from __future__ import annotations

import streamlit as st

import modeops
import schema
from i18n import t
from model import SaveDoc
from ui import components as C
from ui import theme


def render(doc: SaveDoc, issues) -> None:
    theme.page_head(t("md.title"), t("md.sub"))
    mode_counts = modeops.counts(doc)
    st.caption(" · ".join(f"{t(f'fd.mode.{mode}')} {mode_counts[mode]}"
                          for mode in schema.WORLD_MODES))
    action = st.segmented_control(
        "mode operation", ["copy", "clear"], default="copy", key=f"md_action_{doc.widget_id}",
        format_func=lambda value: t(f"md.action.{value}"), label_visibility="collapsed")
    populated = [mode for mode in schema.WORLD_MODES if mode_counts[mode]]
    if not populated:
        st.caption(t("md.noSource"))
        return
    if action == "copy":
        empty = [mode for mode in schema.WORLD_MODES if not mode_counts[mode]]
        if not empty:
            st.caption(t("md.noEmpty"))
            return
        c1, c2 = st.columns(2)
        with c1:
            source = st.selectbox(t("md.source"), populated, key=f"md_source_{doc.widget_id}",
                                  format_func=lambda mode: t(f"fd.mode.{mode}"))
        with c2:
            target = st.selectbox(t("md.target"), empty, key=f"md_target_{doc.widget_id}",
                                  format_func=lambda mode: t(f"fd.mode.{mode}"))
        plan = modeops.build_copy_plan(doc, source, target)
        theme.note(t("md.copyHint"))
        if target in {"creative", "sandbox"}:
            theme.note(t("md.questPolicy"))
        apply_label = t("md.applyCopy")
    else:
        source = st.selectbox(t("md.mode"), populated, key=f"md_clear_{doc.widget_id}",
                              format_func=lambda mode: t(f"fd.mode.{mode}"))
        plan = modeops.build_clear_plan(doc, source)
        theme.warnbox(t("md.clearHint"))
        apply_label = t("md.applyClear")
    theme.note(t("md.sharedNote"))
    if plan.error:
        theme.warnbox(t(plan.error))
    else:
        st.caption(t("md.keys", n=len(plan.changes)))
        if plan.skipped:
            st.caption(t("md.skipped", n=plan.skipped))
        with st.expander(t("rs.detail") + f" ({len(plan.changes)})"):
            C.change_table(plan.changes, limit=200)
    if st.button(apply_label, key=f"md_apply_{action}_{doc.widget_id}",
                 disabled=not st.session_state.editable or bool(plan.error) or not plan.changes):
        modeops.apply_plan(doc, plan)
        st.toast(t("md.applied"))
        st.session_state.nav = "save"
        st.rerun()
