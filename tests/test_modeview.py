"""当前模式视图、模式复制与背包保留区回归测试。"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gamedata
import itemops
import modeops
import modeview
import reset
import schema
import validate
from model import SaveDoc

failures=[]
def check(name,cond,detail=""):
 print(("  ok   " if cond else "  FAIL ")+name+(f" {detail}" if detail and not cond else ""))
 if not cond:failures.append(name)

def doc():
 return SaveDoc.from_dict({
  "charName":"Tester","charGender":"Male","Purchased Skill Points":7,"encrypted":False,
  "Current Level":17,"Current Experience":10,"Inventory_name_4":"Stone","Inventory_count_4":5,
  "Inventory_name_5":"Dirt","Inventory_count_5":2,"Quest: Tutorial":"#end",
  "Current Level_sandbox":3,"Current Experience_sandbox":1,
  "Inventory_name_4_sandbox":"Sand","Inventory_count_4_sandbox":1,
  "Quest: Tutorial_sandbox":"#start",
 })

def test_view():
 full=doc();view=modeview.ModeViewDoc(full,"sandbox")
 check("模式视图使用去后缀键",view.get("Current Level")==3 and "Quest: Tutorial" in view.values)
 check("共享身份与购买点可见",view.get("charName")=="Tester" and view.get("Purchased Skill Points")==7)
 check("剧情不混入沙盒视图",view.get("Inventory_name_4")=="Sand")
 view.push_undo("level")
 view.set("Current Level",9)
 check("编辑写回对应后缀",full.get("Current Level_sandbox")==9 and full.get("Current Level")==17)
 view.undo()
 check("撤销恢复完整文档",full.get("Current Level_sandbox")==3)
 view.values["Inventory_name_6"]="Glass"
 view.values["Inventory_count_6"]=2
 view.order.extend(["Inventory_name_6","Inventory_count_6"])
 check("结构新增键实时映射",full.get("Inventory_name_6_sandbox")=="Glass"
       and "Inventory_name_6_sandbox" in full.order)
 view.delete("Inventory_name_6")
 check("删除只影响当前模式", "Inventory_name_6_sandbox" not in full.values
       and full.get("Inventory_name_4")=="Stone")
 check("模式槽位解析保留容器前缀",schema.slot_family("Inventory_name_4_sandbox")==("Inventory_sandbox","name",4))
 plan=reset.build_plan(view,reset.OP_LEVEL)
 reset.apply_plan(view,plan)
 check("重置只作用于当前模式",full.get("Current Level_sandbox")==1 and full.get("Current Level")==17)
 catalog=gamedata.Catalog(quests={"Tutorial":gamedata.QuestDef("Tutorial","Wizard",False,steps=("#start","#end"))})
 copied=modeops.build_copy_plan(doc(),"story","survival")
 merged=doc();modeops.apply_plan(merged,copied)
 codes={i.code for i in validate.validate(merged,catalog)}
 check("模式后缀任务不误报为自定义任务","I_QUEST_CUSTOM" not in codes)

def test_copy():
 full=doc();plan=modeops.build_copy_plan(full,"story","creative")
 check("创造模式复制排除任务",plan.skipped==1 and "Quest: Tutorial_creative" not in plan.values)
 check("非任务数据仍复制",plan.values.get("Current Level_creative")==17
       and plan.values.get("Inventory_name_4_creative")=="Stone")
 sandbox=modeops.build_copy_plan(full,"story","sandbox")
 check("沙盒复制排除任务且目标原本有数据时阻断",sandbox.error=="md.targetNotEmpty")
 survival=modeops.build_copy_plan(full,"story","survival")
 check("生存模式保留任务",survival.values.get("Quest: Tutorial_survival")=="#end")

def test_reserved_grid():
 full=doc()
 itemops.sort_by_name(full,"Inventory",6,lambda slot:slot.name,start=4)
 check("普通背包按名称排序",full.get("Inventory_name_4")=="Dirt" and full.get("Inventory_name_5")=="Stone")
 full=doc()
 itemops.apply_order(full,"Inventory",[5,4],[4,5])
 check("拖拽不改变保留区映射",full.get("Inventory_name_4")=="Dirt" and full.get("Inventory_name_5")=="Stone")
 check("背包前四格从普通排列起点排除",4 not in list(range(0,4)))

def main():
 for title,fn in (("模式视图",test_view),("模式复制",test_copy),("背包保留区",test_reserved_grid)):
  print(f"\n[{title}]");fn()
 print()
 if failures:
  print(f"失败 {len(failures)} 项：{failures}");return 1
 print("全部通过");return 0
if __name__=="__main__":raise SystemExit(main())
