# Fleet configuration backup, 2026-10-01

Every saved or running model configuration found on the six owned machines (pop-os, omarchy, spark-2822, spark-2384, spark-557f, spark-de5c), captured read-only at 2026-10-01T23:19Z. Nothing was launched, stopped or changed on any host.

Sources read on each host: the Local Studio controller's recipe overlay (`data/model-index.json`, what `:8080` serves), legacy SQLite `recipes` rows that were never migrated into it, rollback and deploy-test databases, the new controller's (`local-studio serve`, `:18090`) export and assignment tables, running engine containers and processes, files those configurations reference (launch scripts, compose files, seccomp profiles), and the MiaAI launcher checkouts behind the Spark adopt-only entries.

## Files

- `manifest.json`: one row per configuration: host, source, decision, gaps, artifact revision, image ids and digests, referenced host files with SHA-256, hardware and context, and `raw_sha256` (the private secret-redacted capture) next to `published_sha256` (this copy).
- `<host>/<source>.json`: the configurations exactly as stored, sanitized: `${HOME}`, `${MODEL_ROOT}`, `<tailnet-ip>`, `<lan-ip>`, `<fabric-ip>`, `GPU-<uuid>`, `<user>`, `<email>` replace host values; secrets were replaced by `<redacted>` at capture.
- `<host>/files/`, `<host>/launcher/`, `pop-os/build/`, `pop-os/images/`: referenced scripts, launcher `.env` and local diffs, the DS4 compose build context, and `docker image inspect` plus history of local images.
- `live-engines.json`: engine containers and processes running at capture time (experiments and quantization jobs; none is a saved serving configuration).

## Decisions

| host | configs | decisions |
|---|---|---|
| omarchy | 12 | archived:not-recoverable 12 |
| pop-os | 53 | archived:not-recoverable 43, duplicate 1, matches-existing-record 1, reference:new-controller-registry-export 5, registry-record 3 |
| spark-2384 | 14 | adopt-forwarder 1, archived:not-recoverable 8, duplicate 4, reference:new-controller-registry-export 1 |
| spark-2822 | 242 | archived:not-recoverable 31, archived:ops-hook 10, archived:probe 198, duplicate 3 |
| spark-de5c | 5 | adopt-forwarder 1, archived:not-recoverable 4 |

- `registry-record`, `adopt-forwarder`: a candidate record in `registry/recipe/` (ids in `registry_record`). Five records: `glm53-flash-nvidia-nvfp4-rtxpro6000-vllm-tp4-popos-20261001`, `deepseek-v4-1-flash-fp8-rtxpro6000-vllm-tp4-popos-20261001`, `deepseek-v4-flash-0731-fp8-rtxpro6000-vllm-tp4-popos-20261001`, `glm53-flash-mia-exl3-tr3-4bpw-dgxspark-vllm-tp2-miaai-20261001`, `qwen38-flash-next-nvfp4-dgxspark-vllm-tp2-miaai-20261001`. All are `candidate`: no registry acceptance has run on these exact launches.
- `matches-existing-record`: pop-os `glm-5.3` is the launch already recorded as `glm-5-3-exl3-tr3-3-0bpw-rtx-pro-6000-blackwell-96gb-vllm-tp4` (environment identical except `CUDA_VISIBLE_DEVICES`).
- `archived:not-recoverable`: the configuration is kept here exactly, but its weights, image or launch script are gone from the host (`gaps`), or the weights have no recorded revision. These are not registry recipes; a nearby model was not substituted.
- `archived:probe`, `archived:ops-hook`: spark-2822 controller-path probes and ops hooks (context 1, `/var/run/docker.sock` as model path), kept for completeness.
- `duplicate`: same serve body as an earlier row (`duplicate_of`).
- `reference:new-controller-registry-export`: the new controller exported or assigned an existing registry recipe; nothing new to record.

## Promotion

A record becomes `validated` only through acceptance evidence on the exact hardware (`scripts/accept_recipe.py`, or `lab/lab.py try --on endpoint` for the current registry), never by editing `status`.
