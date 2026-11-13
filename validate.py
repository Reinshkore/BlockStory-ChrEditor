"""校验引擎。

三级：error 阻止落盘 / warn 需确认 / info 仅提示。
每条问题带键名、序列化行号与参数，由 i18n 渲染文本。
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from dataclasses import dataclass, field
from typing import Any

import schema
from model import SaveDoc, kind_of

ERROR = "error"
WARN = "warn"
INFO = "info"

_LEVEL_ORDER = {ERROR: 0, WARN: 1, INFO: 2}

_INT32_MIN = -(2 ** 31)
_INT32_MAX = 2 ** 31 - 1
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?$")

#: 当前值 → 上限键
CURRENT_MAX_PAIRS = (
    ("Current Health", "Max Health"),
    ("Current Mana", "Max Mana"),
    ("Current Breath", "Max Breath"),
    ("Current Hunger", "Max Hunger"),
)


@dataclass(frozen=True)
class Issue:
    code: str
    level: str
    key: str
    line: int = 0
    params: dict[str, Any] = field(default_factory=dict)

    def sort_key(self) -> tuple:
        return (_LEVEL_ORDER.get(self.level, 9), self.line, self.key)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _iso_ok(text: Any) -> bool:
    if not isinstance(text, str) or not _ISO_RE.match(text):
        return False
    try:
        _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate(doc: SaveDoc, catalog=None) -> list[Issue]:
    issues: list[Issue] = []
    pets = doc.pets()
    add = issues.append

    for dup in doc.duplicates:
        add(Issue("E_DUP", ERROR, dup, doc.line_of(dup)))

    for key in doc.order:
        value = doc.values[key]
        line = doc.line_of(key)
        spec = schema.spec_for(key, pets)
        actual = kind_of(value)

        if spec is None:
            add(Issue("W_UNKNOWN", WARN, key, line))
        else:
            if actual != spec.kind:
                add(Issue("E_TYPE", ERROR, key, line,
                          {"expected": spec.kind, "actual": actual}))
            elif spec.kind == "float" and not math.isfinite(float(value)):
                add(Issue("E_FLOAT_SPECIAL", ERROR, key, line, {"value": repr(value)}))
            elif spec.kind == "int" and not (_INT32_MIN <= int(value) <= _INT32_MAX):
                add(Issue("E_INT_RANGE", ERROR, key, line, {"value": value}))

            if spec.vmin is not None and _is_number(value) and float(value) < spec.vmin:
                add(Issue("W_RANGE_LOW", WARN, key, line,
                          {"value": value, "min": spec.vmin}))
            if spec.vmax is not None and _is_number(value) and float(value) > spec.vmax:
                add(Issue("W_RANGE_HIGH", WARN, key, line,
                          {"value": value, "max": spec.vmax}))

        if not key.isascii():
            add(Issue("I_NONASCII", INFO, key, line))

    issues.extend(_check_growth(doc))
    issues.extend(_check_attributes(doc))
    issues.extend(_check_slots(doc))
    issues.extend(_check_hands(doc))
    issues.extend(_check_identity(doc))
    issues.extend(_check_dates(doc))
    issues.extend(_check_quest_catalog(doc, catalog))
    issues.extend(_check_questline(doc))

    issues.sort(key=Issue.sort_key)
    return issues


# --------------------------------------------------------------------------- #

def _check_quest_catalog(doc: SaveDoc, catalog) -> list[Issue]:
    """任务一致性检查：当前线与旧线分别对各自的目录核对，自定义任务不算错误。"""
    if catalog is None or catalog.error:
        return []
    out: list[Issue] = []
    for key in doc.order:
        if key.startswith("Old Quest: "):
            prefix, line = "Old Quest: ", "old"
        elif key.startswith("Quest: "):
            prefix, line = "Quest: ", "current"
        else:
            continue
        rest = schema.mode_base_key(key[len(prefix):])
        progress = schema.QUEST_PROG_RE.match(rest)
        title = progress.group("title") if progress else rest
        quest = catalog.for_line(line).get(title)
        at = doc.line_of(key)
        if progress:
            if quest is None:
                out.append(Issue("I_PROGRESS_CUSTOM", INFO, key, at, {"title": title}))
            elif progress.group("step") not in quest.steps:
                out.append(Issue("I_PROGRESS_STEP", INFO, key, at,
                                 {"title": title, "step": progress.group("step")}))
            elif " placed " not in rest and schema.mode_base_key(key) not in {x.key for x in quest.targets}:
                out.append(Issue("I_PROGRESS_TARGET", INFO, key, at, {"title": title}))
        elif quest is None:
            out.append(Issue("I_QUEST_CUSTOM", INFO, key, at, {"title": title}))
        elif value_is_invalid_step(doc.values[key], quest):
            out.append(Issue("W_QUEST_STEP", WARN, key, at,
                             {"title": title, "step": str(doc.values[key])}))
    return out


def _check_questline(doc: SaveDoc) -> list[Issue]:
    """任务线设置与现存键族不一致时提示；游戏只加载当前任务线那套键。"""
    line = schema.quest_line(doc.get(schema.QUEST_LINE_KEY, 0))
    counts = {"current": 0, "old": 0}
    current_prefixes = ("Quest: ", "Quest Complete: ", "Daily: ", "Recipe: ")
    old_prefixes = ("Old Quest: ", "Old Quest Complete: ", "Old Daily: ", "Old Recipe: ")
    for key in doc.order:
        if key.startswith(old_prefixes):
            counts["old"] += 1
        elif key.startswith(current_prefixes):
            counts["current"] += 1
    other = "current" if line == "old" else "old"
    if not counts[other]:
        return []
    return [Issue("I_QUESTLINE_EXTRA", INFO, schema.QUEST_LINE_KEY,
                  doc.line_of(schema.QUEST_LINE_KEY),
                  {"line": line, "other": other, "count": counts[other]})]


def value_is_invalid_step(value: Any, quest) -> bool:
    valid = set(quest.steps) | {"#end", "#end_dark_side"}
    return not isinstance(value, str) or value not in valid


def _check_growth(doc: SaveDoc) -> list[Issue]:
    out: list[Issue] = []
    level = doc.get("Current Level")
    exp = doc.get("Current Experience")
    purchased = doc.get("Purchased Skill Points", 0)
    skill = doc.get("Skill Points", 0)

    if isinstance(level, int) and not (0 <= level <= schema.MAX_LEVEL):
        out.append(Issue("W_LEVEL_RANGE", WARN, "Current Level", doc.line_of("Current Level"),
                         {"value": level, "max": schema.MAX_LEVEL}))

    if isinstance(level, int) and isinstance(exp, int):
        cap = schema.max_exp_for_level(level)
        if exp < 0 or exp > cap:
            out.append(Issue("W_EXP_RANGE", WARN, "Current Experience",
                             doc.line_of("Current Experience"),
                             {"value": exp, "cap": cap, "level": level}))

    if isinstance(level, int) and isinstance(purchased, int) and isinstance(skill, int):
        earned = schema.earned_skill_points(level, purchased)
        after_reset = schema.reset_skill_points(level, purchased)
        ceiling = max(earned, after_reset)
        if skill > ceiling:
            out.append(Issue("W_POINTS_OVER", WARN, "Skill Points",
                             doc.line_of("Skill Points"),
                             {"value": skill, "total": ceiling}))
        invested, _ = schema.invested_points(doc.values)
        # 自然升级与“技能重置”是两套合法总量；实际账面等于其一就不算异常。
        actual = int(invested) + skill
        nearest = min((earned, after_reset), key=lambda total: abs(actual - total))
        expected = nearest - skill
        diff = int(invested) - expected
        if abs(diff) >= 1:
            out.append(Issue("W_POINTS_MISMATCH", WARN, "Skill Points",
                             doc.line_of("Skill Points"),
                             {"invested": int(invested), "expected": int(expected),
                              "diff": int(diff), "total": int(nearest),
                              "earned": int(earned), "after_reset": int(after_reset),
                              "unspent": skill}))
    return out


def _check_attributes(doc: SaveDoc) -> list[Issue]:
    out: list[Issue] = []
    for attr in schema.POINT_ATTRIBUTES:
        value = doc.get(attr.key)
        if _is_number(value) and float(value) < 0:
            out.append(Issue("W_ATTR_NEG", WARN, attr.key, doc.line_of(attr.key),
                             {"value": value, "default": attr.default}))

    for cur_key, max_key in CURRENT_MAX_PAIRS:
        cur, cap = doc.get(cur_key), doc.get(max_key)
        if _is_number(cur) and _is_number(cap) and float(cur) > float(cap):
            out.append(Issue("W_CUR_GT_MAX", WARN, cur_key, doc.line_of(cur_key),
                             {"cur": cur, "max": cap, "max_key": max_key}))
    return out


def _check_slots(doc: SaveDoc) -> list[Issue]:
    out: list[Issue] = []
    pets = doc.pets()
    by_prefix = doc.prefix_slots()

    for prefix, slots in by_prefix.items():
        if prefix in schema.FIXED_STORES:
            capacity = schema.STORAGE_CAPACITY[schema.FIXED_STORES[prefix]]
        elif prefix in pets:
            capacity = schema.STORAGE_CAPACITY["pet"]
        else:
            capacity = None

        for idx, slot in sorted(slots.items()):
            if capacity is not None and idx >= capacity:
                out.append(Issue("W_SLOT_INDEX", WARN, f"{prefix}_name_{idx}",
                                 doc.line_of(f"{prefix}_name_{idx}"),
                                 {"prefix": prefix, "index": idx, "capacity": capacity}))
            # 缺 data / paint 无妨（读档时按 0 兜底）；只有 name 与 count 互相缺席才会让物品消失
            if "name" not in slot.present and slot.count > 0:
                add_orphan = True
            else:
                add_orphan = "count" not in slot.present and bool(slot.name)
            if add_orphan:
                anchor = f"{prefix}_name_{idx}" if f"{prefix}_name_{idx}" in doc.values else f"{prefix}_count_{idx}"
                out.append(Issue("W_ORPHAN_SLOT", WARN, anchor, doc.line_of(anchor),
                                 {"prefix": prefix, "index": idx,
                                  "missing": "name" if "name" not in slot.present else "count"}))
            if slot.present & {"name", "count"}:
                if slot.name and slot.count <= 0:
                    out.append(Issue("W_SLOT_STATE", WARN, f"{prefix}_count_{idx}",
                                     doc.line_of(f"{prefix}_count_{idx}"),
                                     {"prefix": prefix, "index": idx, "name": slot.name,
                                      "count": slot.count}))
                elif not slot.name and slot.count > 0:
                    out.append(Issue("W_SLOT_STATE", WARN, f"{prefix}_name_{idx}",
                                     doc.line_of(f"{prefix}_name_{idx}"),
                                     {"prefix": prefix, "index": idx, "name": "",
                                      "count": slot.count}))
            for fld in ("data", "paint"):
                value = getattr(slot, fld)
                if value and not (0 <= value <= 65535):
                    out.append(Issue("W_USHORT", WARN, f"{prefix}_{fld}_{idx}",
                                     doc.line_of(f"{prefix}_{fld}_{idx}"),
                                     {"field": fld, "value": value}))
    return out


def _check_hands(doc: SaveDoc) -> list[Issue]:
    out: list[Issue] = []
    equipment = doc.slots("Equipment")
    for key in ("RightHand", "LeftHand"):
        value = doc.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            continue
        if value == -1:
            continue
        ok = 0 <= value <= 8          # 装备栏 9 格，存的是格号而不是全局下标
        if ok and equipment:
            ok = value in equipment
        if not ok:
            out.append(Issue("W_HAND", WARN, key, doc.line_of(key),
                             {"value": value, "capacity": 9}))
    return out


def _check_identity(doc: SaveDoc) -> list[Issue]:
    out: list[Issue] = []
    name = doc.get("charName")
    stem = doc.path.stem if doc.path else ""
    if not isinstance(name, str) or not name.strip():
        out.append(Issue("W_NAME_EMPTY", WARN, "charName", doc.line_of("charName")))
    elif stem and name != stem:
        out.append(Issue("W_NAME_MISMATCH", WARN, "charName", doc.line_of("charName"),
                         {"in_file": name, "file_name": stem}))
    return out


def _check_dates(doc: SaveDoc) -> list[Issue]:
    out: list[Issue] = []
    for key in doc.order:
        if key.startswith("Daily:") or key.endswith("Summoner"):
            value = doc.values[key]
            if value == "":
                continue
            if not _iso_ok(value):
                out.append(Issue("W_DATE", WARN, key, doc.line_of(key), {"value": value}))
    return out


# --------------------------------------------------------------------------- #

def blocking(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == ERROR]


def counts(issues: list[Issue]) -> dict[str, int]:
    out = {ERROR: 0, WARN: 0, INFO: 0}
    for issue in issues:
        out[issue.level] = out.get(issue.level, 0) + 1
    return out


def issue_index(issues: list[Issue]) -> dict[str, list[Issue]]:
    """按键聚拢，供字段表的状态列使用。"""
    out: dict[str, list[Issue]] = {}
    for issue in issues:
        out.setdefault(issue.key, []).append(issue)
    return out
