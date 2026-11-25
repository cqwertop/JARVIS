"""API keys live in the operating system's secure credential store, never in a KAIRO file.

Windows: Credential Manager. macOS: Keychain. Linux: Secret Service (GNOME Keyring / KWallet).
"""

import logging
import os

log = logging.getLogger("kairo.credentials")

SERVICE = "KAIRO"
OLD_SERVICE = "JARVIS"  # this app's previous name; keys saved under it are moved over on first use
ANTHROPIC = "anthropic_api_key"


def get(account: str) -> str | None:
    try:
        import keyring

        secret = keyring.get_password(SERVICE, account)
        if secret is None:
            secret = keyring.get_password(OLD_SERVICE, account)
            if secret is not None:
                keyring.set_password(SERVICE, account, secret)
                try:
                    keyring.delete_password(OLD_SERVICE, account)
                except Exception:
                    pass
        return secret
    except Exception as exc:  # no keyring backend available (e.g. a minimal Linux)
        log.warning("Secure credential storage unavailable: %r", exc)
        return None


def put(account: str, secret: str):
    """Raises RuntimeError with a plain-language message if the OS store can't be used."""
    try:
        import keyring

        keyring.set_password(SERVICE, account, secret)
    except Exception as exc:
        raise RuntimeError(
            "This computer's secure password storage isn't available, so the key can't be saved safely. "
            "On Linux, install and unlock GNOME Keyring or KWallet, then try again."
        ) from exc


def delete(account: str):
    try:
        import keyring

        keyring.delete_password(SERVICE, account)
    except Exception:
        pass


def load_into_environment():
    """Make a stored Anthropic key available to the Claude API client (only for this process)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        key = get(ANTHROPIC)
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
