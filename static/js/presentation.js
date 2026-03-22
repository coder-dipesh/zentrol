/**
 * Presentation Controller - FINAL PRODUCTION VERSION
 * @version 2.0.0 (FIXED)
 * @date January 14, 2026
 * @author Google Developer Standards
 */

// ============================================================================
// Configuration
// ============================================================================

const GESTURE_ACTION_MAP = {
    'victory': 'nextSlide',           // ✌️ → Next
    'thumbs_up': 'previousSlide',     // 👍 → Previous  
    'open_palm': 'toggleFullscreen',  // 🖐️ → Toggle Fullscreen
    'fist': 'exitFullscreen',         // ✊ → Exit Fullscreen (only when in fullscreen)
    'point_up': 'resetPresentation',  // ☝️ → R☝️et to First Slide
    'ok': 'resetPresentation'         // 👌 → Reset to First Slide (alternative to point_up)
};
// Expose for inline/bootstrap scripts (e.g. SPA) that remap actions at runtime
window.GESTURE_ACTION_MAP = GESTURE_ACTION_MAP;

const GESTURE_DISPLAY = {
    'victory': { emoji: '✌️', action: 'Next Slide' },
    'thumbs_up': { emoji: '👍', action: 'Previous Slide' },
    'open_palm': { emoji: '🖐️', action: 'Toggle Fullscreen' },
    'fist': { emoji: '✊', action: 'Exit Fullscreen' },
    'point_up': { emoji: '☝️', action: 'Reset Presentation' }
};

const GESTURE_ORDER = ['thumbs_up', 'victory', 'open_palm', 'fist', 'point_up', 'ok'];

/** Gesture hint rows in Control Hub → Actions (see presentation.html `#hub-gesture-hints`) */
const GESTURE_GUIDE_ITEM_SELECTOR = '#hub-gesture-hints .gesture-item';

// ============================================================================
// Fullscreen API Helper
// ============================================================================

class FullscreenAPI {
    constructor(containerId = 'presentation-container') {
        this.container = document.getElementById(containerId);
        this.isSupported = this.checkSupport();
        this.fakeFullscreenActive = false; // Track CSS-based fake fullscreen
    }

    checkSupport() {
        return !!(
            document.fullscreenEnabled ||
            document.webkitFullscreenEnabled ||
            document.mozFullScreenEnabled ||
            document.msFullscreenEnabled
        );
    }

    isFullscreen() {
        // Check both real fullscreen API and fake fullscreen
        return this.fakeFullscreenActive || !!(
            document.fullscreenElement ||
            document.webkitFullscreenElement ||
            document.mozFullScreenElement ||
            document.msFullscreenElement
        );
    }

    // CSS-based fake fullscreen (works with gestures)
    enterFakeFullscreen() {
        if (!this.container) return;
        
        this.fakeFullscreenActive = true;
        document.body.classList.add('overflow-hidden', 'fake-fullscreen-active');
        this.container.classList.add('fake-fullscreen');

        // Tailwind utility classes for fullscreen layout instead of custom CSS
        this.container.classList.add(
            'fixed',
            'inset-0',
            'w-screen',
            'h-screen',
            'z-[9999]',
            'bg-gradient-to-br',
            'from-zentrol-navy-500',
            'to-zentrol-teal-600',
            'pt-0',
            'pl-0'
        );

        // Do NOT set .reveal to w-screen — slide column is narrower than 100vw (Control Hub + padding).
        // Forcing 100vw clips slide images; parent flex chain supplies correct width/height.

        // Hide header and mobile controls while in fullscreen
        const elementsToHide = [
            '.gesture-guide',
            'nav.md\\:hidden'
        ];

        elementsToHide.forEach(selector => {
            const el = document.querySelector(selector);
            if (el) {
                el.classList.add('opacity-0', 'pointer-events-none');
            }
        });
        
        // Trigger custom event for listeners
        window.dispatchEvent(new CustomEvent('fakefullscreenchange', { detail: { isFullscreen: true } }));
    }

