# MTP campaign: every NVIDIA recipe on multi-token prediction, one recommendation per card

You are a long-running autonomous agent. Carry this to completion over hours. Log every step you take and
every result to `MTP-CAMPAIGN.log` in this directory (append, timestamped), commit progress often on the
branch named below, and when done write the final report into this file under "## Result

Written 2026-09-28. Branch `mtp-campaign`, 44 commits on top of `de896528`, head `5f7e5adf` (not pushed, no PR
opened: Sero asked for local commits only). Log: `MTP-CAMPAIGN.log` (562 lines, every step timestamped).
Diagnostics: `evidence/mtp-campaign-2026-09-22/` (manifest lists what each file proves). Acceptance evidence
for each recipe is its own `registry/speed-sweep/<recipe-id>-acceptance.json`.

Vast: **54 instances rented**, every one destroyed. Their own per-instance cost lines sum to **$3.30** of
compute. The account's spendable funds went from $45.65 when renting started to $10.28 at closeout, but that
$35 delta is not this campaign's bill: other sessions were renting on the same account throughout
(`omp-vastsweep-*`, `local-ai-lab-*`), and Vast charges bandwidth and storage on top of the hourly rate, which
this campaign incurred heavily by re-downloading 7 GB (Qwen3.5-9B) to 58 GB (Flash-Next) of weights on every
run. `vastai show instances` at closeout holds only a foreign exited GB10 and another session's
`local-ai-lab-rtx-4070-ti-super-16gb`; the two orphans the watchdog flagged (52200590, 52200711) are gone.

### 1. One recommendation per card

The tier map in `scripts/recommend.py` is now 16 GB and up → `qwen3-8-27b`, 12 GB → `qwen3-5-9b`, below that
the best that fits (`lfm2-5-2-6b`); a vision-capable recipe also outranks a blind one at the same engine.
Every one of the 37 cards that had a recommendation before the campaign still has exactly one, none has two,
and the rule now holds without exception on all 33 NVIDIA cards that carry a recommendation: **18 of 18** at
16 GB or more serve Qwen3.8-27B (17 of those with vision), **6 of 6** at 12 GB serve Qwen3.5-9B, and **9 of 9**
below that serve LFM2.5-2.6B.

| VRAM | cards | recommended model | context | vision |
|---|---|---|---|---|
| 96 GB | RTX PRO 6000 | Qwen3.8-27B NVFP4 (SGLang, NEXTN) | 128K | no |
| 48 GB | RTX 6000 Ada, A6000 | Qwen3.8-27B EXL3 SC5bpw-H6-V6 | 256K | yes |
| 32 GB | RTX 5090, PRO 4500 | Qwen3.8-27B EXL3 SC5bpw-H6-V6 | 256K | yes |
| 24 GB | 3090, 3090 Ti, 4090, PRO 4000 | Qwen3.8-27B EXL3 SC4bpw-H5 | 256K | yes |
| 20 GB | RTX 4000 Ada | Qwen3.8-27B EXL3 SC4bpw-H5 | 128K | yes |
| 16 GB | 2000 Ada, 4060 Ti, 4070 Ti S, 4080, 4080 S, 5060 Ti, 5070 Ti, 5080 | Qwen3.8-27B EXL3 SC3bpw-H4-V4 | 128K | yes |
| 12 GB | 3060, 3080 Ti, 4070, 4070 S, 4070 Ti, 5070 | Qwen3.5-9B EXL3 4bpw | 128K | no |
| 8–10 GB | 3060 Ti, 3070, 3070 Ti, 3080 10 GB, 4060, 4060 laptop, 4060 Ti, 5060, 5060 Ti | LFM2.5-2.6B | 128K | no |

The RTX PRO 6000 is the one 16 GB+ card without vision: its NVFP4 SGLang recipe outranks EXL3 on engine
order. Plugin catalogs: `plugin/recipes.json` 37 hardware ids, `plugin/v2/recipes.json`
36 hardware ids and 94 recipes.

