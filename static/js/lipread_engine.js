/**
 * lipread_engine.js — Zentrol AAC Lip-to-Speech
 *
 * KEY FIX: Frames are ONLY sent to the server while isRecording = true.
 * Inference is triggered ONLY when stopRecording() is called (on button/gesture release).
 * The server never auto-fires inference on a timer — it waits for 'infer_now'.
 */
 
const LIP_INDICES = [
    61, 185, 40, 39, 37, 0, 267, 269, 270, 409,   // outer lip
    78,  95, 88, 178, 87, 14, 317, 402, 318, 324   // inner lip
];
 
const FRAME_W = 128;
const FRAME_H = 64;
const LIP_PAD = 0.18;
 
class LipReadEngine {
    constructor(opts = {}) {
        this.wsUrl        = opts.wsUrl        ?? `ws://${location.host}/ws/lipread/`;
        this.targetFPS    = opts.targetFPS    ?? 25;
        this.debug        = opts.debug        ?? false;
        this.onPrediction = opts.onPrediction ?? null;
        this.onStatus     = opts.onStatus     ?? null;
 
        this._running     = false;
        this._faceMesh    = null;
        this._ws          = null;
        this._video       = null;
        this._canvas      = null;
        this._ctx         = null;
        this._lastFrame   = 0;
        this._interval    = 1000 / this.targetFPS;
        this._rafId       = null;
        this._reconnTimer = null;
 
        // Public state
        this.lastWord    = '';
        this.lastConf    = 0;
        this.bufferPct   = 0;
        this.isConnected = false;
 
        // ── RECORDING GATE ──────────────────────────────────────────
        // Frames are only streamed to the server when this is true.
        // Set via startRecording() / stopRecording() from the UI.
        this.isRecording = false;
    }
 
    // ── Public API ────────────────────────────────────────────────────────────
 
    async start(videoElement) {
        if (this._running) return;
        this._video = videoElement;
 
        this._canvas = document.createElement('canvas');
        this._canvas.width  = FRAME_W;
        this._canvas.height = FRAME_H;
        this._ctx = this._canvas.getContext('2d');
 
        await this._initFaceMesh();
        this._connectWS();
        this._running = true;
        this._loop();
        this._log('LipReadEngine started — waiting for recording');
    }
 
    stop() {
        this._running    = false;
        this.isRecording = false;
        cancelAnimationFrame(this._rafId);
        clearTimeout(this._reconnTimer);
        this._ws?.close();
        this._faceMesh?.close();
        this._ws = this._faceMesh = null;
        this._log('LipReadEngine stopped');
    }
 
    /**
     * Call when user STARTS holding button or gesture.
     * Clears any previous buffer on server, begins sending frames.
     */
    startRecording() {
        this.isRecording = true;
        this.lastWord    = '';
        this.lastConf    = 0;
        this.bufferPct   = 0;
        if (this._ws?.readyState === WebSocket.OPEN) {
            this._ws.send(JSON.stringify({ type: 'reset' }));
        }
        this._log('Recording started');
    }
 
    /**
     * Call when user RELEASES button or gesture.
     * Stops sending frames, tells server to run inference immediately
     * on whatever was captured.
     */
    stopRecording() {
        this.isRecording = false;
        if (this._ws?.readyState === WebSocket.OPEN) {
            this._ws.send(JSON.stringify({ type: 'infer_now' }));
        }
        this._log('Recording stopped — inference requested');
    }
 
    getState() {
        return {
            isRunning:   this._running,
            isConnected: this.isConnected,
            isRecording: this.isRecording,
            lastWord:    this.lastWord,
            lastConf:    this.lastConf,
            bufferPct:   this.bufferPct,
        };
    }
 
    // ── MediaPipe Face Mesh ───────────────────────────────────────────────────
 
