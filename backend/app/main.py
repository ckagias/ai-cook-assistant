import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Windows registers .js as text/plain, which makes browsers refuse to execute ES modules served that way.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


# Mounted last: mounting at "/" before the routes above would shadow every one of them.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
