"""
lipread/consumers.py
 
KEY FIX: Inference is ONLY triggered by 'infer_now' message (sent when user
releases button/gesture). Frames are never auto-processed on a timer.
The server is purely passive — it buffers frames, then fires on demand.
"""
 
import json
import base64
import asyncio
import logging
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer
 
logger = logging.getLogger(__name__)
 
_MODEL_BUNDLE = None
 
WEIGHTS_FILENAME = (
    'LipCoordNet_coords_loss_0.025581153109669685'
    '_wer_0.01746208431890914_cer_0.006488426950253695.pt'
)
 
 
class LipReadConsumer(AsyncWebsocketConsumer):
 
    FRAME_W = 128
    FRAME_H = 64
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frames    = []   # accumulated during recording
        self.landmarks = []
        self.busy      = False
 
    # ── WebSocket lifecycle ──────────────────────────────────────────
 
    async def connect(self):
        await self.accept()
        logger.info('LipRead WS connected')
 
        global _MODEL_BUNDLE
        if _MODEL_BUNDLE is None:
            try:
                _MODEL_BUNDLE = await asyncio.get_event_loop().run_in_executor(
                    None, _load_model
                )
                await self._status('model_ready', 'LipCoordNet loaded ✅')
            except FileNotFoundError as e:
                await self._status('model_error', str(e))
                logger.error(f'Model load error: {e}')
            except Exception as e:
                await self._status('model_error', f'Failed to load model: {e}')
                logger.error(f'Model load error: {e}')
        else:
            await self._status('model_ready', 'Ready — hold button to speak')
 
    async def disconnect(self, close_code):
        self.frames.clear()
        self.landmarks.clear()
        logger.info(f'LipRead WS disconnected ({close_code})')
 
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            t    = data.get('type')
 
            if t == 'frame':
                # Only buffer — never auto-infer
                await self._buffer_frame(data)
 
            elif t == 'infer_now':
                # User released button — run inference on what we have
                await self._infer_on_demand()
 
            elif t == 'reset':
                # User started a new recording — clear old buffer
                self._clear_buffer()
                await self._status('ready', 'Recording...')
 
            elif t == 'ping':
                await self.send(json.dumps({'type': 'pong'}))
 
        except Exception as e:
            logger.warning(f'receive error: {e}')
 
    # ── Frame buffering ──────────────────────────────────────────────
 
    async def _buffer_frame(self, data):
        img_b64   = data.get('image',     '')
        landmarks = data.get('landmarks', [])
 
        if not img_b64 or len(landmarks) != 20:
            return
 
        try:
            raw   = base64.b64decode(img_b64.split(',')[-1])
            arr   = np.frombuffer(raw, dtype=np.uint8)
            import cv2
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return
            frame = cv2.resize(frame, (self.FRAME_W, self.FRAME_H))
        except Exception as e:
            logger.debug(f'frame decode error: {e}')
            return
 
        self.frames.append(frame)
        self.landmarks.append(np.array(landmarks, dtype=np.float32))
 
        # Send buffer progress so UI can show fill bar
        n   = len(self.frames)
        pct = min(100, int(n / 75 * 100))
        if n % 5 == 0:  # update every 5 frames
            await self._status('buffering', f'Capturing... {n} frames', pct)
 
    def _clear_buffer(self):
        self.frames.clear()
        self.landmarks.clear()
 
    # ── On-demand inference ──────────────────────────────────────────
 
    async def _infer_on_demand(self):
        """
        Called when user releases the button/gesture.
        Run inference on whatever frames were captured, regardless of count.
        Minimum 5 frames to attempt — otherwise report nothing detected.
        """
        n = len(self.frames)
        logger.info(f'infer_now called with {n} frames')
 
        if n < 5:
            await self._status('too_short', 'Hold longer — not enough frames captured')
            self._clear_buffer()
            return
 
        if self.busy:
            await self._status('busy', 'Processing previous recording...')
            return
 
        frames    = list(self.frames)
        landmarks = list(self.landmarks)
        self._clear_buffer()  # clear immediately so next recording is fresh
 
        await self._run_inference(frames, landmarks)
 
    # ── Inference ────────────────────────────────────────────────────
 
    async def _run_inference(self, frames, landmarks):
        if _MODEL_BUNDLE is None:
            await self._status('model_error', 'Model not loaded')
            return
 
        self.busy = True
        await self._status('processing', 'Reading lips...')
 
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _run_inference_sync, _MODEL_BUNDLE, frames, landmarks
            )
 
            if result and result['word']:
                logger.info(f"Prediction: \"{result['word']}\" ({result['confidence']:.2f})")
                await self.send(json.dumps({
                    'type':       'prediction',
                    'word':       result['word'],
                    'confidence': round(result['confidence'], 3),
                }))
            else:
                await self._status('no_result', 'Nothing detected — try again')
 
        except Exception as e:
            logger.error(f'inference error: {e}')
            await self._status('error', f'Inference error: {e}')
        finally:
            self.busy = False
 
    # ── Helpers ──────────────────────────────────────────────────────
 
    async def _status(self, status, message, progress=None):
        payload = {'type': 'status', 'status': status, 'message': message}
        if progress is not None:
            payload['progress'] = progress
        await self.send(json.dumps(payload))
 
 
# ── Model loading ────────────────────────────────────────────────────────────
 
def _load_model():
    import torch, os, sys
 
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    if parent not in sys.path:
        sys.path.insert(0, parent)
 
    from lipread.model import LipCoordNet
 
    weights_path = os.path.join(here, 'pretrain', WEIGHTS_FILENAME)
    if not os.path.exists(weights_path):
        raise FileNotFoundError(
            f'Weights not found: {weights_path}\n'
            f'Run: python manage.py download_lipread_model'
        )
 
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f'Loading LipCoordNet on {device}...')
    model = LipCoordNet()
    model.load_state_dict(torch.load(weights_path, map_location=device))
    model.to(device).eval()
    logger.info('LipCoordNet loaded successfully')
    return {'model': model, 'device': device}
 
 
# ── Inference (thread pool) ──────────────────────────────────────────────────
 
def _run_inference_sync(bundle, frames, landmarks):
    import torch
 
    try:
        model  = bundle['model']
        device = bundle['device']
        T      = len(frames)
 
        if T < 5:
            return None
 
        # Video tensor (1, 3, T, H, W)
        vid = np.stack(frames, axis=0).astype(np.float32) / 255.0
        vid = torch.FloatTensor(vid.transpose(3, 0, 1, 2)).unsqueeze(0).to(device)
 
        # Coord tensor (1, T, 20, 2)
        crd = np.stack(landmarks, axis=0).astype(np.float32)
        crd = torch.FloatTensor(crd).unsqueeze(0).to(device)
 
        with torch.no_grad():
            out = model(vid, crd)   # (1, T, 28)
 
        word, conf = _ctc_decode(out[0])
        return {'word': word, 'confidence': conf} if word else None
 
    except Exception as e:
        logger.error(f'_run_inference_sync error: {e}')
        return None
 
 
def _ctc_decode(logits):
    VOCAB = ' abcdefghijklmnopqrstuvwxyz'
    probs = logits.softmax(-1).cpu().numpy()
    ids   = probs.argmax(-1)
    chars, confs, prev = [], [], None
 
    for t, idx in enumerate(ids):
        if idx != prev:
            if idx != 0 and idx < len(VOCAB):
                chars.append(VOCAB[idx])
                confs.append(float(probs[t, idx]))
        prev = idx
 
    word = ''.join(chars).strip()
    conf = float(np.mean(confs)) if confs else 0.0
    return word, conf