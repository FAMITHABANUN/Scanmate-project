"""
email_utils.py
----------------
Standalone email-sending helper for ScanMate.
Uses Brevo API over HTTPS with a branded HTML email template.
Free tier: up to 300 emails/day, no credit card required.
"""

import os
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("email_utils")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _get_registration_html(user_name):
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#090a12;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#090a12;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#5b7fff,#ff4fa3,#ff5c5c);border-radius:16px 16px 0 0;padding:40px 30px;text-align:center;">
              <img src="{os.environ.get('APP_URL', '').rstrip('/')}/static/images/icon-192.png" alt="ScanMate" width="48" height="48" style="margin-bottom:10px;border-radius:10px;">
              <h1 style="color:#ffffff;margin:0;font-size:28px;font-weight:700;letter-spacing:1px;">ScanMate</h1>
              <p style="color:#eef0fb;margin:8px 0 0;font-size:14px;">Any Handwritten Page, Instantly Digital</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="background:#14162a;padding:40px 40px 30px;">
              <h2 style="color:#ff4fa3;font-size:22px;margin:0 0 16px;">Welcome aboard, {user_name}! 🎉</h2>
              <p style="color:#c7c9de;font-size:16px;line-height:1.7;margin:0 0 20px;">
                Thank you for registering with <strong style="color:#eef0fb;">ScanMate</strong>. We're really glad to have you here.
              </p>
              <p style="color:#c7c9de;font-size:16px;line-height:1.7;margin:0 0 30px;">
                From now on, any handwritten page you scan gets turned into clean, editable text in seconds — with helpful tips along the way.
              </p>

              <!-- What you can do box -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:#1b1e38;border-left:4px solid #ff4fa3;border-radius:0 8px 8px 0;margin-bottom:30px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="color:#ff4fa3;font-weight:700;font-size:15px;margin:0 0 12px;">✨ What you can do with ScanMate:</p>
                    <p style="color:#c7c9de;font-size:14px;margin:6px 0;">📚 &nbsp;Digitize study and class notes</p>
                    <p style="color:#c7c9de;font-size:14px;margin:6px 0;">💻 &nbsp;Get quick tips on handwritten code/pseudocode</p>
                    <p style="color:#c7c9de;font-size:14px;margin:6px 0;">🛒 &nbsp;Turn grocery lists and to-dos into clean text</p>
                    <p style="color:#c7c9de;font-size:14px;margin:6px 0;">🤖 &nbsp;Ask our assistant a specific question, anytime</p>
                  </td>
                </tr>
              </table>

              <!-- CTA Button -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding-bottom:10px;">
                    <a href="{os.environ.get('APP_URL', '#')}"
                       style="display:inline-block;background:linear-gradient(135deg,#5b7fff,#ff4fa3,#ff5c5c);color:#0b0d10;text-decoration:none;font-size:16px;font-weight:700;padding:14px 40px;border-radius:50px;letter-spacing:0.5px;">
                      📄 Start Scanning Now
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#0f1120;border-radius:0 0 16px 16px;padding:24px 40px;text-align:center;border-top:1px solid #262a4a;">
              <p style="color:#8d90ac;font-size:13px;margin:0 0 6px;">Warmly,</p>
              <p style="color:#ff4fa3;font-weight:700;font-size:15px;margin:0;">The ScanMate Team 📄</p>
              <p style="color:#5a5d75;font-size:12px;margin:12px 0 0;">© 2026 ScanMate · Turn any handwritten page into text, instantly.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_email(to_email, to_name, subject, html_body, text_body):
    """
    Internal helper: sends HTML email via Brevo HTTPS API.
    Returns True on success, False on any failure (never raises).
    """
    api_key = os.environ.get("BREVO_API_KEY")
    mail_from = os.environ.get("MAIL_FROM")

    if not api_key or not mail_from or not to_email:
        logger.warning("Email not sent: missing BREVO_API_KEY, MAIL_FROM, or recipient.")
        return False

    try:
        payload = json.dumps({
            "sender": {"name": "ScanMate", "email": mail_from},
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
            "htmlContent": html_body,
            "textContent": text_body
        }).encode("utf-8")

        req = urllib.request.Request(
            BREVO_API_URL,
            data=payload,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                logger.info("Email sent successfully to %s", to_email)
                return True
            else:
                logger.error("Brevo API returned status %s", resp.status)
                return False

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        logger.error("Brevo API error %s for %s: %s", e.code, to_email, error_body)
        return False

    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False


def _escape_html(text):
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _get_scan_summary_html(user_name, category_label, extracted_text):
    safe_text = _escape_html(extracted_text)[:4000]  # keep the email a reasonable size
    if len(extracted_text or "") > 4000:
        safe_text += "\n\n... (full text available in your ScanMate dashboard)"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#090a12;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#090a12;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#5b7fff,#ff4fa3,#ff5c5c);border-radius:16px 16px 0 0;padding:36px 30px;text-align:center;">
              <img src="{os.environ.get('APP_URL', '').rstrip('/')}/static/images/icon-192.png" alt="ScanMate" width="42" height="42" style="margin-bottom:8px;border-radius:9px;">
              <h1 style="color:#ffffff;margin:0;font-size:24px;font-weight:700;">Your Scan is Ready!</h1>
              <p style="color:#eef0fb;margin:8px 0 0;font-size:13px;">{category_label}</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="background:#14162a;padding:32px 40px;">
              <p style="color:#c7c9de;font-size:15px;line-height:1.6;margin:0 0 20px;">
                Hi {user_name}, here's a copy of what ScanMate extracted from your handwritten page:
              </p>

              <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f1120;border-left:4px solid #5b7fff;border-radius:0 8px 8px 0;margin-bottom:20px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <pre style="color:#eef0fb;font-size:13px;line-height:1.6;white-space:pre-wrap;word-wrap:break-word;margin:0;font-family:'Courier New',monospace;">{safe_text}</pre>
                  </td>
                </tr>
              </table>

              <p style="color:#8d90ac;font-size:13px;line-height:1.6;margin:0;">
                This is an automatic copy sent to your inbox for safekeeping. You can view, ask questions about, or download this scan anytime from your ScanMate dashboard.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#0f1120;border-radius:0 0 16px 16px;padding:20px 40px;text-align:center;border-top:1px solid #262a4a;">
              <p style="color:#ff4fa3;font-weight:700;font-size:14px;margin:0;">The ScanMate Team 📄</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_scan_summary_email(user_email, user_name, category_label, extracted_text):
    """Sends a copy of the scan's extracted text to the user's inbox right
    after scanning - a saved 'receipt' of what was digitized."""
    subject = f"Your ScanMate Scan is Ready 📄 ({category_label})"
    html_body = _get_scan_summary_html(user_name, category_label, extracted_text)
    text_body = f"""Hi {user_name},

Here's a copy of what ScanMate extracted from your handwritten page ({category_label}):

---
{extracted_text or '(no text was extracted)'}
---

You can view, ask questions about, or download this scan anytime from your ScanMate dashboard.

Warmly,
The ScanMate Team
"""
    return _send_email(user_email, user_name, subject, html_body, text_body)
    """Sends the 'Welcome to ScanMate!' email after successful registration."""
    subject = "Welcome to ScanMate! 📄"
    html_body = _get_registration_html(user_name)
    text_body = f"""Hi {user_name},

Thank you for registering with ScanMate!

We're really glad to have you here. From now on you can scan any handwritten
page - class notes, a grocery list, a to-do list, even a bill - and ScanMate
will turn it into clean, editable text in seconds. When it's useful, our
assistant will also offer quick, relevant tips for what you scanned.

Wishing you a smooth and productive experience ahead.

Warmly,
The ScanMate Team
"""
    return _send_email(user_email, user_name, subject, html_body, text_body)
