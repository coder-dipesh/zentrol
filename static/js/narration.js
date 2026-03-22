/**
 * NarrationManager - Text-to-Speech Slide Narration
 * Integrates with GestureEngine + Reveal.js
 * Uses the Web Speech API (no external dependencies)
 *
 * @version 1.0.0
 */

// ============================================================================
// Slide Script Registry
// ============================================================================
// Maps slide index (0-based) to narration text.
// Edit these strings to customize what gets read aloud on each slide.
// If a slide has no entry, the system falls back to reading its alt text.

const SLIDE_SCRIPTS = {
    0: "Welcome to Zentrol — the gesture-controlled presentation system powered by MediaPipe. Use hand gestures to navigate hands-free.",
    1: "Zentrol supports five core gestures. Thumbs up goes to the previous slide. Peace sign advances to the next slide. Open palm toggles fullscreen. A fist exits fullscreen. And pointing up resets to the first slide.",
    2: "The gesture engine runs at up to thirty frames per second in your browser. It uses majority-vote consensus across multiple frames to eliminate false positives and give you precise, reliable control.",
    3: "The analytics dashboard tracks every gesture detected — including confidence scores, latency, frames per second, and session duration — so you can review presentation performance after the fact.",
    4: "Zentrol is built on Django, Django REST Framework, and MediaPipe. The frontend uses Reveal dot js for slide rendering and Vanilla JavaScript for the gesture pipeline — no heavy frameworks required.",
    5: "Hand detection runs entirely in your browser using MediaPipe's machine learning model. No video data is ever sent to a server. Your camera feed stays completely private.",
    6: "You can deploy Zentrol to Vercel with a single git push. The production build uses WhiteNoise for static files and supports PostgreSQL for persistent analytics storage.",
    7: "The gesture engine supports three performance profiles: responsive for low-latency detection, balanced for everyday use, and high-accuracy for precise control in noisy lighting conditions.",
    8: "Zentrol is open for extension. You can add new gesture mappings, custom slide scripts, and platform plugins — including the LMS plugin for Moodle, coming soon.",
    9: "Thank you for watching this Zentrol demonstration. Show your hand to the camera and start presenting — completely hands-free."
};

// ============================================================================
// NarrationManager Class
// ============================================================================

class NarrationManager {
    constructor(options = {}) {
        this.options = {
            rate: options.rate ?? 0.95,         // Speech rate (0.5 – 2.0)
            pitch: options.pitch ?? 1.0,         // Pitch (0.0 – 2.0)
            volume: options.volume ?? 1.0,       // Volume (0.0 – 1.0)
            voiceLang: options.voiceLang ?? 'en-US',
            autoNarrate: options.autoNarrate ?? false,  // Off by default; user or gesture enables
            debug: options.debug ?? false
        };

        this.isEnabled = this.options.autoNarrate;
        this.isSpeaking = false;
        this.selectedVoice = null;
        this.currentUtterance = null;
        this.currentSlideIndex = 0;

        // Callbacks
        this.onSpeakStart = null;
        this.onSpeakEnd = null;
        this.onToggle = null;

        /** @type {number|null} */
        this._waveRaf = null;
        /** Time (seconds) for waveform oscillators */
        this._waveTime = 0;
        /** Energy bump on word/sentence boundaries (0–1), decays each frame */
        this._waveSpeechPulse = 0;
        /** Smoothed bar heights for organic motion */
        this._waveSmoothed = null;

        /** Live sliders: restart remaining text (mutating utterance mid-speech is ignored in most browsers) */
        this._speechCurrentText = '';
        this._speechCharIndex = 0;
        this._hadBoundary = false;
        this._intentionalRestart = false;
        /** @type {ReturnType<typeof setTimeout>|null} */
        this._liveParamTimer = null;
        /** performance.now() at utterance onstart — fallback when charIndex stays 0 */
        this._speechStartT = 0;

        this._init();
        this._updateToggleButton();
        requestAnimationFrame(() => this._resetWaveformBars());
    }

    // -------------------------------------------------------------------------
    // Initialization
    // -------------------------------------------------------------------------

    _init() {
        if (!('speechSynthesis' in window)) {
            this._log('warn', 'Web Speech API not supported in this browser.');
            return;
        }

        // Voices may load asynchronously
        if (speechSynthesis.getVoices().length > 0) {
            this._selectVoice();
        } else {
            speechSynthesis.addEventListener('voiceschanged', () => {
                this._selectVoice();
            });
        }

        this._log('info', '✅ NarrationManager initialized');
    }

