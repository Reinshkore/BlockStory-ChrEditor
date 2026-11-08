"""任务快捷编辑：主线阶段、支线完成/重置、日常次数。

所有操作先在完整键表的副本上预演，应用时只产生一个撤销点。
这里允许补齐游戏约定的 `Quest:` / `Quest Complete:` 键；字段页仍禁止任意新增键。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gamedata import Catalog, QuestDef
from model import Change, SaveDoc, kind_of

MAINLINE_END = "The Grand Finale"
MAINLINE_START = "Tutorial"


@dataclass
class QuestPlan:
    op: str
    values: dict[str, Any]
    order: list[str]
    changes: list[Change] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def modified(self) -> int:
        return sum(c.kind == "modify" for c in self.changes)

    @property
    def added(self) -> int:
        return sum(c.kind == "add" for c in self.changes)

    @property
    def removed(self) -> int:
        return sum(c.kind == "remove" for c in self.changes)


def quest_name(quest: QuestDef, lang: str) -> str:
    translated = {"zh": quest.zh, "ru": quest.ru, "pt": quest.pt, "es": quest.es}.get(lang, "")
    name = translated or quest.en or quest.title
    return f"{name} — {quest.title}" if name != quest.title else quest.title


def mainline(catalog: Catalog) -> list[QuestDef]:
    """沿终章的前置依赖回推主线；不把猎人悬赏等同长支线混进来。"""
    chain: list[QuestDef] = []
    seen: set[str] = set()
    title = MAINLINE_END
    while title in catalog.quests and title not in seen:
        seen.add(title)
        quest = catalog.quests[title]
        chain.append(quest)
        if title == MAINLINE_START:
            break
        # 当前主线每一环都只有一个前置；若未来出现多前置，选择已能回到 Tutorial 的分支。
        candidates = [catalog.quests[d] for d in quest.deps if d in catalog.quests]
        title = candidates[0].title if candidates else ""
    chain.reverse()
    if not chain or chain[0].title != MAINLINE_START:
        return []
    return chain


def current_mainline_stage(doc: SaveDoc, chain: list[QuestDef]) -> int:
    """第一个尚未完成的主线任务下标；全部完成则等于链长。"""
    for index, quest in enumerate(chain):
        if not _is_done(doc.values.get(f"Quest: {quest.title}")):
            return index
    return len(chain)


def completed_after_gap(doc: SaveDoc, chain: list[QuestDef]) -> list[str]:
    """非连续存档中，位于首个缺口之后却已完成的任务。应用阶段预设会将它们重置。"""
    stage = current_mainline_stage(doc, chain)
    return [quest.title for quest in chain[stage + 1:]
            if _is_done(doc.values.get(f"Quest: {quest.title}"))]


def _is_done(step: Any) -> bool:
    return step in {"#end", "#end_dark_side"}


def _clear_step_progress(work: dict[str, Any], title: str) -> None:
    prefix = f"Quest: {title} "
    for key in [k for k in work if k.startswith(prefix)]:
        del work[key]


def _put(work: dict[str, Any], key: str, value: Any) -> None:
    work[key] = value


def build_mainline_plan(doc: SaveDoc, chain: list[QuestDef], stage: int,
                        step: str | None = None, *, catalog: Catalog | None = None,
                        sync_recipes: bool = False, sync_side: bool = False) -> QuestPlan:
    """stage=N：前 N 个主线完成；可选联动只作用于明确声明的游戏关系。"""
    if not chain:
        raise ValueError("mainline unavailable")
    stage = max(0, min(int(stage), len(chain)))
    work = dict(doc.values)
    for index, quest in enumerate(chain):
        _clear_step_progress(work, quest.title)
        if index < stage:
            target = "#end"
        elif index == stage:
            options = valid_steps(quest)
            target = step if step in options else "#start"
        else:
            target = "#start"
        _put(work, f"Quest: {quest.title}", target)

    metrics: dict[str, Any] = {
        "stage": stage, "total": len(chain),
        "current": chain[stage].title if stage < len(chain) else "",
        "step": step or ("#end" if stage == len(chain) else "#start"),
        "recipes_changed": 0, "side_reset": [],
    }
    if sync_side and catalog:
        metrics["side_reset"] = _reset_locked_side_quests(work, catalog, chain)
    if sync_recipes:
        metrics["recipes_changed"] = _sync_mainline_recipes(work, chain, catalog)
    return _make_plan(doc, work, "mainline", metrics)


def _recipe_still_provided(work: dict[str, Any], recipe: str, catalog: Catalog) -> bool:
    """同名配方可能由当前或旧任务线的多个任务提供，任一已完成来源都存在就保留。"""
    for title, recipes in catalog.quest_recipes.items():
        if recipe not in recipes:
            continue
        if _is_done(work.get(f"Quest: {title}")) or _is_done(work.get(f"Old Quest: {title}")):
            return True
    return False


def _sync_mainline_recipes(work: dict[str, Any], chain: list[QuestDef],
                           catalog: Catalog | None) -> int:
    if catalog is None:
        catalog = Catalog(quests={q.title: q for q in chain},
                          quest_recipes={q.title: q.recipes for q in chain if q.recipes})
    before = dict(work)
    for quest in chain:
        for recipe in quest.recipes:
            key = f"Recipe: {recipe}"
            if _is_done(work.get(f"Quest: {quest.title}")):
                work[key] = 1
            elif not _recipe_still_provided(work, recipe, catalog):
                work.pop(key, None)
    return sum(before.get(key) != work.get(key) or (key in before) != (key in work)
               for key in set(before) | set(work))


def _reset_locked_side_quests(work: dict[str, Any], catalog: Catalog,
                              chain: list[QuestDef]) -> list[str]:
    """重置依赖已失效的非主线任务；级联处理依赖其他支线的任务。"""
    main_titles = {quest.title for quest in chain}
    candidates = [quest for quest in catalog.quests.values() if quest.title not in main_titles]
    reset: list[str] = []
    processed: set[str] = set()
    changed = True
    while changed:
        changed = False
        for quest in candidates:
            if quest.title in processed or not quest.deps:
                continue
            if all(_is_done(work.get(f"Quest: {dep}")) for dep in quest.deps):
                continue
            key = f"Quest: {quest.title}"
            affected = ((key in work and work[key] != "#start")
                        or any(k.startswith(f"{key} ") for k in work)
                        or f"Quest Complete: {quest.title}" in work
                        or f"Daily: {quest.title}" in work)
            if key in work and work[key] != "#start":
                work[key] = "#start"
            _clear_step_progress(work, quest.title)
            work.pop(f"Quest Complete: {quest.title}", None)
            work.pop(f"Daily: {quest.title}", None)
            if affected:
                reset.append(quest.title)
            # 未开始且无键的任务也标记为已处理，但不虚增“实际重置”数量。
            processed.add(quest.title)
            changed = True
    return reset


def valid_steps(quest: QuestDef) -> list[str]:
    steps = list(dict.fromkeys(quest.steps))
    for end in ("#end", "#end_dark_side"):
        if end not in steps:
            steps.append(end)
    return steps


def build_side_plan(doc: SaveDoc, quest: QuestDef, action: str,
                    ending: str = "#end") -> QuestPlan:
    if action not in {"complete", "reset"}:
        raise ValueError(action)
    work = dict(doc.values)
    key = f"Quest: {quest.title}"
    _clear_step_progress(work, quest.title)
    if action == "complete":
        _put(work, key, ending if ending in {"#end", "#end_dark_side"} else "#end")
    else:
        _put(work, key, "#start")
        work.pop(f"Quest Complete: {quest.title}", None)
        work.pop(f"Daily: {quest.title}", None)
    return _make_plan(doc, work, f"side:{action}", {"title": quest.title, "action": action})


def daily_slider_upper(current: int, tiers: tuple[int, ...]) -> int:
    """当前值上方始终留出至少 5 次，阈值上方也保留可继续调整的空间。"""
    return max(10, int(current) + 5, (max(tiers) if tiers else 0) + 5)


def build_daily_plan(doc: SaveDoc, quest: QuestDef, count: int,
                     state: str = "keep") -> QuestPlan:
    if state not in {"keep", "completed", "reset"}:
        raise ValueError(state)
    work = dict(doc.values)
    _put(work, f"Quest Complete: {quest.title}", max(0, int(count)))
    if state != "keep":
        _clear_step_progress(work, quest.title)
        _put(work, f"Quest: {quest.title}", "#end" if state == "completed" else "#start")
    if state == "reset":
        work.pop(f"Daily: {quest.title}", None)
    return _make_plan(doc, work, "daily", {
        "title": quest.title, "count": max(0, int(count)), "state": state,
    })


def _make_plan(doc: SaveDoc, work: dict[str, Any], op: str,
               metrics: dict[str, Any]) -> QuestPlan:
    order = [key for key in doc.order if key in work]
    seen = set(order)
    order.extend(key for key in work if key not in seen)
    changes: list[Change] = []
    for key, value in work.items():
        if key not in doc.values:
            changes.append(Change("add", key, None, value))
        elif kind_of(doc.values[key]) != kind_of(value) or doc.values[key] != value:
            changes.append(Change("modify", key, doc.values[key], value))
    for key, value in doc.values.items():
        if key not in work:
            changes.append(Change("remove", key, value, None))
    return QuestPlan(op=op, values=work, order=order, changes=changes, metrics=metrics)


def apply_plan(doc: SaveDoc, plan: QuestPlan) -> None:
    doc.push_undo(f"quest:{plan.op}")
    doc.values = dict(plan.values)
    doc.reorder([key for key in plan.order if key in doc.values])
