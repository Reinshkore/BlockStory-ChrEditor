"""整理条目。

四项独立操作，全部在副本上预演，产出可审阅的差异；应用前不动原对象。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import schema
from model import Change, SaveDoc, kind_of


@dataclass
class TidyOptions:
    normalize: bool = True          # 规范类型与数值表示
    reorder: bool = True            # 按分类重排
    drop_empty_slots: bool = True   # 删除全空槽位
    compact_indices: bool = False   # 压缩槽位编号（默认关闭）


@dataclass
class TidyPlan:
    options: TidyOptions
    changes: list[Change] = field(default_factory=list)
    new_order: list[str] = field(default_factory=list)
    new_values: dict[str, Any] = field(default_factory=dict)
    fixes: int = 0                  # 被修正类型的键数
    reordered: bool = False

    @property
    def added(self) -> int:
        return sum(1 for c in self.changes if c.kind == "add")

    @property
    def removed(self) -> int:
        return sum(1 for c in self.changes if c.kind == "remove")

    @property
    def modified(self) -> int:
        return sum(1 for c in self.changes if c.kind == "modify")

    @property
    def touched(self) -> int:
        return len(self.changes)


# --------------------------------------------------------------------------- #

def _normalize_value(value: Any, kind: str) -> Any:
    """把值调整成目标类型；无法安全转换时原样返回。"""
    actual = kind_of(value)
    if actual == kind:
        return value
    try:
        if kind == "float" and actual in ("int", "float"):
            return float(value)
        if kind == "int" and actual == "float":
            f = float(value)
            if f == int(f):
                return int(f)
        if kind == "str" and actual in ("int", "float"):
            return None  # 数字转字符串没有默认语义，交给用户
    except (ValueError, OverflowError):
        return value
    return value


def _empty_slot_keys(values: dict[str, Any], prefix: str, slots) -> list[str]:
    drop: list[str] = []
    for _, slot in slots.items():
        if slot.empty and not slot.data and not slot.paint:
            for fld in slot.present:
                key = f"{prefix}_{fld}_{slot.index}"
                if key in values:
                    drop.append(key)
    return drop


def _compact(values: dict[str, Any], prefix: str, slots) -> tuple[dict[str, Any], int]:
    """把非空槽位重排到 0..k-1。返回新 dict 与移动的槽位数。"""
    used = [s for _, s in sorted(slots.items()) if not s.empty]
    if not used:
        return values, 0
    moved = 0
    out = dict(values)
    for key in [k for k in out if (p := schema.slot_family(k)) and p[0] == prefix]:
        del out[key]
    for new_index, slot in enumerate(used):
        if slot.index != new_index:
            moved += 1
        for fld in ("name", "count", "data", "paint"):
            # 只写回该槽位原本存在的字段，避免凭空造出 paint 之类的键
            if fld not in slot.present:
                continue
            key = f"{prefix}_{fld}_{new_index}"
            out[key] = slot.name if fld == "name" else int(getattr(slot, fld))
    return out, moved


def build_plan(doc: SaveDoc, options: TidyOptions) -> TidyPlan:
    values: dict[str, Any] = copy.copy(doc.values)
    order: list[str] = list(doc.order)
    pets = doc.pets()
    fixes = 0

    if options.normalize:
        for key in order:
            spec = schema.spec_for(key, pets)
            if spec is None:
                continue
            new_value = _normalize_value(values[key], spec.kind)
            if new_value is not None and kind_of(new_value) != kind_of(values[key]):
                values[key] = new_value
                fixes += 1

    moved_slots = 0
    if options.compact_indices or options.drop_empty_slots:
        for prefix in sorted(doc.prefix_slots()):
            slots = _slots_from(values, prefix)
            if options.drop_empty_slots:
                for key in _empty_slot_keys(values, prefix, slots):
                    values.pop(key, None)
                slots = _slots_from(values, prefix)
            # 装备栏不压缩：RightHand / LeftHand 存的是绝对槽位号
            if options.compact_indices and prefix not in ("Equipment",):
                values, moved = _compact(values, prefix, slots)
                moved_slots += moved
        order = [k for k in order if k in values]
        # 压缩编号会造出新索引键（旧键被删），顺序表必须补齐
        seen = set(order)
        order.extend(k for k in values if k not in seen)

    if options.reorder:
        order = sorted(order, key=lambda k: schema.sort_rank(k, pets))

    plan = TidyPlan(options=options, new_order=order, new_values=values,
                    fixes=fixes, reordered=options.reorder)
    plan.changes = _diff(doc.values, values)
    return plan


def _slots_from(values: dict[str, Any], prefix: str):
    from model import Slot

    out: dict[int, Slot] = {}
    for key, value in values.items():
        parts = schema.slot_family(key)
        if not parts or parts[0] != prefix:
            continue
        _, fld, idx = parts
        slot = out.setdefault(idx, Slot(prefix=prefix, index=idx))
        slot.present.add(fld)
        if fld == "name":
            slot.name = value if isinstance(value, str) else str(value)
        elif isinstance(value, int) and not isinstance(value, bool):
            setattr(slot, fld, value)
    return out


def _diff(before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    out: list[Change] = []
    for key, value in after.items():
        if key not in before:
            out.append(Change("add", key, None, value))
        elif kind_of(before[key]) != kind_of(value) or before[key] != value:
            out.append(Change("modify", key, before[key], value))
    for key, value in before.items():
        if key not in after:
            out.append(Change("remove", key, value, None))
    return out


def apply_plan(doc: SaveDoc, plan: TidyPlan, label: str = "tidy") -> None:
    doc.push_undo(label)
    # 先换值再换序：删除键之后键集合才与计划一致
    doc.values = dict(plan.new_values)
    doc.reorder(plan.new_order)
    doc._pets = None  # noqa: SLF001 - 键集合可能变化
