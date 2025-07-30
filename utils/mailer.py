# utils/mailer.py

import smtplib
from email.message import EmailMessage
from config import MAIL_ID, MAIL_APP_PASSWORD

def send_qr_mail(to_email, qr_path):
    msg = EmailMessage()
    msg['Subject'] = "Your Symposium QR Code"
    msg['From'] = MAIL_ID
    msg['To'] = to_email
    msg.set_content("Attached is your QR code for symposium check-in.")

    with open(qr_path, 'rb') as f:
        file_data = f.read()
        file_name = qr_path.split("/")[-1]
    msg.add_attachment(file_data, maintype='image', subtype='png', filename=file_name)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(MAIL_ID, MAIL_APP_PASSWORD)
        smtp.send_message(msg)
