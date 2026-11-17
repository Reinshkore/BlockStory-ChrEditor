"""14.5.x 回归：模式等级、技能点双公式、沙盒硬核开关、广告票券键。

文件名沿用当时的 "14.5.5" 说法；实际取证基线是 14.5.4（2026-11-13 缓存），
版本核对见 docs/13-1455-update-review.md 第十一节。

全部在临时目录的合成存档上运行，不读取也不写入真实存档。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import modeops  # noqa: E402
import modeview  # noqa: E402
import model  # noqa: E402
import reset as reset_mod  # noqa: E402
import schema  # noqa: E402
import storage  # noqa: E402
import validate  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


def _sandbox_values() -> dict:
    return {
        "charName": "Demo",
        "Purchased Skill Points": 300,
        "Current Level_sandbox": 63,
        "Current Experience_sandbox": 0,
        "Skill Points_sandbox": 1,
        "Max Health_sandbox": 1300.0,
        "Max Mana_sandbox": 100.0,
        "Max Breath_sandbox": 30.0,
        "Max Sword Damage_sandbox": 280.0,
        "Max Magic Damage_sandbox": 0.0,
        "Max Bow Force_sandbox": 0.0,
        "Max Bow Damage_sandbox": 0.0,
        "Max Gun Damage_sandbox": 0.0,
        "Max Loot Distance_sandbox": 0.0,
        "Max Walk Speed_sandbox": 0.0,
        "Max Fly Speed_sandbox": 4.999998092651367,
        "Max Dig Speed_sandbox": 1.0,
        "Sandbox Hardmode Switch?_sandbox": "yes",
    }


def _write_save(folder: Path, name: str, values: dict) -> Path:
    path = folder / f"{name}.chr"
    path.write_text(json.dumps(values, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def test_sidebar_level() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        path = _write_save(folder, "SandboxOnly", _sandbox_values())
        infos = storage.list_saves(folder)
        check("仅沙盒存档的列表等级取后缀键", infos[0].level == 63,
              str(infos[0].level))
        doc = storage.read_save(path)
        check("仅有沙盒数据时建议切到沙盒",
              modeops.suggest_mode(doc, "story") == "sandbox")
        check("当前模式已有数据时不改选择",
              modeops.suggest_mode(doc, "sandbox") is None)

        story_path = _write_save(folder, "StoryAndSandbox",
                                 {"charName": "Demo", "Current Level": 12,
                                  "Current Level_sandbox": 63})
        story_doc = storage.read_save(story_path)
        check("剧情与沙盒并存时优先剧情",
              modeops.suggest_mode(story_doc, "creative") == "story")
        story_info = next(i for i in storage.list_saves(folder) if i.name == "StoryAndSandbox")
        check("无后缀等级优先于模式后缀", story_info.level == 12,
              str(story_info.level))


def test_skill_points() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        path = _write_save(folder, "Demo", _sandbox_values())
        doc = storage.read_save(path)
        view = modeview.ModeViewDoc(doc, "sandbox")

        check("63 级自然升级总量 451", schema.earned_skill_points(63, 300) == 451,
              str(schema.earned_skill_points(63, 300)))
        check("63 级技能重置总量 455", schema.reset_skill_points(63, 300) == 455,
              str(schema.reset_skill_points(63, 300)))

        snap = reset_mod.skill_snapshot(view.values)
        check("账面总量取实际发放的 451", snap["total"] == 451, str(snap))
        check("账面差额为 0", snap["diff"] == 0, str(snap["diff"]))
        issues = validate.validate(view)
        check("自然升级存档不再误报技能点",
              not any(i.code == "W_POINTS_MISMATCH" for i in issues),
              str([(i.code, i.params) for i in issues if i.code.startswith("W_POINTS")]))

        # 技能重置后：属性归零、未分配点数变成 455，也必须是合法状态。
        reset_doc = storage.read_save(path)
        reset_view = modeview.ModeViewDoc(reset_doc, "sandbox")
        for attr in schema.POINT_ATTRIBUTES:
            reset_view.values[attr.key] = float(attr.default)
        reset_view.values["Skill Points"] = 455
        reset_snap = reset_mod.skill_snapshot(reset_view.values)
        reset_issues = validate.validate(reset_view)
        check("技能重置后的 455 点被接受",
              reset_snap["total"] == 455 and reset_snap["diff"] == 0, str(reset_snap))
        check("重置状态不报技能点错误",
              not any(i.code == "W_POINTS_MISMATCH" for i in reset_issues))

        # 人为改大未分配点数，仍应触发异常提示。
        bad = modeview.ModeViewDoc(storage.read_save(path), "sandbox")
        bad.values["Skill Points"] = 10
        bad_issues = validate.validate(bad)
        check("篡改后的点数仍会告警",
              any(i.code == "W_POINTS_MISMATCH" for i in bad_issues))


def test_sandbox_hardmode_key() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        path = _write_save(folder, "Demo", _sandbox_values())
        doc = storage.read_save(path)
        view = modeview.ModeViewDoc(doc, "sandbox")

        spec = schema.spec_for("Sandbox Hardmode Switch?_sandbox", doc.pets())
        check("沙盒硬核键有规格", spec is not None)
        check("类型为字符串", spec is not None and spec.kind == "str",
              spec.kind if spec else "")
        check("归入杂项", schema.classify("Sandbox Hardmode Switch?_sandbox") == "misc")
        issues = validate.validate(view)
        check("不再报未知键",
              not any(i.code == "W_UNKNOWN" and "Hardmode" in i.key for i in issues))


def test_ticket_ad_keys() -> None:
    """14.5.5 新增的广告票券行键。Steam 版 Gated=false 不会写入，
    但存档里出现时应当是可读字段，而不是未知键告警。"""
    for key in ("TicketAdsWatched", "TicketAdRowsBase", "TicketAdRowsGated"):
        spec = schema.spec_for(key)
        check(f"{key} 有规格", spec is not None)
        check(f"{key} 类型为 int", spec is not None and spec.kind == "int",
              spec.kind if spec else "")
        check(f"{key} 归入杂项", schema.classify(key) == "misc")
    doc = model.SaveDoc.from_dict({
        "charName": "Tester",
        "TicketAdsWatched": 12,
        "TicketAdRowsBase": 9,
        "TicketAdRowsGated": 0,
    })
    issues = validate.validate(doc)
    check("广告票券键不再未知",
          not any(i.code == "W_UNKNOWN" for i in issues),
          str([(i.code, i.key) for i in issues]))


def main() -> int:
    for title, fn in (("侧栏等级与模式", test_sidebar_level),
                      ("技能点双公式", test_skill_points),
                      ("沙盒硬核键", test_sandbox_hardmode_key),
                      ("广告票券键", test_ticket_ad_keys)):
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
