"""Block Story `.chr` 存档编解码器。

复刻游戏内 `BlockStory.MiniJSON` 的读写行为（14.5.3，Assembly-CSharp.dll）：

读取（Json.Deserialize → ParseNumber）：
    词元不含 '.' → 先试 int（Int32），失败再试 float
    其余 → float（单精度）

写出（Serializer）：
    对象：'{\n' + 'k':v 之间以 ',\n' 分隔 + '\n}'
    字符串：非 ASCII 与控制字符一律写成 \\uXXXX（小写、左侧补零）
    浮点：ToString(".0###########", InvariantCulture)  —— 小数点前无 0，至少 1 位小数
    整数：十进制

因此本模块可以把任何读入的存档重新序列化成与游戏逐字节相同的文本。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

__all__ = [
    "SaveParseError",
    "ParseResult",
    "entry_kind",
    "fmt_float",
    "escape_string",
    "loads",
    "dumps",
    "dumps_entries",
    "parse_float_text",
]

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


# --------------------------------------------------------------------------- #
# 浮点格式：复刻 float.ToString(".0###########")
# --------------------------------------------------------------------------- #

def _f32(x: float) -> float:
    """把一个 Python float 收窄到 float32，模拟 C# 的 float 精度。"""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _shortest_digits(f: float) -> str:
    """取能唯一还原该 float32 的最短十进制数字串（等价于 .NET 的往返表示）。"""
    if f == 0.0:
        return "0"
    for prec in range(1, 10):  # float32 最多需要 9 位有效数字
        s = f"{f:.{prec}g}"
        try:
            if _f32(float(s)) == f:
                return s
        except (ValueError, OverflowError):
            continue
    return repr(f)


def fmt_float(value: float) -> str:
    """按 C# 的 ".0###########" 格式输出 float。

    >>> fmt_float(0.3), fmt_float(0.0), fmt_float(-0.05), fmt_float(400.0)
    ('.3', '.0', '-.05', '400.0')

    已知差异：负零（-0.0）统一写成 ".0"。游戏存档里不会出现 -.0，
    且 ".0" 读回后语义等价，故不做区分。
    """
    f = _f32(float(value))
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError("float32 无法表示 NaN / Infinity")

    digits = _shortest_digits(f)
    d = Decimal(digits)

    # 展开科学计数法，并截断到 12 位小数（格式串里 '0' + 11 个 '#'）
    if d.as_tuple().exponent < -12:
        d = d.quantize(Decimal("1.000000000000"), rounding=ROUND_HALF_UP)

    text = format(d, "f")
    if "." not in text:
        text += ".0"
    if text.startswith("0."):
        text = text[1:]
    elif text.startswith("-0."):
        text = "-" + text[2:]
    return text


def parse_float_text(text: str) -> float:
    """把存档里的数字词元转成 float32（复刻 float.TryParse 的行为）。"""
    return _f32(float(text))


# --------------------------------------------------------------------------- #
# 字符串转义
# --------------------------------------------------------------------------- #

_SIMPLE_ESCAPES = {
    0x22: '\\"',
    0x5C: "\\\\",
    0x08: "\\b",
    0x0C: "\\f",
    0x0A: "\\n",
    0x0D: "\\r",
    0x09: "\\t",
}


def escape_string(text: str) -> str:
    """按游戏的 SerializeString 逐 UTF-16 码元转义（中文会变成 \\uXXXX）。"""
    if not isinstance(text, str):
        raise TypeError("escape_string 只接受 str")
    out = ['"']
    raw = text.encode("utf-16-le")
    for i in range(0, len(raw), 2):
        unit = raw[i] | (raw[i + 1] << 8)
        simple = _SIMPLE_ESCAPES.get(unit)
        if simple is not None:
            out.append(simple)
        elif 32 <= unit <= 126:
            out.append(chr(unit))
        else:
            out.append(f"\\u{unit:04x}")
    out.append('"')
    return "".join(out)


