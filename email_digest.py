"""
📧 Email Digest Bot
Reads emails from monitored senders, summarizes them with Gemini AI,
and sends a daily digest to Telegram.

Usage:
    Local:   python email_digest.py          (reads from .env)
    GitHub:  Triggered by GitHub Actions cron (reads from env secrets)
"""

import imaplib
import email
import smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from html import unescape

import requests
from dotenv import load_dotenv
from google import genai

from config import WATCH_SENDERS, LOOKBACK_HOURS, GEMINI_MODEL, SUMMARY_PROMPT

# ── Fix Windows console encoding for emoji ──────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Load environment variables ──────────────────────────────────────────
load_dotenv()  # loads .env file if present (ignored in GitHub Actions)

GMAIL_EMAIL = os.environ.get("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def validate_env():
    """Ensure all required environment variables are set."""
    missing = []
    for var_name in ["GMAIL_EMAIL", "GMAIL_APP_PASSWORD", "GEMINI_API_KEY",
                     "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]:
        if not os.environ.get(var_name):
            missing.append(var_name)
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print("   Set them in .env (local) or GitHub Secrets (CI).")
        sys.exit(1)
    print("✅ All environment variables loaded.")


# ═══════════════════════════════════════════════════════════════════════
#  📧  EMAIL FETCHING
# ═══════════════════════════════════════════════════════════════════════

def decode_mime_header(header_value):
    """Decode a MIME-encoded email header into a readable string."""
    if header_value is None:
        return ""
    decoded_parts = decode_header(header_value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def strip_html(html_text):
    """Convert HTML to plain text (basic)."""
    # Remove style and script blocks
    text = re.sub(r'<style[^>]*>.*?</style>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br>, <p>, <div> with newlines
    text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|tr|li|h[1-6])>', '\n', text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = unescape(text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_body(msg):
    """Extract the text body from an email message."""
    body_text = ""
    body_html = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            # Skip attachments
            if "attachment" in content_disposition:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if content_type == "text/plain":
                    body_text += decoded
                elif content_type == "text/html":
                    body_html += decoded
            except Exception:
                continue
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                body_html = decoded
            else:
                body_text = decoded

    # Prefer plain text; fall back to stripped HTML
    if body_text.strip():
        return body_text.strip()
    if body_html.strip():
        return strip_html(body_html)
    return "(empty body)"


def extract_sender_email(from_header):
    """Extract just the email address from a From header like 'Name <email@example.com>'."""
    match = re.search(r'<([^>]+)>', from_header)
    if match:
        return match.group(1).lower()
    return from_header.strip().lower()


def fetch_emails():
    """
    Connect to Gmail via IMAP, fetch emails from monitored senders
    received within the lookback window.
    Searches across Inbox, All Mail, and Spam to catch categorized emails.
    Returns a list of dicts: [{subject, sender, date, body}, ...]
    """
    print(f"\n📧 Connecting to Gmail as {GMAIL_EMAIL}...")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
    except imaplib.IMAP4.error as e:
        print(f"❌ IMAP login failed: {e}")
        print("   Check your GMAIL_EMAIL and GMAIL_APP_PASSWORD.")
        return []

    # Calculate the date cutoff for IMAP SINCE filter
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    since_date = cutoff.strftime("%d-%b-%Y")  # IMAP date format: 01-May-2026

    collected_emails = []
    seen_message_ids = set()  # Deduplicate across folders

    # Search multiple folders — Gmail often puts newsletters in
    # Promotions/Updates tabs or Spam. "[Gmail]/All Mail" catches everything
    # except Spam, so we search both.
    folders_to_search = ['"[Gmail]/All Mail"', '"[Gmail]/Spam"']

    for folder in folders_to_search:
        status, _ = mail.select(folder, readonly=True)
        if status != "OK":
            print(f"   ⚠️  Could not open folder: {folder}")
            continue
        print(f"\n   📂 Searching in {folder}...")

        for sender in WATCH_SENDERS:
            print(f"      🔍 From: {sender}")

            # IMAP search: FROM sender AND received SINCE cutoff date
            search_criteria = f'(FROM "{sender}" SINCE "{since_date}")'
            status, message_ids = mail.search(None, search_criteria)

            if status != "OK" or not message_ids[0]:
                print(f"         → No emails found")
                continue

            ids = message_ids[0].split()
            print(f"         → Found {len(ids)} email(s)")

            for msg_id in ids:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Deduplicate by Message-ID header
                message_id = msg.get("Message-ID", "")
                if message_id and message_id in seen_message_ids:
                    continue
                if message_id:
                    seen_message_ids.add(message_id)

                # Decode headers
                subject = decode_mime_header(msg["Subject"])
                from_header = decode_mime_header(msg["From"])
                date_str = msg["Date"]

                # Parse the date and verify it's within our lookback window
                try:
                    email_date = parsedate_to_datetime(date_str)
                    # Make timezone-aware if needed
                    if email_date.tzinfo is None:
                        email_date = email_date.replace(tzinfo=timezone.utc)
                    if email_date < cutoff:
                        continue  # Skip emails older than lookback window
                except Exception:
                    email_date = None

                # Extract body
                body = extract_body(msg)
                # Truncate very long bodies to avoid hitting Gemini token limits
                if len(body) > 5000:
                    body = body[:5000] + "\n\n... [truncated]"

                collected_emails.append({
                    "subject": subject,
                    "sender": from_header,
                    "sender_email": sender,
                    "date": email_date.strftime("%Y-%m-%d %H:%M %Z") if email_date else date_str,
                    "body": body,
                })

    mail.logout()
    print(f"\n📊 Total emails collected: {len(collected_emails)}")
    return collected_emails


# ═══════════════════════════════════════════════════════════════════════
#  🤖  AI SUMMARIZATION
# ═══════════════════════════════════════════════════════════════════════

def summarize_emails(emails):
    """
    Use Gemini to generate a detailed summary digest of all collected emails.
    """
    if not emails:
        return None

    print("\n🤖 Summarizing with Gemini...")

    # Build the email content block for the prompt
    email_block = ""
    for i, em in enumerate(emails, 1):
        email_block += f"""
--- EMAIL {i} ---
From: {em['sender']}
Subject: {em['subject']}
Date: {em['date']}
Body:
{em['body']}
--- END EMAIL {i} ---

"""

    full_prompt = f"""{SUMMARY_PROMPT}

Here are the emails to summarize:

{email_block}
"""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
        )
        summary = response.text
        print("✅ Summary generated successfully.")
        return summary

    except Exception as e:
        print(f"❌ Gemini summarization failed: {e}")
        # Fallback: return a basic listing
        fallback = "📬 **Daily Email Digest** (AI summary unavailable)\n\n"
        for em in emails:
            fallback += f"📩 **{em['subject']}**\nFrom: {em['sender']}\nDate: {em['date']}\n\n"
        return fallback


# ═══════════════════════════════════════════════════════════════════════
#  📱  TELEGRAM DELIVERY
# ═══════════════════════════════════════════════════════════════════════

def send_to_telegram(message):
    """
    Send a message to Telegram. Handles the 4096 character limit
    by splitting long messages into chunks.
    """
    if not message:
        print("⚠️  No message to send.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    MAX_LENGTH = 4096

    # Split message into chunks if too long
    chunks = []
    while len(message) > MAX_LENGTH:
        # Find a good split point (newline near the limit)
        split_at = message.rfind("\n", 0, MAX_LENGTH)
        if split_at == -1 or split_at < MAX_LENGTH // 2:
            split_at = MAX_LENGTH
        chunks.append(message[:split_at])
        message = message[split_at:].lstrip("\n")
    if message:
        chunks.append(message)

    success = True
    for i, chunk in enumerate(chunks, 1):
        try:
            response = requests.post(url, data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": "Markdown",
            }, timeout=30)

            if response.status_code == 200:
                print(f"📱 Telegram message sent ({i}/{len(chunks)})")
            else:
                # Retry without Markdown if parsing fails
                print(f"⚠️  Markdown parse failed, retrying as plain text...")
                response = requests.post(url, data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk,
                }, timeout=30)
                if response.status_code == 200:
                    print(f"📱 Telegram message sent as plain text ({i}/{len(chunks)})")
                else:
                    print(f"❌ Telegram send failed: {response.text}")
                    success = False

        except Exception as e:
            print(f"❌ Telegram error: {e}")
            success = False

    return success


# ═══════════════════════════════════════════════════════════════════════
#  📧  EMAIL DELIVERY
# ═══════════════════════════════════════════════════════════════════════

DIGEST_RECIPIENT_EMAIL = os.environ.get("DIGEST_RECIPIENT_EMAIL")


def send_email_digest(summary):
    """
    Send the digest summary as an email to the recipient.
    Uses Gmail SMTP with the same App Password used for IMAP.
    """
    if not summary:
        print("⚠️  No summary to email.")
        return False

    print(f"\n📧 Sending digest email to {DIGEST_RECIPIENT_EMAIL}...")

    try:
        # Build the email
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Email Digest Bot <{GMAIL_EMAIL}>"
        msg["To"] = DIGEST_RECIPIENT_EMAIL
        msg["Subject"] = f"📬 Daily Email Digest — {datetime.now().strftime('%d %b %Y')}"

        # Plain text version
        msg.attach(MIMEText(summary, "plain", "utf-8"))

        # HTML version (converts markdown-style bold and newlines)
        html_body = summary.replace("\n", "<br>")
        html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
        html_body = re.sub(r'_(.+?)_', r'<em>\1</em>', html_body)
        html_content = f"""\
<html>
<body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; 
             color: #333; max-width: 700px; margin: 0 auto; padding: 20px;">
  <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
              color: white; padding: 20px; border-radius: 10px 10px 0 0;">
    <h2 style="margin: 0;">📬 Daily Email Digest</h2>
    <p style="margin: 5px 0 0; opacity: 0.9;">{datetime.now().strftime('%A, %d %B %Y')}</p>
  </div>
  <div style="background: #f9f9f9; padding: 20px; border: 1px solid #e0e0e0; 
              border-radius: 0 0 10px 10px;">
    {html_body}
  </div>
  <p style="text-align: center; color: #999; font-size: 12px; margin-top: 15px;">
    Sent by Email Digest Bot
  </p>
</body>
</html>"""
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_EMAIL, DIGEST_RECIPIENT_EMAIL, msg.as_string())

        print(f"✅ Digest email sent to {DIGEST_RECIPIENT_EMAIL}")
        return True

    except Exception as e:
        print(f"❌ Email send failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════
#  🚀  MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    """Run the full email digest pipeline: Fetch → Summarize → Send."""
    print("=" * 50)
    print("📧 Email Digest Bot — Starting")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"👀 Monitoring {len(WATCH_SENDERS)} sender(s)")
    print(f"⏳ Looking back {LOOKBACK_HOURS} hours")
    print("=" * 50)

    # 1. Validate environment
    validate_env()

    # 2. Fetch emails
    emails = fetch_emails()

    if not emails:
        no_mail_msg = (
            f"📬 **Daily Email Digest**\n\n"
            f"No new emails from monitored senders in the last {LOOKBACK_HOURS} hours.\n\n"
            f"👀 Monitoring: {', '.join(WATCH_SENDERS)}\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        print("\n📭 No new emails found.")
        send_to_telegram(no_mail_msg)
        send_email_digest(no_mail_msg)
        return

    # 3. Summarize with AI
    summary = summarize_emails(emails)

    # 4. Send to Telegram & Email
    if summary:
        # Add timestamp footer
        summary += f"\n\n🕐 _Digest generated at {datetime.now().strftime('%Y-%m-%d %H:%M')} IST_"
        send_to_telegram(summary)
        send_email_digest(summary)

    print("\n✅ Email Digest Bot — Complete!")


if __name__ == "__main__":
    main()
