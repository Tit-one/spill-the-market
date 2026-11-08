"""Public source references preserving page identity without common URL secrets."""
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _tracking(key):
    return key.lower().startswith("utm_") or key.lower() in {"fbclid", "gclid", "msclkid", "ttclid", "_ga", "_gl"}


def url_reference_hash(value: str | None) -> str:
    """Opaque identity separate from redacted display, including ambiguous codes."""
    try:
        parsed = urlsplit(value or "")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        if parsed.port is not None and parsed.port != (443 if parsed.scheme == "https" else 80):
            host += f":{parsed.port}"
        query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if not _tracking(key)]
        identity = urlunsplit((parsed.scheme, host, parsed.path or "/", urlencode(query), ""))
        return hashlib.sha256(identity.encode()).hexdigest()
    except (TypeError, ValueError):
        return ""


def public_evidence_url(value: str | None) -> str | None:
    try:
        parsed = urlsplit(value or "")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        if parsed.port is not None and parsed.port != (443 if parsed.scheme == "https" else 80):
            host += f":{parsed.port}"
        sensitive = re.compile(r"token|key|auth|sign|secret|pass|cookie|session|credential|code|email|phone|phpsessid|(?:^|[_-])(?:jwt|pwd|sid)(?:$|[_-])", re.I)
        query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                 if not sensitive.search(key) and not _tracking(key)]
        return urlunsplit((parsed.scheme, host, parsed.path or "/", urlencode(query), ""))
    except (TypeError, ValueError):
        return None
