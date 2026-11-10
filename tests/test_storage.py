"""写入链路测试：备份、原子替换、回读自检、还原。

一律在临时目录的副本上跑，绝不碰真实存档。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import storage  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


def make_copy(tmp: Path) -> Path:
    # 固定使用合成样本：测试只验证写入链路，不应被本机当前存档的键集影响。
    target = tmp / "characters" / "testchar.chr"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        ('{\n"charName":"Tester",\n"Current Level":1,\n'
         '"Inventory_name_4":"Stone",\n"Inventory_count_4":5\n}').encode("utf-8"))
    return target


def test_read(tmp: Path) -> None:
    path = make_copy(tmp)
    doc = storage.read_save(path)
    check("读到键", len(doc.values) >= 2)
    check("路径记录", doc.path == path)
    check("往返一致", doc.serialize() == doc.raw)


def test_write_creates_backup(tmp: Path) -> None:
    path = make_copy(tmp)
    doc = storage.read_save(path)
    before = path.read_bytes()
    doc.push_undo("test")
    doc.set("Current Level", 42)
    result = storage.write_save(doc, path)

    check("写入成功", result.path == path)
    check("生成了备份", result.backup is not None and result.backup.exists())
    check("备份内容等于原文", result.backup.read_bytes() == before if result.backup else False)
    check("主文件已更新", path.read_bytes() != before)

    again = storage.read_save(path)
    check("回读拿到新值", again.get("Current Level") == 42)
    check("键数不变", len(again.values) == len(doc.values))


def test_write_is_bom_free_and_lf(tmp: Path) -> None:
    path = make_copy(tmp)
    doc = storage.read_save(path)
    doc.push_undo("test")
    doc.set("Current Level", 43)
    storage.write_save(doc, path)
    raw = path.read_bytes()
    check("无 BOM", not raw.startswith(b"\xef\xbb\xbf"))
    check("无 CRLF", b"\r\n" not in raw)
    check("末尾无换行", not raw.endswith(b"\n"))


def test_identical_write(tmp: Path) -> None:
    path = make_copy(tmp)
    doc = storage.read_save(path)
    result = storage.write_save(doc, path)
    check("未改动时标记为相同", result.identical_to_original)
    check("内容确实相同", doc.serialize() == path.read_text(encoding="utf-8"))


def test_reject_bad_content(tmp: Path) -> None:
    path = make_copy(tmp)
    doc = storage.read_save(path)
    doc.values["Current Level"] = 1.5      # 故意把整数键写成浮点
    try:
        storage.write_save(doc, path)
    except storage.SaveError as exc:
        check("写入前拦下类型漂移", exc.stage in {"validate", "verify"}, exc.stage)
        check("错误信息指明键名", "Current Level" in str(exc), str(exc))
    else:
        check("写入前拦下类型漂移", False, "写入没有被阻止")


def test_read_errors(tmp: Path) -> None:
    bad = tmp / "bad.chr"
    bad.write_text("this is not json", encoding="utf-8")
    try:
        storage.read_save(bad)
    except storage.SaveError as exc:
        check("非 JSON 报 parse", exc.stage == "parse")
    else:
        check("非 JSON 报 parse", False)

    missing = tmp / "nope.chr"
    try:
        storage.read_save(missing)
    except storage.SaveError as exc:
        check("缺文件报 read", exc.stage == "read")
    else:
        check("缺文件报 read", False)


def test_restore_backup(tmp: Path) -> None:
    path = make_copy(tmp)
    original = path.read_bytes()
    doc = storage.read_save(path)
    doc.push_undo("test")
    doc.set("Current Level", 99)
    result = storage.write_save(doc, path)
    storage.restore_backup(result.backup, path)
    check("还原成功", path.read_bytes() == original)
    check("还原也留下备份", len(storage.list_backups(path)) >= 2)


def test_prune_backups(tmp: Path) -> None:
    path = make_copy(tmp)
    doc = storage.read_save(path)
    for level in range(12):
        doc.push_undo("loop")
        doc.set("Current Level", 100 + level)
        storage.write_save(doc, path, keep=5)
    backups = storage.list_backups(path)
    check("备份数量被限制", len(backups) <= 6, str(len(backups)))


def test_labels(tmp: Path) -> None:
    name = "testchar_labels"
    storage.save_labels(name, {"a": "quest", "b": "recipe"})
    loaded = storage.load_labels(name)
    check("标注可持久化", loaded == {"a": "quest", "b": "recipe"})
    Path(storage._label_path(name)).unlink(missing_ok=True)  # noqa: SLF001


def main() -> int:
    print("样本：合成存档（不依赖本机存档）")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        groups = [
            ("读取", lambda: test_read(tmp)),
            ("写入与备份", lambda: test_write_creates_backup(tmp)),
            ("编码细节", lambda: test_write_is_bom_free_and_lf(tmp)),
            ("未改动写入", lambda: test_identical_write(tmp)),
            ("自检拦截", lambda: test_reject_bad_content(tmp)),
            ("读取错误", lambda: test_read_errors(tmp)),
            ("备份还原", lambda: test_restore_backup(tmp)),
            ("备份轮转", lambda: test_prune_backups(tmp)),
            ("分类标注", lambda: test_labels(tmp)),
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
