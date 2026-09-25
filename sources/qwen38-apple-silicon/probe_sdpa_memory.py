"""Bounded standalone MLX attention probe; does not load model weights."""
import argparse
import gc
import json
import statistics
import time

import mlx.core as mx


def emit(**record):
    print(json.dumps(record, sort_keys=True), flush=True)


def arrays(q_len, k_len, mask_kind):
    mx.random.seed(381)
    q = mx.random.normal((1, 24, q_len, 256)).astype(mx.bfloat16)
    k = mx.random.normal((1, 4, k_len, 256)).astype(mx.bfloat16)
    v = mx.random.normal((1, 4, k_len, 256)).astype(mx.bfloat16)
    q_pos = mx.arange(k_len - q_len, k_len)[:, None]
    k_pos = mx.arange(k_len)[None, :]
    mask = (q_pos >= k_pos)[None, None, :, :]
    if mask_kind == "left_padding":
        mask = mask & (k_pos >= 17)[None, None, :, :]
    if mask_kind == "additive":
        mask = mx.where(mask, mx.array(0, mx.bfloat16), mx.array(-float("inf"), mx.bfloat16))
    mx.eval(q, k, v, mask)
    mx.synchronize()
    return q, k, v, mask


def run(q_len, k_len, fused, mask_kind):
    q, k, v, mask = arrays(q_len, k_len, mask_kind)
    warm = mx.fast.scaled_dot_product_attention(q, k, v, scale=1 / 16, mask=mask, force_fused=fused)
    mx.eval(warm)
    mx.synchronize()
    del warm
    gc.collect()
    mx.clear_cache()
    mx.reset_peak_memory()
    before = mx.get_active_memory()
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        out = mx.fast.scaled_dot_product_attention(q, k, v, scale=1 / 16, mask=mask, force_fused=fused)
        mx.eval(out)
        mx.synchronize()
        timings.append(time.perf_counter() - started)
    seconds = statistics.median(timings)
    emit(kind="allocation", q=q_len, k=k_len, dtype="bfloat16", heads=24, kv_heads=4, dim=256,
         mask=mask_kind, force_fused=fused, wall_seconds=seconds, baseline_bytes=before,
         peak_bytes=mx.get_peak_memory(), incremental_peak_bytes=mx.get_peak_memory()-before,
         active_bytes=mx.get_active_memory(), finite=bool(mx.all(mx.isfinite(out)).item()))


def parity():
    for q_len, k_len, mask_kind in [(33, 257, "causal"), (33, 257, "left_padding"), (33, 257, "additive"), (128, 769, "causal")]:
        q, k, v, mask = arrays(q_len, k_len, mask_kind)
        normal = mx.fast.scaled_dot_product_attention(q, k, v, scale=1 / 16, mask=mask)
        fused = mx.fast.scaled_dot_product_attention(q, k, v, scale=1 / 16, mask=mask, force_fused=True)
        mx.eval(normal, fused)
        diff = normal.astype(mx.float32) - fused.astype(mx.float32)
        max_abs = float(mx.max(mx.abs(diff)).item())
        rms = float(mx.sqrt(mx.mean(diff * diff)).item())
        relative_rms = rms / float(mx.sqrt(mx.mean(normal.astype(mx.float32) ** 2)).item())
        finite = bool(mx.all(mx.isfinite(fused)).item())
        emit(kind="parity", q=q_len, k=k_len, mask=mask_kind, max_abs=max_abs, rms=rms, relative_rms=relative_rms, finite=finite)
        assert finite and max_abs < 0.02 and relative_rms < 0.03
        del q, k, v, mask, normal, fused, diff
        mx.clear_cache()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--q", type=int, default=1024)
    p.add_argument("--k", type=int, default=8192)
    p.add_argument("--fused", action="store_true")
    p.add_argument("--parity", action="store_true")
    args = p.parse_args()
    assert 1 <= args.q <= 1024 and args.q <= args.k <= 32768
    mx.set_memory_limit(6 * 1024**3)
    mx.set_cache_limit(64 * 1024**2)
    if args.parity:
        parity()
    else:
        run(args.q, args.k, args.fused, "causal")
