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
            autoNarrate: options.autoNarrate ?? true,  // Narrate on slide change
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

        this._init();
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

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate   = this.options.rate;
        utterance.pitch  = this.options.pitch;
        utterance.volume = this.options.volume;
        utterance.lang   = this.options.voiceLang;

        if (this.selectedVoice) {
            utterance.voice = this.selectedVoice;
        }

        utterance.onstart = () => {
            this.isSpeaking = true;
            this._updateUIState();
            if (typeof this.onSpeakStart === 'function') this.onSpeakStart(text);
            this._log('info', `🔊 Speaking: "${text.substring(0, 60)}..."`);
        };

        utterance.onend = () => {
            this.isSpeaking = false;
            this._updateUIState();
            if (typeof this.onSpeakEnd === 'function') this.onSpeakEnd();
        };

        utterance.onerror = (e) => {
            // 'interrupted' is not a real error — it fires when stop() is called
            if (e.error !== 'interrupted' && e.error !== 'canceled') {
                this._log('warn', `Speech error: ${e.error}`);
            }
            this.isSpeaking = false;
            this._updateUIState();
        };

        this.currentUtterance = utterance;
        speechSynthesis.speak(utterance);
    }

    /**
     * Stop any current speech immediately.
     */
    stop() {
        if ('speechSynthesis' in window) {
            speechSynthesis.cancel();
        }
        this.isSpeaking = false;
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

    setRate(rate) {
        this.options.rate = Math.max(0.5, Math.min(2.0, rate));
    }

    setPitch(pitch) {
        this.options.pitch = Math.max(0.0, Math.min(2.0, pitch));
    }

    setVolume(volume) {
        this.options.volume = Math.max(0.0, Math.min(1.0, volume));
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
    // UI Updates
    // -------------------------------------------------------------------------

    _updateUIState() {
        // Update the speaking indicator dot
        const indicator = document.getElementById('narration-speaking-dot');
        if (indicator) {
            indicator.style.opacity = this.isSpeaking ? '1' : '0';
        }

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