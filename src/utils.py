"""
Security and Privacy Utilities for SkyDeal AI.
Provides helper functions for masking sensitive data (Tokens, Chat IDs, API keys, Emails) in logs.
"""
import re


def mask_chat_id(chat_id: str | int | None) -> str:
    """
    Masks a Telegram Chat ID or User ID for secure logging.
    Example: '5256572811' -> '******2811'
    """
    if not chat_id:
        return "<none>"
    s = str(chat_id)
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


def mask_secret(secret: str | None, show_prefix: int = 3, show_suffix: int = 4) -> str:
    """
    Masks API keys, tokens, or authorization headers.
    Example: 'sk-1234567890abcdef' -> 'sk-*********cdef'
    """
    if not secret:
        return "<none>"
    s = str(secret)
    if len(s) <= (show_prefix + show_suffix):
        return "*" * len(s)
    prefix = s[:show_prefix]
    suffix = s[-show_suffix:] if show_suffix > 0 else ""
    masked_mid = "*" * (len(s) - show_prefix - show_suffix)
    return f"{prefix}{masked_mid}{suffix}"


def mask_email(email: str | None) -> str:
    """
    Masks an email address for secure logging.
    Example: 'user@example.com' -> 'u***r@example.com'
    """
    if not email or "@" not in email:
        return "<invalid_email>"
    parts = email.split("@", 1)
    name, domain = parts[0], parts[1]
    if len(name) <= 2:
        masked_name = name[0] + "*"
    else:
        masked_name = name[0] + "*" * (len(name) - 2) + name[-1]
    return f"{masked_name}@{domain}"
