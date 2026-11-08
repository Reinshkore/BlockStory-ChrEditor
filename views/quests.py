from __future__ import annotations

import pandas as pd
import streamlit as st

import gamedata
import questops
import schema
from i18n import lang, t
from model import SaveDoc, display_value
from ui import components as C
from ui import theme


@st.cache_resource(show_spinner=False)
def _catalog() -> gamedata.Catalog:
    return gamedata.load_catalog()


def _quest_state(step) -> str:
    if step == "#start":
        return "start"
    if step in {"#end", "#end_dark_side"}:
        return "done"
    return "active"


def render(doc: SaveDoc, issues) -> None:
    theme.page_head(t("q.title"), t("q.sub"))
    catalog = _catalog()
    quests = doc.quests()
    achievements = doc.achievements()
    recipes = doc.recipes()
    done = sum(1 for q in quests if _quest_state(q["step"]) == "done")
    active = sum(1 for q in quests if _quest_state(q["step"]) == "active")
    claimed = sum(1 for a in achievements if a["claimed"])

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(t("q.quests"), len(quests), help=f"{t('q.done')} {done} · {t('q.active')} {active}")
    with c2:
        st.metric(t("q.achieve"), len(achievements), help=f"{t('q.claimed')} {claimed}")
    with c3:
        st.metric(t("q.recipes"), len(recipes))
    if catalog.error:
        theme.warnbox(t("it.catalogError", msg=catalog.error, path=catalog.source))
        _all_progress(doc, achievements, recipes)
        return
    if st.session_state.mode in {"creative", "sandbox"}:
        theme.note(t("q.disabledMode"))
        _all_progress(doc, achievements, recipes)
        return

    tab_main, tab_side, tab_daily, tab_all = st.tabs(
        [t("q.tab.main"), t("q.tab.side"), t("q.tab.daily"), t("q.tab.all")])
    with tab_main:
        _mainline(doc, catalog)
    with tab_side:
        _side(doc, catalog)
    with tab_daily:
        _daily(doc, catalog)
    with tab_all:
        _all_progress(doc, achievements, recipes)


def _mainline(doc: SaveDoc, catalog: gamedata.Catalog) -> None:
    chain = questops.mainline(catalog)
    if not chain:
        st.caption(t("q.noMainline"))
        return
    actual = questops.current_mainline_stage(doc, chain)
    later_done = questops.completed_after_gap(doc, chain)
    if later_done:
        theme.warnbox(t("q.mainGap", names=", ".join(later_done)))
    st.caption(t("q.mainHint", n=len(chain)))
    stage = st.slider(t("q.mainStage"), 0, len(chain), value=actual,
                      key=f"q_main_stage_{doc.widget_id}")
    if stage < len(chain):
        current = chain[stage]
        st.markdown(f"**{stage} / {len(chain)} · {questops.quest_name(current, lang())}**")
        steps = questops.valid_steps(current)
        stored = doc.get(f"Quest: {current.title}")
        default = stored if stage == actual and stored in steps else "#start"
        step = st.selectbox(t("q.mainStep"), steps,
                            index=steps.index(default) if default in steps else 0,
                            key=f"q_main_step_{doc.widget_id}_{stage}")
    else:
        step = "#end"
        st.markdown(f"**{len(chain)} / {len(chain)} · {t('q.mainComplete')}**")
    sync_recipes = st.toggle(t("q.syncRecipes"), key=f"q_sync_recipes_{doc.widget_id}",
                             help=t("q.syncRecipesHint"))
    sync_side = st.toggle(t("q.syncSide"), key=f"q_sync_side_{doc.widget_id}",
                          help=t("q.syncSideHint"))
    plan = questops.build_mainline_plan(
        doc, chain, stage, step, catalog=catalog,
        sync_recipes=sync_recipes, sync_side=sync_side)
    st.caption(t("q.planCounts", add=plan.added, mod=plan.modified, rem=plan.removed))
    if sync_recipes or sync_side:
        st.caption(t("q.syncSummary", recipes=plan.metrics["recipes_changed"],
                     quests=len(plan.metrics["side_reset"])))
    with st.expander(t("q.showPlan")):
        C.change_table(plan.changes, limit=100)
        rows = []
        for index, quest in enumerate(chain):
            target = "#end" if index < stage else (step if index == stage else "#start")
            rows.append({t("q.stage"): index + 1, t("q.quest"): questops.quest_name(quest, lang()),
                         t("q.targetStep"): target})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    theme.note(t("q.mainNote"))
    if st.button(t("q.applyMain"), type="primary", disabled=not st.session_state.editable):
        questops.apply_plan(doc, plan)
        st.toast(t("q.applied", n=len(plan.changes)))
        st.rerun()


