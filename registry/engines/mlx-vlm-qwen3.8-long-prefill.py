"""mlx_vlm.server for Qwen3.8-27B with two long-prefill memory fixes (mlx-vlm 0.7.3).

Usage: python3 qwen38_mlx_serve.py <mlx_vlm.server arguments>

1. Fused prefill attention. Qwen3.8's full-attention layers use head_dim 256, for which MLX
   picks its unfused SDPA during prefill, and mlx-vlm's quantized-KV path always computes
   Q·Kᵀ with quantized_matmul. Both materialise a chunk × context score matrix. Prefill
   chunks (more than 8 query tokens) dequantize the layer's keys/values and run MLX's fused
   kernel with force_fused; decode keeps the quantized path.
2. Segmented prompt embeddings. The full-prompt inputs_embeds (200k x 5120 x bf16 ≈ 2 GB)
   stays resident through prefill: the request kwargs keep a reference and prompt_step's
   `[:, n:]` views keep the buffer alive until the KV cache peaks. The batch takes sole
   ownership and holds it as 8192-token segments that are freed as prefill consumes them.

It also serves POST /v1/token/encode ({"text"} -> {"tokens", "length"}) from the model's own tokenizer, which
lab.py uses to count decoded tokens; lists only the served model on /v1/models (mlx-vlm lists every model in the
Hugging Face cache, and a client that picks the first one makes the server swap models); and applies the model's generation_config sampling (temperature, top_k,
top_p) to requests that leave those fields out, as vLLM and SGLang do by default. mlx-vlm otherwise samples with
top_k 0 and top_p 1.0, and at temperature 0.6 a long thinking answer drifts off the prompt. Both patches fail
loudly (assert) if mlx-vlm's internals no longer match.
"""

import json
import sys
from pathlib import Path

import mlx.core as mx
from mlx_vlm.generate import ar
from mlx_vlm.models import base

PREFILL_MIN_QUERY_TOKENS = 8
HEAD_DIM = 256
SEGMENT_TOKENS = 8192

_quantized_sdpa = base.quantized_scaled_dot_product_attention
_fast_sdpa = mx.fast.scaled_dot_product_attention


def fused_fast_sdpa(q, k, v, **kwargs):
    if q.shape[-2] > PREFILL_MIN_QUERY_TOKENS and q.shape[-1] == HEAD_DIM and kwargs.get("sinks") is None:
        kwargs["force_fused"] = True
    return _fast_sdpa(q, k, v, **kwargs)


def fused_prefill_quantized_sdpa(queries, q_keys, q_values, scale, mask, group_size=64, bits=8):
    if queries.shape[-2] <= PREFILL_MIN_QUERY_TOKENS:
        return _quantized_sdpa(queries, q_keys, q_values, scale=scale, mask=mask, group_size=group_size, bits=bits)
    keys = mx.dequantize(*q_keys, group_size=group_size, bits=bits).astype(queries.dtype)
    values = mx.dequantize(*q_values, group_size=group_size, bits=bits).astype(queries.dtype)
    return mx.fast.scaled_dot_product_attention(queries, keys, values, scale=scale, mask=mask)


class SegmentedEmbeds:
    """Only what PromptProcessingBatch does to `_inputs_embeds`: `.shape`, `[:, :n]`, `[:, n:]`."""

    def __init__(self, embeds):
        self.segments = [mx.contiguous(embeds[:, i:i + SEGMENT_TOKENS]) for i in range(0, embeds.shape[1], SEGMENT_TOKENS)]
        mx.eval(self.segments)
        self.dtype, self.ndim = embeds.dtype, embeds.ndim

    @property
    def shape(self):
        first = self.segments[0].shape
        return (first[0], sum(segment.shape[1] for segment in self.segments), first[2])

    def __getitem__(self, key):
        rows, cols = key
        assert rows == slice(None) and cols.step is None
        if cols.start is None:
            parts, need = [], cols.stop
            for segment in self.segments:
                parts.append(segment[:, :need])
                need -= parts[-1].shape[1]
                if need <= 0:
                    break
            return parts[0] if len(parts) == 1 else mx.concatenate(parts, axis=1)
        drop = cols.start
        while self.segments and drop >= self.segments[0].shape[1]:
            drop -= self.segments.pop(0).shape[1]
        if drop:
            self.segments[0] = self.segments[0][:, drop:]
        # The last segment goes back as a plain array for the final generate() call.
        return self.segments[0] if len(self.segments) == 1 else self


