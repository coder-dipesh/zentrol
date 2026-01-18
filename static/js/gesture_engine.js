/**
 * Core Gesture Detection Engine - FINAL PRODUCTION VERSION
 * @version 2.0.0 (FIXED)
 * @date January 14, 2026
 * @author Google Developer Standards
 */

// ============================================================================
// Configuration Profiles
// ============================================================================

const GESTURE_CONFIGS = {
    'high-accuracy': {
        minGestureConfidence: 0.92,
        minFramesForGesture: 15,
        debounceTime: 1500,
        cooldownFrames: 35
    },
    'responsive': {
        minGestureConfidence: 0.75,
        minFramesForGesture: 8,
        debounceTime: 800,
        cooldownFrames: 20
    },
    'balanced': {
        minGestureConfidence: 0.88,
        minFramesForGesture: 10,
        debounceTime: 1200,
        cooldownFrames: 30
    }
};

const MEDIAPIPE_CDN = 'https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1646424915/';
const CAMERA_UTILS_CDN = 'https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js';

// ============================================================================
// Custom Error Classes
// ============================================================================

class GestureEngineError extends Error {
    constructor(message, type, recoverable = false) {
        super(message);
        this.name = 'GestureEngineError';
        this.type = type; // 'CAMERA', 'MEDIAPIPE', 'NETWORK', 'INIT'
        this.recoverable = recoverable;
        this.timestamp = Date.now();
    }
}

// ============================================================================
// Performance Metrics Helper
// ============================================================================

class PerformanceMetrics {
    constructor() {
        this.fps = 0;
        this.frameCount = 0;
        this.lastFrameTime = performance.now();
        this.detectionTimes = [];
        this.maxSamples = 60;
    }

    recordFrame() {
        this.frameCount++;
        const now = performance.now();
        
        if (now - this.lastFrameTime >= 1000) {
            this.fps = this.frameCount;
            this.frameCount = 0;
            this.lastFrameTime = now;
        }
        
        return this.fps;
    }

    recordDetectionTime(timeMs) {
        this.detectionTimes.push(timeMs);
        if (this.detectionTimes.length > this.maxSamples) {
            this.detectionTimes.shift();
        }
    }

    getAverageDetectionTime() {
        if (this.detectionTimes.length === 0) return 0;
        const sum = this.detectionTimes.reduce((a, b) => a + b, 0);
        return sum / this.detectionTimes.length;
    }

    getMetrics() {
        return {
            fps: this.fps,
            avgDetectionTime: this.getAverageDetectionTime(),
            sampleCount: this.detectionTimes.length
        };
    }

    reset() {
        this.fps = 0;
        this.frameCount = 0;
        this.detectionTimes = [];
    }
}

// ============================================================================
// Gesture Detector (Pure Logic - No Side Effects)
// ============================================================================

class GestureDetector {
    constructor(smoothingWindow = 9, debug = false) {
        this.smoothingWindow = smoothingWindow;
        this.debug = debug;
        this.fingerStates = {
            thumb: [],
            index: [],
            middle: [],
            ring: [],
            pinky: []
        };
    }

    /**
     * Calculate which fingers are extended based on landmarks
     * @param {Array} landmarks - MediaPipe hand landmarks
     * @returns {Object} - Boolean state for each finger
     */
    calculateFingerStates(landmarks) {
        const FINGER_INDICES = {
            thumb: [1, 2, 3, 4],
            index: [5, 6, 7, 8],
            middle: [9, 10, 11, 12],
            ring: [13, 14, 15, 16],
            pinky: [17, 18, 19, 20]
        };

        const states = {};

        for (const [finger, indices] of Object.entries(FINGER_INDICES)) {
            const tip = landmarks[indices[3]];
            const pip = landmarks[indices[2]];

            // Y-axis is inverted in camera coordinates
            const isExtended = tip.y < pip.y;

            // Apply smoothing
            this.fingerStates[finger].push(isExtended);
            if (this.fingerStates[finger].length > this.smoothingWindow) {
                this.fingerStates[finger].shift();
            }

            // Majority voting
            const trueCount = this.fingerStates[finger].filter(v => v).length;
            states[finger] = trueCount > this.fingerStates[finger].length / 2;
        }

        return states;
    }

