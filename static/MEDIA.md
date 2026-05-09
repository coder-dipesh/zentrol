# Static media (slides + logo)

Demo slide images live under `media/slides/` (PNG) and logos under `media/logo/` (SVG).

If those folders are missing (e.g. fresh clone), extract them from the bundled archive:

```bash
# From repo root (recommended)
chmod +x scripts/ensure-static-media.sh
./scripts/ensure-static-media.sh
```

Or manually:

```bash
cd static
unzip -o media.zip 'media/slides/*.png' 'media/logo/*.svg'
```

The presentation page (`/presentation/`) uses Reveal.js and slide content from the template and `static/`; image-backed slides depend on these files being present (see `templates/presentation.html` and `static/js/`).
