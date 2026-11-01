"""
Prospect Brief Engine - web server.

    GET  /           -> the HTML form
    WS   /ws/brief   -> send {"name", "company", "role", "notes"}; receive live events,
                        ending with {"type": "done", "brief"} or {"type": "error", "message"}

Run:  uvicorn main:app --reload
"""
from pathlib import Path

import openai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError, field_validator

from agent import ProspectBriefAgent

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Prospect Brief Engine")
agent = ProspectBriefAgent()


class ProspectRequest(BaseModel):
    name: str
    company: str
    role: str
    notes: str = ""

    @field_validator("name", "company", "role")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws/brief")
async def brief_socket(ws: WebSocket) -> None:
    await ws.accept()

    async def emit(event: dict) -> None:
        await ws.send_json(event)   # send_json will semd message from backend to fromtend

    try:
        while True:  # one connection can generate several briefs
            data = await ws.receive_json()  # recive_json will basically read data that is coming from frontend
            try:
                prospect = ProspectRequest(**data)
                brief = await agent.run(**prospect.model_dump(), emit=emit)
                await emit({"type": "done", "brief": brief})
            except ValidationError as exc:
                first = exc.errors()[0]
                await emit({"type": "error", "message": f"Invalid input: {first['loc'][0]} {first['msg']}"})
            except openai.RateLimitError:
                await emit({"type": "error", "message": "Rate limited by the AI provider. Wait a moment and retry."})
            except openai.APIConnectionError:
                await emit({"type": "error", "message": "Could not reach the AI provider."})
            except openai.APIStatusError as exc:
                await emit({"type": "error", "message": f"AI provider error ({exc.status_code}): {exc.message}"})
            except RuntimeError as exc:
                await emit({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass  # user closed the page mid-run; nothing to clean up


    # fromtend--------> backend ---> agent (run , accepted emit function now run function will use emit function to send something to user via socket )
