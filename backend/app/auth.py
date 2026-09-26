import os

from fastapi import Header, HTTPException, Request

# The laptop itself - and a tablet on `adb reverse`, whose traffic arrives over loopback too.
_LOOPBACK_CLIENTS = {"127.0.0.1", "::1"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def pairing_token_enabled() -> bool:
    return bool(os.getenv("BACKEND_PAIRING_TOKEN"))


def _host_name(host_header: str) -> str:
    host = (host_header or "").strip().lower()
    if host.startswith("["):  # [::1]:8000
        return host[: host.find("]") + 1] if "]" in host else host
    return host.split(":", 1)[0]


def is_local_request(request: Request) -> bool:
    """A request from this machine to one of its own local names. Both halves matter: a web page
    anywhere can point its own domain at 127.0.0.1 (DNS rebinding) and reach this port from the
    cook's browser - its requests come from loopback, but with that domain in the Host header.
    A port-forwarding tunnel (ngrok, ssh -R) arrives from loopback with a public Host too."""
    client = request.client.host if request.client else ""
    return client in _LOOPBACK_CLIENTS and _host_name(request.headers.get("host", "")) in _LOCAL_HOSTS


async def require_pairing_token(request: Request, x_pairing_token: str | None = Header(default=None)) -> None:
    if not pairing_token_enabled():
        return
    # DESIGN.md #15: the token guards the LAN (self-signed HTTPS) path. The laptop and the USB
    # tablet were always trusted - this just stops them needing ?token= after a restart.
    if is_local_request(request):
        return
    expected = os.getenv("BACKEND_PAIRING_TOKEN")
    if x_pairing_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing pairing token")
