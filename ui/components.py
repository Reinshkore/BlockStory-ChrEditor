"""复用组件：状态符号、问题表、差异表、信息栅格。"""

from __future__ import annotations

from typing import Any, Callable, Iterable

import pandas as pd
import streamlit as st

import i18n
from i18n import t
from model import Change, display_value
from ui import theme
from validate import Issue

SEV_ICON = {"error": "✕", "warn": "!", "info": "·"}


def status_symbol(issues: Iterable[Issue]) -> str:
    levels = {i.level for i in issues}
    if "error" in levels:
        return "✕"
    if "warn" in levels:
        return "!"
    if "info" in levels:
        return "·"
    return "✓"


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def kv(rows: list[tuple[str, str]], columns: int = 1) -> None:
    """紧凑的信息栅格（两列布局内使用）。"""
    html = ['<div style="display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:12.3px">']
    for key, value in rows:
        html.append(f'<div style="color:var(--bs-muted)">{key}</div>'
                    f'<div class="bs-mono" style="word-break:break-all">{value}</div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def issue_table(issues: list[Issue], key: str, limit: int = 300,
                on_pick: Callable[[str], None] | None = None) -> str | None:
    """渲染问题表；返回被选中的键（若启用选择）。"""
    if not issues:
        st.caption(t("sv.noIssues"))
        return None
    rows = []
    for issue in issues[:limit]:
        rows.append({
            t("fd.col.status"): SEV_ICON.get(issue.level, "·"),
            t("c.line"): issue.line,
            t("fd.col.key"): issue.key,
            t("fd.col.note"): i18n.issue_text(issue.code, issue.params),
        })
    df = pd.DataFrame(rows)
    if on_pick is None:
        st.dataframe(df, hide_index=True, width="stretch", height=min(80 + 34 * len(df), 420))
        return None

    event = st.dataframe(
        df, hide_index=True, width="stretch", height=min(80 + 34 * len(df), 420),
        on_select="rerun", selection_mode="single-row", key=key,
    )
    picked = None
    sel = getattr(event, "selection", None)
    selected = list(sel.get("rows", [])) if sel else []
    # 选中状态会一直留在会话里；不做去重的话每次重跑都会再触发一次跳转
    signature = tuple(selected)
    if selected and st.session_state.get(f"{key}_handled") != signature:
        st.session_state[f"{key}_handled"] = signature
        idx = selected[0]
        if 0 <= idx < len(rows):
            picked = rows[idx][t("fd.col.key")]
            on_pick(picked)
    if len(issues) > limit:
        st.caption(t("c.more", n=len(issues) - limit))
    return picked


def change_table(changes: list[Change], limit: int = 300) -> None:
    if not changes:
        st.caption(t("sv.noChanges"))
        return
    rows = []
    for ch in changes[:limit]:
        if ch.kind == "remove":
            new = "—"
            old = display_value(ch.old)
        elif ch.kind == "add":
            new = display_value(ch.new)
            old = "—"
        else:
            new = display_value(ch.new)
            old = display_value(ch.old)
        symbol = {"remove": "−", "add": "+", "modify": "~"}[ch.kind]
        rows.append({
            "": symbol,
            t("fd.col.key"): ch.key,
            "→": f"{old} → {new}",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 height=min(80 + 32 * len(rows), 460))
    if len(changes) > limit:
        st.caption(t("c.more", n=len(changes) - limit))


def section(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="bs-cat">{title}</div>', unsafe_allow_html=True)
    if sub:
        theme.note(sub)


def divider() -> None:
    st.markdown('<div class="bs-hr"></div>', unsafe_allow_html=True)