    exitFakeFullscreen() {
        if (!this.container) return;
        
        this.fakeFullscreenActive = false;
        document.body.classList.remove('overflow-hidden', 'fake-fullscreen-active');
        this.container.classList.remove('fake-fullscreen');

        // Remove fullscreen layout classes
        this.container.classList.remove(
            'fixed',
            'inset-0',
            'w-screen',
            'h-screen',
            'z-[9999]',
            'bg-gradient-to-br',
            'from-zentrol-navy-500',
            'to-zentrol-teal-600',
            'pt-0',
            'pl-0'
        );

        // Reset Reveal container height/width back to default (header visible again)
        const revealEl = this.container.querySelector('.reveal');
        if (revealEl) {
            revealEl.classList.remove('w-screen', 'h-screen');
            revealEl.classList.add('h-[calc(100vh-50px)]', 'w-full');
        }

        // Show UI elements again
        const elementsToShow = [
            '.gesture-guide',
            'nav.md\\:hidden'
        ];

        elementsToShow.forEach(selector => {
            const el = document.querySelector(selector);
            if (el) {
                el.classList.remove('opacity-0', 'pointer-events-none');
            }
        });
        
        // Trigger custom event for listeners
        window.dispatchEvent(new CustomEvent('fakefullscreenchange', { detail: { isFullscreen: false } }));
        
        scheduleRevealLayoutDebounced(100);
    }

    toggleFakeFullscreen() {
        if (this.fakeFullscreenActive) {
            this.exitFakeFullscreen();
        } else {
            this.enterFakeFullscreen();
        }
    }

    async enter() {
        if (!this.isSupported) {
            throw new Error('Fullscreen not supported');
        }

        const requestMethod = (
            this.container.requestFullscreen ||
            this.container.webkitRequestFullscreen ||
            this.container.mozRequestFullScreen ||  // Note: Capital 'S'
            this.container.msRequestFullscreen
        );

        if (requestMethod) {
            return requestMethod.call(this.container);
        }

        throw new Error('Fullscreen request method not available');
    }

    async exit() {
        const exitMethod = (
            document.exitFullscreen ||
            document.webkitExitFullscreen ||
            document.mozCancelFullScreen ||
            document.msExitFullscreen
        );

        if (exitMethod) {
            return exitMethod.call(document);
        }

        throw new Error('Fullscreen exit method not available');
    }

    async toggle() {
        if (this.isFullscreen()) {
            return this.exit();
        } else {
            return this.enter();
        }
    }

    /**
     * Single handler — do not register fullscreenchange + webkit + moz + ms together:
     * many browsers emit multiple events for one transition, causing repeated Reveal.layout()
     * and main-thread stalls ("page not responding").
     */
    onFullscreenChange(callback) {
        const handler = () => callback(this.isFullscreen());
        document.addEventListener('fullscreenchange', handler);
        document.addEventListener('webkitfullscreenchange', handler);
    }
}

/** Debounced Reveal layout after fullscreen / resize storms (prevents UI freeze). */
let __zentrolRevealFsLayoutTimer = null;
function scheduleRevealLayoutDebounced(delayMs = 120) {
    if (__zentrolRevealFsLayoutTimer) {
        clearTimeout(__zentrolRevealFsLayoutTimer);
    }
    __zentrolRevealFsLayoutTimer = setTimeout(() => {
        __zentrolRevealFsLayoutTimer = null;
        if (typeof Reveal === 'undefined') return;
        try {
            Reveal.layout();
            if (typeof Reveal.sync === 'function') {
                Reveal.sync();
            }
        } catch (e) {
            console.warn('[Zentrol] Reveal layout failed:', e);
        }
    }, delayMs);
}

// ============================================================================
// Logger Helper
// ============================================================================

class PresentationLogger {
    constructor() {
        this.sessionId = this.getSessionId();
        this.csrfToken = this.getCSRFToken();
    }

    async logAction(action, data = {}) {
        try {
            const headers = {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken,
            };
            const gls = typeof window !== 'undefined' && window.__ZENTROL_GESTURE_LOG_SECRET__;
            if (gls) headers['X-Zentrol-Gesture-Log-Secret'] = gls;
            const response = await fetch('/api/log-gesture/', {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    action,
                    timestamp: Date.now(),
                    session_id: this.sessionId,
                    ...data
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            return true;

        } catch (error) {
            console.warn('Failed to log action:', error);
            return false;
        }
    }

    getCSRFToken() {
        // Try meta tag
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (token) return token;

        // Try cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [key, value] = cookie.trim().split('=');
            if (key === 'csrftoken') {
                return decodeURIComponent(value);
            }
        }

        return '';
    }

    getSessionId() {
        return document.body.dataset.sessionId ||
               sessionStorage.getItem('presentation_session_id') ||
               `session_${Date.now()}`;
    }
}

// ============================================================================
// UI Feedback Manager
// ============================================================================

class FeedbackManager {
    constructor() {
        this.activeMessages = new Set();
    }

