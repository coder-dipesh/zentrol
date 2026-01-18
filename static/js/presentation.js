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

const GESTURE_DISPLAY = {
    'victory': { emoji: '✌️', action: 'Next Slide' },
    'thumbs_up': { emoji: '👍', action: 'Previous Slide' },
    'open_palm': { emoji: '🖐️', action: 'Toggle Fullscreen' },
    'fist': { emoji: '✊', action: 'Exit Fullscreen' },
    'point_up': { emoji: '☝️', action: 'Reset Presentation' }
};

const GESTURE_ORDER = ['thumbs_up', 'victory', 'open_palm', 'fist', 'point_up', 'ok'];

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
        document.body.classList.add('fake-fullscreen-active');
        this.container.classList.add('fake-fullscreen');
        
        // Hide UI elements that should be hidden in fullscreen
        const elementsToHide = [
            '#camera-container',
            '.gesture-guide',
            '.controls'
        ];
        
        elementsToHide.forEach(selector => {
            const el = document.querySelector(selector);
            if (el) {
                el.classList.add('hidden-in-fake-fullscreen');
            }
        });
        
        // Trigger custom event for listeners
        window.dispatchEvent(new CustomEvent('fakefullscreenchange', { detail: { isFullscreen: true } }));
    }

    exitFakeFullscreen() {
        if (!this.container) return;
        
        this.fakeFullscreenActive = false;
        document.body.classList.remove('fake-fullscreen-active');
        this.container.classList.remove('fake-fullscreen');
        
        // Show UI elements again
        const elementsToShow = [
            '#camera-container',
            '.gesture-guide',
            '.controls'
        ];
        
        elementsToShow.forEach(selector => {
            const el = document.querySelector(selector);
            if (el) {
                el.classList.remove('hidden-in-fake-fullscreen');
            }
        });
        
        // Trigger custom event for listeners
        window.dispatchEvent(new CustomEvent('fakefullscreenchange', { detail: { isFullscreen: false } }));
        
        // Recalculate Reveal.js layout after exiting fullscreen
        if (typeof Reveal !== 'undefined') {
            setTimeout(() => {
                Reveal.layout();
                Reveal.sync();
            }, 100);
        }
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

    onFullscreenChange(callback) {
        const events = [
            'fullscreenchange',
            'webkitfullscreenchange',
            'mozfullscreenchange',
            'MSFullscreenChange'
        ];

        events.forEach(event => {
            document.addEventListener(event, () => {
                callback(this.isFullscreen());
            });
        });
    }
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
            const response = await fetch('/api/log-gesture/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
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
        document.querySelectorAll('.gesture-item').forEach(item => {
            item.classList.remove('active');
        });

        // Find index of gesture
        const index = GESTURE_ORDER.indexOf(gestureType);
        if (index === -1) return;

        // Add highlight
        const items = document.querySelectorAll('.gesture-item');
        if (items[index]) {
            items[index].classList.add('active');
            
            setTimeout(() => {
                items[index].classList.remove('active');
            }, duration);
        }
    }

    updateSlideIndicator(current, total) {
        let indicator = document.getElementById('slide-indicator');
        
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'slide-indicator';
            indicator.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 8px 15px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                z-index: 1000;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
            `;
            document.body.appendChild(indicator);
        }

        indicator.textContent = `Slide ${current + 1} / ${total}`;
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
        // Monitor real fullscreen API changes
        this.fullscreen.onFullscreenChange((isFullscreen) => {
            this.updateFullscreenUI(isFullscreen);
            this.updateGestureGuide(isFullscreen);
            // Recalculate Reveal.js layout after fullscreen change
            if (typeof Reveal !== 'undefined') {
                setTimeout(() => {
                    Reveal.layout();
                    Reveal.sync();
                }, 100);
            }
        });

        // Monitor fake fullscreen changes (for gesture-based fullscreen)
        window.addEventListener('fakefullscreenchange', (event) => {
            const isFullscreen = event.detail.isFullscreen;
            this.updateFullscreenUI(isFullscreen);
            this.updateGestureGuide(isFullscreen);
            // Recalculate Reveal.js layout after fullscreen change
            if (typeof Reveal !== 'undefined') {
                setTimeout(() => {
                    Reveal.layout();
                    Reveal.sync();
                }, 100);
            }
        });
    }

    // ========================================================================
    // Gesture Handling
    // ========================================================================

    handleGesture(gestureData) {
        const { gesture, confidence, metrics } = gestureData;

        console.log(`📱 Gesture: ${gesture} (${Math.round(confidence * 100)}%)`, metrics);

        // Get action from mapping
        const actionName = GESTURE_ACTION_MAP[gesture];
        if (!actionName) {
            console.log(`⚠️ Unknown gesture: ${gesture}. Available gestures:`, Object.keys(GESTURE_ACTION_MAP));
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
        }
    }

    // ========================================================================
    // UI Updates
    // ========================================================================

    updateFullscreenUI(isFullscreen) {
        // Update button text
        const btn = document.querySelector('.control-btn[onclick*="fullscreen"]');
        if (btn) {
            btn.textContent = isFullscreen ? 'Exit Fullscreen' : 'Fullscreen';
        }
    }

    updateGestureGuide(isFullscreen) {
        // Update gesture guide dynamically
        const gestureItems = document.querySelectorAll('.gesture-item');
        
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
        
        const slides = document.querySelectorAll('.reveal .slides section');
        this.totalSlides = slides.length;
    }

    updateSlideInfo() {
        this.feedback.updateSlideIndicator(this.currentSlide, this.totalSlides);
    }

    hideLoadingOverlay() {
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

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🎬 Initializing Presentation Controller...');

    // Create controller instance
    window.presentationController = new PresentationController();

    // Wait for Reveal.js to be ready
    if (window.Reveal) {
        Reveal.addEventListener('ready', () => {
            console.log('✅ Presentation Controller ready');
            window.presentationController.updateFullscreenUI(false);
        });
    }
});

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