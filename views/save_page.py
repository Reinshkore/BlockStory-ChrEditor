from __future__ import annotations

from pathlib import Path

import streamlit as st

import storage
import tidy
from i18n import t
from model import SaveDoc, display_value
from ui import components as C
from ui import theme
from validate import ERROR, WARN

CONFIRM_KEYS = ("sv_ok1", "sv_ok2", "sv_ok3")


def render(doc: SaveDoc, issues) -> None:
    ss = st.session_state
    theme.page_head(t("sv.title"), t("sv.sub"))

    result = ss.get("write_result")
    if result is not None:
        _result_panel(doc, result)

    errors = [i for i in issues if i.level == ERROR]
    warns = [i for i in issues if i.level == WARN]
    add, mod, rem = doc.change_counts()
    total = add + mod + rem

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(t("sv.blocking"), len(errors))
    with c2:
        st.metric(t("sv.warnings"), len(warns))
    with c3:
        st.metric(t("sv.changes"), total,
                  help=t("sv.summary", add=add, mod=mod, rem=rem))

    # ── 阻断项 ──────────────────────────────────────────────────
    st.markdown('<div class="bs-cat">' + t("sv.issues") + "</div>", unsafe_allow_html=True)
    if errors:
        C.issue_table(errors, key="sv_errors", limit=120)
        type_errors = [i for i in errors if i.code == "E_TYPE"]
        if type_errors:
            theme.warnbox(t("td.normalizeD"))
            if st.button(t("td.normalize"), key="sv_fix", disabled=not ss.editable):
                plan = tidy.build_plan(doc, tidy.TidyOptions(
                    normalize=True, reorder=False, drop_empty_slots=False,
                    compact_indices=False))
                tidy.apply_plan(doc, plan, label="normalize")
                if plan.touched:
                    st.toast(t("td.applied", removed=0, modified=plan.touched))
                st.rerun()
    else:
        st.caption(t("sv.noIssues"))

    if warns:
        with st.expander(t("sv.warnings") + f" ({len(warns)})"):
            C.issue_table(warns, key="sv_warns", limit=120)

    # ── 变更清单 ────────────────────────────────────────────────
    st.markdown('<div class="bs-cat">' + t("sv.diff") + "</div>", unsafe_allow_html=True)
    changes = doc.changes()
    C.change_table(changes, limit=200)

    if not ss.editable:
        st.caption(t("sv.readonly"))
    elif not changes:
        st.caption(t("sv.noChanges"))

    # ── 目标路径 ────────────────────────────────────────────────
    target = doc.path
    if target is None:
        st.markdown('<div class="bs-cat">' + t("side.path") + "</div>", unsafe_allow_html=True)
        typed = st.text_input(t("side.path"), key="sv_path",
                              placeholder=str(storage.save_dir() / "char.chr"))
        if typed.strip():
            target = Path(typed.strip().strip('"'))

    # ── 确认与写入 ──────────────────────────────────────────────
    st.markdown('<div class="bs-cat">' + t("sv.write") + "</div>", unsafe_allow_html=True)
    ok1 = st.checkbox(t("sv.confirm1"), key=CONFIRM_KEYS[0], help=t("sv.confirm1D"))
    ok2 = st.checkbox(
        t("sv.confirm2"), key=CONFIRM_KEYS[1],
        help=t("sv.confirm2D", stem=(target.stem if target else "char"), keep=storage.KEEP_BACKUPS))
    ok3 = st.checkbox(t("sv.confirm3"), key=CONFIRM_KEYS[2], help=t("sv.confirm3D"))
    ack = st.checkbox(t("sv.ackWarn", n=len(warns)), value=not warns, key="sv_ack",
                      disabled=not warns)

    ready = bool(ss.editable and changes and not errors and ok1 and ok2 and ok3 and ack and target)
    if st.button(t("sv.write"), type="primary", disabled=not ready, width="stretch"):
        _write(doc, target)

    if errors:
        theme.errbox(t("sv.blocked", n=len(errors)))
    elif not (ok1 and ok2 and ok3):
        st.caption(t("sv.needConfirm"))

    _backups(doc)

    b1, b2 = st.columns(2)
    with b1:
        st.download_button(
            t("sv.export"), data=doc.serialize().encode("utf-8"),
            file_name=(target.name if target else "character.chr"),
            mime="application/json", width="stretch", disabled=not doc.values,
        )
    with b2:
        if st.button(t("sv.revertAll"), width="stretch", disabled=not changes):
            fresh = storage.read_save(doc.path) if doc.path else None
            if fresh is not None:
                ss.doc = fresh
            else:
                doc.push_undo("revert")
                doc.order = list(doc.original_order)
                doc.values = dict(doc.original)
            ss.write_result = None
            st.toast(t("sv.reverted"))
            st.rerun()


def _backups(doc: SaveDoc) -> None:
    if not doc.path:
        return
    backups = storage.list_backups(doc.path)
    with st.expander(t("sv.backups") + f" ({len(backups)})"):
        if not backups:
            st.caption(t("sv.backupNone"))
            return
        confirm = st.checkbox(t("sv.restoreWarn"), key="sv_restore_ok")
        for index, backup in enumerate(backups[:10]):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            with c1:
                size = backup.stat().st_size if backup.exists() else 0
                st.markdown(f"<span class='bs-mono'>{backup.name}</span> "
                            f"<span class='bs-note'>· {size:,} B</span>", unsafe_allow_html=True)
            with c2:
                if st.button(t("sv.restore"), key=f"sv_restore_{index}", disabled=not confirm,
                             width="stretch"):
                    try:
                        storage.restore_backup(backup, doc.path)
                    except storage.SaveError as exc:
                        st.error(t("sv.failed", stage=exc.stage, msg=str(exc)))
                    else:
                        fresh = storage.read_save(doc.path)
                        st.session_state.doc = fresh
                        st.session_state.write_result = None
                        st.session_state.editable = False
                        st.toast(t("sv.restored", name=backup.name))
                        st.rerun()


def _write(doc: SaveDoc, target: Path) -> None:
    try:
        result = storage.write_save(doc, target)
    except storage.SaveError as exc:
        st.session_state.write_result = None
        st.error(t("sv.failed", stage=exc.stage, msg=str(exc)))
        return
    doc.mark_saved(doc.serialize())
    doc.path = result.path
    st.session_state.path = result.path
    st.session_state.write_result = result
    st.session_state.editable = False
    st.rerun()


def _result_panel(doc: SaveDoc, result) -> None:
    with st.container(border=True):
        st.markdown(f"**{t('sv.done')}**")
        st.markdown(theme.badge(
            t("sv.doneMsg", size=f"{result.size:,}", path=str(result.path)), "ok"),
            unsafe_allow_html=True)
        if result.backup:
            st.caption(t("sv.backup", path=str(result.backup)))
        if result.identical_to_original:
            st.caption(t("sv.identical"))
    if st.button(t("c.close"), key="sv_close"):
        st.session_state.write_result = None
        st.rerun()
