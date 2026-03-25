/**
 * aac_engine.js — Zentrol AAC Communication Engine
 *
 * No ML model needed. Uses MediaPipe Face Mesh lip landmarks (already loaded)
 * to detect mouth open/closed via pure geometry.
 *
 * Interaction:
 *   Mouth OPEN  → cycle to next phrase in grid
 *   Mouth CLOSED (held 1s on a phrase) → speak it
 *   Type box → fallback for anything not in phrase list
 *
 * Works entirely in the browser. Zero server dependency.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Phrase vocabulary — organised by category
// ─────────────────────────────────────────────────────────────────────────────
const DEFAULT_PHRASES = {
    '👋 Greetings': [
        'Hello everyone',
        'Good morning',
        'Good afternoon',
        'Welcome',
        'Nice to meet you',
    ],
    '💬 Explaining': [
        'Let me explain',
        'For example',
        'As you can see',
        'This shows that',
        'In other words',
        'What I mean is',
    ],
    '🔄 Transitions': [
        'Moving on',
        'Next point',
        'To summarise',
        'Going back',
        'On the other hand',
        'In addition',
    ],
    '❓ Audience': [
        'Any questions?',
        'Good question',
        'I will come back to that',
        'Does that make sense?',
        'Please go ahead',
        'One moment please',
    ],
    '✅ Responses': [
        'Yes',
        'No',
        'Exactly',
        'I agree',
        'Good point',
        'That is correct',
    ],
    '🎯 Closing': [
        'Thank you',
        'In conclusion',
        'That is all from me',
        'Thank you for listening',
        'Any final questions?',
        'Have a great day',
    ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Face Mesh lip landmark indices for mouth open/close detection
// Upper lip: 13  Lower lip: 14  (inner lip vertical distance)
// Also use: 78 (left corner) and 308 (right corner) for mouth width
// ─────────────────────────────────────────────────────────────────────────────
const UPPER_LIP = 13;
const LOWER_LIP = 14;
const MOUTH_LEFT  = 78;
const MOUTH_RIGHT = 308;

// Mouth is "open" when vertical distance > threshold * mouth width
const OPEN_RATIO_THRESHOLD = 0.25;  // tune if needed
const DWELL_MS = 900;               // ms to hold closed to select phrase
const CYCLE_COOLDOWN_MS = 600;      // ms between mouth-open cycles


class AACEngine {
    /**
     * @param {object} opts
     * @param {Function} [opts.onSpeak]   (text) => void — called when phrase spoken
     * @param {Function} [opts.onCycle]   (phraseIndex, phrase) => void — highlight changed
     * @param {boolean}  [opts.debug]
     */
    constructor(opts = {}) {
        this.onSpeak  = opts.onSpeak  ?? null;
        this.onCycle  = opts.onCycle  ?? null;
        this.debug    = opts.debug    ?? false;

        // Phrase list (flat, built from categories)
        this.phrases      = this._buildPhraseList();
        this.currentIndex = 0;

        // Mouth state machine
        this._mouthOpen      = false;
        this._lastOpenTime   = 0;
        this._closedSince    = null;
        this._dwellTimer     = null;
        this._lastCycleTime  = 0;

        // FaceMesh ref (shared with gesture engine)
        this._faceMesh  = null;
        this._running   = false;
        this._video     = null;
        this._rafId     = null;
        this._lastFrame = 0;
        this._interval  = 1000 / 20;  // 20fps is enough for mouth detection

        // Custom phrases added by user
        this._customPhrases = this._loadCustomPhrases();
        if (this._customPhrases.length) {
            this.phrases = [...this.phrases, ...this._customPhrases];
        }
    }

    // ── Public API ────────────────────────────────────────────────────────────

    async start(videoElement) {
        if (this._running) return;
        this._video = videoElement;
        await this._initFaceMesh();
        this._running = true;
        this._loop();
        this._log('AACEngine started');
    }

    stop() {
        this._running = false;
        cancelAnimationFrame(this._rafId);
        clearTimeout(this._dwellTimer);
        this._faceMesh?.close();
        this._faceMesh = null;
        this._log('AACEngine stopped');
    }

    /** Speak a specific phrase immediately (called from UI buttons or type box) */
    speak(text) {
        text = text.trim();
        if (!text) return;
        this._tts(text);
        this.onSpeak?.(text);
        this._log(`Speak: "${text}"`);
    }

    /** Add a custom phrase and persist to localStorage */
    addCustomPhrase(text) {
        text = text.trim();
        if (!text || this.phrases.includes(text)) return;
        this.phrases.push(text);
        this._customPhrases.push(text);
        this._saveCustomPhrases();
    }

    /** Remove a custom phrase */
    removeCustomPhrase(text) {
        this._customPhrases = this._customPhrases.filter(p => p !== text);
        this.phrases = this.phrases.filter(p => p !== text);
        this._saveCustomPhrases();
    }

    getCurrentPhrase() {
        return this.phrases[this.currentIndex] ?? '';
    }

    // ── MediaPipe Face Mesh ───────────────────────────────────────────────────

    async _initFaceMesh() {
        // FaceMesh may already be loaded by lipread_engine — reuse if so
        await this._loadScript(
            'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js'
        );

        this._faceMesh = new FaceMesh({
            locateFile: f =>
                `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${f}`
        });

        await this._faceMesh.setOptions({
            maxNumFaces:            1,
            refineLandmarks:        true,
            minDetectionConfidence: 0.5,
            minTrackingConfidence:  0.5,
        });

        this._faceMesh.onResults(r => this._onFaceResults(r));
        this._log('Face Mesh ready');
    }

    _loop() {
        const tick = async (ts) => {
            if (!this._running) return;
            if (ts - this._lastFrame >= this._interval) {
                this._lastFrame = ts;
                if (this._faceMesh && this._video?.readyState >= 2) {
                    try { await this._faceMesh.send({ image: this._video }); }
                    catch (_) {}
                }
            }
            this._rafId = requestAnimationFrame(tick);
        };
        this._rafId = requestAnimationFrame(tick);
    }

    // ── Face results + mouth geometry ─────────────────────────────────────────

    _onFaceResults(results) {
        if (!results.multiFaceLandmarks?.length) return;
        const lms = results.multiFaceLandmarks[0];

        // Measure mouth openness
        const upper = lms[UPPER_LIP];
        const lower = lms[LOWER_LIP];
        const left  = lms[MOUTH_LEFT];
        const right = lms[MOUTH_RIGHT];

        const vertDist  = Math.abs(lower.y - upper.y);
        const horizDist = Math.abs(right.x - left.x);
        const ratio     = horizDist > 0 ? vertDist / horizDist : 0;

        const isOpen = ratio > OPEN_RATIO_THRESHOLD;
        this._updateMouthState(isOpen, ratio);
    }

    _updateMouthState(isOpen, ratio) {
        const now = Date.now();

        if (isOpen && !this._mouthOpen) {
            // Mouth just opened → cycle to next phrase (with cooldown)
            this._mouthOpen   = true;
            this._closedSince = null;
            clearTimeout(this._dwellTimer);

            if (now - this._lastCycleTime > CYCLE_COOLDOWN_MS) {
                this._lastCycleTime = now;
                this._cycleNext();
            }

        } else if (!isOpen && this._mouthOpen) {
            // Mouth just closed → start dwell timer to speak
            this._mouthOpen   = false;
            this._closedSince = now;

            this._dwellTimer = setTimeout(() => {
                // Still closed after DWELL_MS → speak current phrase
                const phrase = this.getCurrentPhrase();
                if (phrase) this.speak(phrase);
            }, DWELL_MS);

        } else if (isOpen && this._mouthOpen) {
            // Still open — cancel any pending dwell
            clearTimeout(this._dwellTimer);
            this._closedSince = null;
        }

        // Update debug UI
        this._updateRatioDisplay(ratio, isOpen);
    }

    _cycleNext() {
        this.currentIndex = (this.currentIndex + 1) % this.phrases.length;
        const phrase = this.getCurrentPhrase();
        this.onCycle?.(this.currentIndex, phrase);
        this._updateHighlight();
        this._log(`Cycled to: "${phrase}" (${this.currentIndex})`);
    }

    // ── TTS ───────────────────────────────────────────────────────────────────

    _tts(text) {
        window.speechSynthesis.cancel();
        const utt = new SpeechSynthesisUtterance(text);
        utt.rate = 0.95; utt.volume = 1.0; utt.lang = 'en-US';

        const voices = speechSynthesis.getVoices();
        const pick = ['Google US English','Microsoft Aria','Samantha','Karen','Daniel'];
        for (const name of pick) {
            const v = voices.find(v => v.name.includes(name));
            if (v) { utt.voice = v; break; }
        }
        speechSynthesis.speak(utt);
    }

    // ── UI helpers ────────────────────────────────────────────────────────────

    _updateHighlight() {
        document.querySelectorAll('.aac-phrase-btn').forEach((btn, i) => {
            btn.classList.toggle('aac-phrase-selected', i === this.currentIndex);
        });

        // Scroll selected into view
        const selected = document.querySelector('.aac-phrase-selected');
        selected?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    _updateRatioDisplay(ratio, isOpen) {
        const el = document.getElementById('aac-mouth-ratio');
        if (el) {
            el.textContent = `${isOpen ? '😮 Open' : '😐 Closed'} (${ratio.toFixed(2)})`;
            el.style.color = isOpen ? '#1FB6AA' : '#9CA3AF';
        }
    }

    // ── Phrase list helpers ───────────────────────────────────────────────────

    _buildPhraseList() {
        const list = [];
        for (const [, phrases] of Object.entries(DEFAULT_PHRASES)) {
            list.push(...phrases);
        }
        return list;
    }

    _loadCustomPhrases() {
        try {
            return JSON.parse(localStorage.getItem('zentrol_aac_custom') ?? '[]');
        } catch (_) { return []; }
    }

    _saveCustomPhrases() {
        try {
            localStorage.setItem('zentrol_aac_custom', JSON.stringify(this._customPhrases));
        } catch (_) {}
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    _loadScript(url) {
        return new Promise((res, rej) => {
            if (document.querySelector(`script[src="${url}"]`)) { res(); return; }
            const s = document.createElement('script');
            s.src = url; s.onload = res;
            s.onerror = () => rej(new Error(`Failed: ${url}`));
            document.head.appendChild(s);
        });
    }

    _log(...a) { if (this.debug) console.log('[AACEngine]', ...a); }
}

window.AACEngine = AACEngine;
window.AAC_DEFAULT_PHRASES = DEFAULT_PHRASES;