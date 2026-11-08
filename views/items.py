from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st
from streamlit_sortables import sort_items

import gamedata
import itemops
import schema
from i18n import lang, t
from model import SaveDoc
from ui import theme
from validate import issue_index

KINDS = ("inventory", "quickslot", "equipment", "pet", "container")


def close_transients(ss) -> None:
    """离开物品页或退出编辑模式时，关闭格子弹窗和未完成的点选移动。"""
    ss.slot_target = None
    ss.item_move_source = None


@st.cache_resource(show_spinner=False)
def _catalog() -> gamedata.Catalog:
    return gamedata.load_catalog()


def _prefixes(doc: SaveDoc, kind: str) -> list[str]:
    by_prefix = doc.prefix_slots()
    pets = doc.pets()
    if kind == "inventory":
        return ["Inventory"] if "Inventory" in by_prefix else []
    if kind == "quickslot":
        return ["QuickSlot"] if "QuickSlot" in by_prefix else []
    if kind == "equipment":
        return ["Equipment"] if "Equipment" in by_prefix else []
    if kind == "pet":
        return sorted([p for p in by_prefix if p in pets])
    if kind == "pet_equip":
        return sorted([p for p in by_prefix if p.endswith("_Equipment")])
    return sorted([p for p in by_prefix
                   if p not in schema.FIXED_STORES and p not in pets
                   and not p.endswith("_Equipment")])


def _capacity(doc: SaveDoc, prefix: str) -> int:
    kind = schema.classify(f"{prefix}_name_0", doc.pets())
    if kind == "inventory":
        return int(doc.get("InventoryUnlocked") or 64)
    if kind in ("quickslot", "equipment"):
        return schema.STORAGE_CAPACITY[kind]
    slots = doc.slots(prefix)
    return max(slots) + 1 if slots else 0


def _columns(doc: SaveDoc, prefix: str) -> int:
    """与游戏容器一致：玩家背包 5 列，宠物背包/箱子 4 列。"""
    kind = schema.classify(f"{prefix}_name_0", doc.pets())
    if kind == "inventory":
        return 5
    if kind in {"pet_bag", "container", "pet_equip"}:
        return 4
    if kind == "equipment":
        return 3
    return 5


def _grid_start(doc: SaveDoc, prefix: str) -> int:
    """PlayerInventoryStorage 强制锁定 0–3；普通背包从索引 4 开始。"""
    return 4 if schema.classify(f"{prefix}_name_0", doc.pets()) == "inventory" else 0