    showGestureFeedback(text, emoji = '✅', duration = 1500) {
        // Gesture feedback animation commented out - no longer showing in middle of screen
        /*
        const id = `feedback_${Date.now()}`;
        this.activeMessages.add(id);

        const feedback = document.createElement('div');
        feedback.id = id;
        feedback.className = 'gesture-feedback-popup';
        feedback.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 60px;
            background: rgba(0, 0, 0, 0.85);
            color: white;
            padding: 30px 50px;
            border-radius: 20px;
            opacity: 0;
            z-index: 10000;
            pointer-events: none;
            transition: opacity 0.3s ease;
            text-align: center;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6);
        `;

        feedback.innerHTML = `
            <div style="font-size: 80px; margin-bottom: 15px;">${emoji}</div>
            <div style="font-size: 22px; font-weight: bold;">${text}</div>
        `;

        document.body.appendChild(feedback);

        // Animate in
        requestAnimationFrame(() => {
            feedback.style.opacity = '1';
        });

        // Animate out
        setTimeout(() => {
            feedback.style.opacity = '0';
            setTimeout(() => {
                feedback.remove();
                this.activeMessages.delete(id);
            }, 300);
        }, duration);

        return id;
        */
        return null;
    }

    showFullscreenMessage() {
        // Prevent duplicate messages
        if (this.activeMessages.has('fullscreen_msg')) return;

        const id = 'fullscreen_msg';
        this.activeMessages.add(id);

        const msg = document.createElement('div');
        msg.id = id;
        msg.className = 'fullscreen-permission-msg';
        msg.style.cssText = `
            position: fixed;
            top: 40%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.95);
            color: white;
            padding: 40px 60px;
            border-radius: 20px;
            font-size: 20px;
            z-index: 10001;
            text-align: center;
            max-width: 90%;
            border: 3px solid #ff9800;
            box-shadow: 0 0 50px rgba(255, 152, 0, 0.7);
            opacity: 0;
            transition: opacity 0.3s ease;
        `;

        msg.innerHTML = `
            <div style="font-size: 70px; margin-bottom: 20px;">🖐️</div>
            <strong style="font-size: 26px;">Fullscreen Requires User Interaction</strong>
            <br><br>
            <div style="font-size: 18px; line-height: 1.6;">
                Browser security prevents automatic fullscreen from gestures.<br>
                <strong>Please click the "Fullscreen" button</strong> below to enter/exit fullscreen mode.
            </div>
        `;

        document.body.appendChild(msg);

        // Animate in
        requestAnimationFrame(() => {
            msg.style.opacity = '1';
        });

        // Auto-hide after 7 seconds
        setTimeout(() => {
            msg.style.opacity = '0';
            setTimeout(() => {
                msg.remove();
                this.activeMessages.delete(id);
            }, 300);
        }, 7000);
    }

    highlightGestureGuide(gestureType, duration = 1200) {
        // Remove all active highlights
        document.querySelectorAll(GESTURE_GUIDE_ITEM_SELECTOR).forEach(item => {
            item.classList.remove('active');
        });

        // Find index of gesture
        const index = GESTURE_ORDER.indexOf(gestureType);
        if (index === -1) return;

        // Add highlight
        const items = document.querySelectorAll(GESTURE_GUIDE_ITEM_SELECTOR);
        if (items[index]) {
            items[index].classList.add('active');
            
            setTimeout(() => {
                items[index].classList.remove('active');
            }, duration);
        }
    }