# --------------------------------------------------------------------------- #
# 类型判定
# --------------------------------------------------------------------------- #

def entry_kind(value: Any) -> str:
    """返回 'int' / 'float' / 'str' / 'bool' / 'null' / 'other'。"""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if value is None:
        return "null"
    return "other"


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class SaveParseError(ValueError):
    message: str
    line: int
    column: int
    offset: int

    def __str__(self) -> str:  # pragma: no cover - 仅用于展示
        return f"第 {self.line} 行第 {self.column} 列：{self.message}"


@dataclass(slots=True)
class ParseResult:
    entries: list[tuple[str, Any]]
    duplicates: list[str]
    warnings: list[str]
    had_bom: bool
    newline: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.entries)

    @property
    def keys(self) -> list[str]:
        return [k for k, _ in self.entries]


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.n = len(text)
        self.duplicates: list[str] = []
        self.warnings: list[str] = []

    # -- 定位 -------------------------------------------------------------
    def _loc(self, offset: int | None = None) -> tuple[int, int]:
        off = self.pos if offset is None else offset
        line = self.text.count("\n", 0, off) + 1
        last_nl = self.text.rfind("\n", 0, off)
        col = off - last_nl
        return line, col

    def _fail(self, message: str, offset: int | None = None) -> None:
        off = self.pos if offset is None else offset
        line, col = self._loc(off)
        raise SaveParseError(message, line, col, off)

    # -- 基础 -------------------------------------------------------------
    def _peek(self) -> str:
        return self.text[self.pos] if self.pos < self.n else ""

    def _skip_ws(self) -> None:
        while self.pos < self.n and self.text[self.pos] in " \t\r\n\ufeff":
            self.pos += 1

    def _expect(self, ch: str) -> None:
        self._skip_ws()
        if self._peek() != ch:
            got = self._peek() or "文件结尾"
            self._fail(f"期望 {ch!r}，实际是 {got!r}")
        self.pos += 1

    # -- 值 ---------------------------------------------------------------
    def parse_document(self) -> list[tuple[str, Any]]:
        self._skip_ws()
        if self._peek() != "{":
            self._fail("存档应当以 '{' 开头（或者它其实是加密文件）")
        return self._parse_object()

    def _parse_object(self) -> list[tuple[str, Any]]:
        self._expect("{")
        entries: list[tuple[str, Any]] = []
        seen: set[str] = set()
        self._skip_ws()
        if self._peek() == "}":
            self.pos += 1
            return entries
        while True:
            self._skip_ws()
            if self._peek() != '"':
                self._fail("对象键必须是双引号字符串")
            key_start = self.pos
            key = self._parse_string()
            if key in seen:
                self.duplicates.append(key)
                line, _ = self._loc(key_start)
                self.warnings.append(f"第 {line} 行：键 {key!r} 重复出现，游戏只会保留最后一个")
            seen.add(key)
            self._expect(":")
            value = self._parse_value()
            entries.append((key, value))
            self._skip_ws()
            ch = self._peek()
            if ch == ",":
                self.pos += 1
                continue
            if ch == "}":
                self.pos += 1
                return entries
            self._fail(f"对象内期望 ',' 或 '}}'，实际是 {ch!r}")

    def _parse_value(self) -> Any:
        self._skip_ws()
        ch = self._peek()
        if ch == "":
            self._fail("值缺失（文件意外结束）")
        if ch == "{":
            return dict(self._parse_object())
        if ch == "[":
            return self._parse_array()
        if ch == '"':
            return self._parse_string()
        if self.text.startswith("true", self.pos):
            self.pos += 4
            return True
        if self.text.startswith("false", self.pos):
            self.pos += 5
            return False
        if self.text.startswith("null", self.pos):
            self.pos += 4
            return None
        return self._parse_number()

    def _parse_array(self) -> list[Any]:
        self._expect("[")
        items: list[Any] = []
        self._skip_ws()
        if self._peek() == "]":
            self.pos += 1
            return items
        while True:
            items.append(self._parse_value())
            self._skip_ws()
            ch = self._peek()
            if ch == ",":
                self.pos += 1
                continue
            if ch == "]":
                self.pos += 1
                return items
            self._fail(f"数组内期望 ',' 或 ']'，实际是 {ch!r}")

    def _parse_string(self) -> str:
        assert self._peek() == '"'
        self.pos += 1
        chunks: list[str] = []
        while True:
            if self.pos >= self.n:
                self._fail("字符串没有闭合")
            ch = self.text[self.pos]
            if ch == '"':
                self.pos += 1
                return "".join(chunks)
            if ch == "\\":
                self.pos += 1
                esc = self._peek()
                if esc == "":
                    self._fail("转义符后文件结束")
                if esc == "u":
                    hexpart = self.text[self.pos + 1 : self.pos + 5]
                    if len(hexpart) != 4:
                        self._fail("\\u 转义不完整")
                    try:
                        chunks.append(chr(int(hexpart, 16)))
                    except ValueError:
                        self._fail(f"\\u{hexpart} 不是合法的十六进制")
                    self.pos += 5
                    continue
                mapping = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                if esc not in mapping:
                    self._fail(f"未知的转义 \\{esc}")
                chunks.append(mapping[esc])
                self.pos += 1
                continue
            chunks.append(ch)
            self.pos += 1

    def _parse_number(self) -> Any:
        start = self.pos
        while self.pos < self.n and self.text[self.pos] in "+-0123456789.eE":
            self.pos += 1
        token = self.text[start : self.pos]
        if not token:
            self._fail(f"无法识别的值 {self._peek()!r}")

        if "." not in token:
            try:
                ivalue = int(token)
            except ValueError:
                pass
            else:
                if INT32_MIN <= ivalue <= INT32_MAX:
                    return ivalue
                self.warnings.append(
                    f"整数 {token} 超出 Int32 范围，游戏会按 float 读入（随后 GetInt 可能异常）"
                )
        try:
            return parse_float_text(token)
        except ValueError:
            self._fail(f"非法数字 {token!r}", start)

    # -- 结语 -------------------------------------------------------------
    def ensure_eof(self) -> None:
        self._skip_ws()
        if self.pos < self.n:
            self._fail("对象结束后仍有内容")


