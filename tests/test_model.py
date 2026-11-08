"""模型与编解码的联合测试：槽位聚合、差异、撤销、成就/任务提取。

运行： .venv\\Scripts\\python.exe tests\\test_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bsjson  # noqa: E402
import model  # noqa: E402
import schema  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


BASE = {
    "charName": "Tester",
    "charGender": "Male",
    "Current Level": 10,
    "Current Experience": 0,
    "Skill Points": 5,
    "Purchased Skill Points": 0,
    "Max Health": 100.0,
    "Max Mana": 100.0,
    "Current Health": 100.0,
    "Inventory_name_0": "Stone",
    "Inventory_count_0": 5,
    "Inventory_data_0": 0,
    "Inventory_paint_0": 0,
    "Inventory_name_1": "",
    "Inventory_count_1": 0,
    "Inventory_data_1": 0,
    "Inventory_paint_1": 0,
    "Drako_name_0": "Bone",
    "Drako_count_0": 2,
    "Drako_data_0": 0,
    "Drako(Clone) Current Level": 3,
    "Drako(Clone) MaxHealth": 260.0,
    "DrakoUnlocked": 16,
    "Drako_Name": "小飞",
    "Quest: Tutorial": "#end",
    "Quest Complete: Tutorial": 1,
    "Achieve: First Dragon": 1,
    "Achieve: Dragon Slayer kill 48": 10,
    "Recipe: Arrow": 1,
}


def test_slots() -> None:
    doc = model.SaveDoc.from_dict(BASE)
    slots = doc.slots("Inventory")
    check("槽位聚合成 2 个", len(slots) == 2)
    check("槽位 0 有物品", slots[0].name == "Stone" and slots[0].count == 5)
    check("槽位 1 为空", slots[1].empty)
    check("数据字段读入", slots[0].data == 0 and slots[0].paint == 0)


def test_changes_and_undo() -> None:
    doc = model.SaveDoc.from_dict(BASE)
    check("初始纯净", doc.is_pristine())
    doc.push_undo("edit")
    doc.set("Max Health", 200.0)
    check("改值后不纯净", not doc.is_pristine())
    add, mod, rem = doc.change_counts()
    check("计数正确", (add, mod, rem) == (0, 1, 0), f"{add},{mod},{rem}")

    doc.push_undo("test")
    doc.delete("Quest: Tutorial")
    check("删除生效", "Quest: Tutorial" not in doc)
    add, mod, rem = doc.change_counts()
    check("删除计入差异", rem == 1)

    doc.undo()
    check("撤销恢复键", "Quest: Tutorial" in doc)
    doc.undo()
    check("撤销恢复值", doc.get("Max Health") == 100.0)
    check("回到纯净", doc.is_pristine())


def test_no_new_keys() -> None:
    doc = model.SaveDoc.from_dict(BASE)
    try:
        doc.set("Brand New Key", 1)
    except KeyError:
        check("不允许新增键", True)
    else:
        check("不允许新增键", False)


def test_serialize_roundtrip() -> None:
    doc = model.SaveDoc.from_dict(BASE)
    text = doc.serialize()
    back = model.SaveDoc.from_text(text)
    check("往返键序一致", back.order == doc.order)
    check("往返值一致", all(back.get(k) == doc.get(k) for k in doc.order))
    check("浮点保持浮点", isinstance(back.get("Max Health"), float))


def test_achieve_and_quests() -> None:
    doc = model.SaveDoc.from_dict(BASE)
    achievements = doc.achievements()
    titles = {a["title"]: a for a in achievements}
    check("成就标题去掉前缀", "Dragon Slayer" in titles, str(list(titles)))
    check("进度键归到同一标题", bool(titles["Dragon Slayer"]["progress"]))
    check("已领取标记", titles["First Dragon"]["claimed"] is True)
    quests = doc.quests()
    check("任务数量", len(quests) == 1)
    check("任务完成次数", quests[0]["times"] == 1)


def test_pets() -> None:
    doc = model.SaveDoc.from_dict(BASE)
    check("识别宠物", "Drako" in doc.pets())
    stats = doc.pet_stats()
    check("宠物属性聚合", stats["Drako"]["Current Level"] == 3)
    check("宠物背包分类", doc.category("Drako_name_0") == "pet_bag")
    check("宠物属性分类", doc.category("Drako(Clone) MaxHealth") == "pet_stat")
    check("宠物档案分类", doc.category("Drako_Name") == "pet_meta")


def test_float_text() -> None:
    check("浮点显示保持游戏写法", model.display_value(0.3) == ".3")
    check("整数不受影响", model.display_value(7) == "7")
    check("字符串原样", model.display_value("石") == "石")


def test_coerce() -> None:
    check("整数键接收 400.0", model.coerce_input("400.0", "int") == 400)
    check("浮点键接收 400", isinstance(model.coerce_input("400", "float"), float))
    try:
        model.coerce_input("abc", "int")
    except model.CoerceError:
        check("非法输入报错", True)
    else:
        check("非法输入报错", False)


def main() -> int:
    groups = [
        ("槽位聚合", test_slots),
        ("差异与撤销", test_changes_and_undo),
        ("禁止新增键", test_no_new_keys),
        ("序列化往返", test_serialize_roundtrip),
        ("成就与任务", test_achieve_and_quests),
        ("宠物", test_pets),
        ("显示与输入", lambda: (test_float_text(), test_coerce())),
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
