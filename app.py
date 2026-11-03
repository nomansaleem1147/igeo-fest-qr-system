import io
import hashlib
import hmac
import secrets
import uuid
import zipfile
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import qrcode
import streamlit as st
import extra_streamlit_components as stx
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
    st.markdown(f'<div class="hero"><h1>{EVENT}</h1><p>ADMIN & ENTRY MANAGEMENT PORTAL</p></div>', unsafe_allow_html=True)
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

    cookie_manager = stx.CookieManager(key="igeo_fest_scanner_cookie_manager")
    st.session_state["scanner_cookie_manager"] = cookie_manager
    cookie_value = cookie_manager.get(SCANNER_COOKIE_NAME)

    if _valid_scanner_cookie(cookie_value):
        st.session_state["scanner_authenticated"] = True
        return cookie_manager

    st.markdown(f'<div class="hero"><h1>{EVENT}</h1><p>COMMITTEE QR SCANNER</p></div>', unsafe_allow_html=True)
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
            cookie_manager.set(
                SCANNER_COOKIE_NAME,
                _make_scanner_cookie(),
                key="igeo_fest_scanner_auth_set",
                path="/",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=SCANNER_SESSION_HOURS),
                secure=True,
                same_site="lax",
            )
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
    c.setFillColor(gold); c.setFont("Helvetica-Bold", 16); c.drawString(11*mm, h-15*mm, EVENT)
    c.setFillColor(colors.white); c.setFont("Helvetica", 7.5); c.drawString(11*mm, h-21*mm, SUBTITLE)
    c.setFillColor(green); c.roundRect(4*mm, 4*mm, 7*mm, h-36*mm, 2*mm, fill=1, stroke=0)
    c.setFillColor(navy); c.setFont("Helvetica-Bold", 12); c.drawString(15*mm, h-39*mm, str(row.get("full_name", ""))[:34])
    c.setFillColor(green); c.setFont("Helvetica-Bold", 8); c.drawString(15*mm, h-46*mm, str(row.get("attendee_id", ""))[:28])
    c.setFillColor(colors.HexColor("#374151")); c.setFont("Helvetica", 7.5)
    c.drawString(15*mm, h-54*mm, "Category: " + str(row.get("category") or "Guest")[:35])
    c.drawString(15*mm, h-61*mm, "Roll No: " + str(row.get("roll_number") or "—")[:35])
    c.drawString(15*mm, h-68*mm, "Department: " + str(row.get("department") or "—")[:55])
    if row.get("degree"):
        c.drawString(15*mm, h-74*mm, "Degree / Semester: " + str(row.get("degree")) + " / " + str(row.get("semester") or "Alumni")[:30])
    if row.get("fee_amount"):
        c.drawString(15*mm, h-80*mm, "Payment: VERIFIED · PKR " + str(row.get("fee_amount")))
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
        st.markdown(f'<div class="hero"><h1>{EVENT}</h1><p>COMMITTEE TICKET VERIFICATION</p></div>', unsafe_allow_html=True)
    with logout_col:
        st.write("")
        st.write("")
        if st.button("Scanner logout", use_container_width=True):
            cookie_manager = stx.CookieManager(key="igeo_fest_scanner_cookie_manager")
            cookie_manager.delete(SCANNER_COOKIE_NAME, key="igeo_fest_scanner_auth_delete")
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
    if attendee.get("payment_status", "LEGACY_APPROVED") not in ("PAID", "LEGACY_APPROVED"):
        st.error("PAYMENT NOT VERIFIED — This ticket cannot be used for entry.")
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


FEE_BY_DEGREE = {"BS": 4000, "MS": 6000, "PhD": 10000, "Alumni": 6000}
JAZZCASH_ACCOUNT_TITLE = str(get_secret("JAZZCASH_ACCOUNT_TITLE", "") or "")
JAZZCASH_ACCOUNT_NUMBER = str(get_secret("JAZZCASH_ACCOUNT_NUMBER", "") or "")


