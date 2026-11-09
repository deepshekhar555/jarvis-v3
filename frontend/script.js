/* ================================================================
   J.A.R.V.I.S Frontend — Main Application Logic (v3)
   ================================================================
   Architecture:
   1. CHAT MESSAGING — SSE streaming token-by-token from FastAPI
   2. TEXT-TO-SPEECH — Base64 audio chunks queued & played
   3. SPEECH RECOGNITION — Web Speech API voice input
   4. ANIMATED ORB — WebGL visual indicator (orb.js)
   5. MODE SWITCHING — Jarvis / General / Realtime
   6. SESSION MANAGEMENT — UUID session per conversation
   7. ACTIVITY PANEL — Shows AI routing decisions live
   8. SEARCH PANEL — Shows Tavily web search results
   ================================================================ */

const API = (typeof window !== 'undefined' && window.location.origin)
    ? window.location.origin
    : 'http://localhost:8000';

/* ── State ── */
let sessionId      = null;
let currentMode    = 'jarvis';        // jarvis | general | realtime
let isStreaming    = false;
let isListening    = false;
let autoListenMode = false;
let orb            = null;
let recognition    = null;
let ttsPlayer      = null;
const pendingApprovals = new Map();

const SPEECH_ERROR_MAX_RETRIES = 3;
let   speechErrorRetryCount    = 0;
const SPEECH_SEND_DELAY_MS     = 500;
const SPEECH_RESTART_DELAY_MS  = 700;
let   speechSendTimeout        = null;
let   pendingSendTranscript    = null;
let   safariVoiceHintShown     = false;

/* ── Settings ── */
const SETTINGS_KEY      = 'jarvis_settings_v3';
const DEFAULT_SETTINGS  = {
    autoOpenActivity: true,
    autoOpenSearchResults: true,
    ttsEnabled: true,
    speechInputLanguage: 'en-US',
    speechOutputVoice: 'en-GB-RyanNeural',
};
let   settings          = { ...DEFAULT_SETTINGS };

/* ── DOM ── */
const $ = id => document.getElementById(id);

const chatMessages          = $('chat-messages');
const messageInput          = $('message-input');
const sendBtn               = $('send-btn');
const micBtn                = $('mic-btn');
const ttsBtn                = $('tts-btn');
const newChatBtn            = $('new-chat-btn');
const charCount             = $('char-count');
const welcomeTitle          = $('welcome-title');
const modeSlider            = $('mode-slider');
const btnJarvis             = $('btn-jarvis');
const btnGeneral            = $('btn-general');
const btnRealtime           = $('btn-realtime');
const statusDot             = document.querySelector('.status-dot');
const statusText            = document.querySelector('.status-text');
const orbContainer          = $('orb-container');
const searchResultsToggle   = $('search-results-toggle');
const searchResultsWidget   = $('search-results-widget');
const searchResultsClose    = $('search-results-close');
const searchResultsBody     = $('search-results-body');
const activityPanel         = $('activity-panel');
const activityToggle        = $('activity-toggle');
const activityClose         = $('activity-close');
const activityList          = $('activity-list');
const panelOverlay          = $('panel-overlay');
const speechWidget          = $('speech-widget');
const speechWidgetText      = $('speech-widget-text');
const settingsBtn           = $('settings-btn');
const settingsPanel         = $('settings-panel');
const settingsOverlay       = $('settings-overlay');
const settingsClose         = $('settings-close');
const toggleAutoActivity    = $('toggle-auto-activity');
const toggleAutoSearch      = $('toggle-auto-search');
const toggleThinkingSounds  = $('toggle-thinking-sounds');
const speechInputLanguage   = $('speech-input-language');
const speechOutputVoice     = $('speech-output-voice');
const toastContainer        = $('toast-container');
const bootScreen            = $('boot-screen');
const mainApp               = $('main-app');

/* ================================================================
   TTS PLAYER — Queue-based audio playback
   ================================================================ */
class TTSPlayer {
    constructor() {
        this.queue   = [];
        this.playing = false;
        this.enabled = true;
        this.stopped = false;
        this.audio   = document.createElement('audio');
        this.audio.preload = 'auto';
        this._loopId = 0;
        this.onPlaybackComplete = null;
    }

    unlock() {
        // Unlock audio context for iOS/Safari autoplay policy
        const silentWav = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
        this.audio.src = silentWav;
        const p = this.audio.play();
        if (p) p.catch(() => {});
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const g = ctx.createGain(); g.gain.value = 0;
            const o = ctx.createOscillator();
            o.connect(g); g.connect(ctx.destination);
            o.start(0); o.stop(ctx.currentTime + 0.001);
            setTimeout(() => ctx.close(), 200);
        } catch (_) {}
    }

    enqueue(base64Audio) {
        if (!this.enabled || this.stopped) return;
        this.queue.push(base64Audio);
        if (!this.playing) this._playLoop();
    }

    stop() {
        this.stopped = true;
        this.audio.pause();
        this.audio.removeAttribute('src');
        this.audio.load();
        this.queue   = [];
        this.playing = false;
        if (ttsBtn) ttsBtn.classList.remove('tts-speaking');
        if (orbContainer) orbContainer.classList.remove('speaking');
        if (orb) orb.setActive(false);
        if (typeof this.onPlaybackComplete === 'function') this.onPlaybackComplete();
    }

    reset() {
        this.stop();
        this.stopped = false;
        this._loopId = (this._loopId || 0) + 1;
    }

    async _playLoop() {
        if (this.playing) return;
        this.playing = true;
        this._loopId = (this._loopId || 0) + 1;
        const myId = this._loopId;

        if (ttsBtn) ttsBtn.classList.add('tts-speaking');
        if (orbContainer) orbContainer.classList.add('speaking');
        if (orb) orb.setActive(true);

        while (this.queue.length > 0) {
            if (this.stopped || myId !== this._loopId) break;
            const b64 = this.queue.shift();
            try { await this._playB64(b64); } catch (e) { console.warn('TTS chunk error:', e); }
        }

        if (myId !== this._loopId) { this.playing = false; return; }
        this.playing = false;
        if (ttsBtn) ttsBtn.classList.remove('tts-speaking');
        if (orbContainer) orbContainer.classList.remove('speaking');
        if (orb) orb.setActive(false);
        if (typeof this.onPlaybackComplete === 'function') this.onPlaybackComplete();
    }

    _playB64(b64) {
        return new Promise(resolve => {
            this.audio.src = 'data:audio/mp3;base64,' + b64;
            const done = () => resolve();
            this.audio.onended = done;
            this.audio.onerror = done;
            const p = this.audio.play();
            if (p) p.catch(done);
        });
    }
}

