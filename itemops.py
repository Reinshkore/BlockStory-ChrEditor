"""容器物品的结构化操作：交换、拖拽后的重排、按名称排序。

与字段页的“禁止新增任意键”不同，这里只允许在已知容器的合法槽位上补齐
游戏固定的 name/count/data/paint 四元组；其他键仍不能创建。
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

import schema
from model import SaveDoc, Slot

FIELDS = ("name", "count", "data", "paint")
DEFAULTS = {"name": "", "count": 0, "data": 0, "paint": 0}


def snapshot(doc: SaveDoc, prefix: str, index: int) -> dict[str, Any]:
    slot = doc.slots(prefix).get(index)
    return {field: getattr(slot, field) if slot else DEFAULTS[field] for field in FIELDS}


def _write(doc: SaveDoc, prefix: str, index: int, value: dict[str, Any]) -> None:
    for field in FIELDS:
        key = f"{prefix}_{field}_{index}"
        new = str(value[field]) if field == "name" else int(value[field])
        if key not in doc.values:
            # 只接受存档中已经出现过的容器前缀，不能凭空创建容器。
            if not any(schema.slot_family(k) and schema.slot_family(k)[0] == prefix
                       for k in doc.order):
                raise KeyError(f"unknown container: {prefix}")
            doc.values[key] = new
            insert_at = _family_insert_position(doc, prefix)
            doc.order.insert(insert_at, key)
        else:
            doc.set(key, new)


def _family_insert_position(doc: SaveDoc, prefix: str) -> int:
    positions = [i for i, key in enumerate(doc.order)
                 if (parts := schema.slot_family(key)) and parts[0] == prefix]
    return positions[-1] + 1 if positions else len(doc.order)


def set_slot(doc: SaveDoc, prefix: str, index: int, *, name: str,
             count: int, data: int, paint: int) -> None:
    """写入一个完整槽位；调用方负责 push_undo。"""
    _write(doc, prefix, index, {"name": name, "count": count, "data": data, "paint": paint})


def swap_slots(doc: SaveDoc, prefix: str, left: int, right: int) -> bool:
    return swap_slots_between(doc, prefix, left, prefix, right)


def swap_slots_between(doc: SaveDoc, left_prefix: str, left: int,
                       right_prefix: str, right: int) -> bool:
    """交换两个槽位；目标为空时等同于移动，支持不同容器。"""
    if left_prefix == right_prefix and left == right:
        return False
    doc.push_undo(f"swap:{left_prefix}[{left}]<->{right_prefix}[{right}]")
    a, b = snapshot(doc, left_prefix, left), snapshot(doc, right_prefix, right)
    _write(doc, left_prefix, left, b)
    _write(doc, right_prefix, right, a)
    return True


def apply_order(doc: SaveDoc, prefix: str, source_indices: Iterable[int],
                visible_indices: Iterable[int] | None = None) -> bool:
    """按 visible_indices 指定的可见槽位应用拖拽结果，支持跳过背包保留区。"""
    sources = list(source_indices)
    indices = list(visible_indices) if visible_indices is not None else list(range(len(sources)))
    if not sources or sources == indices:
        return False
    if len(set(sources)) != len(sources) or len(sources) != len(indices):
        raise ValueError("duplicate or incomplete slot in drag result")
    if sorted(sources) != indices or len(set(indices)) != len(indices):
        # 组件必须返回当前可见区域的每个槽位恰好一次；否则无法证明隐藏区物品应去哪里。
        raise ValueError("drag result must contain every visible slot exactly once")
    values = [snapshot(doc, prefix, source) for source in sources]
    doc.push_undo(f"arrange:{prefix}")
    for index, value in zip(indices, values):
        _write(doc, prefix, index, value)
    return True


def sort_by_name(doc: SaveDoc, prefix: str, visible: int,
                 label: Callable[[Slot], str], start: int = 0) -> bool:
    slots = doc.slots(prefix)
    indices = list(range(start, visible))
    used = [slot for index in indices
            if (slot := slots.get(index)) is not None and not slot.empty]
    used.sort(key=lambda slot: (label(slot).casefold(), slot.name.casefold(), slot.index))
    order = [slot.index for slot in used]
    order.extend(index for index in indices if index not in set(order))
    return apply_order(doc, prefix, order, indices)
