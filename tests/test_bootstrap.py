"""启动引导：依赖解析、版本比对、空闲端口。"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bootstrap  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


def test_parse() -> None:
    pinned = bootstrap.parse_requirements()
    check("解析出固定版本", len(pinned) >= 5, str(len(pinned)))
    names = dict(pinned)
    check("包含 streamlit", names.get("streamlit") == "1.67.0", str(names.get("streamlit")))
    check("忽略注释与空行", all(name and version for name, version in pinned))


def test_missing() -> None:
    with mock.patch.object(bootstrap.metadata, "version",
                           side_effect=bootstrap.metadata.PackageNotFoundError("demo")):
        problems = bootstrap.missing_requirements([("demo", "1.0")])
    check("缺包被识别", problems and "not installed" in problems[0], str(problems))

    with mock.patch.object(bootstrap.metadata, "version", return_value="0.9"):
        problems = bootstrap.missing_requirements([("demo", "1.0")])
    check("版本不符被识别", problems and "expected 1.0" in problems[0], str(problems))

    with mock.patch.object(bootstrap.metadata, "version", return_value="1.0"):
        check("版本一致无告警", bootstrap.missing_requirements([("demo", "1.0")]) == [])


def test_free_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 8501))
        held.listen(1)
        port = bootstrap.find_free_port(8501, attempts=3)
    check("跳过被占用端口", port != 8501, str(port))
    check("端口在候选范围内", 8502 <= port <= 8503, str(port))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


def main() -> int:
    for title, fn in (("依赖清单", test_parse), ("缺失判定", test_missing),
                      ("端口选择", test_free_port)):
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
