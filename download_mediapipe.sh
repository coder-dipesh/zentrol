#!/bin/bash

cd static/mediapipe

echo "Downloading MediaPipe files..."

# Download all required files
curl -L -o "hand_landmark_full.tflite" "https://cdn.jsdelivr.net/npm/@mediapipe/hands/hand_landmark_full.tflite"
curl -L -o "hand_landmark_lite.tflite" "https://cdn.jsdelivr.net/npm/@mediapipe/hands/hand_landmark_lite.tflite"
curl -L -o "hands_solution_simd_wasm_bin.js" "https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands_solution_simd_wasm_bin.js"
curl -L -o "hands_solution_simd_wasm_bin.wasm" "https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands_solution_simd_wasm_bin.wasm"
curl -L -o "hands.binarypb" "https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.binarypb"
curl -L -o "hands_solution_packed_assets.data" "https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands_solution_packed_assets.data"

echo "All MediaPipe files downloaded!"
ls -la
