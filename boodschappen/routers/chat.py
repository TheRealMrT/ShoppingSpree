"""
POST /api/chat  —  Kookassistent via Ollama
"""
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

OLLAMA_BASE = "http://localhost:11434"
CHAT_MODEL  = "qwen3.5:9b"   # ollama pull qwen3.5:9b

SYSTEM_PROMPT = """\
Je bent een behulpzame, vriendelijke kookassistent voor een Nederlands gezin.
Je helpt met recepten, maaltijdplanning, boodschappenlijsten en kooktips.
Antwoord altijd in het Nederlands. Houd antwoorden beknopt en praktisch.
Als er gezinsinformatie beschikbaar is, houd daar dan rekening mee (allergieën, dieetwensen).
"""


class ChatMessage(BaseModel):
    role: str     # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    context: Optional[str] = None   # extra system context (gezin, huidig recept)
    model: Optional[str] = None     # override; default = CHAT_MODEL


@router.post("/chat")
async def chat_endpoint(data: ChatRequest):
    model = data.model or CHAT_MODEL

    system = SYSTEM_PROMPT
    if data.context:
        system += f"\n\nHuidige context:\n{data.context}"

    messages = [{"role": "system", "content": system}]
    messages.extend([{"role": m.role, "content": m.content} for m in data.messages])

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/chat",
                json={"model": model, "stream": False, "messages": messages},
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Ollama niet bereikbaar. Is 'ollama serve' actief?")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout — probeer opnieuw.")

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model}' niet gevonden. Voer 'ollama pull {model}' uit.",
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama fout {resp.status_code}")

    content = resp.json().get("message", {}).get("content", "")
    return {"response": content, "model": model}
