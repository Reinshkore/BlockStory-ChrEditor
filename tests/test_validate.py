"""校验规则逐条测试。

每条 E/W 规则各造一个最小样本，确认码与等级都对得上。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model  # noqa: E402
import validate  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


def codes(data: dict) -> dict[str, str]:
    doc = model.SaveDoc.from_dict(data)
    return {i.code: i.level for i in validate.validate(doc)}


def issues_of(data: dict, code: str) -> list:
    doc = model.SaveDoc.from_dict(data)
    return [i for i in validate.validate(doc) if i.code == code]


GOOD = {
    "charName": "Tester",
    "charGender": "Male",
    "Current Level": 10,
    "Current Experience": 0,
    "Skill Points": 65,
    "Purchased Skill Points": 0,
    "Max Health": 100.0,
    "Max Mana": 100.0,
    "Max Breath": 30.0,
    "Current Health": 100.0,
    "Current Mana": 100.0,
    "Current Breath": 30.0,
}


def test_clean() -> None:
    found = codes(GOOD)
    errors = [c for c, lv in found.items() if lv == "error"]
    check("干净样本没有错误", not errors, str(found))


def test_type_rules() -> None:
    data = dict(GOOD, **{"Max Health": 100})          # 浮点键写整数
    check("浮点键收到整数 → E_TYPE", codes(data).get("E_TYPE") == "error")

    data = dict(GOOD, **{"Current Level": 10.0})      # 整数键写浮点
    check("整数键收到浮点 → E_TYPE", codes(data).get("E_TYPE") == "error")

    data = dict(GOOD, **{"charName": 123})            # 文本键写数字
    check("文本键收到数字 → E_TYPE", codes(data).get("E_TYPE") == "error")

    data = dict(GOOD, **{"Max Health": float("inf")})
    check("无穷大 → E_FLOAT_SPECIAL", codes(data).get("E_FLOAT_SPECIAL") == "error")


def test_duplicates() -> None:
    doc = model.SaveDoc.from_text('{\n"a":1,\n"a":2\n}')
    found = validate.validate(doc)
    check("重复键 → E_DUP", any(i.code == "E_DUP" and i.level == "error" for i in found))


def test_ranges() -> None:
    check("等级越界 → W_LEVEL_RANGE",
          codes(dict(GOOD, **{"Current Level": 500})).get("W_LEVEL_RANGE") == "warn")
    check("经验越界 → W_EXP_RANGE",
          codes(dict(GOOD, **{"Current Experience": 999999})).get("W_EXP_RANGE") == "warn")
    check("属性为负 → W_ATTR_NEG",
          codes(dict(GOOD, **{"Max Health": -5.0})).get("W_ATTR_NEG") == "warn")
    check("当前值超上限 → W_CUR_GT_MAX",
          codes(dict(GOOD, **{"Current Health": 200.0})).get("W_CUR_GT_MAX") == "warn")


def test_points() -> None:
    # 10 级 + 0 已购 → 总量 5 + 10 = 15；未分配 65 超过总量
    data = dict(GOOD, **{"Skill Points": 65})
    check("未分配超过总量 → W_POINTS_OVER", "W_POINTS_OVER" in codes(data))

    # 属性投入 0，但账面已花 15-5=10 → 不闭合
    hit = issues_of(dict(GOOD, **{"Skill Points": 5}), "W_POINTS_MISMATCH")
    check("投入与账面不闭合 → W_POINTS_MISMATCH", bool(hit))
    if hit:
        check("差额方向正确", hit[0].params["diff"] == -10, str(hit[0].params))


def test_slots() -> None:
    base = dict(GOOD)
    base.update({
        "Inventory_name_0": "Stone", "Inventory_count_0": 5,
        "Inventory_data_0": 0, "Inventory_paint_0": 0,
    })
    check("正常槽位无告警", "W_SLOT_STATE" not in codes(base))

    data = dict(base, **{"Inventory_count_0": 0})
    check("有名字无数量 → W_SLOT_STATE", codes(data).get("W_SLOT_STATE") == "warn")

    data = dict(base)
    data.pop("Inventory_count_0")
    check("缺 count 键 → W_ORPHAN_SLOT", codes(data).get("W_ORPHAN_SLOT") == "warn")

    data = dict(base, **{"Inventory_data_0": 70000})
    check("data 越界 → W_USHORT", codes(data).get("W_USHORT") == "warn")

    data = dict(base, **{"Inventory_name_70": "X", "Inventory_count_70": 1})
    check("索引越界 → W_SLOT_INDEX", codes(data).get("W_SLOT_INDEX") == "warn")

    data = dict(base, **{"RightHand": 40})
    check("手部槽位越界 → W_HAND", codes(data).get("W_HAND") == "warn")


def test_identity_and_dates() -> None:
    check("空角色名 → W_NAME_EMPTY",
          codes(dict(GOOD, **{"charName": ""})).get("W_NAME_EMPTY") == "warn")
    data = dict(GOOD, **{"Daily: Help Us": "not-a-date"})
    check("非法日期 → W_DATE", codes(data).get("W_DATE") == "warn")
    data = dict(GOOD, **{"Daily: Help Us": "2026-04-19T00:00:00.0000000+08:00"})
    check("合法日期不告警", "W_DATE" not in codes(data))


def test_unknown_and_info() -> None:
    check("未知键 → W_UNKNOWN", codes(dict(GOOD, **{"Mystery": 1})).get("W_UNKNOWN") == "warn")
    check("非 ASCII 键 → I_NONASCII",
          codes(dict(GOOD, **{"Achieve: 中文…": 1})).get("I_NONASCII") == "info")


def test_sorted_and_counted() -> None:
    doc = model.SaveDoc.from_dict(dict(GOOD, **{"Current Level": 500, "Max Health": 1}))
    found = validate.validate(doc)
    check("错误排在警告之前", [i.level for i in found][0] == "error" if found else True)
    counts = validate.counts(found)
    check("计数覆盖三级", set(counts) >= {"error", "warn", "info"})


def test_quest_catalog() -> None:
    import gamedata

    target = gamedata.QuestTarget("hunt", "kill", "SmallWorm", 3,
                                  "Quest: Hunt hunt kill 2")
    catalog = gamedata.Catalog(quests={
        "Hunt": gamedata.QuestDef("Hunt", "Wizard", False,
                                   steps=("#start", "hunt"), targets=(target,)),
    })
    doc = model.SaveDoc.from_dict({
        "Quest: Hunt": "missing-step",
        "Quest: Hunt elsewhere kill 2": 1,
        "Quest: Custom": "#start",
    })
    found = validate.validate(doc, catalog=catalog)
    levels = {i.code: i.level for i in found}
    check("未定义任务步骤 → W_QUEST_STEP", levels.get("W_QUEST_STEP") == "warn")
    check("计数指向未定义步骤 → I_PROGRESS_STEP", levels.get("I_PROGRESS_STEP") == "info")
    check("自定义/已移除任务仅提示", levels.get("I_QUEST_CUSTOM") == "info")


def test_messages_exist() -> None:
    """每个会抛出的校验码、每条重置提示，都必须有译文——否则界面会直接显示键名。"""
    import re
    from pathlib import Path as _P

    import i18n

    root = _P(__file__).resolve().parent.parent
    codes = set(re.findall(r'Issue\("([A-Z_]+)"',
                           (root / "validate.py").read_text(encoding="utf-8")))
    missing = sorted(c for c in codes if f"val.{c}" not in i18n.S)
    check("校验码都有文案", not missing, str(missing))

    notes = set(re.findall(r'"(rs\.note\.[a-zA-Z]+)"',
                           (root / "reset.py").read_text(encoding="utf-8")))
    missing = sorted(n for n in notes if n not in i18n.S)
    check("重置提示都有文案", not missing, str(missing))

    check("双语表没有缺项", not i18n.missing_keys(), str(i18n.missing_keys()))


def test_language_settings() -> None:
    import tempfile
    import i18n
    old = i18n.SETTINGS_FILE
    old_legacy = i18n.LEGACY_SETTINGS_FILE
    try:
        with tempfile.TemporaryDirectory() as folder:
            # 保持测试不依赖 Streamlit 运行时，也不碰真实虚拟环境配置。
            from pathlib import Path
            i18n.SETTINGS_FILE = Path(folder) / "settings.json"
            i18n.LEGACY_SETTINGS_FILE = Path(folder) / "legacy.json"
            check("没有配置时回退英文", i18n.load_saved_language() == "en")
            i18n.save_language("ru")
            check("俄语偏好可持久读取", i18n.load_saved_language() == "ru")
            i18n.SETTINGS_FILE.write_text('{"lang":"invalid"}', encoding="utf-8")
            check("非法语言配置安全回退", i18n.load_saved_language() == "en")
    finally:
        i18n.SETTINGS_FILE = old
        i18n.LEGACY_SETTINGS_FILE = old_legacy


def main() -> int:
    groups = [
        ("干净样本", test_clean),
        ("类型规则", test_type_rules),
        ("重复键", test_duplicates),
        ("取值范围", test_ranges),
        ("技能点账面", test_points),
        ("槽位", test_slots),
        ("身份与日期", test_identity_and_dates),
        ("未知键", test_unknown_and_info),
        ("排序与计数", test_sorted_and_counted),
        ("任务目录一致性", test_quest_catalog),
        ("文案齐备", test_messages_exist),
        ("语言偏好保存", test_language_settings),
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
