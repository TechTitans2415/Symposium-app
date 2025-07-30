# utils/qr_generator.py

import qrcode
import os

def generate_qr(data, email):
    filename = f"static/qr_codes/{email}.png"
    qr = qrcode.make(data)
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    qr.save(filename)
    return filename
