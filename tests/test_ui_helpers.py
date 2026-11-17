"""界面性能相关的小工具回归：模式视图副本、详情下拉候选。

对应 docs/14-ui-render-performance.md 的 P0/P1 改动，纯逻辑，不启动 Streamlit。
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import modeview  # noqa: E402
import model  # noqa: E402
from views.fields import MAX_PICK_OPTIONS, _pick_pool  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


def _doc(keys: int = 50) -> model.SaveDoc:
    data = {"charName": "Tester", "Current Level": 3}
    for i in range(keys):
        data[f"Slot_{i}"] = i
    return model.SaveDoc.from_dict(data)


def test_copy_detaches() -> None:
    doc = _doc()
    view = modeview.ModeViewDoc(doc, "story")
    snapshot = copy.copy(view.values)
    check("副本是普通 dict", type(snapshot) is dict, type(snapshot).__name__)
    check("副本内容一致", snapshot == dict(view.values))
    view.values["Current Level"] = 9
    check("改代理不影响副本", snapshot["Current Level"] == 3)
    check("代理写回父档", doc.get("Current Level") == 9)


def test_copy_does_not_sync() -> None:
    doc = _doc()
    view = modeview.ModeViewDoc(doc, "story")
    calls = {"n": 0}
    original = view._sync

    def counted() -> None:
        calls["n"] += 1
        original()

    view._sync = counted  # type: ignore[method-assign]
    copy.copy(view.values)
    check("拷贝不再触发同步", calls["n"] == 0, str(calls["n"]))


def test_pick_pool() -> None:
    keys = [f"Key {i:03d}" for i in range(500)]
    pool = _pick_pool(keys, "Key 000", "")
    check("默认截断到上限", len(pool) == MAX_PICK_OPTIONS, str(len(pool)))
    check("焦点在首位之外也能保留", "Key 400" in _pick_pool(keys, "Key 400", "Key 1"))
    check("搜索命中", all("Key 12" in k for k in _pick_pool(keys, "Key 120", "Key 12")))
    check("无命中时至少保留焦点", _pick_pool(keys, "Key 000", "zzz") == ["Key 000"])
    check("空键集不报错", _pick_pool([], "", "") == [])


def main() -> int:
    for title, fn in (("副本与代理", test_copy_detaches),
                      ("拷贝不触发同步", test_copy_does_not_sync),
                      ("下拉候选", test_pick_pool)):
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
