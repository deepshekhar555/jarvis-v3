"""
models.py — Pydantic models for J.A.R.V.I.S API.
"""
from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "jarvis"  # jarvis | general | realtime


class ChatResponse(BaseModel):
    response: str
    session_id: str
    mode_used: Optional[str] = None
