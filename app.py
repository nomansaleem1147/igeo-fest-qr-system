import io
import hashlib
import hmac
import secrets
import uuid
import zipfile
import time
import os
import base64
from datetime import datetime, timezone, timedelta

import pandas as pd
import qrcode
import streamlit as st
from openpyxl import load_workbook
from reportlab.lib.pagesizes import A6, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from supabase import create_client

# ------------------------------------------------------------
# IGEO FEST CLOUD QR ENTRY SYSTEM
# Data is stored in Supabase; Streamlit hosts the interface.
# Scanner login is remembered securely for 12 hours per browser.
# ------------------------------------------------------------
st.set_page_config(page_title="IGEO FEST 2026 | QR Entry", page_icon="🎟️", layout="wide")

EVENT = "IGEO FEST 2026"
SUBTITLE = "ANNUAL DINNER & FOLK NIGHT"
EVENT_DATE = "Wednesday, 25 November 2026"
EVENT_TIME = "6:00 PM – 10:00 PM"
VENUE = "University Main Ground, Arid Agriculture University Rawalpindi"

NAVY = "#142B45"
GREEN = "#176B57"
GOLD = "#C6A15B"
CREAM = "#F7F4EC"

SCANNER_COOKIE_NAME = "igeo_fest_scanner_auth"
SCANNER_SESSION_HOURS = 12

# Institutional logos stored in the repository's assets folder.
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
UNIVERSITY_LOGO_PATH = os.path.join(ASSETS_DIR, "university_logo.jpeg")
DEPARTMENT_LOGO_PATH = os.path.join(ASSETS_DIR, "department_logo.jpeg")

GEO_BACKGROUND_PATH = os.path.join(ASSETS_DIR, "geoai_satellite_background.jpg")
try:
    with open(GEO_BACKGROUND_PATH, "rb") as _bg_file:
        GEO_BACKGROUND_B64 = base64.b64encode(_bg_file.read()).decode("ascii")
except OSError:
    GEO_BACKGROUND_B64 = ""


def render_event_header(subtitle):
    """Render the event banner with university and department logos."""
    left, center, right = st.columns([1, 6, 1], vertical_alignment="center")
    with left:
        if os.path.exists(UNIVERSITY_LOGO_PATH):
            st.image(UNIVERSITY_LOGO_PATH, width=104)
    with center:
        st.markdown(
            f'<div class="hero"><h1>{EVENT}</h1><p>{subtitle}</p></div>',
            unsafe_allow_html=True,
        )
    with right:
        if os.path.exists(DEPARTMENT_LOGO_PATH):
            st.image(DEPARTMENT_LOGO_PATH, width=104)


