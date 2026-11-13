"""任务快捷编辑：主线阶段、支线完成/重置、日常次数。

所有操作先在完整键表的副本上预演，应用时只产生一个撤销点。
这里允许补齐游戏约定的 `Quest:` / `Quest Complete:` 键；字段页仍禁止任意新增键。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gamedata import Catalog, QuestDef
from model import Change, SaveDoc, kind_of
import schema

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


def _clear_step_progress(work: dict[str, Any], title: str, line: str = "current") -> None:
    """只删除该任务自己的步骤计数键。

    不能只用 `f"Old Quest: {title} "` 做前缀：任务名可能互为前缀
    （`Dancing Lessons` 与 `Dancing Lessons II`），那样会误删下一环的键。
    """
    head = f"{schema.quest_prefix(line)}Quest: {title}"
    for key in list(work):
        if key == head:
            continue
        if not key.startswith(head + " "):
            continue
        match = schema.QUEST_PROG_RE.match(key[len(schema.quest_prefix(line)) + len("Quest: "):])
        if match and match.group("title") == title:
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


def is_done(value: Any) -> bool:
    """对外暴露的完成判定：供页面做前置检查。"""
    return _is_done(value)


def build_side_plan(doc: SaveDoc, quest: QuestDef, action: str,
                    ending: str = "#end") -> QuestPlan:
    if action not in {"complete", "reset"}:
        raise ValueError(action)
    line = quest.line
    work = dict(doc.values)
    key = schema.quest_key(line, "quest", quest.title)
    _clear_step_progress(work, quest.title, line)
    if action == "complete":
        _put(work, key, ending if ending in {"#end", "#end_dark_side"} else "#end")
    else:
        _put(work, key, "#start")
        work.pop(schema.quest_key(line, "complete", quest.title), None)
        work.pop(schema.quest_key(line, "daily", quest.title), None)
    return _make_plan(doc, work, f"side:{action}", {"title": quest.title, "action": action,
                                                    "line": line})


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


# --------------------------------------------------------------------------- #
# 任务线：当前 / 旧
# --------------------------------------------------------------------------- #

def active_questline(doc: SaveDoc) -> str:
    return schema.quest_line(doc.get(schema.QUEST_LINE_KEY, 0))


def line_stats(doc: SaveDoc, line: str) -> dict[str, int]:
    rows = [row for row in doc.quests() if row["line"] == line]
    done = sum(1 for row in rows if _is_done(row["step"]))
    start = sum(1 for row in rows if row["step"] in {"#start", ""})
    return {"total": len(rows), "done": done,
            "active": len(rows) - done - start, "start": start}


def line_key_counts(doc: SaveDoc) -> dict[str, int]:
    """两套键族各自有多少键；用于切换任务线前的确认信息。"""
    current = ("Quest: ", "Quest Complete: ", "Daily: ", "Recipe: ")
    old = ("Old Quest: ", "Old Quest Complete: ", "Old Daily: ", "Old Recipe: ")
    counts = {"current": 0, "old": 0}
    for key in doc.order:
        if key.startswith(old):
            counts["old"] += 1
        elif key.startswith(current):
            counts["current"] += 1
    return counts


def editable_steps(quest: QuestDef) -> list[str]:
    """可写步骤：#start、XML 声明的步骤与 #end。旧线不提供暗面结局。"""
    steps = list(dict.fromkeys(quest.steps))
    if "#end" not in steps:
        steps.append("#end")
    if quest.line != "old" and "#end_dark_side" not in steps:
        steps.append("#end_dark_side")
    return steps


def step_targets(quest: QuestDef, step: str) -> list[tuple[str, int]]:
    """某步骤的目标摘要，只读展示用：[(目标名, 数量)]。"""
    return [(target.target, target.count) for target in quest.targets
            if target.step == step]


@dataclass
class QuestForest:
    defs: dict[str, QuestDef]
    roots: list[str]
    children: dict[str, list[str]]
    parent: dict[str, str]
    depth: dict[str, int]
    order: list[str]

    def path_to(self, title: str) -> list[str]:
        chain: list[str] = []
        seen: set[str] = set()
        node = title
        while node and node not in seen:
            seen.add(node)
            chain.append(node)
            node = self.parent.get(node, "")
        chain.reverse()
        return chain

    def subtree(self, title: str) -> list[str]:
        out: list[str] = []
        stack = [title]
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(reversed(self.children.get(node, [])))
        return out


def old_forest(catalog: Catalog) -> QuestForest:
    """旧任务线是单亲森林：4 个根、严格树形。商店任务不参与。"""
    defs = {title: quest for title, quest in catalog.old_quests.items() if not quest.shop}
    children: dict[str, list[str]] = {title: [] for title in defs}
    parent: dict[str, str] = {}
    roots: list[str] = []
    for title, quest in defs.items():
        linked = [dep for dep in quest.deps if dep in defs]
        if linked:
            parent[title] = linked[0]
            children[linked[0]].append(title)
        else:
            roots.append(title)
    for kids in children.values():
        kids.sort(key=lambda t: (defs[t].source_order, t))
    roots.sort(key=lambda t: (defs[t].source_order, t))

    depth: dict[str, int] = {}
    order: list[str] = []

    def walk(title: str, level: int) -> None:
        depth[title] = level
        order.append(title)
        for child in children[title]:
            walk(child, level + 1)

    for root in roots:
        walk(root, 0)
    for title in sorted(defs, key=lambda t: (defs[t].source_order, t)):
        if title not in depth:      # 依赖成环等异常数据：当作根，避免丢节点
            walk(title, 0)
    return QuestForest(defs, roots, children, parent, depth, order)


def build_quest_plan(doc: SaveDoc, quest: QuestDef, step: str) -> QuestPlan:
    if step not in editable_steps(quest):
        raise ValueError(f"invalid step: {step}")
    work = dict(doc.values)
    _clear_step_progress(work, quest.title, quest.line)
    work[schema.quest_key(quest.line, "quest", quest.title)] = step
    return _make_plan(doc, work, "quest", {"title": quest.title, "step": step,
                                           "line": quest.line})


def build_chain_plan(doc: SaveDoc, forest: QuestForest, node: str,
                     mode: str) -> QuestPlan:
    if mode not in {"complete", "reset"}:
        raise ValueError(mode)
    if node not in forest.defs:
        raise ValueError(f"unknown quest: {node}")
    titles = forest.path_to(node) if mode == "complete" else forest.subtree(node)
    work = dict(doc.values)
    for title in titles:
        _clear_step_progress(work, title, "old")
        if mode == "complete":
            work[schema.quest_key("old", "quest", title)] = "#end"
        else:
            work[schema.quest_key("old", "quest", title)] = "#start"
            work.pop(schema.quest_key("old", "complete", title), None)
            work.pop(schema.quest_key("old", "daily", title), None)
    return _make_plan(doc, work, f"chain:{mode}",
                      {"node": node, "mode": mode, "quests": titles})


def build_questline_plan(doc: SaveDoc, line: str) -> QuestPlan:
    """切换任务线只写 Questline 一个键；切回当前线时，缺失键等价 0，不必补写。"""
    work = dict(doc.values)
    if line == "old":
        work[schema.QUEST_LINE_KEY] = 1
    elif schema.QUEST_LINE_KEY in work:
        work[schema.QUEST_LINE_KEY] = 0
    return _make_plan(doc, work, "questline", {"line": line})
