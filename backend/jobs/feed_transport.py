"""Bounded HTTPS fetch of an explicitly configured public feed.

Resolve and validate every address, then pin the socket to the selected public
IP while retaining TLS hostname verification. No redirects, cookies or auth.
"""
import http.client
import ipaddress
import socket
import ssl
import time
import json
from urllib.parse import urlsplit, parse_qsl
from jobs.connectors import SourceError, public_url, retry_after_seconds

MAX_BYTES = 8_000_000


def feed_url(value):
    value = public_url(value)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.port not in {None, 443}:
        raise ValueError("Feeds require a public HTTPS URL on the standard port.")
    if any(key.lower() in {"key", "api_key", "apikey", "token", "access_token", "password", "secret"} for key, _ in parse_qsl(parsed.query)):
        raise ValueError("Use a public feed without credentials or subscription keys.")
    if len(value) > 2000: raise ValueError("Feed URL is too long.")
    return value


def public_addresses(host):
    try:
        addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise SourceError("Feed address must resolve only to public internet addresses.")
        return addresses
    except (socket.gaierror, ValueError):
        raise SourceError("Feed hostname could not be resolved safely.") from None


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=20, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try: self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch_public_feed(value):
    return request_public(value)


def request_public(value, payload=None):
    """Pinned public HTTPS transport. POST is JSON-only; redirects are rejected."""
    parsed = urlsplit(feed_url(value))
    address = public_addresses(parsed.hostname)[0]
    connection = PinnedHTTPS(parsed.hostname, address)
    try:
        deadline = time.monotonic() + 20
        target = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
        from jobs import http_cache
        key = value
        cached = http_cache.get(key) if payload is None else None
        body = json.dumps(payload).encode() if payload is not None else None
        connection.request("POST" if body is not None else "GET", target, body=body,
                           headers={"Accept": "application/json, application/rss+xml, application/atom+xml, application/xml, text/xml, text/html",
                                    "Accept-Encoding": "identity", "User-Agent": "CareerOS-personal/0.3",
                                    **({"Content-Type": "application/json"} if body is not None else {}),
                                    **(cached[1] if cached else {})})
        response = connection.getresponse()
        if response.status == 304 and cached: return cached[0]
        if response.status != 200:
            if 300 <= response.status < 400:
                raise SourceError("Feed redirect requires its final public URL; existing jobs preserved.", status_code=response.status)
            raise SourceError(f"Feed request failed (HTTP {response.status}).",
                              retry_after_seconds(response.getheader("Retry-After")), response.status)
        if response.getheader("Content-Encoding", "identity").lower() not in {"", "identity"}:
            raise SourceError("Compressed feed response is unsupported; supply an uncompressed feed.")
        chunks, size = [], 0
        while True:
            if time.monotonic() >= deadline: raise SourceError("Feed exceeded the execution time budget.")
            chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
            if not chunk: break
            chunks.append(chunk); size += len(chunk)
            if size > MAX_BYTES: raise SourceError("Feed exceeded the 8 MB response limit.")
        result = b"".join(chunks)
        if payload is None: http_cache.put(key, result, response.headers)
        return result
    except (OSError, http.client.HTTPException):
        raise SourceError("Public feed could not be reached; existing jobs preserved.") from None
    finally: connection.close()
