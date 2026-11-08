"""把完整存档映射为某个游戏模式的可编辑视图。

视图中的键名与游戏 API 一致（不带模式后缀）；字典和顺序表的每次修改都会
立即写回完整 SaveDoc。因此即使用户操作内部调用 st.rerun，也不会丢失同步。
"""

from __future__ import annotations

import copy
from typing import Any, Iterable

import schema
from model import SaveDoc

SHARED_KEYS = {"charName", "charGender", "Purchased Skill Points", "encrypted"}


class _Values(dict):
    def __init__(self, owner: "ModeViewDoc", *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.owner._sync()

    def __delitem__(self, key):
        super().__delitem__(key)
        self.owner._sync()

    def pop(self, key, *default):
        result = super().pop(key, *default)
        self.owner._sync()
        return result

    def popitem(self):
        result = super().popitem()
        self.owner._sync()
        return result

    def clear(self):
        super().clear()
        self.owner._sync()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.owner._sync()

    def setdefault(self, key, default=None):
        if key in self:
            return self[key]
        self[key] = default
        return default


class _Order(list):
    def __init__(self, owner: "ModeViewDoc", values: Iterable[str] = ()):
        self.owner = owner
        super().__init__(values)

    def _changed(self, result=None):
        self.owner._sync()
        return result

    def append(self, value):
        super().append(value)
        self._changed()

    def extend(self, values):
        super().extend(values)
        self._changed()

    def insert(self, index, value):
        super().insert(index, value)
        self._changed()

    def remove(self, value):
        super().remove(value)
        self._changed()

    def pop(self, index=-1):
        result = super().pop(index)
        self._changed()
        return result

    def clear(self):
        super().clear()
        self._changed()

    def sort(self, *args, **kwargs):
        super().sort(*args, **kwargs)
        self._changed()

    def reverse(self):
        super().reverse()
        self._changed()

    def __setitem__(self, index, value):
        super().__setitem__(index, value)
        self._changed()

    def __delitem__(self, index):
        super().__delitem__(index)
        self._changed()

    def __iadd__(self, values):
        super().__iadd__(values)
        self._changed()
        return self


class ModeViewDoc(SaveDoc):
    def __init__(self, parent: SaveDoc, mode: str):
        if mode not in schema.WORLD_MODES:
            raise ValueError(mode)
        self.parent = parent
        self.mode = mode
        self._ready = False
        self._selected_full: set[str] = set()
        entries = [(base, parent.values[key]) for key, base in self._selected(parent.order, parent.values)]
        super().__init__(entries, path=parent.path, raw="",
                         parse_warnings=parent.parse_warnings, duplicates=parent.duplicates)
        self.original = {base: parent.original[key]
                         for key, base in self._selected(parent.original_order, parent.original)}
        self.original_order = [base for key, base in self._selected(parent.original_order, parent.original)]
        self.widget_id = parent.widget_id
        self._selected_full = {key for key, _ in self._selected(parent.order, parent.values)}
        self._ready = True

    def _selected(self, order: Iterable[str], values: dict[str, Any]):
        for key in order:
            if key not in values:
                continue
            if key in SHARED_KEYS:
                yield key, key
            elif schema.world_mode_of(key) == self.mode:
                yield key, schema.mode_base_key(key)

    def _full_key(self, base: str) -> str:
        return base if base in SHARED_KEYS else schema.world_mode_key(base, "story", self.mode)

    @property
    def values(self):
        return self._values_proxy

    @values.setter
    def values(self, new):
        self._values_proxy = _Values(self, new)
        if getattr(self, "_ready", False):
            self._sync()

    @property
    def order(self):
        return self._order_proxy

    @order.setter
    def order(self, new):
        self._order_proxy = _Order(self, new)
        if getattr(self, "_ready", False):
            self._sync()

    def push_undo(self, label: str) -> None:
        self.parent.push_undo(f"{self.mode}:{label}")

    def undo(self) -> str | None:
        return self.parent.undo()

    def undo_depth(self) -> int:
        return self.parent.undo_depth()

    def __deepcopy__(self, memo):
        # 重置计划的副本只需当前视图，不应把 parent 和代理回调一起递归复制。
        clone = SaveDoc(list(self.values.items()), path=self.path)
        clone.original = copy.copy(self.original)
        clone.original_order = list(self.original_order)
        clone.widget_id = self.widget_id
        return clone

    def _sync(self) -> None:
        if not self._ready:
            return
        mapped_values = {self._full_key(base): value for base, value in self.values.items()}
        for key in self._selected_full - mapped_values.keys():
            self.parent.values.pop(key, None)
        self.parent.values.update(mapped_values)
        self._selected_full = set(mapped_values)

        mapped_mode_order = [self._full_key(base) for base in self.order if base not in SHARED_KEYS]
        mapped_set = set(mapped_mode_order)
        new_order = []
        inserted = False
        for key in self.parent.order:
            if key not in self.parent.values:
                continue
            is_selected = key not in SHARED_KEYS and schema.world_mode_of(key) == self.mode
            if is_selected:
                if not inserted:
                    new_order.extend(mapped_mode_order)
                    inserted = True
                continue
            new_order.append(key)
        if not inserted:
            new_order.extend(mapped_mode_order)
        new_order.extend(key for key in mapped_values if key not in new_order and key not in mapped_set)
        # mapped_set 中的键已经按视图顺序插入；共享键和新增键只去重，不重复追加。
        seen = set()
        self.parent.order = [key for key in new_order if not (key in seen or seen.add(key))]
        self.parent._pets = None  # noqa: SLF001