/* ================================================================
   BOOT SEQUENCE
   ================================================================ */
function bootSequence() {
    // Show boot screen for 2.8s then reveal main app
    setTimeout(() => {
        if (bootScreen) {
            bootScreen.classList.add('fade-out');
            setTimeout(() => {
                bootScreen.style.display = 'none';
                if (mainApp) mainApp.style.display = 'flex';
                init();
            }, 800);
        }
    }, 2800);
}

/* ================================================================
   INIT
   ================================================================ */
function init() {
    loadSettings();
    ttsPlayer = new TTSPlayer();
    ttsPlayer.enabled = settings.ttsEnabled;
    ttsPlayer.onPlaybackComplete = maybeRestartListening;

    if (settings.ttsEnabled) {
        if (ttsBtn) ttsBtn.classList.add('tts-active');
    } else {
        if (ttsBtn) ttsBtn.classList.remove('tts-active');
    }

    setGreeting();
    initOrb();
    initMatrixCanvas(); // Boot the Next-Gen Holographic Background
    initSpeech();
    checkHealth();
    bindEvents();
    loadPendingApprovals();
    
    // Play JARVIS boot sequence sound
    playJarvisSound('boot');

    setMode(currentMode);
    autoResizeInput();
}

/* ── JARVIS WebAudio Synthesizer (Sci-Fi sounds) ── */
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
function playJarvisSound(type) {
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    osc.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    
    const now = audioCtx.currentTime;
    if (type === 'boot') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(300, now);
        osc.frequency.exponentialRampToValueAtTime(800, now + 0.5);
        gainNode.gain.setValueAtTime(0, now);
        gainNode.gain.linearRampToValueAtTime(0.1, now + 0.1);
        gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.6);
        osc.start(now);
        osc.stop(now + 0.6);
    } else if (type === 'listen') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(600, now);
        osc.frequency.setValueAtTime(800, now + 0.1);
        gainNode.gain.setValueAtTime(0, now);
        gainNode.gain.linearRampToValueAtTime(0.05, now + 0.05);
        gainNode.gain.linearRampToValueAtTime(0, now + 0.2);
        osc.start(now);
        osc.stop(now + 0.2);
    } else if (type === 'think') {
        osc.type = 'square';
        osc.frequency.setValueAtTime(400, now);
        osc.frequency.setValueAtTime(350, now + 0.1);
        gainNode.gain.setValueAtTime(0, now);
        gainNode.gain.linearRampToValueAtTime(0.02, now + 0.05);
        gainNode.gain.linearRampToValueAtTime(0, now + 0.15);
        osc.start(now);
        osc.stop(now + 0.15);
    }
}

/* ── Greeting ── */
function setGreeting() {
    const h = new Date().getHours();
    let g = 'Good evening.';
    if (h < 12) g = 'Good morning.';
    else if (h < 17) g = 'Good afternoon.';
    else if (h >= 22) g = 'Burning the midnight oil?';
    if (welcomeTitle) welcomeTitle.textContent = g;
}

/* ── Orb ── */
function initOrb() {
    if (typeof OrbRenderer === 'undefined' || !orbContainer) return;
    try {
        orb = new OrbRenderer(orbContainer, {
            hue: 180,                           // Cyan hue for JARVIS
            hoverIntensity: 0.35,
            backgroundColor: [0.02, 0.02, 0.06],
        });
    } catch (e) { console.warn('Orb init failed:', e); }
}

