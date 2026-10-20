"""Visual system for the water planning workspace."""
import html
import streamlit as st

CSS = '''<style>
:root {--ink:#111827;--muted:#667085;--line:#dcdff0;--accent:#00649a;}
.stApp {background:#faf9ff;}
.block-container {padding:1.8rem 2.25rem 3rem;max-width:1420px;}
[data-testid="stHeader"] {background:rgba(250,249,255,.95);}
h1 {font-size:2.05rem!important;letter-spacing:-1px;font-weight:650!important;line-height:1.18!important;}
h2,h3 {letter-spacing:-.5px;font-weight:600!important;}
h3 {font-size:1.25rem!important;}
h4 {font-size:1rem!important;letter-spacing:-.15px;}
p, label {line-height:1.6;}
[data-testid="stCaptionContainer"] {color:var(--muted);}
[data-testid="stSidebar"] {background:#fff;border-right:1px solid var(--line);}
[data-testid="stSidebarUserContent"] {padding:1.1rem .9rem;}
[data-testid="stSidebar"] hr {margin:1rem 0;border-color:var(--line);}
.water-brand {display:flex;gap:10px;align-items:center;padding:0 5px 16px;}
.water-logo {width:38px;height:42px;border-radius:13px;background:#dceeff;color:#00649a;display:grid;place-items:center;font-size:24px;font-weight:600;}
.water-name {font-size:18px;letter-spacing:-.6px;font-weight:700;color:var(--ink);}
.water-tag {font-size:10px;text-transform:uppercase;letter-spacing:1.7px;color:var(--muted);margin-top:2px;}
[data-testid="stSidebar"] [data-testid="stRadio"] > label {font-size:10px;text-transform:uppercase;letter-spacing:1.7px;color:#667085;font-weight:600;margin-top:8px;}
[data-testid="stSidebar"] [role="radiogroup"] {gap:4px;}
[data-testid="stSidebar"] label[data-baseweb="radio"] {margin:0!important;padding:9px 12px;border:1px solid transparent;border-radius:8px;transition:background .15s;min-height:42px;width:100%;}
[data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {display:none;}
[data-testid="stSidebar"] label[data-baseweb="radio"] p {font-size:13px;font-weight:500;}
[data-testid="stSidebar"] label[data-baseweb="radio"]:hover {background:#f1f0ff;}
[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {background:#004f87;border-color:#004f87;border-left:3px solid var(--accent);}
[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) p {color:#ffffff;font-weight:650;}
[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:focus-visible) {outline:2px solid var(--accent);outline-offset:2px;}
[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:disabled) {opacity:.5;}
[data-testid="stSidebar"] [data-testid="stExpander"] {border:1px solid var(--line);border-radius:9px;background:#fff;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p {font-size:12px;font-weight:600;}
.workspace-eyebrow {font-size:9px;letter-spacing:1.6px;text-transform:uppercase;color:#667085;margin:4px 0 8px;}
.workspace-context {display:flex;flex-wrap:wrap;gap:6px;border-bottom:1px solid var(--line);padding:0 0 12px;margin:8px 0 16px;}
.context-chip {font-size:10px;color:#475467;padding:3px 8px;background:#fff;border:1px solid var(--line);border-radius:5px;}
.context-chip:first-child {background:#d8f5ef;color:#006a68;border-color:#b6e5dd;}
[data-testid="stMetric"] {background:#fff;border:1px solid var(--line);border-radius:8px;padding:13px 11px;box-shadow:none;}
[data-testid="stMetricLabel"] {color:#667085;font-size:12px;}
[data-testid="stMetricValue"] > div {white-space:normal!important;overflow:visible!important;text-overflow:clip!important;}
[data-testid="stMetricLabel"] p {white-space:normal;font-size:12px;}
[data-testid="stMetricValue"] {color:var(--ink);font-size:clamp(1rem,1.65vw,1.8rem);font-weight:600;letter-spacing:-.8px;}
[data-testid="stPlotlyChart"], [data-testid="stDeckGlJsonChart"] {background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden;}
[data-testid="stDataFrame"] {border:1px solid var(--line);border-radius:8px;overflow:hidden;}
[data-testid="stAlert"] {border-radius:9px;font-size:13px;}
[data-testid="stAlert"] p {font-size:13px;}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button {border-radius:8px;font-size:12px;min-height:38px;}
[data-baseweb="select"] > div,[data-baseweb="input"] {border-radius:8px;}
[data-testid="stExpander"] {border-color:var(--line);border-radius:9px;}
[data-testid="stBaseButton-primary"] {background:#00649a!important;border-color:#00649a!important;color:#fff!important;}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {background:#f1f0ff!important;color:#344563;border:1px solid #dcdff0;}
[data-testid="stAlertContentInfo"] {color:#344563;}
@media(max-width:800px) {.block-container {padding:2rem 1.2rem;}h1 {font-size:1.85rem!important;}.workspace-context{gap:5px;}}
@media(prefers-reduced-motion:reduce) {* {transition:none!important;}}
</style>'''


def apply_theme():
    st.markdown(CSS,unsafe_allow_html=True)


def sidebar_brand():
    st.markdown('<div class="water-brand"><div class="water-logo">≈</div><div><div class="water-name">Smart Water</div><div class="water-tag">Redistribution workspace</div></div></div>',unsafe_allow_html=True)


def context_bar(items):
    st.markdown('<div class="workspace-context">'+''.join('<span class="context-chip">'+html.escape(str(item))+'</span>' for item in items)+'</div>',unsafe_allow_html=True)