    _selectVoice() {
        const voices = speechSynthesis.getVoices();
        // Prefer a natural-sounding English voice
        const preferred = [
            'Google US English',
            'Microsoft Aria Online (Natural) - English (United States)',
            'Samantha',
            'Karen',
            'Daniel'
        ];

        for (const name of preferred) {
            const match = voices.find(v => v.name === name);
            if (match) {
                this.selectedVoice = match;
                this._log('info', `🎙️ Selected voice: ${match.name}`);
                return;
            }
        }

        // Fallback: first English voice
        const englishVoice = voices.find(v => v.lang.startsWith('en'));
        if (englishVoice) {
            this.selectedVoice = englishVoice;
            this._log('info', `🎙️ Fallback voice: ${englishVoice.name}`);
        }
    }

    // -------------------------------------------------------------------------
    // Core Speech
    // -------------------------------------------------------------------------

    /**
     * Speak a string aloud. Cancels any current speech.
     * @param {string} text
     * @param {boolean} interrupt - Cancel current speech before speaking
     */
    speak(text, interrupt = true) {
        if (!('speechSynthesis' in window) || !this.isEnabled) return;
        if (!text || text.trim() === '') return;

        if (interrupt) {
            this.stop();
        }

        this._speechCurrentText = text;
        this._speechCharIndex = 0;
        this._hadBoundary = false;
        this._enqueueUtterance(text);
    }

