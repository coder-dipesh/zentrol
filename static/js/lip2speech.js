/**
 * LipToSpeechEngine — live lip-to-speech synthesis from the camera feed.
 *
 * Hooks into the existing camera stream (HTMLVideoElement.srcObject),
 * records short video chunks via MediaRecorder, sends each chunk to
 * POST /api/lip2speech/synthesize/, and plays back the returned WAV audio
 * in a sequential queue so synthesised speech doesn't overlap.
 *
 * Usage (after GestureEngine has started the camera):
 *   const engine = new LipToSpeechEngine(document.getElementById('camera-feed'));
 *   engine.start();
 *   engine.stop();
 */

class LipToSpeechEngine {
  /**
   * @param {HTMLVideoElement} videoElement  — the live camera feed element
   * @param {object}           options
   * @param {number}           options.chunkMs        — recording window per chunk (ms), default 3000
   * @param {number}           options.overlapMs       — overlap between chunks (ms), default 0
   * @param {function}         options.onStatusChange  — called with (status, detail) on state changes
   * @param {function}         options.onError         — called with (errorMessage)
   */
  constructor(videoElement, options = {}) {
    this.video      = videoElement;
    this.chunkMs    = options.chunkMs       ?? 3000;
    this.overlapMs  = options.overlapMs     ?? 0;
    this.onStatus   = options.onStatusChange ?? (() => {});
    this.onError    = options.onError        ?? console.error;

    this._recorder    = null;
    this._running     = false;
    this._audioQueue  = [];
    this._playing     = false;
    this._currentAudio = null;
    this._loopTimer   = null;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  start() {
    if (this._running) return;
    const stream = this.video.srcObject;
    if (!stream) {
      this.onError('Camera stream not available. Make sure the camera is enabled.');
      return;
    }
    this._running = true;
    this._setStatus('listening', 'Listening for lip movements…');
    this._scheduleCapture();
  }

  stop() {
    this._running = false;
    clearTimeout(this._loopTimer);
    if (this._recorder && this._recorder.state !== 'inactive') {
      this._recorder.stop();
    }
    if (this._currentAudio) {
      this._currentAudio.pause();
      this._currentAudio = null;
    }
    this._audioQueue = [];
    this._playing    = false;
    this._setStatus('idle', 'Lip to Speech stopped.');
  }

  // ── Capture loop ─────────────────────────────────────────────────────────────

  _scheduleCapture() {
    if (!this._running) return;
    this._captureChunk()
      .then(() => {
        if (this._running) {
          this._loopTimer = setTimeout(() => this._scheduleCapture(), this.overlapMs);
        }
      })
      .catch((err) => {
        this.onError(`Recording error: ${err.message}`);
        // Back-off and retry
        if (this._running) {
          this._loopTimer = setTimeout(() => this._scheduleCapture(), 2000);
        }
      });
  }

  _captureChunk() {
    return new Promise((resolve, reject) => {
      const stream = this.video.srcObject;
      if (!stream) return reject(new Error('No camera stream'));

      // Pick the best supported MIME type
      const mimeType = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4']
        .find((m) => MediaRecorder.isTypeSupported(m)) || '';

      let recorder;
      try {
        recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      } catch (err) {
        return reject(err);
      }

      this._recorder = recorder;
      const chunks = [];

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      };

      recorder.onstop = () => {
        if (!this._running) return resolve();
        if (chunks.length === 0) return resolve();

        const blob = new Blob(chunks, { type: mimeType || 'video/webm' });
        this._setStatus('synthesising', 'Synthesising speech…');
        this._synthesise(blob).finally(resolve);
      };

      recorder.onerror = (e) => reject(e.error || new Error('MediaRecorder error'));

      recorder.start();
      setTimeout(() => {
        if (recorder.state !== 'inactive') recorder.stop();
      }, this.chunkMs);
    });
  }

  // ── Backend call ─────────────────────────────────────────────────────────────

  async _synthesise(blob) {
    const form = new FormData();
    form.append('video', blob, `chunk_${Date.now()}.webm`);

    try {
      const resp = await fetch('/api/lip2speech/synthesize/', {
        method: 'POST',
        body: form,
        headers: { 'X-CSRFToken': this._csrfToken() },
      });

      if (!resp.ok) {
        let msg = `Server error ${resp.status}`;
        try { const d = await resp.json(); msg = d.error || msg; } catch (_) {}
        this.onError(msg);
        this._setStatus('listening', 'Listening for lip movements…');
        return;
      }

      const audioBlob = await resp.blob();
      const duration  = resp.headers.get('X-Duration-Seconds') || '?';
      this._enqueueAudio(audioBlob, parseFloat(duration));

    } catch (err) {
      this.onError(`Network error: ${err.message}`);
      this._setStatus('listening', 'Listening for lip movements…');
    }
  }

  // ── Audio queue ───────────────────────────────────────────────────────────────

  _enqueueAudio(blob, durationSec) {
    const url = URL.createObjectURL(blob);
    this._audioQueue.push({ url, durationSec });
    if (!this._playing) this._playNext();
  }

  _playNext() {
    if (!this._running && this._audioQueue.length === 0) return;
    const item = this._audioQueue.shift();
    if (!item) {
      this._playing = false;
      if (this._running) this._setStatus('listening', 'Listening for lip movements…');
      return;
    }

    this._playing = true;
    this._setStatus('playing', `Playing synthesised speech (${item.durationSec.toFixed(1)}s)…`);

    const audio = new Audio(item.url);
    this._currentAudio = audio;

    audio.onended = () => {
      URL.revokeObjectURL(item.url);
      this._currentAudio = null;
      this._playNext();
    };

    audio.onerror = () => {
      URL.revokeObjectURL(item.url);
      this._currentAudio = null;
      this._playNext();
    };

    audio.play().catch((err) => {
      this.onError(`Audio playback error: ${err.message}`);
      this._currentAudio = null;
      this._playNext();
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────────

  _setStatus(status, detail) {
    this.onStatus(status, detail);
  }

  _csrfToken() {
    const m = document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
}

window.LipToSpeechEngine = LipToSpeechEngine;