st.markdown(f"""
<style>
:root {{
  --igeo-forest:#07583f; --igeo-green:#13835e; --igeo-teal:#147b83;
  --igeo-navy:#102f50; --igeo-blue:#2674a8; --igeo-gold:#d7ad5c;
  --igeo-ink:#193347; --igeo-muted:#718494; --igeo-line:#dce7e9;
}}
.stApp {{
  background:
    radial-gradient(ellipse at 8% 0%,rgba(20,131,94,.08),transparent 34%),
    linear-gradient(135deg,#f4f8f6 0%,#edf3f4 52%,#f8f7f1 100%);
  color:var(--igeo-ink);
}}
[data-testid="stHeader"] {{ background:rgba(247,250,249,.88); }}
.block-container {{ padding-top:1.05rem; padding-bottom:2.8rem; max-width:1540px; }}
/* Institutional banner with animated Earth-observation imagery */
.hero {{
  position:relative; isolation:isolate; overflow:hidden;
  background-image:linear-gradient(105deg,rgba(4,39,43,.94) 0%,rgba(7,75,62,.84) 53%,rgba(10,67,78,.72) 100%),
    url("data:image/jpeg;base64,{GEO_BACKGROUND_B64}");
  background-size:cover,125% auto; background-position:center,0% 50%;
  animation:geoTerrainPan 32s ease-in-out infinite alternate;
  padding:27px 30px 29px; border-radius:20px; color:white; margin-bottom:18px;
  box-shadow:0 14px 34px rgba(8,54,51,.18); border:1px solid rgba(255,255,255,.24);
  min-height:142px; display:flex; flex-direction:column; justify-content:center;
}}
.hero:before {{
  content:""; position:absolute; inset:0; z-index:-1; opacity:.22;
  background-image:linear-gradient(rgba(197,238,219,.2) 1px,transparent 1px),
    linear-gradient(90deg,rgba(197,238,219,.2) 1px,transparent 1px);
  background-size:42px 42px; mask-image:linear-gradient(90deg,transparent,#000 35%,#000);
}}
.hero:after {{
  content:"🛰️"; position:absolute; z-index:1; top:15px; left:-70px;
  font-size:30px; filter:drop-shadow(0 4px 8px #001c2c99);
  animation:satelliteSweep 18s linear infinite; pointer-events:none;
}}
.hero h1 {{ color:#f5d58e; letter-spacing:2px; margin:0; font-size:clamp(1.55rem,3vw,2.45rem); font-weight:850; text-shadow:0 2px 15px #001c2c88; }}
.hero p {{ margin:8px 0 0; color:#f4fbf7; font-size:.94rem; letter-spacing:1.6px; font-weight:700; }}
[data-testid="stImage"] img {{
  border-radius:50%; background:#fff; padding:5px; border:2px solid rgba(15,105,76,.18);
  box-shadow:0 8px 22px rgba(16,45,67,.15); object-fit:contain;
}}
/* Dashboard metric cards */
.metric-card {{
  background:linear-gradient(145deg,#fff 0%,#f8fbfa 100%); border:1px solid #dce8e4;
  border-top:4px solid var(--igeo-green); border-radius:17px; padding:18px 19px;
  min-height:116px; box-shadow:0 7px 22px rgba(16,45,67,.06);
  transition:transform .2s ease,box-shadow .2s ease;
}}
.metric-card:hover {{ transform:translateY(-4px); box-shadow:0 13px 28px rgba(16,65,54,.12); }}
.metric-card.metric-registered {{ border-top-color:var(--igeo-green); }}
.metric-card.metric-tickets {{ border-top-color:var(--igeo-blue); }}
.metric-card.metric-checked {{ border-top-color:#2a9b83; }}
.metric-card.metric-revoked {{ border-top-color:var(--igeo-gold); }}
.metric-icon {{ font-size:21px; margin-bottom:5px; }}
.metric-num {{ font-size:34px; line-height:1.1; font-weight:850; color:var(--igeo-navy); }}
.metric-label {{ color:#70818c; font-size:10px; font-weight:850; letter-spacing:1.4px; margin-top:7px; }}
.ticket-state {{ padding:14px 16px; border-radius:12px; background:#e5f5ed; color:#126847; font-weight:750; }}
/* Tabs and action controls */
div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
  gap:8px; background:#e7efeb; padding:7px; border-radius:14px; border:1px solid #d9e6df;
}}
div[data-testid="stTabs"] button[data-baseweb="tab"] {{
  background:#fff; border:1px solid #e1e9e5; border-radius:10px; padding:10px 17px;
  color:#405a61; font-weight:750; transition:all .18s ease;
}}
div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {{
  background:linear-gradient(110deg,#07583f,#147b83); color:#fff; border-color:#0d715c;
  box-shadow:0 5px 13px #07583f22;
}}
div[data-testid="stTabs"] button[data-baseweb="tab"] p {{ color:inherit; }}
div.stButton > button,div.stDownloadButton > button,div[data-testid="stFormSubmitButton"] button {{
  border-radius:11px; min-height:43px; font-weight:750; border:0;
  transition:all .18s ease; box-shadow:0 5px 13px rgba(16,45,67,.10);
}}
div.stButton > button[kind="primary"],div[data-testid="stFormSubmitButton"] button[kind="primary"] {{
  background:linear-gradient(110deg,#07583f,#168467); color:#fff;
}}
div.stButton > button[kind="secondary"] {{ background:linear-gradient(110deg,#1d6887,#287da0); color:#fff; }}
div.stDownloadButton > button {{ background:linear-gradient(110deg,#b58a3d,#d7ad5c); color:#183b36; }}
div.stButton > button:hover,div.stDownloadButton > button:hover {{
  filter:brightness(1.06); transform:translateY(-2px); box-shadow:0 9px 19px rgba(16,45,67,.16);
}}
/* Inputs, uploader, data grids and status panels */
div[data-testid="stFileUploader"] section {{
  background:#fff; border:1px dashed #9dbbb0; border-radius:14px;
}}
div[data-testid="stDataFrame"] {{ border:1px solid #dce7e9; border-radius:13px; overflow:hidden; }}
div[data-testid="stAlert"] {{ border-radius:13px; }}
div[data-baseweb="input"] input,div[data-baseweb="select"] > div,
div[data-testid="stTextInput"] input {{ border-radius:10px; }}
h1,h2,h3 {{ color:#103c42; font-weight:800; }}
h2 {{ letter-spacing:-.5px; }}
h3 {{ color:#145b4a; }}
hr {{ border-color:#dce7e9; }}
[data-testid="stCaptionContainer"] {{ color:#728592; }}
[data-testid="stExpander"] {{ background:#fff; border:1px solid #e0e9e5; border-radius:12px; }}
@keyframes geoTerrainPan {{
  0% {{ background-position:center,0% 50%; }}
  100% {{ background-position:center,100% 48%; }}
}}
@keyframes satelliteSweep {{
  0% {{ transform:translateX(0) rotate(-8deg); opacity:0; }}
  8% {{ opacity:1; }}
  90% {{ opacity:1; }}
  100% {{ transform:translateX(115vw) rotate(8deg); opacity:0; }}
}}
@media(max-width:850px) {{
  .hero {{ padding:22px 18px; min-height:125px; }}
  .hero h1 {{ font-size:1.65rem; }}
  .metric-card {{ padding:14px; min-height:100px; }}
  .metric-num {{ font-size:28px; }}
  div[data-testid="stTabs"] [data-baseweb="tab-list"] {{ flex-wrap:wrap; }}
}}
@media(prefers-reduced-motion:reduce) {{
  .hero,.hero:after,.metric-card {{ animation:none!important; transition:none!important; }}
}}
</style>
""", unsafe_allow_html=True)


