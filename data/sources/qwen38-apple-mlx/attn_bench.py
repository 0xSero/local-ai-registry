"""Decode attention cost for one full-attention layer at long context (4 KV heads, 24 query heads, head_dim 256)."""
import time
import mlx.core as mx
from mlx_vlm.models.base import quantized_scaled_dot_product_attention as qsdpa

S, D, KV, QH, L = 166_000, 256, 4, 24, 4  # L = MTP verify block (1 + 3 drafts)
k = mx.random.normal((1, KV, S, D)).astype(mx.bfloat16)
v = mx.random.normal((1, KV, S, D)).astype(mx.bfloat16)
qk, qv = mx.quantize(k, group_size=64, bits=4), mx.quantize(v, group_size=64, bits=4)
q = mx.random.normal((1, QH, L, D)).astype(mx.bfloat16)
mx.eval(k, v, qk, qv, q)
scale = D ** -0.5


def bench(name, fn, n=10):
    mx.eval(fn())
    t = time.perf_counter()
    for _ in range(n):
        mx.eval(fn())
    print(f"{name:42s} {1000 * (time.perf_counter() - t) / n:8.2f} ms/layer")


bench("mlx-vlm quantized SDPA (current decode)", lambda: qsdpa(q, qk, qv, scale=scale, mask=None, group_size=64, bits=4))
qr = (q * scale).reshape(1, KV, QH // KV, L, D)
ek = tuple(mx.expand_dims(x, -3) for x in qk)
ev = tuple(mx.expand_dims(x, -3) for x in qv)
bench("  Q·Kᵀ quantized_matmul (transpose=True)", lambda: mx.quantized_matmul(qr, *ek, transpose=True, group_size=64, bits=4))
scores = mx.softmax(mx.quantized_matmul(qr, *ek, transpose=True, group_size=64, bits=4), axis=-1, precise=True)
mx.eval(scores)
bench("  P·V quantized_matmul (transpose=False)", lambda: mx.quantized_matmul(scores, *ev, transpose=False, group_size=64, bits=4))
bench("dequantize K,V + fused SDPA", lambda: mx.fast.scaled_dot_product_attention(
    q, mx.dequantize(*qk, group_size=64, bits=4), mx.dequantize(*qv, group_size=64, bits=4), scale=scale))
bench("bf16 fused SDPA (unquantized cache)", lambda: mx.fast.scaled_dot_product_attention(q, k, v, scale=scale))
