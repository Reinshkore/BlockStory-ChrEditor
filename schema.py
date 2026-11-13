"""键语法知识库。

存档不是固定 schema：键名由游戏代码拼接（`"Max " + gameObject.name`、
`storageName + "_name_" + slot`、`petName + " MaxHealth"`），所以这里全是**规则**，
不是键表。固定表只用来标注中文名、默认值与取值范围。

本模块不依赖 streamlit，可单独测试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# 分类
# --------------------------------------------------------------------------- #

# (分类 id, 所属大组 id)
CATEGORIES: list[tuple[str, str]] = [
    ("identity", "character"),
    ("growth", "character"),
    ("attr_max", "attribute"),
    ("status", "attribute"),
    ("inventory", "bag"),
    ("quickslot", "bag"),
    ("equipment", "bag"),
    ("container", "container"),
    ("pet_bag", "pet"),
    ("pet_equip", "pet"),
    ("pet_stat", "pet"),
    ("pet_meta", "pet"),
    ("quest", "quest"),
    ("achieve", "progress"),
    ("recipe", "progress"),
    ("misc", "misc"),
]

CATEGORY_IDS: list[str] = [c for c, _ in CATEGORIES]
CATEGORY_GROUP: dict[str, str] = dict(CATEGORIES)
CATEGORY_ORDER: dict[str, int] = {c: i for i, (c, _) in enumerate(CATEGORIES)}

GROUPS: list[str] = ["character", "attribute", "bag", "container", "pet", "quest", "progress", "misc"]

GROUP_NAMES: dict[str, tuple[str, str]] = {  # (en, zh)
    "character": ("Character", "角色"),
    "attribute": ("Attributes", "属性"),
    "bag": ("Inventory", "背包"),
    "container": ("Containers", "容器"),
    "pet": ("Pets", "宠物"),
    "quest": ("Quests", "任务"),
    "progress": ("Achievements & Recipes", "成就与配方"),
    "misc": ("Misc", "杂项"),
}

WORLD_MODES = ("story", "survival", "creative", "hardcore", "sandbox")
WORLD_MODE_SUFFIX = {
    "survival": "_survival", "creative": "_creative",
    "hardcore": "_hardcore", "sandbox": "_sandbox",
}

#: 任务线：Questline 枚举，0 = 当前，1 = 旧（游戏 9 版本以前的任务）。
QUEST_LINE_KEY = "Questline"
QUEST_LINES = ("current", "old")
QUEST_LINE_SUFFIX = {"current": "", "old": "Old "}


def quest_line(value: Any) -> str:
    """把存档里的 Questline 值规范成 "current" / "old"；非法值按游戏默认处理。"""
    return "old" if value == 1 else "current"


def quest_prefix(line: str) -> str:
    return QUEST_LINE_SUFFIX.get(line, "")


def quest_key(line: str, kind: str, title: str) -> str:
    """kind: quest / complete / daily / recipe。"""
    base = {"quest": "Quest: ", "complete": "Quest Complete: ",
            "daily": "Daily: ", "recipe": "Recipe: "}[kind]
    return quest_prefix(line) + base + title


def world_mode_of(key: str) -> str:
    for mode, suffix in WORLD_MODE_SUFFIX.items():
        if key.endswith(suffix):
            return mode
    return "story"


def world_mode_key(key: str, source: str, target: str) -> str:
    """把某个模式的键名转换到另一模式；调用方需先排除身份/共享键。"""
    suffix = WORLD_MODE_SUFFIX.get(source, "")
    base = key[:-len(suffix)] if suffix and key.endswith(suffix) else key
    return base + WORLD_MODE_SUFFIX.get(target, "")


def mode_base_key(key: str) -> str:
    """剥去模式后缀，用原键规则确定类型、分类与宠物归属。"""
    return world_mode_key(key, world_mode_of(key), "story")


CATEGORY_NAMES: dict[str, tuple[str, str]] = {
    "identity": ("Identity", "身份"),
    "growth": ("Progress & Skill Points", "成长与技能点"),
    "attr_max": ("Attribute Caps", "属性上限"),
    "status": ("Current State", "当前状态"),
    "inventory": ("Backpack", "背包"),
    "quickslot": ("Quick Slots", "快捷栏"),
    "equipment": ("Equipment", "装备栏"),
    "container": ("Placed Containers", "放置容器"),
    "pet_bag": ("Pet Bags", "宠物背包"),
    "pet_equip": ("Pet Equipment", "宠物装备"),
    "pet_stat": ("Pet Stats", "宠物属性"),
    "pet_meta": ("Pet Profiles", "宠物档案"),
    "quest": ("Quests", "任务"),
    "achieve": ("Achievements", "成就"),
    "recipe": ("Recipes", "配方"),
    "misc": ("Misc", "杂项"),
}

# --------------------------------------------------------------------------- #
# 属性表（顺序 = 游戏 ResetSkills 的赋值顺序）
# --------------------------------------------------------------------------- #

MAX_LEVEL = 199


@dataclass(frozen=True)
class Attribute:
    key: str
    default: float
    step: float          # 每点加成的数值（负数表示越低越好）
    label_en: str
    label_zh: str


#: 12 项可加点属性；`reset_attributes` 按此顺序重置
POINT_ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute("Max Health", 100.0, 10.0, "Health cap", "生命上限"),
    Attribute("Max Mana", 100.0, 10.0, "Mana cap", "法力上限"),
    Attribute("Max Breath", 30.0, 5.0, "Breath cap", "憋气上限"),
    Attribute("Max Sword Damage", 0.0, 1.0, "Sword damage", "剑伤害"),
    Attribute("Max Magic Damage", 0.0, 1.0, "Magic damage", "法术伤害"),
    Attribute("Max Bow Force", 0.0, 10.0, "Bow force", "弓力"),
    Attribute("Max Bow Damage", 0.0, 1.0, "Arrow damage", "箭伤害"),
    Attribute("Max Gun Damage", 0.0, 1.0, "Gun damage", "枪伤害"),
    Attribute("Max Loot Distance", 0.0, 0.1, "Loot range", "拾取范围"),
    Attribute("Max Walk Speed", 0.0, 0.05, "Walk speed", "行走速度"),
    Attribute("Max Fly Speed", 0.0, 0.1, "Fly speed", "飞行速度"),
    Attribute("Max Dig Speed", 1.0, -0.01, "Dig time", "挖掘耗时"),
)

ATTR_BY_KEY: dict[str, Attribute] = {a.key: a for a in POINT_ATTRIBUTES}

#: 不参与加点、由装备或天赋驱动的上限类键：(键, 参考默认值)
OTHER_MAX: tuple[tuple[str, float], ...] = (
    ("Max Health Regen", 0.0),
    ("Max Mana Regen", 0.0),
    ("Max Breath Regen", 0.0),
    ("Max Armor", 0.0),
    ("Max Hunger", 100.0),
    ("Max Hunger Regen", -0.05),
)

#: 浮点键里允许为负的（其余为负会告警）
NEGATIVE_OK = {"Max Hunger Regen"}

# --------------------------------------------------------------------------- #
# 单键规格
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FieldSpec:
    cat: str
    kind: str                      # "int" | "float" | "str"
    label_en: str
    label_zh: str
    default: Any = None
    vmin: float | None = None
    vmax: float | None = None
    note_en: str = ""
    note_zh: str = ""
    #: 是否为核心键（概览页/校验重点）
    core: bool = False


def _spec(cat: str, kind: str, en: str, zh: str,
          default: Any = None, vmin: float | None = None, vmax: float | None = None,
          *, note_en: str = "", note_zh: str = "", core: bool = False) -> FieldSpec:
    return FieldSpec(cat=cat, kind=kind, label_en=en, label_zh=zh, default=default,
                     vmin=vmin, vmax=vmax, note_en=note_en, note_zh=note_zh, core=core)


#: 固定键表
FIXED: dict[str, FieldSpec] = {
    "charName": _spec("identity", "str", "Character name", "角色名", core=True,
                      note_en="Overrides the file name on load", note_zh="读档时以这里的值为准，会覆盖文件名"),
    "charGender": _spec("identity", "str", "Gender", "性别", default="Male", core=True,
                        note_en="Male / Female", note_zh="Male / Female"),
    "Questline": _spec("identity", "int", "Questline", "任务线编号", 0, 0, 1,
                       note_en="0 = current questline, 1 = old (pre-9) questline",
                       note_zh="0 = 当前任务线，1 = 旧任务线（游戏 9 版本以前）"),

    "Current Level": _spec("growth", "int", "Level", "等级", 0, 0, MAX_LEVEL, core=True,
                           note_en="0–199; values above are clamped on level-up",
                           note_zh="0–199，超出会被夹回"),
    "Current Experience": _spec("growth", "int", "Experience", "经验", 0, 0, None, core=True,
                                note_en="XP inside the current level; resets on level-up",
                                note_zh="当前等级内的经验，升级时递减"),
    "Skill Points": _spec("growth", "int", "Unspent skill points", "未分配技能点", 5, 0, None, core=True,
                          note_en="Total = 5 + level-up awards + purchased; a skill reset uses a higher legacy formula",
                          note_zh="总量 = 5 + 升级发放 + 已购；技能重置按另一套更高公式结算"),
    "Purchased Skill Points": _spec("growth", "int", "Purchased skill points", "已购技能点", 0, 0, None, core=True,
                                    note_en="Only key shared across world modes",
                                    note_zh="唯一跨世界模式共享的键"),

    "Current Health": _spec("status", "float", "Current health", "当前生命", 100.0, core=True),
    "Current Mana": _spec("status", "float", "Current mana", "当前法力", 100.0, core=True),
    "Current Breath": _spec("status", "float", "Current breath", "当前憋气", 30.0, core=True),
    "Current Hunger": _spec("status", "float", "Current hunger", "当前饥饿", 100.0, core=True),

    "InventoryUnlocked": _spec("misc", "int", "Unlocked backpack slots", "已解锁背包格", 0, 0, 64,
                               note_en="Takes precedence over the level-based count",
                               note_zh="存在时优先于按等级推算的格数"),
    "InventoryUpdate": _spec("misc", "int", "Item migration flag", "物品迁移标记", 0),
    "JustStarted": _spec("misc", "int", "First-run flag", "首次进入标记", 0),
    "Has Killed Dragon Lord?": _spec("misc", "str", "Dragon Lord defeated", "是否击杀龙王", ""),
    "Sandbox Hardmode Switch?": _spec("misc", "str", "Sandbox hard mode", "沙盒硬核模式", "no",
                                      note_en="yes / no; sandbox mode only",
                                      note_zh="yes / no，仅沙盒模式"),
    "RightHand": _spec("misc", "int", "Right hand slot", "右手槽位", -1, -1, 63,
                       note_en="Absolute slot index, -1 = empty", note_zh="绝对槽位号，-1 表示空手"),
    "LeftHand": _spec("misc", "int", "Left hand slot", "左手槽位", -1, -1, 63,
                      note_en="Absolute slot index, -1 = empty", note_zh="绝对槽位号，-1 表示空手"),
    "Distance Travelled": _spec("misc", "int", "Distance travelled", "行走距离", 0, 0),
    "Distance Travelled In Vehicle": _spec("misc", "int", "Distance in vehicle", "载具距离", 0, 0),
    "Distance Travelled Mounted": _spec("misc", "int", "Distance mounted", "骑乘距离", 0, 0),
}

# --------------------------------------------------------------------------- #
# 键形规则
# --------------------------------------------------------------------------- #

SLOT_RE = re.compile(
    r"^(?P<pre>.*?)_(?P<kind>name|count|data|paint)_(?P<idx>\d+)"
    r"(?P<mode>_survival|_creative|_hardcore|_sandbox)?$")
PET_STAT_RE = re.compile(r"^(?P<pet>.+?)\(Clone\) (?P<stat>.+)$")
PET_META_RE = re.compile(r"^(?P<pet>.+?)(?P<tail>Unlocked|_Name|_Rename|Summoner)$")
ACHIEVE_PROG_RE = re.compile(r"^(?P<title>.+?) (?P<kind>kill|break|collect|daily)(?: (?P<target>.*))?$")
QUEST_PROG_RE = re.compile(
    r"^(?P<title>.+?) (?P<step>\S+) (?:kill \d+|[^ \t\r\n]+ consume .+|placed \d+(?: \d+)?)$")

#: 玩家/宠物的固定储物前缀
FIXED_STORES = {"Inventory": "inventory", "QuickSlot": "quickslot", "Equipment": "equipment"}

#: 常见宠物名（仅用于标签与提示；实际以存档中出现的前缀为准）
KNOWN_PETS: tuple[str, ...] = (
    "Arachy", "BabyAshkore", "Daithir", "Drako", "Eldriar", "Gontar", "Mati",
    "Mech", "Onyx", "Perseus", "RainbowBasilisk", "Slinki", "Snowman",
    "Vairmut", "Xordaraxus",
)

PET_STATS: dict[str, tuple[str, str, str]] = {
    # stat 后缀: (kind, en, zh)
    "Current Level": ("int", "Pet level", "宠物等级"),
    "Current Experience": ("int", "Pet experience", "宠物经验"),
    "MaxHealth": ("float", "Max health", "生命上限"),
    "CurHealth": ("float", "Current health", "当前生命"),
    "Attack": ("float", "Attack", "攻击力"),
    "Fireball": ("float", "Fireball damage", "火球伤害"),
    "Hunger": ("float", "Hunger", "饥饿"),
    "LastRegen": ("float", "Last regen timestamp", "上次回复时间"),
}

#: 储物槽位容量（用于越界检查）
STORAGE_CAPACITY: dict[str, int] = {"inventory": 64, "quickslot": 10, "equipment": 9, "pet": 16}


def detect_pets(keys: Iterable[str]) -> set[str]:
    """从键集合里推断存在哪些宠物（宠物名由预制体名拼接，无法写死）。"""
    pets: set[str] = set()
    for original in keys:
        key = mode_base_key(original)
        m = PET_STAT_RE.match(key)
        if m:
            pets.add(m.group("pet"))
            continue
        m = PET_META_RE.match(key)
        if m:
            name = m.group("pet")
            if name and name not in FIXED_STORES:
                pets.add(name)
    pets.discard("")
    return pets


def detect_containers(keys: Iterable[str], pets: Iterable[str]) -> list[str]:
    """非固定储物、非宠物背包的容器前缀（放置容器、坐标容器、空前缀）。"""
    pet_set = set(pets)
    out: set[str] = set()
    for key in keys:
        m = SLOT_RE.match(key)
        if not m:
            continue
        pre = m.group("pre")
        if pre in FIXED_STORES or pre in pet_set:
            continue
        if pre.endswith("_Equipment") and pre[: -len("_Equipment")] in pet_set:
            continue
        out.add(pre)
    return sorted(out)


def classify(key: str, pets: Iterable[str] = ()) -> str:
    """把一个键归入 16 个分类之一。规则顺序即优先级。"""
    key = mode_base_key(key)
    pet_set = set(pets)
    if key in FIXED:
        return FIXED[key].cat

    if key in ATTR_BY_KEY or key in dict(OTHER_MAX):
        return "attr_max"

    if key.startswith(("Quest Complete:", "Old Quest Complete:")):
        return "quest"
    if key.startswith(("Quest:", "Old Quest:")):
        return "quest"
    if key.startswith(("Daily:", "Old Daily:")):
        return "quest"
    if key.startswith("Achieve:"):
        return "achieve"
    if key.startswith(("Recipe:", "Old Recipe:")):
        return "recipe"

    m = SLOT_RE.match(key)
    if m:
        pre = m.group("pre")
        if pre in FIXED_STORES:
            return FIXED_STORES[pre]
        if pre in pet_set:
            return "pet_bag"
        if pre.endswith("_Equipment") and pre[: -len("_Equipment")] in pet_set:
            return "pet_equip"
        return "container"

    m = PET_STAT_RE.match(key)
    if m:
        return "pet_stat"

    m = PET_META_RE.match(key)
    if m:
        return "pet_meta"

    if key.startswith("Current "):
        return "status"
    if key.startswith("Max "):
        return "attr_max"

    return "misc"


def family_of(key: str) -> str:
    """同族键的族名：槽位键归到 `<前缀>_<字段>_*`，其余为键本身。"""
    m = SLOT_RE.match(key)
    if m:
        return f"{m.group('pre')}_*_{m.group('kind')}"
    return key


def slot_family(key: str) -> tuple[str, str, int] | None:
    """拆出槽位键的 (容器前缀, 字段, 索引)；不是槽位键返回 None。"""
    m = SLOT_RE.match(key)
    if not m:
        return None
    return m.group("pre") + (m.group("mode") or ""), m.group("kind"), int(m.group("idx"))


def spec_for(key: str, pets: Iterable[str] = ()) -> FieldSpec | None:
    """给出单键的规格（类型、标签、默认值、范围）。规则族动态生成。"""
    pet_set = set(pets)
    cat = classify(key, pet_set)
    key = mode_base_key(key)

    if key in FIXED:
        return FIXED[key]

    if key in ATTR_BY_KEY:
        a = ATTR_BY_KEY[key]
        return FieldSpec(
            cat="attr_max", kind="float", label_en=a.label_en, label_zh=a.label_zh,
            default=a.default, core=True,
            note_en=f"default {a.default:g}, {a.step:+g} per point",
            note_zh=f"默认 {a.default:g} · 每点 {a.step:+g}",
        )

    other = dict(OTHER_MAX)
    if key in other:
        return FieldSpec(cat="attr_max", kind="float", label_en=key[4:], label_zh=key[4:],
                         default=other[key],
                         note_en="driven by gear/talents, not by skill points",
                         note_zh="由装备/天赋驱动，不吃加点")

    # 槽位族
    parts = slot_family(key)
    if parts:
        _, fld, _ = parts
        labels = {
            "name": ("Item name", "物品名称"),
            "count": ("Count", "数量"),
            "data": ("Data", "data 值"),
            "paint": ("Paint", "paint 值"),
        }
        env, zhv = labels[fld]
        if fld == "name":
            return FieldSpec(cat=cat, kind="str", label_en=env, label_zh=zhv, default="")
        if fld == "count":
            return FieldSpec(cat=cat, kind="int", label_en=env, label_zh=zhv, default=0, vmin=0)
        return FieldSpec(cat=cat, kind="int", label_en=env, label_zh=zhv, default=0,
                         vmin=0, vmax=65535,
                         note_en="ushort, truncated above 65535",
                         note_zh="ushort，超过 65535 会被截断")

    # 宠物属性
    m = PET_STAT_RE.match(key)
    if m:
        stat = m.group("stat")
        kind, en, zh = PET_STATS.get(stat, ("float", stat, stat))
        return FieldSpec(cat="pet_stat", kind=kind, label_en=en, label_zh=zh)

    # 宠物档案
    m = PET_META_RE.match(key)
    if m:
        tail = m.group("tail")
        if tail == "Unlocked":
            return FieldSpec(cat="pet_meta", kind="int", label_en="Unlocked slots",
                             label_zh="已解锁格数", default=0, vmin=0, vmax=16)
        if tail == "_Name":
            return FieldSpec(cat="pet_meta", kind="str", label_en="Pet name",
                             label_zh="宠物名", default="")
        if tail == "_Rename":
            return FieldSpec(cat="pet_meta", kind="int", label_en="Rename flag",
                             label_zh="改名标记", default=0)
        return FieldSpec(cat="pet_meta", kind="str", label_en="Summoned at",
                         label_zh="召唤时间", default="")

    # 任务 / 成就 / 配方
    if key.startswith(("Quest Complete:", "Old Quest Complete:")):
        return FieldSpec(cat="quest", kind="int", label_en="Times completed",
                         label_zh="完成次数", default=0, vmin=0)
    if key.startswith(("Quest:", "Old Quest:")):
        rest = key.split("Quest: ", 1)[-1]
        if QUEST_PROG_RE.match(key):
            return FieldSpec(cat="quest", kind="int", label_en="Step progress",
                             label_zh="步骤进度", default=0, vmin=0)
        del rest
        return FieldSpec(cat="quest", kind="str", label_en="Current step",
                         label_zh="当前步骤", default="#start",
                         note_en="#start = not started, #end = finished",
                         note_zh="#start 未开始，#end 已完成")
    if key.startswith(("Daily:", "Old Daily:")):
        return FieldSpec(cat="quest", kind="str", label_en="Daily reset time",
                         label_zh="日常重置时间", default="",
                         note_en="ISO 8601 timestamp", note_zh="ISO 8601 时间戳")
    if key.startswith("Achieve:"):
        if ACHIEVE_PROG_RE.match(key) and not key.endswith(":"):
            return FieldSpec(cat="achieve", kind="int", label_en="Progress",
                             label_zh="进度", default=0, vmin=0)
        return FieldSpec(cat="achieve", kind="int", label_en="Claimed",
                         label_zh="已领取", default=0, vmin=0, vmax=1)
    if key.startswith(("Recipe:", "Old Recipe:")):
        return FieldSpec(cat="recipe", kind="int", label_en="Unlocked",
                         label_zh="已解锁", default=0, vmin=0, vmax=1,
                         note_en="Old questline stores unlocks under 'Old Recipe: '",
                         note_zh="旧任务线的解锁键是 'Old Recipe: '")

    return None


def kind_for(key: str, pets: Iterable[str] = ()) -> str | None:
    spec = spec_for(key, pets)
    return spec.kind if spec else None


# --------------------------------------------------------------------------- #
# 数值语义
# --------------------------------------------------------------------------- #

def earned_skill_points(level: int, purchased: int, max_level: int = MAX_LEVEL) -> int:
    """自然升级实际发放的技能点总量。

    复刻 Experience.AddjustCurrentExperience：每升一级按“升级前等级”发放，
    在 10/30/60/100 级换档。它与 StatsCollector.CalculateSkillPoints 并不一致，
    后者只在“技能重置”时使用，且 30 级以后会算得更多。
    """
    total = 5
    level = max(0, min(int(level), max_level))
    for old in range(level):
        if old < 10:
            total += 1
        elif old < 30:
            total += 2
        elif old < 60:
            total += 3
        elif old < 100:
            total += 2
        elif old < max_level - 1:
            total += 1
        elif old < max_level:
            total += 20
    return total + int(purchased)


def reset_skill_points(level: int, purchased: int, max_level: int = MAX_LEVEL) -> int:
    """技能重置后的理论总额（StatsCollector.CalculateSkillPoints）。

    ResetSkillsPurchase 会把未分配点数直接设为该值，因此重置过的存档可以合法
    高于自然升级总量。校验时两种总额都要接受。
    """
    total = 5
    level = max(0, min(int(level), max_level))
    for i in range(1, level + 1):
        if i <= 10:
            total += 1
        elif i <= 29:
            total += 2
        elif i <= max_level - 1:
            total += 3
        elif i <= max_level:
            total += 20
    return total + int(purchased)


def max_exp_for_level(level: int) -> int:
    """复刻 Experience.CalculateMaxExp（含 Mathf.RoundToInt 的银行家舍入）。"""
    base = 40.0
    lv = max(0, int(level))
    a = 1.05 ** min(lv, 10)
    b = 1.1 ** (19 if lv >= 29 else max(0, lv - 10))
    c = 1.12 ** ((18 + lv * 0.2) if lv >= 59 else float(max(0, lv - 29)))
    return int(round(base * a * b * c))


def invested_points(values: dict[str, Any]) -> tuple[float, dict[str, float]]:
    """由 12 项属性上限反算已投入点数（装备与天赋只改运行时值，不写回存档）。"""
    per: dict[str, float] = {}
    total = 0.0
    for attr in POINT_ATTRIBUTES:
        raw = values.get(attr.key)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            per[attr.key] = 0.0
            continue
        if raw != raw or raw in (float("inf"), float("-inf")):
            per[attr.key] = 0.0   # NaN/Inf 交给校验报错，这里不参与反算
            continue
        pts = (float(raw) - attr.default) / attr.step
        pts = round(pts)
        if pts < 0:
            pts = 0.0
        per[attr.key] = float(pts)
        total += pts
    return total, per


#: 固定键的展示顺序（按语义排列，便于阅读）
FIXED_ORDER: dict[str, int] = {key: i for i, key in enumerate(FIXED)}
#: 属性按游戏里的加点顺序展示，其余上限键排在后面
ATTR_ORDER: dict[str, int] = {
    **{a.key: i for i, a in enumerate(POINT_ATTRIBUTES)},
    **{k: 100 + i for i, (k, _) in enumerate(OTHER_MAX)},
}


def natural_key(text: str) -> list:
    """自然排序键：`Inventory_2` 排在 `Inventory_10` 之前。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def sort_rank(key: str, pets: Iterable[str] = ()) -> tuple:
    cat = classify(key, pets)
    parts = slot_family(key)
    if parts:
        pre, fld, idx = parts
        field_rank = {"name": 0, "count": 1, "data": 2, "paint": 3}.get(fld, 9)
        return (CATEGORY_ORDER.get(cat, 99), pre.lower(), idx, field_rank, key)
    rank = FIXED_ORDER.get(key, ATTR_ORDER.get(key, 9000))
    return (CATEGORY_ORDER.get(cat, 99), rank, -1, natural_key(key), key)
