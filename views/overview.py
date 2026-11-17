from __future__ import annotations

from typing import Any

import i18n
import reset as reset_mod
import schema
import storage
import uistate
import validate
from i18n import t
from ui import components as C
from ui import theme

import streamlit as st


def _label(spec: schema.FieldSpec | None, key: str) -> str:
    if spec is None:
        return key
    return spec.label_zh if i18n.lang() == "zh" else spec.label_en


def render(doc, issues) -> None:
    theme.page_head(t("ov.title"), t("ov.sub"))

    level = doc.get("Current Level")
    level = level if isinstance(level, int) else 0
    exp = doc.get("Current Experience")
    exp = exp if isinstance(exp, int) else 0
    purchased = doc.get("Purchased Skill Points", 0)
    purchased = purchased if isinstance(purchased, int) else 0
    unspent = doc.get("Skill Points", 0)
    unspent = unspent if isinstance(unspent, int) else 0

    snap = _rerender_snapshot(doc, level, purchased, unspent)
    bag = doc.slots("Inventory")
    bag_used = sum(1 for s in bag.values() if not s.empty)
    bag_cap = doc.get("InventoryUnlocked") or 64
    pet_stats = doc.pet_stats()
    xp_cap = schema.max_exp_for_level(level)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(t("ov.level"), f"{level}", help=f"0–{schema.MAX_LEVEL}")
    with c2:
        st.metric(t("ov.skill"), f"{unspent}",
                  help=t("ov.skillHint", spent=snap["spent"], total=snap["total"]))
    with c3:
        st.metric(t("ov.bag"), f"{bag_used}", help=t("ov.bagHint", used=bag_used, cap=bag_cap))
    with c4:
        st.metric(t("ov.pets"), f"{len(pet_stats)}",
                  help=t("ov.petsHint", n=len(pet_stats)))

    if isinstance(xp_cap, int) and xp_cap > 0:
        left = max(0, xp_cap - exp)
        st.progress(min(1.0, max(0.0, exp / xp_cap)),
                    text=t("ov.xpNext", cur=C.fmt_int(exp), cap=C.fmt_int(xp_cap), left=C.fmt_int(left)))

    # ── 加点分布 ────────────────────────────────────────────────
    st.markdown('<div class="bs-cat">' + t("ov.points") + "</div>", unsafe_allow_html=True)
    _points_chart(doc, snap)
    theme.note(t("ov.pointsNote"))

    # ── 检查 ────────────────────────────────────────────────────
    st.markdown('<div class="bs-cat">' + t("ov.check") + "</div>", unsafe_allow_html=True)
    counts = validate.counts(issues)
    unknown = sum(1 for i in issues if i.code == "W_UNKNOWN")
    k1, k2, k3 = st.columns(3)
    with k1:
        with st.container(border=True):
            st.metric(t("ov.checkErr"), counts.get("error", 0))
            st.caption(t("ov.checkErrHint"))
            st.button(t("nav.fields"), key="ov_goto_err", width="stretch",
                      on_click=uistate.goto, args=("fields",))
    with k2:
        with st.container(border=True):
            st.metric(t("ov.checkWarn"), counts.get("warn", 0))
            st.caption(t("ov.checkWarnHint"))
            st.button(t("nav.fields"), key="ov_goto_warn", width="stretch",
                      on_click=uistate.goto, args=("fields",))
    with k3:
        with st.container(border=True):
            st.metric(t("ov.checkUnknown"), unknown)
            st.caption(t("ov.checkUnknownHint"))

    # ── 文件信息 ────────────────────────────────────────────────
    st.markdown('<div class="bs-cat">' + t("ov.file") + "</div>", unsafe_allow_html=True)
    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            path_text = str(doc.path) if doc.path else "—"
            backups = storage.list_backups(doc.path) if doc.path else []
            C.kv([
                (t("ov.path"), path_text),
                (t("ov.size"), f"{len(doc.raw.encode('utf-8')):,} B"),
                (t("c.keys"), f"{len(doc.values):,}"),
                (t("ov.backups"), f"{len(backups)}" if backups else t("ov.backupNone")),
            ])
            st.markdown('<div class="bs-hr"></div>', unsafe_allow_html=True)
            _roundtrip_line(doc)
    with right:
        with st.container(border=True):
            st.caption(t("ov.fastest"))
            st.button(t("nav.tidy"), width="stretch", key="ov_tidy",
                      on_click=uistate.goto, args=("tidy",))
            st.button(t("nav.reset"), width="stretch", key="ov_reset",
                      on_click=uistate.goto, args=("reset",))
            st.button(t("nav.save"), width="stretch", key="ov_save",
                      on_click=uistate.goto, args=("save",))


def _rerender_snapshot(doc, level, purchased, unspent) -> dict[str, Any]:
    return reset_mod.skill_snapshot(doc.values)


def _points_chart(doc, snap: dict[str, Any]) -> None:
    per = snap["per_attr"]
    rows = []
    for attr in schema.POINT_ATTRIBUTES:
        spec = schema.spec_for(attr.key, doc.pets())
        rows.append((_label(spec, attr.key), per.get(attr.key, 0.0), attr.key))
    rows.sort(key=lambda r: r[1])
    biggest = max([r[1] for r in rows] + [1.0])

    try:
        import plotly.graph_objects as go
    except ImportError:  # pragma: no cover
        st.dataframe({"": [r[0] for r in rows], t("ov.points"): [r[1] for r in rows]})
        return

    fig = go.Figure(go.Bar(
        x=[r[1] for r in rows], y=[r[0] for r in rows], orientation="h",
        marker_color="#f0a12a", hovertemplate="%{y}: %{x} pts<extra></extra>",
        text=[f"{int(v)}" for v in (r[1] for r in rows)],
        textposition="outside", cliponaxis=False,
    ))
    fig.update_layout(
        height=40 + 26 * len(rows), margin=dict(l=0, r=28, t=6, b=6),
        xaxis=dict(range=[0, biggest * 1.18], showgrid=True, title=None),
        yaxis=dict(title=None), showlegend=False, bargap=0.35,
    )
    st.plotly_chart(fig, width="stretch", theme="streamlit",
                    config={"displayModeBar": False})

    diff = snap["diff"]
    bits = [
        theme.badge(t("ov.pointsSum", invested=C.fmt_int(snap["invested"])), "mute"),
        theme.badge(t("ov.pointsSpent", spent=C.fmt_int(snap["spent"])), "mute"),
    ]
    if abs(diff) >= 1:
        bits.append(theme.badge(t("ov.pointsDiff", diff=diff), "warn"))
    else:
        bits.append(theme.badge(t("ov.pointsOk"), "ok"))
    st.markdown(" ".join(bits), unsafe_allow_html=True)


def _roundtrip_line(doc) -> None:
    if not doc.raw:
        return
    if not doc.is_pristine():
        st.caption(t("c.changed", n=sum(doc.change_counts())))
        return
    ok = doc.serialize() == doc.raw
    if ok:
        st.markdown(theme.badge("✓ " + t("ov.roundtripOk"), "ok"), unsafe_allow_html=True)
    else:
        st.markdown(theme.badge("✕ " + t("ov.roundtripFail", detail="byte diff"), "err"),
                    unsafe_allow_html=True)