    /**
     * Detect gesture from finger states using priority-based logic
     * @param {Object} fingerStates - Boolean state for each finger
     * @returns {string} - Detected gesture name
     */
    detectGesture(fingerStates) {
        const { thumb, index, middle, ring, pinky } = fingerStates;
        const extendedCount = Object.values(fingerStates).filter(Boolean).length;

        // Debug logging
        if (this.debug) {
            console.log(`Fingers - T:${thumb?'✓':'✗'} I:${index?'✓':'✗'} M:${middle?'✓':'✗'} R:${ring?'✓':'✗'} P:${pinky?'✓':'✗'} | Count:${extendedCount}`);
        }

        // Priority-based detection (order matters!)
        
        // 1. Victory/Peace: Index + Middle up, Ring + Pinky down (thumb optional)
        if (index && middle && !ring && !pinky) {
            if (this.debug) console.log('✅ Victory / Peace gesture detected!');
            return 'victory';
        }



        // 5. Point Up: ONLY index finger extended (middle, ring, pinky must be down)
        // Note: OK sign and fist are already checked above
        if (index && !middle && !ring && !pinky) {
            if (this.debug) console.log('✅ Point up detected!');
            return 'point_up';
        }


        // 3. Thumbs Up: ONLY thumb extended (strict) - but only if not already detected as fist
        if (thumb && !index && !middle && !ring && !pinky) {
            if (this.debug) console.log('✅ Thumbs up detected!');
            return 'thumbs_up';
        }



        // 2. Fist: Check BEFORE other single-finger gestures to avoid false positives
        // Fist = middle, ring, pinky ALL down (these are the key fingers for a fist)
        // Allow thumb and index to be flexible (they can be up or down in a loose fist)
        if (!middle && !ring && !pinky) {
            // This is a fist if middle/ring/pinky are down
            // Extended count should be 0-2 (thumb and/or index can be up)
            if (extendedCount <= 2) {
                if (this.debug) console.log('✅ Fist detected!', { extendedCount, thumb, index, middle, ring, pinky });
                return 'fist';
            }
        }


        // 4. OK Sign: Thumb + Index forming circle - but only if not already detected as fist
        if (thumb && index && !middle && !ring && !pinky) {
            if (this.debug) console.log('✅ OK sign detected!');
            return 'ok';
        }

        // 6. Open Palm: 4+ fingers extended
        if (extendedCount >= 4) {
            if (this.debug) console.log('✅ Open palm detected!');
            return 'open_palm';
        }

        return 'unknown';
    }

    /**
     * Reset smoothing buffers
     */
    reset() {
        for (const finger in this.fingerStates) {
            this.fingerStates[finger] = [];
        }
    }
}

// ============================================================================
// Main Gesture Engine
// ============================================================================

class GestureEngine {
    constructor(options = {}) {
        // Configuration
        const profile = options.profile || 'balanced';
        const profileConfig = GESTURE_CONFIGS[profile] || GESTURE_CONFIGS.balanced;
        
        this.options = {
            detectionConfidence: 0.75,
            trackingConfidence: 0.6,
            maxHands: 1,
            smoothingWindow: 9,
            targetFPS: 15, // Process at lower FPS to save resources
            debug: false,
            ...profileConfig,
            ...options
        };

        // State
        this.currentGesture = null;
        this.gestureConfidence = 0;
        this.gestureFrames = 0;
        this.cooldownCounter = 0;
        this.lastGestureTime = 0;
        this.isInitialized = false;
        this.isRunning = false;

        // Gesture buffering for consensus
        this.gestureBuffer = [];
        this.bufferSize = 4;

        // Components
        this.detector = new GestureDetector(this.options.smoothingWindow, this.options.debug);
        this.metrics = new PerformanceMetrics();

        // MediaPipe instances
        this.hands = null;
        this.camera = null;
        this.videoElement = null;

        // Throttling
        this.lastProcessTime = 0;
        this.rafId = null;

        // Bind methods
        this.processResults = this.processResults.bind(this);
    }

