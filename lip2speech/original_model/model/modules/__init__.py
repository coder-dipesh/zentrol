# audio.py requires torchaudio which has a version mismatch — skip for inference
# from .audio import AudioExtractor, SpecEncoder, SpeakerEncoder
from .video import VideoExtractor
from .vgg_face import FaceRecognizer
from .decoder import Decoder