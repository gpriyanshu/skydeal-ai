import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger

from src.domain.entities import Notification
from src.domain.interfaces import NotificationSender
from src.utils import mask_email


class EmailNotificationSender(NotificationSender):
    """
    Sends flight alerts via SMTP Email.
    Gracefully logs the email if SMTP configuration is absent.
    """
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_username: str | None,
        smtp_password: str | None,
        smtp_from_email: str | None
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_from_email = smtp_from_email or smtp_username

    def send(self, notification: Notification, message_header: str, message_body: str) -> bool:
        recipient = notification.user_id
        if not recipient or "@" not in recipient:
            logger.error(f"Invalid email address: {mask_email(recipient)}")
            return False

        if not self.smtp_username or not self.smtp_password or not self.smtp_from_email:
            logger.warning(
                f"SMTP settings incomplete. Simulated email to {mask_email(recipient)}: "
                f"Subject: {message_header}"
            )
            return True

        msg = MIMEMultipart("alternative")
        msg["Subject"] = message_header
        msg["From"] = self.smtp_from_email
        msg["To"] = recipient

        # Simple HTML content compilation
        html_content = f"""
        <html>
          <body>
            <h2>{message_header}</h2>
            <p style="font-size: 14px; line-height: 1.5; color: #333;">
              {message_body.replace('\n', '<br>')}
            </p>
            <hr/>
            <p style="font-size: 11px; color: #777;">
              You received this flight deal alert because you are subscribed to SkyDeal AI.
            </p>
          </body>
        </html>
        """

        msg.attach(MIMEText(message_body, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.smtp_from_email, recipient, msg.as_string())
            logger.info(f"Email notification successfully sent to {mask_email(recipient)}")
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch email to {mask_email(recipient)} over SMTP: {e}")
            return False