    // ========================================================================
    // Initialization
    // ========================================================================

    /**
     * Initialize MediaPipe Hands
     * @returns {Promise<boolean>}
     */
    async initialize() {
        if (this.isInitialized) {
            this.log('warn', 'Already initialized');
            return true;
        }

        try {
            this.log('info', '🚀 Initializing Gesture Engine...');

            // Load camera utils if needed
            if (typeof self.Camera === 'undefined') {
                await this.loadScript(CAMERA_UTILS_CDN);
            }

            // Initialize MediaPipe Hands
            this.hands = new self.Hands({
                locateFile: (file) => {
                    this.log('debug', `📁 Loading MediaPipe file: ${file}`);
                    // Try local first, fallback to CDN
                    const localPath = `/static/mediapipe/${file}`;
                    return localPath;
                }
            });

            await this.hands.setOptions({
                maxNumHands: this.options.maxHands,
                modelComplexity: 1,
                minDetectionConfidence: this.options.detectionConfidence,
                minTrackingConfidence: this.options.trackingConfidence,
            });

            this.hands.onResults(this.processResults);

            this.isInitialized = true;
            this.log('info', '✅ MediaPipe initialized successfully');
            
            return true;

        } catch (error) {
            const engineError = new GestureEngineError(
                'MediaPipe initialization failed',
                'MEDIAPIPE',
                false
            );
            this.handleError(engineError, error);
            return false;
        }
    }

    /**
     * Initialize camera stream
     * @param {HTMLVideoElement} videoElement
     * @returns {Promise<boolean>}
     */
    async initializeCamera(videoElement) {
        try {
            this.log('info', '📹 Initializing camera...');

            if (!navigator.mediaDevices?.getUserMedia) {
                throw new GestureEngineError(
                    'Camera API not available in this browser',
                    'CAMERA',
                    false
                );
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    frameRate: { ideal: 30 },
                    facingMode: 'user'
                }
            });

