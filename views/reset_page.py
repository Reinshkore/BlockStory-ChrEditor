from __future__ import annotations

import streamlit as st

import gamedata
import reset as reset_mod
import schema
from i18n import t
from model import SaveDoc, display_value
from ui import components as C
from ui import theme

@st.cache_resource(show_spinner=False)
def _catalog() -> gamedata.Catalog:
    return gamedata.load_catalog()


CARDS = (
    (reset_mod.OP_LEVEL, "rs.op.level", "rs.op.levelD"),
    (reset_mod.OP_ATTRS, "rs.op.attributes", "rs.op.attributesD"),
    (reset_mod.OP_QUESTS, "rs.op.quests", "rs.op.questsD"),
    (reset_mod.OP_PETS, "rs.op.pets", "rs.op.petsD"),
    (reset_mod.OP_FULL, "rs.op.full", "rs.op.fullD"),
)


def render(doc: SaveDoc, issues) -> None:
    theme.page_head(t("rs.title"), t("rs.sub"))
    for op, title_key, desc_key in CARDS:
        _card(doc, op, title_key, desc_key)
    _after(doc)


@st.fragment
def _card(doc: SaveDoc, op: str, title_key: str, desc_key: str) -> None:
    """每张卡单独成片：切换"同步配方"之类的选项只重算这一张的计划。

    五张卡各建一份计划（每份都扫全档），整页重跑时五份一起重算，
    而用户一次只动一张。
    """
    editable = st.session_state.editable
    plan = _plan(doc, op)
    with st.container(border=True):
        head = [f"**{t(title_key)}**"]
        if plan.modified:
            head.append(theme.badge(t("rs.willModify", n=plan.modified), "warn"))
        if plan.removed:
            head.append(theme.badge(t("rs.willRemove", n=plan.removed), "err"))
        if not plan.changes:
            head.append(theme.badge(t("c.nochange"), "mute"))
        st.markdown(" ".join(head), unsafe_allow_html=True)
        theme.note(t(desc_key))

        if op == reset_mod.OP_FULL:
            theme.warnbox(t("rs.fullWarn"))

        if op == reset_mod.OP_LEVEL:
            mode = st.radio(
                t("rs.skillMode"),
                [reset_mod.SKILL_CLAMP, reset_mod.SKILL_RAW],
                horizontal=True,
                format_func=lambda m: t(f"rs.skillMode.{m}"),
                key="r_skillmode",
                help=t("rs.skillModeHint"),
            )
            theme.note(t("rs.skillModeHint"))
            plan = _plan(doc, op, skill_mode=mode)

        if op == reset_mod.OP_QUESTS:
            catalog = _catalog()
            sync_recipes = st.toggle(
                t("rs.questRecipes"), key="r_quest_recipes",
                help=t("rs.questRecipesHint"), disabled=bool(catalog.error))
            theme.note(t("rs.questRecipesHint"))
            if catalog.error:
                theme.warnbox(t("it.catalogError", msg=catalog.error, path=catalog.source))
            plan = _plan(doc, op, sync_quest_recipes=sync_recipes, catalog=catalog)

        for code, params in plan.notes:
            theme.warnbox(t(code, **params))

        if plan.changes:
            with st.expander(t("rs.detail") + f" ({len(plan.changes)})"):
                C.change_table(plan.changes, limit=200)

        if st.button(t("rs.apply"), key=f"r_apply_{op}", type="primary" if op == reset_mod.OP_FULL else "secondary",
                     disabled=not editable or not plan.changes):
            reset_mod.apply_plan(doc, plan)
            st.toast(t("rs.applied", op=t(title_key)))
            st.session_state.nav = "save"
            st.rerun()

    _after(doc)


def _plan(doc: SaveDoc, op: str, skill_mode: str = reset_mod.SKILL_CLAMP,
          sync_quest_recipes: bool = False, catalog=None):
    return reset_mod.build_plan(doc, op, skill_mode=skill_mode,
                                sync_quest_recipes=sync_quest_recipes, catalog=catalog)


def _after(doc: SaveDoc) -> None:
    snap = reset_mod.skill_snapshot(doc.values)
    st.markdown('<div class="bs-cat">' + t("rs.after") + "</div>", unsafe_allow_html=True)
    attr_bits = " · ".join(
        f"{display_value(doc.get(a.key))}" for a in schema.POINT_ATTRIBUTES[:3]
    )
    with st.container(border=True):
        C.kv([
            (t("ov.level"), f"{snap['level']}"),
            (t("ov.skill"), f"{snap['unspent']} / {snap['total']}"),
            (t("ov.pointsSum", invested=snap["invested"]), f"{snap['invested']}"),
            (t("q.quests"), f"{len(doc.quests())}"),
            (t("q.achieve"), f"{len(doc.achievements())}"),
            (t("q.recipes"), f"{len(doc.recipes())}"),
            ("Max Health / Mana / Breath", attr_bits),
        ])
