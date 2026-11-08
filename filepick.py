"""调用 Windows 原生文件选择框。

浏览器里的 `st.file_uploader` 只能拿到文件字节，拿不到路径；这个工具需要的是
"在磁盘上打开这个文件"，所以必须借宿主机的系统对话框。

实现要点：
- 在**子进程**里跑 tkinter。Streamlit 的脚本跑在工作线程里，直接建 Tk 根窗口在部分
  环境会报 "main thread is not in main loop"，隔离到独立进程最稳。
- 子进程用 `CREATE_NO_WINDOW` 启动，避免每次弹一个黑色控制台。
- 只在本机运行时才有意义：对话框出现在**运行本程序的那台机器**上。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_CHILD = r"""
import json, sys
import tkinter as tk
from tkinter import filedialog

cfg = json.loads(sys.argv[1])
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
path = filedialog.askopenfilename(
    title=cfg.get("title") or "Select save file",
    initialdir=cfg.get("initialdir") or None,
    filetypes=[("Block Story save", "*.chr"), ("Text / JSON", "*.chr *.json *.txt"),
               ("All files", "*.*")],
)
root.destroy()
sys.stdout.write(path or "")
"""


def available() -> bool:
    try:
        import tkinter  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def pick_file(initial_dir: str | Path | None = None, title: str = "") -> str | None:
    """弹出系统文件选择框。返回绝对路径；用户取消则返回 None。

    失败（没有 tkinter、被系统拒绝）时抛 RuntimeError，由界面降级为手动输入。
    """
    import json

    cfg = json.dumps({"initialdir": str(initial_dir) if initial_dir else "", "title": title})
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD, cfg],
            capture_output=True, text=True, timeout=600, creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(str(exc)) from exc
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "").strip() or f"exit {proc.returncode}")
    path = (proc.stdout or "").strip()
    return path or None


if __name__ == "__main__":  # 手动试：python filepick.py
    print(pick_file(Path.home(), "Pick a .chr file"))
