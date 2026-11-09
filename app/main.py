"""
main.py — FastAPI application for J.A.R.V.I.S
Endpoints:
  GET  /health                    → Health check
  POST /chat/stream               → General chat (SSE streaming)
  POST /chat/realtime/stream      → Realtime chat with web search (SSE)
  POST /chat/jarvis/stream        → Brain mode (auto-routes general/realtime)
  GET  /                          → Serve frontend
"""
import logging
import json
import os
import tempfile
from pathlib import Path
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────
app = FastAPI(title="J.A.R.V.I.S", description="Just A Rather Very Intelligent System", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_BROWSER_ORIGINS = {"http://localhost:8000", "http://127.0.0.1:8000"}


@app.middleware("http")
async def reject_untrusted_browser_origins(request: Request, call_next):
    """Block cross-site browser requests, including simple multipart form posts."""
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_BROWSER_ORIGINS:
        return HTMLResponse("Cross-origin requests are not allowed.", status_code=403)
    return await call_next(request)

# Determine base directory
BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
VOICE_AGENT_DIR = BASE_DIR / "voice_agent"

# Mount frontend and static assets
# /static targets the gathered_assets, models, etc.
if (BASE_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# /frontend targets the UI files (html, css, js)
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

if VOICE_AGENT_DIR.exists():
    app.mount(
        "/voice-agent",
        StaticFiles(directory=str(VOICE_AGENT_DIR), html=True),
        name="voice-agent",
    )


# ─────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "jarvis"
    tts_voice: Optional[str] = None


# ─────────────────────────────────────────
# Startup Event
# ─────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Initialize vector store on startup."""
    logger.info("J.A.R.V.I.S starting up...")
    try:
        from app.services.vector_store import load_vector_store
        load_vector_store()
        logger.info("Vector store initialized.")
    except Exception as e:
        logger.warning("Vector store init failed (non-fatal): %s", e)


# ─────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────
@app.get("/health")
async def health():
    from config import OPENAI_API_KEY, OPENAI_MODEL
    return {
        "status": "healthy",
        "model": OPENAI_MODEL,
        "api_key_set": bool(OPENAI_API_KEY),
    }


@app.get("/speech/voices")
async def speech_voices():
    from config import SPEECH_INPUT_LANGUAGES, TTS_VOICE, TTS_VOICE_OPTIONS

    return {
        "input_languages": SPEECH_INPUT_LANGUAGES,
        "output_voices": TTS_VOICE_OPTIONS,
        "default_voice": TTS_VOICE,
    }


@app.post("/actions/{action_id}/approve")
async def approve_pending_action(action_id: str):
    """Approve and execute one pending local action."""
    from app.services.action_approval_service import (
        ApprovalExpiredError,
        ApprovalNotFoundError,
        resolve_approval,
    )

    try:
        return resolve_approval(action_id, approve=True)
    except ApprovalExpiredError as error:
        raise HTTPException(status_code=410, detail=str(error)) from error
    except ApprovalNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (OSError, RuntimeError, ValueError) as error:
        logger.error("Approved action failed: %s", error)
        raise HTTPException(status_code=500, detail=f"Action failed: {error}") from error


@app.post("/actions/{action_id}/deny")
async def deny_pending_action(action_id: str):
    """Deny and discard one pending local action."""
    from app.services.action_approval_service import (
        ApprovalExpiredError,
        ApprovalNotFoundError,
        resolve_approval,
    )

    try:
        return resolve_approval(action_id, approve=False)
    except ApprovalExpiredError as error:
        raise HTTPException(status_code=410, detail=str(error)) from error
    except ApprovalNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (OSError, RuntimeError, ValueError) as error:
        logger.error("Action denial failed: %s", error)
        raise HTTPException(status_code=500, detail=f"Action denial failed: {error}") from error


@app.get("/actions/pending")
async def read_pending_approvals():
    """Recover pending confirmation cards for the local browser UI."""
    from app.services.action_approval_service import get_pending_approvals

    try:
        return {"approvals": get_pending_approvals()}
    except (OSError, RuntimeError, ValueError) as error:
        logger.error("Pending approval read failed: %s", error)
        raise HTTPException(status_code=500, detail=f"Could not read pending approvals: {error}") from error


@app.get("/actions/audit")
async def read_action_audit(limit: int = 100):
    """Read recent local approval and execution events without action payloads."""
    from app.services.action_approval_service import MAX_AUDIT_EVENTS, get_audit_events

    if not 1 <= limit <= MAX_AUDIT_EVENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Limit must be between 1 and {MAX_AUDIT_EVENTS}.",
        )
    try:
        return {"events": get_audit_events(limit)}
    except (OSError, RuntimeError, ValueError) as error:
        logger.error("Action audit read failed: %s", error)
        raise HTTPException(status_code=500, detail=f"Could not read audit log: {error}") from error


def resolve_tts_voice(requested_voice: Optional[str]) -> str:
    from config import TTS_VOICE, TTS_VOICE_OPTIONS

    voice = requested_voice or TTS_VOICE
    if voice not in TTS_VOICE_OPTIONS:
        raise HTTPException(status_code=422, detail="Unsupported speech output voice.")
    return voice


# ─────────────────────────────────────────
# TTS Helper
# ─────────────────────────────────────────
async def generate_tts_audio(text: str, voice: Optional[str] = None) -> Optional[str]:
    """Generate TTS audio using edge-tts. Returns base64 MP3 string."""
    try:
        import edge_tts
        import base64
        from config import TTS_VOICE, TTS_RATE

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        communicate = edge_tts.Communicate(text, voice or TTS_VOICE, rate=TTS_RATE)
        await communicate.save(tmp_path)

        with open(tmp_path, "rb") as f:
            audio_data = f.read()
        os.unlink(tmp_path)

        if audio_data:
            return base64.b64encode(audio_data).decode("utf-8")
    except Exception as e:
        logger.warning("TTS generation failed: %s", e)
    return None


def split_into_tts_sentences(text: str):
    """Split text into sentences for TTS chunking."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


# ─────────────────────────────────────────
# SSE Stream Wrapper
# ─────────────────────────────────────────
async def stream_with_tts(
    token_generator: AsyncGenerator,
    session_id: str,
    message: str,
    mode_label: str,
    tts_voice: str,
) -> AsyncGenerator[str, None]:
    """
    Wraps a token generator to:
    1. Yield activity events
    2. Stream tokens
    3. Generate and yield TTS audio chunks
    4. Yield done event
    """
    from app.services import chat_service

    # Activity: show mode
    yield f"data: {json.dumps({'type': 'activity', 'event': 'Processing', 'detail': f'Mode: {mode_label}'})}\n\n"

    full_response = ""
    tts_buffer = ""

    async for chunk in token_generator:
        # Forward all SSE events from generator
        yield chunk

        # Extract token content
        if chunk.startswith("data: "):
            try:
                data = json.loads(chunk[6:])
                if data.get("type") == "token":
                    token = data.get("content", "")
                    full_response += token
                    tts_buffer += token

                    # Send TTS when we have a complete sentence
                    sentences = split_into_tts_sentences(tts_buffer)
                    if len(sentences) > 1:
                        # All complete sentences except the last (which may be incomplete)
                        for sentence in sentences[:-1]:
                            audio_b64 = await generate_tts_audio(sentence, tts_voice)
                            if audio_b64:
                                yield f"data: {json.dumps({'type': 'audio', 'data': audio_b64})}\n\n"
                        tts_buffer = sentences[-1]  # Keep last incomplete sentence

                elif data.get("type") == "done":
                    # Generate TTS for any remaining text
                    if tts_buffer.strip():
                        audio_b64 = await generate_tts_audio(tts_buffer.strip(), tts_voice)
                        if audio_b64:
                            yield f"data: {json.dumps({'type': 'audio', 'data': audio_b64})}\n\n"
                    # Save conversation
                    chat_service.add_message(session_id, "user", message)
                    chat_service.add_message(session_id, "assistant", full_response)
            except (json.JSONDecodeError, KeyError):
                pass


# ─────────────────────────────────────────
# Chat Endpoints
# ─────────────────────────────────────────
@app.post("/chat/stream")
async def chat_general(request: ChatRequest):
    """General chat endpoint — OpenAI GPT, no web search."""
    from app.services import chat_service
    from app.services.openai_service import stream_general_chat

    session_id = chat_service.get_or_create_session(request.session_id)
    history = chat_service.get_history_messages(session_id)
    tts_voice = resolve_tts_voice(request.tts_voice)

    token_gen = stream_general_chat(request.message, history, session_id)

    async def event_stream():
        yield f"data: {json.dumps({'type': 'activity', 'event': 'Mode', 'detail': 'General — answering from knowledge'})}\n\n"
        async for chunk in stream_with_tts(
            token_gen, session_id, request.message, "General", tts_voice
        ):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/chat/realtime/stream")
async def chat_realtime(request: ChatRequest):
    """Realtime chat endpoint — web search + OpenAI GPT."""
    from app.services import chat_service
    from app.services.realtime_service import stream_realtime_chat

    session_id = chat_service.get_or_create_session(request.session_id)
    history = chat_service.get_history_messages(session_id)
    tts_voice = resolve_tts_voice(request.tts_voice)

    token_gen = stream_realtime_chat(request.message, history, session_id)

    async def event_stream():
        async for chunk in stream_with_tts(
            token_gen, session_id, request.message, "Realtime", tts_voice
        ):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/chat/jarvis/stream")
async def chat_jarvis(request: ChatRequest):
    """
    JARVIS brain mode — auto-classifies and routes to general or realtime.
    This is the main endpoint used by the default Jarvis mode button.
    """
    from app.services import chat_service
    from app.services.openai_service import classify_query, stream_general_chat
    from app.services.realtime_service import stream_realtime_chat

    session_id = chat_service.get_or_create_session(request.session_id)
    history = chat_service.get_history_messages(session_id)
    tts_voice = resolve_tts_voice(request.tts_voice)

    async def event_stream():
        # Step 1: Classify
        yield f"data: {json.dumps({'type': 'activity', 'event': 'Brain', 'detail': 'Analyzing your query...'})}\n\n"
        route = await classify_query(request.message)
        yield f"data: {json.dumps({'type': 'activity', 'event': 'Routing', 'detail': f'→ {route.capitalize()} mode selected'})}\n\n"

        # Step 2: Route
        if route == "realtime":
            token_gen = stream_realtime_chat(request.message, history, session_id)
        else:
            token_gen = stream_general_chat(request.message, history, session_id)

        async for chunk in stream_with_tts(
            token_gen, session_id, request.message, route.capitalize(), tts_voice
        ):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─────────────────────────────────────────
# User-initiated image analysis
# ─────────────────────────────────────────
@app.post("/vision/analyze")
async def analyze_uploaded_image(file: UploadFile = File(...)):
    """Analyze a user-selected image in memory; do not save it to disk."""
    from app.services.vision_service import (
        MAX_IMAGE_BYTES,
        VisionConfigurationError,
        VisionProviderError,
        analyze_image,
        detect_image_media_type,
    )

    try:
        image = await file.read(MAX_IMAGE_BYTES + 1)
    finally:
        await file.close()

    try:
        media_type = detect_image_media_type(image)
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error

    try:
        description = await analyze_image(image, media_type)
    except VisionConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except VisionProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {"analysis": description}


# ─────────────────────────────────────────
# Frontend Serving
# ─────────────────────────────────────────
@app.get("/")
async def serve_frontend():
    """Serve the Iron Man HUD frontend."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>J.A.R.V.I.S — Frontend not found. Run from d:\\JARVIS_V3</h1>")


@app.get("/frontend/{path:path}")
async def serve_frontend_files(path: str):
    """Serve frontend static files."""
    file_path = FRONTEND_DIR / path
    if file_path.exists():
        return FileResponse(str(file_path))
    return HTMLResponse("Not found", status_code=404)