    _createUtterance(text) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = this.options.rate;
        utterance.pitch = this.options.pitch;
        utterance.volume = this.options.volume;
        utterance.lang = this.options.voiceLang;
        if (this.selectedVoice) {
            utterance.voice = this.selectedVoice;
        }
        return utterance;
    }

    _attachUtteranceHandlers(utterance) {
        utterance.onboundary = (e) => {
            if (typeof e.charIndex === 'number') {
                this._speechCharIndex = e.charIndex;
                this._hadBoundary = true;
            }
            const n = e && e.name;
            const bump = n === 'word' || n === 'sentence' ? 0.32 : 0.18;
            this._waveSpeechPulse = Math.min(1, this._waveSpeechPulse + bump);
        };

        utterance.onstart = () => {
            this.isSpeaking = true;
            this.currentUtterance = utterance;
            this._speechStartT = performance.now();
            this._waveSpeechPulse = 0.38;
            this._startWaveformLoop();
            this._updateUIState();
            const t = this._speechCurrentText || '';
            if (typeof this.onSpeakStart === 'function') this.onSpeakStart(t);
            this._log('info', `🔊 Speaking: "${t.substring(0, 60)}..."`);
        };

        utterance.onend = () => {
            if (this._intentionalRestart) return;
            this.isSpeaking = false;
            this.currentUtterance = null;
            this._speechCurrentText = '';
            this._speechCharIndex = 0;
            this._hadBoundary = false;
            this._speechStartT = 0;
            this._stopWaveformLoop();
            this._resetWaveformBars();
            this._updateUIState();
            if (typeof this.onSpeakEnd === 'function') this.onSpeakEnd();
        };

        utterance.onerror = (e) => {
            if (this._intentionalRestart) {
                return;
            }
            if (e.error !== 'interrupted' && e.error !== 'canceled') {
                this._log('warn', `Speech error: ${e.error}`);
            }
            this.isSpeaking = false;
            this.currentUtterance = null;
            this._speechCurrentText = '';
            this._speechCharIndex = 0;
            this._hadBoundary = false;
            this._speechStartT = 0;
            this._stopWaveformLoop();
            this._resetWaveformBars();
            this._updateUIState();
        };
    }

    _enqueueUtterance(text) {
        const utterance = this._createUtterance(text);
        this._attachUtteranceHandlers(utterance);
        this.currentUtterance = utterance;
        try {
            if (typeof speechSynthesis !== 'undefined' && speechSynthesis.paused) {
                speechSynthesis.resume();
            }
        } catch (_) {
            /* ignore */
        }
        speechSynthesis.speak(utterance);
    }

    /**
     * Stop any current speech immediately.
     */
    stop() {
        if (this._liveParamTimer) {
            clearTimeout(this._liveParamTimer);
            this._liveParamTimer = null;
        }
        if ('speechSynthesis' in window) {
            speechSynthesis.cancel();
        }
        this.isSpeaking = false;
        this.currentUtterance = null;
        this._speechCurrentText = '';
        this._speechCharIndex = 0;
        this._hadBoundary = false;
        this._intentionalRestart = false;
        this._speechStartT = 0;
        this._stopWaveformLoop();
        this._resetWaveformBars();
        this._updateUIState();
    }

    /**
     * Narrate a specific slide by index.
     * Uses SLIDE_SCRIPTS if available, falls back to slide alt text.
     * @param {number} slideIndex - 0-based index
     */
    narrateSlide(slideIndex) {
        this.currentSlideIndex = slideIndex;
        const text = this._getSlideText(slideIndex);
        if (text) {
            this.speak(text);
        }
    }

    /**
     * Re-narrate the current slide (e.g. user clicked replay).
     */
    replayCurrentSlide() {
        this.narrateSlide(this.currentSlideIndex);
    }

    // -------------------------------------------------------------------------
    // Toggle & Control
    // -------------------------------------------------------------------------

    /**
     * Toggle narration on/off.
     * @returns {boolean} new enabled state
     */
    toggle() {
        this.isEnabled = !this.isEnabled;

        if (!this.isEnabled) {
            this.stop();
        } else {
            // Immediately narrate the current slide when re-enabling
            this.narrateSlide(this.currentSlideIndex);
        }

        this._updateToggleButton();
        if (typeof this.onToggle === 'function') this.onToggle(this.isEnabled);

        this._log('info', `Narration ${this.isEnabled ? 'enabled' : 'disabled'}`);
        return this.isEnabled;
    }

    /**
     * Enable narration.
     */
    enable() {
        if (!this.isEnabled) this.toggle();
    }

    /**
     * Disable narration.
     */
    disable() {
        if (this.isEnabled) this.toggle();
    }

    // -------------------------------------------------------------------------
    // Settings
    // -------------------------------------------------------------------------

    /**
     * Assign rate/volume/pitch on the active utterance (often ignored until pause/resume or restart).
     */
    _applyLiveUtteranceProps() {
        if (!this.isSpeaking || !this.currentUtterance) return;
        const u = this.currentUtterance;
        try {
            u.rate = this.options.rate;
            u.volume = this.options.volume;
            u.pitch = this.options.pitch;
        } catch (_) {
            /* ignore */
        }
    }

    /**
     * Some engines pick up property changes only after pause/resume (first ~word only).
     */
    _flushSpeechParamsWithPauseResume() {
        try {
            if (typeof speechSynthesis === 'undefined' || !speechSynthesis.speaking) return;
            speechSynthesis.pause();
            requestAnimationFrame(() => {
                try {
                    speechSynthesis.resume();
                } catch (_) {
                    /* ignore */
                }
            });
        } catch (_) {
            /* ignore */
        }
    }

    /**
     * Re-apply speed/volume by cancelling and speaking the unread remainder.
     * Web Speech API generally ignores live edits to rate/volume on the current utterance.
     */
    _applyLiveUtterancePropsFromSliders() {
        if (!this.isSpeaking) return;
        this._applyLiveUtteranceProps();

        const text = this._speechCurrentText;
        if (!text || !text.length) {
            this._flushSpeechParamsWithPauseResume();
            return;
        }

        let idx = Math.max(0, Math.min(this._speechCharIndex, text.length));
        // If no boundary index yet, estimate position from elapsed time (~chars/sec)
        if (idx < 1 && text.length > 32) {
            const elapsed = performance.now() - this._speechStartT;
            const cps = 11 * this.options.rate;
            const guess = Math.floor((elapsed / 1000) * cps);
            if (guess >= 6 && guess < text.length - 5) {
                idx = guess;
            }
        }
        if (idx < 1) {
            this._flushSpeechParamsWithPauseResume();
            return;
        }

        let remaining = text.slice(idx).trimStart();
        if (!remaining.length) {
            this._flushSpeechParamsWithPauseResume();
            return;
        }

        this._intentionalRestart = true;
        speechSynthesis.cancel();

        window.setTimeout(() => {
            this._intentionalRestart = false;
            if (!this.isEnabled) return;
            this._speechCurrentText = remaining;
            this._speechCharIndex = 0;
            this._hadBoundary = false;
            this._enqueueUtterance(remaining);
        }, 32);
    }

    _scheduleLiveParamApply() {
        if (this._liveParamTimer) {
            clearTimeout(this._liveParamTimer);
            this._liveParamTimer = null;
        }
        if (!this.isSpeaking) return;
        this._liveParamTimer = setTimeout(() => {
            this._liveParamTimer = null;
            this._applyLiveUtterancePropsFromSliders();
        }, 45);
    }

    setRate(rate) {
        this.options.rate = Math.max(0.5, Math.min(2.0, rate));
        const rateVal = document.getElementById('narration-rate-val');
        const rateSlider = document.getElementById('narration-rate-slider');
        if (rateVal) rateVal.textContent = `${this.options.rate.toFixed(2)}×`;
        if (rateSlider) rateSlider.value = String(this.options.rate);
        this._scheduleLiveParamApply();
    }

    setPitch(pitch) {
        this.options.pitch = Math.max(0.0, Math.min(2.0, pitch));
        this._scheduleLiveParamApply();
    }

    setVolume(volume) {
        this.options.volume = Math.max(0.0, Math.min(1.0, volume));
        const volVal = document.getElementById('narration-vol-val');
        const volSlider = document.getElementById('narration-vol-slider');
        if (volVal) volVal.textContent = `${Math.round(this.options.volume * 100)}%`;
        if (volSlider) volSlider.value = String(this.options.volume);
        this._scheduleLiveParamApply();
    }

    getAvailableVoices() {
        return speechSynthesis.getVoices().filter(v => v.lang.startsWith('en'));
    }

    setVoice(voiceName) {
        const voices = speechSynthesis.getVoices();
        const match = voices.find(v => v.name === voiceName);
        if (match) {
            this.selectedVoice = match;
            this._log('info', `Voice changed to: ${voiceName}`);
        }
    }

    // -------------------------------------------------------------------------
    // Slide Script Helpers
    // -------------------------------------------------------------------------

    /**
     * Get narration text for a slide.
     * Priority: SLIDE_SCRIPTS registry → slide alt text → null
     */
    _getSlideText(slideIndex) {
        // 1. Check script registry
        if (SLIDE_SCRIPTS[slideIndex]) {
            return SLIDE_SCRIPTS[slideIndex];
        }

        // 2. Fall back to slide image alt text
        const slides = document.querySelectorAll('.reveal .slides section');
        if (slides[slideIndex]) {
            const img = slides[slideIndex].querySelector('img');
            if (img && img.alt && img.alt.trim() !== '') {
                return img.alt;
            }
            // 3. Fall back to any text content in the slide
            const text = slides[slideIndex].textContent?.trim();
            if (text) return text;
        }

        return null;
    }

    /**
     * Update or add a slide script at runtime.
     * @param {number} slideIndex
     * @param {string} text
     */
    setSlideScript(slideIndex, text) {
        SLIDE_SCRIPTS[slideIndex] = text;
    }

    // -------------------------------------------------------------------------
    // Waveform (driven by RAF + speech boundaries; Web Speech API exposes no PCM)
    // -------------------------------------------------------------------------

    _stopWaveformLoop() {
        if (this._waveRaf != null) {
            cancelAnimationFrame(this._waveRaf);
            this._waveRaf = null;
        }
    }

    /**
     * Idle bell-shaped bar heights (no container background — bars only).
     */
    _resetWaveformBars() {
        const strip = document.getElementById('narration-wave-strip');
        if (!strip) return;
        const bars = strip.querySelectorAll('.narration-wave-bar');
        const n = bars.length;
        if (!n) return;
        if (!this._waveSmoothed || this._waveSmoothed.length !== n) {
            this._waveSmoothed = new Float32Array(n);
        }
        const center = (n - 1) / 2;
        const maxSpan = Math.max(0.5, center);
        for (let i = 0; i < n; i++) {
            const env = Math.cos(((i - center) / maxSpan) * (Math.PI * 0.5));
            const envPos = Math.max(0, env) ** 1.12;
            const h = 4 + envPos * 18;
            this._waveSmoothed[i] = h;
            bars[i].style.height = `${Math.round(h)}px`;
            bars[i].style.opacity = '';
            bars[i].style.background = 'rgba(255,255,255,0.22)';
            bars[i].style.boxShadow = 'none';
        }
    }

    _startWaveformLoop() {
        this._stopWaveformLoop();
        const strip = document.getElementById('narration-wave-strip');
        if (!strip) return;
        const bars = strip.querySelectorAll('.narration-wave-bar');
        const n = bars.length;
        if (!n) return;
        if (!this._waveSmoothed || this._waveSmoothed.length !== n) {
            this._waveSmoothed = new Float32Array(n);
        }
        const center = (n - 1) / 2;
        const maxSpan = Math.max(0.5, center);
        for (let i = 0; i < n; i++) {
            const env = Math.cos(((i - center) / maxSpan) * (Math.PI * 0.5));
            const envPos = Math.max(0, env) ** 1.12;
            this._waveSmoothed[i] = 4 + envPos * 18;
        }

        const tick = () => {
            if (!this.isSpeaking) {
                this._resetWaveformBars();
                return;
            }
            const t = performance.now() * 0.001;
            this._waveTime = t;
            this._waveSpeechPulse *= 0.94;
            // Fallback motion when boundary events are sparse (Safari / some voices)
            if (Math.random() < 0.02) {
                this._waveSpeechPulse = Math.min(1, this._waveSpeechPulse + 0.1);
            }

            const pitch = this.options.pitch;
            const rate = this.options.rate;
            const vol = this.options.volume;

            for (let i = 0; i < n; i++) {
                const env = Math.cos(((i - center) / maxSpan) * (Math.PI * 0.5));
                const envPos = Math.max(0, env) ** 1.12;
                const t1 = this._waveTime * (2.2 + rate * 1.2) + i * 0.42;
                const t2 = this._waveTime * (3.5 + pitch * 2.4) - i * 0.28;
                const mixed =
                    0.42 * Math.sin(t1 * 8.2) +
                    0.33 * Math.sin(t2 * 5.1 + pitch) +
                    0.25 * Math.sin((this._waveTime + i * 0.2) * (11 + pitch * 3));
                const norm = (mixed + 1) * 0.5;
                const pulse = 0.22 + 0.78 * this._waveSpeechPulse;
                const amp = envPos * (0.32 + 0.68 * norm) * pulse * vol;
                const target = 4 + amp * 22;
                const prev = this._waveSmoothed[i];
                this._waveSmoothed[i] = prev + (target - prev) * 0.38;
                const h = this._waveSmoothed[i];
                bars[i].style.height = `${Math.round(h)}px`;
                const glow = 0.55 + 0.45 * Math.min(1, h / 26);
                bars[i].style.opacity = String(Math.min(1, glow));
                bars[i].style.background = 'rgba(255,255,255,0.92)';
                bars[i].style.boxShadow = '0 0 6px rgba(255,255,255,0.32)';
            }
            this._waveRaf = requestAnimationFrame(tick);
        };
        this._waveRaf = requestAnimationFrame(tick);
    }

    // -------------------------------------------------------------------------
    // UI Updates
    // -------------------------------------------------------------------------

    _updateUIState() {
        // Update the speaking indicator dot
        const indicator = document.getElementById('narration-speaking-dot');
        if (indicator) {
            indicator.style.opacity = this.isSpeaking ? '1' : '0';
        }

        // Single waveform strip above Toggle + Replay
        const waveStrip = document.getElementById('narration-wave-strip');
        if (waveStrip) waveStrip.classList.toggle('narration-waves-active', this.isSpeaking);

        // Update the narration status text
        const statusText = document.getElementById('narration-status-text');
        if (statusText) {
            if (!this.isEnabled) {
                statusText.textContent = 'Off';
            } else if (this.isSpeaking) {
                statusText.textContent = 'Speaking…';
            } else {
                statusText.textContent = 'On';
            }
        }
    }

    _updateToggleButton() {
        const btn = document.getElementById('narration-toggle-btn');
        if (!btn) return;

        if (this.isEnabled) {
            btn.classList.remove('narration-off');
            btn.classList.add('narration-on');
            btn.setAttribute('aria-pressed', 'true');
            btn.title = 'Narration on — click to disable';
        } else {
            btn.classList.remove('narration-on');
            btn.classList.add('narration-off');
            btn.setAttribute('aria-pressed', 'false');
            btn.title = 'Narration off — click to enable';
        }

        this._updateUIState();
    }

    // -------------------------------------------------------------------------
    // Utility
    // -------------------------------------------------------------------------

    _log(level, message) {
        if (!this.options.debug && level === 'debug') return;
        console[level]?.(`[NarrationManager] ${message}`);
    }

    isSupported() {
        return 'speechSynthesis' in window;
    }

    getState() {
        return {
            isEnabled: this.isEnabled,
            isSpeaking: this.isSpeaking,
            currentSlide: this.currentSlideIndex,
            voice: this.selectedVoice?.name ?? 'default',
            rate: this.options.rate,
            pitch: this.options.pitch,
            volume: this.options.volume
        };
    }
}

// ============================================================================
// Export
// ============================================================================

window.NarrationManager = NarrationManager;
window.SLIDE_SCRIPTS = SLIDE_SCRIPTS;