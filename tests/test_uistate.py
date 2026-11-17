"""界面状态回调的回归：导航、临时选择、退出编辑模式的延迟生效。

这些函数不依赖 Streamlit 运行时——传一个简单的命名空间对象就能测。
对应 docs/14-ui-render-performance.md 的 P2「把渲染期的状态写入挪进回调」。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uistate  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


class FakeState(dict):
    """够用的 session_state 替身：同时支持 d["k"] 与 d.k 两种访问。"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self[name] = value


def _ss(**extra) -> FakeState:
    base = FakeState(nav="overview", language_dialog=False, editable=False,
                     slot_target=None, item_move_source=None, active_nav="overview")
    base.update(extra)
    return base


def test_goto() -> None:
    ss = _ss(slot_target=("Inventory", 3), item_move_source=("Inventory", 1),
             language_dialog=True)
    uistate.goto("items", ss)
    check("切页写入 nav", ss.nav == "items")
    check("切页关闭语言弹窗", ss.language_dialog is False)
    check("切页清掉格子弹窗与移动源",
          ss.slot_target is None and ss.item_move_source is None)

    ss.slot_target = ("Inventory", 2)
    uistate.goto("items", ss)
    check("点当前页不清状态", ss.slot_target == ("Inventory", 2))

    ss2 = _ss(nav="items", slot_target=("Inventory", 5))
    uistate.goto("fields", ss2)
    check("离开物品页清掉临时选择", ss2.slot_target is None and ss2.nav == "fields")


def test_editable_change() -> None:
    ss = _ss(editable=False, slot_target=("Inventory", 1), item_move_source=("Inventory", 2))
    uistate.on_editable_change(ss)
    check("退出编辑收临时选择",
          ss.slot_target is None and ss.item_move_source is None)

    ss2 = _ss(editable=True, slot_target=("Inventory", 1), item_move_source=("Inventory", 2))
    uistate.on_editable_change(ss2)
    check("保持编辑时不动临时选择",
          ss2.slot_target == ("Inventory", 1) and ss2.item_move_source == ("Inventory", 2))


def test_readonly_request() -> None:
    ss = _ss(editable=True)
    uistate.request_readonly(ss)
    check("请求只排队，不立刻改开关", ss.editable is True and ss._readonly_requested is True)
    uistate.apply_pending(ss)
    check("下一次渲染开头落实", ss.editable is False)
    check("标记被消费掉", not hasattr(ss, "_readonly_requested"))

    ss2 = _ss(editable=True)
    uistate.apply_pending(ss2)
    check("没有请求时不改开关", ss2.editable is True)


def test_helpers() -> None:
    ss = _ss()
    uistate.set_value("i_show_all", True, ss)
    check("set_value 写常量", ss.i_show_all is True)
    uistate.open_slot("Inventory", 7, ss)
    check("open_slot 写元组", ss.slot_target == ("Inventory", 7))
    ss.f_pickkey = "Current Level"
    ss.f_page = 3
    ss.keep = "x"
    uistate.forget("f_pickkey", "f_page", "missing", ss=ss)
    check("forget 只删列出的键",
          not hasattr(ss, "f_pickkey") and not hasattr(ss, "f_page") and ss.keep == "x")


def main() -> int:
    for title, fn in (("导航回调", test_goto),
                      ("编辑开关回调", test_editable_change),
                      ("退出编辑的延迟生效", test_readonly_request),
                      ("小工具", test_helpers)):
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
