(() => {
    'use strict';

    const API = window.location.origin;
    const $ = id => document.getElementById(id);
    const ui = {
        status: $('status'),
        toggle: $('voice-toggle'),
        inputLanguage: $('input-language'),
        outputVoice: $('output-voice'),
        mode: $('chat-mode'),
        messages: $('messages'),
        empty: $('empty-state'),
        form: $('message-form'),
        message: $('message'),
        send: $('send'),
        orb: $('orb'),
    };
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const state = {
        active: false,
        listening: false,
        busy: false,
        sessionId: localStorage.getItem('jarvis_voice_agent_session') || null,
        recognition: null,
        audio: new Audio(),
        audioQueue: [],
        playing: false,
        audioGeneration: 0,
        playbackResolve: null,
        restartTimer: null,
    };

    function setStatus(message, isError = false) {
        ui.status.textContent = message;
        ui.status.classList.toggle('error', isError);
    }

    function addBubble(role, text) {
        ui.empty.hidden = true;
        const bubble = document.createElement('article');
        bubble.className = `bubble ${role}`;
        const label = document.createElement('span');
        label.className = 'bubble-label';
        label.textContent = role === 'user' ? 'You' : 'J.A.R.V.I.S';
        const content = document.createElement('div');
        content.textContent = text;
        bubble.append(label, content);
        ui.messages.appendChild(bubble);
        ui.messages.scrollTop = ui.messages.scrollHeight;
        return { bubble, content };
    }

    function scheduleListening() {
        clearTimeout(state.restartTimer);
        if (!state.active || state.busy || state.listening || state.playing || state.audioQueue.length) return;
        state.restartTimer = setTimeout(startListening, 650);
    }

    function stopVoiceMode() {
        state.active = false;
        state.listening = false;
        clearTimeout(state.restartTimer);
        if (state.recognition) {
            try { state.recognition.abort(); } catch (error) { console.debug('Speech recognition already stopped.', error); }
        }
        stopPlayback();
        ui.toggle.textContent = 'Start voice mode';
        ui.toggle.setAttribute('aria-pressed', 'false');
        ui.orb.classList.remove('active');
        setStatus('Voice mode is off.');
    }

    function stopPlayback() {
        state.audioGeneration++;
        if (state.playbackResolve) state.playbackResolve();
        state.audio.pause();
        state.audio.removeAttribute('src');
        state.audio.load();
        state.audioQueue = [];
        state.playing = false;
    }

    function startListening() {
        if (!state.active || state.busy || state.listening || !state.recognition) return;
        state.recognition.lang = ui.inputLanguage.value || 'en-US';
        try {
            state.recognition.start();
        } catch (error) {
            if (error.name !== 'InvalidStateError') {
                setStatus('Could not start microphone recognition. Check browser permissions.', true);
            }
        }
    }

    function initRecognition() {
        if (!Recognition) {
            ui.toggle.disabled = true;
            setStatus('Speech recognition is unavailable in this browser. You can still type messages.', true);
            return;
        }
        const recognition = new Recognition();
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.onstart = () => {
            state.listening = true;
            ui.orb.classList.add('active');
            setStatus('Listening… speak now.');
        };
        recognition.onresult = event => {
            let transcript = '';
            let final = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const text = event.results[i][0].transcript;
                transcript += text;
                if (event.results[i].isFinal) final += text;
            }
            if (transcript) setStatus(`Heard: ${transcript}`);
            if (final.trim()) sendMessage(final.trim());
        };
        recognition.onerror = event => {
            state.listening = false;
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                setStatus('Microphone access was denied. Allow it in your browser, then start voice mode again.', true);
                stopVoiceMode();
            } else if (event.error !== 'no-speech' && event.error !== 'aborted') {
                setStatus(`Speech recognition error: ${event.error}. You can still type.`, true);
            }
        };
        recognition.onend = () => {
            state.listening = false;
            if (state.active && !state.busy && !state.playing) scheduleListening();
        };
        state.recognition = recognition;
    }

    async function playNextAudio() {
        if (state.playing || !state.audioQueue.length) {
            if (!state.playing) scheduleListening();
            return;
        }
        const generation = state.audioGeneration;
        state.playing = true;
        ui.orb.classList.add('active');
        while (state.audioQueue.length && generation === state.audioGeneration) {
            const audio = state.audioQueue.shift();
            await new Promise(resolve => {
                let settled = false;
                const finish = () => {
                    if (settled) return;
                    settled = true;
                    if (state.playbackResolve === finish) state.playbackResolve = null;
                    resolve();
                };
                state.playbackResolve = finish;
                state.audio.onended = finish;
                state.audio.onerror = finish;
                state.audio.src = `data:audio/mp3;base64,${audio}`;
                state.audio.play().catch(() => {
                    setStatus('Could not play the spoken reply. Check your browser audio settings.', true);
                    finish();
                });
            });
        }
        if (generation !== state.audioGeneration) return;
        state.playing = false;
        ui.orb.classList.remove('active');
        scheduleListening();
    }

    function appendApproval(approval, target) {
        const panel = document.createElement('div');
        panel.className = 'approval';
        const details = document.createElement('p');
        details.textContent = approval.details || 'Review this action before it is performed.';
        const result = document.createElement('p');
        const approve = document.createElement('button');
        approve.textContent = 'Approve';
        const deny = document.createElement('button');
        deny.textContent = 'Deny';
        deny.className = 'deny';

        async function decide(choice) {
            approve.disabled = true;
            deny.disabled = true;
            result.textContent = choice === 'approve' ? 'Approving…' : 'Denying…';
            try {
                const response = await fetch(`${API}/actions/${encodeURIComponent(approval.id)}/${choice}`, { method: 'POST' });
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || `Action failed (${response.status}).`);
                result.textContent = choice === 'approve' ? `Completed: ${data.result}` : data.result;
            } catch (error) {
                result.textContent = error.message || 'Could not resolve this approval.';
                approve.disabled = false;
                deny.disabled = false;
            }
        }
        approve.addEventListener('click', () => decide('approve'));
        deny.addEventListener('click', () => decide('deny'));
        panel.append(details, approve, deny, result);
        target.appendChild(panel);
    }

    async function sendMessage(message) {
        const text = (message || ui.message.value).trim();
        if (!text || state.busy) return;
        state.busy = true;
        clearTimeout(state.restartTimer);
        if (state.listening && state.recognition) {
            state.listening = false;
            try { state.recognition.abort(); } catch (error) { console.debug('Speech recognition already stopped.', error); }
        }
        if (state.playing || state.audioQueue.length) stopPlayback();
        ui.message.value = '';
        ui.send.disabled = true;
        addBubble('user', text);
        const reply = addBubble('assistant', '');
        let responseText = '';
        setStatus('Thinking…');

        try {
            const endpoint = ui.mode.value === 'general'
                ? '/chat/stream'
                : ui.mode.value === 'realtime'
                    ? '/chat/realtime/stream'
                    : '/chat/jarvis/stream';
            const response = await fetch(`${API}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    session_id: state.sessionId,
                    mode: ui.mode.value,
                    tts_voice: ui.outputVoice.value,
                }),
            });
            if (!response.ok) throw new Error(`Assistant request failed (${response.status}).`);
            if (!response.body) throw new Error('The server did not provide a response stream.');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const handleLine = line => {
                if (!line.startsWith('data: ')) return;
                let data;
                try { data = JSON.parse(line.slice(6)); } catch (error) {
                    console.warn('Ignoring malformed assistant event.', error);
                    return;
                }
                if (data.type === 'token') {
                    responseText += data.content || '';
                    reply.content.textContent = responseText;
                } else if (data.type === 'audio' && typeof data.data === 'string') {
                    state.audioQueue.push(data.data);
                    playNextAudio();
                } else if (data.type === 'approval_required' && data.approval) {
                    appendApproval(data.approval, reply.bubble);
                } else if (data.type === 'done' && data.session_id) {
                    state.sessionId = data.session_id;
                    localStorage.setItem('jarvis_voice_agent_session', data.session_id);
                }
                ui.messages.scrollTop = ui.messages.scrollHeight;
            };
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                lines.forEach(handleLine);
            }
            if (buffer.trim()) handleLine(buffer);
            if (!responseText && !reply.bubble.querySelector('.approval')) {
                reply.content.textContent = 'The assistant returned an empty response.';
            }
        } catch (error) {
            console.error('Voice agent request failed:', error);
            reply.content.textContent = error.message || 'The assistant request failed.';
            setStatus(error.message || 'The assistant request failed.', true);
        } finally {
            state.busy = false;
            ui.send.disabled = false;
            if (!ui.status.classList.contains('error')) {
                setStatus(state.active ? 'Reply complete.' : 'Ready. Voice mode is off.');
            }
            scheduleListening();
        }
    }

    async function loadSpeechOptions() {
        const response = await fetch(`${API}/speech/voices`);
        if (!response.ok) throw new Error(`Voice settings unavailable (${response.status}).`);
        const data = await response.json();
        Object.entries(data.input_languages || {}).forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            ui.inputLanguage.appendChild(option);
        });
        Object.entries(data.output_voices || {}).forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            ui.outputVoice.appendChild(option);
        });
        ui.outputVoice.value = data.default_voice || ui.outputVoice.options[0]?.value || '';
    }

    ui.toggle.addEventListener('click', () => {
        if (state.active) {
            stopVoiceMode();
            return;
        }
        if (!state.recognition) return;
        state.active = true;
        ui.toggle.textContent = 'Stop voice mode';
        ui.toggle.setAttribute('aria-pressed', 'true');
        setStatus('Starting microphone…');
        startListening();
    });
    ui.form.addEventListener('submit', event => {
        event.preventDefault();
        sendMessage();
    });
    ui.message.addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    initRecognition();
    loadSpeechOptions().catch(error => {
        console.error('Could not load speech options:', error);
        setStatus(`${error.message} Default input and reply options are unavailable.`, true);
    });
})();
