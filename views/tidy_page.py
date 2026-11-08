from __future__ import annotations

import streamlit as st

import tidy
from i18n import t
from model import SaveDoc, display_value
from ui import components as C
from ui import theme
from validate import ERROR

OPTIONS = (
    ("normalize", "td.normalize", "td.normalizeD"),
    ("reorder", "td.reorder", "td.reorderD"),
    ("drop_empty_slots", "td.dropEmpty", "td.dropEmptyD"),
    ("compact_indices", "td.compact", "td.compactD"),
)


def render(doc: SaveDoc, issues) -> None:
    theme.page_head(t("td.title"), t("td.sub"))

    values = {}
    for field, title, desc in OPTIONS:
        default = tidy.TidyOptions().__getattribute__(field)
        values[field] = st.toggle(f"**{t(title)}**", value=bool(st.session_state.get(f"t_{field}", default)),
                                  key=f"t_{field}", help=t(desc))
        theme.note(t(desc))

    opts = tidy.TidyOptions(**values)
    plan = tidy.build_plan(doc, opts)

    st.markdown('<div class="bs-cat">' + t("c.preview") + "</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(t("td.added"), plan.added)
    with c2:
        st.metric(t("td.removed"), plan.removed)
    with c3:
        st.metric(t("td.modified"), plan.modified)
    with c4:
        st.metric(t("td.fixesLabel"), plan.fixes)

    if plan.changes:
        with st.expander(t("td.previewHead"), expanded=False):
            C.change_table(plan.changes, limit=40)
    else:
        st.caption(t("td.nothing"))

    editable = st.session_state.editable
    if not editable:
        st.caption(t("fd.readonlyHint"))
    if st.button(t("td.apply"), type="primary", disabled=not editable or not plan.changes):
        tidy.apply_plan(doc, plan)
        st.toast(t("td.applied", removed=plan.removed, modified=plan.modified))
        st.rerun()