    updateSlideIndicator() {
        // Removed per UI request (it overlaps mobile controls).
        const indicator = document.getElementById('slide-indicator');
        if (indicator) indicator.remove();
    }
}

// ============================================================================
// Main Presentation Controller
// ============================================================================

class PresentationController {
    constructor() {
        // State
        this.currentSlide = 0;
        this.totalSlides = 0;
        this.isPresenting = false;

        // Components
        this.fullscreen = new FullscreenAPI();
        this.logger = new PresentationLogger();
        this.feedback = new FeedbackManager();

        // Initialize
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.updateSlideCount();
        this.setupFullscreenMonitoring();
        this.hideLoadingOverlay();
    }

    // ========================================================================
    // Event Listeners
    // ========================================================================

    setupEventListeners() {
        // Gesture detection
        document.addEventListener('gestureDetected', (event) => {
            this.handleGesture(event.detail);
        });

        // Reveal.js events
        if (window.Reveal) {
            Reveal.addEventListener('slidechanged', (event) => {
                this.currentSlide = event.indexh;
                this.updateSlideInfo();
            });

            Reveal.addEventListener('ready', () => {
                this.updateSlideCount();
                this.updateSlideInfo();
            });
        }

        // Keyboard shortcuts (fallback)
        document.addEventListener('keydown', (event) => {
            this.handleKeyboard(event);
        });
    }

    setupFullscreenMonitoring() {
        // Monitor real fullscreen API changes (debounced layout — avoids freeze)
        this.fullscreen.onFullscreenChange((isFullscreen) => {
            this.updateFullscreenUI(isFullscreen);
            this.updateGestureGuide(isFullscreen);
            scheduleRevealLayoutDebounced(120);
        });

        // Monitor fake fullscreen changes (for gesture-based fullscreen)
        window.addEventListener('fakefullscreenchange', (event) => {
            const isFullscreen = event.detail.isFullscreen;
            this.updateFullscreenUI(isFullscreen);
            this.updateGestureGuide(isFullscreen);
            scheduleRevealLayoutDebounced(120);
        });
    }

    // ========================================================================
    // Gesture Handling
    // ========================================================================

    handleGesture(gestureData) {
        const { gesture, confidence, metrics } = gestureData;

        console.log(`📱 Gesture: ${gesture} (${Math.round(confidence * 100)}%)`, metrics);

        // Get action from mapping (prefer live object on window for SPA overrides)
        const map = window.GESTURE_ACTION_MAP || GESTURE_ACTION_MAP;
        const actionName = map[gesture];
        if (!actionName) {
            console.log(`⚠️ Unknown gesture: ${gesture}. Available gestures:`, Object.keys(map));
            return;
        }

        console.log(`🎯 Executing action: ${actionName} for gesture: ${gesture}`);

        // Execute action
        const action = this[actionName];
        if (typeof action === 'function') {
            action.call(this);
            this.feedback.highlightGestureGuide(gesture);
        } else {
            console.error(`❌ Action ${actionName} is not a function!`, typeof action);
        }
    }

    handleKeyboard(event) {
        // Keyboard shortcuts for accessibility
        switch (event.key) {
            case 'f':
            case 'F':
                if (event.ctrlKey || event.metaKey) {
                    event.preventDefault();
                    this.toggleFullscreenDirect();
                }
                break;
            case 'r':
            case 'R':
                if (event.ctrlKey || event.metaKey) {
                    event.preventDefault();
                    this.resetPresentation();
                }
                break;
        }
    }

    // ========================================================================
    // Presentation Actions
    // ========================================================================

    nextSlide() {
        if (!window.Reveal) return;

        Reveal.next();
        this.logger.logAction('next_slide', { 
            from: this.currentSlide,
            method: 'gesture'
        });
        
        console.log('➡️ Next slide');
    }

    previousSlide() {
        if (!window.Reveal) return;

        Reveal.prev();
        this.logger.logAction('previous_slide', { 
            from: this.currentSlide,
            method: 'gesture'
        });
        
        console.log('⬅️ Previous slide');
    }

    resetPresentation() {
        console.log('🔄 resetPresentation() called');
        
        if (!window.Reveal) {
            console.error('❌ Reveal.js not available!');
            return;
        }

        try {
            Reveal.slide(0);
            this.currentSlide = 0;
            this.logger.logAction('reset_presentation');
            
            this.feedback.showGestureFeedback('Reset to Start!', '🔄');
            console.log('✅ Reset to first slide successful');
        } catch (error) {
            console.error('❌ Error resetting presentation:', error);
        }
    }

