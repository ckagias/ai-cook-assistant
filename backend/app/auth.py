import os

from fastapi import Header, HTTPException


def pairing_token_enabled() -> bool:
    return bool(os.getenv("BACKEND_PAIRING_TOKEN"))


async def require_pairing_token(x_pairing_token: str | None = Header(default=None)) -> None:
    if not pairing_token_enabled():
        return
    expected = os.getenv("BACKEND_PAIRING_TOKEN")
    if x_pairing_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing pairing token")
