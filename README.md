# J.A.R.V.I.S V3

J.A.R.V.I.S is a local-first assistant prototype with a FastAPI backend and a browser-based chat interface. It combines model chat, optional web search, browser speech input, text-to-speech, and a small set of desktop tools.

## What works today

- Streamed chat through an OpenAI-compatible model configured in `.env`.
- Optional realtime web search when `TAVILY_API_KEY` is configured.
- Browser speech recognition and spoken replies (browser and voice availability varies).
- A separate voice-agent console at [http://localhost:8000/voice-agent/](http://localhost:8000/voice-agent/) with continuous listening under an explicit start/stop control, configurable speech languages, typed fallback, realtime mode, and approval buttons for local actions.
- User-initiated PNG/JPEG/WebP image analysis using the configured OpenAI model. The UI can capture one camera frame or select an image, shows a preview, asks for confirmation before upload, and processes images in memory rather than saving them to disk.
- Explicit local memory: ask J.A.R.V.I.S to remember, list, or forget notes. Saving or deleting a note requires approval; passwords, API keys, tokens, and private keys are refused.
- Software project planning: request an architecture, MVP scope, milestones, test strategy, and risks. Plans are stored locally in `database/project_plans/` only when explicitly requested; this feature does not create or execute project code.
- Explicit approval for task-board, memory, project-plan, image generation, volume, and brightness changes. The chat displays the proposed action and requires a one-time approval click before execution; approvals expire after five minutes and pending cards can be recovered after a page reload while the server remains running.
- A local action audit (last 500 events), viewable in Settings or through `GET /actions/audit`. The audit records action type and outcome but omits task, note, and plan contents.
- Windows app launching for supported aliases (Notepad, Calculator, Command Prompt, File Explorer, Paint, Edge, Chrome, Firefox, and VS Code) or an executable found on `PATH`. Launching does not pass arguments or run a shell command.
- Opening web pages, approved volume/brightness adjustments, a local task list, and approved image generation.

The assistant does **not** currently have general-purpose mouse/keyboard control, continuous camera access, reliable face identity verification, autonomous software installation, or the ability to safely operate every application. Camera access is user-initiated for one frame at a time; it does not monitor continuously. Image analysis is limited to a captured or selected image the user previews and consents to sending to the configured model. It is not sentient and does not have human intelligence or emotions. Do not treat generated answers as guaranteed facts.

## Setup

Requirements: Windows, Python 3.11+, and an OpenAI API key.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root and set `OPENAI_API_KEY`. `TAVILY_API_KEY` is optional and enables web search. Then start the server:

```powershell
python run.py
```

Open [http://localhost:8000](http://localhost:8000).

If chat reports that the AI provider rejected the API key, create or update `OPENAI_API_KEY` in `.env` with a valid key from your provider account, then restart the server. Do not paste API keys into chat or commit them to the repository. The health endpoint confirms the server is running; a real chat request is needed to verify provider access.

## Project layout

- `app/`: FastAPI routes and chat, search, and tool services.
- `frontend/`: main browser UI, voice input, and streamed response handling.
- `voice_agent/`: standalone voice-agent interface and browser speech workflow.
- `skills/`: local operating-system helpers.
- `database/`: local chat, task, learning, and vector-store data.
- `database/memory.json`: user-approved personal notes, created when the first note is saved.
- `database/project_plans/`: locally saved project plan documents, created on the first explicit save.
- `database/action_audit.json`: local approval, denial, expiration, and execution events; action payloads are not stored in the audit.

## Safety and privacy

Desktop tools are intentionally narrow: app launch accepts an app name, not a shell command; downloaded installers and arbitrary commands are not executed. Changes to local tasks, memory, project plans, system volume, and screen brightness require a visible one-time approval, and decisions are recorded in a local audit log. Pending approvals are held in memory and expire after five minutes. The server binds to localhost and is not intended for network exposure. Microphone access is browser-controlled; image analysis is user-initiated and discloses transfer to the configured hosted model. Keep API keys in `.env`, never in frontend code or commits.

## Next development milestones

1. Build narrow, testable workflows for selected apps before considering broader UI automation.
2. Add audit export and retention controls if the local audit grows beyond the current bounded history.

Each milestone should be implemented and validated independently; broad unattended control and arbitrary downloads are not safe defaults.
