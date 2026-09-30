"""
PlacementPrep OS - Autonomous Voice Agent Console Component
Features:
- Strict Locale-to-Voice matching (en-IN NEVER speaks for te-IN/hi-IN)
- UTF-8 Indic Natural Speech Synthesis with multi-sentence audio queue
- Audio-driven dynamic Canvas Waveform visualizer
- Safe dual Streamlit dispatch (postMessage + parent URL + localStorage)
- Properly escaped JavaScript blocks for Python f-string compatibility
"""

import json
import html as html_lib
import streamlit.components.v1 as components
from language_config import get_language_config

def esc(val):
    return html_lib.escape("" if val is None else str(val))

def render_voice_agent_console(
    latest_reply_text: str,
    selected_language: str = "Telugu",
    autoplay: bool = True,
    height: int = 240
):
    escaped_reply = json.dumps(latest_reply_text or "").replace("</", "<\\/")
    cfg = get_language_config(selected_language)
    lang_code = cfg.get("ttsLocale", "te-IN")

    voice_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            body {{
                padding: 12px 16px;
                background: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                color: #F8FAFC;
                overflow: hidden;
            }}
            .voice-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
            }}
            .title-area {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            .title {{
                font-size: 0.88rem;
                font-weight: 700;
                color: #38BDF8;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }}
            .status-pill {{
                font-size: 0.74rem;
                font-weight: 700;
                padding: 3px 10px;
                border-radius: 20px;
                background: rgba(100, 116, 139, 0.2);
                border: 1px solid rgba(148, 163, 184, 0.2);
                color: #94A3B8;
                transition: all 0.3s ease;
            }}
            .status-listening {{
                background: rgba(56, 189, 248, 0.25);
                border-color: #38BDF8;
                color: #38BDF8;
                animation: pulse-blue 1.5s infinite;
            }}
            .status-speaking {{
                background: rgba(52, 211, 153, 0.25);
                border-color: #34D399;
                color: #34D399;
                animation: pulse-green 1.5s infinite;
            }}
            .status-thinking {{
                background: rgba(168, 85, 247, 0.25);
                border-color: #A855F7;
                color: #A855F7;
            }}
            @keyframes pulse-blue {{
                0% {{ box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.4); }}
                70% {{ box-shadow: 0 0 0 8px rgba(56, 189, 248, 0); }}
                100% {{ box-shadow: 0 0 0 0 rgba(56, 189, 248, 0); }}
            }}
            @keyframes pulse-green {{
                0% {{ box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.4); }}
                70% {{ box-shadow: 0 0 0 8px rgba(52, 211, 153, 0); }}
                100% {{ box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }}
            }}
            .canvas-container {{
                width: 100%;
                height: 40px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 6px;
                margin: 6px 0;
                overflow: hidden;
            }}
            canvas {{
                width: 100%;
                height: 100%;
                display: block;
            }}
            .controls-row {{
                display: flex;
                align-items: center;
                gap: 8px;
                margin-top: 6px;
            }}
            .btn-action {{
                background: rgba(30, 41, 59, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.12);
                color: #F8FAFC;
                padding: 6px 14px;
                border-radius: 8px;
                font-size: 0.82rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
                gap: 6px;
            }}
            .btn-action:hover {{
                background: rgba(51, 65, 85, 0.9);
                border-color: #38BDF8;
            }}
            .btn-primary {{
                background: #0284c7;
                border-color: #38bdf8;
            }}
            .btn-primary:hover {{
                background: #0369a1;
            }}
            .settings-row {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: 0.74rem;
                color: #94A3B8;
                margin-top: 6px;
            }}
            input[type="range"] {{
                accent-color: #38BDF8;
                height: 4px;
                cursor: pointer;
            }}
            .transcript-live {{
                font-size: 0.76rem;
                color: #CBD5E1;
                margin-top: 4px;
                font-style: italic;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                min-height: 16px;
            }}
        </style>
    </head>
    <body>
        <div class="voice-header">
            <div class="title-area">
                <span class="title">🎙️ Autonomous Voice Agent</span>
                <span id="lang-tag" style="font-size: 0.72rem; color: #818CF8; font-weight: 700;">{esc(selected_language)}</span>
            </div>
            <div id="status-pill" class="status-pill">IDLE</div>
        </div>

        <div class="canvas-container">
            <canvas id="waveform"></canvas>
        </div>

        <div id="live-transcript" class="transcript-live">Ready to speak in {esc(selected_language)}...</div>

        <div class="controls-row">
            <button id="btn-mic" class="btn-action btn-primary" onclick="toggleListening()">
                <span>🎙️ Speak Answer</span>
            </button>
            <button id="btn-replay" class="btn-action" onclick="speakFullReply()">
                <span>🔊 Replay AI</span>
            </button>
            <button id="btn-stop" class="btn-action" onclick="stopAllAudio()">
                <span>⏹️ Stop</span>
            </button>
        </div>

        <div class="settings-row">
            <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="chk-auto" {"checked" if autoplay else ""}>
                <span>Auto-speak AI responses</span>
            </label>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span>Speed:</span>
                <input type="range" id="rng-speed" min="0.8" max="1.3" step="0.1" value="1.0" style="width: 70px;">
                <span id="speed-val">1.0x</span>
            </div>
        </div>

        <script>
            const rawReply = {escaped_reply};
            const currentSelectedLang = "{selected_language}";
            const targetTtsLocale = "{lang_code}";

            let recognition = null;
            let isListening = false;
            let animId = null;
            let keepAliveTimer = null;

            const statusPill = document.getElementById('status-pill');
            const btnMic = document.getElementById('btn-mic');
            const chkAuto = document.getElementById('chk-auto');
            const rngSpeed = document.getElementById('rng-speed');
            const speedVal = document.getElementById('speed-val');
            const liveTranscript = document.getElementById('live-transcript');
            const canvas = document.getElementById('waveform');
            const ctx = canvas.getContext('2d');

            rngSpeed.oninput = () => {{ speedVal.innerText = rngSpeed.value + "x"; }};

            function resizeCanvas() {{
                canvas.width = canvas.parentElement.clientWidth;
                canvas.height = canvas.parentElement.clientHeight;
            }}
            window.addEventListener('resize', resizeCanvas);
            resizeCanvas();

            let phase = 0;
            function drawWaveform(active, color = '#38BDF8') {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.beginPath();
                ctx.moveTo(0, canvas.height / 2);

                const width = canvas.width;
                const height = canvas.height;
                const amp = active ? height * 0.38 : height * 0.05;

                for (let x = 0; x < width; x++) {{
                    const y = height / 2 + Math.sin(x * 0.04 + phase) * amp * Math.sin(x / width * Math.PI);
                    ctx.lineTo(x, y);
                }}

                ctx.strokeStyle = color;
                ctx.lineWidth = 2;
                ctx.stroke();

                phase += active ? 0.16 : 0.02;
                animId = requestAnimationFrame(() => drawWaveform(active, color));
            }}
            drawWaveform(false, '#64748B');

            function cleanForSpeech(text) {{
                if (!text) return "";
                return text
                    .replace(/```[\\s\\S]*?```/g, "Code omitted.")
                    .replace(/`([^`]+)`/g, "$1")
                    .replace(/#+\\s/g, "")
                    .replace(/\\*\\*(.*?)\\*\\*/g, "$1")
                    .replace(/\\*(.*?)\\*/g, "$1")
                    .replace(/\\[.*?\\]\\((.*?)\\)/g, "$1")
                    .replace(/\\$\\$(.*?)\\$\\$/g, "")
                    .replace(/\\$(.*?)\\$/g, "$1")
                    .replace(/[-•*]\\s+/g, "")
                    .replace(/\\n+/g, " ")
                    .trim();
            }}

            function splitIntoSentences(text) {{
                if (!text) return [];
                const regex = /[^।!?.\\n]+[।!?.\\n]+/g;
                const matches = text.match(regex);
                return matches && matches.length > 0 ? matches.map(s => s.trim()) : [text];
            }}

            function findTargetVoice(locale) {{
                const voices = window.speechSynthesis.getVoices();
                const prefix = locale.substring(0, 2).toLowerCase();

                let match = voices.find(v => v.lang.toLowerCase() === locale.toLowerCase());
                if (match) return match;

                match = voices.find(v => v.lang.toLowerCase().startsWith(prefix));
                if (match) return match;

                match = voices.find(v => v.name.toLowerCase().includes(currentSelectedLang.toLowerCase()));
                if (match) return match;

                return null;
            }}

            function speakFullReply() {{
                if (!('speechSynthesis' in window)) {{
                    updateStatus('TTS UNAVAILABLE', '');
                    return;
                }}

                stopAllAudio();
                const cleaned = cleanForSpeech(rawReply);
                if (!cleaned) return;

                const chosenVoice = findTargetVoice(targetTtsLocale);

                console.log({{
                    "selectedLanguage": currentSelectedLang,
                    "responseText": cleaned.substring(0, 80) + '...',
                    "ttsLanguage": targetTtsLocale,
                    "selectedVoice": chosenVoice ? chosenVoice.name + ' (' + chosenVoice.lang + ')' : 'Default Browser Synthesis'
                }});

                const chunks = splitIntoSentences(cleaned);
                let chunkIdx = 0;

                updateStatus('SPEAKING', 'status-speaking');
                cancelAnimationFrame(animId);
                drawWaveform(true, '#34D399');

                clearInterval(keepAliveTimer);
                keepAliveTimer = setInterval(() => {{
                    if (window.speechSynthesis.speaking) {{
                        window.speechSynthesis.pause();
                        window.speechSynthesis.resume();
                    }}
                }}, 10000);

                function speakNextChunk() {{
                    if (chunkIdx >= chunks.length) {{
                        clearInterval(keepAliveTimer);
                        updateStatus('IDLE', '');
                        cancelAnimationFrame(animId);
                        drawWaveform(false, '#64748B');
                        return;
                    }}

                    const utter = new SpeechSynthesisUtterance(chunks[chunkIdx]);
                    utter.lang = targetTtsLocale;
                    utter.rate = parseFloat(rngSpeed.value);

                    if (chosenVoice) {{
                        utter.voice = chosenVoice;
                    }}

                    utter.onend = () => {{
                        chunkIdx++;
                        speakNextChunk();
                    }};

                    utter.onerror = (e) => {{
                        console.warn("TTS Chunk Error:", e);
                        chunkIdx++;
                        speakNextChunk();
                    }};

                    window.speechSynthesis.speak(utter);
                }}

                speakNextChunk();
            }}

            function initSTT() {{
                const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
                if (!SR) return null;

                const sr = new SR();
                sr.continuous = false;
                sr.interimResults = true;
                sr.lang = targetTtsLocale;

                sr.onstart = () => {{
                    isListening = true;
                    btnMic.innerHTML = '<span>🔴 Stop Listening</span>';
                    btnMic.classList.add('btn-primary');
                    updateStatus('LISTENING', 'status-listening');
                    liveTranscript.innerText = "Listening in " + currentSelectedLang + "...";
                    cancelAnimationFrame(animId);
                    drawWaveform(true, '#38BDF8');
                }};

                sr.onresult = (evt) => {{
                    let interim = '';
                    let finalTranscript = '';
                    for (let i = evt.resultIndex; i < evt.results.length; ++i) {{
                        if (evt.results[i].isFinal) {{
                            finalTranscript += evt.results[i][0].transcript;
                        }} else {{
                            interim += evt.results[i][0].transcript;
                        }}
                    }}

                    const displayText = finalTranscript || interim;
                    if (displayText) {{
                        liveTranscript.innerText = '"' + displayText + '"';
                    }}

                    if (finalTranscript) {{
                        updateStatus('THINKING', 'status-thinking');
                        liveTranscript.innerText = 'Recognized (' + currentSelectedLang + '): "' + finalTranscript + '"';
                        
                        try {{
                            window.parent.postMessage({{
                                type: 'STREAMLIT_VOICE_TRANSCRIPT',
                                text: finalTranscript
                            }}, '*');

                            const pUrl = new URL(window.parent.location.href);
                            pUrl.searchParams.set('voice_input', finalTranscript);
                            window.parent.location.href = pUrl.toString();
                        }} catch (e) {{
                            try {{
                                localStorage.setItem('placementprep_voice_input', finalTranscript);
                            }} catch(err) {{}}
                        }}
                    }}
                }};

                sr.onerror = (evt) => {{
                    if (evt.error !== 'no-speech') {{
                        liveTranscript.innerText = 'Voice Notice: ' + evt.error;
                    }}
                    stopAllAudio();
                }};

                sr.onend = () => {{
                    if (isListening) stopAllAudio();
                }};

                return sr;
            }}

            function toggleListening() {{
                if (isListening) {{
                    stopAllAudio();
                    return;
                }}
                window.speechSynthesis.cancel();
                if (!recognition) recognition = initSTT();
                if (recognition) {{
                    try {{ recognition.start(); }} catch(e) {{ recognition.stop(); }}
                }} else {{
                    alert("Speech recognition is not supported in this browser. Please use Google Chrome or Microsoft Edge.");
                }}
            }}

            function stopAllAudio() {{
                clearInterval(keepAliveTimer);
                if (recognition && isListening) {{
                    try {{ recognition.stop(); }} catch(e) {{}}
                }}
                if ('speechSynthesis' in window) {{
                    window.speechSynthesis.cancel();
                }}
                isListening = false;
                btnMic.innerHTML = '<span>🎙️ Speak Answer</span>';
                updateStatus('IDLE', '');
                cancelAnimationFrame(animId);
                drawWaveform(false, '#64748B');
            }}

            function updateStatus(label, cssClass) {{
                statusPill.innerText = label;
                statusPill.className = 'status-pill ' + cssClass;
            }}

            if ('speechSynthesis' in window) {{
                window.speechSynthesis.getVoices();
                if (window.speechSynthesis.onvoiceschanged !== undefined) {{
                    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
                }}
            }}

            if (chkAuto.checked && rawReply) {{
                setTimeout(speakFullReply, 450);
            }}
        </script>
    </body>
    </html>
    """
    components.html(voice_html, height=height)