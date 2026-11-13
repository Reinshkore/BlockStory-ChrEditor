"""编解码器回归测试。

直接运行：  .venv\\Scripts\\python.exe tests\\test_bsjson.py
也可被 pytest 收集：pytest tests/
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bsjson  # noqa: E402

SAVE_DIR = Path(os.environ.get("BS_SAVE_DIR",
                               r"C:\Users\Administrator\AppData\LocalLow\Mindblocks\Block Story\characters"))

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


# --------------------------------------------------------------------------- #

def test_float_format() -> None:
    cases = {
        0.3: ".3",
        0.0: ".0",
        -0.05: "-.05",
        400.0: "400.0",
        850.0: "850.0",
        0.6000001: ".6000001",
        29.18341: "29.18341",
        1635.397: "1635.397",
        -0.5: "-.5",
        2.0: "2.0",
        1e-7: ".0000001",
    }
    for value, expect in cases.items():
        got = bsjson.fmt_float(value)
        check(f"fmt_float({value}) == {expect!r}", got == expect, f"got {got!r}")


def test_escape() -> None:
    check("ASCII 原样", bsjson.escape_string("abc") == '"abc"')
    check("引号与反斜杠", bsjson.escape_string('a"b\\c') == '"a\\"b\\\\c"')
    check("控制字符", bsjson.escape_string("\n\t\x00") == '"\\n\\t\\u0000"')
    check("中文转义", bsjson.escape_string("冈塔") == '"\\u5188\\u5854"')
    check("DEL 也转义", bsjson.escape_string("\x7f") == '"\\u007f"')
    # 星号平面字符在 C# 里是逐 UTF-16 码元转义，必须产出代理对
    check("代理对", bsjson.escape_string("\U0001F600") == '"\\ud83d\\ude00"')


def test_types() -> None:
    res = bsjson.loads('{\n"a":1,\n"b":1.0,\n"c":.5,\n"d":"1",\n"e":true}'.replace("\n", "\n"))
    d = dict(res.entries)
    check("无小数点 → int", isinstance(d["a"], int) and not isinstance(d["a"], bool))
    check("1.0 → float", isinstance(d["b"], float))
    check(".5 → float", isinstance(d["c"], float) and abs(d["c"] - 0.5) < 1e-9)
    check("引号 → str", d["d"] == "1")
    check("true → bool", d["e"] is True)


def test_errors() -> None:
    try:
        bsjson.loads('{\n"a":1\n"b":2\n}')
    except bsjson.SaveParseError as exc:
        check("缺逗号报错并给出行号", exc.line == 3, f"line={exc.line}")
    else:
        check("缺逗号报错", False)

    try:
        bsjson.loads("not json at all")
    except bsjson.SaveParseError as exc:
        check("非对象开头报错", exc.line == 1)
    else:
        check("非对象开头报错", False)

    res = bsjson.loads('{\n"k":1,\n"k":2\n}')
    check("重复键被记录", res.duplicates == ["k"])
    check("重复键被警告", any("重复" in w for w in res.warnings))


def test_int32_overflow() -> None:
    res = bsjson.loads('{\n"big":3000000000\n}')
    value = dict(res.entries)["big"]
    check("超 Int32 变成 float（复刻游戏行为）", isinstance(value, float))
    check("并给出警告", any("Int32" in w for w in res.warnings))


def test_roundtrip_real_saves() -> None:
    files = sorted(glob.glob(str(SAVE_DIR / "*.chr"))) + sorted(glob.glob(str(SAVE_DIR / "*.bak_*")))
    if not files:
        print("  skip 未找到真实存档，跳过往返测试")
        return
    for path in files:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        if not raw.lstrip().startswith("{"):
            print(f"  skip {Path(path).name} 非明文存档")
            continue
        res = bsjson.loads(raw)
        out = bsjson.dumps_entries(res.entries)
        check(f"往返一致 {Path(path).name}", out == raw,
              f"len {len(raw)} -> {len(out)}")


def test_roundtrip_synthetic() -> None:
    doc = [
        ("charName", "测试角色"),
        ("charGender", "Male"),
        ("Current Level", 69),
        ("Current Health", 850.0),
        ("Max Health Regen", 0.3),
        ("Max Hunger Regen", -0.05),
        ("Quest: Dragon Training", "#end"),
        ("Achieve: Goblin Miner break 65594", 83),
        ("Recipe: Health Potion", 1),
    ]
    text = bsjson.dumps_entries(doc)
    back = bsjson.loads(text).entries
    # 浮点会以 float32 精度回来，逐项比较时放宽容差
    same = len(back) == len(doc) and all(
        (a[0] == b[0]) and (
            isinstance(a[1], float) and isinstance(b[1], float) and abs(a[1] - b[1]) < 1e-6
            or a[1] == b[1]
        )
        for a, b in zip(doc, back)
    )
    check("中文键值往返", same, f"{back}")
    check("无末尾换行", not text.endswith("\n"))
    check("每行一个键", text.count("\n") == len(doc) + 1)


def main() -> int:
    groups = [
        ("浮点格式", test_float_format),
        ("字符串转义", test_escape),
        ("类型判定", test_types),
        ("错误定位", test_errors),
        ("Int32 边界", test_int32_overflow),
        ("真实存档往返", test_roundtrip_real_saves),
        ("合成数据往返", test_roundtrip_synthetic),
    ]
    for title, fn in groups:
        print(f"\n[{title}]")
        fn()

    print()
    if _failures:
        print(f"失败 {len(_failures)} 项：{_failures}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