def get_secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


def db_client():
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error("Cloud database is not configured. Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in Streamlit Secrets.")
        st.stop()
    return create_client(url, key)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def app_url():
    value = get_secret("APP_URL", "")
    return str(value).rstrip("/")


def admin_password():
    return str(get_secret("ADMIN_PASSWORD", ""))


def _scanner_signing_key():
    # A dedicated secret is recommended, but deriving a stable key keeps
    # existing deployments working without requiring another Secrets entry.
    configured = str(get_secret("SCANNER_COOKIE_SECRET", "") or "")
    if not configured:
        configured = admin_password() + "|" + str(get_secret("SUPABASE_SERVICE_ROLE_KEY", "") or "")
    return hashlib.sha256(configured.encode("utf-8")).digest()


def _make_scanner_cookie():
    expires = int(time.time()) + SCANNER_SESSION_HOURS * 60 * 60
    nonce = secrets.token_urlsafe(12)
    payload = f"{expires}.{nonce}"
    signature = hmac.new(_scanner_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _valid_scanner_cookie(value):
    if not value or not isinstance(value, str):
        return False
    try:
        expires_text, nonce, signature = value.split(".", 2)
        expires = int(expires_text)
        if expires <= int(time.time()):
            return False
        payload = f"{expires_text}.{nonce}"
        expected = hmac.new(_scanner_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def login_gate():
    """Password gate for the administration dashboard."""
    if st.session_state.get("authenticated"):
        return
    render_event_header("ADMIN & ENTRY MANAGEMENT PORTAL")
    st.markdown("### Admin sign in")
    st.caption("Enter the event administrator password to open the dashboard.")
    with st.form("login_form"):
        password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if submitted:
        expected = admin_password()
        if expected and secrets.compare_digest(password, expected):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")
    st.stop()


def scanner_login_gate():
    """
    Scanner-only login. A signed, expiring browser cookie remembers the
    committee device, so each QR scan does not ask for the password again.
    """
    # Keep the successful login in this Streamlit session immediately.
    # The signed cookie then carries access across later QR-link page loads.
    if st.session_state.get("scanner_authenticated"):
        return st.session_state.get("scanner_cookie_manager")

    try:
        import extra_streamlit_components as stx
        cookie_manager = stx.CookieManager(key="igeo_fest_scanner_cookie_manager")
    except Exception as exc:
        st.error("The browser cookie component could not be loaded. Scanner login will work for this browser session only.")
        st.caption(f"Cookie component detail: {type(exc).__name__}: {exc}")
        cookie_manager = None
    st.session_state["scanner_cookie_manager"] = cookie_manager
    cookie_value = cookie_manager.get(SCANNER_COOKIE_NAME) if cookie_manager is not None else None

    if _valid_scanner_cookie(cookie_value):
        st.session_state["scanner_authenticated"] = True
        return cookie_manager

    render_event_header("COMMITTEE QR SCANNER")
    st.markdown("### Scanner sign in")
    st.caption(f"Sign in once on this device. Scanner access will remain active for {SCANNER_SESSION_HOURS} hours.")
    with st.form("scanner_login_form"):
        password = st.text_input("Committee / admin password", type="password")
        submitted = st.form_submit_button("Open scanner", type="primary", use_container_width=True)

    if submitted:
        expected = admin_password()
        if expected and secrets.compare_digest(password, expected):
            # Set the browser cookie with a stable path and mobile-friendly
            # SameSite policy. Store session auth before rerunning so the
            # CookieManager component's own rerun cannot lose the button event.
            if cookie_manager is not None:
                try:
                    cookie_manager.set(
                        SCANNER_COOKIE_NAME,
                        _make_scanner_cookie(),
                        key="igeo_fest_scanner_auth_set",
                        path="/",
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=SCANNER_SESSION_HOURS),
                        secure=True,
                        same_site="lax",
                    )
                except Exception as exc:
                    st.warning("Scanner login is active for this browser session, but the 12-hour remember-device cookie could not be saved.")
                    st.caption(f"Cookie detail: {type(exc).__name__}: {exc}")
            st.session_state["scanner_authenticated"] = True
            time.sleep(1.0)  # allow the browser component to finish writing cookie
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")
    st.stop()


def fetch_attendees(search=""):
    sb = db_client()
    q = sb.table("attendees").select("*").order("created_at", desc=True).limit(500)
    if search.strip():
        term = search.strip().replace(",", " ")
        q = q.or_(f"full_name.ilike.%{term}%,attendee_id.ilike.%{term}%,roll_number.ilike.%{term}%")
    return q.execute().data or []


def get_counts():
    sb = db_client()
    rows = sb.table("attendees").select("attendee_id,token_hash,checked_in_at,revoked").limit(10000).execute().data or []
    return {
        "total": len(rows),
        "issued": sum(1 for r in rows if r.get("token_hash") and not r.get("revoked")),
        "checked": sum(1 for r in rows if r.get("checked_in_at")),
        "revoked": sum(1 for r in rows if r.get("revoked")),
    }


def make_ticket_pdf(row, token, base_url):
    out = io.BytesIO()
    w, h = landscape(A6)
    c = canvas.Canvas(out, pagesize=(w, h))
    navy, green, gold, cream = map(colors.HexColor, [NAVY, GREEN, GOLD, CREAM])
    c.setFillColor(cream); c.roundRect(4*mm, 4*mm, w-8*mm, h-8*mm, 4*mm, fill=1, stroke=0)
    c.setFillColor(navy); c.roundRect(4*mm, h-28*mm, w-8*mm, 24*mm, 3*mm, fill=1, stroke=0)

    # University logo on the left and IGEO department logo on the right.
    from reportlab.lib.utils import ImageReader
    if os.path.exists(UNIVERSITY_LOGO_PATH):
        c.drawImage(
            ImageReader(UNIVERSITY_LOGO_PATH),
            8*mm, h-26*mm, width=19*mm, height=19*mm,
            preserveAspectRatio=True, anchor="c", mask="auto"
        )
    if os.path.exists(DEPARTMENT_LOGO_PATH):
        c.drawImage(
            ImageReader(DEPARTMENT_LOGO_PATH),
            w-27*mm, h-26*mm, width=19*mm, height=19*mm,
            preserveAspectRatio=True, anchor="c", mask="auto"
        )

    c.setFillColor(gold); c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w/2, h-15*mm, EVENT)
    c.setFillColor(colors.white); c.setFont("Helvetica", 7.2)
    c.drawCentredString(w/2, h-21*mm, SUBTITLE)
    c.setFillColor(green); c.roundRect(4*mm, 4*mm, 7*mm, h-36*mm, 2*mm, fill=1, stroke=0)
    c.setFillColor(navy); c.setFont("Helvetica-Bold", 12); c.drawString(15*mm, h-39*mm, str(row.get("full_name", ""))[:34])
    c.setFillColor(green); c.setFont("Helvetica-Bold", 8); c.drawString(15*mm, h-46*mm, str(row.get("attendee_id", ""))[:28])
    c.setFillColor(colors.HexColor("#374151")); c.setFont("Helvetica", 7.5)
    c.drawString(15*mm, h-54*mm, "Category: " + str(row.get("category") or "Guest")[:35])
    c.drawString(15*mm, h-61*mm, "Roll No: " + str(row.get("roll_number") or "—")[:35])
    c.drawString(15*mm, h-68*mm, "Department: " + str(row.get("department") or "—")[:55])
    c.setStrokeColor(gold); c.setLineWidth(1.2); c.line(w-43*mm, 9*mm, w-43*mm, h-31*mm)
    qr_img = qrcode.make(f"{base_url}/?ticket={token}")
    qbuf = io.BytesIO(); qr_img.save(qbuf, format="PNG"); qbuf.seek(0)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(qbuf), w-39*mm, (h-32*mm)/2-2*mm, 30*mm, 30*mm)
    c.setFillColor(navy); c.setFont("Helvetica-Bold", 7); c.drawString(15*mm, 12*mm, EVENT_DATE + " | " + EVENT_TIME)
    c.setFillColor(colors.HexColor("#555")); c.setFont("Helvetica", 6); c.drawString(15*mm, 7.5*mm, VENUE[:105])
    c.setFillColor(gold); c.setFont("Helvetica-Bold", 6); c.drawCentredString(w-24*mm, 12*mm, "SCAN TO VERIFY")
    c.save(); out.seek(0)
    return out.getvalue()