    // ========================================================================
    // Fullscreen Management
    // ========================================================================
    // Uses CSS-based "fake fullscreen" for gestures (works around browser security)
    // Real Fullscreen API is used for button clicks

    async toggleFullscreen() {
        console.log('🖐️ Open Palm - Toggle fullscreen (gesture)');

        // Use fake fullscreen for gestures (bypasses browser security restriction)
        const wasFullscreen = this.fullscreen.isFullscreen();
        this.fullscreen.toggleFakeFullscreen();
        const isFullscreenNow = this.fullscreen.isFullscreen();

        // Update UI
        this.updateFullscreenUI(isFullscreenNow);
        this.updateGestureGuide(isFullscreenNow);

        // Show feedback
        if (isFullscreenNow) {
            this.feedback.showGestureFeedback('Entered Fullscreen', '🖐️', 1000);
        } else {
            this.feedback.showGestureFeedback('Exited Fullscreen', '🖐️', 1000);
        }

        // Log action
        this.logger.logAction('toggle_fullscreen', { 
            method: 'gesture',
            type: 'fake_fullscreen',
            entering: isFullscreenNow && !wasFullscreen
        });

        console.log(isFullscreenNow ? '✅ Entered fake fullscreen' : '✅ Exited fake fullscreen');
    }

    async exitFullscreen() {
        // Only exit if currently in fullscreen (real or fake)
        if (!this.fullscreen.isFullscreen()) {
            console.log('✊ Fist detected but not in fullscreen → ignored');
            return;
        }

        console.log('✊ Fist - Exiting fullscreen');

        // Try real fullscreen API first (in case we're in real fullscreen)
        if (this.fullscreen.fakeFullscreenActive) {
            // Exit fake fullscreen
            this.fullscreen.exitFakeFullscreen();
            this.updateFullscreenUI(false);
            this.updateGestureGuide(false);
            this.logger.logAction('exit_fullscreen', { method: 'gesture', type: 'fake_fullscreen' });
            this.feedback.showGestureFeedback('Exited Fullscreen', '✊', 1000);
        } else {
            // Try to exit real fullscreen
            try {
                await this.fullscreen.exit();
                this.logger.logAction('exit_fullscreen', { method: 'gesture', type: 'real_fullscreen' });
            } catch (error) {
                console.warn('Exit fullscreen failed:', error.message);
            }
        }
    }

    async toggleFullscreenDirect() {
        // Direct toggle (called from button click) - uses real Fullscreen API
        // Exit fake fullscreen first if active
        if (this.fullscreen.fakeFullscreenActive) {
            this.fullscreen.exitFakeFullscreen();
            this.updateFullscreenUI(false);
            this.updateGestureGuide(false);
        }

        try {
            // Check real fullscreen state (not fake)
            const isRealFullscreen = !!(
                document.fullscreenElement ||
                document.webkitFullscreenElement ||
                document.mozFullScreenElement ||
                document.msFullscreenElement
            );

            if (isRealFullscreen) {
                await this.fullscreen.exit();
            } else {
                await this.fullscreen.enter();
            }

            this.logger.logAction('toggle_fullscreen', { 
                method: 'button',
                type: 'real_fullscreen',
                entering: !isRealFullscreen
            });
        } catch (error) {
            console.error('Fullscreen error:', error);
            alert('Fullscreen is not supported in your browser.');
        } finally {
            // Ensure Reveal catches up even if fullscreenchange is delayed or coalesced oddly.
            scheduleRevealLayoutDebounced(180);
        }
    }

    // ========================================================================
    // UI Updates
    // ========================================================================

    updateFullscreenUI(isFullscreen) {
        const label = document.getElementById('zentrol-fullscreen-label');
        if (label) {
            label.textContent = isFullscreen ? 'Exit Fullscreen' : 'Fullscreen';
            return;
        }
        const btn = document.querySelector('.control-btn[onclick*="fullscreen"]');
        if (btn) {
            btn.textContent = isFullscreen ? 'Exit Fullscreen' : 'Fullscreen';
        }
    }