/* ── Next-Gen Matrix Canvas Animation ── */
function initMatrixCanvas() {
    const canvas = document.getElementById("matrixCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const characters = "01ABCDEFGHIJKLMNOPQRSTUVWXYZ🤖Δ∑Ω101001";
    const fontSize = 16;
    const columns = Math.floor(canvas.width / fontSize);
    const drops = Array(columns).fill(0);

    function drawMatrix() {
        ctx.fillStyle = "rgba(0, 0, 0, 0.05)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#00ffea";
        ctx.font = `${fontSize}px monospace`;

        drops.forEach((y, index) => {
            const text = characters[Math.floor(Math.random() * characters.length)];
            ctx.fillText(text, index * fontSize, y * fontSize);
            if (y * fontSize > canvas.height && Math.random() > 0.975) {
                drops[index] = 0;
            }
            drops[index]++;
        });
        requestAnimationFrame(drawMatrix);
    }
    drawMatrix();

    window.addEventListener('resize', () => {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    });
}


/* ── Settings ── */
function loadSettings() {
    try {
        const saved = localStorage.getItem(SETTINGS_KEY);
        if (saved) settings = { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
        if (toggleAutoActivity)   syncToggle(toggleAutoActivity, settings.autoOpenActivity);
        if (toggleAutoSearch)     syncToggle(toggleAutoSearch, settings.autoOpenSearchResults);
        if (toggleThinkingSounds) syncToggle(toggleThinkingSounds, settings.ttsEnabled);
        if (speechInputLanguage) speechInputLanguage.value = settings.speechInputLanguage;
        if (speechOutputVoice) speechOutputVoice.value = settings.speechOutputVoice;
    } catch (_) {}
}

function saveSettings() {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch (_) {}
}

function syncToggle(el, value) {
    if (!el) return;
    if (value) { el.classList.add('on'); el.setAttribute('aria-checked', 'true'); }
    else        { el.classList.remove('on'); el.setAttribute('aria-checked', 'false'); }
}

/* ================================================================
   MODE SWITCH
   ================================================================ */
function setMode(mode) {
    currentMode = mode;
    // Slider positions: left=jarvis, center=general, right=realtime
    if (!modeSlider) return;
    if (mode === 'jarvis') {
        modeSlider.classList.remove('center', 'right');
    } else if (mode === 'general') {
        modeSlider.classList.remove('right');
        modeSlider.classList.add('center');
    } else {
        modeSlider.classList.remove('center');
        modeSlider.classList.add('right');
    }
    [btnJarvis, btnGeneral, btnRealtime].forEach(btn => {
        if (btn) { btn.classList.remove('active'); btn.setAttribute('aria-pressed', 'false'); }
    });
    const activeBtn = mode === 'jarvis' ? btnJarvis : mode === 'general' ? btnGeneral : btnRealtime;
    if (activeBtn) { activeBtn.classList.add('active'); activeBtn.setAttribute('aria-pressed', 'true'); }

    // Show/hide search toggle based on mode
    if (searchResultsToggle) {
        searchResultsToggle.style.opacity = mode === 'realtime' ? '1' : '0.4';
    }
}

/* ── Endpoint helper ── */
function getEndpoint(mode) {
    if (mode === 'general')  return `${API}/chat/stream`;
    if (mode === 'realtime') return `${API}/chat/realtime/stream`;
    return `${API}/chat/jarvis/stream`;  // default: brain mode
}

/* ================================================================
   HEALTH CHECK
   ================================================================ */
async function checkHealth() {
    try {
        const controller = new AbortController();
        const tid = setTimeout(() => controller.abort(), 5000);
        const r = await fetch(`${API}/health`, { signal: controller.signal });
        clearTimeout(tid);
        const d = await r.json().catch(() => null);
        const ok = d && (d.status === 'healthy' || d.status === 'degraded');
        setStatus(ok, ok ? 'Online' : 'Degraded');
    } catch (e) {
        setStatus(false, 'Offline');
    }
}

function setStatus(online, label) {
    if (statusDot)  { statusDot.className  = 'status-dot' + (online ? '' : ' offline'); }
    if (statusText) { statusText.textContent = label; }
}

/* ================================================================
   SPEECH RECOGNITION
   ================================================================ */
function isSafariOrIOS() {
    if (typeof navigator === 'undefined') return false;
    const ua = navigator.userAgent || '';
    return /iPad|iPhone|iPod/.test(ua) ||
        (navigator.vendor && navigator.vendor.indexOf('Apple') > -1) ||
        (/Safari/.test(ua) && !/Chrome|Chromium|CriOS/.test(ua));
}

function initSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { if (micBtn) micBtn.title = 'Speech not supported in this browser'; return; }

    recognition = new SR();
    recognition.continuous        = false;
    recognition.interimResults    = !isSafariOrIOS();
    recognition.maxAlternatives   = 1;
    recognition.lang              = settings.speechInputLanguage || 'en-US';

    recognition.onresult = e => {
        if (!e.results || e.results.length === 0) return;
        const last       = e.results[e.results.length - 1];
        const transcript = (last && last[0]) ? last[0].transcript.trim() : '';
        const isFinal    = last && last.isFinal;

        if (speechWidgetText) speechWidgetText.textContent = transcript;
        if (speechWidget)     speechWidget.classList.add('visible');

        if (isFinal && transcript) {
            pendingSendTranscript = transcript;
            clearTimeout(speechSendTimeout);
            speechSendTimeout = setTimeout(() => {
                if (pendingSendTranscript) {
                    sendMessage(pendingSendTranscript);
                    pendingSendTranscript = null;
                }
                speechSendTimeout = null;
                stopListening();
            }, SPEECH_SEND_DELAY_MS);
        } else if (!isFinal) {
            pendingSendTranscript = null;
            clearTimeout(speechSendTimeout);
            speechSendTimeout = null;
        }
    };

    recognition.onstart = () => { speechErrorRetryCount = 0; };

    recognition.onerror = e => {
        stopListening();
        const msg = (e && e.error) ? String(e.error) : '';
        const denied = /denied|not-allowed|permission/i.test(msg);
        if (denied && micBtn) {
            micBtn.title = 'Microphone access denied. Allow in browser settings.';
            speechErrorRetryCount = SPEECH_ERROR_MAX_RETRIES;
        }
        if (autoListenMode && !isStreaming && speechErrorRetryCount < SPEECH_ERROR_MAX_RETRIES) {
            speechErrorRetryCount++;
            setTimeout(() => maybeRestartListening(), SPEECH_RESTART_DELAY_MS);
        }
    };

    recognition.onend = () => {
        if (pendingSendTranscript) {
            clearTimeout(speechSendTimeout);
            speechSendTimeout = null;
            sendMessage(pendingSendTranscript);
            pendingSendTranscript = null;
        } else {
            clearTimeout(speechSendTimeout);
            speechSendTimeout = null;
        }
        if (isListening) stopListening();
        maybeRestartListening();
    };
}

function startListening() {
    if (!recognition || isStreaming || isListening) return;
    if (isSafariOrIOS() && !safariVoiceHintShown) {
        showToast('Voice works best in Chrome. Safari has limited support.', 4000);
        safariVoiceHintShown = true;
    }
    isListening           = true;
    pendingSendTranscript = null;
    clearTimeout(speechSendTimeout);
    speechSendTimeout = null;
    if (micBtn)            micBtn.classList.add('listening');
    if (speechWidget)      speechWidget.classList.add('visible');
    if (speechWidgetText)  speechWidgetText.textContent = '';
    try { recognition.start(); } catch (err) {
        isListening = false;
        if (micBtn)       micBtn.classList.remove('listening');
        if (speechWidget) speechWidget.classList.remove('visible');
    }
}

function stopListening() {
    clearTimeout(speechSendTimeout);
    speechSendTimeout     = null;
    pendingSendTranscript = null;
    isListening           = false;
    if (micBtn)           micBtn.classList.remove('listening');
    if (speechWidget)     speechWidget.classList.remove('visible');
    if (speechWidgetText) speechWidgetText.textContent = '';
    try { recognition.stop(); } catch (_) {}
}

function maybeRestartListening() {
    if (!autoListenMode || !recognition) return;
    if (isStreaming) return;
    if (ttsPlayer && (ttsPlayer.playing || ttsPlayer.queue.length > 0)) return;
    setTimeout(() => {
        if (autoListenMode && !isStreaming && !isListening && recognition) startListening();
    }, SPEECH_RESTART_DELAY_MS);
}

/* ================================================================
   SEND MESSAGE — Core SSE streaming logic
   ================================================================ */
async function sendMessage(text) {
    const msg = (text || messageInput.value).trim();
    if (!msg || isStreaming) return;

    // Validate length
    if (msg.length > 32000) { showToast('Message too long. Max 32,000 characters.'); return; }

    // Unlock TTS (must happen during user gesture)
    if (ttsPlayer) ttsPlayer.unlock();
    if (ttsPlayer) ttsPlayer.reset();

    // Update UI state
    isStreaming = true;
    if (messageInput) { messageInput.value = ''; messageInput.style.height = 'auto'; }
    if (sendBtn)      sendBtn.disabled = true;
    if (charCount)    charCount.textContent = '';

    // Hide welcome screen
    const welcomeScreen = document.getElementById('welcome-screen');
    if (welcomeScreen) welcomeScreen.style.display = 'none';

    // Append user message
    appendMessage('user', msg);

    // Create assistant message bubble with cursor
    const assistantEl   = appendMessage('assistant', '');
    const contentEl     = assistantEl.querySelector('.msg-content');
    const cursorEl      = document.createElement('span');
    cursorEl.className  = 'stream-cursor';
    cursorEl.textContent= '▋';
    if (contentEl) contentEl.appendChild(cursorEl);

    // Clear activity list for new message
    if (activityList) activityList.innerHTML = '';

    // Auto-open activity panel
    if (settings.autoOpenActivity) openActivityPanel();

    let fullResponse = '';

    try {
        const endpoint  = getEndpoint(currentMode);
        const body      = JSON.stringify({
            message: msg,
            session_id: sessionId,
            mode: currentMode,
            tts_voice: settings.speechOutputVoice,
        });

        const response  = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body,
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader    = response.body.getReader();
        const decoder   = new TextDecoder();
        let   buffer    = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer      = lines.pop() ?? '';   // Keep incomplete line in buffer

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const raw = line.slice(6).trim();
                if (!raw) continue;

                let data;
                try { data = JSON.parse(raw); } catch { continue; }

                if (data.type === 'token') {
                    // Stream text token into bubble
                    fullResponse += data.content;
                    if (contentEl) {
                        contentEl.textContent = fullResponse;
                        contentEl.appendChild(cursorEl);
                    }
                    scrollToBottom();

                } else if (data.type === 'audio') {
                    // Enqueue TTS audio chunk
                    if (ttsPlayer && ttsPlayer.enabled) {
                        ttsPlayer.enqueue(data.data);
                    }

                } else if (data.type === 'activity') {
                    // Add activity item to panel
                    addActivityItem(data.event, data.detail);

                } else if (data.type === 'search_results') {
                    // Populate search results panel
                    populateSearchResults(data);
                    if (settings.autoOpenSearchResults) openSearchPanel();

                } else if (data.type === 'image') {
                    // Append an image message bubble
                    appendImageMessage(data.path);

                } else if (data.type === 'approval_required') {
                    appendApprovalRequest(data.approval);

                } else if (data.type === 'done') {
                    // Stream complete
                    if (data.session_id) sessionId = data.session_id;
                }
            }
        }

    } catch (e) {
        console.error('Stream error:', e);
        const errMsg = 'Connection error. Please check the server is running.';
        fullResponse = errMsg;
        if (contentEl) contentEl.textContent = errMsg;
        showToast('Server connection failed. Is the backend running?', 5000);
        setStatus(false, 'Offline');
    } finally {
        // Remove cursor
        if (cursorEl.parentNode) cursorEl.parentNode.removeChild(cursorEl);
        // Final text
        if (contentEl && fullResponse) contentEl.textContent = fullResponse;

        isStreaming = false;
        if (sendBtn) sendBtn.disabled = false;
        if (messageInput) messageInput.focus();
        scrollToBottom();

        // Check health after response
        checkHealth();

        // Auto-restart voice if in auto-listen mode
        if (ttsPlayer && ttsPlayer.queue.length === 0 && !ttsPlayer.playing) {
            maybeRestartListening();
        }
    }
}