def read_upload(upload):
    raw = upload.getvalue()
    name = upload.name.lower()
    if name.endswith(".csv"):
        import csv
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    elif name.endswith(".xlsx"):
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        rows = list(wb.active.iter_rows(values_only=True)); wb.close()
    else:
        raise ValueError("Please upload .xlsx or .csv. Legacy .xls is not supported.")
    if not rows:
        raise ValueError("The uploaded file is empty.")
    headers = [str(x or "").strip().lower() for x in rows[0]]
    return headers, rows[1:]


ALIASES = {
    "attendee_id": ["attendee_id", "student_id", "id"],
    "full_name": ["full_name", "name", "student_name"],
    "roll_number": ["roll_number", "roll no", "roll_no", "registration_number"],
    "category": ["category", "program", "degree"],
    "department": ["department"],
    "email": ["email"],
    "phone": ["phone", "mobile"],
}


def cell_value(headers, row, key):
    for alias in ALIASES[key]:
        if alias in headers:
            i = headers.index(alias)
            if i < len(row) and row[i] is not None:
                return str(row[i]).strip()
    return ""


def show_ticket_page(token):
    sb = db_client()
    hashed = token_hash(token)
    result = sb.table("attendees").select("*").eq("token_hash", hashed).limit(1).execute().data or []

    # Compact scanner header and a logout action for the committee device.
    header_col, logout_col = st.columns([5, 1])
    with header_col:
        render_event_header("COMMITTEE TICKET VERIFICATION")
    with logout_col:
        st.write("")
        st.write("")
        if st.button("Scanner logout", use_container_width=True):
            try:
                import extra_streamlit_components as stx
                cookie_manager = stx.CookieManager(key="igeo_fest_scanner_cookie_manager")
                cookie_manager.delete(SCANNER_COOKIE_NAME, key="igeo_fest_scanner_auth_delete")
            except Exception:
                pass
            st.session_state["scanner_authenticated"] = False
            st.session_state.pop("scanner_cookie_manager", None)
            time.sleep(0.5)
            st.rerun()

    if not result:
        st.error("INVALID TICKET — This QR code is not recognized.")
        return

    attendee = result[0]
    if attendee.get("revoked"):
        st.error("TICKET REVOKED — Do not admit. Contact the event administrator.")
        return
    if attendee.get("registration_status", "APPROVED") != "APPROVED":
        st.error("REGISTRATION NOT APPROVED.")
        return
    if attendee.get("checked_in_at"):
        st.error("ALREADY CHECKED IN")
        st.write("Check-in time:", attendee["checked_in_at"])
        st.write("Attendee:", attendee["full_name"])
        st.write("ID:", attendee["attendee_id"])
        return

    st.success("VALID TICKET — Confirm the student's identity and entry.")
    st.markdown("### Student information")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Attendee:** {attendee['full_name']}")
        st.markdown(f"**Attendee ID:** {attendee['attendee_id']}")
        st.markdown(f"**Category:** {attendee.get('category') or 'Guest'}")
    with c2:
        st.markdown(f"**Roll number:** {attendee.get('roll_number') or '—'}")
        st.markdown(f"**Department:** {attendee.get('department') or '—'}")
        st.markdown(f"**Event date:** {EVENT_DATE}")

    st.warning("Confirm only after checking the student's identity and physical presence.")
    if st.button("CONFIRM ENTRY", type="primary", use_container_width=True):
        # SQL RPC performs atomic check-in to prevent two gate scans admitting twice.
        response = sb.rpc("confirm_igeo_entry", {"p_token_hash": hashed}).execute()
        payload = response.data
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if isinstance(payload, dict):
            status = payload.get("status", "UNKNOWN")
            if status == "VALID":
                st.success("ENTRY CONFIRMED — Attendance has been updated.")
            elif status == "DUPLICATE":
                st.error("ALREADY CHECKED IN — This ticket was already used.")
            elif status == "REVOKED":
                st.error("TICKET REVOKED.")
            else:
                st.error("INVALID OR NOT APPROVED TICKET.")
        else:
            st.error("Could not confirm entry. Check database setup and try again.")
        st.rerun()


