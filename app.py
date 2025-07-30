from eventlet import monkey_patch
monkey_patch()
from flask import Flask, redirect, url_for, session, request, render_template, jsonify
import os
import json 
import ast
from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_DISCOVERY_URL,
    SECRET_KEY,
    ADMIN_ID,
    ADMIN_PASSWORD,
    MAIL_ID,
    MAIL_APP_PASSWORD
)
from oauthlib.oauth2 import WebApplicationClient
import requests
import json
import pandas as pd
import qrcode
import csv
from email.message import EmailMessage
import smtplib
import cv2
from datetime import datetime
from flask_socketio import SocketIO, emit

socketio = SocketIO(cors_allowed_origins="*")


# ---- Flask & OAuth Setup ----
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # allow multiple connections
app.secret_key = SECRET_KEY
client = WebApplicationClient(GOOGLE_CLIENT_ID)

RESPONSES_FILE = 'responses.csv'
STATUS_FILE = 'qr_status.csv'
ATTENDANCE_FILE = 'attendance.csv'

# ---- Google OAuth Functions ----
def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

@app.route("/")
def index():
    return render_template("index.html", user=session.get("user"))

@app.route("/login")
def login():
    google_provider_cfg = get_google_provider_cfg()
    auth_endpoint = google_provider_cfg["authorization_endpoint"]

    request_uri = client.prepare_request_uri(
        auth_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)

@app.route("/login/callback")
def callback():
    code = request.args.get("code")
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]

    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code,
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )
    client.parse_request_body_response(json.dumps(token_response.json()))

    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    userinfo = userinfo_response.json()

    full_name = userinfo.get("name", "Unknown User")
    given_name = userinfo.get("given_name", "")
    family_name = userinfo.get("family_name", "")

    session["user"] = {
        "name": f"{given_name} {family_name}".strip() if given_name else full_name,
        "email": userinfo.get("email", "no-email@example.com"),
        "picture": userinfo.get("picture", "")
    }

    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---- Admin Login System ----
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["admin_id"] == ADMIN_ID and request.form["admin_password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin-dashboard")
        else:
            return render_template("admin_login.html", error="Invalid credentials")
    return render_template("admin_login.html")

@app.route("/admin-logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin-login")

@app.route("/admin-dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin-login")

    df = pd.read_csv(RESPONSES_FILE)
    qr_status = get_qr_status()
    
    # Check if attendance exists
    if os.path.exists(ATTENDANCE_FILE):
        attendance_df = pd.read_csv(ATTENDANCE_FILE)
    else:
        attendance_df = pd.DataFrame(columns=["Email", "Time"])

    participants = []

    for _, row in df.iterrows():
        email = row['Email']
        status = qr_status.get(email, 'Pending')
        
        # Get time from attendance if available
        time = ""
        att_row = attendance_df[attendance_df["Email"] == email]
        if not att_row.empty:
            time = att_row.iloc[0].get("Time", "")
        
        participants.append({
            "Name": row.get("Name", ""),
            "Email": email,
            "Department": row.get("Department", ""),
            "College": row.get("College", ""),
            "Year": row.get("Year", ""),
            "status": status,
            "Time": time
        })

    return render_template("admin_dashboard.html", participants=participants)

# ---- QR Code Mail System ----
def get_qr_status():
    if not os.path.exists(STATUS_FILE):
        return {}
    df = pd.read_csv(STATUS_FILE)
    return dict(zip(df['Email'], df['Status']))

