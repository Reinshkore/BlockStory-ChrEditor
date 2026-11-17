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
    if step in (None, "", "#start"):
        return "start"
    if step in {"#end", "#end_dark_side"}:
        return "done"
    return "active"


def _line_name(line: str) -> str:
    return t("q.line.old") if line == "old" else t("q.line.current")


def render(doc: SaveDoc, issues) -> None:
    theme.page_head(t("q.title"), t("q.sub"))
    catalog = _catalog()
    line = questops.active_questline(doc)
    stats = questops.line_stats(doc, line)
    achievements = doc.achievements()
    recipes = doc.recipes()
    claimed = sum(1 for a in achievements if a["claimed"])

    _line_bar(doc, line, stats, recipes)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(t("q.quests"), stats["total"],
                  help=f"{t('q.done')} {stats['done']} · {t('q.active')} {stats['active']}")
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

    # 只渲染当前分区：st.tabs 会把所有标签页的正文都执行一遍，
    # 四个区加起来有 5 个表格和多份计划，用户却只看其中一个。
    if line == "old":
        sections = (("chain", "q.tab.chain"), ("side", "q.tab.side"), ("all", "q.tab.all"))
    else:
        sections = (("main", "q.tab.main"), ("side", "q.tab.side"),
                    ("daily", "q.tab.daily"), ("all", "q.tab.all"))
    ids = [sid for sid, _ in sections]
    labels = {sid: t(key) for sid, key in sections}
    picked = st.segmented_control(
        t("q.section"), ids, default=ids[0], key=f"q_section_{line}",
        format_func=lambda sid: labels[sid], label_visibility="collapsed") or ids[0]

    _section(doc, catalog, line, picked, achievements, recipes)


@st.fragment
def _section(doc: SaveDoc, catalog: gamedata.Catalog, line: str, picked: str,
             achievements, recipes) -> None:
    """分区正文单独成片：拖动滑块、切任务节点只重跑本区。"""
    if picked == "main":
        _mainline(doc, catalog)
    elif picked == "chain":
        _chain(doc, catalog)
    elif picked == "side":
        _side(doc, catalog, line)
    elif picked == "daily":
        _daily(doc, catalog)
    else:
        _all_progress(doc, achievements, recipes)


# --------------------------------------------------------------------------- #
# 任务线
# --------------------------------------------------------------------------- #

def _line_bar(doc: SaveDoc, line: str, stats: dict, recipes) -> None:
    counts = questops.line_key_counts(doc)
    other = "current" if line == "old" else "old"
    raw = doc.get(schema.QUEST_LINE_KEY)
    with st.container(border=True):
        left, right = st.columns([3, 1])
        with left:
            st.markdown(f"**{t('q.line.badge', name=_line_name(line))}**")
            st.caption(t("q.line.stats", **stats))
            if raw is None:
                st.caption(t("q.line.missing"))
            elif raw not in (0, 1):
                st.caption(t("q.line.mismatch", value=raw))
            if counts[other]:
                theme.warnbox(t("q.line.conflict", count=counts[other]))
        with right:
            if st.button(t("q.line.switch"), width="stretch",
                         key=f"q_line_switch_{doc.widget_id}"):
                st.session_state["q_line_dialog"] = True
    _line_dialog(doc, line, recipes)


def _line_dialog(doc: SaveDoc, line: str, recipes) -> None:
    if not st.session_state.get("q_line_dialog"):
        return
    target = "current" if line == "old" else "old"
    counts = questops.line_key_counts(doc)
    target_stats = questops.line_stats(doc, target)
    own = sum(1 for prefix, _name, _value in recipes
              if prefix.startswith("Old") == (line == "old"))
    other_recipes = len(recipes) - own

    @st.dialog(t("q.line.switch"))
    def _body() -> None:
        st.markdown(f"**{_line_name(line)} → {_line_name(target)}**")
        st.write(t("q.line.write", value=1 if target == "old" else 0))
        st.caption(t("q.line.otherKeys", count=counts[line]))
        st.caption(t("q.line.targetStats", total=target_stats["total"],
                     done=target_stats["done"]))
        st.caption(t("q.line.recipes", own=own, other=other_recipes))
        st.caption(t("q.line.recipeNote"))
        ok = st.checkbox(t("q.line.confirm"), key=f"q_line_ok_{line}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(t("q.line.apply"), type="primary", width="stretch",
                         disabled=not ok or not st.session_state.editable):
                questops.apply_plan(doc, questops.build_questline_plan(doc, target))
                st.session_state["q_line_dialog"] = False
                st.toast(t("q.line.done"))
                st.rerun()
        with c2:
            if st.button(t("c.cancel"), width="stretch"):
                st.session_state["q_line_dialog"] = False
                st.rerun()

    _body()


