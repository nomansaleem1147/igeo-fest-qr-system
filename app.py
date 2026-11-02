import io
import hashlib
import secrets
import uuid
import zipfile
from datetime import datetime, timezone

import pandas as pd
import qrcode
import streamlit as st
from openpyxl import load_workbook, Workbook
from reportlab.lib.pagesizes import A6, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from supabase import create_client

# ------------------------------------------------------------
# IGEO FEST CLOUD QR ENTRY SYSTEM
# Data is stored in Supabase; Streamlit hosts the interface.
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

st.markdown(f"""
<style>
.stApp {{ background:#f3f5f7; color:#263648; }}
.block-container {{ padding-top:1.2rem; max-width:1450px; }}
.hero {{ background:linear-gradient(110deg,{NAVY},{GREEN}); padding:22px 28px; border-radius:15px; color:white; margin-bottom:18px; }}
.hero h1 {{ color:#e6c982; letter-spacing:2px; margin:0; }}
.hero p {{ margin:5px 0 0; color:#f4f5f6; }}
.metric-card {{ background:white; border:1px solid #e6ebef; border-radius:13px; padding:16px; }}
.metric-num {{ font-size:30px; font-weight:800; color:{NAVY}; }}
.metric-label {{ color:#718096; font-size:12px; }}
.ticket-state {{ padding:14px 16px; border-radius:10px; background:#e8f3ed; color:{GREEN}; font-weight:700; }}
div.stButton > button {{ border-radius:8px; font-weight:650; }}
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

def login_gate():
    if st.session_state.get("authenticated"):
        return
    st.markdown(f'<div class="hero"><h1>{EVENT}</h1><p>ADMIN & ENTRY MANAGEMENT PORTAL</p></div>', unsafe_allow_html=True)
    st.markdown("### Admin sign in")
    st.caption("Enter the event administrator password to open the dashboard and ticket verification pages.")
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

def fetch_attendees(search=""):
    sb = db_client()
    q = sb.table("attendees").select("*").order("created_at", desc=True).limit(500)
    if search.strip():
        term = search.strip().replace(",", " ")
        # Search by common exact/prefix fields; broad server-side OR filter.
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
    c.setFillColor(cream); c.roundRect(4*mm,4*mm,w-8*mm,h-8*mm,4*mm,fill=1,stroke=0)
    c.setFillColor(navy); c.roundRect(4*mm,h-28*mm,w-8*mm,24*mm,3*mm,fill=1,stroke=0)
    c.setFillColor(gold); c.setFont("Helvetica-Bold",16); c.drawString(11*mm,h-15*mm,EVENT)
    c.setFillColor(colors.white); c.setFont("Helvetica",7.5); c.drawString(11*mm,h-21*mm,SUBTITLE)
    c.setFillColor(green); c.roundRect(4*mm,4*mm,7*mm,h-36*mm,2*mm,fill=1,stroke=0)
    c.setFillColor(navy); c.setFont("Helvetica-Bold",12); c.drawString(15*mm,h-39*mm,str(row.get("full_name",""))[:34])
    c.setFillColor(green); c.setFont("Helvetica-Bold",8); c.drawString(15*mm,h-46*mm,str(row.get("attendee_id",""))[:28])
    c.setFillColor(colors.HexColor("#374151")); c.setFont("Helvetica",7.5)
    c.drawString(15*mm,h-54*mm,"Category: "+str(row.get("category") or "Guest")[:35])
    c.drawString(15*mm,h-61*mm,"Roll No: "+str(row.get("roll_number") or "—")[:35])
    c.drawString(15*mm,h-68*mm,"Department: "+str(row.get("department") or "—")[:55])
    c.setStrokeColor(gold); c.setLineWidth(1.2); c.line(w-43*mm,9*mm,w-43*mm,h-31*mm)
    qr_img = qrcode.make(f"{base_url}/?ticket={token}")
    qbuf = io.BytesIO(); qr_img.save(qbuf, format="PNG"); qbuf.seek(0)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(qbuf),w-39*mm,(h-32*mm)/2-2*mm,30*mm,30*mm)
    c.setFillColor(navy); c.setFont("Helvetica-Bold",7); c.drawString(15*mm,12*mm,EVENT_DATE+" | "+EVENT_TIME)
    c.setFillColor(colors.HexColor("#555")); c.setFont("Helvetica",6); c.drawString(15*mm,7.5*mm,VENUE[:105])
    c.setFillColor(gold); c.setFont("Helvetica-Bold",6); c.drawCentredString(w-24*mm,12*mm,"SCAN TO VERIFY")
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
    if not rows: raise ValueError("The uploaded file is empty.")
    headers = [str(x or "").strip().lower() for x in rows[0]]
    return headers, rows[1:]

ALIASES = {
    "attendee_id":["attendee_id","student_id","id"],
    "full_name":["full_name","name","student_name"],
    "roll_number":["roll_number","roll no","roll_no","registration_number"],
    "category":["category","program","degree"],
    "department":["department"], "email":["email"], "phone":["phone","mobile"]
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
    st.markdown(f'<div class="hero"><h1>{EVENT}</h1><p>TICKET VERIFICATION</p></div>', unsafe_allow_html=True)
    if not result:
        st.error("INVALID TICKET — This QR code is not recognized.")
        return
    attendee = result[0]
    if attendee.get("revoked"):
        st.error("TICKET REVOKED — Do not admit. Contact the event administrator.")
        return
    if attendee.get("registration_status","APPROVED") != "APPROVED":
        st.error("REGISTRATION NOT APPROVED.")
        return
    if attendee.get("checked_in_at"):
        st.error("ALREADY CHECKED IN")
        st.write("Check-in time:", attendee["checked_in_at"])
        st.write("Attendee:", attendee["full_name"])
        st.write("ID:", attendee["attendee_id"])
        return
    st.success("TICKET FOUND — Review attendee information before confirming entry.")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown(f"**Attendee:** {attendee['full_name']}")
        st.markdown(f"**Attendee ID:** {attendee['attendee_id']}")
        st.markdown(f"**Category:** {attendee.get('category') or 'Guest'}")
    with c2:
        st.markdown(f"**Roll number:** {attendee.get('roll_number') or '—'}")
        st.markdown(f"**Department:** {attendee.get('department') or '—'}")
        st.markdown(f"**Event date:** {EVENT_DATE}")
    st.warning("Confirm only after checking the attendee's identity and physical presence.")
    if st.button("CONFIRM ENTRY", type="primary", use_container_width=True):
        # SQL RPC performs atomic check-in to prevent two gate scans admitting twice.
        response = sb.rpc("confirm_igeo_entry", {"p_token_hash": hashed}).execute()
        payload = response.data
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if isinstance(payload, dict):
            status = payload.get("status","UNKNOWN")
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
    st.markdown(f'<div class="hero"><h1>{EVENT}</h1><p>{SUBTITLE} · QR ENTRY MANAGEMENT</p></div>', unsafe_allow_html=True)
    st.caption(f"{EVENT_DATE}  |  {EVENT_TIME}  |  {VENUE}")
    if st.button("Log out"):
        st.session_state["authenticated"] = False
        st.rerun()

    counts = get_counts()
    cols = st.columns(4)
    for col, label, value in zip(cols, ["REGISTERED","ACTIVE TICKETS","CHECKED IN","REVOKED"], counts.values()):
        col.markdown(f'<div class="metric-card"><div class="metric-num">{value}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)

    tab_import, tab_tickets, tab_register, tab_reports = st.tabs(["Import attendees","Generate tickets","Attendee register","Reports"])
    sb = db_client()
    with tab_import:
        st.subheader("Import attendee list")
        up = st.file_uploader("Upload Excel (.xlsx) or CSV", type=["xlsx","csv"])
        if up and st.button("Import attendees", type="primary"):
            try:
                headers, data_rows = read_upload(up)
                inserted = 0
                for row in data_rows:
                    full_name = cell_value(headers,row,"full_name")
                    if not full_name: continue
                    aid = cell_value(headers,row,"attendee_id") or "IGEO-"+uuid.uuid4().hex[:10].upper()
                    payload = {
                        "attendee_id":aid, "full_name":full_name,
                        "roll_number":cell_value(headers,row,"roll_number"),
                        "category":cell_value(headers,row,"category"),
                        "department":cell_value(headers,row,"department"),
                        "email":cell_value(headers,row,"email"), "phone":cell_value(headers,row,"phone"),
                        "registration_status":"APPROVED", "ticket_status":"NOT_ISSUED",
                        "revoked":False, "created_at":now_utc()
                    }
                    try:
                        sb.table("attendees").insert(payload).execute(); inserted += 1
                    except Exception:
                        pass
                st.success(f"Imported {inserted} new attendees. Duplicate IDs were skipped.")
            except Exception as e:
                st.error(f"Import failed: {e}")
    with tab_tickets:
        st.subheader("Issue QR tickets")
        base = app_url()
        if not base:
            st.error("Set APP_URL in Streamlit Secrets to your deployed Streamlit app URL before generating tickets.")
        else:
            st.info(f"QR links will open: {base}")
            if st.button("Generate / Refresh all tickets", type="primary"):
                attendees = sb.table("attendees").select("*").eq("registration_status","APPROVED").eq("revoked",False).limit(5000).execute().data or []
                generated = []
                progress = st.progress(0)
                for i, attendee in enumerate(attendees):
                    token = secrets.token_urlsafe(32)
                    sb.table("attendees").update({
                        "token_hash":token_hash(token), "ticket_status":"NOT_USED",
                        "checked_in_at":None, "revoked":False
                    }).eq("attendee_id",attendee["attendee_id"]).execute()
                    pdf = make_ticket_pdf(attendee,token,base)
                    generated.append((attendee["attendee_id"],pdf))
                    progress.progress((i+1)/max(len(attendees),1))
                st.session_state["generated_pdfs"] = generated
                st.success(f"Generated {len(generated)} tickets. Previous QR codes are now invalid.")
        generated = st.session_state.get("generated_pdfs", [])
        if generated:
            bundle=io.BytesIO()
            with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
                for aid,pdf in generated: z.writestr(f"{aid}_IGEO_FEST.pdf",pdf)
            st.download_button("Download all tickets (ZIP)",bundle.getvalue(),"IGEO_FEST_All_Tickets.zip","application/zip",use_container_width=True)
            st.caption(f"{len(generated)} ticket PDFs ready.")
            with st.expander("Download individual tickets"):
                for aid,pdf in generated:
                    st.download_button(f"Download {aid}",pdf,f"{aid}_IGEO_FEST.pdf","application/pdf",key=f"pdf_{aid}")
    with tab_register:
        st.subheader("Attendee register")
        search=st.text_input("Search name, attendee ID or roll number")
        rows=fetch_attendees(search)
        if rows:
            view=[{k:r.get(k) for k in ["attendee_id","full_name","roll_number","category","department","registration_status","ticket_status","checked_in_at","revoked"]} for r in rows]
            st.dataframe(pd.DataFrame(view),use_container_width=True,hide_index=True)
            st.caption("Select an attendee to revoke a ticket.")
            aid=st.selectbox("Attendee ID",[""]+[r["attendee_id"] for r in rows])
            if aid and st.button("Revoke selected ticket",type="secondary"):
                sb.table("attendees").update({"revoked":True,"token_hash":None,"ticket_status":"REVOKED"}).eq("attendee_id",aid).execute()
                st.success("Ticket revoked."); st.rerun()
        else:
            st.info("No attendees found. Import an attendee list first.")
    with tab_reports:
        st.subheader("Attendance export")
        rows=sb.table("attendees").select("attendee_id,full_name,roll_number,category,department,registration_status,ticket_status,checked_in_at,revoked").limit(10000).execute().data or []
        df=pd.DataFrame(rows)
        if not df.empty:
            out=io.BytesIO()
            with pd.ExcelWriter(out,engine="openpyxl") as writer: df.to_excel(writer,index=False,sheet_name="Attendance")
            st.download_button("Download attendance Excel",out.getvalue(),"IGEO_FEST_Attendance.xlsx",use_container_width=True)
            st.dataframe(df,use_container_width=True,hide_index=True)
        else:
            st.info("No attendee records yet.")

# App flow: QR query opens ticket detail; otherwise admin portal.
login_gate()
ticket_token = st.query_params.get("ticket")
if ticket_token:
    show_ticket_page(str(ticket_token))
else:
    admin_dashboard()
