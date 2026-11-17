from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import i18n
import schema
import storage
from i18n import t
from model import CoerceError, SaveDoc, coerce_input, display_value, kind_of
from ui import components as C
from ui import theme
from validate import ERROR, issue_index

VIEWS = ("category", "mode", "raw", "changed", "issues")
MODES = schema.WORLD_MODES
PAGE_SIZE = 200
MAX_PICK_OPTIONS = 300


def _mode_of(key: str) -> str:
    return schema.world_mode_of(key)


def _spec_label(spec: schema.FieldSpec | None, key: str) -> str:
    if spec is None:
        return key
    return spec.label_zh if i18n.lang() == "zh" else spec.label_en


def _note_short(spec: schema.FieldSpec | None, key: str) -> str:
    """表格里只放短标签；默认值与取值范围留给详情面板，否则一行塞不下。"""
    return _spec_label(spec, key) if spec else ""


def _note(spec: schema.FieldSpec | None) -> str:
    if spec is None:
        return ""
    label = _spec_label(spec, "")
    note = spec.note_zh if i18n.lang() == "zh" else spec.note_en
    return f"{label} · {note}" if note else label


def _apply_pending() -> None:
    pending = st.session_state.pop("pending", None)
    if pending:
        for key, value in pending.items():
            st.session_state[key] = value


def render(doc: SaveDoc, issues) -> None:
    theme.page_head(t("fd.title"), t("fd.sub", n=len(doc.values)))
    _body(doc, issues)


