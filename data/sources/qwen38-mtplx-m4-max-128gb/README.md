# Qwen3.8-27B: native MTPLX on Apple M4 Max, 128 GB

Archived measurements from the pre-lab registry. Run the historical commands
below from `data/`. The active lab integration is documented in
[the native M4 guide](../../../lab/native-mtplx.md).

This is a native macOS recipe for the registry's data/research collection. It is
not an Omarchy/Linux container recommendation. Hardware claims apply only to the
M4 Max with 128 GB tested here. Other chips, 24 GB and 32 GB machines require
their own acceptance runs; a configured context window does not prove it fits.

## Artifact and runtime

- Model: `Youssofal/Qwen3.8-27B-MTPLX-Bare-Speed` at
  `b59d7002368575f08a58ba0d26686b53a9c162d6`.
- Language weights and MTP matrices: MLX affine 4-bit, group size 64. Norms and
  the vision tower retain the artifact's higher precision. This is not a claim
  that every tensor or the total artifact averages exactly four bits.
- Runtime: MTPLX 2.12.0, MLX 0.32.2, MLX-LM 0.31.3, Python 3.12.4.
  The complete tested dependency versions are in `scripts/mtplx-requirements.txt`.
- macOS 27.0 (26A428), 40 GPU cores, Apple-managed fans, one active inference request.
- `artifacts.json` contains byte sizes and SHA-256 values for every downloaded
  file. Large-file hashes were checked against the Hugging Face LFS manifest;
  the remaining hashes were computed from files downloaded at the pinned revision.

## Reproduce

From the repository checkout containing this contribution, install the runtime
in a separate environment. `sfw` is the package-download review wrapper used for
this run; it is not a dependency of the inference engine.

```bash
uv venv .venv-mtplx --python 3.12
sfw uv pip install --python .venv-mtplx/bin/python -r scripts/mtplx-requirements.txt
export MODEL_DIR=/absolute/path/to/qwen38-mtplx-4bit
.venv-mtplx/bin/python scripts/prepare_qwen38_mtplx.py "$MODEL_DIR"
MTPLX_BIN="$PWD/.venv-mtplx/bin/mtplx" bash scripts/serve_qwen38_mtplx.sh "$MODEL_DIR"
```

The server binds only `127.0.0.1:18198`. In a second terminal, with the same
`MODEL_DIR`, run:

```bash
.venv-mtplx/bin/python scripts/benchmark_mtplx.py --model-path "$MODEL_DIR" \
  --stage short --output /tmp/qwen38-short.jsonl
.venv-mtplx/bin/python scripts/benchmark_mtplx.py --model-path "$MODEL_DIR" \
  --stage long --output /tmp/qwen38-long.jsonl
```

After these workload checks pass, record the registry's separate short-completion
acceptance on the same server:

```bash
.venv-mtplx/bin/python scripts/accept_recipe.py \
  qwen38-27b-mtplx-4bit-apple-m4-max-128gb-200k \
  --endpoint http://127.0.0.1:18198 \
  --request-json sources/qwen38-mtplx-m4-max-128gb/acceptance-request.json \
  --harness "scripts/accept_recipe.py native-script" --revalidate
make trust
make index
make check
```

`--revalidate` permits repeating the published recipe's acceptance. Its status
is derived from the recorded evidence, not assigned based on the context flag.

Use fresh output filenames: the harness refuses to overwrite existing evidence.
It clears the dedicated server's session cache before each request. Do not run
it against a server used for other work. Stop the server with Ctrl-C afterwards.

## What is measured

The short sweep requests 256 output tokens for a synthetic coding prompt, three
times each with AR and MTP depths 1, 2 and 3. All samples, including first-use
compilation costs, are retained. Run order is fixed; this is a practical depth
sweep, not a randomized hardware comparison or proof of global optimality.
Thinking is off, temperature 0.7, top-p 0.8, top-k 20, seed 42.

Vision uses a generated PNG with a red square, blue circle and the text
`ORBIT 7319`. The long test places three secrets at distributed positions in a
synthetic archive of at least 200,000 text tokens, attaches the same image, and
requires all three secrets plus image text in the answer. Acceptance also
requires reported prompt tokens >=200,000 and actual drafted and accepted MTP
tokens. This checks retrieval and image use together, not general long-context
quality. It does not test reasoning, tools, video, or multiple concurrent users.

The context window is 204,800 tokens, KV decoding uses Q4, and the final launcher
uses 4,096-token prefill chunks. The initial short sweep used 512-token chunks;
all of its prompts were shorter than either chunk size. An initial long test
at 512 was cancelled during prefill and is recorded as tuning, not acceptance.
MTPLX 2.12.0 documents that prefill uses unquantized KV, so its
peak memory must be measured independently of the smaller Q4 decode cache.
Reported MLX peak allocation is not total system memory or proof of fit on a
machine with that amount of RAM.

## Privacy

The model downloader explicitly avoids cached Hugging Face credentials and
disables Hub telemetry. After download, the launcher sets offline mode for the
Hub and Transformers. SSD session caching and agent transcript rewrites are
disabled. The local API has no authentication and is accessible to other local
processes; it is not exposed to the LAN by this launcher.

Published evidence uses only synthetic input, synthetic output, timestamps,
software versions, chip/RAM/OS, workload settings, and performance counters.
Server logs and full health responses are intentionally excluded because they
can contain local filesystem paths. No serial numbers, machine names, account
credentials, personal prompts, or private files are needed. GitHub still
identifies the submitting account; this is not an anonymous submission system.

The pinned files improve reproducibility. They are not a security certification
of the runtime or all of its dependencies. Recipe validation is functional
acceptance on the stated hardware, not an independent security audit.

## Measured results (2026-09-25)

| Workload | Samples | Decode tokens/s |
| --- | ---: | ---: |
| Short AR, depth 0 | 3 | 23.242 median |
| Short MTP, depth 1 | 3 | 34.625 median |
| Short MTP, depth 2 | 3 | 39.830 median |
| Short MTP, depth 3 | 3 | 51.307 median |
| 200,592-token input + image, MTP depth 3 | 1 | 4.383 |

The long request completed with 72 output tokens. All three distributed secrets
and `ORBIT 7319` were recovered. The server reported zero cached prompt tokens,
54 drafted tokens, 46 accepted drafts, and Q4 paged KV mode. All harness checks passed.

Cold prompt processing took 1879.167 seconds (106.745 tokens/s);
client time to first token was 1880.042 seconds and total request time
was 1896.475 seconds. Peak MLX allocation was 74,686,072,406 bytes
(69.56 GiB). This run does **not** fit 24 GB or 32 GB.

The best median in the short fixed-order sweep was depth 3, about 2.21x AR.
That short-prompt speed does not describe 200k-context decoding. In particular,
full-context decode was below the acceptance helper's default 5 tokens/s threshold;
the separate short-completion acceptance is the registry trust anchor. Passing
functional retrieval does not imply fast interactive use at 200k tokens.

`short.jsonl` and `long.jsonl` preserve each workload's synthetic answer and
performance counters. `tuning-attempt.json` records the interrupted 512-token
prefill experiment. No result is extrapolated to another chip or RAM capacity.
