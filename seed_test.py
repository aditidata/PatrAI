"""
PatrAI — seed_test.py

Sends a fake scheduling email to the assistant inbox via SMTP to trigger
the full PatrAI pipeline end-to-end.

Usage:
    cd patrai
    python seed_test.py
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

ASSISTANT_EMAIL = os.environ["ASSISTANT_EMAIL"]
ASSISTANT_EMAIL_PASSWORD = os.environ["ASSISTANT_EMAIL_PASSWORD"]
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")

# Fake sender — send to ourselves so PatrAI picks it up on next poll
TO = ASSISTANT_EMAIL
FROM = ASSISTANT_EMAIL

next_week = datetime.now() + timedelta(days=7)
date_str = next_week.strftime("%A, %B %d")

subject = "Can we schedule a meeting next week?"
body = f"""Hi,

I'd like to schedule a 1-hour meeting to discuss the Q3 roadmap.

Would {date_str} at 10am or 2pm work for you? Alternatively, any time
on {(next_week + timedelta(days=1)).strftime('%A, %B %d')} between 9am and 5pm is fine.

Please let me know what works best.

Best,
Test Sender
"""

msg = MIMEMultipart("alternative")
msg["Subject"] = subject
msg["From"] = FROM
msg["To"] = TO
msg.attach(MIMEText(body, "plain"))

print(f"Sending seed email to {TO}...")
with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
    server.login(ASSISTANT_EMAIL, ASSISTANT_EMAIL_PASSWORD)
    server.sendmail(FROM, [TO], msg.as_string())

print("Done. PatrAI will pick it up on the next IMAP poll (within 60 seconds).")
print("Watch the Celery worker logs for pipeline activity.")
