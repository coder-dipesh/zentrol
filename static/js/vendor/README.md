# Vendored JS (served as `/static/js/vendor/...`)

## `camera_utils.js`

MediaPipe **Camera** helper (from `@mediapipe/camera_utils`). Vendored here so the React app does **not** depend on a public CDN (corporate networks often block CDNs, which caused blank/hung `/presentation` loads).

Source: same file as `https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js` (pin version in lockfile if you upgrade MediaPipe).