### 2. The image

`ghcr.io/0xsero/tabbyapi-exl3@sha256:0f83e6198dc3be2561652d8df2525a7d1a69733e12fc8e25cbc5bc319a8a3ad1`
(tag `v2`), rebuilt on upstream `tabbyapi:cu13@sha256:9d4696ef…` which is built from tabbyAPI `f07131cd`
and pins ExLlamaV3 **1.5.1** (the previous base shipped 1.4.2, below the 1.4.6 that `draft_mode: mtp` needs).
Built by the repo's own `release-image` workflow, run
[35754016842](https://github.com/0xSero/local-ai-images/actions/runs/35754016842);
`gh attestation verify oci://… -o 0xSero` exits 0 with a SLSA v1 provenance naming that workflow and ref.
Source change: `0xSero/local-ai-images` PR **#3**, branch `mtp/tabbyapi-exl3-1.5.1`, left open for review.
CUDA floor unchanged at `cuda>=13.2`, which is what limited the rentals below.

### 3. Accepted, with measured tok/s

37 recipes were accepted on their exact card (37 distinct ids across 37 `ACCEPTED` log lines). Numbers are
the acceptance harness's single-stream decode at ~256 prompt tokens, median of 3 samples. Campaign recipes now
stand at 40: 38 validated, 2 candidates.

**Same recipe, MTP off → on.** Both numbers come from `acceptance-run` sweeps, so they compare directly.
Median gain **+57%** over 19 recipes.

| card | recipe | ctx | before | after | change |
|---|---|---|---|---|---|
| RTX 5070 Ti | qwen359b-exl3-4bpw-rtx5070ti-tabbyapi-tp1 | 256K | 55.5 | 171.5 | +209% |
| RTX A6000 | qwen3827b-exl3-4bpw-rtxa6000-tabbyapi-tp1 | 256K | 36.7 | 63.5 | +73% |
| RTX PRO 4500 | qwen3827b-exl3-4bpw-rtxpro4500-tabbyapi-tp1 | 256K | 45.0 | 77.2 | +72% |
| RTX 3060 | qwen359b-exl3-4bpw-rtx3060-tabbyapi-tp1 | 128K | 48.0 | 81.0 | +69% |
| RTX 5090 | qwen3827b-exl3-4bpw-rtx5090-tabbyapi-tp1 | 256K | 73.7 | 123.7 | +68% |
| RTX 6000 Ada | qwen3827b-exl3-4bpw-rtx6000ada-tabbyapi-tp1 | 256K | 49.5 | 81.7 | +65% |
| RTX 4080 | qwen359b-exl3-4bpw-rtx4080-tabbyapi-tp1 | 256K | 96.9 | 159.9 | +65% |
| RTX 4090 | qwen3827b-exl3-4bpw-rtx4090-tabbyapi-tp1 | 128K | 52.7 | 85.6 | +62% |
| RTX 5070 | qwen359b-exl3-4bpw-rtx5070-tabbyapi-tp1 | 128K | 91.1 | 146.1 | +60% |
| RTX 5060 Ti | qwen359b-exl3-4bpw-rtx5060ti-tabbyapi-tp1 | 256K | 69.1 | 108.2 | +57% |
| RTX 4080 Super | qwen359b-exl3-4bpw-rtx4080super-tabbyapi-tp1 | 256K | 100.8 | 154.9 | +54% |
| RTX 3090 Ti | qwen3827b-exl3-4bpw-rtx3090ti-tabbyapi-tp1 | 128K | 46.4 | 69.3 | +49% |
| RTX 4000 Ada | qwen359b-exl3-4bpw-rtx4000ada-tabbyapi-tp1 | 256K | 60.2 | 89.9 | +49% |
| RTX 5080 | qwen359b-exl3-4bpw-rtx5080-tabbyapi-tp1 | 256K | 124.3 | 179.4 | +44% |
| RTX 3080 Ti | qwen359b-exl3-4bpw-rtx3080ti-tabbyapi-tp1 | 128K | 89.4 | 128.4 | +44% |
| RTX 4070 | qwen359b-exl3-4bpw-rtx4070-tabbyapi-tp1 | 128K | 83.0 | 118.1 | +42% |
| RTX 4060 Ti | qwen359b-exl3-4bpw-rtx4060ti-tabbyapi-tp1 | 256K | 56.0 | 76.8 | +37% |
| RTX 4070 Ti Super | qwen359b-exl3-4bpw-rtx4070tisuper-tabbyapi-tp1 | 256K | 106.0 | 145.3 | +37% |
| RTX 4070 Ti | qwen359b-exl3-4bpw-rtx4070ti-tabbyapi-tp1 | 128K | 81.7 | 102.7 | +26% |

**New recipes**, so there is no before. All are Qwen3.8-27B EXL3 with vision, MTP and full KV, and all are
now their card's recommendation:

| card | recipe | ctx | tok/s |
|---|---|---|---|
| RTX 3090 Ti | qwen3827b-exl3-sc4bpw-rtx3090ti-tabbyapi-tp1 | 256K | 67.2 |
| RTX 4000 Ada | qwen3827b-exl3-sc4bpw-rtx4000ada-tabbyapi-tp1 | 128K | 37.4 |
| RTX 4060 Ti | qwen3827b-exl3-sc3bpw-v4-rtx4060ti-tabbyapi-tp1 | 128K | 38.2 |
| RTX 4070 Ti Super | qwen3827b-exl3-sc3bpw-v4-rtx4070tisuper-tabbyapi-tp1 | 128K | 62.9 |
| RTX 4080 | qwen3827b-exl3-sc3bpw-v4-rtx4080-tabbyapi-tp1 | 128K | 56.6 |
| RTX 4080 Super | qwen3827b-exl3-sc3bpw-v4-rtx4080super-tabbyapi-tp1 | 128K | 77.4 |
| RTX 5060 Ti | qwen3827b-exl3-sc3bpw-v4-rtx5060ti-tabbyapi-tp1 | 128K | 39.1 |
| RTX 5070 Ti | qwen3827b-exl3-sc3bpw-v4-rtx5070ti-tabbyapi-tp1 | 128K | 76.2 |
| RTX 5080 | qwen3827b-exl3-sc3bpw-v4-rtx5080-tabbyapi-tp1 | 128K | 77.6 |
| RTX 5090 | qwen3827b-exl3-sc5bpw-v6-rtx5090-tabbyapi-tp1 | 256K | 117.0 |
| RTX 6000 Ada | qwen3827b-exl3-sc5bpw-v6-rtx6000ada-tabbyapi-tp1 | 256K | 71.1 |
| RTX A6000 | qwen3827b-exl3-sc5bpw-v6-rtxa6000-tabbyapi-tp1 | 256K | 58.1 |

**Already had MTP**, re-accepted on the rebuilt image. Their old numbers are peaks from a `tabby_sweep.py`
campaign sweep across concurrency 1/2/4, not single-stream acceptance decode, so **the two columns are not
comparable and no speedup is claimed for these four**:

| card | recipe | old campaign-sweep peak | new acceptance decode |
|---|---|---|---|
| RTX 3090 | qwen3827b-exl3-sc4bpw-rtx3090-tabbyapi-tp1 | 41.9 | 68.9 |
| RTX 4090 | qwen3827b-exl3-sc4bpw-rtx4090-tabbyapi-tp1 | 89.4 | 85.6 |
| RTX PRO 4000 | qwen3827b-exl3-sc4bpw-rtxpro4000-tabbyapi-tp1 | 76.9 | 57.4 |
| RTX PRO 4500 | qwen3827b-exl3-sc5bpw-v6-rtxpro4500-tabbyapi-tp1 | 95.4 | 64.5 |

**No prior sweep**: `qwen3827b-exl3-4bpw-rtx3090-tabbyapi-tp1` 58.5 tok/s (was a candidate before) and
`qwen38-27b-nvfp4-rtxpro6000-sglang-tp1` 88.2 tok/s with `--speculative-algo NEXTN` (first acceptance run on
that recipe; its previous evidence was an imported sweep).

### 4. Findings worth keeping

- **The stock Qwen3.5-9B EXL3 quant has no MTP head.** `turboderp/Qwen3.5-9B-exl3` omits the 39 `mtp.*`
  tensors on every branch (2.00–6.00bpw, checked by reading the safetensors headers), so TabbyAPI with
  `draft_mode: mtp` dies with `Required tensor mtp.pre_fc_norm_hidden.weight not found`. The 16 Qwen3.5-9B
  recipes now pin `TheMelonGod/Qwen3.5-9B-exl3` branch `6hb-4.0bpw` (`e98453aa`, 6.83 GB, 4 bpw with a 6-bit
  head, 1402 tensors including the 39 `mtp.*`). `Ppeerapon/Qwen3.5-9B-EXL3-4.0bpw` carries the head too.
  Qwen3.8-27B needed no such change: `turboderp/Qwen3.8-27B-exl3` ships the head on every branch.
- **vLLM cannot fit an MTP draft next to these models on a 24 GB card** (v0.27.1). The flags are accepted
  (`Overriding draft model max model len…`) but Qwen3.8-27B-AWQ-INT4 OOMs allocating the draft's 2.37 GiB
  vocab embedding, and Qwen3.6-35B-A3B-GPTQ leaves 0.61 GiB for a KV cache that needs 1.53 GiB at 128K.
  All four vLLM recipes were restored to their pre-campaign state rather than shipped degraded.
- **Flash-Next does not load on ExLlamaV3 1.5.1** at the settings that worked on 1.5.0: same config, same
  32 GB card, `RuntimeError: Insufficient VRAM in split for model and cache`. Recipe left on the upstream image.
- **A campaign that re-validates recipes must guard the recommendation set.** Demoting a card's only
  validated recipe silently drops that card from the plugin catalog. Comparing the recommended set against
  the base commit caught the RTX 4070 SUPER falling out; see Blocked.
- **`accept_recipe.py` reuses `<recipe>-acceptance` as the sweep id**, so re-validating a recipe overwrites
  its own before-MTP evidence. `evidence/mtp-campaign-2026-09-22/mtp_report.py` reads the old numbers from
  commit `de896528` for that reason.

### 5. Failed runs (all resolved or reverted, nothing left running)

| recipe | what happened | cost | evidence |
|---|---|---|---|
| qwen3827b-exl3-sc4bpw-rtx3090 | two hosts stalled pulling image layer `19ecffd1183d`; **accepted on retry** at 68.9 tok/s | $0.04 | `run-logs/…rtx3090….1790111276.log` |
| qwen359b-exl3-4bpw-rtx5060ti | host had no DNS, `huggingface_hub` could not resolve; **accepted on retry** at 108.2 tok/s | $0.17 | `run-logs/…rtx5060ti….1790112756.log` |
| qwen38flashnext (×3) | 58.5 GB of weights on a 50 GB disk, then two health timeouts, then the VRAM split error | $0.60 | `engine-logs/flashnext-container.log` |
| qwen38-awq-int4-rtx4090-vllm | host docker daemon rejected the container (`Minimum memory limit…`) | $0.16 | `run-logs/…rtx4090-vllm….log` |
| qwen38-awq-int4-rtx3090ti-vllm | MTP draft OOM loop until the 3600 s health timeout | $0.26 | `run-logs/…rtx3090ti-vllm….log` |
| qwen38-awq-int4-rtx3090-vllm | same OOM, stopped by hand once the cause was read from the container | $0.07 | `engine-logs/vllm-3090-container.log` |
| qwen36-gptq-int4-rtx3090-vllm (×2) | KV cache squeeze; the manual re-run mirrored the log before the box died | $0.09 | `engine-logs/vllm-qwen36-3090-container.log` |

Two incidents of my own making, both fixed in `evidence/mtp-campaign-2026-09-22/mtp_runner.py`: a duplicate
runner pair rented two extra boxes for ~2 minutes ($0.01), and a queue's cleanup destroyed another queue's
live instance twice because it matched every `local-ai-validate-*` label. Cleanup now matches only the recipe
the runner is running, and a pidfile refuses duplicate starts. One deviation from the brief: the RTX PRO 6000
run rented at $1.99/h, above the $1/h ceiling, because `validate_rented.py` had no price filter;
`--vast-max-price` (default $1/h) was added in `395631b4` and every later run inherited it.

### 6. Blocked

- **RTX 2000 Ada, Qwen3.8-27B on the new image.** Zero verified Vast offers for the card in 8 retry passes
  and at closeout. Its pre-campaign recipe (`qwen3827b-exl3-sc3bpw-v4-rtx2000ada-tabbyapi-tp1`, validated
  2026-09-19 on upstream `tabbyapi:cu13@1c13dd`, `draft_mode: mtp` already on) was restored verbatim, so the
  card does get Qwen3.8-27B with vision and MTP at 128K — just on the upstream image, not the attested one.
- **RTX 4070 SUPER, Qwen3.5-9B with MTP.** No offer in 8 passes. Restored to its pre-campaign validated
  recipe (82.0 tok/s, no MTP) with its config frozen as
  `qwen359b-exl3-4bpw-128k-q4-nomtp-tabbyapi-config`, because the shared config now carries MTP and the
  TheMelonGod quant. Without this the card would have dropped out of the plugin catalog.
- **RTX 3080 12 GB and RTX 2000 Ada, Qwen3.5-9B.** Still candidates, as they were before the campaign. Every
  RTX 3080 offer on Vast is the 10 GB variant, so the 12 GB recipe cannot be placed there at all.
- **Why the small cards cannot be rented.** The attested image requires `cuda>=13.2`. At closeout the only
  RTX 4070 SUPER offers ran CUDA 13.0 drivers (and 80 Mbps links), so nvidia-container would refuse the
  image. `local-ai-images` already contains `tabbyapi-exl3-cu12/` (a CUDA 12.8 base) built for exactly this
  problem; building and attesting it, then adding cu12 variants of these recipes, is the way to finish these
  three cards without waiting for a 13.2 host to appear. That is a new image and new recipes, so it is
  outside this campaign's scope and left for Sero to decide.
- **vLLM MTP on 24 GB cards and Flash-Next on 1.5.1**: see Findings; both need an upstream fix or a smaller
  cache, not another rental.

### 7. What Sero still has to do

1. Review `0xSero/local-ai-images` PR #3 (the image rebuild) and merge it if the base bump is acceptable.
2. Review this branch and open the PR yourself, or tell me to: nothing is pushed. Note `origin/main` has
   moved a long way since `de896528` (306 commits by other sessions, and its history looks rewritten), so a
   rebase will be needed before any PR.
3. Decide on the cu12 image path for the RTX 2000 Ada / 4070 SUPER / 3080 12 GB.
4. The plugin sync is **deliberately not committed**. Running
   `make sync REGISTRY=$PWD/../registry-v6 REGISTRY_REF=mtp-campaign` on branch `v6` does apply cleanly, but it
   takes the vendored catalog from 38 card kinds down to 36: this branch predates `rx-7600-xt-16gb` and
   `rx-9070-xt-16gb`, which reached `origin/main` while the campaign was running. Syncing now would delete two
   AMD cards from the plugin. Rebase this branch on current `origin/main` first, re-run
   `python3 scripts/export_plugin_v2.py --out plugin/v2/recipes.json`, then sync. The plugin working tree was
   left untouched at 38 card kinds.
