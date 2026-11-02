IGEO FEST 2026 — STREAMLIT CLOUD QR ENTRY SYSTEM
===================================================

WHAT THIS VERSION DOES
- Runs as a public HTTPS website hosted by Streamlit Community Cloud.
- Opens on laptop and mobile from different networks; no shared Wi-Fi required.
- Admin password login.
- Supabase PostgreSQL database stores attendee and check-in records persistently.
- Import attendees from Excel (.xlsx) or CSV.
- Generate professional navy, emerald and gold PDF tickets.
- QR code opens this hosted app directly to the attendee verification page.
- Committee confirms entry; central database updates immediately.
- Repeat scans are rejected as DUPLICATE.
- Revoke tickets and export attendance.

EVENT
IGEO FEST – Annual Dinner & Folk Night
Wednesday, 25 November 2026 | 6:00 PM–10:00 PM
University Main Ground, Arid Agriculture University Rawalpindi

DEFAULT ADMIN PASSWORD
igeo2026
Set/change this in Streamlit Secrets as ADMIN_PASSWORD before deployment.

IMPORTANT SERVICES
1. GitHub: stores your application source code.
2. Streamlit Community Cloud: hosts the website.
3. Supabase: stores persistent attendee and check-in data.

SETUP PART A — SUPABASE DATABASE
1. Visit https://supabase.com and create/sign in to your account.
2. Create a new project. Save the database password securely.
3. Wait until the project is ready.
4. Open SQL Editor in the Supabase dashboard.
5. Open this repository file: sql/supabase_setup.sql
6. Copy all SQL and paste it into Supabase SQL Editor; click RUN.
7. Open Project Settings > API (or API Keys).
8. Copy the Project URL.
9. Copy the service_role key / secret key. Treat it like a password.
   NEVER put this key in GitHub source code or share it publicly.

SETUP PART B — GITHUB
1. Create a new GitHub repository, e.g. igeo-fest-qr-system.
2. Upload all files/folders from this project to the repository root.
3. Ensure app.py and requirements.txt are in the repository root.
4. Ensure sql/supabase_setup.sql is uploaded.
5. Do NOT upload real secrets.toml or any Supabase keys.

SETUP PART C — STREAMLIT CLOUD
1. Visit https://share.streamlit.io and sign in using GitHub.
2. Click Create app.
3. Select your repository, branch main, and app.py as the main file.
4. Open Advanced settings > Secrets.
5. Paste the following TOML, replacing the example values:

ADMIN_PASSWORD = "igeo2026"
APP_URL = "https://YOUR-APP-NAME.streamlit.app"
SUPABASE_URL = "https://YOUR-PROJECT-ID.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "PASTE_YOUR_SERVICE_ROLE_KEY"

6. Choose a memorable app subdomain if available.
7. Click Deploy.
8. Wait for deployment and open the generated HTTPS URL.
9. If the URL differs from APP_URL, update APP_URL in app Secrets and reboot/redeploy.

HOW TO USE
1. Open your Streamlit app URL on laptop or mobile.
2. Enter admin password.
3. Import your approved attendee Excel/CSV list.
4. Open Generate tickets tab.
5. Generate/refresh all tickets.
6. Download all tickets ZIP and print/distribute.
7. Committee scans a ticket using phone camera or any QR app that opens web links.
8. The hosted app opens the ticket page. Enter the admin password if asked.
9. Verify attendee identity and click CONFIRM ENTRY.
10. The database updates. A second scan shows ALREADY CHECKED IN.

IMPORTANT PASSWORD / SCANNER BEHAVIOUR
This starter deployment uses the same admin password to open the portal and
ticket verification page. Share it only with authorized gate committee members.
For a larger event, a separate scanner PIN/role can be added later.

IMPORTANT SECURITY
- The Supabase service-role key bypasses Row Level Security. It must remain
  only in Streamlit Secrets and must never be committed to GitHub.
- Do not publish the secrets file or screenshots containing secret keys.
- Change the default admin password before the event.
- Limit repository write access to trusted organizers.
- This app uses server-side Supabase calls; browser users do not receive the
  database service key.
- Test valid, duplicate, invalid and revoked ticket flows before printing all
  tickets.
- This is a starter deployment package. Complete a full rehearsal and review
  access controls before using real attendee data.

TROUBLESHOOTING
- App says database not configured: check Streamlit Secrets names and values.
- SQL/RPC error: confirm sql/supabase_setup.sql was run in the correct project.
- QR opens wrong app: correct APP_URL in Streamlit Secrets and regenerate tickets.
- Streamlit redeploy: wait for dependency installation; inspect app logs.
- Changes to app.py on GitHub trigger a new deployment.