def render(doc: SaveDoc, issues) -> None:
    ss = st.session_state
    theme.page_head(t("it.title"), t("it.sub"))
    catalog = _catalog()
    _catalog_browser(catalog)

    kind = st.segmented_control(
        "storage", list(KINDS) + ["pet_equip"], key="i_kind",
        format_func=lambda k: {
            "inventory": t("cat.inventory"), "quickslot": t("cat.quickslot"),
            "equipment": t("cat.equipment"), "pet": t("cat.pet_bag"),
            "pet_equip": t("cat.pet_equip"), "container": t("cat.container"),
        }[k], label_visibility="collapsed",
    ) or "inventory"

    prefixes = _prefixes(doc, kind)
    if not prefixes:
        st.caption(t("it.containerEmpty") if kind == "container" else t("it.noItems"))
        return
    prefix = (st.selectbox("prefix", prefixes, key=f"i_prefix_{kind}",
                           format_func=lambda p: p or t("it.worldContainer"))
              if len(prefixes) > 1 else prefixes[0])

    slots = doc.slots(prefix)
    capacity = _capacity(doc, prefix)
    total = max(capacity, (max(slots) + 1) if slots else 0)
    used = sum(1 for s in slots.values() if not s.empty)
    idx = issue_index(issues)
    columns = _columns(doc, prefix)
    st.caption(f"{prefix} · " + t("it.used", used=used, cap=total)
               + f" · {t('it.columns', n=columns)}")

    show_all = ss.get("i_show_all", False)
    if total > 32 and not show_all:
        last_used = max([s.index for s in slots.values() if not s.empty] + [-1])
        visible = min(total, max(24, (last_used // columns + 2) * columns))
    else:
        visible = total

    editable = ss.editable
    arrange = False
    if editable:
        arrange = st.segmented_control(
            "interaction", ["edit", "arrange"], key="i_interaction",
            format_func=lambda x: t(f"it.mode.{x}"), label_visibility="collapsed",
        ) == "arrange"
    if arrange:
        _arrange_toolbar(doc, prefix, slots, visible, catalog)
        if ss.get("item_click_move"):
            _grid(doc, prefix, slots, visible, idx, catalog, click_move=True)
        else:
            _drag_grid(doc, prefix, slots, visible, columns, catalog)
    else:
        _grid(doc, prefix, slots, visible, idx, catalog)

    if visible < total:
        st.caption(t("it.moreEmpty", n=total - visible))
        if st.button(t("it.showAll"), key="i_all"):
            ss.i_show_all = True
            st.rerun()
    elif ss.get("i_show_all") and total > 32:
        if st.button(t("it.showLess"), key="i_less"):
            ss.i_show_all = False
            st.rerun()
    theme.note(t("it.note"))
    _maybe_open_dialog(doc, prefix, catalog)


def _catalog_browser(catalog: gamedata.Catalog) -> None:
    title = t("it.catalog")
    if not catalog.error:
        title += f" · {len(catalog.items)} / {len(catalog.mobs)}"
    with st.expander(title):
        if catalog.error:
            theme.warnbox(t("it.catalogError", msg=catalog.error, path=catalog.source))
            return
        kind = st.segmented_control("catalog kind", ["items", "mobs"], key="i_cat_kind",
                                    format_func=lambda x: t(f"it.catalog.{x}"),
                                    label_visibility="collapsed") or "items"
        if kind == "items":
            c1, c2 = st.columns([3, 1])
            with c1:
                query = st.text_input(t("it.catalogSearch"), key="i_cat_search",
                                      placeholder=t("it.catalogPlaceholder"))
            with c2:
                categories = sorted({e.category for e in catalog.items.values() if e.category})
                category = st.selectbox(t("it.category"), [""] + categories,
                                        format_func=lambda x: x or t("c.all"), key="i_cat_category")
            entries = [e for e in catalog.search_items(query, lang())
                       if not category or e.category == category]
            rows = [{"ID": e.id, t("it.displayEn"): e.en, t("it.displayZh"): e.zh,
                     t("it.category"): e.category} for e in entries[:100]]
        else:
            query = st.text_input(t("it.catalogSearch"), key="i_cat_search_mobs",
                                  placeholder=t("it.catalogPlaceholder"))
            rows = [{"data": i, "ID": e.id, t("it.displayEn"): e.en,
                     t("it.displayZh"): e.zh}
                    for i, e in catalog.search_mobs(query, lang())[:100]]
        st.caption(t("it.catalogSource", path=catalog.source))
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         height=min(400, 38 + 34 * len(rows)))
        else:
            st.caption(t("it.noMatch"))
        if st.button(t("it.catalogRefresh"), key="i_cat_refresh"):
            gamedata.load_catalog(refresh=True)
            st.cache_resource.clear()  # 物品页、任务页与侧栏版本号共享同一份目录
            st.rerun()


def _arrange_toolbar(doc: SaveDoc, prefix: str, slots, visible: int,
                     catalog: gamedata.Catalog) -> None:
    ss = st.session_state
    c1, c2, c3 = st.columns([1.2, 1, 1], vertical_alignment="center")
    with c1:
        st.toggle(t("it.clickMove"), key="item_click_move", help=t("it.clickMoveHint"))
    with c2:
        if st.button(t("it.sort"), width="stretch", help=t("it.sortHint")):
            if itemops.sort_by_name(doc, prefix, visible,
                                    lambda s: catalog.item_label(s.name, lang(), s.data),
                                    start=_grid_start(doc, prefix)):
                st.rerun()
    with c3:
        source = ss.get("item_move_source")
        if source and st.button(t("it.cancelMove"), width="stretch"):
            ss.item_move_source = None
            st.rerun()
    source = ss.get("item_move_source")
    if source:
        st.info(t("it.moveSource", slot=source[1] + 1, prefix=source[0] or t("it.worldContainer")))
    else:
        st.caption(t("it.dragHint"))


def _display(catalog: gamedata.Catalog, slot) -> str:
    if slot is None or slot.empty:
        return t("it.empty")
    return f"{catalog.item_label(slot.name, lang(), slot.data)}  ×{slot.count}"


def _grid(doc: SaveDoc, prefix: str, slots, visible: int, idx,
          catalog: gamedata.Catalog, click_move: bool = False) -> None:
    columns = _columns(doc, prefix)
    grid_start = _grid_start(doc, prefix)
    if grid_start:
        st.caption(t("it.reservedHint"))
        reserved = st.columns(grid_start, gap="small")
        for index, col in enumerate(reserved):
            slot = slots.get(index)
            label = t("it.reserved") if slot is None or slot.empty else _display(catalog, slot)
            with col:
                st.button(label, key=f"reserved_{prefix}_{index}", width="stretch",
                          disabled=True, help=t("it.reservedHint"))
    for start in range(grid_start, visible, columns):
        cols = st.columns(columns, gap="small")
        for offset, col in enumerate(cols):
            index = start + offset
            if index >= visible:
                continue
            slot = slots.get(index)
            with col:
                empty = slot is None or slot.empty
                label = t("it.empty") if empty else _display(catalog, slot)
                key_prefix = "empt" if empty else "slot"
                help_text = f"#{index + 1} · " + (slot.name if slot and slot.name else t("it.empty"))
                problems = [i for i in idx.get(f"{prefix}_name_{index}", []) if i.level != "info"]
                if problems:
                    help_text += "  ✕"
                if st.button(label, key=f"{key_prefix}_{prefix}_{index}",
                             width="stretch", help=help_text, type="tertiary"):
                    if click_move:
                        _click_move(doc, prefix, index)
                    else:
                        st.session_state.slot_target = (prefix, index)
                        st.rerun()


def _click_move(doc: SaveDoc, prefix: str, index: int) -> None:
    ss = st.session_state
    source = ss.get("item_move_source")
    if source is None:
        ss.item_move_source = (prefix, index)
    elif source == (prefix, index):
        ss.item_move_source = None
    else:
        itemops.swap_slots_between(doc, source[0], source[1], prefix, index)
        ss.item_move_source = None
    st.rerun()


def _drag_grid(doc: SaveDoc, prefix: str, slots, visible: int, columns: int,
               catalog: gamedata.Catalog) -> None:
    indices = list(range(_grid_start(doc, prefix), visible))
    labels = [f"{i:03d} | {_display(catalog, slots.get(i))}" for i in indices]
    digest = hashlib.sha1("\n".join(labels).encode("utf-8")).hexdigest()[:12]
    style = f"""
    .sortable-component {{width:100%;}}
    .sortable-container-header {{display:none;}}
    .sortable-container-body {{display:grid;grid-template-columns:repeat({columns},minmax(0,1fr));
      gap:7px;background:transparent;padding:0;}}
    .sortable-item,.sortable-item:hover {{margin:0;min-height:64px;padding:8px;border-radius:8px;
      border:1px solid rgba(240,161,42,.35);background:rgba(240,161,42,.07);color:inherit;
      font-size:12px;line-height:1.35;overflow-wrap:anywhere;}}
    .sortable-item.dragging {{opacity:.65;}}
    """
    arranged = sort_items(labels, multi_containers=False, direction="vertical",
                          custom_style=style, key=f"drag_{prefix}_{visible}_{digest}")
    if arranged != labels:
        try:
            order = [int(label.split(" | ", 1)[0]) for label in arranged]
            itemops.apply_order(doc, prefix, order, indices)
        except (ValueError, KeyError) as exc:
            st.error(t("it.dragError", msg=str(exc)))
        else:
            st.rerun()


def _maybe_open_dialog(doc: SaveDoc, prefix: str, catalog: gamedata.Catalog) -> None:
    target = st.session_state.get("slot_target")
    if not target or target[0] != prefix:
        return
    _slot_dialog(doc, target[0], target[1], catalog)


def _slot_dialog(doc: SaveDoc, prefix: str, index: int, catalog: gamedata.Catalog) -> None:
    @st.dialog(t("it.edit"), width="small")
    def _body() -> None:
        _slot_body(doc, prefix, index, catalog)
    _body()


def _slot_body(doc: SaveDoc, prefix: str, index: int, catalog: gamedata.Catalog) -> None:
    slot = doc.slots(prefix).get(index)
    st.markdown(
        f"<div class='bs-mono' style='color:var(--bs-muted);font-size:12px'>"
        f"{prefix} · #{index + 1}</div>", unsafe_allow_html=True)
    editable = st.session_state.editable
    current_name = slot.name if slot else ""
    item_ids = sorted(catalog.items, key=lambda x: catalog.item_label(x, lang()).casefold())
    if current_name and current_name not in catalog.items:
        item_ids.insert(0, current_name)
    if "" not in item_ids:
        item_ids.insert(0, "")
    try:
        selected = item_ids.index(current_name)
    except ValueError:
        selected = 0
    name = st.selectbox(
        t("it.name"), item_ids, index=selected,
        format_func=lambda item_id: (t("it.empty") if not item_id else
                                     catalog.item_label(item_id, lang(), slot.data if slot else 0)),
        disabled=not editable, key=f"dlg_name_{prefix}_{index}",
        help=t("it.nameHelp"))
    count = st.number_input(t("it.count"), value=int(slot.count if slot else 0),
                            min_value=0, step=1, disabled=not editable,
                            key=f"dlg_count_{prefix}_{index}")
    c1, c2 = st.columns(2)
    with c1:
        if catalog.is_spawner(name):
            mob_rows = catalog.search_mobs("", lang())
            current_data = int(slot.data if slot else 0)
            mob_indices = [i for i, _ in mob_rows]
            data = st.selectbox(
                t("it.spawnerMob"), mob_indices,
                index=mob_indices.index(current_data) if current_data in mob_indices else 0,
                format_func=lambda i: f"{i} · {catalog.mobs[gamedata.MOB_TYPES[i]].label(lang())}",
                disabled=not editable, key=f"dlg_mob_{prefix}_{index}")
        else:
            data = st.number_input(t("it.data"), value=int(slot.data if slot else 0),
                                   min_value=0, max_value=65535, step=1,
                                   disabled=not editable, key=f"dlg_data_{prefix}_{index}")
    with c2:
        paint = st.number_input(t("it.paint"), value=int(slot.paint if slot else 0),
                                min_value=0, max_value=65535, step=1,
                                disabled=not editable, key=f"dlg_paint_{prefix}_{index}")
    if catalog.is_spawner(name):
        theme.note(t("it.spawnerHint", data=data,
                     mob=catalog.mobs[gamedata.MOB_TYPES[data]].label(lang())))
    theme.note(t("it.structuralKeys"))

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button(t("it.clear"), width="stretch", disabled=not editable):
            doc.push_undo(f"clear:{prefix}[{index}]")
            itemops.set_slot(doc, prefix, index, name="", count=0, data=0, paint=0)
            st.session_state.slot_target = None
            st.rerun()
    with b2:
        if st.button(t("c.cancel"), width="stretch"):
            st.session_state.slot_target = None
            st.rerun()
    with b3:
        if st.button(t("c.apply"), type="primary", width="stretch", disabled=not editable):
            doc.push_undo(f"edit:{prefix}[{index}]")
            itemops.set_slot(doc, prefix, index, name=name, count=int(count),
                             data=int(data), paint=int(paint))
            st.session_state.slot_target = None
            st.rerun()
