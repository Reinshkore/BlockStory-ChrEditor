"""重置进度。

五种并列操作，彼此不组合（除 `full` 明确包含前四项的效果）：

1. level       等级重置：等级 1、经验 0、属性不变、技能点重算
2. attributes  属性重置：等效于游戏内重置属性，技能点退回总量
3. quests      重置任务：删 Quest / Quest Complete / Daily
4. pets        宠物重置：删全部 `<宠物>(Clone) …` 属性键，让游戏取预制体默认值
5. full        彻底重置：前四项效果 + 清除成就与配方

每项都先在副本上预演，返回可展示的键级差异。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import schema
from model import Change, SaveDoc, kind_of

OP_LEVEL = "level"
OP_ATTRS = "attributes"
OP_QUESTS = "quests"
OP_PETS = "pets"
OP_FULL = "full"

ORDERED_OPS = (OP_LEVEL, OP_ATTRS, OP_QUESTS, OP_PETS, OP_FULL)

#: 属性重置后需要跟着夹紧的当前值 → 对应上限
CLAMP_AFTER_ATTR_RESET = (
    ("Current Health", "Max Health"),
    ("Current Mana", "Max Mana"),
    ("Current Breath", "Max Breath"),
)

SKILL_CLAMP = "clamp"
SKILL_RAW = "raw"


@dataclass
class ResetPlan:
    op: str
    changes: list[Change] = field(default_factory=list)
    notes: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    #: 重置后的派生数字，供预览展示
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def modified(self) -> int:
        return sum(1 for c in self.changes if c.kind == "modify")

    @property
    def removed(self) -> int:
        return sum(1 for c in self.changes if c.kind == "remove")

    @property
    def added(self) -> int:
        return sum(1 for c in self.changes if c.kind == "add")

    def keys_to_remove(self, prefix: str = "") -> list[str]:
        return [c.key for c in self.changes if c.kind == "remove"
                and (not prefix or c.key.startswith(prefix))]


# --------------------------------------------------------------------------- #

def _drop_prefix(values: dict[str, Any], prefixes: tuple[str, ...]) -> list[str]:
    doomed = [k for k in values if k.startswith(prefixes)]
    for key in doomed:
        del values[key]
    return doomed


def _set(work: dict[str, Any], key: str, value: Any) -> None:
    if key in work:
        work[key] = value


def _clone_like(doc: SaveDoc) -> SaveDoc:
    clone = copy.deepcopy(doc)
    clone._undo = []  # noqa: SLF001
    return clone


def _changes(before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    out: list[Change] = []
    for key, value in after.items():
        if key not in before:
            out.append(Change("add", key, None, value))
        elif kind_of(before[key]) != kind_of(value) or before[key] != value:
            out.append(Change("modify", key, before[key], value))
    for key, value in before.items():
        if key not in after:
            out.append(Change("remove", key, value, None))
    out.sort(key=lambda c: (0 if c.kind == "remove" else 1, c.key))
    return out


def _level_of(work: dict[str, Any]) -> int:
    level = work.get("Current Level", 0)
    return level if isinstance(level, int) and not isinstance(level, bool) else 0


def _purchased_of(work: dict[str, Any]) -> int:
    purchased = work.get("Purchased Skill Points", 0)
    return purchased if isinstance(purchased, int) and not isinstance(purchased, bool) else 0


# --------------------------------------------------------------------------- #
# 单项实现（直接改 work 里的扁平字典）
# --------------------------------------------------------------------------- #

def _do_level(work: dict[str, Any], skill_mode: str, notes) -> dict[str, Any]:
    purchased = _purchased_of(work)
    invested, _ = schema.invested_points(work)
    total_after = schema.earned_skill_points(1, purchased)
    raw_unspent = total_after - int(invested)
    stored = raw_unspent if skill_mode == SKILL_RAW else max(0, raw_unspent)

    _set(work, "Current Level", 1)
    _set(work, "Current Experience", 0)
    _set(work, "Skill Points", int(stored))

    if raw_unspent < 0:
        notes.append(("rs.note.negativeUnspent",
                      {"raw": int(raw_unspent), "stored": int(stored),
                       "invested": int(invested), "total": int(total_after)}))
    return {"total_after": total_after, "invested": int(invested),
            "raw_unspent": int(raw_unspent), "stored": int(stored)}


def _do_attributes(work: dict[str, Any], notes) -> dict[str, Any]:
    level = _level_of(work)
    purchased = _purchased_of(work)
    for attr in schema.POINT_ATTRIBUTES:
        _set(work, attr.key, float(attr.default))
    total = schema.reset_skill_points(level, purchased)
    _set(work, "Skill Points", total)

    clamped = []
    for cur_key, max_key in CLAMP_AFTER_ATTR_RESET:
        cur, cap = work.get(cur_key), work.get(max_key)
        if isinstance(cur, (int, float)) and isinstance(cap, (int, float)) and cur > cap:
            work[cur_key] = float(cap)
            clamped.append((cur_key, cur, cap))
    if clamped:
        notes.append(("rs.note.clamped", {"items": ", ".join(k for k, _, _ in clamped)}))
    return {"total": total, "level": level}


def _do_quests(work: dict[str, Any], notes,
               recipe_names: tuple[str, ...] = ()) -> dict[str, Any]:
    removed = _drop_prefix(work, ("Quest: ", "Quest Complete: ", "Daily: ",
                                  "Old Quest: ", "Old Quest Complete: ", "Old Daily: "))
    notes.append(("rs.note.quests", {"count": len(removed)}))
    recipe_keys = [f"Recipe: {name}" for name in recipe_names]
    recipes_removed = sum(work.pop(key, None) is not None for key in recipe_keys)
    if recipe_names:
        notes.append(("rs.note.questRecipes", {"count": recipes_removed}))
    return {"removed": len(removed), "recipes_removed": recipes_removed}


def _do_pets(work: dict[str, Any], notes) -> dict[str, Any]:
    doomed: list[str] = []
    touched: set[str] = set()
    for key in list(work):
        m = schema.PET_STAT_RE.match(key)
        if m:
            doomed.append(key)
            touched.add(m.group("pet"))
    for key in doomed:
        del work[key]
    notes.append(("rs.note.pets", {"count": len(doomed), "pets": len(touched)}))
    return {"removed": len(doomed), "pets": len(touched)}


def _do_clear_progress(work: dict[str, Any], notes) -> dict[str, Any]:
    removed = _drop_prefix(work, ("Achieve: ", "Recipe: "))
    notes.append(("rs.note.progress", {"count": len(removed)}))
    return {"removed": len(removed)}


def doc_pets(values: Any) -> set[str]:
    keys = values.keys() if isinstance(values, dict) else values
    return schema.detect_pets(keys)


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #

def build_plan(doc: SaveDoc, op: str, *, skill_mode: str = SKILL_CLAMP,
               sync_quest_recipes: bool = False, catalog: Any = None) -> ResetPlan:
    """在副本上算出某个重置操作的结果，不改动 doc。"""
    if op not in ORDERED_OPS:
        raise ValueError(f"unknown reset op: {op}")

    clone = _clone_like(doc)
    work = clone.values
    notes: list[tuple[str, dict[str, Any]]] = []
    metrics: dict[str, Any] = {}

    if op == OP_LEVEL:
        metrics.update(_do_level(work, skill_mode, notes))
    elif op == OP_ATTRS:
        metrics.update(_do_attributes(work, notes))
    elif op == OP_QUESTS:
        recipe_names = tuple(sorted({name for recipes in getattr(catalog, "quest_recipes", {}).values()
                                     for name in recipes})) if sync_quest_recipes else ()
        metrics.update(_do_quests(work, notes, recipe_names))
    elif op == OP_PETS:
        metrics.update(_do_pets(work, notes))
    elif op == OP_FULL:
        do_attrs = _do_attributes(work, notes)
        do_level = _do_level(work, SKILL_CLAMP, notes)
        _do_quests(work, notes)
        _do_pets(work, notes)
        _do_clear_progress(work, notes)
        metrics.update({"attrs": do_attrs, "level": do_level})

    # 顺序表跟着键集合走：删除的键剔除，剩下的保持原序
    order = [k for k in clone.order if k in work]
    seen = set(order)
    order.extend(k for k in work if k not in seen)

    plan = ResetPlan(op=op, values=work, order=order, notes=notes, metrics=metrics)
    plan.changes = _changes(doc.values, work)
    return plan


def apply_plan(doc: SaveDoc, plan: ResetPlan) -> None:
    doc.push_undo(f"reset:{plan.op}")
    doc.values = dict(plan.values)
    doc.reorder([k for k in plan.order if k in doc.values] or list(doc.values))
    doc._pets = None  # noqa: SLF001


# --------------------------------------------------------------------------- #
# 供预览使用的派生数字
# --------------------------------------------------------------------------- #

def skill_snapshot(values: dict[str, Any]) -> dict[str, Any]:
    """当前技能点账面：总量、未分配、反算已投入、差额。

    自然升级与技能重置使用两套不同的总量公式，取与实际账面最接近的一套展示。
    """
    level = values.get("Current Level", 0)
    purchased = values.get("Purchased Skill Points", 0)
    unspent = values.get("Skill Points", 0)
    level = level if isinstance(level, int) else 0
    purchased = purchased if isinstance(purchased, int) else 0
    unspent = unspent if isinstance(unspent, int) else 0
    earned = schema.earned_skill_points(level, purchased)
    after_reset = schema.reset_skill_points(level, purchased)
    invested, per_attr = schema.invested_points(values)
    actual = int(invested) + unspent
    total = min((earned, after_reset), key=lambda value: abs(actual - value))
    return {
        "level": level,
        "purchased": purchased,
        "total": total,
        "earned": earned,
        "after_reset": after_reset,
        "actual": actual,
        "unspent": unspent,
        "spent": total - unspent,
        "invested": int(invested),
        "diff": actual - total,
        "per_attr": per_attr,
    }