def loads(text: str) -> ParseResult:
    """解析存档文本。失败时抛 SaveParseError（带行/列）。"""
    if text is None:
        raise SaveParseError("内容为空", 1, 1, 0)
    had_bom = text.startswith("\ufeff")
    if had_bom:
        text = text[1:]
    newline = "\r\n" if "\r\n" in text else "\n"

    parser = _Parser(text)
    entries = parser.parse_document()
    parser.ensure_eof()
    return ParseResult(
        entries=entries,
        duplicates=parser.duplicates,
        warnings=parser.warnings,
        had_bom=had_bom,
        newline=newline,
    )


# --------------------------------------------------------------------------- #
# 序列化
# --------------------------------------------------------------------------- #

def _serialize_value(value: Any) -> str:
    kind = entry_kind(value)
    if kind == "str":
        return escape_string(value)
    if kind == "bool":
        return "true" if value else "false"
    if kind == "null":
        return "null"
    if kind == "int":
        return str(value)
    if kind == "float":
        return fmt_float(value)
    raise TypeError(f"不支持的值类型：{type(value)!r}")


def dumps_entries(entries: list[tuple[str, Any]]) -> str:
    """把 (键, 值) 序列化成与游戏一致的文本（无末尾换行）。"""
    if not entries:
        return "{\n\n}"
    parts = []
    for key, value in entries:
        parts.append(f"{escape_string(str(key))}:{_serialize_value(value)}")
    return "{\n" + ",\n".join(parts) + "\n}"


def dumps(mapping: dict[str, Any]) -> str:
    return dumps_entries(list(mapping.items()))