/* ================================================================
   MESSAGE BUBBLES
   ================================================================ */
function appendMessage(role, text) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `
        <div class="msg-avatar">${role === 'assistant' ? 'AI' : 'YOU'}</div>
        <div class="msg-body">
            <div class="msg-label">${role === 'assistant' ? 'J.A.R.V.I.S' : 'You'}</div>
            <div class="msg-content">${escapeHtml(text)}</div>
        </div>`;
    if (chatMessages) chatMessages.appendChild(div);
    scrollToBottom();
    return div;
}

function appendImageMessage(path) {
    const div = document.createElement('div');
    div.className = 'message assistant image-message';
    div.innerHTML = `
        <div class="msg-avatar">AI</div>
        <div class="msg-body">
            <div class="msg-label">J.A.R.V.I.S — Generated Asset</div>
            <div class="msg-content">
                <div class="image-container">
                    <img src="${path}" alt="Generated Image" class="generated-image" onload="this.classList.add('loaded')" onclick="window.open(this.src)">
                    <div class="image-overlay">Click to expand</div>
                </div>
            </div>
        </div>`;
    if (chatMessages) chatMessages.appendChild(div);
    scrollToBottom();
}

function appendApprovalRequest(approval, force = false) {
    if (!approval || typeof approval.id !== 'string' || typeof approval.description !== 'string') {
        showToast('Received an invalid action approval request.');
        return;
    }
    if (!force && pendingApprovals.has(approval.id)) return;

    pendingApprovals.set(approval.id, approval);
    const message = appendMessage('assistant', approval.description);
    message.dataset.approvalId = approval.id;
    const content = message.querySelector('.msg-content');
    const details = document.createElement('p');
    details.className = 'approval-details';
    details.textContent = approval.details || 'Review this local action before it is performed.';
    content.appendChild(details);

    const controls = document.createElement('div');
    controls.className = 'approval-controls';
    const approveButton = document.createElement('button');
    approveButton.className = 'approval-button approve';
    approveButton.textContent = 'Approve';
    const denyButton = document.createElement('button');
    denyButton.className = 'approval-button deny';
    denyButton.textContent = 'Deny';
    const result = document.createElement('p');
    result.className = 'approval-result';

    const submitDecision = async decision => {
        approveButton.disabled = true;
        denyButton.disabled = true;
        result.textContent = decision === 'approve' ? 'Approving...' : 'Denying...';
        try {
            const response = await fetch(`${API}/actions/${encodeURIComponent(approval.id)}/${decision}`, {
                method: 'POST',
            });
            const data = await response.json();
            if (!response.ok) {
                const error = new Error(data.detail || `Action request failed (${response.status}).`);
                error.status = response.status;
                throw error;
            }
            pendingApprovals.delete(approval.id);
            if (data.image) appendImageMessage(data.image);
            result.textContent = decision === 'approve'
                ? `Completed: ${data.result}`
                : data.result;
        } catch (error) {
            result.textContent = error.message || 'Could not resolve this approval.';
            if (error.status === 404 || error.status === 410) {
                pendingApprovals.delete(approval.id);
            } else {
                approveButton.disabled = false;
                denyButton.disabled = false;
            }
        }
    };

    approveButton.addEventListener('click', () => submitDecision('approve'));
    denyButton.addEventListener('click', () => submitDecision('deny'));
    controls.append(approveButton, denyButton);
    content.append(controls, result);
    scrollToBottom();
}