def admin_dashboard():
    render_event_header(f"{SUBTITLE} · QR ENTRY MANAGEMENT")
    st.markdown(
        f'<div style="background:#E7F0F2;border:1px solid #D8E4E8;border-radius:12px;'
        f'padding:12px 16px;margin:0 0 12px 0;color:#40566A;">'
        f'<b style="color:#102D43;">EVENT CONTROL CENTER</b><br>'
        f'<span style="font-size:0.88rem;">{EVENT_DATE} &nbsp;|&nbsp; {EVENT_TIME} &nbsp;|&nbsp; {VENUE}</span></div>',
        unsafe_allow_html=True,
    )
    logout_col, spacer_col = st.columns([1, 5])
    with logout_col:
        if st.button("↪  Log out", type="secondary", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()

    st.markdown("### Event overview")
    counts = get_counts()
    cols = st.columns(4)
    metric_specs = [
        ("REGISTERED", "👥", "metric-registered"),
        ("ACTIVE TICKETS", "🎟️", "metric-tickets"),
        ("CHECKED IN", "✓", "metric-checked"),
        ("REVOKED", "⛔", "metric-revoked"),
    ]
    for col, (label, icon, css_class), value in zip(cols, metric_specs, counts.values()):
        col.markdown(
            f'<div class="metric-card {css_class}">'
            f'<div class="metric-icon">{icon}</div>'
            f'<div class="metric-num">{value}</div>'
            f'<div class="metric-label">{label}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("### Management workspace")
    tab_import, tab_tickets, tab_register, tab_reports = st.tabs([
        "📥  Import attendees", "🎟️  Generate tickets",
        "👥  Attendee register", "📊  Reports"
    ])
    sb = db_client()

    with tab_import:
        st.subheader("Import attendee list")
        st.caption("Add approved student and alumni records using an Excel or CSV file.")
        up = st.file_uploader("Upload Excel (.xlsx) or CSV", type=["xlsx", "csv"])
        if up and st.button("Import attendees", type="primary"):
            try:
                headers, data_rows = read_upload(up)
                inserted = 0
                skipped = 0
                errors = []
                for row in data_rows:
                    full_name = cell_value(headers, row, "full_name")
                    if not full_name:
                        continue
                    aid = cell_value(headers, row, "attendee_id") or "IGEO-" + uuid.uuid4().hex[:10].upper()
                    payload = {
                        "attendee_id": aid, "full_name": full_name,
                        "roll_number": cell_value(headers, row, "roll_number"),
                        "category": cell_value(headers, row, "category"),
                        "department": cell_value(headers, row, "department"),
                        "email": cell_value(headers, row, "email"),
                        "phone": cell_value(headers, row, "phone"),
                        "registration_status": "APPROVED", "ticket_status": "NOT_ISSUED",
                        "revoked": False, "created_at": now_utc()
                    }
                    try:
                        sb.table("attendees").insert(payload).execute()
                        inserted += 1
                    except Exception as exc:
                        skipped += 1
                        if len(errors) < 5:
                            errors.append(f"{aid}: {type(exc).__name__}: {exc}")
                st.success(f"Imported {inserted} new attendees. Skipped {skipped} rows.")
                if errors:
                    with st.expander("View first import errors"):
                        for message in errors:
                            st.write(message)
            except Exception as e:
                st.error(f"Import failed: {e}")

    with tab_tickets:
        st.subheader("Issue QR tickets")
        st.caption("Generate printable QR entry tickets for approved attendees.")
        base = app_url()
        if not base:
            st.error("Set APP_URL in Streamlit Secrets to your deployed Streamlit app URL before generating tickets.")
        else:
            st.info(f"QR links will open: {base}")
            st.warning(
                "Refreshing tickets replaces every active QR token and clears previous check-in timestamps. "
                "Use this only when you intentionally want to invalidate all previously issued tickets."
            )
            confirm_refresh = st.checkbox(
                "I understand that existing QR codes will stop working and check-in timestamps will be reset.",
                key="confirm_refresh_all_tickets",
            )
            if st.button(
                "Generate / Refresh all tickets",
                type="primary",
                disabled=not confirm_refresh,
            ):
                attendees = sb.table("attendees").select("*").eq("registration_status", "APPROVED").eq("revoked", False).limit(5000).execute().data or []
                generated = []
                progress = st.progress(0)
                for i, attendee in enumerate(attendees):
                    token = secrets.token_urlsafe(32)
                    sb.table("attendees").update({
                        "token_hash": token_hash(token), "ticket_status": "NOT_USED",
                        "checked_in_at": None, "revoked": False
                    }).eq("attendee_id", attendee["attendee_id"]).execute()
                    pdf = make_ticket_pdf(attendee, token, base)
                    generated.append((attendee["attendee_id"], pdf))
                    progress.progress((i + 1) / max(len(attendees), 1))
                st.session_state["generated_pdfs"] = generated
                st.success(f"Generated {len(generated)} tickets. Previous QR codes are now invalid.")

        generated = st.session_state.get("generated_pdfs", [])
        if generated:
            bundle = io.BytesIO()
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
                for aid, pdf in generated:
                    z.writestr(f"{aid}_IGEO_FEST.pdf", pdf)
            st.download_button("Download all tickets (ZIP)", bundle.getvalue(), "IGEO_FEST_All_Tickets.zip", "application/zip", use_container_width=True)
            st.caption(f"{len(generated)} ticket PDFs ready.")
            with st.expander("Download individual tickets"):
                for aid, pdf in generated:
                    st.download_button(f"Download {aid}", pdf, f"{aid}_IGEO_FEST.pdf", "application/pdf", key=f"pdf_{aid}")

    with tab_register:
        st.subheader("Attendee register")
        st.caption("Search attendee records and manage ticket access.")
        search = st.text_input("Search name, attendee ID or roll number")
        rows = fetch_attendees(search)
        if rows:
            view = [{k: r.get(k) for k in ["attendee_id", "full_name", "roll_number", "category", "department", "registration_status", "ticket_status", "checked_in_at", "revoked"]} for r in rows]
            st.dataframe(pd.DataFrame(view), use_container_width=True, hide_index=True)
            st.caption("Select an attendee to revoke a ticket.")
            aid = st.selectbox("Attendee ID", [""] + [r["attendee_id"] for r in rows])
            if aid and st.button("Revoke selected ticket", type="secondary"):
                sb.table("attendees").update({"revoked": True, "token_hash": None, "ticket_status": "REVOKED"}).eq("attendee_id", aid).execute()
                st.success("Ticket revoked.")
                st.rerun()
        else:
            st.info("No attendees found. Import an attendee list first.")

    with tab_reports:
        st.subheader("Attendance export")
        st.caption("Review attendance information and export the event register.")
        rows = sb.table("attendees").select("attendee_id,full_name,roll_number,category,department,registration_status,ticket_status,checked_in_at,revoked").limit(10000).execute().data or []
        df = pd.DataFrame(rows)
        if not df.empty:
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Attendance")
            st.download_button("Download attendance Excel", out.getvalue(), "IGEO_FEST_Attendance.xlsx", use_container_width=True)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No attendee records yet.")


# ------------------------------------------------------------
# APP ROUTING
# QR scanner route has its own remembered-device login.
# Admin route retains the regular password-protected dashboard.
# ------------------------------------------------------------
ticket_token = st.query_params.get("ticket")

try:
    if ticket_token:
        scanner_login_gate()
        show_ticket_page(str(ticket_token))
    else:
        login_gate()
        admin_dashboard()
except Exception as exc:
    st.error("IGEO FEST could not complete this request.")
    st.markdown("**Diagnostic information**")
    st.code(f"{type(exc).__name__}: {exc}")
    st.info(
        "If this happened on Streamlit Cloud, open Manage app → Logs and check the first "
        "red traceback. Never share Streamlit Secrets or your Supabase service-role key."
    )
