# blackwell-forge ledger excerpt (pop-os, 2026-09-25/26)

The rows of the owner's tuning ledger (`bench.py`, one JSON object per cell) for the experiments behind the three 4x RTX PRO 6000 recipes promoted on 2026-09-26. Host paths and boot-log excerpts were removed; nothing else was changed.

| model | experiments | what each one is |
|---|---|---|
| glm-5.3-flash | K5-flash-seqs48, K8-flash-cap-32-128 | 48 sequences; CUDA graph sizes 1 2 4 8 16 32 128 192 (the production config) |
| glm-5.3 | F1-glm53-freeze, G1-glm53-psi2 | the F1 freeze; F1 plus --prefill-schedule-interval 2 (the production config) |
| deepseek-v4.1-flash | D1-ds41-kvbytes105, D3-ds41-dspark-k5, D4-ds41-seqs32, D5-ds41-csweep | KV bytes pinned; DSpark K5; 32 sequences; the production config swept C2-C32 |

Owner's blackwell-forge bench (bench.py) on pop-os, 4x RTX PRO 6000 Blackwell Workstation at 275 W, no P2P override. Decode: C EOS-respected streams on cold unique prompts, temperature 1.0, top_p 0.95, thinking off, no max_tokens, aggregate tok/s over a 30 s window after every stream has its first token. Prefill: unique cold ~32K-token document, input tokens / client TTFT. Smoke: 17 x 23 = 391 and a tool call. Rows are the ledger rows in data/sources/pop-os/2026-09-26-blackwell-forge/ledger.jsonl.