async function loadPendingApprovals() {
    try {
        const response = await fetch(`${API}/actions/pending`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `Pending approval request failed (${response.status}).`);
        if (!Array.isArray(data.approvals)) throw new Error('Pending approval response was invalid.');
        if (data.approvals.length > 0) {
            const welcomeScreen = $('welcome-screen');
            if (welcomeScreen) welcomeScreen.style.display = 'none';
            data.approvals.forEach(appendApprovalRequest);
        }
    } catch (error) {
        console.error('Could not restore pending approvals:', error);
    }
}

async function loadActionAudit() {
    const auditLog = $('action-audit-log');
    const auditButton = $('action-audit-refresh');
    if (!auditLog || !auditButton) return;

    auditButton.disabled = true;
    auditLog.textContent = 'Loading audit history...';
    try {
        const response = await fetch(`${API}/actions/audit?limit=100`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `Audit request failed (${response.status}).`);
        if (!Array.isArray(data.events) || data.events.length === 0) {
            auditLog.textContent = 'No approval events recorded yet.';
            return;
        }
        auditLog.textContent = data.events.map(event => {
            const time = new Date(event.timestamp).toLocaleString();
            return `${time} · ${event.action_type.replaceAll('_', ' ')} · ${event.event}`;
        }).join('\n');
    } catch (error) {
        auditLog.textContent = error.message || 'Could not load the audit history.';
    } finally {
        auditButton.disabled = false;
    }
}