def public_registration_page():
    """Public student/alumni payment submission. This does NOT verify payment."""
    st.markdown(f'<div class="hero"><h1>{EVENT}</h1><p>STUDENT & ALUMNI REGISTRATION · JAZZCASH</p></div>', unsafe_allow_html=True)
    st.info("Complete this form after making your JazzCash transfer. Your registration and QR ticket will be activated only after the IGEO FEST admin verifies the transaction in the receiving account.")

    if not JAZZCASH_ACCOUNT_NUMBER:
        st.warning("JazzCash receiving account details are not configured yet. Please contact the IGEO FEST registration team.")
    else:
        st.markdown("### JazzCash payment details")
        a, b = st.columns(2)
        a.metric("Account title", JAZZCASH_ACCOUNT_TITLE or "As shown in JazzCash")
        b.metric("JazzCash number", JAZZCASH_ACCOUNT_NUMBER)
        st.caption("Transfer the exact fee and keep your JazzCash transaction reference. Do not share your MPIN or OTP.")

    with st.form("public_payment_submission", clear_on_submit=True):
        degree = st.selectbox("Registration category", ["BS", "MS", "PhD", "Alumni"], format_func=lambda x: {"BS":"BS Student — PKR 4,000", "MS":"MS Student — PKR 6,000", "PhD":"PhD Student — PKR 10,000", "Alumni":"Alumni — PKR 6,000"}[x])
        fee = FEE_BY_DEGREE[degree]
        st.success(f"Registration fee: PKR {fee:,}")
        full_name = st.text_input("Full name *")
        phone = st.text_input("Your mobile number *", placeholder="03XXXXXXXXX")
        email = st.text_input("Email address")
        department = st.text_input("Department")
        if degree == "Alumni":
            semester = ""
            roll_number = st.text_input("Previous registration / roll number (if available)")
            graduation_year = st.text_input("Graduation year / batch")
        else:
            semester = st.text_input("Current semester *", placeholder="e.g. 1st, 2nd, 3rd or 4th")
            roll_number = st.text_input("University registration / roll number *")
            graduation_year = ""
        st.markdown("#### JazzCash transaction information")
        transaction_reference = st.text_input("JazzCash transaction ID / TID *")
        sender_phone = st.text_input("JazzCash sender mobile number", placeholder="03XXXXXXXXX")
        payment_date = st.date_input("Date of payment", value=datetime.now().date())
        submitted = st.form_submit_button("Submit payment details", type="primary", use_container_width=True)

    if submitted:
        errors = []
        if not full_name.strip(): errors.append("Enter your full name.")
        if not phone.strip(): errors.append("Enter your mobile number.")
        if not transaction_reference.strip(): errors.append("Enter the JazzCash transaction ID.")
        if degree != "Alumni" and not semester.strip(): errors.append("Enter your current semester.")
        if degree != "Alumni" and not roll_number.strip(): errors.append("Enter your university registration / roll number.")
        if not JAZZCASH_ACCOUNT_NUMBER: errors.append("Registration is not open because the receiving account is not configured.")
        if errors:
            for error in errors: st.error(error)
            return
        sb = db_client()
        payload = {
            "full_name": full_name.strip(), "degree": degree,
            "semester": semester.strip() or None, "graduation_year": graduation_year.strip() or None,
            "roll_number": roll_number.strip() or None, "department": department.strip() or None,
            "email": email.strip() or None, "phone": phone.strip(), "amount": fee,
            "payment_method": "JazzCash", "transaction_reference": transaction_reference.strip(),
            "sender_phone": sender_phone.strip() or None, "payment_date": payment_date.isoformat(),
            "status": "SUBMITTED"
        }
        try:
            response = sb.table("payment_orders").insert(payload).execute()
            order = (response.data or [{}])[0]
            st.success("Payment details submitted successfully. Your registration is pending admin verification.")
            if order.get("id"):
                st.code(str(order["id"]), language=None)
                st.caption("Save this payment submission ID for follow-up.")
            st.warning("This submission is not yet a confirmed payment and does not activate a QR ticket.")
        except Exception as exc:
            message = str(exc).lower()
            if "duplicate key" in message or "unique" in message:
                st.error("This JazzCash transaction reference has already been submitted. Contact the registration team if you believe this is an error.")
            else:
                st.error(f"Could not submit payment details. Please contact the administrator. Details: {exc}")


