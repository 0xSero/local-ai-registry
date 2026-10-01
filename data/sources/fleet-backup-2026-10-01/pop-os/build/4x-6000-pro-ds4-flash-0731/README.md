# DeepSeek-V4-Flash-0731 exact Docker deployment

This repository is a reproducible, controller-owned deployment for four RTX PRO 6000 Blackwell GPUs. It locks the runtime image, model revision, server command, environment, GPU ordering, mounts, and Local Studio recipe.

The model files are mounted read-only and are not committed or baked into Docker. The deployment expects the verified 48-shard checkpoint to already be present locally.

## Standup

Create a local `.env` from `.env.example`, set the checkpoint and cache paths, then run:

```bash
./up
```

Or pass the required values directly in one command:

```bash
MODEL_DIR=/path/to/DeepSeek-V4-Flash-0731 CACHE_DIR=/path/to/writable-cache ./up
```

`./up` validates the checkpoint, discovers the four local GPU UUIDs, builds the locked image, updates the `deepseek-v4-flash` Local Studio recipe to point to this checked-out Compose file, and launches only when the controller is not already serving DeepSeek. It refuses to evict another active model.

If DeepSeek is already healthy, the script validates the bundle/recipe and exits without restarting it.

## Locked deployment

| Surface | Value |
|---|---|
| Served model ID | `DeepSeek-V4-Flash-0731` |
| Model revision | `7872f01b1d1fe23eabc4c98b48bffcef5a386062` |
| Runtime base | `voipmonitor/vllm@sha256:937db99d072fe089be6d9d88c356e5e2540243389bc7669ecf57a102f637c15e` |
| Context | 1,048,576 tokens |
| TP / DCP | 4 / 1 |
| KV cache | `fp8_ds_mla` |
| MoE backend | `b12x` |
| Speculation | DSpark, five drafts, probabilistic sampling |
| Tool/reasoning parsers | `deepseek_v4` / `deepseek_v4` |
| API bind | loopback port 8000 |

The exact Compose command retains CUDA graphs (full, piecewise, and DSpark capture). It intentionally does not enable eager mode or disable CUDA graphs.

## Prerequisites

- Docker Compose with NVIDIA GPU access
- Local Studio controller running on this host, configured to allow custom launch commands
- `jq`, `curl`, `pgrep`, and Tailscale CLI (the latter is used to discover a controller bound to the tailnet address)
- A local DeepSeek-V4-Flash-0731 checkpoint with all 48 model shards

The local `.env` is ignored by Git. Use `.env.example` as the starting point:

```bash
MODEL_DIR=/path/to/model
CACHE_DIR=/path/to/writable-cache
# NVIDIA_VISIBLE_DEVICES is optional; ./up discovers all four GPU UUIDs by default.
```

The script takes the Local Studio API key from `LOCAL_STUDIO_API_KEY`, if supplied, otherwise from the already-running controller process owned by the current user. It never writes or prints that key.

## Files

- `Dockerfile` — pinned runtime image plus every vLLM argument and process environment setting.
- `compose.yaml` — GPU, IPC, shared-memory, model/cache mounts, and loopback port binding.
- `recipe.template.json` — Local Studio’s controller recipe, filled at runtime with the checked-out Compose path.
- `up` — idempotent build, recipe promotion, and controller-managed launch.

No host paths, GPU UUIDs, controller keys, or credentials are stored in this repository. Keep `.env` local.
