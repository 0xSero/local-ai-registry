# MTP campaign: every NVIDIA recipe on multi-token prediction, one recommendation per card

You are a long-running autonomous agent. Carry this to completion over hours. Log every step you take and
every result to `MTP-CAMPAIGN.log` in this directory (append, timestamped), commit progress often on the
branch named below, and when done write the final report into this file under "## Result".

## Goal (from Sero, 2026-09-22)

1. One recommendation per card: 16 GB and up → Qwen3.8-27B EXL3 with vision and full KV (128K on 16 GB,
   256K from 24 GB); 12 GB → Qwen3.5-9B EXL3; 8–10 GB → the best that fits (LFM2.5 today). EXL3 on TabbyAPI
   preferred; llama.cpp only where EXL3 cannot run (Intel B70, AMD).
2. Every recipe whose model has an MTP head uses it: Qwen3.8-27B, Qwen3.5-9B, Qwen3.6-35B, Qwen3.8-Flash-Next,
   GLM-5.3-Flash. Gemma-4, LFM2.5, Ornith, Bonsai have no head: leave them.
3. Validate every changed or new recipe on the exact rented card, accept, re-export schema 2, sync the plugin.

## Repositories (all local)

- Registry worktree: this directory, `~/local-omarchy/registry-v6`. Create branch `mtp-campaign` from
  `origin/main` first (`git fetch origin && git checkout -b mtp-campaign origin/main`). Never edit
  `~/local-omarchy/local-ai-registry` (someone else's checkout).
- Images: `~/local-omarchy/local-ai-images` (attested images, GitHub workflow builds them; `tabbyapi-exl3/`).
- Plugin: `~/local-omarchy/omarchy-local-ai`, branch `v6`; `make sync REGISTRY=~/local-omarchy/registry-v6`
  takes `plugin/v2/recipes.json`. Do not push the plugin's `main`.
- Context worth reading first: `~/.claude/skills/omarchy-local-ai/SKILL.md` (traps), the memory notes in
  `~/.claude/projects/-Users-sero-local-omarchy/memory/` (gpu-rental-accounts, local-ai-images-repo,
  local-ai-v6-handoff), `scripts/recommend.py`, `scripts/export_plugin_v2.py`, `scripts/validate_rented.py`,
  `scripts/accept_recipe.py`, `CONTRIBUTING.md`, and how a recipe record and its config asset look under
  `registry/recipe/` and `registry/asset/`.

## How each engine turns MTP on (verified 2026-09-22)

- TabbyAPI: in the recipe's config asset, `draft_model: { draft_mode: mtp }`. Needs exllamav3 ≥ 1.4.6; our
  attested image `ghcr.io/0xsero/tabbyapi-exl3` ships 1.4.2, so rebuild it on exllamav3 1.5.1 with current
  TabbyAPI, through the repo's own workflow (attestation), and pin the new digest in every TabbyAPI recipe.
  Also fix the `ghcr.io/theroyallab/tabbyapi:cu13` recipes onto the attested image.
- vLLM: `--speculative-config '{"method":"mtp","num_speculative_tokens":1}'` (one token; more crashes on FP8).
- SGLang: `--speculative-algo NEXTN --speculative-num-steps 3 --speculative-eagle-topk 1 --speculative-num-draft-tokens 4`;
  no adaptive speculation (open bug on hybrid GDN layers).
- llama.cpp: no MTP for these models upstream. Leave those recipes as they are.

## Steps

1. Image: rebuild `tabbyapi-exl3` on exllamav3 1.5.1 in `local-ai-images` (PR, wait for the workflow, verify
   the attestation with `gh attestation verify oci://<image>@<digest> -o 0xSero`), record the digest.
2. Registry, branch `mtp-campaign`: change `TIERS` in `scripts/recommend.py` to the rule above; add `draft_mode: mtp`
   to every TabbyAPI config asset for MTP-capable models; add the vLLM and SGLang flags to their recipes;
   for the 16 GB cards without a Qwen3.8-27B recipe, create recipes from `qwen3827b-exl3-sc3bpw-v4-rtx2000ada-tabbyapi-tp1`
   (turboderp sc3bpw, 12.1 GB, vision, 128K); for the RTX 4000 Ada 20 GB from the sc4bpw 128K recipe; every
   touched recipe becomes a candidate (status), never "validated" by hand. Run the registry's own checks
   (`npm test`, `python3 scripts/format_registry.py --check`, `check_plugin_gate.py`, `test_export_plugin_v2.py`)
   and commit.
3. Vast: the CLI `vastai` works with the key on this machine. The balance was negative (about -$4) on
   2026-09-22; Sero is topping it up. Poll `vastai show user --raw | jq .balance` every 10 minutes until it is
   above $5, logging each check; do not rent before. Then validate each candidate on its exact card with
   `scripts/validate_rented.py` (read it; it rents the card, runs the recipe's own image and acceptance,
   promotes on success). Only verified, rentable single-GPU offers under $1/h; always destroy the instance
   afterwards, and check `vastai show instances` is empty between runs. Cards and current cheapest offers:
   4060 Ti $0.09, 5060 Ti $0.12, 5070 Ti $0.20, 5080 $0.27, 4080 $0.27, 4080 Super (listed "RTX 4080S"),
   4000 Ada $0.17, 3090 Ti $0.20, 4090, 5090 $0.45, RTX Pro 4000/4500/6000 when offered. 4070 Ti Super had no
   offer; retry hourly, and record it as pending if none appears within the campaign.
4. After each acceptance: `python3 scripts/export_plugin_v2.py --out plugin/v2/recipes.json`, commit.
   When everything possible is accepted: open a PR `mtp-campaign` → `main` on 0xSero/local-ai-registry with the
   full table of what changed and the measured tok/s before and after MTP per card, and do NOT merge it; Sero
   reviews. Then in the plugin: `git checkout v6 && make sync REGISTRY=$PWD/../registry-v6 REGISTRY_REF=mtp-campaign`
   and commit on `v6` (not pushed to `main`).

## Rules

- Never `pkill -f` from your shell (the pattern matches your own process). Never run without a timeout on
  anything that reads a socket or the network. Never spend on an instance that is not verified, and never leave
  one running; if a run hangs beyond 90 minutes, destroy it and log why.
- Every claim in the final report must come from a log line or a file you can point to.
- If you are blocked (balance, no offer, a build failure you cannot fix in two attempts), log it, move to the
  next item, and list it under "Blocked" in the result; do not stop the whole campaign for one card.

## Result

(written by the agent when done)