def payment_management_tab(sb):
    st.subheader("JazzCash payment verification")
    st.caption("Verify each transaction against the actual receiving JazzCash wallet or official transaction statement before approving it.")
    try:
        pending = sb.table("payment_orders").select("*").eq("status", "SUBMITTED").order("submitted_at", desc=True).limit(500).execute().data or []
        paid = sb.table("payment_orders").select("id,full_name,degree,amount,transaction_reference,attendee_id,verified_at").eq("status", "PAID").order("verified_at", desc=True).limit(500).execute().data or []
        rejected = sb.table("payment_orders").select("id,full_name,degree,amount,transaction_reference,review_note,verified_at").eq("status", "REJECTED").order("verified_at", desc=True).limit(200).execute().data or []
    except Exception as exc:
        st.error(f"Payment tables are not available. Run the payment SQL migration first. Details: {exc}")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Awaiting verification", len(pending))
    m2.metric("Verified payments", len(paid))
    m3.metric("Rejected submissions", len(rejected))

    if pending:
        st.markdown("### Pending submissions")
        display = [{"Submission ID": r.get("id"), "Name": r.get("full_name"), "Category": r.get("degree"), "Semester": r.get("semester") or "—", "Fee (PKR)": r.get("amount"), "Transaction ID": r.get("transaction_reference"), "Sender": r.get("sender_phone") or "—", "Submitted": r.get("submitted_at")} for r in pending]
        st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
        labels = {f"{r.get('full_name')} | {r.get('degree')} | PKR {r.get('amount'):,} | {r.get('transaction_reference')} | {str(r.get('id'))[:8]}": r for r in pending}
        chosen_label = st.selectbox("Select a payment submission to review", list(labels.keys()))
        chosen = labels[chosen_label]
        with st.container(border=True):
            st.markdown(f"**{chosen.get('full_name')}** · {chosen.get('degree')} · PKR {chosen.get('amount'):,}")
            st.write("Roll / registration number:", chosen.get("roll_number") or "—")
            st.write("Department:", chosen.get("department") or "—")
            st.write("Student contact:", chosen.get("phone") or "—")
            st.write("JazzCash transaction reference:", chosen.get("transaction_reference"))
            st.write("Sender number:", chosen.get("sender_phone") or "Not supplied")
            st.write("Payment date:", chosen.get("payment_date") or "—")
            st.warning("Do not approve based on the student's screenshot alone. Confirm the matching credit, exact amount and transaction reference in the receiving JazzCash account.")
            verified = st.checkbox("I independently verified this exact transaction in the JazzCash receiving account.", key=f"verify_{chosen['id']}")
            admin_label = st.text_input("Verified by", value="IGEO FEST Admin", key=f"verifier_{chosen['id']}")
            approve_col, reject_col = st.columns(2)
            with approve_col:
                if st.button("Verify & approve payment", type="primary", disabled=not verified, use_container_width=True, key=f"approve_{chosen['id']}"):
                    raw_token = secrets.token_urlsafe(32)
                    try:
                        result = sb.rpc("approve_igeo_payment", {
                            "p_payment_id": str(chosen["id"]),
                            "p_token_hash": token_hash(raw_token),
                            "p_verified_by": admin_label.strip() or "IGEO FEST Admin"
                        }).execute().data
                        if isinstance(result, list) and result: result = result[0]
                        if isinstance(result, dict) and result.get("status") == "SUCCESS":
                            attendee = {
                                "attendee_id": result["attendee_id"], "full_name": chosen["full_name"],
                                "category": "Alumni" if chosen["degree"] == "Alumni" else chosen["degree"] + " Student",
                                "roll_number": chosen.get("roll_number"), "department": chosen.get("department"),
                                "degree": chosen["degree"], "semester": chosen.get("semester"),
                                "fee_amount": chosen["amount"]
                            }
                            base = app_url()
                            if base:
                                pdf = make_ticket_pdf(attendee, raw_token, base)
                                st.session_state["newly_approved_ticket"] = (attendee["attendee_id"], pdf)
                            st.success(f"Payment verified. Registration created: {attendee['attendee_id']}")
                            if not base: st.warning("Set APP_URL in Streamlit Secrets to create the downloadable QR ticket.")
                            st.rerun()
                        elif isinstance(result, dict) and result.get("status") == "ALREADY_PAID":
                            st.info("This payment was already approved. No duplicate attendee was created.")
                        else:
                            st.error(f"Approval was not completed: {result}")
                    except Exception as exc:
                        st.error(f"Payment approval failed: {exc}")
            with reject_col:
                reason = st.text_input("Rejection reason", key=f"reason_{chosen['id']}")
                if st.button("Reject submission", disabled=not reason.strip(), use_container_width=True, key=f"reject_{chosen['id']}"):
                    try:
                        result = sb.rpc("reject_igeo_payment", {"p_payment_id": str(chosen["id"]), "p_reason": reason.strip(), "p_reviewed_by": admin_label.strip() or "IGEO FEST Admin"}).execute().data
                        st.success("Submission rejected.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not reject submission: {exc}")
    else:
        st.info("There are no payment submissions awaiting verification.")

    ticket = st.session_state.get("newly_approved_ticket")
    if ticket:
        st.markdown("### Newly generated QR ticket")
        st.download_button("Download verified attendee ticket (PDF)", ticket[1], f"{ticket[0]}_IGEO_FEST.pdf", "application/pdf", use_container_width=True)

    with st.expander("Previously verified payments"):
        if paid: st.dataframe(pd.DataFrame(paid), use_container_width=True, hide_index=True)
        else: st.info("No verified payments yet.")
    with st.expander("Rejected submissions"):
        if rejected: st.dataframe(pd.DataFrame(rejected), use_container_width=True, hide_index=True)
        else: st.info("No rejected submissions.")


