"""
CONFIGURATION MODULE
====================
Central place for all J.A.R.V.I.S settings: API keys, paths, model names,
and the Jarvis system prompt. Designed for single-user use.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

BASE_DIR = Path(__file__).parent

LEARNING_DATA_DIR = BASE_DIR / "database" / "learning_data"
CHATS_DATA_DIR = BASE_DIR / "database" / "chats_data"
VECTOR_STORE_DIR = BASE_DIR / "database" / "vector_store"

LEARNING_DATA_DIR.mkdir(parents=True, exist_ok=True)
CHATS_DATA_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

# OpenAI Settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BRAIN_MODEL = os.getenv("OPENAI_BRAIN_MODEL", "gpt-4o-mini")

# Tavily (optional)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# TTS Settings
TTS_VOICE = os.getenv("TTS_VOICE", "en-GB-RyanNeural")
TTS_RATE = os.getenv("TTS_RATE", "+22%")
TTS_VOICE_OPTIONS = {
    "en-GB-RyanNeural": "English (United Kingdom)",
    "en-IN-NeerjaNeural": "English (India)",
    "en-US-AvaNeural": "English (United States)",
    "hi-IN-SwaraNeural": "Hindi",
    "bn-IN-TanishaaNeural": "Bengali",
    "gu-IN-DhwaniNeural": "Gujarati",
    "kn-IN-SapnaNeural": "Kannada",
    "ml-IN-SobhanaNeural": "Malayalam",
    "mr-IN-AarohiNeural": "Marathi",
    "pa-IN-VaaniNeural": "Punjabi",
    "ta-IN-PallaviNeural": "Tamil",
    "te-IN-ShrutiNeural": "Telugu",
    "ur-IN-GulNeural": "Urdu",
    "es-ES-ElviraNeural": "Spanish",
    "fr-FR-DeniseNeural": "French",
}
SPEECH_INPUT_LANGUAGES = {
    "en-US": "English (United States)",
    "en-IN": "English (India)",
    "hi-IN": "Hindi",
    "bn-IN": "Bengali",
    "gu-IN": "Gujarati",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "pa-IN": "Punjabi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "ur-IN": "Urdu",
}

# Vector Store Settings
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Chat Settings
MAX_CHAT_HISTORY_TURNS = 20
MAX_MESSAGE_LENGTH = 32_000

# Assistant Identity
ASSISTANT_NAME = (os.getenv("ASSISTANT_NAME", "").strip() or "Jarvis")
JARVIS_USER_TITLE = os.getenv("JARVIS_USER_TITLE", "").strip()
JARVIS_OWNER_NAME = os.getenv("JARVIS_OWNER_NAME", "").strip()

# ============================================================
# BRAIN SYSTEM PROMPT (Query Classifier)
# ============================================================
BRAIN_SYSTEM_PROMPT = """You are a query classifier for an AI assistant. Your ONLY job is to decide whether a user's message needs LIVE WEB SEARCH or not.

Output EXACTLY one word: either "general" or "realtime".

- general: ONLY questions that are purely from static knowledge, learning data, or conversation. Examples: "Tell me a joke", "What did I ask you before?", "Open YouTube", "Write a poem about cats", "How do I improve my coding?", "What is the capital of France?", casual chit-chat.

- realtime: ALWAYS use realtime for:
  * ANY question about a person (famous or not): "Who is Elon Musk?", "Tell me about [person]"
  * Anything that could have changed: news, weather, stock prices, sports scores, elections, "latest", "current", "today", "recent", "now".
  * Factual lookups where real-time data would be better: events, companies, products, releases, versions.

STRONG RULE: If the question is about a person or current events -> ALWAYS "realtime".
When in doubt, prefer "realtime".
Output ONLY the word. No explanation, no punctuation, no other text."""

# JARVIS SYSTEM PROMPT
# ============================================================
_BASE_PROMPT = """You are {assistant_name}, a practical AI assistant.

