"""外观：注入 CSS、隐藏 Streamlit 自带元素、统一卡片与等宽字体。"""

from __future__ import annotations

import streamlit as st

CSS = """
<style>
  :root{
    --bs-line: rgba(255,255,255,.09);
    --bs-muted: #9aa4b2;
    --bs-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  }
  /* 收紧默认留白。顶部要留出 header 的高度：
     Streamlit 把「展开侧栏」按钮放在 header 里，内容若顶到最上面就会和它重叠。 */
  .block-container{padding-top:3.05rem;padding-bottom:4rem;max-width:1500px}
  header[data-testid="stHeader"]{background:transparent;height:2.75rem;min-height:2.75rem}
  footer{visibility:hidden}
  /* 只隐藏 Deploy 与右上角菜单；整块 stToolbar 里还装着「展开侧栏」按钮，不能一起隐藏 */
  div[data-testid="stDecoration"], .stAppDeployButton, [data-testid="stMainMenu"]{display:none!important}
  div[data-testid="stExpandSidebarButton"] button,
  button[data-testid="stExpandSidebarButton"]{color:var(--bs-muted)}
  div[data-testid="stSegmentedControl"] button{padding:.05rem .4rem;font-size:12px;min-height:1.6rem}

  /* 侧栏 */
  section[data-testid="stSidebar"]{border-right:1px solid var(--bs-line)}
  section[data-testid="stSidebar"] .block-container{padding-top:.6rem}

  /* 侧栏头：默认占 60px 高、收起按钮还是 hover 才显示。
     这里压成 0 高，让品牌行与按钮同处一行；按钮强制常显，否则用户找不到收起入口。 */
  section[data-testid="stSidebar"] [data-testid="stSidebarHeader"]{
    height:0;min-height:0;padding:0;overflow:visible}
  section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]{
    position:relative;top:3rem}          /* 与品牌行同一水平线 */
  section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button{
    visibility:visible!important;opacity:.7}
  section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button:hover{opacity:1}
  section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding-top:.55rem}

  /* 品牌行：右侧给「收起侧栏」按钮留位，否则它会被语言按钮盖住 */
  .st-key-bs_brandrow{padding-right:2.4rem}

  /* 品牌行 */
  .bs-brand{display:flex;align-items:center;gap:9px;padding:2px 0 6px}
  .bs-mark{width:26px;height:26px;border-radius:7px;flex:0 0 auto;
    background:linear-gradient(135deg,#f0a12a 0 50%,#7a4a10 50% 100%)}
  .bs-brand b{font-size:13.5px;letter-spacing:.2px;line-height:1.2;white-space:nowrap}
  .bs-brand span{display:block;font-size:10.5px;color:var(--bs-muted);font-weight:400}

  /* 状态徽标 */
  .bs-badge{display:inline-flex;align-items:center;gap:5px;padding:1px 8px;border-radius:99px;
    font-size:11.5px;border:1px solid var(--bs-line);color:var(--bs-muted);white-space:nowrap}
  .bs-badge.ok{color:#5cbd70;border-color:rgba(92,189,112,.38);background:rgba(92,189,112,.1)}
  .bs-badge.warn{color:#f5a524;border-color:rgba(245,165,36,.38);background:rgba(245,165,36,.1)}
  .bs-badge.err{color:#ff8185;border-color:rgba(229,72,77,.42);background:rgba(229,72,77,.12)}
  .bs-badge.mute{color:var(--bs-muted)}

  /* 顶部条 */
  .bs-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}
  .bs-top h2{margin:0;font-size:19px;font-weight:650;letter-spacing:.1px}
  .bs-top .bs-sub{color:var(--bs-muted);font-size:12.5px;margin:0}

  /* 指标卡 */
  div[data-testid="stMetric"]{border:1px solid var(--bs-line);border-radius:10px;padding:10px 13px;height:100%}
  div[data-testid="stMetricLabel"] p{font-size:11.5px;letter-spacing:.03em;color:var(--bs-muted)}
  div[data-testid="stMetricValue"]{font-size:23px}

  /* 表格 */
  div[data-testid="stDataFrame"]{border:1px solid var(--bs-line);border-radius:10px}
  div[data-testid="stDataFrame"] *{font-variant-numeric:tabular-nums}

  /* 代码/键名 */
  code{font-family:var(--bs-mono)!important;font-size:12px!important}

  /* 展开器 */
  details[data-testid="stExpander"]{border:1px solid var(--bs-line);border-radius:10px;margin-bottom:8px}
  details[data-testid="stExpander"] summary{font-size:13px}

  /* 按钮紧凑些 */
  .stButton button, .stDownloadButton button{padding:.25rem .7rem;min-height:2.1rem;font-size:13px}
  .stButton button[kind="primary"]{font-weight:600}

  /* 分段控件 */
  div[data-testid="stSegmentedControl"] button{padding:.15rem .5rem;font-size:12.5px;min-height:1.7rem}

  /* 侧栏导航：按钮伪装成列表项 */
  div[class*="st-key-nav_on_"] button, div[class*="st-key-nav_off_"] button{
    display:flex!important;justify-content:flex-start!important;text-align:left;
    padding:.28rem .55rem;min-height:1.9rem;
    border:0!important;border-left:2px solid transparent!important;
    border-radius:6px!important;background:transparent!important;
    color:var(--bs-muted);font-size:13.5px;font-weight:500;
  }
  div[class*="st-key-nav_on_"] button > div,
  div[class*="st-key-nav_off_"] button > div{
    width:100%;justify-content:flex-start!important;display:flex}
  div[class*="st-key-nav_on_"] button p, div[class*="st-key-nav_off_"] button p{
    text-align:left;width:100%;font-size:13.5px;margin:0}
  div[class*="st-key-nav_off_"] button:hover{
    background:rgba(255,255,255,.05)!important;color:var(--bs-text)}
  div[class*="st-key-nav_on_"] button{
    background:rgba(240,161,42,.13)!important;color:var(--bs-text);
    border-left-color:#f0a12a!important;font-weight:600}
  div[class*="st-key-nav_on_"] button p{font-weight:600}

  /* 物品格子：按钮做成卡片 */
  div[class*="st-key-slot_"] button, div[class*="st-key-empt_"] button{
    min-height:58px;height:58px;width:100%;
    display:flex;justify-content:flex-start;align-items:flex-start;
    text-align:left;padding:6px 8px;line-height:1.25;font-size:11.5px;
    border-radius:8px;white-space:normal;overflow:hidden}
  div[class*="st-key-slot_"] button p, div[class*="st-key-empt_"] button p{
    font-size:11.5px;line-height:1.25;white-space:normal;text-align:left;margin:0;
    display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  div[class*="st-key-slot_"] button{border-color:rgba(240,161,42,.35);background:rgba(240,161,42,.06)}
  div[class*="st-key-slot_"] button:hover{border-color:rgba(240,161,42,.75);background:rgba(240,161,42,.12)}
  div[class*="st-key-empt_"] button{border-style:dashed;opacity:.55}
  div[class*="st-key-empt_"] button p{color:var(--bs-muted)}

  /* 对话弹窗 */
  div[data-testid="stDialog"] div[role="dialog"]{border-radius:14px}

  /* 小字说明 */
  .bs-note{color:var(--bs-muted);font-size:11.8px;line-height:1.65}
  .bs-mono{font-family:var(--bs-mono);font-size:12px}
  .bs-hr{height:1px;background:var(--bs-line);margin:10px 0}
  .bs-cat{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--bs-muted);margin:14px 0 5px}
  .bs-warnbox{border:1px solid rgba(245,165,36,.35);background:rgba(245,165,36,.08);
    border-radius:10px;padding:10px 12px;font-size:12.3px;line-height:1.6}
  .bs-errbox{border:1px solid rgba(229,72,77,.4);background:rgba(229,72,77,.1);
    border-radius:10px;padding:10px 12px;font-size:12.3px;line-height:1.6}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def brand(title: str, subtitle: str) -> str:
    return (f'<div class="bs-brand"><div class="bs-mark"></div>'
            f'<div><b>{title}</b><span>{subtitle}</span></div></div>')


def page_head(title: str, sub: str = "") -> None:
    sub_html = f'<p class="bs-sub">{sub}</p>' if sub else ""
    st.markdown(f'<div class="bs-top"><h2>{title}</h2>{sub_html}</div>', unsafe_allow_html=True)


def badge(text: str, tone: str = "mute") -> str:
    return f'<span class="bs-badge {tone}">{text}</span>'


def note(text: str) -> None:
    st.markdown(f'<div class="bs-note">{text}</div>', unsafe_allow_html=True)


def warnbox(text: str) -> None:
    st.markdown(f'<div class="bs-warnbox">{text}</div>', unsafe_allow_html=True)


def errbox(text: str) -> None:
    st.markdown(f'<div class="bs-errbox">{text}</div>', unsafe_allow_html=True)
