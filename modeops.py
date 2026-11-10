"""按游戏模式清除或复制角色数据。

非剧情模式使用键名后缀；剧情模式使用无后缀键。角色身份、跨模式共享的
已购技能点和文件级加密标记不属于可清除/复制的模式数据。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import schema
from model import Change, SaveDoc, kind_of

PRESERVED_SHARED_KEYS = {"Purchased Skill Points", "encrypted"}


@dataclass
class ModePlan:
    action: str
    source: str
    target: str
    values: dict[str, Any]
    order: list[str]
    changes: list[Change] = field(default_factory=list)
    error: str = ""
    skipped: int = 0

    @property
    def added(self) -> int:
        return sum(c.kind == "add" for c in self.changes)

    @property
    def removed(self) -> int:
        return sum(c.kind == "remove" for c in self.changes)


def data_keys(doc: SaveDoc, mode: str) -> list[str]:
    if mode not in schema.WORLD_MODES:
        raise ValueError(mode)
    out = []
    for key in doc.order:
        if key not in doc.values or schema.world_mode_of(key) != mode:
            continue
        if key in PRESERVED_SHARED_KEYS or schema.classify(key, doc.pets()) == "identity":
            continue
        out.append(key)
    return out


def counts(doc: SaveDoc) -> dict[str, int]:
    return {mode: len(data_keys(doc, mode)) for mode in schema.WORLD_MODES}


def suggest_mode(doc: SaveDoc, current: str) -> str | None:
    """当前模式没有数据时，给出一个更适合展示的模式。

    优先剧情模式；否则选数据键最多的模式。当前模式本身有数据时返回 None，
    避免用户手动选择的空模式在每次载入时被强行改掉。
    """
    tally = counts(doc)
    if tally.get(current):
        return None
    populated = [mode for mode in schema.WORLD_MODES if tally.get(mode)]
    if not populated:
        return None
    if tally.get("story"):
        return "story"
    return max(populated, key=lambda mode: tally[mode])


def _changes(before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    out = []
    for key, value in after.items():
        if key not in before:
            out.append(Change("add", key, None, value))
        elif kind_of(before[key]) != kind_of(value) or before[key] != value:
            out.append(Change("modify", key, before[key], value))
    for key, value in before.items():
        if key not in after:
            out.append(Change("remove", key, value, None))
    return out


def _plan(doc: SaveDoc, action: str, source: str, target: str,
          work: dict[str, Any], error: str = "", skipped: int = 0) -> ModePlan:
    order = [key for key in doc.order if key in work]
    seen = set(order)
    order.extend(key for key in work if key not in seen)
    return ModePlan(action, source, target, work, order,
                    _changes(doc.values, work), error, skipped)


def build_clear_plan(doc: SaveDoc, mode: str) -> ModePlan:
    keys = data_keys(doc, mode)
    work = dict(doc.values)
    error = ""
    if not keys:
        error = "md.sourceEmpty"
    elif sum(bool(data_keys(doc, other)) for other in schema.WORLD_MODES) == 1:
        error = "md.lastMode"
    else:
        for key in keys:
            del work[key]
    return _plan(doc, "clear", mode, mode, work, error)


def build_copy_plan(doc: SaveDoc, source: str, target: str) -> ModePlan:
    work = dict(doc.values)
    error = ""
    skipped = 0
    if source == target:
        error = "md.sameMode"
    elif not data_keys(doc, source):
        error = "md.sourceEmpty"
    elif data_keys(doc, target):
        error = "md.targetNotEmpty"
    else:
        for key in data_keys(doc, source):
            # QuestModeSupport.QuestsEnabled：Creative / Sandbox 均为 false。
            if target in {"creative", "sandbox"} and schema.classify(key, doc.pets()) == "quest":
                skipped += 1
                continue
            work[schema.world_mode_key(key, source, target)] = copy.deepcopy(doc.values[key])
    return _plan(doc, "copy", source, target, work, error, skipped)


def apply_plan(doc: SaveDoc, plan: ModePlan) -> None:
    if plan.error:
        raise ValueError(plan.error)
    doc.push_undo(f"mode:{plan.action}:{plan.source}->{plan.target}")
    doc.values = dict(plan.values)
    doc.reorder([key for key in plan.order if key in doc.values])
    doc._pets = None  # noqa: SLF001