def _side(doc: SaveDoc, catalog: gamedata.Catalog) -> None:
    main_titles = {q.title for q in questops.mainline(catalog)}
    quests = [q for q in catalog.quests.values()
              if not q.daily and q.title not in main_titles]
    quests.sort(key=lambda q: questops.quest_name(q, lang()).casefold())
    if not quests:
        st.caption(t("c.none_yet"))
        return
    title = st.selectbox(t("q.sidePick"), [q.title for q in quests],
                         format_func=lambda x: questops.quest_name(catalog.quests[x], lang()),
                         key=f"q_side_{doc.widget_id}")
    quest = catalog.quests[title]
    current = doc.get(f"Quest: {title}", "#start")
    st.caption(f"{t('q.current')}: {display_value(current)} · NPC {quest.npc}")
    ending = "#end"
    if current == "#end_dark_side":
        ending = st.selectbox(t("q.ending"), ["#end_dark_side", "#end"], key="q_side_ending")
    c1, c2 = st.columns(2)
    with c1:
        if st.button(t("q.completeSide"), width="stretch", disabled=not st.session_state.editable):
            questops.apply_plan(doc, questops.build_side_plan(doc, quest, "complete", ending))
            st.toast(t("q.applied", n=1))
            st.rerun()
    with c2:
        if st.button(t("q.resetSide"), width="stretch", disabled=not st.session_state.editable):
            questops.apply_plan(doc, questops.build_side_plan(doc, quest, "reset"))
            st.toast(t("q.applied", n=1))
            st.rerun()
    theme.note(t("q.sideNote"))


def _daily(doc: SaveDoc, catalog: gamedata.Catalog) -> None:
    quests = sorted((q for q in catalog.quests.values() if q.daily),
                    key=lambda q: questops.quest_name(q, lang()).casefold())
    if not quests:
        st.caption(t("c.none_yet"))
        return
    title = st.selectbox(t("q.dailyPick"), [q.title for q in quests],
                         format_func=lambda x: questops.quest_name(catalog.quests[x], lang()),
                         key=f"q_daily_{doc.widget_id}")
    quest = catalog.quests[title]
    current = int(doc.get(f"Quest Complete: {title}", 0) or 0)
    upper = questops.daily_slider_upper(current, quest.daily_tiers)
    count = st.slider(t("q.dailyCount"), 0, upper, value=current,
                      key=f"q_daily_count_{doc.widget_id}_{title}")
    if quest.daily_tiers:
        st.caption(t("q.dailyTiers", tiers=", ".join(map(str, quest.daily_tiers))))
    else:
        st.caption(t("q.dailyNoTiers"))
    state = st.segmented_control(
        t("q.dailyState"), ["keep", "completed", "reset"], default="keep",
        format_func=lambda x: t(f"q.dailyState.{x}"), key=f"q_daily_state_{doc.widget_id}_{title}")
    plan = questops.build_daily_plan(doc, quest, count, state or "keep")
    st.caption(t("q.planCounts", add=plan.added, mod=plan.modified, rem=plan.removed))
    if st.button(t("q.applyDaily"), type="primary", disabled=not st.session_state.editable):
        questops.apply_plan(doc, plan)
        st.toast(t("q.applied", n=len(plan.changes)))
        st.rerun()
    theme.note(t("q.dailyNote"))


def _all_progress(doc: SaveDoc, achievements, recipes) -> None:
    theme.warnbox(t("q.trap"))
    search = st.text_input(t("c.search"), key="q_search", placeholder=t("c.search"))
    needle = (search or "").strip().lower()
    quests = doc.quests()
    st.markdown('<div class="bs-cat">' + t("q.quests") + "</div>", unsafe_allow_html=True)
    rows = []
    for q in quests:
        if needle and needle not in q["title"].lower():
            continue
        rows.append({t("fd.col.key"): q["title"], t("q.step"): display_value(q["step"]),
                     "": t(f"q.{_quest_state(q['step'])}"), t("q.times"): q["times"],
                     t("q.daily"): (q["daily"] or "")[:19]})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     height=min(80 + 32 * len(rows), 420))
    else:
        st.caption(t("c.none_yet"))

    counter_rows = []
    for key in doc.order:
        rest = key.split("Quest: ", 1)[-1] if "Quest: " in key else ""
        if rest and schema.QUEST_PROG_RE.match(rest) and (not needle or needle in key.lower()):
            counter_rows.append({t("fd.col.key"): key, t("fd.col.value"): display_value(doc.values[key])})
    if counter_rows:
        st.markdown('<div class="bs-cat">' + t("q.counters") + "</div>", unsafe_allow_html=True)
        st.caption(t("q.countersHint"))
        st.dataframe(pd.DataFrame(counter_rows), hide_index=True, width="stretch",
                     height=min(80 + 32 * len(counter_rows), 300))

    st.markdown('<div class="bs-cat">' + t("q.achieve") + "</div>", unsafe_allow_html=True)
    arows = []
    for a in achievements:
        if needle and needle not in a["title"].lower():
            continue
        prog = ", ".join(f"{k[len(a['title']):].strip()}={v}" for k, v in a["progress"])
        arows.append({t("fd.col.key"): a["title"],
                      "": t("q.claimed") if a["claimed"] else t("q.unclaimed"),
                      t("q.progress"): prog})
    if arows:
        st.dataframe(pd.DataFrame(arows), hide_index=True, width="stretch",
                     height=min(80 + 32 * len(arows), 420))
    else:
        st.caption(t("c.none_yet"))

    st.markdown('<div class="bs-cat">' + t("q.recipes") + "</div>", unsafe_allow_html=True)
    names = [name for name, value in recipes if not needle or needle in name.lower()]
    if names:
        st.markdown(" ".join(theme.badge(n, "mute") for n in names), unsafe_allow_html=True)
    else:
        st.caption(t("c.none_yet"))
