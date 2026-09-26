# Qwen3.8-27B on Apple M4 Max, 128 GB

This profile carries the MTPLX configuration measured in
[PR #104](https://github.com/0xSero/local-ai-registry/pull/104) into the six-gate lab.
It uses MTPLX 2.12.0 / MLX 0.32.2, 4-bit language and MTP weights, Q4 decode KV,
a 204,800-token window, one request, and native MTP depth 3. Vision and norms
retain the artifact's higher precision. The measured Mac has 40 GPU cores,
128 GiB unified memory, and macOS 27.0 (26A428). No other Mac is certified by
this run.

The earlier combined 200,592-token cold retrieval/image/MTP test, including its
69.56 GiB peak MLX allocation and 4.383 tokens/s long-context decode, remains
available in the [original immutable evidence](https://github.com/swwwamo/local-ai-registry/blob/98a8c1533a7dcd9fd54b68a3a5402966b873edbf/sources/qwen38-mtplx-m4-max-128gb/README.md).
That memory figure is an allocator peak, not total system RAM. The new lab
measures speed on its separate short story prompt; it does not assert 15
tokens/s at maximum context. Its six gates do not re-test vision or certify
optimal settings. The previous vision/MTP evidence supports those settings.

## Start and test

Read `registry/engines/mtplx-qwen3.8-27b-4bit-200k.json`. Its `runtime` block is
the exact dependency lock and its argv/environment are the native launch.
After a passing recipe exists, `lab.py render` and the SDK's `steps()` provide
the corresponding setup commands. `uv` is required for those setup commands.
Use a fresh virtual environment; do not replace an existing model runtime.

Download `Youssofal/Qwen3.8-27B-MTPLX-Bare-Speed` at
`b59d7002368575f08a58ba0d26686b53a9c162d6`, including vision and MTP tensors.
The [original file manifest](https://github.com/swwwamo/local-ai-registry/blob/80ba2a841bc017d06260340dce571f6504148d72/sources/qwen38-mtplx-m4-max-128gb/artifacts.json)
and hash-verifying downloader remain available from the original contribution.
Set `MODEL_DIR` to that local directory and launch the profile's command with
`${model_dir}` replaced by it. Keep thinking enabled (MTPLX's default) so the
reasoning gate can observe a separate reasoning field.

Run the lab with the same pinned virtualenv's Python:

```sh
"$VENV/bin/python" lab/lab.py try \
  Youssofal/Qwen3.8-27B-MTPLX-Bare-Speed@b59d7002368575f08a58ba0d26686b53a9c162d6 \
  --model qwen3.8-27b --engine mtplx-qwen3.8-27b-4bit-200k \
  --card apple-m4-max-128gb --gpu 'Apple M4 Max' \
  --on endpoint --endpoint http://127.0.0.1:18198 --tokenizer "$MODEL_DIR"
make
make check
```

`--tokenizer` loads only local files, with remote tokenizer code disabled. This
counts the actual streamed output tokens instead of the character estimate
used when a server lacks `/v1/token/encode`. The local path is not saved in the
run evidence. The six gate thresholds and synthetic prompts are unchanged.
The context prompt is substantial: leave the server and lab running until it
finishes. Stop the dedicated server afterwards.

## Privacy and scope

All six prompts and the tool response are synthetic. The weather tool is a
fixture; it does not contact a weather service. Owner-endpoint evidence records
model/card settings, synthetic results and performance, not private prompts,
machine names, serial numbers, credentials, or the local tokenizer path.
Download steps disable implicit Hub credentials and Hub telemetry; inference
uses offline Hub/Transformers settings. The unauthenticated server binds only
127.0.0.1; other local processes can still access it. SSD session caching and
agent rewrites are disabled. Package/model downloads still contact their public
hosts. A public PR exposes the submitting GitHub account and benchmark results.

Run a dedicated server rather than pointing the lab at a personal conversation
session. Inspect the generated `lab/runs/` file before explicitly adding it to
Git; that directory is ignored by default. Do not include complete server logs,
local configuration, credentials, virtual environments, or model files.