# --------------------------------------------------------------------------- #
# 主线（仅当前线）
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# 支线（两线共用）
# --------------------------------------------------------------------------- #

def _quest_label(doc: SaveDoc, catalog: gamedata.Catalog, line: str, title: str) -> str:
    quest = catalog.for_line(line).get(title)
    name = questops.quest_name(quest, lang()) if quest else title
    step = doc.get(schema.quest_key(line, "quest", title), "#start")
    return f"{name} — {t(f'q.{_quest_state(step)}')}"


def _side(doc: SaveDoc, catalog: gamedata.Catalog, line: str) -> None:
    defs = catalog.for_line(line)
    pool = [q for q in defs.values() if not q.daily and not q.shop]
    if line == "current":
        main_titles = {q.title for q in questops.mainline(catalog)}
        pool = [q for q in pool if q.title not in main_titles]
    if not pool:
        st.caption(t("c.none_yet"))
        return
    npcs = sorted({q.npc for q in pool if q.npc})
    all_label = t("q.all")
    c1, c2 = st.columns([1, 2])
    with c1:
        npc_choice = st.selectbox(t("q.npc"), [all_label, *npcs],
                                  key=f"q_npc_{line}_{doc.widget_id}")
    npc = "" if npc_choice == all_label else npc_choice
    narrowed = [q for q in pool if not npc or q.npc == npc]
    narrowed.sort(key=lambda q: questops.quest_name(q, lang()).casefold())
    labels = {q.title: _quest_label(doc, catalog, line, q.title) for q in narrowed}
    with c2:
        choice = st.selectbox(t("q.sidePick"), list(labels.values()),
                              key=f"q_side_{line}_{npc}_{doc.widget_id}")
    title = next((key for key, value in labels.items() if value == choice),
                 narrowed[0].title)
    quest = defs[title]
    _quest_detail(doc, quest, line)


def _quest_detail(doc: SaveDoc, quest: gamedata.QuestDef, line: str) -> None:
    key = schema.quest_key(line, "quest", quest.title)
    current = doc.get(key, "#start")
    deps = [dep for dep in quest.deps if dep]
    prereq = ", ".join(deps) if deps else t("q.prereqNone")
    st.markdown(f"**{questops.quest_name(quest, lang())}**")
    st.caption(f"{t('q.npc')} {quest.npc} · {t('q.prereq')}: {prereq} · "
               f"{t('q.current')}: {display_value(current)}")
    if deps and not all(questops.is_done(doc.get(schema.quest_key(line, "quest", dep)))
                        for dep in deps):
        theme.warnbox(t("q.prereqWarn"))

    steps = questops.editable_steps(quest)
    action_steps = [s for s in steps if s not in {"#start", "#end", "#end_dark_side"}]
    states = ["start"] + (["active"] if action_steps else []) + ["done"]
    state = _quest_state(current)
    default = state if state in states else "start"
    status = st.segmented_control(
        t("q.status"), states, default=default,
        format_func=lambda s: t(f"q.{s}"),
        key=f"q_status_{line}_{quest.title}_{doc.widget_id}")
    status = status or default

    step = "#start"
    if status == "active":
        stored = current if current in action_steps else action_steps[0]
        step = st.selectbox(t("q.step"), action_steps,
                            index=action_steps.index(stored) if stored in action_steps else 0,
                            key=f"q_step_{line}_{quest.title}_{doc.widget_id}")
        targets = questops.step_targets(quest, step)
        st.caption(t("q.targets"))
        if targets:
            st.markdown(" ".join(
                theme.badge(t("q.targetKill", name=name, count=count), "mute")
                for name, count in targets), unsafe_allow_html=True)
        else:
            st.caption(t("q.noTargets"))
    elif status == "done":
        endings = [e for e in ("#end", "#end_dark_side") if e in steps]
        if len(endings) > 1:
            step = st.selectbox(t("q.ending"), endings,
                                key=f"q_end_{line}_{quest.title}_{doc.widget_id}")
        else:
            step = "#end"

    plan = questops.build_quest_plan(doc, quest, step)
    st.caption(t("q.planCounts", add=plan.added, mod=plan.modified, rem=plan.removed))
    with st.expander(t("q.showPlan")):
        C.change_table(plan.changes, limit=100)
    if st.button(t("q.applySide"), type="primary", disabled=not st.session_state.editable,
                 key=f"q_apply_side_{line}_{quest.title}_{doc.widget_id}"):
        questops.apply_plan(doc, plan)
        st.toast(t("q.applied", n=len(plan.changes)))
        st.rerun()
    theme.note(t("q.sideNote"))


