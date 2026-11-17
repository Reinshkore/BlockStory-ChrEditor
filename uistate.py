"""界面会话状态：导航、编辑开关与跨页面的临时选择。

这些状态一律由控件回调（``on_click`` / ``on_change``）修改，渲染函数只读。
理由：Streamlit 默认开启 ``runner.fastReruns``，新交互会中断正在跑的脚本；
如果在绘制过程中写 ``session_state``，被中断的那一轮会留下"改了一半"的状态，
下一次运行读到它就是两个页面的内容混在一起。回调在渲染之前执行，天然没有这个问题。

函数都接受可选的 ``ss``，默认取 ``st.session_state``——回调里不用传，
单元测试可以直接传一个简单的命名空间对象。
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def _state(ss=None):
    return st.session_state if ss is None else ss


def close_transients(ss=None) -> None:
    """关闭格子弹窗与未完成的点选移动（离开物品页、切档、退出编辑时）。"""
    ss = _state(ss)
    ss.slot_target = None
    ss.item_move_source = None


def goto(page: str, ss=None) -> None:
    """切页。作为按钮回调使用：状态在渲染前就位，页面不必再跑第二轮。"""
    ss = _state(ss)
    if ss.get("nav") == page:
        return
    close_transients(ss)
    ss.language_dialog = False
    ss.nav = page


def on_editable_change(ss=None) -> None:
    """退出编辑模式时收掉只在编辑状态有意义的临时选择。"""
    ss = _state(ss)
    if not ss.get("editable"):
        close_transients(ss)


def open_slot(prefix: str, index: int, ss=None) -> None:
    _state(ss).slot_target = (prefix, index)


def set_value(key: str, value: Any, ss=None) -> None:
    """通用回调：把常量写进会话状态（开关、展开状态等）。"""
    _state(ss)[key] = value


def forget(*keys: str, ss=None) -> None:
    """丢掉指定键。换档时清理属于上一份存档的控件状态。"""
    ss = _state(ss)
    for key in keys:
        ss.pop(key, None)


def request_readonly(ss=None) -> None:
    """请求退出编辑模式（写盘、恢复备份、换档后）。

    不能直接写 ``ss.editable``：它现在是侧栏开关的 widget key，
    控件实例化之后再写会触发 Streamlit 的 "cannot be modified after the widget
    ... is instantiated"。这里只留一个待办标记，由 ``apply_pending`` 在下一次
    渲染开始、控件尚未创建时落实。
    """
    _state(ss)["_readonly_requested"] = True


def apply_pending(ss=None) -> None:
    """在新一轮渲染的最前面落实上一轮排队的状态变更。"""
    ss = _state(ss)
    if ss.pop("_readonly_requested", False):
        ss.editable = False
