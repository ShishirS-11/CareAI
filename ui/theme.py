
from __future__ import annotations

import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=DM+Serif+Display&display=swap');

        :root {
            color-scheme: light;
            --forest: #174D36;
            --forest-dark: #103D2A;
            --forest-light: #286548;
            --sage: #E5EEE3;
            --sage-light: #F0F4ED;
            --sage-panel: #EAF2E8;
            --ivory: #F7F6F0;
            --paper: #FFFEFA;
            --ink: #26372E;
            --ink-soft: #405648;
            --muted: #52685A;
            --line: #DDE5DB;
            --active-bg: #F8DCDD;
            --active-text: #963B45;
            --shadow: 0 8px 24px rgba(28,55,39,.055);
        }

        /* GLOBAL */

        html, body, [class*="css"], button, input, textarea {
            font-family: 'DM Sans', sans-serif !important;
        }

        .stApp {
            background: var(--ivory) !important;
            color: var(--ink) !important;
        }

        [data-testid="stHeader"] {
            background: rgba(247,246,240,.97) !important;
        }

        [data-testid="stMainBlockContainer"] {
            max-width: 1540px;
            padding: 2rem 2.4rem 4rem;
        }

        h1, h2 {
            font-family: 'DM Serif Display', Georgia, serif !important;
            color: var(--forest) !important;
            letter-spacing: -.025em;
        }

        h1 {
            font-size: 2.65rem !important;
            line-height: 1.13 !important;
        }

        h2 {
            font-size: 1.85rem !important;
        }

        h3, h4 {
            color: var(--forest) !important;
            font-weight: 800 !important;
        }

        p, li {
            color: var(--muted);
            line-height: 1.7;
        }

        /* SIDEBAR */

        [data-testid="stSidebar"] {
            background: #F0F2EB !important;
            border-right: 1px solid var(--line);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding: 1.15rem .85rem 1.5rem;
        }

        .brand-lockup {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 8px 20px;
            border-bottom: 1px solid var(--line);
            margin-bottom: 15px;
        }

        .brand-mark {
            width: 43px;
            height: 43px;
            display: grid;
            place-items: center;
            flex: 0 0 43px;
            border-radius: 13px;
            background: var(--forest);
            color: white !important;
            font-size: 25px;
            font-weight: 800;
        }

        .brand-name {
            color: var(--forest);
            font-size: 23px;
            font-weight: 800;
        }

        .brand-subtitle {
            color: #55745E !important;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 1.35px;
            margin-top: 3px;
        }

        .sidebar-section-label {
            color: #55745E !important;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1.7px;
            margin: 18px 9px 10px;
        }

        /* GENERAL BUTTONS */

        div[data-testid="stButton"] > button,
        div[data-testid="stFormSubmitButton"] > button,
        div[data-testid="stDownloadButton"] > button {
            min-height: 43px;
            border-radius: 11px !important;
            background: var(--paper) !important;
            color: var(--forest) !important;
            border: 1px solid #D2DED2 !important;
            font-size: 13px !important;
            font-weight: 800 !important;
            box-shadow: none !important;
            opacity: 1 !important;
        }

        div[data-testid="stButton"] > button *,
        div[data-testid="stFormSubmitButton"] > button *,
        div[data-testid="stDownloadButton"] > button * {
            color: inherit !important;
            -webkit-text-fill-color: currentColor !important;
            font-weight: 800 !important;
            opacity: 1 !important;
        }

        div[data-testid="stButton"] > button[kind="primary"],
        div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"],
        div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
            background: var(--forest) !important;
            color: white !important;
            border-color: var(--forest) !important;
        }

        div[data-testid="stButton"] > button[kind="primary"] *,
        div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] *,
        div[data-testid="stFormSubmitButton"] > button[kind="primary"] * {
            color: white !important;
            -webkit-text-fill-color: white !important;
        }

        div[data-testid="stButton"] > button:hover,
        div[data-testid="stDownloadButton"] > button:hover {
            border-color: #91AE98 !important;
        }

        /* SIDEBAR NAVIGATION: LIGHT SAGE DEFAULT, SOFT RED ACTIVE */

        /* Streamlit may wrap the actual button in additional elements.
           Descendant selectors intentionally avoid relying on direct-child DOM. */
        [data-testid="stSidebar"] [data-testid="stButton"] button,
        [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"],
        [data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] {
            width: 100% !important;
            min-height: 46px !important;
            padding: 11px 14px !important;
            margin: 4px 0 !important;
            background: #E5EEE3 !important;
            background-color: #E5EEE3 !important;
            color: #174D36 !important;
            -webkit-text-fill-color: #174D36 !important;
            border: 1px solid #D1DFD0 !important;
            border-radius: 11px !important;
            font-size: 13px !important;
            font-weight: 800 !important;
            text-align: left !important;
            box-shadow: none !important;
            opacity: 1 !important;
            transition: background-color .18s ease, border-color .18s ease !important;
        }

        [data-testid="stSidebar"] [data-testid="stButton"] button *,
        [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] *,
        [data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] * {
            color: #174D36 !important;
            -webkit-text-fill-color: #174D36 !important;
            font-weight: 800 !important;
            opacity: 1 !important;
        }

        [data-testid="stSidebar"] [data-testid="stButton"] button:hover,
        [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"]:hover {
            background: #D9E8D7 !important;
            background-color: #D9E8D7 !important;
            border-color: #BFD4BF !important;
        }

        /* Active page uses Streamlit's primary button type. */
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
        [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
            background: #F8DCDD !important;
            background-color: #F8DCDD !important;
            border: 1px solid #EBC4C7 !important;
            color: #963B45 !important;
            -webkit-text-fill-color: #963B45 !important;
            font-weight: 800 !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] *,
        [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] * {
            color: #963B45 !important;
            -webkit-text-fill-color: #963B45 !important;
            font-weight: 800 !important;
        }

        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover,
        [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]:hover {
            background: #F3CED1 !important;
            background-color: #F3CED1 !important;
        }

        /* PROFILE */

        .sidebar-bottom {
            border-top: 1px solid var(--line);
            margin-top: 24px;
            padding-top: 13px;
        }

        .profile-card {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 11px;
            background: rgba(255,255,255,.78);
            border: 1px solid var(--line);
            border-radius: 14px;
        }

        .avatar {
            width: 36px;
            height: 36px;
            flex: 0 0 36px;
            display: grid;
            place-items: center;
            border-radius: 50%;
            background: var(--sage);
            color: var(--forest);
            font-weight: 800;
        }

        .profile-copy {
            min-width: 0;
            display: flex;
            flex-direction: column;
        }

        .profile-copy strong {
            color: var(--ink);
            font-size: 11px;
            font-weight: 800;
        }

        .profile-copy span {
            color: var(--muted);
            font-size: 10px;
            overflow-wrap: anywhere;
        }

        /* PAGE HEADINGS */

        .eyebrow {
            color: #557A60 !important;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1.7px;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .page-lead {
            color: #52685A !important;
            font-size: 14px;
            line-height: 1.8;
            max-width: 800px;
            margin-bottom: 1.5rem;
        }

        /* CARDS */

        .hero-panel {
            background: linear-gradient(115deg,#E6EFE4,#F3F3E9) !important;
            border: 1px solid #D8E4D7 !important;
            border-radius: 20px;
            padding: 25px 28px;
            margin: 1.4rem 0 2rem;
        }

        .hero-panel strong {
            color: var(--forest) !important;
            font-size: 16px;
            font-weight: 800;
        }

        .hero-panel p {
            color: #52685A !important;
            font-size: 13px;
        }

        .tool-card, .record-card {
            background: var(--paper) !important;
            border: 1px solid var(--line) !important;
            border-radius: 17px;
            padding: 20px;
            box-shadow: var(--shadow);
            margin-bottom: 12px;
        }

        .tool-icon {
            width: 43px;
            height: 43px;
            display: grid;
            place-items: center;
            background: var(--sage);
            color: var(--forest);
            border-radius: 13px;
            font-size: 20px;
            margin-bottom: 12px;
        }

        .tool-card h3 {
            color: var(--forest) !important;
            font-size: 16px;
            font-weight: 800;
        }

        .tool-card p, .record-card p {
            color: #52685A !important;
            font-size: 12px;
        }

        .note-strip {
            background: var(--sage-light) !important;
            border: 1px solid var(--line) !important;
            border-radius: 16px;
            padding: 17px 20px;
            margin-top: 1.5rem;
        }

        .medical-disclaimer {
            color: #52685A !important;
            font-size: 11px;
            line-height: 1.7;
            margin-top: 20px;
        }

        /* STREAMLIT CONTAINERS */

        [data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--paper) !important;
            border: 1px solid var(--line) !important;
            border-radius: 16px !important;
            box-shadow: 0 4px 14px rgba(28,55,39,.035) !important;
        }

        [data-testid="stForm"] {
            background: transparent !important;
            border: 0 !important;
            padding: 0 !important;
        }

        /* FORM LABELS */

        [data-testid="stTextInput"] label,
        [data-testid="stTextArea"] label,
        [data-testid="stDateInput"] label,
        [data-testid="stSelectbox"] label,
        [data-testid="stNumberInput"] label,
        [data-testid="stFileUploader"] label {
            color: #304D3A !important;
            font-size: 12px !important;
            font-weight: 800 !important;
        }

        /* TEXT INPUTS */

        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input {
            background: #FFFFFF !important;
            color: #26372E !important;
            -webkit-text-fill-color: #26372E !important;
            border: 1px solid #C9D8C9 !important;
            border-radius: 10px !important;
            opacity: 1 !important;
        }

        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {
            color: #849187 !important;
            -webkit-text-fill-color: #849187 !important;
            opacity: 1 !important;
        }

        /* Keep authentication fields light, including browser autofill. */
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,
        [data-testid="stForm"] input {
            background-color: #FFFFFF !important;
            color: #26372E !important;
            -webkit-text-fill-color: #26372E !important;
            caret-color: #174D36 !important;
        }

        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        textarea:-webkit-autofill,
        textarea:-webkit-autofill:hover,
        textarea:-webkit-autofill:focus {
            -webkit-text-fill-color: #26372E !important;
            -webkit-box-shadow: 0 0 0 1000px #FFFFFF inset !important;
            box-shadow: 0 0 0 1000px #FFFFFF inset !important;
            caret-color: #174D36 !important;
            transition: background-color 9999s ease-out 0s;
        }

        /* Trash controls use a soft-green surface; the icon stays red. */
        div[data-testid="stButton"]:has(button p) button[aria-label*="Delete"],
        div[data-testid="stButton"]:has(button p) button[title*="Delete"] {
            background: #E5F2E5 !important;
            border-color: #C9E1C9 !important;
            color: #C43D45 !important;
            -webkit-text-fill-color: #C43D45 !important;
        }

        /* SELECTBOX */

        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            background: #FFFFFF !important;
            color: #26372E !important;
            border-color: #C9D8C9 !important;
            border-radius: 10px !important;
            box-shadow: none !important;
        }

        [data-testid="stSelectbox"] [data-baseweb="select"] *,
        [data-testid="stMultiSelect"] [data-baseweb="select"] * {
            color: #26372E !important;
            -webkit-text-fill-color: #26372E !important;
        }

        [data-baseweb="popover"],
        [data-baseweb="menu"],
        [role="listbox"] {
            background: #FFFFFF !important;
            color: #26372E !important;
        }

        [role="option"] {
            background: #FFFFFF !important;
            color: #26372E !important;
        }

        [role="option"]:hover,
        [aria-selected="true"] {
            background: #E4EDE2 !important;
            color: #174D36 !important;
        }

        /* DATE PICKER */

        [data-testid="stDateInput"] > div > div {
            background: #FFFFFF !important;
            border-color: #C9D8C9 !important;
        }

        [data-testid="stDateInput"] button {
            color: #174D36 !important;
        }

        /* EXPANDERS */

        [data-testid="stExpander"] {
            background: #FFFEFA !important;
            border: 1px solid #DDE5DB !important;
            border-radius: 13px !important;
            overflow: hidden;
        }

        [data-testid="stExpander"] details {
            background: #FFFEFA !important;
        }

        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary:hover {
            background: #EAF2E8 !important;
            color: #174D36 !important;
            border-radius: 12px !important;
        }

        [data-testid="stExpander"] summary * {
            color: #174D36 !important;
            -webkit-text-fill-color: #174D36 !important;
            font-weight: 800 !important;
        }

        [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            background: #FFFEFA !important;
            color: #26372E !important;
        }

        /* ALERTS AND EMPTY STATES */

        [data-testid="stAlert"],
        [data-testid="stAlert"] > div {
            background: #EAF2E8 !important;
            border: 1px solid #D3E2D1 !important;
            border-radius: 13px !important;
            color: #294F37 !important;
        }

        [data-testid="stAlert"] *,
        [data-testid="stAlert"] p,
        [data-testid="stAlert"] span {
            color: #294F37 !important;
            -webkit-text-fill-color: #294F37 !important;
            opacity: 1 !important;
        }

        [data-testid="stAlert"][kind="warning"] {
            background: #F7F0DF !important;
            border-color: #E8DAB9 !important;
        }

        [data-testid="stAlert"][kind="error"] {
            background: #F9EAEA !important;
            border-color: #EBCACA !important;
        }

        [data-testid="stAlert"][kind="success"] {
            background: #E8F2E8 !important;
            border-color: #CFE1D0 !important;
        }

        .empty-state,
        .empty-state-message,
        .no-records,
        .no-data,
        .empty-message {
            background: #EAF2E8 !important;
            color: #294F37 !important;
            border: 1px solid #D3E2D1 !important;
            border-radius: 12px !important;
            padding: 15px 18px !important;
        }

        .empty-state *,
        .empty-state-message *,
        .no-records *,
        .no-data *,
        .empty-message * {
            color: #294F37 !important;
            -webkit-text-fill-color: #294F37 !important;
            opacity: 1 !important;
        }

        /* METRICS */

        [data-testid="stMetric"] {
            background: var(--paper) !important;
            border: 1px solid var(--line) !important;
            padding: 14px 16px;
            border-radius: 14px;
        }

        [data-testid="stMetricLabel"] {
            color: #52685A !important;
            font-weight: 700 !important;
        }

        [data-testid="stMetricValue"] {
            color: var(--forest) !important;
            font-weight: 800 !important;
        }

        /* TABS */

        [data-testid="stTabs"] [role="tablist"] {
            border-bottom: 1px solid #DDE5DB;
            gap: 12px;
        }

        [data-testid="stTabs"] button[role="tab"] {
            color: #52685A !important;
            font-weight: 700 !important;
        }

        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: #174D36 !important;
            border-bottom-color: #174D36 !important;
        }

        /* FILE UPLOADER */

        [data-testid="stFileUploader"] section {
            background: #FFFFFF !important;
            border: 1px dashed #B9CCBA !important;
            border-radius: 13px !important;
        }

        [data-testid="stFileUploader"] section * {
            color: #304D3A !important;
        }

        [data-testid="stFileUploader"] button {
            background: #174D36 !important;
            color: #FFFFFF !important;
            border-color: #174D36 !important;
        }

        /* CHAT MESSAGES */

        div[data-testid="stChatMessage"] {
            max-width: 94%;
            background: #FFFEFA !important;
            border: 1px solid #DDE5DB !important;
            border-radius: 15px !important;
            padding: 13px 16px !important;
            margin-bottom: 12px;
            box-shadow: 0 4px 12px rgba(28,55,39,.04);
        }

        div[data-testid="stChatMessage"] p {
            color: #26372E !important;
            font-size: 14px !important;
            line-height: 1.7 !important;
        }

        /* CHAT INPUT */

        [data-testid="stChatInput"],
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] > div > div {
            background: #FFFFFF !important;
            border: 1px solid #C9D8C9 !important;
            border-radius: 13px !important;
            box-shadow: none !important;
        }

        [data-testid="stChatInput"] textarea {
            background: #FFFFFF !important;
            color: #26372E !important;
            -webkit-text-fill-color: #26372E !important;
            caret-color: #174D36 !important;
        }

        [data-testid="stChatInput"] button {
            background: #174D36 !important;
            color: #FFFFFF !important;
            border-radius: 10px !important;
        }

        /* CONSULTATION HISTORY */

        .history-panel-heading {
            color: #174D36;
            font-size: 17px;
            font-weight: 800;
            margin: 4px 0;
        }

        .history-panel-caption {
            color: #52685A;
            font-size: 12px;
            line-height: 1.6;
            margin-bottom: 14px;
        }

        .history-item-title {
            color: #20392B;
            font-size: 13px;
            font-weight: 800;
            line-height: 1.5;
            overflow-wrap: anywhere;
        }

        .history-item-date {
            color: #64746A;
            font-size: 11px;
            margin: 6px 0 12px;
        }

        .history-empty {
            background: #FFFEFA;
            border: 1px dashed #C9D8C9;
            border-radius: 14px;
            padding: 18px;
            margin-top: 14px;
        }

        .history-empty strong {
            color: #174D36;
            font-size: 13px;
            font-weight: 800;
        }

        .history-empty p {
            color: #52685A;
            font-size: 12px;
            margin: 7px 0 0;
        }

        /* CHAT HEADER */

        .careai-chat-header {
            display: flex;
            align-items: center;
            gap: 12px;
            background: #FFFEFA;
            border: 1px solid #DDE5DB;
            border-radius: 16px 16px 0 0;
            padding: 15px 18px;
        }

        .careai-chat-logo {
            width: 40px;
            height: 40px;
            flex: 0 0 40px;
            display: grid;
            place-items: center;
            background: #174D36;
            color: #FFFFFF;
            font-size: 25px;
            font-weight: 800;
            border-radius: 12px;
        }

        .careai-chat-name {
            color: #174D36;
            font-size: 14px;
            font-weight: 800;
        }

        .careai-chat-status {
            color: #52685A;
            font-size: 11px;
            margin-top: 3px;
        }

        .careai-chat-label {
            margin-left: auto;
            color: #557A60;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 1.2px;
        }

        /* EMPTY CHAT */

        .chat-empty-state {
            background: #FFFEFA;
            border: 1px solid #DDE5DB;
            border-top: 0;
            border-radius: 0 0 16px 16px;
            padding: 55px 28px;
            text-align: center;
        }

        .chat-empty-mark {
            width: 55px;
            height: 55px;
            display: grid;
            place-items: center;
            margin: 0 auto 18px;
            border-radius: 17px;
            background: #E4EDE2;
            color: #174D36;
            font-size: 30px;
            font-weight: 800;
        }

        .chat-empty-state h2 {
            color: #174D36;
            font-size: 25px;
        }

        .chat-empty-state p {
            max-width: 520px;
            margin: 12px auto;
            color: #52685A;
            font-size: 13px;
            line-height: 1.8;
        }

        .chat-empty-foot {
            color: #557A60;
            font-size: 11px;
            font-weight: 700;
            margin-top: 22px;
        }

        .summary-notice {
            background: #EAF2E8 !important;
            border: 1px solid #D5E2D4 !important;
            border-radius: 12px;
            padding: 14px 16px;
            color: #315A3D !important;
            font-size: 12px;
            line-height: 1.7;
            margin: 12px 0 18px;
        }

        .consult-disclaimer {
            color: #52685A !important;
            font-size: 11px;
            line-height: 1.7;
            margin: 12px 0;
        }

        /* GENERAL TEXT VISIBILITY */

        [data-testid="stVerticalBlockBorderWrapper"] p,
        [data-testid="stVerticalBlockBorderWrapper"] span,
        [data-testid="stVerticalBlockBorderWrapper"] li {
            color: #405648 !important;
            opacity: 1 !important;
        }

        [data-testid="stCaptionContainer"] p {
            color: #64746A !important;
        }

        hr {
            border-color: #DDE5DB !important;
        }

        /* RESPONSIVE */

        @media(max-width: 900px) {
            [data-testid="stMainBlockContainer"] {
                padding: 1.2rem 1rem 3rem;
            }

            h1 {
                font-size: 2.15rem !important;
            }

            .tool-card {
                padding: 16px;
            }

            .careai-chat-label {
                display: none;
            }

            .chat-empty-state {
                padding: 32px 16px;
            }

            div[data-testid="stChatMessage"] {
                max-width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
