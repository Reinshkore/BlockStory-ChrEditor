"""中英双语文案。

规则：所有面向用户的字符串都必须走 `t()`。键名、物品名、任务名不翻译
（它们是存档契约），只翻译界面说明。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

DEFAULT_LANG = "en"
LANGS = ("en", "zh", "ru", "pt", "es")
LANG_LABEL = {
    "en": "English", "zh": "简体中文", "ru": "Русский",
    "pt": "Português (Brasil)", "es": "Español",
}
HTML_LANG = {"en": "en", "zh": "zh-CN", "ru": "ru", "pt": "pt-BR", "es": "es"}
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
SETTINGS_FILE = CACHE_DIR / "settings.json"
LEGACY_SETTINGS_FILE = Path(__file__).resolve().parent / ".venv" / "save_editor_settings.json"

S: dict[str, tuple[str, str]] = {
    # ── 应用与导航 ───────────────────────────────────────────────
    "app.title": ("Save Editor", "存档编辑器"),
    "app.subtitle": ("Block Story", "Block Story"),
    "app.version": ("v14.5.3", "v14.5.3"),
    "nav.overview": ("Overview", "概览"),
    "nav.fields": ("Fields", "字段"),
    "nav.items": ("Items", "物品与容器"),
    "nav.quests": ("Quests", "任务与成就"),
    "nav.tidy": ("Tidy", "整理条目"),
    "nav.reset": ("Reset", "重置进度"),
    "nav.modes": ("Mode data", "模式数据"),
    "nav.save": ("Review & Save", "校验与保存"),

    # ── 侧栏 ─────────────────────────────────────────────────────
    "side.save": ("Save file", "当前存档"),
    "side.mode": ("Mode", "模式"),
    "side.nav": ("Navigate", "导航"),
    "side.edit": ("Edit mode", "编辑模式"),
    "side.editOn": ("Write access on", "可编辑"),
    "side.editOff": ("Read-only", "只读"),
    "side.editHint": ("Turn on to change values", "打开后才能改值"),
    "side.unsaved": ("Unsaved changes: {n}", "未保存改动 {n} 处"),
    "side.undo": ("Undo last action", "撤销上一步"),
    "side.undoLabel": ("Undid: {label}", "已撤销：{label}"),
    "side.noUndo": ("Nothing to undo", "没有可撤销的操作"),
    "side.multiplayer": ("Local saves are ignored in multiplayer — the server is authoritative.",
                         "联机模式下本地存档不生效，服务端权威。"),
    "side.choose": ("Character", "角色"),
    "side.browse": ("Open another file", "打开其他文件"),
    "side.path": ("File path", "文件路径"),
    "side.open": ("Open", "打开"),
    "side.browseFile": ("Choose file…", "选择文件…"),
    "side.browseHint": ("Opens the system file dialog on the machine running this app",
                        "在运行本程序的这台电脑上弹出系统文件选择框"),
    "side.browseTitle": ("Select a Block Story save", "选择 Block Story 存档"),
    "side.browseFail": ("Could not open the system dialog: {msg}", "无法打开系统对话框：{msg}"),
    "side.orTypePath": ("or paste a path", "或粘贴路径"),
    "side.upload": ("Or drop a .chr file", "或拖入 .chr 文件"),
    "side.noSaves": ("No save found in {dir}", "在 {dir} 下没有找到存档"),
    "side.keys": ("keys", "键"),
    "side.encrypted": ("Cannot read: {msg}", "无法读取：{msg}"),
    "side.reload": ("Reload from disk", "从磁盘重新载入"),
    "side.reloadHint": ("Discard the in-memory copy and read the current file again", "放弃内存副本并重新读取当前文件；有改动时会先确认"),
    "side.unsavedTitle": ("Unsaved changes", "有未保存的改动"),
    "side.unsavedLoad": ("Opening {name} will discard the current unsaved changes.", "打开 {name} 将丢弃当前的未保存改动。"),
    "side.discardOpen": ("Discard and open", "丢弃并打开"),
    "side.keepWorking": ("Keep current work", "保留当前改动"),
    "side.reloaded": ("Reloaded {name}", "已重新载入 {name}"),
    "side.lang": ("Language", "语言"),
    "side.langDialog": ("Choose interface language", "选择界面语言"),
    "side.langSaved": ("Language preference is saved in this local Python environment.", "语言偏好已保存在本机 Python 虚拟环境中。"),

    # ── 通用 ─────────────────────────────────────────────────────
    "c.apply": ("Apply", "应用"),
    "c.cancel": ("Cancel", "取消"),
    "c.close": ("Close", "关闭"),
    "c.preview": ("Preview", "预览"),
    "c.all": ("All", "全部"),
    "c.none": ("None", "无"),
    "c.yes": ("Yes", "是"),
    "c.no": ("No", "否"),
    "c.search": ("Search keys or values", "搜索键名或值"),
    "c.of": ("of", "/"),
    "c.rows": ("Rows: {n}", "共 {n} 行"),
    "c.matching": ("Matching: {n}", "匹配 {n} 个"),
    "c.showing": ("Showing {n} of {total}", "显示 {n} / {total}"),
    "c.more": ("… {n} more", "… 还有 {n} 条"),
    "c.error": ("Error", "错误"),
    "c.warn": ("Warning", "警告"),
    "c.info": ("Note", "提示"),
    "c.ok": ("OK", "正常"),
    "c.keys": ("{n} keys", "{n} 个键"),
    "c.none_yet": ("Nothing here yet.", "暂无内容。"),
    "c.line": ("Line {n}", "第 {n} 行"),
    "c.changed": ("{n} changed", "已改 {n} 处"),
    "c.nochange": ("No changes", "没有改动"),

    "kind.int": ("Integer", "整数"),
    "kind.float": ("Float", "浮点"),
    "kind.str": ("Text", "文本"),
    "kind.bool": ("Boolean", "布尔"),
    "kind.null": ("Null", "空值"),

    # ── 分类 ─────────────────────────────────────────────────────
    "cat.identity": ("Identity", "身份"),
    "cat.growth": ("Progress & Skill Points", "成长与技能点"),
    "cat.attr_max": ("Attribute Caps", "属性上限"),
    "cat.status": ("Current State", "当前状态"),
    "cat.inventory": ("Backpack", "背包"),
    "cat.quickslot": ("Quick Slots", "快捷栏"),
    "cat.equipment": ("Equipment", "装备栏"),
    "cat.container": ("Placed Containers", "放置容器"),
    "cat.pet_bag": ("Pet Bags", "宠物背包"),
    "cat.pet_equip": ("Pet Equipment", "宠物装备"),
    "cat.pet_stat": ("Pet Stats", "宠物属性"),
    "cat.pet_meta": ("Pet Profiles", "宠物档案"),
    "cat.quest": ("Quests", "任务"),
    "cat.achieve": ("Achievements", "成就"),
    "cat.recipe": ("Recipes", "配方"),
    "cat.misc": ("Misc", "杂项"),

    "group.character": ("Character", "角色"),
    "group.attribute": ("Attributes", "属性"),
    "group.bag": ("Inventory", "背包"),
    "group.container": ("Containers", "容器"),
    "group.pet": ("Pets", "宠物"),
    "group.quest": ("Quests", "任务"),
    "group.progress": ("Achievements & Recipes", "成就与配方"),
    "group.misc": ("Misc", "杂项"),

    # ── 概览 ─────────────────────────────────────────────────────
    "ov.title": ("Overview", "概览"),
    "ov.sub": ("Everything below is read straight from the save file, except the XP bar and the point breakdown, which are derived.",
               "以下数字直接来自存档；经验条与加点分布是推算值。"),
    "ov.level": ("Level", "等级"),
    "ov.skill": ("Skill points", "技能点"),
    "ov.skillSub": ("unspent", "未分配"),
    "ov.skillHint": ("spent {spent} · total {total}", "已花 {spent} · 总量 {total}"),
    "ov.bag": ("Backpack", "背包"),
    "ov.bagHint": ("{used} of {cap} slots", "{used} / {cap} 格"),
    "ov.pets": ("Pets", "宠物"),
    "ov.petsHint": ("{n} with stats", "{n} 只带属性数据"),
    "ov.xp": ("Experience", "经验"),
    "ov.xpNext": ("{cur} / {cap} · {left} to next level", "{cur} / {cap} · 距升级还差 {left}"),
    "ov.xpMax": ("Level cap reached", "已到等级上限"),
    "ov.points": ("Point breakdown (derived from attribute caps)", "加点分布（由属性上限反算）"),
    "ov.pointsSum": ("Total invested {invested}", "合计投入 {invested} 点"),
    "ov.pointsSpent": ("Book says {spent} spent", "存档账面已花 {spent} 点"),
    "ov.pointsDiff": ("Gap {diff} → inconsistent", "差 {diff} 点 → 数值不闭合"),
    "ov.pointsOk": ("Numbers add up", "数值闭合"),
    "ov.pointsNote": ("Per-point gains: health/mana +10, breath +5, weapon damage +1, bow force +10, loot +0.1, walk +0.05, fly +0.1, dig −0.01. Armor, hunger and regen are gear-driven and excluded.",
                      "换算：生命/法力每点 +10，憋气 +5，剑/魔法/箭/枪伤 +1，弓力 +10，拾取 +0.1，行走 +0.05，飞行 +0.1，挖掘 −0.01。护甲、饥饿与回复由装备驱动，不在表内。"),
    "ov.check": ("Save check", "存档检查"),
    "ov.checkErr": ("Blocking errors", "阻断性错误"),
    "ov.checkErrHint": ("Type mismatches that would crash the game on load", "类型不符，游戏读档会抛异常"),
    "ov.checkWarn": ("Warnings", "警告"),
    "ov.checkWarnHint": ("Out-of-range or inconsistent values", "越界或数值不自洽"),
    "ov.checkUnknown": ("Unrecognised keys", "未识别键"),
    "ov.checkUnknownHint": ("Kept as-is, no type checking", "原样保留，不做类型校验"),
    "ov.file": ("File", "文件"),
    "ov.path": ("Path", "路径"),
    "ov.size": ("Size", "大小"),
    "ov.mtime": ("Modified", "最后修改"),
    "ov.backups": ("Backups", "备份"),
    "ov.backupNone": ("none", "无"),
    "ov.roundtrip": ("Serializer check", "序列化校验"),
    "ov.roundtripOk": ("Re-serialising an untouched save reproduces the original byte for byte", "未改动时重新序列化与原文件逐字节相同"),
    "ov.roundtripFail": ("Round-trip mismatch: {detail}", "往返不一致：{detail}"),
    "ov.petsOf": ("Pets", "宠物"),
    "ov.fastest": ("Quick actions", "快捷入口"),
    "ov.playtime": ("Distance travelled", "行走距离"),

    # ── 字段 ─────────────────────────────────────────────────────
    "fd.title": ("Fields", "字段"),
    "fd.sub": ("{n} keys, grouped by category. Values are editable; type and category columns are read-only.",
               "共 {n} 个键，按分类分组。值可改，类型与分类列只读。"),
    "fd.view": ("View", "视图"),
    "fd.view.category": ("By category", "分类"),
    "fd.view.mode": ("By world mode", "游戏模式"),
    "fd.view.raw": ("File order", "原始键序"),
    "fd.view.changed": ("Changed", "改动"),
    "fd.view.issues": ("Issues", "异常"),
    "fd.filterCat": ("Category", "分类"),
    "fd.filterType": ("Type", "类型"),
    "fd.col.key": ("Key", "键"),
    "fd.col.value": ("Value", "值"),
    "fd.col.type": ("Type", "类型"),
    "fd.col.cat": ("Category", "分类"),
    "fd.col.status": ("", "状态"),
    "fd.col.note": ("Note", "说明"),
    "fd.detail": ("Field detail", "字段详情"),
    "fd.pick": ("Pick a key to inspect it", "选择一个键查看详情"),
    "fd.default": ("Default {value}", "默认 {value}"),
    "fd.range": ("Range {min}–{max}", "范围 {min}–{max}"),
    "fd.resetDefault": ("Reset to default", "恢复默认值"),
    "fd.deleteKey": ("Delete this key", "删除该键"),
    "fd.deleted": ("Deleted {key}", "已删除 {key}"),
    "fd.noAdd": ("Adding new keys is disabled — the editor only touches keys the game already wrote.",
                 "不允许新增键：编辑器只改游戏自己写过的键。"),
    "fd.empty": ("No key matches the current filters.", "当前筛选下没有键。"),
    "fd.readonlyHint": ("Read-only. Turn on Edit mode in the sidebar.", "只读。请在侧栏打开编辑模式。"),
    "fd.editedN": ("{n} edited in this view", "本视图已改 {n} 处"),
    "fd.revert": ("Revert", "还原"),
    "fd.mode.story": ("Story / shared", "剧情 / 共享"),
    "fd.mode.survival": ("Survival", "生存"),
    "fd.mode.creative": ("Creative", "创造"),
    "fd.mode.hardcore": ("Hardcore", "硬核"),
    "fd.mode.sandbox": ("Sandbox", "沙盒"),
    "fd.badInput": ("{key}: {msg}", "{key}：{msg}"),

    # ── 物品 ─────────────────────────────────────────────────────
    "it.title": ("Items & Containers", "物品与容器"),
    "it.sub": ("The slot index is the grid position; empty slots keep their place.", "槽位索引就是格子位置，空格保留占位。"),
    "it.used": ("{used} / {cap} slots used", "已用 {used} / {cap} 格"),
    "it.empty": ("empty", "空"),
    "it.edit": ("Edit slot", "编辑槽位"),
    "it.name": ("Item name", "物品名称"),
    "it.count": ("Count", "数量"),
    "it.data": ("Data", "data"),
    "it.paint": ("Paint", "paint"),
    "it.clear": ("Clear this slot", "清空该格"),
    "it.cleared": ("Cleared {prefix}[{index}]", "已清空 {prefix}[{index}]"),
    "it.note": ("data and paint are 0–65535. Most items keep data = 0; paint stores dye.", "data 与 paint 取 0–65535。多数物品 data 为 0，paint 存染色。"),
    "it.moreEmpty": ("{n} more slots are empty", "还有 {n} 格为空"),
    "it.showAll": ("Show all", "展开全部"),
    "it.showLess": ("Show used only", "只看已用"),
    "it.noItems": ("This character has no such storage.", "该角色没有这类储物。"),
    "it.containerEmpty": ("No placed containers in this save.", "该存档没有放置容器。"),
    "it.unnamed": ("(unnamed)", "（无名）"),
    "it.catalog": ("Game catalog", "游戏目录"),
    "it.catalog.items": ("Items", "物品"),
    "it.catalog.mobs": ("Creatures", "生物"),
    "it.catalogSearch": ("Search by display name or save ID", "按游戏显示名或存档 ID 搜索"),
    "it.catalogPlaceholder": ("e.g. Mutagen, Ruby, Dragon Lord", "例如：诱变剂、红水晶块、龙主"),
    "it.displayEn": ("English name", "英文名"),
    "it.displayZh": ("Chinese name", "中文名"),
    "it.catalogSource": ("Read from this installation: {path}", "读取自本机游戏：{path}"),
    "it.catalogError": ("Catalog unavailable: {msg}. Expected game data at {path}", "目录不可用：{msg}。预期游戏数据位置：{path}"),
    "it.catalogRefresh": ("Reload after a game update", "游戏更新后重新载入"),
    "it.noMatch": ("No matching entries.", "没有匹配项。"),
    "it.columns": ("{n} columns", "每行 {n} 格"),
    "it.mode.edit": ("Edit slots", "编辑物品"),
    "it.mode.arrange": ("Arrange", "整理位置"),
    "it.clickMove": ("Click to move instead", "改用点选移动"),
    "it.clickMoveHint": ("Select a source slot, then a destination to swap them", "先点来源格，再点目标格，两格交换"),
    "it.sort": ("Sort by name", "按名称排序"),
    "it.sortHint": ("Sort occupied slots and move empty slots to the end", "已用格按名称排序，空格移到末尾"),
    "it.cancelMove": ("Cancel move", "取消移动"),
    "it.moveSource": ("Source: {prefix} #{slot}; choose a destination in any container", "来源：{prefix} 第 {slot} 格；可在任意容器中选择目标格"),
    "it.dragHint": ("Drag cards to rearrange. Every occupied and empty card keeps one slot.", "拖动卡片调整位置；已用格和空格都参与排列。"),
    "it.dragError": ("Could not apply drag result: {msg}", "无法应用拖拽结果：{msg}"),
    "it.nameHelp": ("Type to search both display names and save IDs. Unknown existing IDs remain available.", "可输入游戏显示名或存档 ID 检索；已有的未知 ID 也会保留。"),
    "it.spawnerMob": ("Creature to spawn", "刷怪生物"),
    "it.spawnerHint": ("data = {data} → {mob}", "data = {data} → {mob}"),
    "it.structuralKeys": ("Saving a previously empty slot creates only its standard name/count/data/paint keys.", "写入原本为空的格子时，只补齐游戏固定的 name/count/data/paint 四个键。"),
    "it.worldContainer": ("Placed container (empty save prefix)", "放置容器（存档空前缀）"),
    "it.category": ("Category", "分类"),
    "it.reserved": ("Reserved", "游戏保留"),
    "it.reservedHint": ("Indices 0–3 are locked by the game. Regular backpack slots start at #5; these four are not the 2x2 crafting grid.", "索引 0–3 由游戏强制锁定，普通背包从第 5 格开始；这四格不是 2x2 合成台。"),

    # ── 任务 ─────────────────────────────────────────────────────
    "q.title": ("Quests & Achievements", "任务与成就"),
    "q.sub": ("Quick progress presets plus the complete raw progress list.", "快捷调整进度，也可查看完整的原始进度。"),
    "q.tab.main": ("Main story", "主线"),
    "q.tab.side": ("Side quests", "支线"),
    "q.tab.daily": ("Daily quests", "日常"),
    "q.tab.all": ("All progress", "全部进度"),
    "q.noMainline": ("The current game files do not contain the expected main story chain.", "当前游戏文件中没有找到预期的主线链。"),
    "q.disabledMode": ("The game disables quests in Creative and Sandbox modes. Missing quest keys are normal in this view; achievements and stored recipes remain available below.", "创造和沙盒模式会关闭任务系统，此视图中没有任务键属于正常现象；成就与已存配方仍列在下方。"),
    "q.mainHint": ("19 linked stages, derived from the installed game's quest dependencies.", "共 19 个衔接阶段，由本机游戏的任务依赖关系推导。"),
    "q.mainGap": ("Non-contiguous save: these later quests are already completed: {names}. Applying a stage preset will reset them.", "存档进度不连续：后续任务已完成：{names}。应用阶段预设会将它们重置。"),
    "q.mainStage": ("Completed main-story quests", "已完成的主线任务数"),
    "q.mainStep": ("Step of the current quest", "当前任务的步骤"),
    "q.mainComplete": ("Main story completed", "主线已完成"),
    "q.planCounts": ("Preview: +{add} / ~{mod} / −{rem}", "预览：新增 {add} · 修改 {mod} · 删除 {rem}"),
    "q.showPlan": ("Preview affected keys and stages", "预览受影响的键与阶段"),
    "q.stage": ("Stage", "阶段"),
    "q.quest": ("Quest", "任务"),
    "q.targetStep": ("Target step", "目标步骤"),
    "q.mainNote": ("Earlier quests are marked #end and the current quest's stale counters are cleared. Rewards, achievements and persistent world changes are not replayed; only quest progress and explicitly selected synchronisation are edited.", "此前的任务标记为 #end，并清除当前任务的旧计数；奖励、成就及持久世界变化不会补执行，只修改任务进度和明确选择的联动项。"),
    "q.syncRecipes": ("Sync recipes unlocked by main-story quests", "同步主线任务解锁的配方"),
    "q.syncRecipesHint": ("Advance: add rewards from completed main quests. Roll back: remove their recipes only when no other completed quest still provides them.", "前进时补充已完成主线的配方；回退时移除失效主线的配方，但其他已完成任务仍提供的同名配方会保留。"),
    "q.syncSide": ("Sync side and daily quest states", "同步支线与日常任务状态"),
    "q.syncSideHint": ("On rollback, reset side/daily quests whose prerequisites are no longer completed, including counters and daily timestamps. Unrelated and still-unlocked quests stay untouched.", "回退主线时，重置前置条件已不再满足的支线和日常，包括计数与日常时间戳；无关或仍已解锁的任务保持不变。"),
    "q.syncSummary": ("Linked changes: {recipes} recipe keys; {quests} side/daily quests reset", "联动变化：{recipes} 个配方键；重置 {quests} 个支线/日常任务"),
    "q.applyMain": ("Apply main-story progress", "应用主线进度"),
    "q.applied": ("Applied: {n} changed keys", "已应用：{n} 个键发生变化"),
    "q.sidePick": ("Side quest", "支线任务"),
    "q.current": ("Current", "当前"),
    "q.ending": ("Ending", "结局"),
    "q.completeSide": ("Mark completed", "标记完成"),
    "q.resetSide": ("Reset quest", "重置任务"),
    "q.sideNote": ("Completing a quest changes its saved state only; it does not replay rewards or side effects. Reset also removes its counters and daily timestamp.", "标记完成只修改存档状态，不补发奖励或执行副作用；重置还会清除计数与日常时间戳。"),
    "q.dailyPick": ("Daily quest", "日常任务"),
    "q.dailyCount": ("Lifetime completions", "历史完成次数"),
    "q.dailyTiers": ("Content changes at these completion counts: {tiers}", "完成次数达到这些值时内容分档：{tiers}"),
    "q.dailyNoTiers": ("This quest has no completion-count tier in the game files.", "该任务在游戏文件中没有按完成次数分档。"),
    "q.dailyState": ("Today's state", "今日状态"),
    "q.dailyState.keep": ("Keep current step", "保持当前步骤"),
    "q.dailyState.completed": ("Mark today completed", "标记今日完成"),
    "q.dailyState.reset": ("Reset today", "重置今日"),
    "q.applyDaily": ("Apply daily progress", "应用日常进度"),
    "q.dailyNote": ("Count tiers are read from the #start step's <complete count=…> rules. Keeping the current step changes only the lifetime counter.", "次数档位来自 #start 步骤中的 <complete count=…> 规则。保持当前步骤时只修改历史次数。"),
    "q.quests": ("Quests", "任务"),
    "q.achieve": ("Achievements", "成就"),
    "q.recipes": ("Recipes", "配方"),
    "q.start": ("Not started", "未开始"),
    "q.active": ("In progress", "进行中"),
    "q.done": ("Finished", "已完成"),
    "q.claimed": ("Claimed", "已领取"),
    "q.unclaimed": ("Not claimed", "未领取"),
    "q.times": ("Times completed", "完成次数"),
    "q.step": ("Step", "当前步骤"),
    "q.daily": ("Daily reset", "日常重置"),
    "q.trap": ("Achievements and recipes are coupled: the game treats an unlocked reward recipe as a claimed achievement. Clearing achievements alone would bring some of them back on the next load, which is why they are only cleared together on the Reset page.",
               "成就与配方是耦合的：游戏会把「奖励配方已解锁」当成「成就已领取」。单独清成就会在下次加载时把一部分成就带回来，因此只在重置页里与配方一起清。"),
    "q.progressOf": ("{n} in progress", "{n} 条有进度"),
    "q.progress": ("Progress", "进度"),
    "q.counters": ("Raw step counters", "原始步骤计数"),
    "q.countersHint": ("Includes counters for custom quests and quests removed from the current version.", "包括自定义任务及当前版本已移除任务的计数。"),

    # ── 任务线
    "q.tab.chain": ("Quest chains", "任务链"),
    "q.line.current": ("Current questline", "当前任务线"),
    "q.line.old": ("Old questline", "旧任务线"),
    "q.line.badge": ("Questline: {name}", "任务线：{name}"),
    "q.line.stats": ("{total} quests · {done} done / {active} in progress / {start} not started", "{total} 个任务 · 已完成 {done} / 进行中 {active} / 未开始 {start}"),
    "q.line.switch": ("Switch questline", "切换任务线"),
    "q.line.write": ("Will write Questline = {value}", "将写入 Questline = {value}"),
    "q.line.otherKeys": ("{count} keys of the other questline stay in the file but will not be loaded by the game.", "另一任务线的 {count} 个键会留在存档里，但不会被游戏加载。"),
    "q.line.targetStats": ("Target line: {total} quests, {done} already completed.", "目标线：{total} 个任务，当前已完成 {done} 个。"),
    "q.line.recipes": ("Recipes: {own} unlocked in this line, {other} in the other line.", "配方：本线已解锁 {own} 项，另一线 {other} 项。"),
    "q.line.recipeNote": ("The two questlines store recipe unlocks under different prefixes. Switching does not migrate them.", "两条任务线的配方解锁使用不同前缀，切换不会迁移。"),
    "q.line.confirm": ("I understand progress and recipe unlocks are not migrated.", "我明白进度与配方解锁都不会迁移。"),
    "q.line.apply": ("Switch", "确认切换"),
    "q.line.done": ("Questline switched. It takes effect the next time the game loads this save.", "已切换任务线，游戏下次读档时生效。"),
    "q.line.missing": ("This save has no Questline key; the game treats it as the current line.", "此存档没有 Questline 键，游戏按当前任务线处理。"),
    "q.line.mismatch": ("Questline is {value}; values other than 0 or 1 are treated as the current line.", "Questline 的值是 {value}；除 0 与 1 之外的值按当前任务线处理。"),
    "q.line.conflict": ("{count} keys from the other questline are present. The game does not load them.", "存在另一任务线的 {count} 个键，游戏不会加载它们。"),

    # ── 支线编辑
    "q.npc": ("NPC", "NPC"),
    "q.all": ("All", "全部"),
    "q.status": ("Target state", "目标状态"),
    "q.targets": ("Step goals (read-only)", "该步骤目标（只读）"),
    "q.targetKill": ("Kill {name} × {count}", "击杀 {name} × {count}"),
    "q.noTargets": ("This step has no kill counter; progress is checked against your inventory or position.", "该步骤没有击杀计数，进度直接按背包或位置判定。"),
    "q.prereq": ("Prerequisites", "前置任务"),
    "q.prereqNone": ("None", "无"),
    "q.prereqWarn": ("Prerequisites are not completed, so the game will not offer this quest. Changing its state does not make it available.", "前置任务未完成，游戏内不会出现该任务；修改状态不会让它变得可接。"),
    "q.applySide": ("Apply this quest", "应用本任务改动"),

    # ── 任务链
    "q.chain.mode": ("Operation", "操作"),
    "q.chain.complete": ("Complete up to this node", "完成到该节点"),
    "q.chain.reset": ("Reset this node and its descendants", "重置该节点及其后代"),
    "q.chain.node": ("Node", "节点"),
    "q.chain.affected": ("{n} quests affected: {names}", "影响 {n} 个任务：{names}"),
    "q.chain.apply": ("Apply chain change", "应用链路改动"),
    "q.chain.note": ("Completing walks up the dependency chain; resetting touches the node and everything below it. Neither touches sibling branches.", "完成只沿前置链向上，重置只作用于该节点与其所有后代；两者都不碰旁支。"),
    "q.line.col": ("Questline", "任务线"),

    # ── 整理 ─────────────────────────────────────────────────────
    "td.title": ("Tidy entries", "整理条目"),
    "td.sub": ("Four independent operations. Preview first; applying only touches memory until you save.", "四项独立操作。先预览；应用后仍只改内存，存档要另行写入。"),
    "td.normalize": ("Normalise types and numbers", "规范化类型与数值"),
    "td.normalizeD": ("Integer keys get integers, float keys get floats, so the game's unboxing cast cannot fail.", "整数键取整数、浮点键取浮点，避免游戏拆箱失败。"),
    "td.reorder": ("Reorder by category", "按分类重排"),
    "td.reorderD": ("Character → attributes → bag → containers → pets → quests → achievements → recipes, with natural numeric order inside a family.", "角色 → 属性 → 背包 → 容器 → 宠物 → 任务 → 成就 → 配方，同族内按自然数字序。"),
    "td.dropEmpty": ("Drop empty slots", "删除全空槽位"),
    "td.dropEmptyD": ("Removes slot keys whose name is empty and whose count/data/paint are all zero. The game reads these as non-existent anyway.", "删除 name 为空且 count/data/paint 全为 0 的槽位键；游戏读档时本来就当作不存在。"),
    "td.compact": ("Compact slot indices", "压缩槽位编号"),
    "td.compactD": ("Moves used slots to 0,1,2… inside each container. Visual positions change; items do not. Equipment is skipped because the hand keys store absolute indices.", "把每个容器的非空槽位排到 0,1,2…。格子位置会变，物品不会丢。装备栏跳过，因为左右手存的是绝对槽位号。"),
    "td.added": ("Added", "新增"),
    "td.removed": ("Removed", "删除"),
    "td.modified": ("Rewritten", "改写"),
    "td.fixes": ("Type fixes: {n}", "类型修正 {n} 个"),
    "td.fixesLabel": ("Type fixes", "类型修正"),
    "td.previewHead": ("First changes", "前若干条变化"),
    "td.apply": ("Apply to memory", "应用到内存"),
    "td.applied": ("Tidy applied: −{removed}, ~{modified}", "已整理：删除 {removed}、改写 {modified}"),
    "td.nothing": ("Nothing to change with the current selection.", "当前选项下没有需要改动的内容。"),

    # ── 重置 ─────────────────────────────────────────────────────
    "rs.title": ("Reset progress", "重置进度"),
    "rs.sub": ("Five separate operations. Each one previews exactly which keys it touches before you apply it.", "五种并列操作。每一项都先列出会动哪些键，再决定是否应用。"),
    "rs.op.level": ("Level reset", "等级重置"),
    "rs.op.levelD": ("Level → 1, experience → 0, attributes untouched, skill points recalculated.", "等级 → 1，经验 → 0，属性不变，技能点重算。"),
    "rs.op.attributes": ("Attribute reset", "属性重置"),
    "rs.op.attributesD": ("The twelve skill-point attributes go back to their defaults and all points are refunded — the same thing the in-game reset scroll does.", "12 项可加点属性回到默认值并退还全部点数，等同游戏内重置卷轴。"),
    "rs.op.quests": ("Reset quests", "重置任务"),
    "rs.op.questsD": ("Deletes Quest, Quest Complete and Daily keys. Quest NPCs may hand out the first step again on the next visit.", "删除 Quest、Quest Complete、Daily 三类键。首次进世界时任务 NPC 可能重新派发起点。"),
    "rs.op.pets": ("Reset pets", "重置宠物"),
    "rs.op.petsD": ("Deletes every pet stat key so the game falls back to prefab defaults. Names, bags and equipment are kept.", "删除全部宠物属性键，让游戏取预制体默认值。名字、背包与装备保留。"),
    "rs.op.full": ("Full reset", "彻底重置"),
    "rs.op.fullD": ("Everything the four above do, plus clearing achievements and recipes together.", "前四项的全部效果，并清除成就与配方。"),
    "rs.fullWarn": ("This also wipes achievements and recipes. They are cleared together because a claimed achievement is inferred from its unlocked recipe.", "这会连成就与配方一起清空。必须一起清，因为「奖励配方已解锁」会被当成「成就已领取」。"),
    "rs.willModify": ("Modifies {n} keys", "修改 {n} 个键"),
    "rs.willRemove": ("Removes {n} keys", "删除 {n} 个键"),
    "rs.detail": ("Keys affected", "受影响的键"),
    "rs.apply": ("Apply to memory", "应用到内存"),
    "rs.applied": ("Applied: {op}", "已应用：{op}"),
    "rs.skillMode": ("Negative unspent points", "未分配点数为负时"),
    "rs.skillMode.clamp": ("Clamp to 0", "记为 0"),
    "rs.skillMode.raw": ("Keep the negative number", "保留负数"),
    "rs.skillModeHint": ("Keeping attributes while dropping to level 1 makes the book-keeping negative: the attributes already consumed the points that level 1 no longer grants.", "保留属性却降到 1 级会让账面变成负数：属性已经吃掉了 1 级不再发放的点数。"),
    "rs.after": ("After this operation", "操作后"),
    "rs.note.negativeUnspent": ("Computed unspent points would be {raw}; writing {stored}. Invested {invested}, level-1 total {total}.", "算出的未分配点数为 {raw}，将写入 {stored}；已投入 {invested}，1 级总量 {total}。"),
    "rs.note.clamped": ("Current values above the new caps were pulled down: {items}.", "超过新上限的当前值已下调：{items}。"),
    "rs.note.quests": ("{count} quest keys will be removed.", "将删除 {count} 个任务键。"),
    "rs.questRecipes": ("Also remove recipes unlocked by quests", "同时移除任务解锁的配方"),
    "rs.questRecipesHint": ("Uses reward declarations in current and old quest XML. Only listed Recipe keys are removed; other recipes stay untouched. This can also make related achievements appear unclaimed.", "依据当前与旧任务 XML 的奖励声明，只删除其中列出的 Recipe 键，其他配方不变；相关成就也可能因此显示为未领取。"),
    "rs.note.questRecipes": ("{count} quest reward recipe keys will be removed.", "将删除 {count} 个任务奖励配方键。"),
    "rs.note.pets": ("{count} pet stat keys across {pets} pets will be removed.", "将删除 {pets} 只宠物的 {count} 个属性键。"),
    "rs.note.progress": ("{count} achievement and recipe keys will be removed.", "将删除 {count} 个成就与配方键。"),
    "rs.empty": ("This operation would not change anything.", "该操作不会产生任何改动。"),
    "rs.done": ("Applied. Nothing is written to disk until you save.", "已应用。在你保存之前不会写入磁盘。"),

    # ── 模式数据 ──────────────────────────────────────────────────
    "md.title": ("Mode-specific character data", "各游戏模式的角色数据"),
    "md.sub": ("Copy a populated mode to an empty one, or clear one mode while keeping at least one other populated mode.", "把已有数据的模式复制到空模式，或清除一个模式；至少保留一个有数据的模式。"),
    "md.action.copy": ("Copy to empty mode", "复制到空模式"),
    "md.action.clear": ("Clear mode data", "清除模式数据"),
    "md.source": ("Source mode", "来源模式"),
    "md.target": ("Empty target mode", "空目标模式"),
    "md.mode": ("Mode to clear", "要清除的模式"),
    "md.keys": ("{n} data keys", "{n} 个数据键"),
    "md.noSource": ("No populated mode is available.", "没有可操作的已有数据模式。"),
    "md.noEmpty": ("Every mode already contains data; copying is disabled to prevent overwrites.", "所有模式都已有数据；为避免覆盖，不能执行复制。"),
    "md.copyHint": ("Only an empty target is allowed. Existing target data is never overwritten.", "只允许复制到空模式，绝不覆盖目标模式的既有数据。"),
    "md.questPolicy": ("Creative and Sandbox disable quests in the game, so Quest / Quest Complete / Daily keys are excluded from the copy.", "游戏在创造和沙盒模式下禁用任务，因此复制时会排除 Quest / Quest Complete / Daily 键。"),
    "md.skipped": ("{n} unsupported quest keys are excluded", "已排除 {n} 个目标模式不支持的任务键"),
    "md.clearHint": ("Deletes only the selected mode's data. The last populated mode cannot be cleared.", "只删除所选模式的数据；最后一个有数据的模式不能清除。"),
    "md.sharedNote": ("Character identity, Purchased Skill Points and the file encryption marker are preserved and are not copied between modes.", "角色身份、跨模式共享的 Purchased Skill Points 和文件加密标记会保留，也不随模式复制。"),
    "md.lastMode": ("Blocked: this is the last populated mode. Clearing it would remove all mode-specific character data.", "已阻止：这是最后一个有数据的模式，清除会删除全部模式角色数据。"),
    "md.targetNotEmpty": ("Blocked: the target mode already contains data.", "已阻止：目标模式已有数据。"),
    "md.sourceEmpty": ("The selected mode has no data.", "所选模式没有数据。"),
    "md.sameMode": ("Source and target must be different modes.", "来源与目标必须是不同模式。"),
    "md.applyCopy": ("Copy mode data to memory", "复制模式数据到内存"),
    "md.applyClear": ("Clear mode data in memory", "在内存中清除模式数据"),
    "md.applied": ("Mode operation applied; save separately to write it.", "模式操作已应用；需另行保存写入。"),

    # ── 保存 ─────────────────────────────────────────────────────
    "sv.title": ("Review & save", "校验与保存"),
    "sv.sub": ("The only place that writes to disk. Blocking errors disable the button.", "唯一会写磁盘的地方。存在阻断性错误时按钮不可用。"),
    "sv.blocking": ("Blocking errors", "阻断性错误"),
    "sv.warnings": ("Warnings", "警告"),
    "sv.changes": ("Changes", "本次变更"),
    "sv.summary": ("+{add} added · ~{mod} modified · −{rem} removed", "+{add} 新增 · ~{mod} 修改 · −{rem} 删除"),
    "sv.issues": ("Issues that must be fixed", "必须修复的问题"),
    "sv.noIssues": ("No blocking errors.", "没有阻断性错误。"),
    "sv.diff": ("Change list", "变更清单"),
    "sv.noChanges": ("The save is unchanged since it was loaded.", "自载入以来没有任何改动。"),
    "sv.confirm1": ("The game is closed", "我已关闭游戏"),
    "sv.confirm1D": ("The running game holds the save in memory and overwrites the file on exit.", "游戏运行时会持有内存字典，退出时整体覆盖文件。"),
    "sv.confirm2": ("I understand a backup will be created", "我确认会自动备份"),
    "sv.confirm2D": ("A copy named {stem}.bak_<timestamp> is written next to the save, keeping the newest {keep}.", "将在存档旁生成 {stem}.bak_<时间戳>，最多保留最新 {keep} 份。"),
    "sv.confirm3": ("I will reload the character afterwards", "我会重新载入存档"),
    "sv.confirm3D": ("Returning to the title screen and entering the character again is enough.", "回到标题界面再进入角色即可。"),
    "sv.write": ("Write to disk", "写入存档"),
    "sv.blocked": ("Blocked by {n} error(s)", "因 {n} 条错误暂停写入"),
    "sv.needConfirm": ("Tick the three boxes to enable writing", "勾选三项后即可写入"),
    "sv.achieveWarn": ("{n} warning(s) acknowledged", "已确认 {n} 条警告"),
    "sv.ackWarn": ("I have read the {n} warning(s)", "我已查看这 {n} 条警告"),
    "sv.done": ("Saved.", "已保存。"),
    "sv.doneMsg": ("Wrote {size} bytes to {path}", "已写入 {size} 字节到 {path}"),
    "sv.backup": ("Backup: {path}", "备份：{path}"),
    "sv.identical": ("Content is byte-identical to the file on disk — nothing meaningful changed.", "内容与磁盘上的文件逐字节相同，实际上没有改动。"),
    "sv.export": ("Download a copy", "下载副本"),
    "sv.revertAll": ("Discard all changes", "放弃全部改动"),
    "sv.reverted": ("All changes discarded", "已放弃全部改动"),
    "sv.failed": ("Write failed at stage «{stage}»: {msg}", "写入失败（阶段：{stage}）：{msg}"),
    "sv.readonly": ("Edit mode is off — nothing to save.", "编辑模式关闭，没有可保存的内容。"),
    "sv.backups": ("Backups", "备份"),
    "sv.backupNone": ("No backup yet — one is created on the first write.", "还没有备份，首次写入时会自动生成。"),
    "sv.restore": ("Restore", "还原"),
    "sv.restoreWarn": ("Replacing the save with an older backup is irreversible", "用旧备份覆盖当前存档不可撤销"),
    "sv.restored": ("Restored {name}", "已还原 {name}"),

    # ── 校验消息 ─────────────────────────────────────────────────
    "val.E_DUP": ("Duplicate key; the game keeps the last one", "键重复出现，游戏只会保留最后一个"),
    "val.E_TYPE": ("Holds {actual} but the game reads it as {expected}", "实际是 {actual}，游戏按 {expected} 读取"),
    "val.E_FLOAT_SPECIAL": ("Not a finite float ({value})", "不是有限浮点数（{value}）"),
    "val.E_INT_RANGE": ("{value} is outside the 32-bit integer range", "{value} 超出 32 位整数范围"),
    "val.W_RANGE_LOW": ("{value} is below the minimum {min}", "{value} 小于下限 {min}"),
    "val.W_RANGE_HIGH": ("{value} is above the maximum {max}", "{value} 大于上限 {max}"),
    "val.W_LEVEL_RANGE": ("Level {value} is outside 0–{max}", "等级 {value} 超出 0–{max}"),
    "val.W_EXP_RANGE": ("Experience {value} is outside 0–{cap} for level {level}", "经验 {value} 超出 {level} 级的 0–{cap}"),
    "val.W_POINTS_OVER": ("Unspent points {value} exceed the total {total}", "未分配点数 {value} 超过总量 {total}"),
    "val.W_POINTS_MISMATCH": ("Attributes account for {invested} points but the save says {expected} were spent (gap {diff})",
                              "属性反算投入 {invested} 点，存档账面已花 {expected} 点（差 {diff}）"),
    "val.W_ATTR_NEG": ("Attribute cap is negative ({value}); default is {default}", "属性上限为负（{value}），默认 {default}"),
    "val.W_CUR_GT_MAX": ("{cur} is above {max_key} ({max})", "{cur} 超过 {max_key}（{max}）"),
    "val.W_ORPHAN_SLOT": ("Slot {prefix}[{index}] has no {missing} key", "槽位 {prefix}[{index}] 缺少 {missing} 键"),
    "val.W_SLOT_STATE": ("Slot {prefix}[{index}] reads as empty (name={name}, count={count})", "槽位 {prefix}[{index}] 读出来是空的（name={name}，count={count}）"),
    "val.W_USHORT": ("{field} = {value} exceeds 65535 and will be truncated", "{field} = {value} 超过 65535，会被截断"),
    "val.W_SLOT_INDEX": ("Index {index} is beyond the {capacity} slots of {prefix}", "索引 {index} 超出 {prefix} 的 {capacity} 格"),
    "val.W_HAND": ("{value} points at an empty or out-of-range slot", "{value} 指向空槽或越界槽位"),
    "val.W_NAME_EMPTY": ("Character name is empty", "角色名为空"),
    "val.W_NAME_MISMATCH": ("Character is '{in_file}' but the file is '{file_name}'", "角色名为 '{in_file}'，文件名却是 '{file_name}'"),
    "val.W_DATE": ("'{value}' is not a valid ISO 8601 timestamp", "'{value}' 不是合法的 ISO 8601 时间"),
    "val.W_QUEST_STEP": ("Step '{step}' is not defined for quest {title}; the game will restart that quest", "任务 {title} 未定义步骤 '{step}'；游戏会重新开始该任务"),
    "val.I_QUEST_CUSTOM": ("Quest {title} is not in the installed catalog; it may be custom or removed", "任务 {title} 不在本机目录中，可能是自定义任务或已移除内容"),
    "val.I_QUESTLINE_EXTRA": ("{count} keys from the other questline ({other}) are present; the game does not load them", "存在另一任务线（{other}）的 {count} 个键，游戏不会加载它们"),
    "val.I_PROGRESS_CUSTOM": ("Counter belongs to {title}, which is not in the installed catalog", "计数属于 {title}，该任务不在本机目录中"),
    "val.I_PROGRESS_STEP": ("Counter references undefined step {step} of {title}", "计数指向 {title} 中未定义的步骤 {step}"),
    "val.I_PROGRESS_TARGET": ("Counter does not match any current target of {title}", "计数与 {title} 当前版本的目标不匹配"),
    "val.W_UNKNOWN": ("Unrecognised key — kept as-is, not type-checked", "未识别的键，原样保留、不做类型校验"),
    "val.I_NONASCII": ("Key contains non-ASCII characters; it will be written as \\uXXXX escapes",
                       "键名含非 ASCII 字符，写入时会转义成 \\uXXXX"),
    "val.E_TYPE_HINT_INT": ("Integers must be written without a decimal point", "整数不能带小数点"),
    "val.E_TYPE_HINT_FLOAT": ("Floats must keep a decimal point (400.0, not 400)", "浮点必须带小数点（写 400.0，不要写 400）"),
    "val.E_TYPE_HINT_STR": ("Text keys must stay quoted strings", "文本键必须是带引号的字符串"),
}


def lang() -> str:
    # 允许在 streamlit 之外（单测、命令行）调用
    try:
        return st.session_state.get("lang", DEFAULT_LANG)
    except Exception:  # noqa: BLE001 - 没有脚本上下文时退回默认语言
        return DEFAULT_LANG


def load_saved_language() -> str:
    """读取界面语言偏好；旧版本存在 .venv 里的设置仍兼容。"""
    for path in (SETTINGS_FILE, LEGACY_SETTINGS_FILE):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            value = payload.get("lang", "")
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if value in LANGS:
            return value
    return DEFAULT_LANG


def save_language(value: str) -> None:
    """原子写入界面偏好；只读环境下静默保留当前会话设置。"""
    value = value if value in LANGS else DEFAULT_LANG
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"lang": value}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, SETTINGS_FILE)
    except OSError:
        pass


def set_lang(value: str, *, persist: bool = False) -> None:
    value = value if value in LANGS else DEFAULT_LANG
    st.session_state["lang"] = value
    if persist:
        save_language(value)


def t(key: str, **kw) -> str:
    pair = S.get(key)
    if pair is None:
        return key
    current = lang()
    if current in {"en", "zh"}:
        text = pair[0 if current == "en" else 1]
    else:
        from locales import es, pt, ru
        text = {"ru": ru.STRINGS, "pt": pt.STRINGS, "es": es.STRINGS}[current].get(key) or pair[0]
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError):
            return text
    return text


def cat(category: str) -> str:
    return t(f"cat.{category}")


def group(group_id: str) -> str:
    return t(f"group.{group_id}")


def kind(kind_id: str) -> str:
    return t(f"kind.{kind_id}")


def issue_text(code: str, params: dict) -> str:
    return t(f"val.{code}", **_clean(params))


def _clean(params: dict) -> dict:
    out = {}
    for key, value in params.items():
        if isinstance(value, float):
            out[key] = f"{value:g}"
        elif isinstance(value, bool):
            out[key] = t("c.yes") if value else t("c.no")
        else:
            out[key] = value
    return out


def missing_keys() -> list[str]:
    """测试用：所有已公开语言都必须覆盖全部界面键。"""
    missing = [k for k, v in S.items() if len(v) != 2 or not v[1]]
    from locales import es, pt, ru
    for code, strings in (("ru", ru.STRINGS), ("pt", pt.STRINGS), ("es", es.STRINGS)):
        missing.extend(f"{code}:{key}" for key in S if not strings.get(key))
        missing.extend(f"{code}:extra:{key}" for key in strings.keys() - S.keys())
    return missing
