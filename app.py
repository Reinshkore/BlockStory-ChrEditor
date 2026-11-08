"""Block Story 存档编辑器 —— Streamlit 入口。

运行：  .venv\\Scripts\\python.exe -m streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

import filepick  # noqa: E402
import gamedata  # noqa: E402
import i18n  # noqa: E402
import modeview  # noqa: E402
import schema  # noqa: E402
import storage  # noqa: E402
import validate  # noqa: E402
from i18n import t  # noqa: E402
from ui import theme  # noqa: E402
from views import fields, items, mode_page, overview, quests, reset_page, save_page, tidy_page  # noqa: E402

PAGES = {
    "overview": overview,
    "fields": fields,
    "items": items,
    "quests": quests,
    "tidy": tidy_page,
    "reset": reset_page,
    "modes": mode_page,
    "save": save_page,
}

NAV_ORDER = ("overview", "fields", "items", "quests", "tidy", "reset", "modes", "save")


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("lang", i18n.load_saved_language())
    ss.setdefault("language_dialog", False)
    ss.setdefault("nav", "overview")
    ss.setdefault("mode", "story")
    ss.setdefault("doc", None)
    ss.setdefault("path", None)
    ss.setdefault("editable", False)
    ss.setdefault("focus_key", None)
    ss.setdefault("labels", {})
    ss.setdefault("flash", [])
    ss.setdefault("write_result", None)
    ss.setdefault("slot_target", None)
    ss.setdefault("loaded_once", False)
    ss.setdefault("pending_load", None)

    # 支持 ?page=fields&lang=zh 直达，便于分享与自动化截图
    if not ss.loaded_once:
        ss.loaded_once = True
        page = st.query_params.get("page")
        if page in PAGES:
            ss["nav"] = page
        lang_q = st.query_params.get("lang")
        if lang_q in i18n.LANGS:
            i18n.set_lang(lang_q)
        mode_q = st.query_params.get("mode")
        if mode_q in schema.WORLD_MODES:
            ss.mode = mode_q


def flash(level: str, text: str) -> None:
    st.session_state.setdefault("flash", []).append((level, text))


def load_path(path: Path) -> bool:
    try:
        doc = storage.read_save(path)
    except storage.SaveError as exc:
        flash("error", t("side.encrypted", msg=f"{exc}"))
        return False
    request_doc(doc, Path(path), Path(path).stem)
    return True


def request_doc(doc, path: Path | None, label: str) -> None:
    """载入前守住未保存改动；pending_load 由主区域的确认框处理。"""
    current = st.session_state.doc
    if current is not None and not current.is_pristine():
        st.session_state.pending_load = (doc, path, label)
    else:
        _install_doc(doc, path, label)


def _install_doc(doc, path: Path | None, label: str) -> None:
    st.session_state.doc = doc
    st.session_state.path = path
    st.session_state.labels = storage.load_labels(label)
    st.session_state.focus_key = None
    st.session_state.write_result = None
    st.session_state.slot_target = None
    st.session_state.item_move_source = None
    st.session_state.editable = False
    st.session_state.pending_load = None


def current_issues(doc):
    return validate.validate(doc, catalog=_game_catalog()) if doc else []


@st.cache_resource(show_spinner=False)
def _game_catalog() -> gamedata.Catalog:
    return gamedata.load_catalog()


@st.cache_resource(show_spinner=False)
def _game_version() -> str:
    version = _game_catalog().version
    return version or "14.5.3"


# --------------------------------------------------------------------------- #
# 侧栏
# --------------------------------------------------------------------------- #

def render_sidebar() -> None:
    ss = st.session_state
    with st.sidebar:
        with st.container(key="bs_brandrow"):
            c1, c2 = st.columns([1.3, 1], vertical_alignment="center")
            with c1:
                st.markdown(theme.brand(t("app.title"), t("app.subtitle")),
                            unsafe_allow_html=True)
            with c2:
                if st.button("🌐 Language", key="_langbtn", width="stretch",
                             help=t("side.lang")):
                    ss.language_dialog = True
                    st.rerun()

        _render_loader()

        doc = ss.doc
        if doc is None:
            st.caption(t("side.noSaves", dir=str(storage.save_dir())))
            return

        st.markdown('<div class="bs-hr"></div>', unsafe_allow_html=True)
        editable = st.toggle(t("side.edit"), value=ss.editable, help=t("side.editHint"))
        if ss.editable and not editable:
            items.close_transients(ss)
        ss.editable = editable

        st.markdown(f'<div class="bs-cat">{t("side.nav")}</div>', unsafe_allow_html=True)
        _render_nav()

        add, mod, rem = doc.change_counts()
        total = add + mod + rem
        if total:
            st.markdown(theme.badge(t("side.unsaved", n=total), "warn"), unsafe_allow_html=True)
            if st.button(t("side.undo"), width="stretch"):
                label = doc.undo()
                st.toast(t("side.undoLabel", label=label) if label else t("side.noUndo"))
                st.rerun()
        else:
            st.caption(t("c.nochange"))

        st.markdown('<div class="bs-hr"></div>', unsafe_allow_html=True)
        st.caption(t("side.multiplayer"))
        st.caption(f"v{_game_version()}")


def _render_nav() -> None:
    """用按钮而不是 st.radio：Streamlit 的单选框只有点中最左侧的小圆圈才响应，
    点文字没有反应——导航几乎全是文字，用户会以为坏了。"""
    ss = st.session_state
    for pid in NAV_ORDER:
        active = ss.nav == pid
        key = f"nav_{'on' if active else 'off'}_{pid}"
        if st.button(t(f"nav.{pid}"), key=key, width="stretch"):
            items.close_transients(ss)
            ss.language_dialog = False
            ss.nav = pid
            st.rerun()


def _render_loader() -> None:
    saves = storage.list_saves()
    if saves:
        ss = st.session_state
        labels = {s.name: f"{s.character or s.name} · {t('ov.level')} {s.level if s.level is not None else '?'}" for s in saves}
        names = [s.name for s in saves]
        current = ss.path.stem if ss.path else None
        if ss.pop("_reset_save_picker", False):
            ss.side_save_pick = current if current in names else names[0]
        index = names.index(current) if current in names else 0

        def _on_pick() -> None:
            selected = next((s for s in saves if s.name == ss.side_save_pick), None)
            if selected is not None and not selected.error:
                load_path(selected.path)

        picked = st.selectbox(t("side.save"), names, index=index, key="side_save_pick",
                              format_func=lambda n: labels.get(n, n), on_change=_on_pick)

        def _on_mode() -> None:
            items.close_transients(ss)

        st.selectbox(t("side.mode"), schema.WORLD_MODES, key="mode",
                     format_func=lambda mode: t(f"fd.mode.{mode}"), on_change=_on_mode)
        info = next((s for s in saves if s.name == picked), None)
        if info is not None:
            if info.error:
                st.caption(t("side.encrypted", msg=info.error))
            else:
                st.caption(f"{info.character} · {t('c.keys', n=info.keys)} · {info.mtime_text}")
            if ss.doc is None and not info.error:
                if load_path(info.path):
                    st.rerun()
        if ss.doc is not None and ss.path is not None:
            if st.button(t("side.reload"), width="stretch", help=t("side.reloadHint")):
                load_path(ss.path)
                st.rerun()
    else:
        st.caption(t("side.noSaves", dir=str(storage.save_dir())))

    with st.expander(t("side.browse"), expanded=not saves):
        if st.button(t("side.browseFile"), width="stretch", help=t("side.browseHint"),
                     key="pickfile"):
            try:
                picked = filepick.pick_file(storage.save_dir(), t("side.browseTitle"))
            except RuntimeError as exc:
                flash("error", t("side.browseFail", msg=str(exc)))
            else:
                if picked and load_path(Path(picked)):
                    st.rerun()
        st.caption(t("side.orTypePath"))
        path_text = st.text_input(t("side.path"), value="", placeholder=r"C:\...\char.chr")
        if st.button(t("side.open"), disabled=not path_text.strip()):
            candidate = Path(path_text.strip().strip('"'))
            if candidate.is_file():
                if load_path(candidate):
                    st.rerun()
            else:
                flash("error", t("side.encrypted", msg=str(candidate)))
        uploaded = st.file_uploader(t("side.upload"), type=["chr", "json", "txt"])
        if uploaded is not None:
            raw = uploaded.getvalue().decode("utf-8", errors="replace")
            from model import SaveDoc

            try:
                doc = SaveDoc.from_text(raw, path=None)
            except Exception as exc:  # noqa: BLE001
                flash("error", t("side.encrypted", msg=str(exc)))
            else:
                request_doc(doc, None, uploaded.name)
                st.rerun()


def _confirm_load() -> None:
    pending = st.session_state.get("pending_load")
    if not pending:
        return
    doc, path, label = pending

    @st.dialog(t("side.unsavedTitle"))
    def _body() -> None:
        st.warning(t("side.unsavedLoad", name=label))
        c1, c2 = st.columns(2)
        with c1:
            if st.button(t("side.discardOpen"), type="primary", width="stretch"):
                _install_doc(doc, path, label)
                st.rerun()
        with c2:
            if st.button(t("side.keepWorking"), width="stretch"):
                st.session_state.pending_load = None
                st.session_state._reset_save_picker = True
                st.rerun()

    _body()


def _choose_language() -> None:
    ss = st.session_state
    if not ss.get("language_dialog"):
        return

    @st.dialog("Language")
    def _body() -> None:
        selected = st.radio(
            t("side.langDialog"), i18n.LANGS,
            index=i18n.LANGS.index(ss.lang) if ss.lang in i18n.LANGS else 0,
            format_func=lambda code: i18n.LANG_LABEL[code], key="language_choice")
        st.caption(t("side.langSaved"))
        c1, c2 = st.columns(2)
        with c1:
            if st.button(t("c.apply"), type="primary", width="stretch"):
                i18n.set_lang(selected, persist=True)
                st.query_params["lang"] = selected
                ss.language_dialog = False
                st.rerun()
        with c2:
            if st.button(t("c.cancel"), width="stretch"):
                ss.language_dialog = False
                st.rerun()

    _body()


# --------------------------------------------------------------------------- #
# 主体
# --------------------------------------------------------------------------- #

def main() -> None:
    st.set_page_config(
        page_title="Block Story Save Editor",
        page_icon="▧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    if st.session_state.get("active_nav") != st.session_state.nav:
        # 不论通过侧栏、直达链接还是浏览器导航，进入 Items 都不恢复旧弹窗。
        items.close_transients(st.session_state)
        st.session_state.active_nav = st.session_state.nav
    theme.inject()
    render_sidebar()
    _confirm_load()
    _choose_language()

    for level, message in st.session_state.pop("flash", []) or []:
        {"error": st.error, "warn": st.warning, "info": st.info}.get(level, st.info)(message)

    full_doc = st.session_state.doc
    if full_doc is None:
        _welcome()
        return

    full_page = st.session_state.nav in {"save", "modes"}
    doc = full_doc if full_page else modeview.ModeViewDoc(full_doc, st.session_state.mode)
    issues = current_issues(doc)
    _status_bar(doc, issues)
    PAGES[st.session_state.nav].render(doc, issues)


def _status_bar(doc, issues) -> None:
    counts = validate.counts(issues)
    add, mod, rem = doc.change_counts()
    left, right = st.columns([3, 2], vertical_alignment="center")
    with left:
        name = doc.get("charName") or (doc.path.stem if doc.path else "—")
        mode = _mode_name()
        bits = [f"<b>{name}</b>", f"<span style='color:var(--bs-muted)'>{mode}</span>"]
        level = doc.get("Current Level")
        if isinstance(level, int):
            bits.append(theme.badge(f"{t('ov.level')} {level}", "mute"))
        bits.append(theme.badge(t("c.keys", n=len(doc.values)), "mute"))
        if not st.session_state.editable:
            bits.append(theme.badge(t("side.editOff"), "mute"))
        st.markdown(
            "<div class='bs-top'>" + " ".join(bits) + "</div>", unsafe_allow_html=True)
    with right:
        c1, c2, c3 = st.columns([1, 1, 1.2])
        with c1:
            if counts.get("error"):
                st.markdown(theme.badge(f"{counts['error']} {t('c.error')}", "err"),
                            unsafe_allow_html=True)
            else:
                st.markdown(theme.badge(t("c.ok"), "ok"), unsafe_allow_html=True)
        with c2:
            if counts.get("warn"):
                st.markdown(theme.badge(f"{counts['warn']} {t('c.warn')}", "warn"),
                            unsafe_allow_html=True)
            else:
                st.markdown(theme.badge("0 " + t("c.warn"), "mute"), unsafe_allow_html=True)
        with c3:
            if mod + add + rem:
                st.markdown(theme.badge(t("c.changed", n=mod + add + rem), "warn"),
                            unsafe_allow_html=True)
            else:
                st.markdown(theme.badge(t("c.nochange"), "mute"), unsafe_allow_html=True)
    st.markdown('<div class="bs-hr"></div>', unsafe_allow_html=True)


def _mode_name() -> str:
    return t(f"fd.mode.{st.session_state.mode}")


def _welcome() -> None:
    theme.page_head(t("app.title"), t("side.noSaves", dir=str(storage.save_dir())))
    theme.note(t("side.multiplayer"))


main()