    updateGestureGuide(isFullscreen) {
        // Update gesture guide dynamically
        const gestureItems = document.querySelectorAll(GESTURE_GUIDE_ITEM_SELECTOR);
        
        // Update open_palm action text (index 2)
        if (gestureItems[2]) {
            const actionEl = gestureItems[2].querySelector('.gesture-action');
            if (actionEl) {
                actionEl.textContent = isFullscreen ? 'Toggle Fullscreen' : 'Enter Fullscreen';
            }
        }

        // Update fist action text (index 3)
        if (gestureItems[3]) {
            const actionEl = gestureItems[3].querySelector('.gesture-action');
            if (actionEl) {
                actionEl.textContent = isFullscreen ? 'Exit Fullscreen' : 'Exit Fullscreen';
                // Optionally disable styling when not in fullscreen
                gestureItems[3].style.opacity = isFullscreen ? '1' : '0.5';
            }
        }
    }

    updateSlideCount() {
        if (!window.Reveal) return;
        // Optional: window.__zentrolSlideCount overrides DOM count (e.g. dynamic decks).
        if (typeof window.__zentrolSlideCount === 'number' && window.__zentrolSlideCount > 0) {
            this.totalSlides = window.__zentrolSlideCount;
            return;
        }
        const slides = document.querySelectorAll('.reveal .slides section');
        this.totalSlides = slides.length;
    }

    updateSlideInfo() {
        this.feedback.updateSlideIndicator();

        // Skip DOM filmstrip updates when a host sets this flag (e.g. custom UI).
        if (!window.__zentrolExternalSlideDeck) {
            const thumbs = document.querySelectorAll('.slide-thumb[data-slide-index]');
            thumbs.forEach((thumb) => {
                const idx = parseInt(thumb.dataset.slideIndex || '0', 10);
                if (idx === this.currentSlide) {
                    thumb.classList.add('ring-2', 'ring-zentrol-teal-500', 'bg-white');
                } else {
                    thumb.classList.remove('ring-2', 'ring-zentrol-teal-500');
                }
            });
        }

        // Update slide count label in filmstrip header
        const label = document.getElementById('slide-count-label');
        if (label && this.totalSlides > 0) {
            label.textContent = `${this.currentSlide + 1} / ${this.totalSlides}`;
        }
    }

    hideLoadingOverlay() {
        // Optional: skip auto-hide when host coordinates loading overlay
        if (typeof window !== 'undefined' && window.__zentrolSkipAutoHideOverlay) {
            return;
        }
        setTimeout(() => {
            const overlay = document.getElementById('loading-overlay');
            if (overlay) {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    overlay.style.display = 'none';
                }, 500);
            }
        }, 1500);
    }

    // ========================================================================
    // Public API
    // ========================================================================

    getCurrentSlide() {
        return this.currentSlide;
    }

    getTotalSlides() {
        return this.totalSlides;
    }

    isInFullscreen() {
        return this.fullscreen.isFullscreen();
    }
}

window.PresentationController = PresentationController;

// ============================================================================
// Initialization (supports late script injection after DOMContentLoaded)
// ============================================================================

function initPresentationController() {
    console.log('🎬 Initializing Presentation Controller...');
    if (window.presentationController) return;

    window.presentationController = new PresentationController();

    if (window.Reveal) {
        Reveal.addEventListener('ready', () => {
            console.log('✅ Presentation Controller ready');
            window.presentationController.updateFullscreenUI(false);
            window.presentationController.updateGestureGuide(false);
        });
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPresentationController);
} else {
    initPresentationController();
}

// ============================================================================
// Debug Helpers (Development Only)
// ============================================================================

if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    window.testGesture = function(gestureName) {
        const event = new CustomEvent('gestureDetected', {
            detail: {
                gesture: gestureName,
                confidence: 0.95,
                timestamp: Date.now(),
                metrics: { fps: 30, avgDetectionTime: 15 }
            }
        });
        document.dispatchEvent(event);
        console.log(`🧪 Test gesture: ${gestureName}`);
    };

    window.testAllGestures = function() {
        const gestures = ['thumbs_up', 'victory', 'open_palm', 'fist', 'ok'];
        gestures.forEach((gesture, index) => {
            setTimeout(() => {
                window.testGesture(gesture);
            }, index * 2000);
        });
    };

    console.log('🧪 Debug mode: Use testGesture("gesture_name") or testAllGestures()');
}