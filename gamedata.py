"""从本机游戏文件派生物品、生物与任务目录。

只读取用户已经安装的 Block Story；缓存中仅保留 ID、译名和任务结构摘要，
不导出贴图、音频、任务正文等原始资产。游戏更新后按文件大小/mtime 自动重建。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache"
CACHE_FILE = CACHE_DIR / "game_catalog_v4.json"
SOURCE_FILES = ("resources.assets", "sharedassets0.assets", "sharedassets2.assets", "level2")

# 游戏目录来源，优先级：BS_GAME_DATA_DIR 环境变量 > Steam 库自动探测。
GAME_DATA_ENV = "BS_GAME_DATA_DIR"
_STEAM_ROOTS: tuple[Path, ...] = tuple(
    Path(f"{drive}/{folder}")
    for drive in ("C:", "D:", "E:", "F:", "G:")
    for folder in ("Program Files (x86)/Steam", "Program Files/Steam",
                   "Steam", "SteamLibrary", "Games/Steam")
) + (
    Path.home() / ".steam" / "steam",
    Path.home() / ".local" / "share" / "Steam",
    Path("/Applications/Steam.app/Contents/Resources"),
)

# Blocksters.Terrain.chunk.MOBTypes : byte，顺序就是存档 data 数值。
MOB_TYPES: tuple[str, ...] = (
    "BabyHorseOld", "HorseOld", "SmallWorm", "MediumWorm", "BigWorm", "Striker",
    "SkeletonNormal", "SkeletonFresh", "SkeletonDark", "SkeletonMage", "SmallHugo",
    "BigHugo", "BabyGoblin", "MrGoblin", "DarkBoss", "Spider", "GiantSpider",
    "SnowWorm", "SnowBigWorm", "DarkWorm", "DarkBigWorm", "Lizard", "DuckF",
    "DuckM", "Shark", "Megalodon", "Bird", "Werewoolf", "WerewoolfBlack",
    "Jackelope", "FeralPig", "TriggerFish", "GruntFish", "ClownFish", "Dolphin",
    "LionFish", "Otter", "Squid", "Starfish", "Stingray", "Turtle", "Urchin",
    "Yeti", "Viking", "Barlog", "TRex", "Hydra", "Snake", "Dragon", "DragonBug",
    "DragonBat", "Basilisk", "Squirrel", "Eagle", "Chupacabra", "BobCat", "Pig",
    "WhiteSheep", "BlackSheep", "ColoredSheep", "IceElemental", "SourceOfLife",
    "ShadowHunter", "Warrior", "FemaleWarrior", "IceDragon", "Cow", "Bull",
    "Tiger", "Panther", "Raven", "WhiteRaven", "BearGrizzly", "BearPolar", "Bear",
    "BabyBearGrizzly", "BabyBearPolar", "BabyBear", "Chicken", "Rooster", "Deer",
    "BabyDeer", "MissDeer", "JungleBat", "SwampSnake", "GoblinWarrior",
    "ForgottenGoblin", "Ashkore", "Visitors", "Tentaclon", "PoisonDartFrog", "Shiva",
    "Wizard", "DragonLord", "Mati", "VikingShip", "AlchemistShip", "Jellyfish",
    "Manowar", "DumboOctopus", "Dunkleosteus", "Fangtooth", "Gulper", "Purplefish",
    "Tylosaurus", "Liopleurodon", "Dagi", "SwampGolem", "Phoenix", "Rucal", "Mech",
    "Bulm", "Umhi", "Dreamcat", "Screl", "Fuza", "PeasantMale", "PeasantFemale",
    "SpaceWren", "Frog", "Stormbringer", "Umbrosk", "Glaciros", "EmberTyr",
    "Seraphax", "Zerath", "Rat", "Wyvern", "OrbisFelix", "CrescentRay",
    "InfelixCentrum", "DragonWorm", "Manticore", "Orthros", "Raptor", "Triceratops",
    "LavaGolem", "SnowGolem", "MountainGolem", "FemaleKnight", "Horse", "BabyHorse",
    "CaveScorpion", "THEDRAGON", "UndeadDragon", "Wyrm", "FantasyTiger",
    "DragonTurtle", "AbyssDragon", "Scorpion", "Unicorn", "MushroomMonster",
    "Elongata", "WildSpirit", "Mantarion", "Pegasus", "Sunfish", "Ammonite",
    "LeopardSeal", "Orca", "Marlin", "Beluga", "Amberjack", "DreamWhisp",
)

SPAWNER_ITEMS = {
    "Animal Spawner", "Antique Spawner", "Monster Spawner", "Nest", "Spider Web",
    "Desert Bird Spawner", "Alien Spawner", "Bug Spawner", "Duck Spawner",
    "Realm Spawner", "Sand Spawner", "Swamp Spawner", "Spawner Green Coral",
}


@dataclass(frozen=True)
class Entry:
    id: str
    en: str
    zh: str
    category: str = ""
    spawner: bool = False
    id16: int = 0
    ru: str = ""
    pt: str = ""
    es: str = ""

    def name(self, lang: str) -> str:
        translated = {"zh": self.zh, "ru": self.ru, "pt": self.pt, "es": self.es}.get(lang, "")
        return translated or self.en or self.id

    def label(self, lang: str) -> str:
        name = self.name(lang)
        return name if name == self.id else f"{name} — {self.id}"


@dataclass(frozen=True)
class QuestTarget:
    step: str
    kind: str
    target: str
    count: int
    key: str


@dataclass(frozen=True)
class QuestDef:
    title: str
    npc: str
    daily: bool
    en: str = ""
    zh: str = ""
    daily_tiers: tuple[int, ...] = ()
    deps: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    targets: tuple[QuestTarget, ...] = ()
    recipes: tuple[str, ...] = ()
    source_order: int = 0
    ru: str = ""
    pt: str = ""
    es: str = ""
    #: "current" 或 "old"；旧任务线由 Resources/Quests/Old 加载，键名多一个 "Old " 前缀。
    line: str = "current"
    #: <store> 商店任务：以 #close 结束、不写存档，编辑器按只读处理。
    shop: bool = False


@dataclass
class Catalog:
    items: dict[str, Entry] = field(default_factory=dict)
    mobs: dict[str, Entry] = field(default_factory=dict)
    quests: dict[str, QuestDef] = field(default_factory=dict)
    #: 旧任务线任务（resources.assets 的 Quests/Old + 商店任务），与当前线同名不同源。
    old_quests: dict[str, QuestDef] = field(default_factory=dict)
    #: 当前与旧任务线的配方奖励全集：title -> recipe names。
    quest_recipes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    source: str = ""
    error: str = ""
    version: str = ""

    def for_line(self, line: str) -> dict[str, QuestDef]:
        return self.old_quests if line == "old" else self.quests

    def is_spawner(self, item_id: str) -> bool:
        entry = self.items.get(item_id)
        return entry.spawner if entry else item_id in SPAWNER_ITEMS

    def item_label(self, item_id: str, lang: str, data: int = 0) -> str:
        entry = self.items.get(item_id)
        if self.is_spawner(item_id) and data in range(len(MOB_TYPES)):
            mob_id = MOB_TYPES[data]
            mob = self.mobs.get(mob_id)
            mob_name = (mob.name(lang) if mob else mob_id) or mob_id
            template = (entry.name(lang) if entry else item_id) or item_id
            try:
                base = template.format(mob_name)
            except (ValueError, IndexError):
                base = f"{mob_name} {template}"
            return f"{base} — {item_id} · data {data}"
        return entry.label(lang) if entry else item_id

    def search_items(self, query: str, lang: str) -> list[Entry]:
        return _search(self.items.values(), query, lang)

    def search_mobs(self, query: str, lang: str) -> list[tuple[int, Entry]]:
        rows = [(i, self.mobs.get(name, Entry(name, name, name)))
                for i, name in enumerate(MOB_TYPES)]
        needle = query.strip().casefold()
        return [(i, e) for i, e in rows
                if needle in str(i) or any(needle in value.casefold() for value in
                                           (e.id, e.en, e.zh, e.ru, e.pt, e.es))]


def _search(entries: Iterable[Entry], query: str, lang: str) -> list[Entry]:
    needle = query.strip().casefold()
    rows = list(entries)
    if needle:
        rows = [e for e in rows if any(needle in value.casefold() for value in
                                       (e.id, e.en, e.zh, e.ru, e.pt, e.es))]
    return sorted(rows, key=lambda e: e.name(lang).casefold())


def _steam_roots() -> list[Path]:
    """常见 Steam 安装位置，外加 libraryfolders.vdf 里登记的其它游戏库。"""
    roots: list[Path] = list(_STEAM_ROOTS)
    for base in _STEAM_ROOTS:
        for cfg in (base / "steamapps" / "libraryfolders.vdf",
                    base / "config" / "libraryfolders.vdf"):
            try:
                text = cfg.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for raw in re.findall(r'"path"\s+"([^"]+)"', text):
                roots.append(Path(raw.replace("\\\\", "\\")))
    return roots


def game_data_dir() -> Path:
    """定位 Block Story 的 `*_Data` 目录。

    先看 BS_GAME_DATA_DIR；未设置时扫描常见 Steam 库。找不到就返回一个
    约定路径，让上层把实际查找位置显示在错误提示里。
    """
    override = os.environ.get(GAME_DATA_ENV, "").strip().strip('"')
    if override:
        return Path(override)
    for root in _steam_roots():
        candidate = root / "steamapps" / "common" / "BlockStory" / "Block Story_Data"
        if (candidate / "level2").is_file():
            return candidate
    return (_STEAM_ROOTS[0] / "steamapps" / "common" / "BlockStory"
            / "Block Story_Data")


def _fingerprint(source: Path) -> dict[str, Any]:
    """按内容而非 mtime 判断游戏更新：Steam 的批量旧时间戳不能作为版本依据。"""
    out = []
    for name in (*SOURCE_FILES, "Managed/Assembly-CSharp.dll"):
        p = source / name
        if not p.is_file():
            continue
        digest = hashlib.sha256()
        with p.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
        out.append({"name": name, "size": p.stat().st_size, "sha256": digest.hexdigest()})
    extractor = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {"parser": 9, "extractor": extractor, "files": out}


def load_catalog(refresh: bool = False) -> Catalog:
    """优先读派生缓存；只有游戏文件变化或用户刷新时才扫描 Unity 资源。"""
    source = game_data_dir()
    fingerprint = _fingerprint(source)
    if not refresh and CACHE_FILE.is_file():
        try:
            payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if payload.get("fingerprint") == fingerprint and fingerprint:
                return _from_payload(payload)
        except (OSError, ValueError, TypeError, KeyError):
            pass
    try:
        catalog = _extract(source)
    except Exception as exc:  # 资源损坏/未安装时编辑器其余功能仍可用
        return Catalog(error=f"{type(exc).__name__}: {exc}", source=str(source))
    payload = _to_payload(catalog)
    payload["fingerprint"] = fingerprint
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass
    return catalog


def _to_payload(c: Catalog) -> dict[str, Any]:
    return {
        "source": c.source,
        "version": c.version,
        "items": {k: asdict(v) for k, v in c.items.items()},
        "mobs": {k: asdict(v) for k, v in c.mobs.items()},
        "quests": {k: {**asdict(v), "deps": list(v.deps), "steps": list(v.steps),
                       "daily_tiers": list(v.daily_tiers), "recipes": list(v.recipes),
                       "targets": [asdict(x) for x in v.targets]}
                   for k, v in c.quests.items()},
        "old_quests": {k: {**asdict(v), "deps": list(v.deps), "steps": list(v.steps),
                           "daily_tiers": list(v.daily_tiers), "recipes": list(v.recipes),
                           "targets": [asdict(x) for x in v.targets]}
                       for k, v in c.old_quests.items()},
        "quest_recipes": {k: list(v) for k, v in c.quest_recipes.items()},
    }


def _quest_from_payload(v: dict[str, Any]) -> QuestDef:
    return QuestDef(title=v["title"], npc=v["npc"], daily=v["daily"],
                    en=v.get("en", ""), zh=v.get("zh", ""),
                    daily_tiers=tuple(v.get("daily_tiers", ())),
                    deps=tuple(v.get("deps", ())), steps=tuple(v.get("steps", ())),
                    targets=tuple(QuestTarget(**x) for x in v.get("targets", ())),
                    recipes=tuple(v.get("recipes", ())),
                    source_order=v.get("source_order", 0),
                    ru=v.get("ru", ""), pt=v.get("pt", ""), es=v.get("es", ""),
                    line=v.get("line", "current"), shop=v.get("shop", False))


def _from_payload(p: dict[str, Any]) -> Catalog:
    return Catalog(
        items={k: Entry(**v) for k, v in p.get("items", {}).items()},
        mobs={k: Entry(**v) for k, v in p.get("mobs", {}).items()},
        quests={k: _quest_from_payload(v) for k, v in p.get("quests", {}).items()},
        old_quests={k: _quest_from_payload(v) for k, v in p.get("old_quests", {}).items()},
        quest_recipes={k: tuple(v) for k, v in p.get("quest_recipes", {}).items()},
        source=p.get("source", ""), version=p.get("version", ""),
    )


def parse_po(text: str) -> dict[str, str]:
    """解析游戏使用的简化 PO（msgid/msgstr + 连续字符串行）。"""
    out: dict[str, str] = {}
    key: str | None = None
    value: str | None = None
    part = ""

    def quoted(raw: str) -> str:
        try:
            return json.loads(raw)
        except ValueError:
            return raw[1:-1] if raw.startswith('"') and raw.endswith('"') else raw

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            if key is not None and value is not None:
                out[key] = value
            key, value, part = quoted(line[6:].strip()), None, "key"
        elif line.startswith("msgstr "):
            value, part = quoted(line[7:].strip()), "value"
        elif line.startswith('"'):
            if part == "key" and key is not None:
                key += quoted(line)
            elif part == "value" and value is not None:
                value += quoted(line)
    if key is not None and value is not None:
        out[key] = value
    return out


def _text(asset: Any) -> str:
    raw = asset.m_Script
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "surrogateescape")
    return raw.decode("utf-8-sig", "replace")


def _language(table: dict[str, str]) -> str:
    header = table.get("", "")
    match = re.search(r"^Language:\s*([^\n]+)", header, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract(source: Path) -> Catalog:
    import UnityPy  # 延迟导入：无游戏文件时不影响其他模块

    if not (source / SOURCE_FILES[0]).is_file():
        raise FileNotFoundError(source / SOURCE_FILES[0])
    translations: dict[str, dict[str, dict[str, str]]] = {}
    quests: dict[str, QuestDef] = {}
    old_quests: dict[str, QuestDef] = {}
    quest_recipes: dict[str, tuple[str, ...]] = {}
    version = ""
    order = 0
    old_order = 0
    for filename in SOURCE_FILES:
        path = source / filename
        if not path.is_file():
            continue
        env = UnityPy.load(str(path))
        for obj in env.objects:
            if obj.type.name != "TextAsset":
                continue
            asset = obj.read()
            text = _text(asset)
            stripped = text.lstrip()
            if asset.m_Name == "Version":
                version = stripped
            if "msgid" in text[:500] and "msgstr" in text[:500]:
                table = parse_po(text)
                lang = _language(table)
                if lang in {"en", "zh_CN", "ru", "pt_BR", "es"}:
                    target = translations.setdefault(asset.m_Name, {}).setdefault(lang, {})
                    for key, value in table.items():
                        if key and value:
                            target[key] = value
            elif stripped.startswith("<quest"):
                # resources.assets 是 Resources/Quests/Old：旧任务线；sharedassets2 是内置当前线。
                line = "old" if filename == "resources.assets" else "current"
                quest = _parse_quest(stripped, old_order if line == "old" else order, line)
                if quest is None:
                    continue
                if "<store" in stripped:
                    quest = replace(quest, shop=True)
                if quest.recipes:
                    quest_recipes[quest.title] = tuple(dict.fromkeys(
                        quest_recipes.get(quest.title, ()) + quest.recipes))
                if line == "old":
                    old_quests[quest.title] = quest
                    old_order += 1
                else:
                    quests[quest.title] = quest
                    order += 1
                    if quest.shop:
                        # 游戏的 AddShopQuests 把 <store> 任务也以 "Old " 前缀加载到旧线。
                        old_quests[quest.title] = replace(
                            quest, line="old", source_order=old_order)
                        old_order += 1
    for group in (quests, old_quests):
        for title, quest in list(group.items()):
            sheet = translations.get(quest.npc, {})
            group[title] = QuestDef(
                title=quest.title, npc=quest.npc, daily=quest.daily,
                en=sheet.get("en", {}).get(title, title),
                zh=sheet.get("zh_CN", {}).get(title, ""),
                ru=sheet.get("ru", {}).get(title, ""),
                pt=sheet.get("pt_BR", {}).get(title, ""),
                es=sheet.get("es", {}).get(title, ""),
                daily_tiers=quest.daily_tiers, deps=quest.deps, steps=quest.steps,
                targets=quest.targets, recipes=quest.recipes,
                source_order=quest.source_order, line=quest.line, shop=quest.shop)
    item_defs = _extract_item_db(source)
    items: dict[str, Entry] = {}
    for item_id, definition in item_defs.items():
        names = translations.get("ItemNames", {})
        items[item_id] = Entry(
            item_id, names.get("en", {}).get(item_id, item_id),
            names.get("zh_CN", {}).get(item_id, ""),
            category=definition["category"], spawner=definition["spawner"],
            id16=definition["id16"], ru=names.get("ru", {}).get(item_id, ""),
            pt=names.get("pt_BR", {}).get(item_id, ""),
            es=names.get("es", {}).get(item_id, ""))
    mobs: dict[str, Entry] = {}
    for mob_id in MOB_TYPES:
        mob_sheets, item_sheets = translations.get("Mobs", {}), translations.get("ItemNames", {})
        def localized(code: str) -> str:
            return mob_sheets.get(code, {}).get(mob_id) or item_sheets.get(code, {}).get(mob_id) or ""
        mobs[mob_id] = Entry(mob_id, localized("en") or mob_id, localized("zh_CN"),
                             ru=localized("ru"), pt=localized("pt_BR"), es=localized("es"))
    return Catalog(items=items, mobs=mobs, quests=quests, old_quests=old_quests,
                   quest_recipes=quest_recipes, source=str(source), version=version)


def _extract_item_db(source: Path) -> dict[str, dict[str, Any]]:
    """读取 level2 里的 InvDatabase，而不是把翻译键误当作可加载物品。"""
    import UnityPy
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

    env = UnityPy.load(str(source / "level2"))
    unity_version = env.assets[0].unity_version
    generator = TypeTreeGenerator(unity_version)
    generator.load_local_dll_folder(str(source / "Managed"))
    nodes = generator.get_nodes_up("Assembly-CSharp.dll", "InvDatabase")
    categories = ("Blocks", "Items", "Weapons", "Tools", "Armor", "Animals",
                  "Plants", "Vehicles", "Hide", "Foods")
    out: dict[str, dict[str, Any]] = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            behaviour = obj.read(check_read=False)
            if behaviour.m_Script.read().m_ClassName != "InvDatabase":
                continue
            tree = obj.read_typetree(nodes)
        except (ValueError, AttributeError):
            continue
        for item in tree.get("items", []):
            name = item.get("name", "")
            if not name:
                continue
            category = item.get("category", 0)
            out[name] = {
                "id16": int(item.get("id16", 0)),
                "spawner": bool(int(item.get("options", 0)) & 0x10),
                "category": categories[category] if 0 <= category < len(categories) else str(category),
            }
    if not out:
        raise ValueError("No InvDatabase items found in level2")
    return out


def _option_actions(step: ET.Element):
    """步骤的直接动作 + option 内的动作；info/desc 等展示节点不递归。"""
    for child in step:
        if child.tag == "option":
            yield from _option_actions(child)
        elif child.tag in {"kill", "consume"}:
            yield child


def _parse_quest(text: str, order: int, line: str = "current") -> QuestDef | None:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    title = root.attrib.get("title", "").strip()
    if not title:
        return None
    prefix = "Old " if line == "old" else ""
    steps = tuple(child.attrib.get("id", "") for child in root
                  if child.tag.endswith("step") and child.attrib.get("id"))
    targets: list[QuestTarget] = []
    for step in root:
        step_id = step.attrib.get("id")
        if not step_id:
            continue
        for child in _option_actions(step):
            target = child.attrib.get("enemy") if child.tag == "kill" else child.attrib.get("target", "Player")
            if not target:
                continue
            count = _as_int(child.attrib.get("count"), 1)
            if child.tag == "kill":
                try:
                    saved_target = str(MOB_TYPES.index(target))
                except ValueError:
                    continue
                key = f"{prefix}Quest: {title} {step_id} kill {saved_target}"
            else:
                key = f"{prefix}Quest: {title} {step_id} {target} consume {child.attrib.get('item', 'Food')}"
            targets.append(QuestTarget(step_id, child.tag, target, count, key))
    tiers: set[int] = set()
    for step in root:
        if step.attrib.get("id") != "#start":
            continue
        for option in step.findall("option"):
            for complete in option.findall("complete"):
                count = _as_int(complete.attrib.get("count"), -1)
                if count >= 0:
                    tiers.add(count)
    recipes = tuple(dict.fromkeys(
        reward.attrib["recipe"].strip() for reward in root.iter("reward")
        if reward.attrib.get("recipe", "").strip()))
    return QuestDef(title=title, npc=root.attrib.get("npc", ""),
                    daily=root.find("daily") is not None,
                    daily_tiers=tuple(sorted(tiers)),
                    deps=tuple(x.attrib["quest"] for x in root.findall("complete")
                               if x.attrib.get("quest")),
                    steps=steps, targets=tuple(targets), recipes=recipes, source_order=order,
                    line=line)


def _as_int(raw: Any, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default
