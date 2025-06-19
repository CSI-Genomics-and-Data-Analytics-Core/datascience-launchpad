import secrets
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import (
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    EMAIL_HOST,
    EMAIL_PORT,
    EMAIL_USE_SSL,
    EMAIL_USE_TLS,
    OTP_VALIDITY_MINUTES,
    OTP_LENGTH,
    MAX_OTP_ATTEMPTS,
    MAX_OTP_REQUESTS_PER_HOUR,
)
from app.db.database import get_db

logger = logging.getLogger(__name__)


class OTPService:
    def __init__(self):
        # Check if SMTP credentials are configured
        if not SMTP_USER or not SMTP_PASSWORD:
            logger.error("SMTP credentials not configured")
            raise ValueError("SMTP credentials not configured")
        logger.info("Using SMTP for email sending")

    def generate_otp(self) -> str:
        """Generate a random OTP of specified length"""
        return "".join([str(secrets.randbelow(10)) for _ in range(OTP_LENGTH)])

    def can_request_otp(self, email: str) -> tuple[bool, str]:
        """Check if user can request a new OTP"""
        db = get_db()
        try:
            # Check rate limiting - max requests per hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_requests = db.execute(
                "SELECT COUNT(*) as count FROM otp_tokens WHERE email = ? AND created_at > ?",
                (email, one_hour_ago),
            ).fetchone()

            if recent_requests["count"] >= MAX_OTP_REQUESTS_PER_HOUR:
                return False, "Too many OTP requests. Please try again later."

            # Check if there's an active OTP that's not expired
            active_otp = db.execute(
                "SELECT * FROM otp_tokens WHERE email = ? AND expires_at > ? AND used = FALSE ORDER BY created_at DESC LIMIT 1",
                (email, datetime.utcnow()),
            ).fetchone()

            if active_otp:
                remaining_time = (
                    datetime.fromisoformat(active_otp["expires_at"]) - datetime.utcnow()
                ).total_seconds()
                if remaining_time > 60:  # More than 1 minute remaining
                    return (
                        False,
                        f"Please wait {int(remaining_time/60)} minutes before requesting a new OTP.",
                    )

            return True, ""
        finally:
            db.close()

    def create_otp(self, email: str) -> tuple[bool, str]:
        """Create and send OTP to email"""
        can_request, message = self.can_request_otp(email)
        if not can_request:
            return False, message

        otp_code = self.generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_VALIDITY_MINUTES)

        db = get_db()
        try:
            # Invalidate any existing active OTPs for this email
            db.execute(
                "UPDATE otp_tokens SET used = TRUE WHERE email = ? AND used = FALSE",
                (email,),
            )

            # Create new OTP
            db.execute(
                "INSERT INTO otp_tokens (email, token, expires_at) VALUES (?, ?, ?)",
                (email, otp_code, expires_at),
            )
            db.commit()

            # Send email
            success, error_msg = self.send_otp_email(email, otp_code)
            if not success:
                # Mark OTP as used if email sending failed
                db.execute(
                    "UPDATE otp_tokens SET used = TRUE WHERE email = ? AND token = ?",
                    (email, otp_code),
                )
                db.commit()
                return False, error_msg

            logger.info(f"OTP created and sent successfully for {email}")
            return True, "Access code sent successfully"

        except Exception as e:
            logger.error(f"Error creating OTP for {email}: {str(e)}")
            return False, "Failed to create access code. Please try again."
        finally:
            db.close()

    def verify_otp(self, email: str, otp_code: str) -> tuple[bool, str]:
        """Verify OTP code"""
        db = get_db()
        try:
            # Get active OTP
            otp_record = db.execute(
                "SELECT * FROM otp_tokens WHERE email = ? AND token = ? AND used = FALSE AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                (email, otp_code, datetime.utcnow()),
            ).fetchone()

            if not otp_record:
                # Check if there's any OTP for this email to increment attempts
                any_otp = db.execute(
                    "SELECT * FROM otp_tokens WHERE email = ? AND used = FALSE AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                    (email, datetime.utcnow()),
                ).fetchone()

                if any_otp:
                    new_attempts = any_otp["attempts"] + 1
                    db.execute(
                        "UPDATE otp_tokens SET attempts = ? WHERE id = ?",
                        (new_attempts, any_otp["id"]),
                    )

                    if new_attempts >= MAX_OTP_ATTEMPTS:
                        # Mark as used after max attempts
                        db.execute(
                            "UPDATE otp_tokens SET used = TRUE WHERE id = ?",
                            (any_otp["id"],),
                        )
                        db.commit()
                        return (
                            False,
                            "Too many incorrect attempts. Please request a new OTP.",
                        )

                db.commit()
                return False, "Invalid or expired OTP"

            # Mark OTP as used
            db.execute(
                "UPDATE otp_tokens SET used = TRUE WHERE id = ?", (otp_record["id"],)
            )
            db.commit()

            logger.info(f"OTP verified successfully for {email}")
            return True, "OTP verified successfully"

        except Exception as e:
            logger.error(f"Error verifying OTP for {email}: {str(e)}")
            return False, "Failed to verify OTP. Please try again."
        finally:
            db.close()

    def send_otp_email(self, email: str, otp_code: str) -> tuple[bool, str]:
        """Send OTP email via SMTP"""
        try:
            subject = f"Your GeDaC Launchpad Access Code: {otp_code}"

            body_text = f"""
Your GeDaC Launchpad access code is: {otp_code}

This code will expire in {OTP_VALIDITY_MINUTES} minutes.

Please enter this code to access your account.

If you didn't request this code, please ignore this email.

Best regards,
GeDaC Launchpad Team
            """.strip()

            body_html = f"""
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GeDaC Launchpad Access Code</title>
</head>
<body style="margin: 0; padding: 20px; background-color: #f4f6f9; font-family: Arial, sans-serif;">
    <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 5px;">
        <h1 style="color: #333; margin-top: 0; font-size: 24px;">GeDaC Launchpad Access Code</h1>

        <p style="color: #555; font-size: 16px;">Your access code is:</p>

        <!-- OTP Code Box -->
        <div style="background-color: #f2f2f2; padding: 20px; text-align: center; border-radius: 5px; margin: 20px 0;">
            <div style="color: #333; font-size: 32px; font-weight: bold; letter-spacing: 5px;">
                {otp_code}
            </div>
        </div>

        <p style="color: #555; font-size: 14px;">
            ⏰ This code will expire in <strong>{OTP_VALIDITY_MINUTES} minutes</strong>
        </p>

        <p style="color: #555; font-size: 14px; margin-top: 20px;">
            If you didn't request this code, please ignore this email.
        </p>

        <p style="color: #777; font-size: 14px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 20px;">
            Best regards,<br>
            GeDaC Team
        </p>
    </div>
</body>
</html>
            """

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
            msg["To"] = email

            # Create text and HTML parts
            text_part = MIMEText(body_text, "plain", "utf-8")
            html_part = MIMEText(body_html, "html", "utf-8")

            # Attach parts
            msg.attach(text_part)
            msg.attach(html_part)

            # Send email via SMTP
            if EMAIL_USE_SSL:
                # Use SSL connection (typically port 465)
                with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT) as server:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.send_message(msg)
            else:
                # Use regular SMTP with optional TLS (typically port 587)
                with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                    if EMAIL_USE_TLS:
                        server.starttls()
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.send_message(msg)

            logger.info(f"Email sent successfully via SMTP to {email}")
            return True, ""

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email to {email}: {str(e)}")
            return False, f"Failed to send email via SMTP: {str(e)}"
        except Exception as e:
            logger.error(
                f"Unexpected error sending email via SMTP to {email}: {str(e)}"
            )
            return False, f"Failed to send email: {str(e)}"

    def cleanup_expired_otps(self):
        """Clean up expired and used OTPs"""
        db = get_db()
        try:
            # Delete OTPs older than 24 hours
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            result = db.execute(
                "DELETE FROM otp_tokens WHERE created_at < ?", (cutoff_time,)
            )
            db.commit()
            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired OTP records")
        except Exception as e:
            logger.error(f"Error cleaning up OTPs: {str(e)}")
        finally:
            db.close()


# Global OTP service instance
otp_service = OTPService()


def get_otp_service() -> OTPService:
    """Get OTP service instance"""
    return otp_service
