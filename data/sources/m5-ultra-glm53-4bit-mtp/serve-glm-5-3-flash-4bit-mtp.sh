#!/bin/sh
# Serve Vontra/GLM-5.3-Flash-MLX-4bit-MTP with oMLX 0.7.0.dev4.
# MODEL_DIR is the parent of the model directory. MTP is enabled in
# ~/.omlx/model_settings.json for GLM-5.3-Flash-MLX-4bit-MTP.
set -eu
: "${MODEL_DIR:?MODEL_DIR must contain GLM-5.3-Flash-MLX-4bit-MTP}"
exec omlx serve --model-dir "$MODEL_DIR"
