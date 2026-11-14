"""Visual theme for Physics AI Studio.

Presentation-only styling. This module does not import or modify physics solvers.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

COLORS = {
    "canvas": "#202A36",
    "panel": "#293645",
    "panel_alt": "#313F50",
    "border": "#405064",
    "text": "#E7EDF5",
    "muted": "#A8B5C5",
    "accent": "#38C8F2",
    "accent_hover": "#72DDF8",
    "success": "#55C99A",
}

def apply_theme():
    """Apply the dark slate UI and a matching Plotly canvas."""
    pio.templates["physics_ai_dark"] = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=COLORS["canvas"],
            plot_bgcolor=COLORS["panel"],
            font={"family": "Inter, Segoe UI, Arial, sans-serif", "color": COLORS["text"], "size": 12},
            title={"font": {"size": 15, "color": COLORS["text"]}},
            xaxis={
                "gridcolor": COLORS["border"], "zerolinecolor": COLORS["border"],
                "linecolor": COLORS["border"], "tickfont": {"color": COLORS["muted"]},
                "title": {"font": {"color": COLORS["muted"]}},
            },
            yaxis={
                "gridcolor": COLORS["border"], "zerolinecolor": COLORS["border"],
                "linecolor": COLORS["border"], "tickfont": {"color": COLORS["muted"]},
                "title": {"font": {"color": COLORS["muted"]}},
            },
            legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": COLORS["text"]}},
            colorway=["#38C8F2", "#A78BFA", "#F4B860", "#55C99A", "#F28B82"],
            margin={"l": 48, "r": 20, "t": 48, "b": 42},
        )
    )
    pio.templates.default = "physics_ai_dark"

    st.markdown(
        """
        <style>
        :root {
            color-scheme: dark;
            --pas-canvas: #202A36;
            --pas-panel: #293645;
            --pas-panel-alt: #313F50;
            --pas-border: #405064;
            --pas-text: #E7EDF5;
            --pas-muted: #A8B5C5;
            --pas-accent: #38C8F2;
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            background: var(--pas-canvas);
            color: var(--pas-text);
        }
        [data-testid="stHeader"] { background: rgba(32,42,54,.92); }
        [data-testid="stSidebar"] {
            background: #1B2530;
            border-right: 1px solid var(--pas-border);
        }
        [data-testid="stSidebar"] > div { background: #1B2530; }
        .block-container {
            max-width: 1440px;
            padding-top: 1.1rem; padding-bottom: 2rem;
            padding-left: 1.35rem; padding-right: 1.35rem;
        }
        html, body, [class*="css"] {
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            color: var(--pas-text);
        }
        h1 { font-size: 1.62rem !important; font-weight: 680 !important; letter-spacing: -.035em; }
        h2 { font-size: 1.18rem !important; font-weight: 640 !important; letter-spacing: -.02em; }
        h3 { font-size: 1.02rem !important; font-weight: 620 !important; }
        p, li, label, .stMarkdown { font-size: .91rem; }
        [data-testid="stCaptionContainer"] { color: var(--pas-muted); font-size: .77rem; }
        [data-testid="stMetric"] {
            background: var(--pas-panel); border: 1px solid var(--pas-border);
            padding: 9px 11px; border-radius: 9px;
        }
        [data-testid="stMetricLabel"] { color: var(--pas-muted); font-size: .75rem; }
        [data-testid="stMetricValue"] {
            color: var(--pas-text); font-size: 1.22rem;
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
            font-variant-numeric: tabular-nums lining-nums;
            font-feature-settings: "tnum" 1, "lnum" 1;
        }
        input, textarea, [data-testid="stNumberInput"] input,
        [data-testid="stDataFrame"], code, pre {
            font-variant-numeric: tabular-nums lining-nums;
            font-feature-settings: "tnum" 1, "lnum" 1;
        }
        [data-testid="stNumberInput"] input, code, pre {
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        }
        [data-testid="stExpander"] {
            background: var(--pas-panel); border: 1px solid var(--pas-border);
            border-radius: 10px;
        }
        [data-testid="stExpander"] details summary p { font-size: .91rem; font-weight: 620; }
        .stButton button, .stDownloadButton button {
            min-height: 2.35rem; font-size: .87rem; border-radius: 8px;
            border: 1px solid #3C7890; transition: all .15s ease;
        }
        .stButton button[kind="primary"] {
            background: var(--pas-accent); color: #10212B; border-color: var(--pas-accent);
            font-weight: 700;
        }
        .stButton button:hover, .stDownloadButton button:hover {
            border-color: var(--pas-accent); color: var(--pas-accent);
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--pas-accent); border-bottom-color: var(--pas-accent);
        }
        [data-testid="stNumberInput"] input, [data-testid="stTextInput"] input,
        [data-testid="stSelectbox"] [role="combobox"], [data-testid="stTextArea"] textarea {
            background: var(--pas-panel-alt); border-color: var(--pas-border);
            border-radius: 7px;
        }
        [data-testid="stDataFrame"], [data-testid="stTable"] {
            border: 1px solid var(--pas-border); border-radius: 8px; overflow: hidden;
        }
        hr { border-color: var(--pas-border); margin: .85rem 0; }
        .app-topbar {
            display:flex; align-items:center; justify-content:space-between;
            padding:12px 16px; border:1px solid var(--pas-border);
            border-radius:9px 9px 0 0; background:#253241;
        }
        .app-name { font-size:1.04rem; font-weight:760; letter-spacing:.09em; color:var(--pas-text); }
        .app-subtitle { font-size:.74rem; color:var(--pas-muted); margin-top:3px; }
        .app-status { font-size:.72rem; font-weight:700; color:#55C99A; }
        .app-ribbon {
            padding:8px 14px; border:1px solid var(--pas-border); border-top:0;
            border-radius:0 0 9px 9px; background:#1B2530;
            color:#B9C8D8; font-size:.72rem; font-weight:650;
            letter-spacing:.025em; margin-bottom:12px;
        }
        [data-testid="stSidebar"] [data-testid="stTabs"] button { font-size:.82rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