    async _initFaceMesh() {
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
 
    // ── Frame loop ────────────────────────────────────────────────────────────
 
    _loop() {
        const tick = async (ts) => {
            if (!this._running) return;
            if (ts - this._lastFrame >= this._interval) {
                this._lastFrame = ts;
                // Face mesh runs always (keeps model warm) but
                // _onFaceResults only sends frames when isRecording
                if (this._faceMesh && this._video?.readyState >= 2) {
                    try { await this._faceMesh.send({ image: this._video }); }
                    catch (_) {}
                }
            }
            this._rafId = requestAnimationFrame(tick);
        };
        this._rafId = requestAnimationFrame(tick);
    }
 
    // ── Face results ──────────────────────────────────────────────────────────
 
    _onFaceResults(results) {
        // ── GATE: only send frames when user is actively recording ──
        if (!this.isRecording) return;
 
        if (!results.multiFaceLandmarks?.length) return;
        const lms = results.multiFaceLandmarks[0];
        const lipCoords = LIP_INDICES.map(i => [lms[i].x, lms[i].y]);
        const img = this._cropLip(lms);
        if (!img) return;
        this._sendFrame(img, lipCoords);
    }
 
    // ── Lip crop ──────────────────────────────────────────────────────────────
 
    _cropLip(lms) {
        if (!this._video || !this._ctx) return null;
        const vw = this._video.videoWidth  || 640;
        const vh = this._video.videoHeight || 480;
 
        const pts  = LIP_INDICES.map(i => lms[i]);
        const xs   = pts.map(p => p.x * vw);
        const ys   = pts.map(p => p.y * vh);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);
        const bw   = maxX - minX, bh = maxY - minY;
 
        if (bw < 8 || bh < 4) return null;
 
        const padX = bw * LIP_PAD, padY = bh * LIP_PAD * 1.5;
        const sx = Math.max(0, minX - padX);
        const sy = Math.max(0, minY - padY);
        const sw = Math.min(vw - sx, bw + padX * 2);
        const sh = Math.min(vh - sy, bh + padY * 2);
 
        this._ctx.clearRect(0, 0, FRAME_W, FRAME_H);
        this._ctx.drawImage(this._video, sx, sy, sw, sh, 0, 0, FRAME_W, FRAME_H);
        return this._canvas.toDataURL('image/jpeg', 0.72);
    }
 
    // ── WebSocket ─────────────────────────────────────────────────────────────
 
    _connectWS() {
        try {
            this._ws = new WebSocket(this.wsUrl);
            this._ws.onopen = () => {
                this.isConnected = true;
                this._notify('connected', 'Ready — hold button to speak');
            };
            this._ws.onmessage = e => this._onMessage(e.data);
            this._ws.onclose = () => {
                this.isConnected = false;
                this._notify('disconnected', 'Reconnecting...');
                if (this._running)
                    this._reconnTimer = setTimeout(() => this._connectWS(), 3000);
            };
            this._ws.onerror = () => this._notify('error', 'Connection error');
        } catch (e) { this._log('WS error:', e); }
    }
 
    _sendFrame(imgB64, lipCoords) {
        if (this._ws?.readyState !== WebSocket.OPEN) return;
        this._ws.send(JSON.stringify({
            type: 'frame', image: imgB64, landmarks: lipCoords
        }));
    }
 
    _onMessage(raw) {
        try {
            const msg = JSON.parse(raw);
            if (msg.type === 'prediction') {
                this.lastWord = msg.word;
                this.lastConf = msg.confidence;
                this._log(`Prediction: "${msg.word}" (${(msg.confidence*100).toFixed(0)}%)`);
                this.onPrediction?.(msg.word, msg.confidence);
            } else if (msg.type === 'status') {
                if (msg.progress != null) this.bufferPct = msg.progress;
                this._notify(msg.status, msg.message);
            }
        } catch (_) {}
    }
 
    // ── Helpers ───────────────────────────────────────────────────────────────
 
    _notify(status, msg) { this.onStatus?.(status, msg); }
 
    _loadScript(url) {
        return new Promise((res, rej) => {
            if (document.querySelector(`script[src="${url}"]`)) { res(); return; }
            const s = document.createElement('script');
            s.src = url; s.onload = res;
            s.onerror = () => rej(new Error(`Failed: ${url}`));
            document.head.appendChild(s);
        });
    }
 
    _log(...a) { if (this.debug) console.log('[LipReadEngine]', ...a); }
}
 
window.LipReadEngine = LipReadEngine;
 