def admin_dashboard():
    st.markdown(f'<div class="hero"><h1>{EVENT}</h1><p>{SUBTITLE} · PAYMENT & QR ENTRY MANAGEMENT</p></div>', unsafe_allow_html=True)
    st.caption(f"{EVENT_DATE}  |  {EVENT_TIME}  |  {VENUE}")
    registration_link = public_registration_url()
    if registration_link:
        st.markdown("**Public student / alumni registration link**")
        st.code(registration_link, language=None)
        st.caption("Share this link with students. Their registration becomes active only after payment verification.")
    else:
        st.warning("Set APP_URL in Streamlit Secrets to display the public registration link.")
    if st.button("Log out"):
        st.session_state["authenticated"] = False
        st.rerun()

    counts = get_counts()
    cols = st.columns(4)
    for col, label, value in zip(cols, ["REGISTERED", "ACTIVE TICKETS", "CHECKED IN", "REVOKED"], counts.values()):
        col.markdown(f'<div class="metric-card"><div class="metric-num">{value}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)

    tab_payments, tab_import, tab_tickets, tab_register, tab_reports = st.tabs(["Payment verification", "Import attendees", "Generate tickets", "Attendee register", "Reports"])
    sb = db_client()

    with tab_payments:
        payment_management_tab(sb)

    with tab_import:
        st.subheader("Import existing / legacy attendee list")
        st.caption("Imported records are marked LEGACY_APPROVED to preserve the existing attendee workflow. Use payment verification for all new paid registrations.")
        up = st.file_uploader("Upload Excel (.xlsx) or CSV", type=["xlsx", "csv"])
        if up and st.button("Import attendees", type="primary"):
            try:
                headers, data_rows = read_upload(up)
                inserted = 0
                for row in data_rows:
                    full_name = cell_value(headers, row, "full_name")
                    if not full_name: continue
                    aid = cell_value(headers, row, "attendee_id") or "IGEO-" + uuid.uuid4().hex[:10].upper()
                    category = cell_value(headers, row, "category")
                    payload = {
                        "attendee_id": aid, "full_name": full_name,
                        "roll_number": cell_value(headers, row, "roll_number"),
                        "category": category,
                        "degree": category.upper().replace(" STUDENT", "") if category.upper().replace(" STUDENT", "") in ("BS", "MS", "PHD", "ALUMNI") else None,
                        "department": cell_value(headers, row, "department"),
                        "email": cell_value(headers, row, "email"),
                        "phone": cell_value(headers, row, "phone"),
                        "registration_status": "APPROVED", "ticket_status": "NOT_ISSUED",
                        "payment_status": "LEGACY_APPROVED", "revoked": False, "created_at": now_utc()
                    }
                    try:
                        sb.table("attendees").insert(payload).execute(); inserted += 1
                    except Exception:
                        pass
                st.success(f"Imported {inserted} new legacy attendees. Duplicate IDs or roll numbers were skipped.")
            except Exception as e:
                st.error(f"Import failed: {e}")

    with tab_tickets:
        st.subheader("Issue / refresh QR tickets")
        base = app_url()
        if not base:
            st.error("Set APP_URL in Streamlit Secrets to your deployed Streamlit app URL before generating tickets.")
        else:
            st.info(f"QR links will open: {base}")
            if st.button("Generate / Refresh all eligible tickets", type="primary"):
                attendees = sb.table("attendees").select("*").eq("registration_status", "APPROVED").eq("revoked", False).limit(5000).execute().data or []
                attendees = [a for a in attendees if a.get("payment_status", "LEGACY_APPROVED") in ("PAID", "LEGACY_APPROVED")]
                generated = []
                progress = st.progress(0)
                for i, attendee in enumerate(attendees):
                    token = secrets.token_urlsafe(32)
                    sb.table("attendees").update({"token_hash": token_hash(token), "ticket_status": "NOT_USED", "checked_in_at": None, "revoked": False}).eq("attendee_id", attendee["attendee_id"]).execute()
                    pdf = make_ticket_pdf(attendee, token, base)
                    generated.append((attendee["attendee_id"], pdf))
                    progress.progress((i + 1) / max(len(attendees), 1))
                st.session_state["generated_pdfs"] = generated
                st.success(f"Generated {len(generated)} eligible tickets. Previously issued QR codes have been replaced.")

        generated = st.session_state.get("generated_pdfs", [])
        if generated:
            bundle = io.BytesIO()
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
                for aid, pdf in generated: z.writestr(f"{aid}_IGEO_FEST.pdf", pdf)
            st.download_button("Download all tickets (ZIP)", bundle.getvalue(), "IGEO_FEST_All_Tickets.zip", "application/zip", use_container_width=True)
            st.caption(f"{len(generated)} ticket PDFs ready.")
            with st.expander("Download individual tickets"):
                for aid, pdf in generated: st.download_button(f"Download {aid}", pdf, f"{aid}_IGEO_FEST.pdf", "application/pdf", key=f"pdf_{aid}")

    with tab_register:
        st.subheader("Attendee register")
        search = st.text_input("Search name, attendee ID or roll number")
        rows = fetch_attendees(search)
        if rows:
            view = [{k: r.get(k) for k in ["attendee_id", "full_name", "degree", "semester", "roll_number", "category", "department", "fee_amount", "payment_status", "registration_status", "ticket_status", "checked_in_at", "revoked"]} for r in rows]
            df_view = pd.DataFrame(view)
            st.dataframe(df_view, use_container_width=True, hide_index=True)
            st.caption("Select an attendee to revoke a ticket.")
            aid = st.selectbox("Attendee ID", [""] + [r["attendee_id"] for r in rows])
            if aid and st.button("Revoke selected ticket", type="secondary"):
                sb.table("attendees").update({"revoked": True, "token_hash": None, "ticket_status": "REVOKED"}).eq("attendee_id", aid).execute()
                st.success("Ticket revoked."); st.rerun()
            st.markdown("### Category views")
            category = st.selectbox("Filter register", ["All", "BS", "MS", "PhD", "Alumni"])
            if category != "All":
                filtered = df_view[df_view["degree"].fillna("").str.upper() == category]
                st.dataframe(filtered, use_container_width=True, hide_index=True)
        else:
            st.info("No attendees found. Import a legacy list or verify a payment submission first.")

    with tab_reports:
        st.subheader("Financial & attendance reports")
        rows = sb.table("attendees").select("attendee_id,full_name,roll_number,category,degree,semester,department,fee_amount,payment_status,payment_method,registration_status,ticket_status,checked_in_at,revoked").limit(10000).execute().data or []
        df = pd.DataFrame(rows)
        if not df.empty:
            paid_df = df[df["payment_status"].eq("PAID")] if "payment_status" in df else pd.DataFrame()
            total_collected = int(pd.to_numeric(paid_df.get("fee_amount", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
            a, b, c = st.columns(3)
            a.metric("Verified collection", f"PKR {total_collected:,}")
            b.metric("Paid registrations", len(paid_df))
            c.metric("Legacy registrations", int(df["payment_status"].eq("LEGACY_APPROVED").sum()) if "payment_status" in df else 0)
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Attendees")
                if not paid_df.empty: paid_df.to_excel(writer, index=False, sheet_name="Paid Registrations")
            st.download_button("Download financial & attendance Excel", out.getvalue(), "IGEO_FEST_Financial_Attendance.xlsx", use_container_width=True)
            st.dataframe(df, use_container_width=True, hide_index=True)
            if not paid_df.empty and "degree" in paid_df:
                summary = paid_df.groupby("degree", dropna=False).agg(Registrations=("attendee_id", "count"), Collection_PKR=("fee_amount", "sum")).reset_index()
                st.markdown("### Category-wise verified collection")
                st.dataframe(summary, use_container_width=True, hide_index=True)
        else:
            st.info("No attendee records yet.")


def public_registration_url():
    base = app_url()
    return f"{base}/?register=1" if base else ""


# ------------------------------------------------------------
# APP ROUTING
# QR scanner route has its own remembered-device login.
# Admin route retains the regular password-protected dashboard.
# ------------------------------------------------------------
ticket_token = st.query_params.get("ticket")
register_route = st.query_params.get("register")

if ticket_token:
    scanner_login_gate()
    show_ticket_page(str(ticket_token))
elif register_route:
    public_registration_page()
else:
    login_gate()
    admin_dashboard()