def update_qr_status(email):
    status = get_qr_status()
    status[email] = 'Sent'
    with open(STATUS_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Email', 'Status'])
        for k, v in status.items():
            writer.writerow([k, v])

def generate_qr(data_str, email):
    clean_data = data_str.encode('utf-8', 'ignore').decode('utf-8')
    qr = qrcode.make(clean_data)
    qr_folder = 'static/qr_codes'
    os.makedirs(qr_folder, exist_ok=True)
    file_path = os.path.join(qr_folder, f"{email}.png")
    qr.save(file_path)
    return file_path

def send_qr_mail(to_email, qr_path):
    msg = EmailMessage()
    msg['Subject'] = "Your Symposium QR Code"
    msg['From'] = MAIL_ID
    msg['To'] = to_email
    msg.set_content("Attached is your QR code for symposium check-in.")

    with open(qr_path, 'rb') as f:
        file_data = f.read()
        file_name = os.path.basename(qr_path)
    msg.add_attachment(file_data, maintype='image', subtype='png', filename=file_name)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(MAIL_ID, MAIL_APP_PASSWORD)
        smtp.send_message(msg)

@app.route("/generate-mail", methods=["POST"])
def generate_mail():
    if not session.get("admin"):
        return redirect("/admin-login")

    email = request.form["email"]

    # Load full participant details from responses.csv using the email
    df = pd.read_csv(RESPONSES_FILE)
    if email not in df['Email'].values:
        return f"Email {email} not found in responses"

    user = df[df['Email'] == email].iloc[0]
    participant_info = {
        "Name": user.get("Name", ""),
        "Email": user.get("Email", ""),
        "Department": user.get("Department", ""),
        "Year": user.get("Year", "")
    }

    # Now encode as clean JSON
    qr_data = json.dumps(participant_info, ensure_ascii=False)
    qr_path = generate_qr(qr_data, email)
    send_qr_mail(email, qr_path)
    update_qr_status(email)
    return redirect("/admin-dashboard")


# ---- Attendance System ----
def load_responses():
    if os.path.exists(RESPONSES_FILE):
        return pd.read_csv(RESPONSES_FILE)
    return pd.DataFrame()

def mark_attendance(email):
    df = pd.read_csv(RESPONSES_FILE)
    if email not in df['Email'].values:
        return "Email not found"

    if os.path.exists(ATTENDANCE_FILE):
        attendance_df = pd.read_csv(ATTENDANCE_FILE)
    else:
        attendance_df = pd.DataFrame(columns=["Email", "Name", "Time", "Status"])

    if email in attendance_df['Email'].values:
        return "Already Marked"

    row = df[df["Email"] == email].iloc[0]
    name = row.get("Name", "Unknown")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_entry = {"Email": email, "Name": name, "Time": now, "Status": "Present"}

    # ✅ Updated for pandas 2.0+
    attendance_df = pd.concat([attendance_df, pd.DataFrame([new_entry])], ignore_index=True)

    attendance_df.to_csv(ATTENDANCE_FILE, index=False)
    socketio.emit('attendance_update', {
    "email": email,
    "name": name,
    "college": row.get("College", ""),
    "time": now,
    "status": "Present"
    }, )

    return "Marked"

@app.route("/scanner")
def scanner_dashboard():
    if not session.get("admin"):
        return redirect("/admin-login")

    df = load_responses()

    if os.path.exists(ATTENDANCE_FILE):
        att_df = pd.read_csv(ATTENDANCE_FILE)
    else:
        att_df = pd.DataFrame(columns=["Email", "Name", "Time", "Status"])

    present_emails = set(att_df['Email'].values)

    # ✅ Merge present users with time
    present = df[df['Email'].isin(present_emails)]
    present = pd.merge(present, att_df[['Email', 'Time']], on="Email", how="left")

    # Absent
    absent = df[~df['Email'].isin(present_emails)]

    return render_template("scanner_dashboard.html", 
                           present=present.to_dict('records'), 
                           absent=absent.to_dict('records'))


@app.route("/start-scan")
def start_scan():
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"})

    cap = cv2.VideoCapture(0)
    detector = cv2.QRCodeDetector()
    result = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        data, bbox, _ = detector.detectAndDecode(frame)
        if data:
            try:
                parsed = json.loads(data)
                email = parsed.get("Email") or parsed.get("email")
                if email:
                    status = mark_attendance(email)
                    result = {"email": email, "status": status}
                else:
                    result = {"error": "Invalid QR (No Email found)"}
            except Exception as e:
                result = {"error": str(e)}
            break

    cap.release()
    cv2.destroyAllWindows()
    return jsonify(result)

# ---- Main ----
if __name__ == "__main__":
        
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        import eventlet
        import eventlet.wsgi
        socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)