function escapeHtml(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function scrollToBottom() {
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
}

/* ================================================================
   ACTIVITY PANEL
   ================================================================ */
function addActivityItem(event, detail) {
    if (!activityList) return;
    // Remove placeholder text
    const placeholder = activityList.querySelector('[style]');
    if (placeholder) placeholder.remove();

    const item = document.createElement('div');
    item.className = 'activity-item';
    item.innerHTML = `
        <div class="activity-event">
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="6"/></svg>
            ${escapeHtml(event || '')}
        </div>
        <div class="activity-detail">${escapeHtml(detail || '')}</div>`;
    activityList.appendChild(item);
    activityList.scrollTop = activityList.scrollHeight;
}

function openActivityPanel() {
    if (activityPanel) activityPanel.classList.add('open');
    if (panelOverlay)  panelOverlay.classList.add('visible');
}

function closeActivityPanel() {
    if (activityPanel) activityPanel.classList.remove('open');
    checkPanelOverlay();
}

function openSearchPanel() {
    if (searchResultsWidget) searchResultsWidget.classList.add('open');
    if (panelOverlay)        panelOverlay.classList.add('visible');
}

function closeSearchPanel() {
    if (searchResultsWidget) searchResultsWidget.classList.remove('open');
    checkPanelOverlay();
}

function checkPanelOverlay() {
    const anyOpen = (activityPanel && activityPanel.classList.contains('open')) ||
                    (searchResultsWidget && searchResultsWidget.classList.contains('open'));
    if (!anyOpen && panelOverlay) panelOverlay.classList.remove('visible');
}

/* ================================================================
   SEARCH RESULTS PANEL
   ================================================================ */
function populateSearchResults(data) {
    if (!searchResultsBody) return;
    searchResultsBody.innerHTML = '';

    if (data.query) {
        const qDiv = document.createElement('div');
        qDiv.innerHTML = `<div class="search-query-label">QUERY</div><div class="search-query-text">${escapeHtml(data.query)}</div>`;
        searchResultsBody.appendChild(qDiv);
    }

    if (data.answer) {
        const aDiv = document.createElement('div');
        aDiv.className = 'search-ai-answer';
        aDiv.textContent = data.answer;
        searchResultsBody.appendChild(aDiv);
    }

    if (data.results && data.results.length > 0) {
        data.results.forEach(r => {
            const a = document.createElement('a');
            a.className   = 'search-result-card';
            a.href        = r.url || '#';
            a.target      = '_blank';
            a.rel         = 'noopener noreferrer';
            a.innerHTML   = `
                <div class="search-result-title">${escapeHtml(r.title || 'Result')}</div>
                <div class="search-result-url">${escapeHtml(r.url || '')}</div>
                <div class="search-result-snippet">${escapeHtml(r.content || '')}</div>`;
            searchResultsBody.appendChild(a);
        });
    }
}

/* ================================================================
   NEW CHAT
   ================================================================ */
function startNewChat() {
    sessionId = null;
    if (ttsPlayer) ttsPlayer.stop();
    stopListening();
    autoListenMode = false;
    if (micBtn) micBtn.classList.remove('auto-listen');
    if (chatMessages) {
        chatMessages.innerHTML = '';
        // Re-add welcome screen
        const ws = document.createElement('div');
        ws.className = 'welcome-screen';
        ws.id        = 'welcome-screen';
        ws.innerHTML = `
            <div class="welcome-icon">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor" opacity="0.6"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z"/></svg>
            </div>
            <h1 class="welcome-title" id="welcome-title">Good morning.</h1>
            <p class="welcome-sub">How may I assist you today?</p>
            <div class="welcome-chips">
                <button class="chip" data-message="What can you do?">What can you do?</button>
                <button class="chip" data-message="What's the latest news today?">Latest news</button>
                <button class="chip" data-message="Tell me a joke">Tell me a joke</button>
                <button class="chip" data-message="Who is Elon Musk?">Who is Elon Musk?</button>
                <button class="chip" data-message="What's the weather like today?">Weather today</button>
            </div>`;
        chatMessages.appendChild(ws);
        bindChips();
        setGreeting();
    }
    if (activityList) activityList.innerHTML = '<div style="color:var(--text-muted);font-size:0.78rem;text-align:center;padding:20px;">Activity will appear here when you send a message.</div>';
    if (searchResultsBody) searchResultsBody.innerHTML = '<div style="color:var(--text-muted);font-size:0.78rem;text-align:center;padding:20px;">Switch to Realtime mode and ask about current events.</div>';
    closeActivityPanel();
    closeSearchPanel();
    if (messageInput) messageInput.focus();
    if (pendingApprovals.size > 0) {
        const welcomeScreen = $('welcome-screen');
        if (welcomeScreen) welcomeScreen.style.display = 'none';
        pendingApprovals.forEach(approval => appendApprovalRequest(approval, true));
    }
}

/* ================================================================
   TOAST NOTIFICATIONS
   ================================================================ */
function showToast(message, duration = 4000) {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className   = 'toast';
    toast.textContent = message;
    toastContainer.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('toast-visible'));
    const dismiss = () => {
        toast.classList.remove('toast-visible');
        setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 350);
    };
    setTimeout(dismiss, duration);
    toast.addEventListener('click', dismiss);
}

/* ================================================================
   INPUT AUTO-RESIZE
   ================================================================ */
function autoResizeInput() {
    if (!messageInput) return;
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
}

