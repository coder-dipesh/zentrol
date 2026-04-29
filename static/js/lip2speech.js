/**
 * LipToSpeechEngine — live lip-to-speech synthesis from the camera feed.
 *
 * Key design:
 *  - AudioContext is created on the toggle click (a user gesture) so the
 *    browser never blocks playback — no matter how long synthesis takes.
 *  - Web Audio API (decodeAudioData + BufferSource) is used instead of
 *    new Audio() so autoplay restrictions never apply after that first gesture.
 */

class LipToSpeechEngine {
  /**
   * @param {HTMLVideoElement} videoElement
   * @param {object}  options
   * @param {number}  options.chunkMs        recording window per chunk (ms), default 3000
   * @param {function} options.onStatusChange called with (status, detail)
   * @param {function} options.onError        called with (errorMessage)
   */
  constructor(videoElement, options = {}) {
    this.video    = videoElement;
    this.chunkMs  = options.chunkMs       ?? 3000;
    this.onStatus = options.onStatusChange ?? (() => {});
    this.onError  = options.onError        ?? console.error;

    this._recorder    = null;
    this._running     = false;
    this._audioQueue  = [];   // { arrayBuffer, durationSec }
    this._playing     = false;
    this._currentNode = null;
    this._loopTimer   = null;

    // AudioContext created immediately (during user gesture in start())
    this._audioCtx = null;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  start() {
    if (this._running) return;

    const stream = this.video.srcObject;
    if (!stream) {
      this.onError('Camera stream not available. Enable the camera first.');
      return;
    }

    // Create / resume AudioContext during the user-gesture call stack.
    // This is the key unlock — all subsequent play() calls will succeed.
    if (!this._audioCtx) {
      this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this._audioCtx.state === 'suspended') {
      this._audioCtx.resume();
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
    if (this._currentNode) {
      try { this._currentNode.stop(); } catch (_) {}
      this._currentNode = null;
    }

    this._audioQueue = [];
    this._playing    = false;
    this._setStatus('idle', 'Off — toggle to start');
  }

  // ── Capture loop ─────────────────────────────────────────────────────────────

  _scheduleCapture() {
    if (!this._running) return;
    this._captureChunk()
      .then(() => {
        if (this._running) this._scheduleCapture();
      })
      .catch((err) => {
        this.onError(`Recording error: ${err.message}`);
        if (this._running) {
          this._loopTimer = setTimeout(() => this._scheduleCapture(), 2000);
        }
      });
  }

  _captureChunk() {
    return new Promise((resolve, reject) => {
      const stream = this.video.srcObject;
      if (!stream) return reject(new Error('No camera stream'));

      const mimeType = [
        'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4',
      ].find((m) => MediaRecorder.isTypeSupported(m)) || '';

      let recorder;
      try {
        recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      } catch (err) {
        return reject(err);
      }

      this._recorder = recorder;
      const chunks  = [];

      recorder.ondataavailable = (e) => { if (e.data?.size > 0) chunks.push(e.data); };

      recorder.onstop = () => {
        if (!this._running || chunks.length === 0) return resolve();
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
        if (this._running) this._setStatus('listening', 'Listening for lip movements…');
        return;
      }

      // Read as ArrayBuffer so Web Audio API can decode it without a URL
      const arrayBuffer = await resp.arrayBuffer();
      const duration    = parseFloat(resp.headers.get('X-Duration-Seconds') || '0');
      this._enqueueAudio(arrayBuffer, duration);

    } catch (err) {
      this.onError(`Network error: ${err.message}`);
      if (this._running) this._setStatus('listening', 'Listening for lip movements…');
    }
  }

  // ── Audio queue (Web Audio API — never blocked by autoplay policy) ────────────

  _enqueueAudio(arrayBuffer, durationSec) {
    this._audioQueue.push({ arrayBuffer, durationSec });
    if (!this._playing) this._playNext();
  }

  async _playNext() {
    const item = this._audioQueue.shift();
    if (!item) {
      this._playing = false;
      if (this._running) this._setStatus('listening', 'Listening for lip movements…');
      return;
    }

    this._playing = true;
    const durStr  = item.durationSec > 0 ? `${item.durationSec.toFixed(1)}s` : '';
    this._setStatus('playing', `Playing synthesised speech${durStr ? ` (${durStr})` : ''}…`);

    try {
      // Decode WAV — AudioContext was created during the user gesture so this works
      const audioBuffer = await this._audioCtx.decodeAudioData(item.arrayBuffer);

      const source = this._audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this._audioCtx.destination);
      this._currentNode = source;

      source.onended = () => {
        this._currentNode = null;
        this._playNext();
      };

      source.start(0);

    } catch (err) {
      this.onError(`Playback error: ${err.message}`);
      this._currentNode = null;
      this._playNext();
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────────

  _setStatus(status, detail) { this.onStatus(status, detail); }

  _csrfToken() {
    const m = document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
}

window.LipToSpeechEngine = LipToSpeechEngine;

// ── File-upload UI ────────────────────────────────────────────────────────────
// Wires up the drop zone, file picker, synthesise button, and result display
// on the /lip2speech/ page.

(function () {
  const dropZone      = document.getElementById('dropZone');
  const videoInput    = document.getElementById('videoInput');
  const fileInfo      = document.getElementById('fileInfo');
  const fileInfoText  = document.getElementById('fileInfoText');
  const videoPreview  = document.getElementById('videoPreview');
  const synthesiseBtn = document.getElementById('synthesiseBtn');
  const statusCard    = document.getElementById('statusCard');
  const statusText    = document.getElementById('statusText');
  const statusSpinner = document.getElementById('statusSpinner');
  const progressFill  = document.getElementById('progressFill');
  const resultCard    = document.getElementById('resultCard');
  const audioPlayer   = document.getElementById('audioPlayer');
  const statsGrid     = document.getElementById('statsGrid');
  const downloadLink  = document.getElementById('downloadLink');
  const resetBtn      = document.getElementById('resetBtn');
  const errorCard     = document.getElementById('errorCard');
  const errorText     = document.getElementById('errorText');
  const errorResetBtn = document.getElementById('errorResetBtn');

  // Only run on the lip2speech page
  if (!dropZone || !videoInput) return;

  let selectedFile = null;

  // ── CSRF ──────────────────────────────────────────────────────────────────
  function getCsrf() {
    const m = document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }

  // ── File selection ────────────────────────────────────────────────────────
  function handleFile(file) {
    if (!file || !file.type.startsWith('video/')) {
      showError('Please select a video file (MP4, WebM, or MOV).');
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      showError('File exceeds the 50 MB limit. Please use a shorter clip.');
      return;
    }

    selectedFile = file;
    const sizeMB = (file.size / 1024 / 1024).toFixed(1);
    fileInfoText.textContent = `${file.name}  —  ${sizeMB} MB`;
    fileInfo.classList.remove('hidden');

    // Preview
    const url = URL.createObjectURL(file);
    videoPreview.src = url;
    videoPreview.classList.remove('hidden');

    synthesiseBtn.disabled = false;

    // Hide any old results / errors
    resultCard.classList.add('hidden');
    errorCard.classList.add('hidden');
    statusCard.classList.add('hidden');
  }

  // Click on drop zone → open file picker
  dropZone.addEventListener('click', () => videoInput.click());

  videoInput.addEventListener('change', () => {
    if (videoInput.files[0]) handleFile(videoInput.files[0]);
  });

  // Drag & drop
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('border-zentrol-teal-500', 'bg-zentrol-teal-50');
  });

  ['dragleave', 'dragend'].forEach((ev) =>
    dropZone.addEventListener(ev, () =>
      dropZone.classList.remove('border-zentrol-teal-500', 'bg-zentrol-teal-50')
    )
  );

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('border-zentrol-teal-500', 'bg-zentrol-teal-50');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // ── Synthesise ────────────────────────────────────────────────────────────
  synthesiseBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    // Show status
    synthesiseBtn.disabled = true;
    statusCard.classList.remove('hidden');
    resultCard.classList.add('hidden');
    errorCard.classList.add('hidden');
    statusText.textContent = 'Uploading video…';
    statusSpinner.classList.remove('hidden');
    animateProgress(0, 30, 800);

    const form = new FormData();
    form.append('video', selectedFile, selectedFile.name);

    try {
      statusText.textContent = 'Running inference… (this may take 10–30 s)';
      animateProgress(30, 85, 15000);

      const resp = await fetch('/api/lip2speech/synthesize/', {
        method: 'POST',
        body: form,
        headers: { 'X-CSRFToken': getCsrf() },
      });

      animateProgress(85, 100, 500);

      if (!resp.ok) {
        let msg = `Server error ${resp.status}`;
        try { const d = await resp.json(); msg = d.error || msg; } catch (_) {}
        throw new Error(msg);
      }

      const wavBlob    = await resp.blob();
      const wavUrl     = URL.createObjectURL(wavBlob);
      const duration   = resp.headers.get('X-Duration-Seconds');
      const procTime   = resp.headers.get('X-Processing-Time-MS');
      const inferID    = resp.headers.get('X-Inference-ID');

      // Show result
      statusCard.classList.add('hidden');
      resultCard.classList.remove('hidden');

      audioPlayer.src = wavUrl;
      audioPlayer.play().catch(() => {});

      downloadLink.href = wavUrl;
      downloadLink.download = inferID ? `lip2speech_${inferID}.wav` : 'lip2speech.wav';

      // Stats
      statsGrid.innerHTML = '';
      const stats = [
        { label: 'Duration',        value: duration  ? `${parseFloat(duration).toFixed(2)} s`  : '—' },
        { label: 'Processing time', value: procTime  ? `${Math.round(procTime)} ms` : '—' },
        { label: 'File size',       value: `${(selectedFile.size / 1024).toFixed(0)} KB` },
        { label: 'Inference ID',    value: inferID ? inferID.slice(0, 8) + '…' : '—' },
      ];
      stats.forEach(({ label, value }) => {
        statsGrid.insertAdjacentHTML('beforeend', `
          <div class="rounded-lg bg-zentrol-gray-50 px-3 py-2">
            <dt class="text-xs text-zentrol-gray-500">${label}</dt>
            <dd class="mt-0.5 font-semibold text-zentrol-navy-500">${value}</dd>
          </div>`);
      });

      synthesiseBtn.disabled = false;

    } catch (err) {
      showError(err.message);
      synthesiseBtn.disabled = false;
    }
  });

  // ── Reset ─────────────────────────────────────────────────────────────────
  function reset() {
    selectedFile = null;
    videoInput.value = '';
    videoPreview.src = '';
    videoPreview.classList.add('hidden');
    fileInfo.classList.add('hidden');
    statusCard.classList.add('hidden');
    resultCard.classList.add('hidden');
    errorCard.classList.add('hidden');
    audioPlayer.src = '';
    synthesiseBtn.disabled = true;
  }

  resetBtn.addEventListener('click', reset);
  errorResetBtn.addEventListener('click', reset);

  // ── Helpers ───────────────────────────────────────────────────────────────
  function showError(msg) {
    statusCard.classList.add('hidden');
    errorCard.classList.remove('hidden');
    errorText.textContent = msg;
  }

  function animateProgress(from, to, durationMs) {
    const start = performance.now();
    function step(now) {
      const t = Math.min((now - start) / durationMs, 1);
      const val = from + (to - from) * t;
      progressFill.style.width = `${val}%`;
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
})();
