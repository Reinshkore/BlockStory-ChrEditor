"""物品结构操作、任务快捷编辑与游戏目录解析的回归测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gamedata  # noqa: E402
import itemops  # noqa: E402
import model  # noqa: E402
import questops  # noqa: E402
import schema  # noqa: E402
from views import items as items_view  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + (f" {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def _doc() -> model.SaveDoc:
    return model.SaveDoc.from_dict({
        "Inventory_name_0": "Stone", "Inventory_count_0": 5,
        "Inventory_data_0": 2, "Inventory_paint_0": 7,
        "Inventory_name_1": "Dirt", "Inventory_count_1": 9,
        "Inventory_data_1": 0, "Inventory_paint_1": 0,
        "Drako_name_0": "Bone", "Drako_count_0": 2,
        "Drako_data_0": 0, "Drako_paint_0": 0,
        "Quest: Tutorial": "#end",
        "Quest: A": "old",
        "Quest: A kill 2": 4,
        "Quest: A Player consume Food": 1,
        "Quest: A placed 12 0": 3,
        "Quest Complete: Daily": 4,
        "Daily: Daily": "2026-01-01",
    })


def test_items() -> None:
    from types import SimpleNamespace
    ss = SimpleNamespace(slot_target=("Inventory", 0), item_move_source=("Inventory", 1))
    items_view.close_transients(ss)
    check("导航清理物品弹窗与移动状态", ss.slot_target is None and ss.item_move_source is None)

    doc = _doc()
    check("交换保留四元组", itemops.swap_slots(doc, "Inventory", 0, 1))
    check("来源变成 Dirt", doc.get("Inventory_name_1") == "Stone"
          and doc.get("Inventory_data_1") == 2 and doc.get("Inventory_paint_1") == 7)
    check("目标变成 Stone", doc.get("Inventory_name_0") == "Dirt"
          and doc.get("Inventory_count_0") == 9)
    doc.undo()
    check("交换可完整撤销", doc.get("Inventory_name_0") == "Stone"
          and doc.get("Inventory_data_0") == 2 and doc.is_pristine())

    itemops.swap_slots(doc, "Inventory", 0, 3)
    check("可写入已知容器的空格", doc.get("Inventory_name_3") == "Stone"
          and doc.get("Inventory_count_3") == 5)
    check("原位被完整清空", doc.get("Inventory_name_0") == ""
          and doc.get("Inventory_data_0") == 0 and doc.get("Inventory_paint_0") == 0)
    check("补齐键进入顺序表", all(f"Inventory_{f}_3" in doc.order
                                  for f in itemops.FIELDS))
    try:
        itemops.swap_slots(doc, "Missing", 0, 1)
    except KeyError:
        check("不能创建未知容器", True)
    else:
        check("不能创建未知容器", False)

    doc = _doc()
    doc.set("Drako_name_0", "Bone")
    doc.set("Drako_count_0", 2)
    itemops.swap_slots_between(doc, "Inventory", 0, "Drako", 0)
    check("跨容器交换", doc.get("Inventory_name_0") == "Bone"
          and doc.get("Drako_name_0") == "Stone")

    doc = _doc()
    itemops.apply_order(doc, "Inventory", [1, 0])
    check("拖拽顺序映射到槽位", doc.get("Inventory_name_0") == "Dirt"
          and doc.get("Inventory_name_1") == "Stone")
    doc.undo()
    itemops.sort_by_name(doc, "Inventory", 2, lambda slot: slot.name)
    check("按名称排序", doc.get("Inventory_name_0") == "Dirt"
          and doc.get("Inventory_name_1") == "Stone")

    doc = _doc()
    doc.set("Inventory_name_1", "")
    doc.set("Inventory_count_1", 0)
    itemops.set_slot(doc, "Inventory", 7, name="Hidden", count=1, data=0, paint=0)
    itemops.apply_order(doc, "Inventory", [1, 0])
    check("部分排列不碰隐藏区", doc.get("Inventory_name_7") == "Hidden")
    try:
        itemops.apply_order(doc, "Inventory", [1, 3])
    except ValueError:
        check("稀疏拖拽结果被拒绝", True)
    else:
        check("稀疏拖拽结果被拒绝", False)


def _catalog() -> gamedata.Catalog:
    quests = {
        "Tutorial": gamedata.QuestDef("Tutorial", "Wizard", False, steps=("#start", "begin"),
                                       recipes=("Arrow",)),
        "A": gamedata.QuestDef("A", "Wizard", False, deps=("Tutorial",),
                               steps=("#start", "hunt"), recipes=("Shared",)),
        "B": gamedata.QuestDef("B", "Wizard", False, deps=("A",), steps=("#start",)),
        "The Grand Finale": gamedata.QuestDef("The Grand Finale", "Wizard", False,
                                               deps=("B",), steps=("#start", "final")),
        "Side": gamedata.QuestDef("Side", "Wizard", False, deps=("A",),
                                   steps=("#start", "task"), recipes=("Shared",)),
        "Free": gamedata.QuestDef("Free", "Wizard", False, steps=("#start",)),
        "Daily": gamedata.QuestDef("Daily", "Wizard", True, daily_tiers=(5, 6), deps=("A",),
                                    steps=("#start", "daily")),
    }
    return gamedata.Catalog(quests=quests, quest_recipes={
        title: quest.recipes for title, quest in quests.items() if quest.recipes})


def test_quests() -> None:
    doc = _doc()
    catalog = _catalog()
    chain = questops.mainline(catalog)
    check("主线从终章回推", [q.title for q in chain] == ["Tutorial", "A", "B", "The Grand Finale"])
    plan = questops.build_mainline_plan(doc, chain, 2, "hunt")
    check("阶段之前的任务完成", plan.values["Quest: A"] == "#end")
    check("当前任务到指定步骤", plan.values["Quest: B"] == "#start")
    check("未来任务未开始", plan.values["Quest: The Grand Finale"] == "#start")
    check("旧进度被清理", "Quest: A kill 2" not in plan.values)
    questops.apply_plan(doc, plan)
    check("任务计划可撤销", doc.undo() is not None and doc.get("Quest: A") == "old")
    questops.apply_plan(doc, questops.build_side_plan(doc, catalog.quests["B"], "complete"))
    check("识别非连续主线", questops.current_mainline_stage(doc, chain) == 1
          and questops.completed_after_gap(doc, chain) == ["B"])

    side = catalog.quests["Side"]
    plan = questops.build_side_plan(doc, side, "complete")
    check("支线完成", plan.values["Quest: Side"] == "#end")
    questops.apply_plan(doc, plan)
    plan = questops.build_side_plan(doc, side, "reset")
    check("支线重置", plan.values["Quest: Side"] == "#start")

    daily = catalog.quests["Daily"]
    plan = questops.build_daily_plan(doc, daily, 6)
    check("日常次数修改且保持步骤", plan.values["Quest Complete: Daily"] == 6
          and "Quest: Daily" not in plan.values)
    check("日常滑块在当前值上方留余量", questops.daily_slider_upper(40, (5,)) == 45)
    plan = questops.build_daily_plan(doc, daily, 0, "reset")
    check("日常重置清除日期", "Daily: Daily" not in plan.values
          and plan.values["Quest: Daily"] == "#start")


def test_sync() -> None:
    catalog = _catalog()
    chain = questops.mainline(catalog)
    doc = _doc()
    doc.values.update({
        "Quest: Tutorial": "#end", "Quest: A": "#end", "Quest: Side": "#end",
        "Quest: Free": "#end", "Quest: Daily": "#end", "Quest Complete: Daily": 8,
        "Daily: Daily": "2026-01-01", "Recipe: Arrow": 1, "Recipe: Shared": 1,
        "Recipe: Unrelated": 1,
    })
    doc.order = list(doc.values)

    rollback = questops.build_mainline_plan(
        doc, chain, 1, "#start", catalog=catalog, sync_recipes=True, sync_side=False)
    check("主线回退保留已完成主线配方", rollback.values.get("Recipe: Arrow") == 1)
    check("其他已完成支线仍提供同名配方", rollback.values.get("Recipe: Shared") == 1)
    check("配方同步不碰无关配方", rollback.values.get("Recipe: Unrelated") == 1)
    check("关闭支线联动时不改支线", rollback.values.get("Quest: Side") == "#end")

    linked = questops.build_mainline_plan(
        doc, chain, 1, "#start", catalog=catalog, sync_recipes=True, sync_side=True)
    check("回退重置未解锁支线", linked.values.get("Quest: Side") == "#start")
    check("回退重置未解锁日常及次数日期", linked.values.get("Quest: Daily") == "#start"
          and "Quest Complete: Daily" not in linked.values and "Daily: Daily" not in linked.values)
    check("无依赖支线保持原状", linked.values.get("Quest: Free") == "#end")
    check("支线来源失效后移除共享配方", "Recipe: Shared" not in linked.values)
    check("联动指标可预览", linked.metrics["recipes_changed"] >= 1
          and set(linked.metrics["side_reset"]) == {"Side", "Daily"})

    advance = questops.build_mainline_plan(
        doc, chain, 2, "#start", catalog=catalog, sync_recipes=True)
    check("主线前进补齐任务配方", advance.values.get("Recipe: Shared") == 1)


def test_formats() -> None:
    table = gamedata.parse_po('msgid ""\nmsgstr ""\n"Language: en\\n"\n'
                              'msgid "Replicon"\nmsgstr "Mutagen"\n')
    check("PO 表解析", table.get("Replicon") == "Mutagen")
    check("语言识别", gamedata._language(table) == "en")
    hits = gamedata.Catalog().search_mobs("1", "en")
    check("生物数字检索过滤 data=0", all(i != 0 for i, _ in hits)
          and any(i == 1 for i, _ in hits))
    quest = gamedata._parse_quest(
        '<quest npc="Wizard" title="Hunt"><killstep id="hunt">'
        '<kill enemy="SmallWorm" count="3"/></killstep>'
        '<consumestep id="feed"><consume target="Player" item="Food"/></consumestep>'
        '<step id="nested"><option><kill enemy="Dragon"/></option>'
        '<reward recipe="Arrow"/><reward recipe="Arrow"/><reward recipe="Bow"/></step></quest>', 0)
    keys = [x.key for x in quest.targets]
    check("任务配方奖励去重", quest.recipes == ("Arrow", "Bow"), str(quest.recipes))
    check("击杀键保存数值生物 ID", "Quest: Hunt hunt kill 2" in keys, str(keys))
    check("喂食键顺序正确", "Quest: Hunt feed Player consume Food" in keys, str(keys))
    check("读取 option 嵌套击杀", "Quest: Hunt nested kill 48" in keys, str(keys))
    for key in ("Hunt hunt kill 2", "Hunt feed Player consume Food", "Build x placed 12 0",
                "Hunt feed Baby Ashkore consume Food"):
        check(f"识别进度键 {key}", bool(schema.QUEST_PROG_RE.match(key)))
    check("主线键不误判", not schema.QUEST_PROG_RE.match("A"))


def test_installed_catalog() -> None:
    if not (gamedata.game_data_dir() / "level2").is_file():
        print("  skip  本机没有游戏资源")
        return
    catalog = gamedata.load_catalog()
    check("当前版本目录可读", not catalog.error, catalog.error)
    check("版本来自 Version 资产", bool(catalog.version), catalog.version)
    check("物品来自真实 InvDatabase", len(catalog.items) > 600)
    check("刷怪箱标记来自物品 options", catalog.is_spawner("Antique Spawner"))
    check("生物枚举完整映射", len(catalog.mobs) == len(gamedata.MOB_TYPES))
    check("当前主线 19 环", len(questops.mainline(catalog)) == 19)
    check("当前与旧任务配方来源已提取", len(catalog.quest_recipes) > 50
          and catalog.quests["The Grand Finale"].recipes == ("Sunshard Wizard",))
    check("俄语物品名称来自游戏 PO", bool(catalog.items["Stone"].ru))


def main() -> int:
    for title, fn in (("物品操作", test_items), ("任务操作", test_quests),
                      ("任务联动", test_sync), ("格式与键序", test_formats),
                      ("本机游戏目录", test_installed_catalog)):
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