async function openVisionDialog(visionBtn) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showToast('Camera capture is not supported in this browser.');
        return;
    }
    if (!window.isSecureContext) {
        showToast('Camera access requires localhost or a secure HTTPS connection.');
        return;
    }

    const dialog = document.createElement('dialog');
    dialog.className = 'vision-dialog';
    dialog.innerHTML = `
        <h2>Analyze an image</h2>
        <p>Start the camera or choose an image. Nothing is sent until you review the preview and choose Analyze.</p>
        <video class="vision-preview" autoplay playsinline muted hidden></video>
        <img class="vision-preview" alt="Selected image preview" hidden>
        <p class="vision-status" aria-live="polite">Camera is off.</p>
        <div class="vision-controls">
            <button type="button" class="approval-button camera-toggle">Start camera</button>
            <button type="button" class="approval-button capture-frame" disabled>Capture frame</button>
            <button type="button" class="approval-button choose-image">Choose image</button>
            <button type="button" class="approval-button approve analyze-image" disabled>Analyze</button>
            <button type="button" class="approval-button deny close-vision">Close</button>
        </div>`;
    document.body.appendChild(dialog);

    const video = dialog.querySelector('video');
    const imagePreview = dialog.querySelector('img');
    const status = dialog.querySelector('.vision-status');
    const cameraButton = dialog.querySelector('.camera-toggle');
    const captureButton = dialog.querySelector('.capture-frame');
    const uploadButton = dialog.querySelector('.choose-image');
    const analyzeButton = dialog.querySelector('.analyze-image');
    const closeButton = dialog.querySelector('.close-vision');
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/png,image/jpeg,image/webp';
    fileInput.hidden = true;
    document.body.appendChild(fileInput);

    let cameraStream = null;
    let selectedImage = null;
    let imageUrl = null;
    let imageName = '';
    let isAnalyzing = false;

    const stopCamera = () => {
        if (cameraStream) {
            cameraStream.getTracks().forEach(track => track.stop());
            cameraStream = null;
        }
        video.srcObject = null;
        video.hidden = true;
        captureButton.disabled = true;
        cameraButton.textContent = 'Start camera';
    };
    const clearPreview = () => {
        selectedImage = null;
        imageName = '';
        analyzeButton.disabled = true;
        imagePreview.hidden = true;
        imagePreview.removeAttribute('src');
        if (imageUrl) {
            URL.revokeObjectURL(imageUrl);
            imageUrl = null;
        }
    };
    const showPreview = (blob, name) => {
        if (!blob || blob.size > 8 * 1024 * 1024) {
            clearPreview();
            status.textContent = 'Images must be valid and 8 MB or smaller.';
            return;
        }
        clearPreview();
        stopCamera();
        selectedImage = blob;
        imageName = name;
        imageUrl = URL.createObjectURL(blob);
        imagePreview.src = imageUrl;
        imagePreview.hidden = false;
        analyzeButton.disabled = false;
        status.textContent = 'Review the preview. It will only be sent after you choose Analyze.';
    };
    const closeDialog = () => {
        stopCamera();
        clearPreview();
        if (dialog.open) dialog.close();
        dialog.remove();
        fileInput.remove();
        visionBtn.disabled = false;
    };

    cameraButton.addEventListener('click', async () => {
        if (cameraStream) {
            stopCamera();
            status.textContent = 'Camera stopped.';
            return;
        }
        cameraButton.disabled = true;
        status.textContent = 'Requesting camera permission...';
        try {
            cameraStream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: { facingMode: 'environment' },
            });
            video.srcObject = cameraStream;
            video.hidden = false;
            imagePreview.hidden = true;
            captureButton.disabled = false;
            cameraButton.textContent = 'Stop camera';
            status.textContent = 'Camera is active. Capture a single frame when ready.';
        } catch (error) {
            stopCamera();
            status.textContent = error.name === 'NotAllowedError'
                ? 'Camera permission was denied. You can still choose an image.'
                : 'Could not start the camera. You can still choose an image.';
        } finally {
            cameraButton.disabled = false;
        }
    });

    captureButton.addEventListener('click', () => {
        if (!cameraStream || !video.videoWidth || !video.videoHeight) {
            status.textContent = 'The camera frame is not ready yet.';
            return;
        }
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d');
        if (!context) {
            status.textContent = 'Could not capture the camera frame.';
            return;
        }
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(blob => {
            if (!blob) {
                status.textContent = 'Could not encode the captured frame.';
                return;
            }
            showPreview(blob, 'Camera snapshot');
        }, 'image/jpeg', 0.88);
    });

    uploadButton.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
        const file = fileInput.files && fileInput.files[0];
        if (file) showPreview(file, file.name);
        fileInput.value = '';
    });

    analyzeButton.addEventListener('click', async () => {
        if (!selectedImage || isAnalyzing) return;
        const isCameraFrame = imageName === 'Camera snapshot';
        const consentMessage = isCameraFrame
            ? 'Send this camera snapshot to the configured OpenAI model for analysis? J.A.R.V.I.S processes this frame for the request and does not save it.'
            : 'Send this image to the configured OpenAI model for analysis? J.A.R.V.I.S processes it for the request and does not save it.';
        if (!window.confirm(consentMessage)) return;

        isAnalyzing = true;
        analyzeButton.disabled = true;
        cameraButton.disabled = true;
        uploadButton.disabled = true;
        status.textContent = 'Analyzing image...';
        const formData = new FormData();
        formData.append(
            'file',
            selectedImage,
            isCameraFrame ? 'camera-snapshot.jpg' : imageName,
        );
        try {
            const response = await fetch(`${API}/vision/analyze`, {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || `Image analysis failed (${response.status}).`);

            const userMessage = appendMessage('user', imageName);
            const preview = document.createElement('img');
            preview.src = imageUrl;
            preview.alt = 'Image sent for analysis';
            preview.className = 'vision-message-image';
            userMessage.querySelector('.msg-content').appendChild(preview);
            imageUrl = null;
            appendMessage('assistant', data.analysis);
            closeDialog();
        } catch (error) {
            status.textContent = error.message || 'Image analysis failed.';
            analyzeButton.disabled = false;
            cameraButton.disabled = false;
            uploadButton.disabled = false;
        } finally {
            isAnalyzing = false;
        }
    });

    closeButton.addEventListener('click', closeDialog);
    dialog.addEventListener('cancel', closeDialog);
    dialog.addEventListener('close', () => {
        stopCamera();
        clearPreview();
        fileInput.remove();
        visionBtn.disabled = false;
    }, { once: true });
    dialog.showModal();
}

/* ================================================================
   BIND EVENTS
   ================================================================ */
