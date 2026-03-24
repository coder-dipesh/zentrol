"""
lipread/management/commands/download_lipread_model.py
 
Downloads LipCoordNet weights + shape predictor from HuggingFace.
 
Usage:
    python manage.py download_lipread_model
"""
 
import os
import urllib.request
from django.core.management.base import BaseCommand
 
BASE = 'https://huggingface.co/wissemkarous/LIPREAD/resolve/main'
 
FILES = [
    (
        os.path.join('lipread', 'pretrain',
            'LipCoordNet_coords_loss_0.025581153109669685'
            '_wer_0.01746208431890914_cer_0.006488426950253695.pt'),
        BASE + '/pretrain/'
               'LipCoordNet_coords_loss_0.025581153109669685'
               '_wer_0.01746208431890914_cer_0.006488426950253695.pt',
        '~95 MB'
    ),
    (
        os.path.join('lipread', 'lip_coordinate_extraction',
            'shape_predictor_68_face_landmarks_GTX.dat'),
        BASE + '/lip_coordinate_extraction/'
               'shape_predictor_68_face_landmarks_GTX.dat',
        '~60 MB'
    ),
]
 
 
class Command(BaseCommand):
    help = 'Download LIPREAD model weights from HuggingFace'
 
    def handle(self, *args, **options):
        self.stdout.write('\n📥 Downloading LIPREAD model files...\n')
 
        for dest, url, size in FILES:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            name = os.path.basename(dest)
 
            if os.path.exists(dest):
                self.stdout.write(f'  ✅ Already exists: {name}')
                continue
 
            self.stdout.write(f'  ⬇  {name} ({size})')
 
            def _progress(block, block_sz, total):
                if total > 0:
                    pct = min(100, int(block * block_sz / total * 100))
                    self.stdout.write(f'\r     {pct}%  ', ending='')
                    self.stdout.flush()
 
            try:
                urllib.request.urlretrieve(url, dest, reporthook=_progress)
                self.stdout.write(f'\r     ✅ Done\n')
            except Exception as e:
                self.stdout.write(f'\r     ❌ Failed: {e}\n')
                raise
 
        self.stdout.write(self.style.SUCCESS(
            '\n✅ All model files ready!\n'
            'Now run: daphne -p 8000 config.asgi:application\n'
        ))