# --------------------------------------------------------------------------- #
# 任务链（仅旧线）
# --------------------------------------------------------------------------- #

def _pick_chain_node(title: str) -> None:
    st.session_state["q_chain_node"] = title


def _chain(doc: SaveDoc, catalog: gamedata.Catalog) -> None:
    forest = questops.old_forest(catalog)
    if not forest.defs:
        st.caption(t("c.none_yet"))
        return

    selected = st.session_state.get("q_chain_node")
    if selected not in forest.defs:
        selected = forest.order[0]

    labels = {}
    for title in forest.order:
        indent = "　" * forest.depth[title] + ("↳ " if forest.depth[title] else "")
        labels[title] = indent + questops.quest_name(forest.defs[title], lang())

    widths = [3.6, 1.2, 1.4, 0.9]
    head = st.columns(widths, vertical_alignment="center")
    for col, label in zip(head, (t("q.quest"), t("q.npc"), t("q.step"), t("q.chain.status"))):
        col.markdown(f'<div class="bs-chain-head">{label}</div>', unsafe_allow_html=True)

    with st.container(key="q_chain_list"):
        for title in forest.order:
            quest = forest.defs[title]
            step = doc.get(schema.quest_key("old", "quest", title), "#start")
            c1, c2, c3, c4 = st.columns(widths, vertical_alignment="center")
            c1.button(labels[title], key=f"q_chain_pick_{doc.widget_id}_{title}",
                      type="primary" if title == selected else "tertiary",
                      on_click=_pick_chain_node, args=(title,))
            c2.markdown(f'<div class="bs-chain-cell">{quest.npc}</div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="bs-chain-cell">{display_value(step)}</div>',
                        unsafe_allow_html=True)
            c4.markdown(theme.badge(t(f"q.{_quest_state(step)}"),
                                    "ok" if _quest_state(step) == "done"
                                    else "warn" if _quest_state(step) == "active" else "mute"),
                        unsafe_allow_html=True)

    st.caption(f"{t('q.chain.node')}: {labels[selected]}")
    mode = st.segmented_control(
        t("q.chain.mode"), ["complete", "reset"], default="complete",
        format_func=lambda m: t(f"q.chain.{m}"),
        key=f"q_chain_mode_{doc.widget_id}")
    mode = mode or "complete"
    plan = questops.build_chain_plan(doc, forest, selected, mode)
    affected = plan.metrics.get("quests", [])
    st.caption(t("q.chain.affected", n=len(affected), names=", ".join(affected[:6])))
    st.caption(t("q.planCounts", add=plan.added, mod=plan.modified, rem=plan.removed))
    with st.expander(t("q.showPlan")):
        C.change_table(plan.changes, limit=100)
    theme.note(t("q.chain.note"))
    if st.button(t("q.chain.apply"), type="primary", disabled=not st.session_state.editable,
                 key=f"q_chain_apply_{doc.widget_id}"):
        questops.apply_plan(doc, plan)
        st.toast(t("q.applied", n=len(plan.changes)))
        st.rerun()


# --------------------------------------------------------------------------- #
# 日常（仅当前线）
# --------------------------------------------------------------------------- #

def _daily(doc: SaveDoc, catalog: gamedata.Catalog) -> None:
    quests = sorted((q for q in catalog.quests.values() if q.daily),
                    key=lambda q: questops.quest_name(q, lang()).casefold())
    if not quests:
        st.caption(t("c.none_yet"))
        return
    labels = {q.title: questops.quest_name(q, lang()) for q in quests}
    choice = st.selectbox(t("q.dailyPick"), list(labels.values()),
                          key=f"q_daily_{doc.widget_id}")
    title = next((key for key, value in labels.items() if value == choice), quests[0].title)
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


# --------------------------------------------------------------------------- #
# 全部进度
# --------------------------------------------------------------------------- #

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
        rows.append({t("fd.col.key"): q["title"],
                     t("q.line.col"): _line_name(q["line"]),
                     t("q.step"): display_value(q["step"]),
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
            counter_rows.append({t("fd.col.key"): key,
                                 t("fd.col.value"): display_value(doc.values[key])})
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
    names = [("Old " if prefix.startswith("Old") else "") + name
             for prefix, name, _value in recipes if not needle or needle in name.lower()]
    if names:
        st.markdown(" ".join(theme.badge(n, "mute") for n in names), unsafe_allow_html=True)
    else:
        st.caption(t("c.none_yet"))
