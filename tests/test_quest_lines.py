"""任务线（当前 / 旧）与支线步骤编辑的回归测试。

不依赖本机是否安装游戏：目录部分用合成 QuestDef，键级行为用合成存档。
真实目录相关的断言在末尾，未安装游戏时自动跳过。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gamedata  # noqa: E402
import model  # noqa: E402
import questops  # noqa: E402
import reset as reset_mod  # noqa: E402
import schema  # noqa: E402
import validate  # noqa: E402

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _failures.append(name)


def _doc(**extra) -> model.SaveDoc:
    base = {
        "charName": "Tester",
        "Questline": 1,
        "Old Quest: Dancing Lessons": "mages",
        "Old Quest: Dancing Lessons mages kill 9": 12,
        "Old Quest: Dancing Lessons II": "#start",
        "Old Quest: Dancing Lessons II slashers kill 7": 5,
        "Old Quest: Ted the Viking": "#end",
        "Old Quest: Wimpy Kid": "#start",
        "Old Recipe: Boat": 1,
        "Recipe: Arrow": 1,
    }
    base.update(extra)
    return model.SaveDoc.from_dict(base)


def _catalog() -> gamedata.Catalog:
    defs = {
        "Dancing Lessons": gamedata.QuestDef(
            "Dancing Lessons", "SkeletonNormal", False, steps=("#start", "mages"),
            targets=(gamedata.QuestTarget("mages", "kill", "SkeletonMage", 20,
                                          "Old Quest: Dancing Lessons mages kill 9"),),
            line="old", source_order=1),
        "Dancing Lessons II": gamedata.QuestDef(
            "Dancing Lessons II", "SkeletonNormal", False, deps=("Dancing Lessons",),
            steps=("#start", "slashers"), line="old", source_order=2),
        "Dancing Lessons III": gamedata.QuestDef(
            "Dancing Lessons III", "SkeletonNormal", False, deps=("Dancing Lessons II",),
            steps=("#start", "knights"), line="old", source_order=3),
        "Ted the Viking": gamedata.QuestDef(
            "Ted the Viking", "Viking", False, steps=("#start", "wood"),
            line="old", source_order=4),
        "Wimpy Kid": gamedata.QuestDef(
            "Wimpy Kid", "Viking", False, deps=("Ted the Viking",), steps=("#start", "ores"),
            line="old", source_order=5),
        "Store": gamedata.QuestDef("Store", "ShadowHunter", False, steps=("#start",),
                                   line="old", shop=True, source_order=6),
        "Tutorial": gamedata.QuestDef("Tutorial", "Wizard", False, steps=("#start", "begin")),
        "The Grand Finale": gamedata.QuestDef("The Grand Finale", "Wizard", False,
                                              deps=("Tutorial",), steps=("#start", "finale")),
    }
    return gamedata.Catalog(quests={
        "Tutorial": defs["Tutorial"], "The Grand Finale": defs["The Grand Finale"]},
        old_quests={k: v for k, v in defs.items() if v.line == "old"})


def test_schema() -> None:
    check("Questline 常量", schema.QUEST_LINE_KEY == "Questline")
    check("0 是当前线", schema.quest_line(0) == "current")
    check("1 是旧线", schema.quest_line(1) == "old")
    check("缺失按当前线", schema.quest_line(None) == "current")
    check("非法值按当前线", schema.quest_line(7) == "current")
    check("旧线前缀", schema.quest_prefix("old") == "Old ")
    check("当前线无前缀", schema.quest_prefix("current") == "")
    check("旧线任务键", schema.quest_key("old", "quest", "A") == "Old Quest: A")
    check("旧线完成键", schema.quest_key("old", "complete", "A") == "Old Quest Complete: A")
    check("旧线配方键", schema.quest_key("old", "recipe", "Boat") == "Old Recipe: Boat")
    check("Old Recipe 归配方", schema.classify("Old Recipe: Boat") == "recipe")
    spec = schema.spec_for("Old Recipe: Boat")
    check("Old Recipe 类型为 int", spec is not None and spec.kind == "int" and spec.vmax == 1)
    check("Old Recipe 不再未知", spec is not None)


def test_catalog() -> None:
    catalog = _catalog()
    check("当前线目录独立", len(catalog.quests) == 2)
    check("旧线目录独立", len(catalog.old_quests) == 6)
    check("for_line 切换", catalog.for_line("old") is catalog.old_quests)
    check("商店任务标记", catalog.old_quests["Store"].shop is True)
    check("旧线任务带 line", catalog.old_quests["Wimpy Kid"].line == "old")
    check("当前线任务默认 line", catalog.quests["Tutorial"].line == "current")


def test_forest() -> None:
    forest = questops.old_forest(_catalog())
    check("森林排除商店任务", "Store" not in forest.defs)
    check("森林节点数", len(forest.defs) == 5)
    check("根节点", forest.roots == ["Dancing Lessons", "Ted the Viking"])
    check("子节点", forest.children["Dancing Lessons"] == ["Dancing Lessons II"])
    check("深度", forest.depth["Dancing Lessons III"] == 2)
    check("前置链", forest.path_to("Dancing Lessons III") ==
          ["Dancing Lessons", "Dancing Lessons II", "Dancing Lessons III"])
    check("子树", forest.subtree("Dancing Lessons II") ==
          ["Dancing Lessons II", "Dancing Lessons III"])


def test_quest_plan() -> None:
    catalog = _catalog()
    doc = _doc()
    quest = catalog.old_quests["Dancing Lessons"]
    plan = questops.build_quest_plan(doc, quest, "#end")
    check("只改旧线键", all(not c.key.startswith("Quest: ") for c in plan.changes))
    check("目标状态写入", plan.values["Old Quest: Dancing Lessons"] == "#end")
    check("清除自己的计数", "Old Quest: Dancing Lessons mages kill 9" not in plan.values)
    check("不清除同名后续任务", plan.values.get("Old Quest: Dancing Lessons II") == "#start")
    check("不清除后续任务计数",
          plan.values.get("Old Quest: Dancing Lessons II slashers kill 7") == 5)
    plan = questops.build_quest_plan(doc, quest, "mages")
    check("可回到进行中步骤", plan.values["Old Quest: Dancing Lessons"] == "mages")
    try:
        questops.build_quest_plan(doc, quest, "nope")
    except ValueError:
        check("拒绝非法步骤", True)
    else:
        check("拒绝非法步骤", False)
    check("旧线不出暗面结局",
          "#end_dark_side" not in questops.editable_steps(quest))
    check("当前线保留暗面结局",
          "#end_dark_side" in questops.editable_steps(catalog.quests["Tutorial"]))
    check("步骤目标只读摘要", questops.step_targets(quest, "mages") == [("SkeletonMage", 20)])


def test_chain_plan() -> None:
    catalog = _catalog()
    forest = questops.old_forest(catalog)
    doc = _doc()
    plan = questops.build_chain_plan(doc, forest, "Dancing Lessons III", "complete")
    check("完成到节点：3 个任务", plan.metrics["quests"] ==
          ["Dancing Lessons", "Dancing Lessons II", "Dancing Lessons III"])
    check("完成沿链写 #end",
          plan.values["Old Quest: Dancing Lessons III"] == "#end"
          and plan.values["Old Quest: Dancing Lessons II"] == "#end")
    check("完成不碰旁支", plan.values["Old Quest: Ted the Viking"] == "#end")
    plan = questops.build_chain_plan(doc, forest, "Dancing Lessons", "reset")
    check("重置覆盖子树", set(plan.metrics["quests"]) ==
          {"Dancing Lessons", "Dancing Lessons II", "Dancing Lessons III"})
    check("重置回 #start", plan.values["Old Quest: Dancing Lessons"] == "#start")
    check("重置清除计数", "Old Quest: Dancing Lessons mages kill 9" not in plan.values)
    check("重置不碰另一棵树", plan.values["Old Quest: Wimpy Kid"] == "#start")
    try:
        questops.build_chain_plan(doc, forest, "Store", "complete")
    except ValueError:
        check("拒绝未知节点", True)
    else:
        check("拒绝未知节点", False)


def test_questline_plan() -> None:
    doc = _doc()
    plan = questops.build_questline_plan(doc, "current")
    check("切换只改一个键", len(plan.changes) == 1)
    check("切换写入 0", plan.values["Questline"] == 0)
    plan = questops.build_questline_plan(model.SaveDoc.from_dict({"charName": "X"}), "old")
    check("切旧线写 1", plan.values["Questline"] == 1)
    plan = questops.build_questline_plan(model.SaveDoc.from_dict({"charName": "X"}), "current")
    check("缺键且切当前线不新增", plan.changes == [])
    check("识别当前线", questops.active_questline(model.SaveDoc.from_dict({"charName": "X"})) == "current")
    check("识别旧线", questops.active_questline(_doc()) == "old")
    counts = questops.line_key_counts(_doc())
    check("统计两线键数", counts == {"current": 1, "old": 7}, str(counts))
    stats = questops.line_stats(_doc(), "old")
    check("旧线统计", stats == {"total": 4, "done": 1, "active": 1, "start": 2}, str(stats))


def test_recipe_aliases() -> None:
    """14.5.5 把 Sunshard Wizard / Sunshard Paula 合并成 Sunshard。
    旧存档里的历史键在回退任务时必须一起撤销，否则游戏仍按别名解锁。"""
    check("别名映射", schema.recipe_names("Sunshard") ==
          ("Sunshard", "Sunshard Wizard", "Sunshard Paula"))
    check("反查别名", schema.recipe_names("Sunshard Paula")[0] == "Sunshard")

    tutorial = gamedata.QuestDef("Tutorial", "Wizard", False, steps=("#start", "begin"))
    finale = gamedata.QuestDef("The Grand Finale", "Wizard", False,
                               steps=("#start", "finale"), recipes=("Sunshard",))
    chain = [tutorial, finale]
    catalog = gamedata.Catalog(quests={"Tutorial": tutorial, "The Grand Finale": finale},
                               quest_recipes={"The Grand Finale": ("Sunshard",)})

    legacy = model.SaveDoc.from_dict({
        "charName": "Tester",
        "Quest: Tutorial": "#end",
        "Quest: The Grand Finale": "#end",
        "Recipe: Sunshard Wizard": 1,
        "Recipe: Sunshard Paula": 1,
        "Recipe: Arrow": 1,
    })
    plan = questops.build_mainline_plan(legacy, chain, 1, catalog=catalog, sync_recipes=True)
    check("回退删除历史配方键",
          "Recipe: Sunshard Wizard" not in plan.values
          and "Recipe: Sunshard Paula" not in plan.values, str(plan.values))
    check("回退不动无关配方", plan.values.get("Recipe: Arrow") == 1)

    done = model.SaveDoc.from_dict({
        "charName": "Tester",
        "Quest: Tutorial": "#end",
        "Quest: The Grand Finale": "#start",
    })
    plan = questops.build_mainline_plan(done, chain, 2, catalog=catalog, sync_recipes=True)
    check("完成时写当前配方名", plan.values.get("Recipe: Sunshard") == 1)
    check("完成时不伪造历史键", "Recipe: Sunshard Wizard" not in plan.values)

    reset_plan = reset_mod.build_plan(legacy, reset_mod.OP_QUESTS,
                                      sync_quest_recipes=True, catalog=catalog)
    check("重置任务同样清历史配方键",
          "Recipe: Sunshard Wizard" not in reset_plan.values
          and "Recipe: Sunshard Paula" not in reset_plan.values, str(reset_plan.values))


def test_model_and_validate() -> None:
    doc = _doc()
    rows = doc.quests()
    check("任务列表带任务线", all("line" in row for row in rows))
    check("旧线任务被识别", sum(1 for row in rows if row["line"] == "old") == 4)
    recipes = doc.recipes()
    check("配方返回三元组", all(len(item) == 3 for item in recipes))
    check("两线配方分开", {prefix for prefix, _n, _v in recipes} ==
          {"Recipe: ", "Old Recipe: "})
    check("按线筛选配方", [n for _p, n, _v in doc.recipes("old")] == ["Boat"])
    check("当前线配方", [n for _p, n, _v in doc.recipes("current")] == ["Arrow"])

    issues = validate.validate(doc, _catalog())
    codes = {i.code for i in issues}
    check("旧配方不再未知", "W_UNKNOWN" not in codes)
    check("键族冲突提示", "I_QUESTLINE_EXTRA" in codes)
    bad = model.SaveDoc.from_dict({"Questline": 1, "Old Quest: Dancing Lessons": "nope"})
    check("旧线非法步骤告警",
          any(i.code == "W_QUEST_STEP" for i in validate.validate(bad, _catalog())))
    custom = model.SaveDoc.from_dict({"Questline": 1, "Old Quest: Custom": "#start"})
    check("旧线自定义任务仅提示",
          any(i.code == "I_QUEST_CUSTOM" and i.level == "info"
              for i in validate.validate(custom, _catalog())))


def test_reset() -> None:
    doc = _doc()
    plan = reset_mod.build_plan(doc, reset_mod.OP_QUESTS, catalog=_catalog())
    check("重置任务清两线任务键",
          not any(k.startswith(("Quest: ", "Old Quest: ")) for k in plan.values))
    plan = reset_mod.build_plan(doc, reset_mod.OP_FULL, catalog=_catalog())
    check("彻底重置清旧线配方", "Old Recipe: Boat" not in plan.values)
    check("彻底重置清当前线配方", "Recipe: Arrow" not in plan.values)


def test_installed_catalog() -> None:
    catalog = gamedata.load_catalog()
    if catalog.error:
        print("  skip 未安装游戏，跳过真实目录检查")
        return
    check("旧线任务数 37（35 + 2 商店）", len(catalog.old_quests) == 37,
          str(len(catalog.old_quests)))
    check("商店任务 2 个", sum(1 for q in catalog.old_quests.values() if q.shop) == 2)
    forest = questops.old_forest(catalog)
    check("旧线 4 个根", len(forest.roots) == 4)
    check("旧线 35 个节点", len(forest.defs) == 35)
    check("最大深度 8", max(forest.depth.values()) == 8)
    check("旧线无日常", not any(q.daily for q in catalog.old_quests.values()))
    check("带击杀目标 12 个",
          sum(1 for q in catalog.old_quests.values() if q.targets) == 12,
          str(sum(1 for q in catalog.old_quests.values() if q.targets)))
    check("旧线目标键带前缀",
          all(t.key.startswith("Old Quest: ") for q in catalog.old_quests.values()
              for t in q.targets))
    check("当前线不含旧线标题", "Ted the Viking" not in catalog.quests)


def main() -> int:
    for title, fn in (("任务线基础", test_schema), ("目录", test_catalog),
                      ("森林", test_forest), ("单任务计划", test_quest_plan),
                      ("链路计划", test_chain_plan), ("任务线切换", test_questline_plan),
                      ("配方别名", test_recipe_aliases),
                      ("模型与校验", test_model_and_validate), ("重置", test_reset),
                      ("本机目录", test_installed_catalog)):
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
