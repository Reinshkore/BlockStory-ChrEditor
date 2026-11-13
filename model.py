"""存档的内存模型：有序条目 + 差异 + 撤销。

只依赖标准库与 bsjson/schema，不碰 streamlit，便于单测。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import bsjson
import schema

# --------------------------------------------------------------------------- #
# 类型与显示
# --------------------------------------------------------------------------- #

KIND_LABEL = {
    "int": ("Integer", "整数"),
    "float": ("Float", "浮点"),
    "str": ("Text", "文本"),
    "bool": ("Boolean", "布尔"),
    "null": ("Null", "空值"),
}


def kind_of(value: Any) -> str:
    return bsjson.entry_kind(value)


def display_value(value: Any) -> str:
    """把值渲染成与游戏一致的文本形式（浮点用 `.0###########` 风格）。"""
    k = kind_of(value)
    if k == "float":
        try:
            return bsjson.fmt_float(float(value))
        except (ValueError, OverflowError):
            return repr(value)
    if k == "bool":
        return "true" if value else "false"
    if k == "null":
        return "null"
    return str(value)


class CoerceError(ValueError):
    """用户输入无法按目标类型解析。"""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def coerce_input(raw: str, kind: str) -> Any:
    """把界面输入转成目标类型。宽容：整数键收到 `400.0` 会转成 400。

    抛出 CoerceError 时附带修复提示。
    """
    text = (raw or "").strip()
    if kind == "str":
        return raw if raw is not None else ""

    if kind == "bool":
        low = text.lower()
        if low in {"true", "1", "yes"}:
            return True
        if low in {"false", "0", "no"}:
            return False
        raise CoerceError("expected true/false", "true / false")

    if kind == "int":
        if not text:
            raise CoerceError("empty", "an integer, e.g. 69")
        try:
            if any(ch in text for ch in ".eE"):
                f = float(text)
                if f != f or f in (float("inf"), float("-inf")):
                    raise ValueError
                if abs(f - round(f)) > 1e-9:
                    raise CoerceError(f"{text} is not a whole number",
                                      f"an integer near {round(f)}")
                return int(round(f))
            return int(text)
        except CoerceError:
            raise
        except ValueError:
            raise CoerceError(f"{text!r} is not an integer", "digits only, e.g. 69") from None

    if kind == "float":
        if not text:
            raise CoerceError("empty", "a decimal number, e.g. 400.0")
        try:
            f = float(text)
        except ValueError:
            raise CoerceError(f"{text!r} is not a number", "e.g. 400.0") from None
        if f != f or f in (float("inf"), float("-inf")):
            raise CoerceError("not a finite number", "e.g. 400.0")
        return bsjson.parse_float_text(text)
    return raw


# --------------------------------------------------------------------------- #
# 差异
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Change:
    kind: str          # "add" | "remove" | "modify"
    key: str
    old: Any = None
    new: Any = None


# --------------------------------------------------------------------------- #
# 存档
# --------------------------------------------------------------------------- #

@dataclass
class Slot:
    """一个储物槽位（容器 + 索引），由四个键聚合而成。"""

    prefix: str
    index: int
    name: str = ""
    count: int = 0
    data: int = 0
    paint: int = 0
    present: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not self.name or self.count <= 0

    @property
    def keys(self) -> dict[str, str]:
        base = f"{self.prefix}_"
        return {f: f"{base}{f}_{self.index}" for f in ("name", "count", "data", "paint")}


class SaveDoc:
    """一份存档的内存表示。

    用 `order` + `values` 而不是条目列表：改值不移动位置，删键不需要重排，
    整理时只替换 `order`。`original` 保留载入时的快照，用于差异与"是否纯净"。
    """

    def __init__(self, entries: list[tuple[str, Any]], *, path: Path | None = None,
                 raw: str = "", parse_warnings: list[str] | None = None,
                 duplicates: list[str] | None = None) -> None:
        self.path = path
        self.widget_id = id(self)
        self.raw = raw
        self.parse_warnings = list(parse_warnings or [])
        self.duplicates = list(duplicates or [])
        self.order: list[str] = []
        self.values: dict[str, Any] = {}
        for key, value in entries:
            if key in self.values:
                continue  # 重复键：游戏只认最后一个；解析层已经报过
            self.order.append(key)
            self.values[key] = value
        self.original: dict[str, Any] = copy.copy(self.values)
        self.original_order: list[str] = list(self.order)
        self._undo: list[tuple[str, list[str], dict[str, Any]]] = []
        self._pets: set[str] | None = None

    # -- 载入 -------------------------------------------------------------
    @classmethod
    def from_text(cls, text: str, path: Path | None = None) -> "SaveDoc":
        parsed = bsjson.loads(text)
        # 重复键以最后出现的为准
        dedup: dict[str, Any] = {}
        for key, value in parsed.entries:
            dedup[key] = value
        return cls(list(dedup.items()), path=path, raw=text,
                   parse_warnings=parsed.warnings, duplicates=parsed.duplicates)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SaveDoc":
        return cls(list(data.items()))

    # -- 基本访问 ---------------------------------------------------------
    def __contains__(self, key: str) -> bool:
        return key in self.values

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def kind(self, key: str) -> str | None:
        return kind_of(self.values[key]) if key in self.values else None

    def pets(self) -> set[str]:
        if self._pets is None:
            self._pets = schema.detect_pets(self.order)
        return self._pets

    def containers(self) -> list[str]:
        return schema.detect_containers(self.order, self.pets())

    def spec(self, key: str) -> schema.FieldSpec | None:
        return schema.spec_for(key, self.pets())

    def category(self, key: str) -> str:
        return schema.classify(key, self.pets())

    # -- 撤销 -------------------------------------------------------------
    def push_undo(self, label: str) -> None:
        self._undo.append((label, list(self.order), copy.copy(self.values)))
        if len(self._undo) > 30:
            self._undo.pop(0)

    def undo(self) -> str | None:
        if not self._undo:
            return None
        label, order, values = self._undo.pop()
        self.order = order
        self.values = values
        self._pets = None
        return label

    def undo_depth(self) -> int:
        return len(self._undo)

    # -- 编辑 -------------------------------------------------------------
    def set(self, key: str, value: Any) -> bool:
        """改已有键的值。不允许新增键（游戏没有契约保证）。"""
        if key not in self.values:
            raise KeyError(key)
        if self.values[key] == value and kind_of(self.values[key]) == kind_of(value):
            return False
        self.values[key] = value
        return True

    def delete(self, key: str) -> bool:
        if key not in self.values:
            return False
        del self.values[key]
        self.order = [k for k in self.order if k != key]
        self._pets = None
        return True

    def delete_many(self, keys: Iterable[str]) -> int:
        keys = [k for k in keys if k in self.values]
        for key in keys:
            del self.values[key]
        drop = set(keys)
        self.order = [k for k in self.order if k not in drop]
        if keys:
            self._pets = None
        return len(keys)

    def reorder(self, order: list[str]) -> None:
        if set(order) != set(self.values):
            raise ValueError("reorder 必须包含且仅包含现有的全部键")
        self.order = list(order)

    # -- 差异 -------------------------------------------------------------
    def changes(self) -> list[Change]:
        out: list[Change] = []
        for key in self.order:
            if key not in self.original:
                out.append(Change("add", key, None, self.values[key]))
            elif not _same(self.original[key], self.values[key]):
                out.append(Change("modify", key, self.original[key], self.values[key]))
        current = set(self.values)
        for key in self.original:
            if key not in current:
                out.append(Change("remove", key, self.original[key], None))
        return out

    def change_counts(self) -> tuple[int, int, int]:
        add = mod = rem = 0
        for ch in self.changes():
            if ch.kind == "add":
                add += 1
            elif ch.kind == "modify":
                mod += 1
            else:
                rem += 1
        return add, mod, rem

    def is_pristine(self) -> bool:
        return not self.changes() and self.order == self.original_order

    def mark_saved(self, raw: str) -> None:
        """写入磁盘后把当前状态当作新的基线。"""
        self.raw = raw
        self.original = copy.copy(self.values)
        self.original_order = list(self.order)
        self._undo.clear()

    def reverted(self) -> "SaveDoc":
        """丢弃全部改动，回到载入时的状态。"""
        clone = SaveDoc.from_text(self.raw, path=self.path) if self.raw else SaveDoc.from_dict(self.original)
        return clone

    # -- 输出 -------------------------------------------------------------
    def serialize(self) -> str:
        return bsjson.dumps_entries([(k, self.values[k]) for k in self.order])

    def line_of(self, key: str) -> int:
        """键在序列化文本中的行号（1 起），用于定位。"""
        try:
            return self.order.index(key) + 2  # 第 1 行是 '{'
        except ValueError:
            return 0

    # -- 派生视图 ---------------------------------------------------------
    def slots(self, prefix: str) -> dict[int, Slot]:
        """把某容器的四元组聚合成槽位。"""
        out: dict[int, Slot] = {}
        for key in self.order:
            parts = schema.slot_family(key)
            if not parts or parts[0] != prefix:
                continue
            _, fld, idx = parts
            slot = out.setdefault(idx, Slot(prefix=prefix, index=idx))
            slot.present.add(fld)
            value = self.values[key]
            if fld == "name":
                slot.name = value if isinstance(value, str) else str(value)
            elif isinstance(value, int) and not isinstance(value, bool):
                setattr(slot, fld, value)
        return out

    def prefix_slots(self) -> dict[str, dict[int, Slot]]:
        prefixes = {p[0] for p in (schema.slot_family(k) for k in self.order) if p}
        return {pre: self.slots(pre) for pre in sorted(prefixes)}

    def pet_stats(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key in self.order:
            import re as _re
            m = schema.PET_STAT_RE.match(key)
            if not m:
                continue
            out.setdefault(m.group("pet"), {})[m.group("stat")] = self.values[key]
        return out

    def quests(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key in self.order:
            if key.startswith("Old Quest: "):
                prefix, complete_prefix, daily_prefix = "Old Quest: ", "Old Quest Complete: ", "Old Daily: "
                line = "old"
            elif key.startswith("Quest: "):
                prefix, complete_prefix, daily_prefix = "Quest: ", "Quest Complete: ", "Daily: "
                line = "current"
            else:
                continue
            rest = key[len(prefix):]
            if schema.QUEST_PROG_RE.match(rest):
                continue
            rows.append({
                "key": key,
                "title": rest,
                "line": line,
                "step": self.values[key],
                "times": self.get(f"{complete_prefix}{rest}", 0),
                "daily": self.get(f"{daily_prefix}{rest}"),
            })
        return rows

    def achievements(self) -> list[dict[str, Any]]:
        claimed: dict[str, Any] = {}
        progress: dict[str, list[tuple[str, Any]]] = {}
        for key in self.order:
            if not key.startswith("Achieve: "):
                continue
            rest = key[len("Achieve: "):]
            m = schema.ACHIEVE_PROG_RE.match(rest)
            if m:
                progress.setdefault(m.group("title"), []).append((rest, self.values[key]))
            else:
                claimed[rest] = self.values[key]
        titles = list(dict.fromkeys(list(claimed) + list(progress)))
        return [
            {
                "title": t,
                "claimed": bool(claimed.get(t)),
                "key": f"Achieve: {t}",
                "progress": progress.get(t, []),
            }
            for t in sorted(titles, key=schema.natural_key)
        ]

    def recipes(self, line: str | None = None) -> list[tuple[str, str, Any]]:
        """返回 (前缀, 配方名, 值)。旧任务线的解锁键是 `Old Recipe: `。"""
        out: list[tuple[str, str, Any]] = []
        for key in self.order:
            for prefix, tag in (("Old Recipe: ", "Old Recipe: "), ("Recipe: ", "Recipe: ")):
                if not key.startswith(prefix):
                    continue
                if line == "old" and not prefix.startswith("Old"):
                    continue
                if line == "current" and prefix.startswith("Old"):
                    continue
                out.append((tag, key[len(prefix):], self.values[key]))
                break
        return out


def _same(a: Any, b: Any) -> bool:
    if kind_of(a) != kind_of(b):
        return False
    return a == b
