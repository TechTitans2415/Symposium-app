from eventlet import monkey_patch
monkey_patch()

from flask import Flask, redirect, url_for, session, request, render_template, jsonify
import os
import json
import ast
from config import (
    SECRET_KEY,
    ADMIN_ID,
    ADMIN_PASSWORD,
    MAIL_ID,
    MAIL_APP_PASSWORD
)
import requests
import qrcode
import csv
from email.message import EmailMessage
import smtplib
from datetime import datetime
from flask_socketio import SocketIO, emit
import numpy as np
import pandas as pd



# ---- Flask & OAuth Setup ----
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # allow multiple connections
app.secret_key = SECRET_KEY
RESPONSES_FILE = 'responses.csv'
STATUS_FILE = 'qr_status.csv'
ATTENDANCE_FILE = 'attendance.csv'

    
@app.route("/")
def index():
    return render_template("index.html", user=session.get("user"))


# ---- Admin Login System ----
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["admin_id"] == ADMIN_ID and request.form["admin_password"] == ADMIN_PASSWORD:
            session["admin"] = True
            # redirect to the page user wanted, else dashboard
            next_page = request.args.get("next")
            return redirect(next_page if next_page else "/admin-dashboard")
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
        return redirect("/admin-login?next=/admin-dashboard")

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
            "Team members": row.get("Team members", ""),
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
    msg.set_content("Greetings from the Technovation 2K25 Organizing Team! ✨\n\nThank you for registering for Technovation 2K25.\n\nAttached is your QR code, which contains your registration details. Please show this QR code at the event venue during check-in. It will be used to verify your details and mark your attendance.\n\nWe look forward to seeing you at Technovation 2K25!\n\nBest regards,\nOrganizing Team\nTechnovation 2K25")


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
        "Name": str(user.get("Name", "")),
        "Email": str(user.get("Email", "")),
        "Department": str(user.get("Department", "")),
        "College": str(user.get("College", "")),
        "Year": str(user.get("Year", "")),   # 👈 always keep as string
        "Team members": str(user.get("Team members", ""))
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

    # Define columns for attendance.csv
    columns = ["Email", "Name", "Year", "Department", "College", "Team members", "Phone number", "Time", "Status"]
    if os.path.exists(ATTENDANCE_FILE):
        attendance_df = pd.read_csv(ATTENDANCE_FILE)
    else:
        attendance_df = pd.DataFrame(columns=columns)

    if email in attendance_df['Email'].values:
        return "Already Marked"

    row = df[df["Email"] == email].iloc[0]
    name = str(row.get("Name", "Unknown"))
    year = str(row.get("Year", ""))
    department = str(row.get("Department", ""))
    college = str(row.get("College", ""))
    team_members = str(row.get("Team members", ""))
    phone = str(row.get("Phone", ""))  # Change column name if needed
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_entry = {
        "Email": email,
        "Name": name,
        "Year": year,
        "Department": department,
        "College": college,
        "Team members": team_members,
        "Phone number": phone,
        "Time": now,
        "Status": "Present"
    }

    attendance_df = pd.concat([attendance_df, pd.DataFrame([new_entry])], ignore_index=True)
    attendance_df.to_csv(ATTENDANCE_FILE, index=False)

    socketio.emit('attendance_update', {
        "email": str(email),
        "name": name,
        "year": year,
        "department": department,
        "college": college,
        "team_members": team_members,
        "phone number": phone,
        "time": now,
        "status": "Present"
    })

    return "Marked"

@app.route("/scanner")
def scanner_dashboard():
    if not session.get("admin"):
        return redirect("/admin-login?next=/scanner")

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


@app.route("/mark-scan", methods=["POST"])
def mark_from_client():
    try:
        data = request.json
        email = data.get("email")
        if not email:
            return jsonify({"status": "error", "message": "Email not provided"}), 400

        status = mark_attendance(email)
        return jsonify({"status": "success", "message": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---- Main ----
if __name__ == "__main__":
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        import eventlet
        import eventlet.wsgi
        socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)