@st.fragment
def _body(doc: SaveDoc, issues) -> None:
    """筛选、表格与详情单独成片。

    搜索框每敲一个字、翻一页、换一个详情键都只重跑这一块，
    侧栏、状态栏和页面头部不再跟着重建。
    """
    ss = st.session_state
    _apply_pending()
    ss.setdefault("f_view", "category")
    ss.setdefault("f_search", "")

    idx = issue_index(issues)

    view = st.segmented_control(
        t("fd.view"), list(VIEWS), key="f_view",
        format_func=lambda v: t(f"fd.view.{v}"),
        label_visibility="collapsed",
    ) or "category"

    c1, c2, c3 = st.columns([2.2, 1, 1.6], vertical_alignment="bottom")
    with c1:
        search = st.text_input(t("c.search"), key="f_search", placeholder=t("c.search"))
    with c2:
        kind_pick = st.selectbox(
            t("fd.filterType"), ["all", "int", "float", "str"], key="f_kind",
            format_func=lambda k: t("c.all") if k == "all" else t(f"kind.{k}"))
    with c3:
        picked_cats = st.multiselect(
            t("fd.filterCat"), list(schema.CATEGORY_IDS), key="f_cats",
            format_func=lambda c: t(f"cat.{c}"), placeholder=t("c.all"),
        )

    keys = _select_keys(doc, view, idx, search, kind_pick, picked_cats)

    # 分页：一次只渲染 200 行。整表 1654 行会让每次输入都重发 170 KB，
    # 并且 data_editor 的 key 随筛选结果变化，整块重建会丢掉滚动位置。
    signature = (view, search, kind_pick, tuple(picked_cats))
    if ss.get("f_sig") != signature:
        ss.f_sig = signature
        ss.f_page = 0
    page_count = max(1, (len(keys) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(int(ss.get("f_page", 0)), page_count - 1))
    ss.f_page = page

    c1, c2, c3 = st.columns([0.6, 0.6, 4], vertical_alignment="center")
    with c1:
        if st.button("‹", key="f_prev", width="stretch", disabled=page <= 0):
            ss.f_page = page - 1
            page -= 1
    with c2:
        if st.button("›", key="f_next", width="stretch", disabled=page >= page_count - 1):
            ss.f_page = page + 1
            page += 1
    with c3:
        st.caption(f"{page + 1}/{page_count} · "
                   + t("c.showing", n=len(keys), total=len(doc.values)))

    visible = keys[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    if visible:
        _table(doc, visible, idx)
    else:
        st.caption(t("fd.empty"))

    if not ss.editable:
        st.caption(t("fd.readonlyHint"))

    st.markdown('<div class="bs-cat">' + t("fd.detail") + "</div>", unsafe_allow_html=True)
    _detail(doc, issues, idx)

    if issues:
        st.markdown('<div class="bs-cat">' + t("fd.view.issues") + "</div>", unsafe_allow_html=True)
        C.issue_table(issues, key="f_issues", on_pick=_focus)


def _focus(key: str) -> None:
    st.session_state["pending"] = {"f_search": key, "f_view": "category", "f_pickkey": key}
    st.session_state.nav = "fields"
    st.rerun()


def _select_keys(doc, view, idx, search, kind_pick, picked_cats) -> list[str]:
    keys = list(doc.order)

    if view == "changed":
        changed = {c.key for c in doc.changes()}
        keys = [k for k in keys if k in changed]
    elif view == "issues":
        keys = [k for k in keys if k in idx]

    if picked_cats:
        allowed = set(picked_cats)
        keys = [k for k in keys if doc.category(k) in allowed]
    if kind_pick != "all":
        keys = [k for k in keys if doc.kind(k) == kind_pick]
    if search:
        needle = search.strip().lower()
        keys = [k for k in keys
                if needle in k.lower() or needle in display_value(doc.values[k]).lower()]

    if view == "raw":
        return keys
    if view == "mode":
        return sorted(keys, key=lambda k: (MODES.index(_mode_of(k)), schema.natural_key(k)))
    pets = doc.pets()
    return sorted(keys, key=lambda k: schema.sort_rank(k, pets))


def _table(doc: SaveDoc, keys: list[str], idx) -> None:
    labels = st.session_state.labels
    changed = {c.key for c in doc.changes()}
    rows = []
    for key in keys:
        spec = doc.spec(key)
        issues_here = idx.get(key, [])
        symbol = C.status_symbol(issues_here)
        if key in changed:
            symbol = "• " + symbol
        rows.append({
            "_key": key,
            t("fd.col.key"): key,
            t("fd.col.value"): display_value(doc.values[key]),
            t("fd.col.type"): t(f"kind.{kind_of(doc.values[key])}"),
            t("fd.col.cat"): labels.get(key) or doc.category(key),
            t("fd.col.status"): symbol,
            t("fd.col.note"): _note_short(spec, key)[:28],
        })
    df = pd.DataFrame(rows).set_index("_key")

    edited = st.data_editor(
        df, width="stretch", height=min(70 + 34 * len(df), 560), hide_index=True,
        num_rows="fixed", disabled=not st.session_state.editable,
        key=f"editor_{view_token(keys)}",
        column_config={
            t("fd.col.key"): st.column_config.TextColumn(width="medium"),
            t("fd.col.value"): st.column_config.TextColumn(width="medium"),
            t("fd.col.type"): st.column_config.TextColumn(width="small"),
            t("fd.col.cat"): st.column_config.SelectboxColumn(
                options=list(schema.CATEGORY_IDS), width="medium",
                format_func=lambda c: t(f"cat.{c}")),
            t("fd.col.status"): st.column_config.TextColumn(width="small"),
            t("fd.col.note"): st.column_config.TextColumn(width="medium"),
        },
    )
    if st.session_state.editable:
        _apply_table_edits(doc, df, edited)


def view_token(keys: list[str]) -> str:
    return f"{len(keys)}_{abs(hash(tuple(keys[:3])))}"


def _apply_table_edits(doc: SaveDoc, before: pd.DataFrame, after: pd.DataFrame) -> None:
    if after is None or len(after) == 0:
        return
    pending: dict[str, Any] = {}
    label_changes: dict[str, str] = {}
    errors: list[str] = []
    vcol, ccol = t("fd.col.value"), t("fd.col.cat")

    for key in after.index:
        row, old_row = after.loc[key], before.loc[key]
        if row[vcol] != old_row[vcol]:
            spec = doc.spec(key)
            kind = spec.kind if spec else (doc.kind(key) or "str")
            try:
                value = coerce_input(str(row[vcol]), kind)
            except CoerceError as exc:
                hint = f" ({exc.hint})" if exc.hint else ""
                errors.append(t("fd.badInput", key=key, msg=str(exc) + hint))
                continue
            if value != doc.values.get(key):
                pending[str(key)] = value
        if row[ccol] != old_row[ccol]:
            label_changes[str(key)] = str(row[ccol])

    changed_values = 0
    if pending:
        doc.push_undo("edit")
        for key, value in pending.items():
            if doc.set(key, value):
                changed_values += 1

    if label_changes:
        labels = dict(st.session_state.labels)
        labels.update(label_changes)
        st.session_state.labels = labels
        storage.save_labels(doc.path.stem if doc.path else "upload", labels)

    if changed_values:
        st.toast(t("c.changed", n=changed_values))
        st.rerun()
    for message in errors[:5]:
        st.warning(message)


# --------------------------------------------------------------------------- #

def _pick_pool(keys: list[str], focus: str, query: str) -> list[str]:
    """详情下拉的候选：搜索过滤 + 上限；当前焦点必须留在列表里，否则控件值会失效。"""
    needle = query.strip().lower()
    pool = ([k for k in keys if needle in k.lower()] if needle else list(keys))[:MAX_PICK_OPTIONS]
    if focus in keys and focus not in pool:
        pool.insert(0, focus)
    return pool or keys[:1]


def _detail(doc: SaveDoc, issues, idx) -> None:
    ss = st.session_state
    keys = list(doc.order)
    if not keys:
        return
    focus = ss.get("f_pickkey")
    if focus not in keys:
        focus = keys[0]
    # 下拉只放前 300 项（可再搜索），避免每次重跑都传 1654 个选项。
    query = st.text_input(t("fd.pick"), key="f_pick_search", placeholder=t("c.search"),
                          label_visibility="collapsed")
    pool = _pick_pool(keys, focus, query)
    picked = st.selectbox(
        t("fd.pick"), pool, index=pool.index(focus) if focus in pool else 0,
        key="f_pickkey", label_visibility="collapsed",
    )

    spec = doc.spec(picked)
    current = doc.values.get(picked)
    expected = spec.kind if spec else kind_of(current)

    with st.container(border=True):
        head = [
            theme.badge(t(f"kind.{expected}"), "mute"),
            theme.badge(t(f"cat.{ss.labels.get(picked) or doc.category(picked)}"), "mute"),
            theme.badge(t("c.line", n=doc.line_of(picked)), "mute"),
        ]
        if spec and spec.default is not None:
            head.append(theme.badge(t("fd.default", value=display_value(spec.default)), "mute"))
        if spec and (spec.vmin is not None or spec.vmax is not None):
            lo = "−∞" if spec.vmin is None else f"{spec.vmin:g}"
            hi = "∞" if spec.vmax is None else f"{spec.vmax:g}"
            head.append(theme.badge(t("fd.range", min=lo, max=hi), "mute"))
        st.markdown(" ".join(head), unsafe_allow_html=True)
        theme.note(_note(spec) or t("val.W_UNKNOWN"))

        for issue in idx.get(picked, []):
            text = i18n.issue_text(issue.code, issue.params)
            (theme.errbox if issue.level == ERROR else theme.warnbox)(text)

        editable = ss.editable
        c1, c2, c3, c4 = st.columns([3, 0.8, 1.1, 1], vertical_alignment="bottom")
        with c1:
            candidate = _value_widget(picked, expected, current, editable)
        with c2:
            st.markdown(f"<div class='bs-mono' style='padding-bottom:.55rem;color:var(--bs-muted)'>"
                        f"{display_value(current)}</div>", unsafe_allow_html=True)
        with c3:
            if st.button(t("fd.resetDefault"), width="stretch",
                         disabled=not editable or spec is None or spec.default is None,
                         key="d_reset"):
                if doc.set(picked, spec.default):
                    st.rerun()
        with c4:
            if st.button(t("fd.deleteKey"), width="stretch", disabled=not editable, key="d_del"):
                doc.push_undo(f"delete:{picked}")
                doc.delete(picked)
                ss.pop("f_pickkey", None)
                st.rerun()

        if editable and candidate != current:
            st.button(
                f"{t('c.apply')}  {display_value(current)} → {display_value(candidate)}",
                type="primary", key="d_apply",
                on_click=_apply_value, args=(doc, picked, candidate),
            )

        _family_row(doc, picked, ss)


def _value_widget(key: str, kind: str, current: Any, editable: bool) -> Any:
    # 把当前值编进 widget key：值被外部改动（恢复默认、撤销、重置）后能拿到新控件，
    # 否则 Streamlit 会继续显示旧文本。
    stamp = display_value(current) if current is not None else ""
    widget_key = f"d_{kind}_{key}_{abs(hash(stamp)) % 100000}"
    if kind == "int" and isinstance(current, int) and not isinstance(current, bool):
        return int(st.number_input(t("fd.col.value"), value=int(current), step=1,
                                   disabled=not editable, key=widget_key))
    # 浮点与文本都用文本框：number_input 的格式化会吃掉 .6000001 这类精度
    text = "" if current is None else display_value(current)
    raw = st.text_input(t("fd.col.value"), value=text, disabled=not editable, key=widget_key)
    if not editable:
        return current
    try:
        return coerce_input(raw, kind)
    except CoerceError:
        return current


def _apply_value(doc: SaveDoc, key: str, value: Any) -> None:
    doc.push_undo(f"edit:{key}")
    doc.set(key, value)


def _family_row(doc: SaveDoc, key: str, ss) -> None:
    family = schema.family_of(key)
    siblings = [k for k in doc.order if schema.family_of(k) == family]
    if len(siblings) < 2:
        return
    cat = ss.labels.get(key) or doc.category(key)
    st.caption(f"{t('fd.filterCat')}: {t(f'cat.{cat}')} · {len(siblings)}")
    if st.button(f"{t('c.apply')} → {len(siblings)}", key="d_family"):
        labels = dict(ss.labels)
        for sibling in siblings:
            labels[sibling] = cat
        ss.labels = labels
        storage.save_labels(doc.path.stem if doc.path else "upload", labels)
        st.toast(t("c.changed", n=len(siblings)))
        st.rerun()