def install():
    assert hasattr(base, "quantized_scaled_dot_product_attention") and hasattr(ar, "_merge_prefill_prompt_kwargs")
    base.quantized_scaled_dot_product_attention = fused_prefill_quantized_sdpa
    mx.fast.scaled_dot_product_attention = fused_fast_sdpa

    merge = ar._merge_prefill_prompt_kwargs

    def merge_and_release(prompt_kwargs_list, input_ids):
        inputs_embeds, merged = merge(prompt_kwargs_list, input_ids)
        for kwargs in prompt_kwargs_list:
            if kwargs:
                kwargs.pop("inputs_embeds", None)
        return inputs_embeds, merged

    ar._merge_prefill_prompt_kwargs = merge_and_release
    init = ar.PromptProcessingBatch.__init__

    def init_segmented(self, *args, **kwargs):
        init(self, *args, **kwargs)
        embeds = self._inputs_embeds
        if embeds is not None and self.prefill_step_size and embeds.shape[1] > 2 * SEGMENT_TOKENS:
            self._inputs_embeds = SegmentedEmbeds(embeds)

    ar.PromptProcessingBatch.__init__ = init_segmented


class ServedModelOnly:
    """ASGI middleware: GET /v1/models lists the served model only."""

    def __init__(self, app, model_id):
        self.app = app
        self.body = json.dumps({"object": "list", "data": [{"id": model_id, "object": "model", "owned_by": "local"}]}).encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "GET" or scope["path"] not in ("/v1/models", "/models"):
            return await self.app(scope, receive, send)
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(self.body)).encode())]})
        await send({"type": "http.response.body", "body": self.body})


def add_lab_routes(model_path):
    from mlx_vlm.server import app
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    app.add_middleware(ServedModelOnly, model_id=model_path)

    @app.post("/v1/token/encode")
    async def encode(body: dict):
        ids = tokenizer.encode(body.get("text") or "", add_special_tokens=False)
        return {"tokens": ids, "length": len(ids)}


SAMPLING_KEYS = ("temperature", "top_k", "top_p")
GENERATION_PATHS = {"/v1/chat/completions", "/chat/completions", "/v1/responses", "/responses", "/v1/messages", "/messages"}


class SamplingDefaults:
    """ASGI middleware: fill in the model's sampling settings a request body leaves out; never override one it sets."""

    def __init__(self, app, defaults):
        self.app, self.defaults = app, defaults

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in GENERATION_PATHS:
            return await self.app(scope, receive, send)
        body, more = b"", True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                body = json.dumps({**self.defaults, **data}).encode()
        except ValueError:
            pass
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        headers = [(k, v) for k, v in scope["headers"] if k != b"content-length"] + [(b"content-length", str(len(body)).encode())]
        return await self.app({**scope, "headers": headers}, replay, send)


def add_sampling_defaults(model_path):
    config = Path(model_path) / "generation_config.json"
    defaults = {k: v for k, v in json.loads(config.read_text()).items() if k in SAMPLING_KEYS} if config.exists() else {}
    if defaults:
        from mlx_vlm.server import app

        app.add_middleware(SamplingDefaults, defaults=defaults)


if __name__ == "__main__":
    install()
    model_path = sys.argv[sys.argv.index("--model") + 1]
    add_lab_routes(model_path)
    add_sampling_defaults(model_path)
    from mlx_vlm.server.cli import main

    sys.argv[0] = "mlx_vlm.server"
    main()
