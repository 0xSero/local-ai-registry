#!/bin/sh
# Serve gcoli/Qwen3.8-27B-oQ4e-mtp with oMLX 0.6.4.
# MODEL_DIR is the parent of Qwen3.8-27B-oQ4e-mtp.
# ~/.omlx/model_settings.json must set mtp_enabled for that model, and
# the mtp3 profile must be applied (the only path that preserves
# mtp_num_draft_tokens in oMLX 0.6.4).
set -eu
: "${MODEL_DIR:?MODEL_DIR must contain Qwen3.8-27B-oQ4e-mtp}"
exec omlx serve --model-dir "$MODEL_DIR"