            videoElement.srcObject = stream;
            this.videoElement = videoElement;

            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('Camera initialization timeout'));
                }, 10000);

                videoElement.onloadedmetadata = () => {
                    clearTimeout(timeout);
                    videoElement.play()
                        .then(() => {
                            this.log('info', '✅ Camera initialized');
                            resolve(true);
                        })
                        .catch(reject);
                };

                videoElement.onerror = () => {
                    clearTimeout(timeout);
                    reject(new Error('Video element error'));
                };
            });

        } catch (error) {
            const engineError = new GestureEngineError(
                'Camera access denied or unavailable',
                'CAMERA',
                false
            );
            this.handleError(engineError, error);
            return false;
        }
    }

    /**
     * Load external script
     * @param {string} url
     * @returns {Promise<void>}
     */
    loadScript(url) {
        return new Promise((resolve, reject) => {
            // Check if already loaded
            if (document.querySelector(`script[src="${url}"]`)) {
                resolve();
                return;
            }

            const script = document.createElement('script');
            script.src = url;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error(`Failed to load script: ${url}`));
            document.head.appendChild(script);
        });
    }

    // ========================================================================
    // Main Processing Loop
    // ========================================================================

    /**
     * Process MediaPipe results (called every frame)
     * @param {Object} results - MediaPipe detection results
     */
    processResults(results) {
        // Throttle processing to target FPS
        const now = performance.now();
        const elapsed = now - this.lastProcessTime;
        const minInterval = 1000 / this.options.targetFPS;

        if (elapsed < minInterval) {
            return; // Skip this frame
        }

        const startTime = performance.now();
        this.lastProcessTime = now;

        // Update FPS
        this.metrics.recordFrame();

        // No hands detected
        if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
            if (this.currentGesture !== null) {
                this.resetGestureState();
                this.updateUI('none', 0);
            }
            return;
        }

        // Process first hand
        const landmarks = results.multiHandLandmarks[0];
        this.analyzeGesture(landmarks);

        // Record performance
        const detectionTime = performance.now() - startTime;
        this.metrics.recordDetectionTime(detectionTime);
    }

    /**
     * Analyze gesture from landmarks
     * @param {Array} landmarks - Hand landmarks
     */
    analyzeGesture(landmarks) {
        // Apply cooldown
        if (this.cooldownCounter > 0) {
            this.cooldownCounter--;
            return;
        }

        // Detect gesture
        const fingerStates = this.detector.calculateFingerStates(landmarks);
        const gesture = this.detector.detectGesture(fingerStates);

        // Add to consensus buffer
        this.gestureBuffer.push(gesture);
        if (this.gestureBuffer.length > this.bufferSize) {
            this.gestureBuffer.shift();
        }

        // Get consensus gesture
        const consensusGesture = this.getConsensusGesture();

        // Update confidence
        if (consensusGesture === this.currentGesture && consensusGesture !== 'unknown') {
            this.gestureFrames++;
            this.gestureConfidence = Math.min(1.0, this.gestureFrames / 12);
        } else {
            this.currentGesture = consensusGesture;
            this.gestureFrames = 1;
            this.gestureConfidence = 0;
        }

        // Update UI
        this.updateUI(this.currentGesture, this.gestureConfidence);

        // Check if gesture should trigger action
        this.checkGestureTrigger();
    }

    /**
     * Get consensus gesture from buffer
     * @returns {string}
     */
    getConsensusGesture() {
        if (this.gestureBuffer.length === 0) return 'unknown';

        // Count occurrences
        const counts = {};
        this.gestureBuffer.forEach(gesture => {
            counts[gesture] = (counts[gesture] || 0) + 1;
        });

        // Find max
        let maxCount = 0;
        let consensus = 'unknown';

        for (const [gesture, count] of Object.entries(counts)) {
            if (count > maxCount) {
                maxCount = count;
                consensus = gesture;
            }
        }

        // Require strong consensus (75% of buffer)
        const threshold = Math.floor(this.bufferSize * 0.75);
        const result = maxCount >= threshold ? consensus : 'unknown';
        
        // Debug logging for fist gesture
        if (consensus === 'fist' || this.gestureBuffer.includes('fist')) {
            console.log(`🔍 [fist consensus]`, {
                buffer: this.gestureBuffer,
                counts,
                maxCount,
                threshold,
                consensus,
                result,
                bufferSize: this.bufferSize
            });
        }
        
        return result;
    }

    /**
     * Check if gesture should trigger action
     */
    checkGestureTrigger() {
        const now = Date.now();
        const timeSinceLastGesture = now - this.lastGestureTime;
        const canTrigger = (
            this.gestureConfidence >= this.options.minGestureConfidence &&
            this.gestureFrames >= this.options.minFramesForGesture &&
            this.currentGesture !== 'unknown' &&
            timeSinceLastGesture >= this.options.debounceTime
        );

        // Debug logging for fist gesture specifically
        if (this.currentGesture === 'fist') {
            console.log(`🔍 [fist check]`, {
                gesture: this.currentGesture,
                confidence: this.gestureConfidence,
                minConfidence: this.options.minGestureConfidence,
                frames: this.gestureFrames,
                minFrames: this.options.minFramesForGesture,
                timeSinceLast: timeSinceLastGesture,
                debounceTime: this.options.debounceTime,
                canTrigger,
                confidenceMet: this.gestureConfidence >= this.options.minGestureConfidence,
                framesMet: this.gestureFrames >= this.options.minFramesForGesture,
                debounceMet: timeSinceLastGesture >= this.options.debounceTime
            });
        }

        // Debug logging for point_up specifically
        if (this.currentGesture === 'point_up' && this.debug) {
            console.log(`🔍 [point_up check]`, {
                gesture: this.currentGesture,
                confidence: this.gestureConfidence,
                minConfidence: this.options.minGestureConfidence,
                frames: this.gestureFrames,
                minFrames: this.options.minFramesForGesture,
                timeSinceLast: timeSinceLastGesture,
                debounceTime: this.options.debounceTime,
                canTrigger
            });
        }

        if (canTrigger) {
            this.triggerGesture(this.currentGesture);
        }
    }

    /**
     * Trigger gesture action
     * @param {string} gesture
     */
    triggerGesture(gesture) {
        this.log('info', `🎯 Gesture detected: ${gesture} (${Math.round(this.gestureConfidence * 100)}%)`);
        console.log(`🎯 [GestureEngine] Triggering gesture: ${gesture}`, {
            confidence: this.gestureConfidence,
            frames: this.gestureFrames,
            buffer: this.gestureBuffer
        });

        // Dispatch event
        const event = new CustomEvent('gestureDetected', {
            detail: {
                gesture,
                confidence: this.gestureConfidence,
                timestamp: Date.now(),
                cooldown: this.options.debounceTime,
                metrics: this.metrics.getMetrics()
            }
        });
        console.log(`📤 [GestureEngine] Dispatching gestureDetected event:`, event.detail);
        document.dispatchEvent(event);

        // Visual feedback
        this.showGestureFeedback(gesture);

        // Log to backend
        this.logGestureToBackend(gesture);

        // Reset for next gesture
        this.lastGestureTime = Date.now();
        this.cooldownCounter = this.options.cooldownFrames;
        this.gestureFrames = 0;
        this.gestureBuffer = [];
    }

    /**
     * Reset gesture state
     */
    resetGestureState() {
        this.currentGesture = null;
        this.gestureConfidence = 0;
        this.gestureFrames = 0;
        this.gestureBuffer = [];
    }

    // ========================================================================
    // UI Updates (Batched)
    // ========================================================================

    /**
     * Update UI elements (batched DOM updates)
     * @param {string} gesture
     * @param {number} confidence
     */
    updateUI(gesture, confidence) {
        // Use RAF for smooth updates
        requestAnimationFrame(() => {
            const icons = {
                'thumbs_up': '👍',
                'fist': '✊',
                'open_palm': '🖐️',
                'victory': '✌️',
                'ok': '☝️',  // Show point up icon for OK gesture
                'point_up': '☝️',
                'unknown': '❓',
                'none': '👋'
            };

            const names = {
                'thumbs_up': 'Thumbs Up',
                'fist': 'Fist',
                'open_palm': 'Open Palm',
                'victory': 'Victory / Peace',
                'ok': 'Point Up',  // Show "Point Up" text for OK gesture
                'point_up': 'Point Up',
                'unknown': 'Unknown',
                'none': 'Show your hand...'
            };

            // Batch reads
            const iconEl = document.getElementById('gesture-icon');
            const nameEl = document.getElementById('gesture-name');
            const confEl = document.getElementById('confidence-bar');
            const fpsEl = document.getElementById('fps-counter');
            const latencyEl = document.getElementById('latency-counter');

            // Batch writes
            if (iconEl) iconEl.textContent = icons[gesture] || '❓';
            if (nameEl) nameEl.textContent = names[gesture] || 'Unknown';
            if (confEl) confEl.style.width = `${confidence * 100}%`;
            if (fpsEl) fpsEl.textContent = Math.round(this.metrics.fps);
            if (latencyEl) {
                const avgLatency = this.metrics.getAverageDetectionTime();
                latencyEl.textContent = Math.round(avgLatency);
            }
        });
    }

    /**
     * Show gesture feedback animation
     * @param {string} gesture
     */
    showGestureFeedback(gesture) {
        // Gesture feedback animation commented out - no longer showing emoji in middle of screen
        /*
        const emojiMap = {
            'thumbs_up': '👍',
            'fist': '✊',
            'open_palm': '🖐️',
            'victory': '✌️',
            'ok': '☝️',  // Show point up icon for OK gesture
            'point_up': '☝️'
        };

        const feedback = document.createElement('div');
        feedback.className = 'gesture-feedback-animation';
        feedback.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 80px;
            opacity: 0;
            z-index: 10000;
            pointer-events: none;
            transition: opacity 0.3s ease;
            text-shadow: 0 0 30px rgba(76, 175, 80, 0.7);
        `;

        feedback.textContent = emojiMap[gesture] || '❓';
        document.body.appendChild(feedback);

        requestAnimationFrame(() => {
            feedback.style.opacity = '1';
            
            setTimeout(() => {
                feedback.style.opacity = '0';
                setTimeout(() => feedback.remove(), 300);
            }, 600);
        });
        */
    }

    // ========================================================================
    // Backend Communication
    // ========================================================================

    /**
     * Log gesture to backend
     * @param {string} gesture
     */
    async logGestureToBackend(gesture) {
        try {
            const response = await fetch('/api/log-gesture/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    gesture_type: gesture,
                    confidence: this.gestureConfidence,
                    frame_count: this.gestureFrames,
                    detection_time_ms: this.metrics.getAverageDetectionTime(),
                    fps: this.metrics.fps,
                    session_id: this.getSessionId(),
                    timestamp: Date.now()
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

        } catch (error) {
            const engineError = new GestureEngineError(
                'Failed to log gesture to backend',
                'NETWORK',
                true // Recoverable - can continue without logging
            );
            this.handleError(engineError, error);
        }
    }

    /**
     * Get CSRF token with fallback
     * @returns {string}
     */
    getCSRFToken() {
        // Try meta tag first
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        
        if (token) return token;

        // Try cookie
        const cookieToken = this.getCSRFFromCookie();
        if (cookieToken) return cookieToken;

        // Log warning
        this.log('warn', 'CSRF token not found');
        return '';
    }

    /**
     * Get CSRF token from cookie
     * @returns {string|null}
     */
    getCSRFFromCookie() {
        const name = 'csrftoken';
        const cookies = document.cookie.split(';');
        
        for (let cookie of cookies) {
            const [key, value] = cookie.trim().split('=');
            if (key === name) {
                return decodeURIComponent(value);
            }
        }
        
        return null;
    }

    /**
     * Get session ID
     * @returns {string}
     */
    getSessionId() {
        return document.body.dataset.sessionId || 
               sessionStorage.getItem('gesture_session_id') || 
               'anonymous';
    }

    // ========================================================================
    // Lifecycle Management
    // ========================================================================

    /**
     * Start the gesture engine
     * @param {HTMLVideoElement} videoElement
     * @returns {Promise<boolean>}
     */
    async start(videoElement) {
        if (this.isRunning) {
            this.log('warn', 'Already running');
            return true;
        }

        try {
            // Sequential initialization
            const mpSuccess = await this.initialize();
            if (!mpSuccess) {
                throw new GestureEngineError('MediaPipe init failed', 'INIT', false);
            }

            const camSuccess = await this.initializeCamera(videoElement);
            if (!camSuccess) {
                throw new GestureEngineError('Camera init failed', 'INIT', false);
            }

            // Start camera loop
            this.camera = new self.Camera(videoElement, {
                onFrame: async () => {
                    if (!this.isRunning) return;
                    
                    try {
                        await this.hands.send({ image: videoElement });
                    } catch (error) {
                        this.log('warn', 'Frame processing error', { error: error.message });
                    }
                },
                width: 640,
                height: 480
            });

            this.camera.start();
            this.isRunning = true;

            this.log('info', '✅ Gesture engine started successfully');

            // Hide loading overlay
            this.hideLoadingOverlay();

            return true;

        } catch (error) {
            this.handleError(error);
            this.cleanup();
            return false;
        }
    }

    /**
     * Stop the gesture engine
     */
    stop() {
        this.log('info', 'Stopping gesture engine...');
        
        this.isRunning = false;
        
        // Stop camera
        if (this.camera) {
            this.camera.stop();
            this.camera = null;
        }

        // Stop video stream
        if (this.videoElement?.srcObject) {
            this.videoElement.srcObject.getTracks().forEach(track => track.stop());
            this.videoElement.srcObject = null;
        }

        // Close MediaPipe
        if (this.hands) {
            this.hands.close();
            this.hands = null;
        }

        this.cleanup();
        this.log('info', 'Gesture engine stopped');
    }

    /**
     * Cleanup resources
     */
    cleanup() {
        // Reset state
        this.resetGestureState();
        this.detector.reset();
        this.metrics.reset();
        
        // Clear buffers
        this.gestureBuffer = [];
        
        // Cancel RAF
        if (this.rafId) {
            cancelAnimationFrame(this.rafId);
            this.rafId = null;
        }

        this.isInitialized = false;
        this.isRunning = false;
    }

    // ========================================================================
    // Error Handling & Logging
    // ========================================================================

    /**
     * Handle errors consistently
     * @param {Error|GestureEngineError} error
     * @param {Error} originalError - Original error if wrapped
     */
    handleError(error, originalError = null) {
        const isGestureError = error instanceof GestureEngineError;
        const errorType = isGestureError ? error.type : 'UNKNOWN';
        const recoverable = isGestureError ? error.recoverable : false;

        // Log error
        this.log('error', error.message, {
            type: errorType,
            recoverable,
            original: originalError?.message,
            stack: originalError?.stack
        });

        // Show user-facing error only for non-recoverable errors
        if (!recoverable) {
            this.showError(this.getUserFriendlyMessage(error));
        }

        // Report to monitoring service
        this.reportError(error, originalError);
    }

    /**
     * Get user-friendly error message
     * @param {Error} error
     * @returns {string}
     */
    getUserFriendlyMessage(error) {
        if (error instanceof GestureEngineError) {
            switch (error.type) {
                case 'CAMERA':
                    return 'Camera access denied. Please allow camera permissions and refresh.';
                case 'MEDIAPIPE':
                    return 'Failed to initialize gesture detection. Please refresh the page.';
                case 'INIT':
                    return 'Failed to start gesture system. Please check your camera and refresh.';
                default:
                    return 'An error occurred. Please refresh the page.';
            }
        }
        return error.message;
    }

    /**
     * Show error message to user
     * @param {string} message
     */
    showError(message) {
        this.log('error', message);
        
        const statusEl = document.getElementById('loading-status');
        if (statusEl) {
            statusEl.innerHTML = `<span style="color: #f44336">⚠️ ${message}</span>`;
        }
    }

    /**
     * Report error to monitoring service
     * @param {Error} error
     * @param {Error} originalError
     */
    reportError(error, originalError = null) {
        // In production, send to error tracking service (Sentry, etc.)
        if (this.options.debug) {
            console.error('Error Report:', {
                error,
                originalError,
                timestamp: new Date().toISOString(),
                userAgent: navigator.userAgent,
                metrics: this.metrics.getMetrics()
            });
        }
    }

    /**
     * Logging helper
     * @param {string} level - 'info', 'warn', 'error', 'debug'
     * @param {string} message
     * @param {Object} data
     */
    log(level, message, data = {}) {
        if (!this.options.debug && level === 'debug') return;

        const logEntry = {
            timestamp: new Date().toISOString(),
            level,
            message,
            ...data
        };

        const consoleFn = console[level] || console.log;
        consoleFn(`[GestureEngine] ${message}`, data);
    }

    // ========================================================================
    // UI Helpers
    // ========================================================================

    /**
     * Hide loading overlay
     */
    hideLoadingOverlay() {
        setTimeout(() => {
            const overlay = document.getElementById('loading-overlay');
            if (overlay) {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    overlay.style.display = 'none';
                }, 500);
            }
        }, 1000);
    }
}

// ============================================================================
// Export
// ============================================================================

window.GestureEngine = GestureEngine;
window.GESTURE_CONFIGS = GESTURE_CONFIGS;