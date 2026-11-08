"""整理与重置的测试。

重点不是"跑通了"，而是：整理不改值、重置结果与游戏公式一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bsjson  # noqa: E402
import gamedata  # noqa: E402
import model  # noqa: E402
import modeops  # noqa: E402
import reset  # noqa: E402
import schema  # noqa: E402
import tidy  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


def base(**extra):
    data = {
        "charName": "Tester",
        "charGender": "Male",
        "Current Level": 69,
        "Current Experience": 7282,
        "Skill Points": 1,
        "Purchased Skill Points": 100,
        "Max Health": 400.0,
        "Max Mana": 100.0,
        "Max Breath": 30.0,
        "Max Sword Damage": 200.0,
        "Max Dig Speed": 1.0,
        "Current Health": 850.0,
        "Current Mana": 100.0,
        "Current Breath": 30.0,
        "InventoryUnlocked": 64,
        "Inventory_name_0": "Stone",
        "Inventory_count_0": 5,
        "Inventory_data_0": 0,
        "Inventory_paint_0": 0,
        "Inventory_name_1": "",
        "Inventory_count_1": 0,
        "Inventory_data_1": 0,
        "Inventory_paint_1": 0,
        "Drako(Clone) Current Level": 20,
        "Drako(Clone) MaxHealth": 600.0,
        "Drako(Clone) Attack": 125.0,
        "DrakoUnlocked": 16,
        "Drako_Name": "小飞",
        "Drako_name_0": "Bone",
        "Drako_count_0": 2,
        "Quest: Tutorial": "#end",
        "Quest Complete: Tutorial": 1,
        "Daily: Help Us": "2026-04-19T00:00:00.0000000+08:00",
        "Achieve: First Dragon": 1,
        "Recipe: Arrow": 1,
    }
    data.update(extra)
    return data


# --------------------------------------------------------------------------- #
# 整理
# --------------------------------------------------------------------------- #

def test_normalize() -> None:
    doc = model.SaveDoc.from_dict(base(**{"Max Health": 400}))  # 错误的整数
    plan = tidy.build_plan(doc, tidy.TidyOptions(normalize=True, reorder=False,
                                                 drop_empty_slots=False))
    check("识别出类型问题", plan.fixes == 1, str(plan.fixes))
    check("规范化后是浮点", isinstance(plan.new_values["Max Health"], float))
    check("数值不变", float(plan.new_values["Max Health"]) == 400.0)


def test_drop_empty() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = tidy.build_plan(doc, tidy.TidyOptions(normalize=False, reorder=False,
                                                 drop_empty_slots=True))
    check("删掉空槽四元组", plan.removed == 4, str(plan.removed))
    check("非空槽保留", "Inventory_name_0" in plan.new_values)
    check("空槽键清空", "Inventory_name_1" not in plan.new_values)


def test_drop_empty_keeps_nonzero_data() -> None:
    doc = model.SaveDoc.from_dict(base(**{"Inventory_data_1": 7}))
    plan = tidy.build_plan(doc, tidy.TidyOptions(normalize=False, reorder=False,
                                                 drop_empty_slots=True))
    check("data 非零的空槽不删", "Inventory_data_1" in plan.new_values)


def test_compact() -> None:
    doc = model.SaveDoc.from_dict(base(**{
        "Inventory_name_5": "Iron", "Inventory_count_5": 3,
        "Inventory_name_9": "Gold", "Inventory_count_9": 1,
    }))
    plan = tidy.build_plan(doc, tidy.TidyOptions(normalize=False, reorder=False,
                                                 drop_empty_slots=True,
                                                 compact_indices=True))
    values = plan.new_values
    names = {k: v for k, v in values.items() if k.startswith("Inventory_name_")}
    check("压缩后索引连续", set(names) == {"Inventory_name_0", "Inventory_name_1", "Inventory_name_2"},
          str(sorted(names)))
    check("物品没丢", sorted(v for v in names.values() if v) == ["Gold", "Iron", "Stone"])
    check("装备栏不压缩", all(not k.startswith("Equipment_") for k in values))


def test_reorder() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = tidy.build_plan(doc, tidy.TidyOptions(normalize=False, reorder=True,
                                                 drop_empty_slots=False))
    check("首项是身份类", plan.new_order[0] in ("charName", "charGender"), plan.new_order[0])
    doc2 = model.SaveDoc.from_dict(base())
    tidy.apply_plan(doc2, plan)
    check("顺序与计划一致", doc2.order == plan.new_order)
    check("键集合没变", set(doc2.values) == set(doc.values))


def test_apply_keeps_parseable() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = tidy.build_plan(doc, tidy.TidyOptions())
    tidy.apply_plan(doc, plan)
    text = doc.serialize()
    back = bsjson.loads(text)
    check("整理后仍可解析", len(back.entries) == len(doc.values))
    check("整理后可撤销", doc.undo() is not None)


# --------------------------------------------------------------------------- #
# 重置
# --------------------------------------------------------------------------- #

def test_skill_formula() -> None:
    check("1 级总量 6", schema.total_skill_points(1, 0) == 6)
    check("10 级总量 15", schema.total_skill_points(10, 0) == 15)
    check("29 级总量 53", schema.total_skill_points(29, 0) == 53)
    check("69 级总量 173", schema.total_skill_points(69, 0) == 173,
          str(schema.total_skill_points(69, 0)))
    check("69 级 + 100 已购 = 273", schema.total_skill_points(69, 100) == 273)
    check("199 级含 +20", schema.total_skill_points(199, 0) ==
          schema.total_skill_points(198, 0) + 20)


def test_reset_level() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = reset.build_plan(doc, reset.OP_LEVEL)
    check("等级回 1", plan.values["Current Level"] == 1)
    check("经验回 0", plan.values["Current Experience"] == 0)
    check("属性不变", plan.values["Max Health"] == 400.0)
    # 1 级总量 = 6 + 100 已购 = 106；属性已投入 30(生命) + 200(剑) = 230
    check("属性投入 230", schema.invested_points(doc.values)[0] == 230,
          str(schema.invested_points(doc.values)[0]))
    check("默认把负数夹到 0", plan.values["Skill Points"] == 0,
          str(plan.values["Skill Points"]))
    check("提示未分配为负", any(n[0] == "rs.note.negativeUnspent" for n in plan.notes))
    note = next(n for n in plan.notes if n[0] == "rs.note.negativeUnspent")
    check("算出 -124", note[1]["raw"] == -124, str(note[1]))

    raw_plan = reset.build_plan(doc, reset.OP_LEVEL, skill_mode=reset.SKILL_RAW)
    check("raw 模式写入负数", raw_plan.values["Skill Points"] == -124,
          str(raw_plan.values["Skill Points"]))

    # 没有属性投入时，结果就是满额
    plain = model.SaveDoc.from_dict(base(**{"Max Health": 100.0, "Max Sword Damage": 0.0}))
    plain_plan = reset.build_plan(plain, reset.OP_LEVEL)
    check("无投入时 = 6 + 100", plain_plan.values["Skill Points"] == 106,
          str(plain_plan.values["Skill Points"]))


def test_reset_attributes() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = reset.build_plan(doc, reset.OP_ATTRS)
    check("生命上限回 100", plan.values["Max Health"] == 100.0)
    check("剑伤回 0", plan.values["Max Sword Damage"] == 0.0)
    check("挖掘回 1", plan.values["Max Dig Speed"] == 1.0)
    check("技能点退回总量", plan.values["Skill Points"] == 273,
          str(plan.values["Skill Points"]))
    check("当前生命被夹到上限", plan.values["Current Health"] == 100.0,
          str(plan.values["Current Health"]))
    check("有夹紧提示", any(n[0] == "rs.note.clamped" for n in plan.notes))


def test_reset_quests() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = reset.build_plan(doc, reset.OP_QUESTS)
    check("Quest 键被删", not any(k.startswith("Quest") for k in plan.values))
    check("Daily 键被删", not any(k.startswith("Daily") for k in plan.values))
    check("其它键不动", plan.values["Max Health"] == 400.0)


def test_reset_quest_recipes() -> None:
    doc = model.SaveDoc.from_dict(base(**{"Recipe: Other": 1}))
    catalog = gamedata.Catalog(quest_recipes={"Tutorial": ("Arrow",)})
    plan = reset.build_plan(doc, reset.OP_QUESTS, sync_quest_recipes=True, catalog=catalog)
    check("任务重置可同步删除任务配方", "Recipe: Arrow" not in plan.values)
    check("任务配方以外的配方保留", plan.values.get("Recipe: Other") == 1)
    check("任务配方删除有说明", any(n[0] == "rs.note.questRecipes" for n in plan.notes))
    plain = reset.build_plan(doc, reset.OP_QUESTS, catalog=catalog)
    check("默认任务重置保留配方", plain.values.get("Recipe: Arrow") == 1)


def test_reset_pets() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = reset.build_plan(doc, reset.OP_PETS)
    check("宠物属性键被删", not any("(Clone)" in k for k in plan.values))
    check("宠物名保留", plan.values.get("Drako_Name") == "小飞")
    check("宠物背包保留", plan.values.get("Drako_name_0") == "Bone")
    check("解锁格保留", plan.values.get("DrakoUnlocked") == 16)


def test_reset_full() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = reset.build_plan(doc, reset.OP_FULL)
    values = plan.values
    check("等级回 1", values["Current Level"] == 1)
    check("属性回默认", values["Max Health"] == 100.0)
    check("技能点 = 106", values["Skill Points"] == 106, str(values["Skill Points"]))
    check("任务被清", not any(k.startswith("Quest") for k in values))
    check("成就被清", not any(k.startswith("Achieve") for k in values))
    check("配方被清", not any(k.startswith("Recipe") for k in values))
    check("宠物属性和被清", not any("(Clone)" in k for k in values))
    check("背包保留", values.get("Inventory_name_0") == "Stone")
    check("已购点数保留", values.get("Purchased Skill Points") == 100)


def test_mode_data() -> None:
    doc = model.SaveDoc.from_dict(base(encrypted=False))
    last = modeops.build_clear_plan(doc, "story")
    check("阻止清除最后有数据的模式", last.error == "md.lastMode" and not last.changes)

    copied = modeops.build_copy_plan(doc, "story", "survival")
    check("复制剧情到空生存模式", not copied.error
          and copied.values.get("Current Level_survival") == 69
          and copied.values.get("Inventory_name_0_survival") == "Stone")
    check("复制不复制身份与共享键", "charName_survival" not in copied.values
          and "Purchased Skill Points_survival" not in copied.values
          and "encrypted_survival" not in copied.values)
    check("复制保留原模式", copied.values.get("Current Level") == 69)
    check("模式后缀继承原键类型", schema.kind_for("Gontar(Clone) Current Level_survival", {"Gontar"}) == "int"
          and schema.kind_for("Inventory_count_0_survival") == "int"
          and schema.kind_for("Quest: Tutorial_survival") == "str")
    check("拒绝复制到非空模式", modeops.build_copy_plan(doc, "story", "story").error == "md.sameMode")
    modeops.apply_plan(doc, copied)
    check("模式复制可撤销", doc.undo() is not None
          and "Current Level_survival" not in doc.values)

    modeops.apply_plan(doc, copied)
    cleared = modeops.build_clear_plan(doc, "story")
    check("存在其他模式时允许清除剧情", not cleared.error)
    check("清除剧情保留角色身份", cleared.values.get("charName") == "Tester"
          and cleared.values.get("charGender") == "Male")
    check("清除剧情保留共享购买点与加密标记", cleared.values.get("Purchased Skill Points") == 100
          and cleared.values.get("encrypted") is False)
    check("清除剧情保留生存副本", cleared.values.get("Current Level_survival") == 69
          and "Current Level" not in cleared.values)
    occupied = modeops.build_copy_plan(doc, "survival", "story")
    check("目标有数据时拒绝覆盖", occupied.error == "md.targetNotEmpty" and not occupied.changes)


def test_apply_plan() -> None:
    doc = model.SaveDoc.from_dict(base())
    plan = reset.build_plan(doc, reset.OP_ATTRS)
    reset.apply_plan(doc, plan)
    check("应用后值生效", doc.get("Max Health") == 100.0)
    check("应用后可撤销", doc.undo() == "reset:attributes")
    check("撤销后还原", doc.get("Max Health") == 400.0)


def main() -> int:
    groups = [
        ("整理·类型规范化", test_normalize),
        ("整理·删空槽", test_drop_empty),
        ("整理·非零 data 不删", test_drop_empty_keeps_nonzero_data),
        ("整理·压缩索引", test_compact),
        ("整理·重排", test_reorder),
        ("整理·可解析性与撤销", test_apply_keeps_parseable),
        ("重置·技能点公式", test_skill_formula),
        ("重置·等级", test_reset_level),
        ("重置·属性", test_reset_attributes),
        ("重置·任务", test_reset_quests),
        ("重置·任务配方联动", test_reset_quest_recipes),
        ("重置·宠物", test_reset_pets),
        ("重置·彻底", test_reset_full),
        ("模式数据复制与清除", test_mode_data),
        ("重置·应用与撤销", test_apply_plan),
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
