import os

from fastapi import Header, HTTPException, Request

def pairing_token_enabled() -> bool:
    return bool(os.getenv("BACKEND_PAIRING_TOKEN"))

async def require_pairing_token(request: Request, x_pairing_token: str | None = Header(default=None)) -> None:
    if not pairing_token_enabled():
        return
    # Bypass token requirement for the local machine
    if request.client and request.client.host in ("127.0.0.1", "::1", "localhost"):
        return
    expected = os.getenv("BACKEND_PAIRING_TOKEN")
    if x_pairing_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing pairing token")
