# Lane campaign evidence

Measured ollama probe runs from the registry lane campaign
(Ampere, Ada, Blackwell lanes). Raw counters and audit notes live in
this repository's history; skips below are honest capacity or probe failures.

## Honest skips (9)

- `rtx3060ti` / `qwen3.8-27b`: skip: weights 17408MB vs 8192MB VRAM (<12GB host)
- `rtx3060ti` / `qwen3.6-35b-a3b`: skip: weights 23552MB vs 8192MB VRAM (<12GB host)
- `rtx3070` / `qwen3.8-27b`: skip: weights 17408MB vs 8192MB VRAM (<12GB host)
- `rtx3070` / `qwen3.6-35b-a3b`: skip: weights 23552MB vs 8192MB VRAM (<12GB host)
- `rtx3080` / `qwen3.8-27b`: skip: weights 17408MB vs 10240MB VRAM (<12GB host)
- `rtx3080` / `qwen3.6-35b-a3b`: skip: weights 23552MB vs 10240MB VRAM (<12GB host)
- `rtx5070` / `qwen3.8-27b`: weights 17GB > usable VRAM ~10GB (12227MiB total minus ~2GB headroom)
- `rtx5070` / `qwen3.6-35b-a3b`: weights 23GB > usable VRAM ~10GB (12227MiB total minus ~2GB headroom)
- `rtx5060` / `ALL`: blocked: 7 rental attempts failed