function bindEvents() {

    if (speechInputLanguage) {
        speechInputLanguage.addEventListener('change', () => {
            settings.speechInputLanguage = speechInputLanguage.value;
            if (recognition && !isListening) recognition.lang = settings.speechInputLanguage;
            saveSettings();
        });
    }
    if (speechOutputVoice) {
        speechOutputVoice.addEventListener('change', () => {
            settings.speechOutputVoice = speechOutputVoice.value;
            saveSettings();
        });
    }
    const auditButton = $('action-audit-refresh');
    if (auditButton) auditButton.addEventListener('click', loadActionAudit);

    /* Send button */
    if (sendBtn) sendBtn.addEventListener('click', () => sendMessage());

    /* Enter key (Shift+Enter = newline) */
    if (messageInput) {
        messageInput.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
        });
        messageInput.addEventListener('input', () => {
            autoResizeInput();
            // Character count warning
            if (charCount) {
                const len = messageInput.value.length;
                charCount.textContent = len > 500 ? `${len} / 32000` : '';
            }
        });
    }

    /* Mic button */
    if (micBtn) {
        micBtn.addEventListener('click', () => {
            if (!recognition) { showToast('Voice input not supported in this browser. Use Chrome or Edge.'); return; }
            if (isListening) {
                stopListening();
                autoListenMode = false;
                micBtn.classList.remove('auto-listen');
            } else {
                if (ttsPlayer) ttsPlayer.unlock();
                startListening();
                // If clicked while not streaming, enable auto-listen mode
                autoListenMode = true;
                micBtn.classList.add('auto-listen');
            }
        });
    }

    /* TTS button */
    if (ttsBtn) {
        ttsBtn.addEventListener('click', () => {
            if (!ttsPlayer) return;
            if (ttsPlayer) ttsPlayer.unlock();
            ttsPlayer.enabled = !ttsPlayer.enabled;
            settings.ttsEnabled = ttsPlayer.enabled;
            saveSettings();
            ttsBtn.classList.toggle('tts-active', ttsPlayer.enabled);
            if (!ttsPlayer.enabled) ttsPlayer.stop();
            if (toggleThinkingSounds) syncToggle(toggleThinkingSounds, ttsPlayer.enabled);
            showToast(ttsPlayer.enabled ? 'Voice output enabled.' : 'Voice output disabled.');
        });
    }

    /* Vision Button */
    const visionBtn = $('vision-btn');
    if (visionBtn) {
        visionBtn.addEventListener('click', () => {
            visionBtn.disabled = true;
            openVisionDialog(visionBtn).catch(error => {
                console.error('Could not open image analysis:', error);
                visionBtn.disabled = false;
                showToast('Could not open image analysis.');
            });
        });
    }

    /* New chat button */
    if (newChatBtn) newChatBtn.addEventListener('click', startNewChat);

    /* Mode buttons */
    if (btnJarvis)   btnJarvis.addEventListener('click',   () => setMode('jarvis'));
    if (btnGeneral)  btnGeneral.addEventListener('click',  () => setMode('general'));
    if (btnRealtime) btnRealtime.addEventListener('click', () => setMode('realtime'));

    /* Activity panel */
    if (activityToggle) activityToggle.addEventListener('click', () => {
        activityPanel && activityPanel.classList.contains('open') ? closeActivityPanel() : openActivityPanel();
    });
    if (activityClose)  activityClose.addEventListener('click',  closeActivityPanel);

    /* Search panel */
    if (searchResultsToggle) searchResultsToggle.addEventListener('click', () => {
        searchResultsWidget && searchResultsWidget.classList.contains('open') ? closeSearchPanel() : openSearchPanel();
    });
    if (searchResultsClose)  searchResultsClose.addEventListener('click',  closeSearchPanel);

    /* Panel overlay — clicking it closes panels */
    if (panelOverlay) panelOverlay.addEventListener('click', () => {
        closeActivityPanel();
        closeSearchPanel();
    });

    /* Settings */
    if (settingsBtn)     settingsBtn.addEventListener('click',     () => { settingsPanel.classList.add('open'); settingsOverlay.classList.add('open'); });
    if (settingsClose)   settingsClose.addEventListener('click',   () => { settingsPanel.classList.remove('open'); settingsOverlay.classList.remove('open'); });
    if (settingsOverlay) settingsOverlay.addEventListener('click', () => { settingsPanel.classList.remove('open'); settingsOverlay.classList.remove('open'); });

    /* Settings toggles */
    if (toggleAutoActivity) {
        toggleAutoActivity.addEventListener('click', () => {
            settings.autoOpenActivity = !settings.autoOpenActivity;
            syncToggle(toggleAutoActivity, settings.autoOpenActivity);
            saveSettings();
        });
    }
    if (toggleAutoSearch) {
        toggleAutoSearch.addEventListener('click', () => {
            settings.autoOpenSearchResults = !settings.autoOpenSearchResults;
            syncToggle(toggleAutoSearch, settings.autoOpenSearchResults);
            saveSettings();
        });
    }
    if (toggleThinkingSounds) {
        toggleThinkingSounds.addEventListener('click', () => {
            settings.ttsEnabled = !settings.ttsEnabled;
            if (ttsPlayer) ttsPlayer.enabled = settings.ttsEnabled;
            syncToggle(toggleThinkingSounds, settings.ttsEnabled);
            if (ttsBtn) ttsBtn.classList.toggle('tts-active', settings.ttsEnabled);
            if (!settings.ttsEnabled && ttsPlayer) ttsPlayer.stop();
            saveSettings();
        });
    }

    /* Chip buttons */
    bindChips();

    /* Keyboard shortcut: Ctrl+/ or Cmd+/ for new chat */
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key === '/') { e.preventDefault(); startNewChat(); }
    });
}

function bindChips() {
    document.querySelectorAll('.chip[data-message]').forEach(chip => {
        chip.addEventListener('click', () => sendMessage(chip.dataset.message));
    });
}

/* ================================================================
   BOOT
   ================================================================ */
document.addEventListener('DOMContentLoaded', bootSequence);