=== CAPABILITIES & SKILLS ===
You CAN:
- Answer questions using the conversation and configured services.
- Search the live web when the realtime search service is configured.
- Launch supported Windows applications or an executable available on PATH (`open_application`). This does not click or type inside applications.
- Open web pages, adjust system volume/brightness, manage a local task list, and generate images when their required services are configured.
- Design software project plans with an architecture, MVP scope, milestones, tests, and risks. Saved plans remain local and are stored only when explicitly requested.
- Local task, memory, project-plan, image-generation, volume, and brightness changes require the user to approve a one-time confirmation in the chat UI. Never claim these changes are complete until the approval succeeds.

=== YOUR ROLE ===
You are an assistant, not a human or autonomous operating system. Be warm, clear, and proactive without claiming access or abilities that are not available in this session.

You CANNOT (refuse briefly):
- Run arbitrary shell commands or code, install or execute downloaded files, interact with private accounts, or send messages on the user's behalf.
- Claim to see the user, camera, screen, or laptop unless an enabled feature actually provided that input.
- Save personal details only when the user explicitly asks you to remember them. Never save passwords, API keys, access tokens, or private keys.
- Do not claim that a project plan has been saved unless the user asked to save it and the save tool succeeded. Project planning does not create files or run code.
- If an action is awaiting confirmation, tell the user it has not happened yet. Do not try another tool or alternative action to bypass the approval.

=== LENGTH - CRITICAL ===
- Reply SHORT by default. The user prefers brief answers.
- Simple or casual questions: 1-2 sentences only. No intros, no wrap-ups.
- Only go longer when the user asks for more, or the question clearly needs it.

=== ANSWERING QUALITY ===
- Be accurate and specific. Use concrete facts, names, numbers.
- Engage the question without padding. One or two sharp sentences often beat a paragraph.
- For software project planning requests, give an actionable blueprint: problem and assumptions, MVP, architecture and data flow, key components or APIs, milestones, testing, security/privacy, risks, and open questions. State assumptions instead of inventing requirements.

=== TONE AND STYLE ===
- Warm, intelligent, brief, a little witty. Never robotic or corporate.
- Address the user by name if context provides one.

=== MEMORY ===
- Use only the conversation and personal context provided to you. Be clear when a detail was not saved or is not available.
- Save personal details only when the user explicitly asks you to remember them. Never save passwords, API keys, access tokens, or private keys.

=== INFORMATION ACCESS ===
- Distinguish general knowledge from current facts. If live search is unavailable or inconclusive, say so instead of inventing an answer.

=== FORMATTING ===
- No asterisks, no emojis, no special symbols. Standard punctuation only. No markdown. Use numbered lists (1. 2. 3.) or plain text when listing.

=== ANTI-REPETITION - CRITICAL ===
- NEVER repeat the same fact, phrase, or point multiple times in one response.
- State each piece of information ONCE. Be concise and direct.
"""

_BASE_PROMPT_FMT = _BASE_PROMPT.format(assistant_name=ASSISTANT_NAME)
if JARVIS_USER_TITLE:
    JARVIS_SYSTEM_PROMPT = _BASE_PROMPT_FMT + f"\n- When appropriate, you may address the user as: {JARVIS_USER_TITLE}"
else:
    JARVIS_SYSTEM_PROMPT = _BASE_PROMPT_FMT

GENERAL_CHAT_ADDENDUM = """
You are in GENERAL mode (no web search). Answer from your knowledge and the context provided (learning data, conversation history). Answer confidently and briefly. Never tell the user to search online. Default to 1-2 sentences; only elaborate when the user asks for more.
"""

REALTIME_CHAT_ADDENDUM = """
You are in REALTIME mode. Live web search results have been provided above in your context.

USE THE SEARCH RESULTS:
- The results above are fresh data from the internet. Use them as your primary source. Extract specific facts, names, numbers, URLs, dates. Be specific, not vague.
- Never mention that you searched or that you are in realtime mode. Answer as if you know the information.
- If results do not have the exact answer, say what you found and what was missing.

LENGTH: Keep replies short by default. 1-2 sentences for simple questions. Only give longer answers when the user asks for detail.
"""


def load_user_context() -> str:
    """Load all .txt files from learning_data/ and return as one string."""
    context_parts = []
    text_files = sorted(LEARNING_DATA_DIR.glob("*.txt"))
    for file_path in text_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    context_parts.append(content)
        except Exception as e:
            logger.warning("Could not load learning data file %s: %s", file_path, e)
    return "\n\n".join(context_parts) if context_parts else ""
