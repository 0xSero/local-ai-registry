#!/bin/sh
# Serve Jundot/Qwen3.8-27B-oQ4e-mtp with oMLX 0.7.0.dev4.
# MODEL_DIR is the parent of Qwen3.8-27B-oQ4e-mtp.
# ~/.omlx/model_settings.json must set mtp_enabled for that model.
set -eu
: "${MODEL_DIR:?MODEL_DIR must contain Qwen3.8-27B-oQ4e-mtp}"
exec omlx serve --model-dir "$MODEL_DIR"
