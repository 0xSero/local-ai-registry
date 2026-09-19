# Discord recipes — Local Inference Lab

Ledger for branch `discord-recipes-20260919`: the serving recipes found in the
Local Inference Lab Discord (guild `1466898002793857221`) and what happened to it in the registry.

## How the server was read

- Read-only. The user's logged-in Discord session was driven from a browser tab through the sitegeist bridge.
  Nothing was posted, reacted to, joined, or clicked that sends. Every request was a `GET` against the same
  endpoints the web client uses (`/api/v9/guilds/.../channels`, `/messages`, `/threads/archived/public`, `/messages/search`).
- Dump written to `/Users/sero/local-registry/discord-dump-20260919/` (outside the repo):
  - `channels.json`  111 channels (text, news, forum, voice, categories) from the guild channel list.
  - `messages/`  one file per text/news channel, 88 channels.
  - `threads/`  one file per thread, 508 threads scraped (471 archived threads enumerated through the archived-threads endpoint,
    the rest found by sweeping the search API for common tokens, link/file/embed filters and model names, which is how
    unarchived threads surface when the active-threads endpoint answers 403 for a user token).
  - `messages` total: **240323** messages (2026-08-27 .. 2026-09-19, i.e. the whole life of the server at capture time).
  - `attachments-index.json` + `attachments/`  **931** text attachments (`.yaml`, `.yml`, `.sh`, `.txt`, `.json`, `.md`, `.env`)
    downloaded from the CDN, 15.2 MB.
- Capture time for every record: `2026-09-19T05:35:00Z`.

### Channels that could not be read

Nine channels returned `403` for this account, so nothing in them is in this branch: `moderation`, `vip-chat`, `vllm (VIP)`, `docker (VIP)`, `quants (VIP)`, `kld (VIP)`, `optimization (VIP)`, `spark (VIP)`, `nonprofit (VIP)`.
They are the Contributor & VIP category plus `moderation`. If recipes were posted there, this branch does not have them.

## Rules the records follow

- Records under `registry/`, `status` derived by `scripts/trust.py` (nothing here is typed `validated`; without a GPU acceptance run
  every Discord record is correctly `candidate`).
- `launch.kind` is `docker`/`docker-compose` when the message contains a real executable launch, and `reference` when only the
  numbers or a non-executable command were posted. Every launch keeps the image, arguments, environment and ports exactly as posted.
- Every number carries provenance pointing at the Discord message that reported it, with the poster's own wording in the row label.
- Where a post leaves the checkpoint or the rig implicit, the record says how it was resolved (`metadata.model_resolution`,
  `metadata.rig_resolution`, `metadata.checkpoint_resolution`) and points at the message that supplied it:
  - `explicit`: the post itself names it.
  - `unique-basename`: the model directory's basename identifies exactly one registry repository.
  - `prose-repository-mentioned`: the text contains exactly one `owner/name` repository string.
  - `author-thread-checkpoint`, `author-thread rig`: the same author named exactly one repository or rig elsewhere in the same channel or thread.
  - `scope: author` rig: the author named exactly one rig anywhere in the server (authors who named several are skipped).
- A message counts as a launch only when it carries a CLI flag or a fenced engine command, so "can someone post a docker run"
  requests are not recipes.
- Credentials members pasted into their launch commands (one Hub token in an environment map) are replaced with
  `<redacted-credential>`; the generator scrubs every record it writes, and the branch history was rewritten so no
  token remains in any commit.
- Pinned upstream imports (`lil-*` from `sources/local-inference-lab/2026-09-13.json`) stay evidence-free, so numbers reported in
  Discord for those images live on Discord reference records instead (`scripts/check_lil_import.py` enforces this).

## Added

| record | model | hardware | engine | context | source |
|---|---|---|---|---|---|
| `discord-0xsero-glm-5-2-nvfp4-reap-469b-nvfp4-reap-rtx-pro-6000-blackwell-96gb-tp0` | 0xsero-glm-5-2-nvfp4-reap-469b--nvfp4-reap | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:glm52-v11-darkdevotion-vllma86f74e- |  | [msg](https://discord.com/channels/1466898002793857221/1517182540853809162/1517222801688232027) |
| `discord-brandonmusic-glm-5-3-flash-tr3-4bpw-exl3-4bpw-rtx-pro-6000-blackwell-96gb-tp0` | brandonmusic-glm-5-3-flash-tr3-4bpw--exl3-4bpw | rtx-pro-6000-blackwell-96gb 1 | ghcr.io/tpurtell/glm-5.3-flash-exl3-4bpw-2x-rtx |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1547093497952084048) |
| `discord-compose-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-624138` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | luke-sglang:blackwell |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1499410301672624138) |
| `discord-compose-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-895454` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 4 | lukealonso/sglang-cuda13-b12x:latest | 131072 | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1501228227601895454) |
| `discord-compose-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp2-557170` | qwen-qwen3-6-27b--fp8 | rtx-pro-6000-blackwell-96gb 2 | repne/vllm:latest | 65536 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1500340443911557170) |
| `discord-cyankiwi-qwen3-6-27b-awq-int4-awq-rtx-5070-ti-16gb-tp2` | cyankiwi-qwen3-6-27b-awq-int4--awq | rtx-5070-ti-16gb 2 | voipmonitor/vllm:gilded-gnosis-v20-vllm7e3bee1-si623 | 102400 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1530407673776967781) |
| `discord-deepseek-ai-deepseek-v4-1-flash-fp8-rtx-pro-6000-blackwell-96gb-tp0-339856` | deepseek-ai-deepseek-v4-1-flash--fp8 | rtx-pro-6000-blackwell-96gb 4 | ghcr.io/local-inference-lab/vllm:jovian-judgement-be |  | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1550242308459339856) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0-019956` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/vllm:infernal-invocation-vllma7f04eb-b12 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1537546027073019956) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0-148804` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | rtx-pro-6000-blackwell-96gb 2 | docker.io/voipmonitor/vllm:infernal-invocation-vllm3 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1537061281285148804) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0-267250` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/vllm:infernal-invocation-vllmf0fa1ce-b12 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1539582368745267250) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0-364885` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/vllm:jovian-judgement-vllm28bc825-b12x8a |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1545345760227364885) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0-489643` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/vllm:infernal-invocation-vllm7ed814e-b12 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1537436882336489643) |
| `discord-deepseek-ai-deepseek-v4-flash-2-bit-experts-vllm-moet-w2-fp8-kv-rtx-5080-16gb-tp2-331035` | deepseek-ai-deepseek-v4-flash--2-bit-experts-vllm-moet-w2-fp8-kv | rtx-5080-16gb 2 | repne/vllm:dsv4-v0 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1506712614309331035) |
| `discord-deepseek-ai-deepseek-v4-flash-2-bit-experts-vllm-moet-w2-fp8-kv-rtx-5090-32gb-tp0-302131` | deepseek-ai-deepseek-v4-flash--2-bit-experts-vllm-moet-w2-fp8-kv | rtx-5090-32gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm1e9c9c3-sieec |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1533976446224302131) |
| `discord-deepseek-ai-deepseek-v4-flash-2-bit-experts-vllm-moet-w2-fp8-kv-rtx-pro-6000-blackwell-96gb-tp0` | deepseek-ai-deepseek-v4-flash--2-bit-experts-vllm-moet-w2-fp8-kv | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/vllm:eldritch-final-vbfaa36b-b12x284a2ea |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1521034278941495429) |
| `discord-deepseek-ai-deepseek-v4-flash-2-bit-experts-vllm-moet-w2-fp8-kv-rtx-pro-6000-blackwell-96gb-tp2` | deepseek-ai-deepseek-v4-flash--2-bit-experts-vllm-moet-w2-fp8-kv | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/dsv4-flash:lucifer-mxfp4-cutlass-2026060 | 256000 | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1511828195895410708) |
| `discord-deepseek-ai-deepseek-v4-flash-dspark-fp8-rtx-pro-6000-blackwell-96gb-tp0-266914` | deepseek-ai-deepseek-v4-flash-dspark--fp8 | rtx-pro-6000-blackwell-96gb 2 | vllm/ds4flash:dspark0713 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1526155667000266914) |
| `discord-deepseek-ai-deepseek-v4-flash-dspark-fp8-rtx-pro-6000-blackwell-96gb-tp0-418546` | deepseek-ai-deepseek-v4-flash-dspark--fp8 | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/vllm:gilded-gnosis-v18-vllm264bce1-b12xb |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1528164614989418546) |
| `discord-ds41-flash-1m-context-dspark-docker-rtxpro6000-ws-tp4` | deepseek-ai-deepseek-v4-1-flash--fp8 | rtx-pro-6000-blackwell-96gb 4 | ghcr.io/local-inference-lab/vllm:jovian-judgement-be | 1048576 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1550426993453965384) |
| `discord-ds41-flash-jovian-judgement-beta-docker-rtxpro6000-ws-tp4` | deepseek-ai-deepseek-v4-1-flash--fp8 | rtx-pro-6000-blackwell-96gb 4 | ghcr.io/local-inference-lab/vllm:jovian-judgement-be | 131072 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1550242308459339856) |
| `discord-ds41-flash-jovian-judgement-r38-compose-rtxpro6000-ws-tp4` | deepseek-ai-deepseek-v4-1-flash--fp8 | rtx-pro-6000-blackwell-96gb 4 | localinferencelab/vllm:jovian-judgement-community-20 | 131072 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1548872593522565164) |
| `discord-lil-deepseek-ai-deepseek-v4-flash-vision-exp-unpinned-rtx-pro-6000-blackwell-96gb-tp0-909068` | lil-deepseek-ai-deepseek-v4-flash-vision-exp--unpinned | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/vllm:jovian-judgement-vllmf66599d-b12x15 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1546497871958909068) |
| `discord-lil-deepseek-ai-deepseek-v4-flash-vision-exp-unpinned-rtx-pro-6000-blackwell-96gb-tp0-950730` | lil-deepseek-ai-deepseek-v4-flash-vision-exp--unpinned | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/vllm:jovian-judgement-vllmf66599d-b12x15 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1546923987441950730) |
| `discord-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp0-592838` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:cu130-b12x-full |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1490740681218592838) |
| `discord-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp2-242471` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 2 | lmsysorg/sglang:glm5-blackwell |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1480573750335242471) |
| `discord-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp2-740001` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/llm-pytorch-blackwell:nightly |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1480577558616740001) |
| `discord-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp8-323428` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 8 | sglang-glm5:latest |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1478931189405323428) |
| `discord-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp8-479519` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1491140313052479519) |
| `discord-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp8-957799` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/llm-pytorch-blackwell:nightly |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1481831080158957799) |
| `discord-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp8-974526` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/llm-pytorch-blackwell:nightly |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1482687780822974526) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 1 | localinferencelab/vllm:jovian-judgement-community-20 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1548244373953847368) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-001558` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260906 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1546103275752001558) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-132362` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260901 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1544320517132132362) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-305792` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260908 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1546850663391305792) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-325016` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260908 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1546930555340325016) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-545832` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260902 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1544557486512545832) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-641376` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260903 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1545156576195641376) |
| `discord-lil-local-inference-lab-qwen3-8-flash-next-nvfp4-unpinned-rtx-3090-24gb-tp2-737612` | lil-local-inference-lab-qwen3-8-flash-next-nvfp4--unpinned | rtx-3090-24gb 2 | kanadaj/sglang-qwen38fn-sm120-turbo:r22-lilfix5-mtp | 524288 | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1545872359779737612) |
| `discord-lil-lribeiro-qwen3-8-27b-nvfp4-v17-unpinned-rtx-pro-6000-blackwell-96gb-tp0-603530` | lil-lribeiro-qwen3-8-27b-nvfp4-v17--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:v0.27.1-cu129 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1538964880986603530) |
| `discord-lil-lukealonso-glm-5-1-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp8-165652` | lil-lukealonso-glm-5-1-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1509871840196165652) |
| `discord-lil-lukealonso-glm-5-1-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp8-376496` | lil-lukealonso-glm-5-1-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1491801217423376496) |
| `discord-lil-lukealonso-glm-5-2-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0` | lil-lukealonso-glm-5-2-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm2167295-si6a9 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1529479030112522370) |
| `discord-lil-lukealonso-kimi-k3-qsrt-k2-3b98114115f1-rtx-pro-6000-blackwell-96gb-tp0` | lil-lukealonso-kimi-k3-qsrt-k2--3b98114115f1 | rtx-pro-6000-blackwell-96gb 1 | amygdala/vllm:kimi-k3-dcp8-flashinfer-fa2-nograph-20 |  | [msg](https://discord.com/channels/1466898002793857221/1528141816459689984/1537921009833869342) |
| `discord-lil-lukealonso-minimax-m2-5-nvfp4-unpinned-dgx-spark-gb10-128gb-tp2-711790` | lil-lukealonso-minimax-m2-5-nvfp4--unpinned | dgx-spark-gb10-128gb 2 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1491917077072711790) |
| `discord-lil-lukealonso-minimax-m2-5-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp2-863353` | lil-lukealonso-minimax-m2-5-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 2 | lmsysorg/sglang:dev-cu13 |  | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1477801308944863353) |
| `discord-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp4-386949` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1495795167725224158/1495795626116386949) |
| `discord-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp4-566359` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/sglang:dev-cu132 |  | [msg](https://discord.com/channels/1466898002793857221/1477045884326908191/1483219003177566359) |
| `discord-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp4-642729` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/sglang:test-cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1481791503285227612/1484649075222642729) |
| `discord-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp4-884352` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 4 | orthozany/vllm-qwen35-mtp:latest | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1481991865153884352) |
| `discord-lil-minimaxai-minimax-m2-5-unpinned-b200-180gb-tp4-464353` | lil-minimaxai-minimax-m2-5--unpinned | b200-180gb 4 | vllm/vllm-openai:latest |  | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1473317148641464353) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp0-105612` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 1 | k26-0424-clean:v12 |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1505191701726105612) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp0-391976` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:kimi-k26-mtp-upstream-stack-pcie-en |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1501586182260391976) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp0-564218` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:cu130-mtp-tuned-v3-20260423 |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1499411482050564218) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp0-616391` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:kimi-k26-mtp-upstream-stack-pcie-en |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1501606808018616391) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp0-686393` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:cu130-mtp-tuned-20260423 |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1496926704302686393) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-164274` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | orthozany/k26-0424-clean:v12 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1505873583338164274) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-168701` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | luke-sglang:blackwell-20260421 |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1496174942797168701) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-624138` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | luke-sglang:blackwell |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1499410301672624138) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-732958` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/vllm:kimi-k26-mtp-upstream-stack-pcie-en | 262144 | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1502115128420732958) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-790824` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/vllm:kimi-v5-cu132-89da7631 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1508846127900790824) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-930182` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/vllm:cu130-mtp-tuned-v3-20260423 | 256000 | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1496979314019930182) |
| `discord-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-166053` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/llm-pytorch-blackwell:nightly |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1479255806951166053) |
| `discord-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-716117` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:cu130-b12x-full |  | [msg](https://discord.com/channels/1466898002793857221/1476263308242714718/1490492684211716117) |
| `discord-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp1-504294` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:v0.17.1-cu130 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1482131191338504294) |
| `discord-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp2-039610` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 2 | vllm/vllm-openai:cu130-nightly | 186560 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1490084838815039610) |
| `discord-lil-sehyo-qwen3-5-27b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp1-069215` | lil-sehyo-qwen3-5-27b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:v0.17.0-cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1466898004219789502/1479693581903069215) |
| `discord-lil-willfalco-glm-5-2-exl3-tr3-3-36bpw-unpinned-rtx-pro-6000-blackwell-96gb-tp0` | lil-willfalco-glm-5-2-exl3-tr3-3-36bpw--unpinned | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm4d006a4-b12xc |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1537224373931479110) |
| `discord-lil-willfalco-glm-5-2-exl3-tr3-3-42bpw-unpinned-rtx-5090-32gb-tp0-287706` | lil-willfalco-glm-5-2-exl3-tr3-3-42bpw--unpinned | rtx-5090-32gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm966d57c-sibbb |  | [msg](https://discord.com/channels/1466898002793857221/1532052969896284161/1534330212706287706) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-5090-32gb-tp4-356919` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-5090-32gb 4 | docker.io/lukealonso/sglang-cuda13-b12x:noloop |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1501389893866356919) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-5090-32gb-tp4-489633` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-5090-32gb 4 | docker.io/lukealonso/sglang-cuda13-b12x |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1501209168160489633) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-895454` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | lukealonso/sglang-cuda13-b12x:latest |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1501228227601895454) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-918243` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 4 | lukealonso/sglang-cuda13-b12x:noloop |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1501785693439918243) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-239770` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/sglang:mimo-v25-pro-tp8-b12x3917cb2-late |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1503933602663239770) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-251849` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/sglang:glm51-nsa-luke-a2573ab-b12x0111-m | 128000 | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1499566806724251849) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-789029` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | lukealonso/sglang-cuda13-b12x:noloop | 131072 | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1503657281617789029) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-356919` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 4 | docker.io/lukealonso/sglang-cuda13-b12x:noloop |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1501389893866356919) |
| `discord-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-622120` | lukealonso-mimo-v2-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 4 | docker.io/lukealonso/sglang-cuda13-b12x |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1501072974344622120) |
| `discord-lukealonso-minimax-m2-7-nvfp4-nvfp4-rtx-5090-32gb-tp2-926656` | lukealonso-minimax-m2-7-nvfp4--nvfp4 | rtx-5090-32gb 2 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1484016763124453456/1493337042132926656) |
| `discord-lukealonso-minimax-m2-7-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-185674` | lukealonso-minimax-m2-7-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | lmsysorg/sglang:latest |  | [msg](https://discord.com/channels/1466898002793857221/1484016763124453456/1494191967507185674) |
| `discord-lukealonso-minimax-m2-7-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-193536` | lukealonso-minimax-m2-7-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1484016763124453456/1493080777968193536) |
| `discord-madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid-nvfp4-rtx-pro-6000-blackwell-96gb-tp0` | madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:fathomless-firmament-v17-vllm6ccc3e |  | [msg](https://discord.com/channels/1466898002793857221/1523800435490820239/1527117187632992377) |
| `discord-madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-208317` | madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | madeby561/vllm-glm52-nvfp4-nf3-hybrid:v3 |  | [msg](https://discord.com/channels/1466898002793857221/1523800435490820239/1525131836794208317) |
| `discord-madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-471084` | madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | verdictai/glm52-nvfp4-kv:v1 |  | [msg](https://discord.com/channels/1466898002793857221/1517182540853809162/1523720989618471084) |
| `discord-moonshotai-kimi-k2-5-int4-rtx-pro-6000-blackwell-96gb-tp8-125968` | moonshotai-kimi-k2-5--int4 | rtx-pro-6000-blackwell-96gb 8 | lmsysorg/sglang:dev-cu13 |  | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1481714010889125968) |
| `discord-moonshotai-kimi-k2-5-int4-rtx-pro-6000-blackwell-96gb-tp8-147438` | moonshotai-kimi-k2-5--int4 | rtx-pro-6000-blackwell-96gb 8 | vllm/vllm-openai:cu130-nightly | 210000 | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1476876233387147438) |
| `discord-nvidia-glm-5-2-nvfp4-nvfp4-b200-180gb-tp1-531335` | nvidia-glm-5-2-nvfp4--nvfp4 | b200-180gb 1 | vllm/vllm-openai:nightly-aarch64 | 150000 | [msg](https://discord.com/channels/1466898002793857221/1516097906967576706/1539034681595531335) |
| `discord-nvidia-glm-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp8-891305` | nvidia-glm-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/sglang:test-cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1488132113738891305) |
| `discord-nvidia-minimax-m2-7-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-826524` | nvidia-minimax-m2-7-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1526581556183826524) |
| `discord-nvidia-minimax-m2-7-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-934565` | nvidia-minimax-m2-7-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 2 | llm-sglang-blackwell:cu130 | 196608 | [msg](https://discord.com/channels/1466898002793857221/1484016763124453456/1502417779263934565) |
| `discord-nvidia-nvidia-nemotron-3-ultra-550b-a55b-nvfp4-nvfp4-mixed-rtx-pro-6000-blackwell-96gb-tp4-1881` | nvidia-nvidia-nemotron-3-ultra-550b-a55b-nvfp4--nvfp4-mixed | rtx-pro-6000-blackwell-96gb 4 | klc/nemotron3-ultra-b12x:v1 | 32768 | [msg](https://discord.com/channels/1466898002793857221/1494478683258490892/1512154004040188127) |
| `discord-nvidia-nvidia-nemotron-3-ultra-550b-a55b-nvfp4-nvfp4-mixed-rtx-pro-6000-blackwell-96gb-tp4-6133` | nvidia-nvidia-nemotron-3-ultra-550b-a55b-nvfp4--nvfp4-mixed | rtx-pro-6000-blackwell-96gb 4 | vllm/vllm-openai:cu130-nightly | 131072 | [msg](https://discord.com/channels/1466898002793857221/1494478683258490892/1512317209282613388) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-b200-180gb-tp4-040872` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | b200-180gb 4 | vllm/vllm-openai:cu130-nightly |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1477716462130040872) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-b200-180gb-tp4-171357` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | b200-180gb 4 | lmsysorg/sglang:dev-cu13 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1474793281132171357) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-b200-180gb-tp4-621351` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | b200-180gb 4 | vllm/vllm-openai:qwen3_5-cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1476028912109621351) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-011083` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:nightly |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1476024281787011083) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-118743` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 1 | localhost/vllm:cu130-nightly |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1477727036587118743) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-258463` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 1 | orthozany/vllm-qwen35-mtp:latest |  | [msg](https://discord.com/channels/1466898002793857221/1478543811385884702/1479345001770258463) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-760226` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:cu130-nightly |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1476077012924760226) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-430304` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 4 | docker.io/verdictai/vllm-blackwell-k64:latest |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1482489242197430304) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-722710` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/llm-pytorch-blackwell:nightly |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1480685597302722710) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-851530` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 4 | lmsysorg/sglang:dev-cu13 | 128000 | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1480358650575851530) |
| `discord-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-919424` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/llm-pytorch-blackwell:customallreduce | 128000 | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1480310254418919424) |
| `discord-nvidia-qwen3-6-35b-a3b-nvfp4-nvfp4-rtx-5090-32gb-tp1-440867` | nvidia-qwen3-6-35b-a3b-nvfp4--nvfp4 | rtx-5090-32gb 1 | repne/vllm:nvfp4-moe-n433m | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1513468779722440867) |
| `discord-nvidia-qwen3-6-35b-a3b-nvfp4-nvfp4-rtx-5090-32gb-tp1-960761` | nvidia-qwen3-6-35b-a3b-nvfp4--nvfp4 | rtx-5090-32gb 1 | repne/vllm:nvfp4-moe-n433m | 250000 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1512441417710960761) |
| `discord-ormandj-glm-5-3-flash-w4a16-nvfp4-k32-experts-fp8-wo-nvfp4-rtx-pro-6000-blackwell-96gb-tp0` | ormandj-glm-5-3-flash-w4a16-nvfp4-k32-experts-fp8-wo-nvfp4 | rtx-pro-6000-blackwell-96gb 1 | ghcr.io/ormandj/sglang-glm53-flash-sm120 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1547468602335035463) |
| `discord-qwen-qwen3-5-27b-q4-k-xl-rtx-5090-32gb-tp0-541476` | qwen-qwen3-5-27b--q4-k-xl | rtx-5090-32gb 1 | vllm/vllm-openai:cu130-nightly | 128000 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1488565008781541476) |
| `discord-qwen-qwen3-6-27b-fp8-fp8-33492-rtx-5090-32gb-tp1-599053` | qwen-qwen3-6-27b-fp8--fp8--33492 | rtx-5090-32gb 1 | repne/vllm:v12.1 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1508958413986599053) |
| `discord-qwen-qwen3-6-27b-fp8-fp8-33492-rtx-pro-6000-blackwell-96gb-tp0-698172` | qwen-qwen3-6-27b-fp8--fp8--33492 | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:latest |  | [msg](https://discord.com/channels/1466898002793857221/1500236293324669130/1500469786436698172) |
| `discord-qwen-qwen3-6-27b-fp8-fp8-33492-rtx-pro-6000-blackwell-96gb-tp1-460526` | qwen-qwen3-6-27b-fp8--fp8--33492 | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:cu130-nightly | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1498365027382460526) |
| `discord-qwen-qwen3-6-27b-fp8-rtx-5090-32gb-tp0-503166` | qwen-qwen3-6-27b--fp8 | rtx-5090-32gb 1 | repne/vllm:latest | 131072 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1500247730931503166) |
| `discord-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp1-207424` | qwen-qwen3-6-27b--fp8 | rtx-pro-6000-blackwell-96gb 2 | repne/vllm:latest | 262144 | [msg](https://discord.com/channels/1466898002793857221/1498094855442927698/1498094859167207424) |
| `discord-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp1-484575` | qwen-qwen3-6-27b--fp8 | rtx-pro-6000-blackwell-96gb 1 | repne/vllm:v1 | 15000 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1502796035909484575) |
| `discord-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp1-504917` | qwen-qwen3-6-27b--fp8 | rtx-pro-6000-blackwell-96gb 1 | repne/vllm:latest | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1500098167415504917) |
| `discord-radixark-qwen3-8-27b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-964932` | radixark-qwen3-8-27b-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | lmsysorg/sglang:qwen38-27b | 262144 | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1539724342965964932) |
| `discord-radixark-qwen3-8-flash-next-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0` | radixark-qwen3-8-flash-next-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | sglang-qwen38fn-sm120-turbo:r22 |  | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1546121824885280829) |
| `discord-reported-ds41-flash-r36-rtxpro6000-ws-tp4` | lil-deepseek-ai-deepseek-v4-1-flash--unpinned | rtx-pro-6000-blackwell-96gb 4 | localinferencelab/vllm:jovian-judgement-community-20 | 131072 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1548464464641134753) |
| `discord-reported-ds41-flash-r37-rtxpro6000-ws-tp4` | lil-deepseek-ai-deepseek-v4-1-flash--unpinned | rtx-pro-6000-blackwell-96gb 4 | localinferencelab/vllm:jovian-judgement-community-20 | 131072 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1548698823625277564) |
| `discord-sakamakismile-huihui-qwen3-6-27b-abliterated-nvfp4-mtp-nvfp4-rtx-5070-ti-16gb-tp0` | sakamakismile-huihui-qwen3-6-27b-abliterated-nvfp4-mtp--nvfp4 | rtx-5070-ti-16gb 1 | vllm/vllm-openai:cu129-nightly |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1534988203235475626) |
| `discord-serve-baseten-admin-glm-4-7-fp8-attn-fp4-mlp-fp8-rtx-pro-6000-blackwell-96gb-tp0-873357` | baseten-admin-glm-4-7-fp8-attn-fp4-mlp-fp8 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1505012495444873357) |
| `discord-serve-deepseek-ai-deepseek-v4-flash-2-bit-experts-vllm-moet-w2-fp8-kv-rtx-pro-6000-blackwell-96gb-tp0` | deepseek-ai-deepseek-v4-flash--2-bit-experts-vllm-moet-w2-fp8-kv | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1525524125282603068) |
| `discord-serve-deepseek-ai-deepseek-v4-flash-2-bit-experts-vllm-moet-w2-fp8-kv-rtx-pro-6000-blackwell-96gb-tp2` | deepseek-ai-deepseek-v4-flash--2-bit-experts-vllm-moet-w2-fp8-kv | rtx-pro-6000-blackwell-96gb 2 | vllm | 1048576 | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1524159306822586499) |
| `discord-serve-deepseek-ai-deepseek-v4-flash-2-bit-experts-vllm-moet-w2-fp8-kv-rtx-pro-6000-blackwell-96gb-tp4` | deepseek-ai-deepseek-v4-flash--2-bit-experts-vllm-moet-w2-fp8-kv | rtx-pro-6000-blackwell-96gb 4 | vllm | 307200 | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1510310262467461242) |
| `discord-serve-google-gemma-4-31b-it-q4-k-m-rtx-pro-6000-blackwell-96gb-tp0-841343` | google-gemma-4-31b-it--q4-k-m | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1476946295552741489/1489328648417841343) |
| `discord-serve-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp0-921950` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1484629919118921950) |
| `discord-serve-lil-festr2-glm-5-nvfp4-mtp-unpinned-rtx-pro-6000-blackwell-96gb-tp8-917939` | lil-festr2-glm-5-nvfp4-mtp--unpinned | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1488165552298917939) |
| `discord-serve-lil-local-inference-lab-glm-5-3-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-094502` | lil-local-inference-lab-glm-5-3-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1542910591730192434/1544120742613094502) |
| `discord-serve-lil-lukealonso-glm-5-1-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-967067` | lil-lukealonso-glm-5-1-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1499445202211967067) |
| `discord-serve-lil-lukealonso-minimax-m2-5-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp2-726884` | lil-lukealonso-minimax-m2-5-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 2 | vllm | 196608 | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1482559558084726884) |
| `discord-serve-lil-lukealonso-minimax-m2-5-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp2-797025` | lil-lukealonso-minimax-m2-5-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 2 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1483522926773797025) |
| `discord-serve-lil-lukealonso-minimax-m2-5-reap-139b-a10b-nvfp4-unpinned-dgx-spark-gb10-128gb-tp1-956090` | lil-lukealonso-minimax-m2-5-reap-139b-a10b-nvfp4--unpinned | dgx-spark-gb10-128gb 1 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1475367156328956090) |
| `discord-serve-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-273601` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1488322286347096086/1490860406053273601) |
| `discord-serve-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-876722` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1476749439065653353/1482700856334876722) |
| `discord-serve-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp4-061279` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 4 | vllm | 262144 | [msg](https://discord.com/channels/1466898002793857221/1477045884326908191/1483211706326061279) |
| `discord-serve-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp4-615248` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 4 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1488886652884615248) |
| `discord-serve-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp4-921636` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 4 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1488130116658921636) |
| `discord-serve-lil-minimaxai-minimax-m2-5-unpinned-b200-180gb-tp4-262614` | lil-minimaxai-minimax-m2-5--unpinned | b200-180gb 4 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1475489659676262614) |
| `discord-serve-lil-minimaxai-minimax-m2-5-unpinned-rtx-pro-6000-blackwell-96gb-tp4-138079` | lil-minimaxai-minimax-m2-5--unpinned | rtx-pro-6000-blackwell-96gb 4 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1471986344187138079) |
| `discord-serve-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-5090-32gb-tp8-655462` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-5090-32gb 8 | vllm | 220000 | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1496061994560655462) |
| `discord-serve-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp0-279154` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1507001523199279154) |
| `discord-serve-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-189263` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1496444195597189263) |
| `discord-serve-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-390656` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1496129038568390656) |
| `discord-serve-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-889824` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | vllm | 262144 | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1505922614235889824) |
| `discord-serve-lil-nvidia-kimi-k2-5-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp8-442503` | lil-nvidia-kimi-k2-5-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1477798264064442503) |
| `discord-serve-lil-nvidia-kimi-k2-5-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp8-759119` | lil-nvidia-kimi-k2-5-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1480579278817984553/1480579286149759119) |
| `discord-serve-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-193035` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1466898004219789502/1479147690104193035) |
| `discord-serve-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-413441` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm | 60000 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1484088438180413441) |
| `discord-serve-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0-624650` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1482164480736624650) |
| `discord-serve-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp2-556225` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 2 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1476263308242714718/1490498233829556225) |
| `discord-serve-lil-willfalco-glm-5-2-exl3-tr3-3-42bpw-unpinned-rtx-pro-6000-blackwell-96gb-tp0-645067` | lil-willfalco-glm-5-2-exl3-tr3-3-42bpw--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1532052969896284161/1533722762009645067) |
| `discord-serve-local-step-3-7-flash-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-634807` | local-step-3-7-flash-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1509994867944591552/1525129310820634807) |
| `discord-serve-lukealonso-glm-5-nvfp4-nvfp4-b200-180gb-tp0-672060` | lukealonso-glm-5-nvfp4--nvfp4 | b200-180gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1477078762951672060) |
| `discord-serve-lukealonso-glm-5-nvfp4-nvfp4-b200-180gb-tp8-050617` | lukealonso-glm-5-nvfp4--nvfp4 | b200-180gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1477326363475050617) |
| `discord-serve-lukealonso-glm-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp8-343012` | lukealonso-glm-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1473136363330343012) |
| `discord-serve-lukealonso-glm-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp8-595946` | lukealonso-glm-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1473514811353595946) |
| `discord-serve-lukealonso-glm-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp8-896987` | lukealonso-glm-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1480577372909605004/1480577378290896987) |
| `discord-serve-lukealonso-minimax-m2-7-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-015312` | lukealonso-minimax-m2-7-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | vllm | 196608 | [msg](https://discord.com/channels/1466898002793857221/1484016763124453456/1493309123394015312) |
| `discord-serve-lukealonso-minimax-m2-7-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-409898` | lukealonso-minimax-m2-7-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1484016763124453456/1507667249870409898) |
| `discord-serve-lukealonso-minimax-m2-7-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-915079` | lukealonso-minimax-m2-7-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 4 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1484016763124453456/1493173941743915079) |
| `discord-serve-moonshotai-kimi-k2-5-int4-rtx-pro-6000-blackwell-96gb-tp0-519569` | moonshotai-kimi-k2-5--int4 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1476916698035519569) |
| `discord-serve-moonshotai-kimi-k2-5-int4-rtx-pro-6000-blackwell-96gb-tp8-587028` | moonshotai-kimi-k2-5--int4 | rtx-pro-6000-blackwell-96gb 8 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1475421638668587028/1475421638668587028) |
| `discord-serve-moonshotai-kimi-k2-5-int4-rtx-pro-6000-blackwell-96gb-tp8-849765` | moonshotai-kimi-k2-5--int4 | rtx-pro-6000-blackwell-96gb 8 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1466898004219789502/1475696884029849765) |
| `discord-serve-moonshotai-kimi-k2-5-int4-rtx-pro-6000-blackwell-96gb-tp8-979578` | moonshotai-kimi-k2-5--int4 | rtx-pro-6000-blackwell-96gb 8 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1495352244344979578) |
| `discord-serve-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-dgx-spark-gb10-128gb-tp4-868457` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | dgx-spark-gb10-128gb 4 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1474777653255868457) |
| `discord-serve-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-238973` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1482012371475238973) |
| `discord-serve-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp4-100911` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 4 | sglang | 128000 | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1480294386570100911) |
| `discord-serve-nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp8-889919` | nvidia-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 8 | sglang | 262144 | [msg](https://discord.com/channels/1466898002793857221/1471459991734059050/1480288802864889919) |
| `discord-serve-nvidia-qwen3-6-27b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-059560` | nvidia-qwen3-6-27b-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1525278827822059560) |
| `discord-serve-nvidia-qwen3-6-35b-a3b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-194230` | nvidia-qwen3-6-35b-a3b-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1511015211816194230) |
| `discord-serve-qwen-qwen3-5-27b-q4-k-xl-rtx-5090-32gb-tp2-110757` | qwen-qwen3-5-27b--q4-k-xl | rtx-5090-32gb 2 | vllm | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1487236820487110757) |
| `discord-serve-qwen-qwen3-5-35b-a3b-q4-k-xl-b200-180gb-tp0-551686` | qwen-qwen3-5-35b-a3b--q4-k-xl | b200-180gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1476647077357551686) |
| `discord-serve-qwen-qwen3-6-27b-fp8-fp8-33492-rtx-pro-6000-blackwell-96gb-tp0-955571` | qwen-qwen3-6-27b-fp8--fp8--33492 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1498365802942955571) |
| `discord-serve-qwen-qwen3-6-27b-fp8-fp8-33492-rtx-pro-6000-blackwell-96gb-tp1-300718` | qwen-qwen3-6-27b-fp8--fp8--33492 | rtx-pro-6000-blackwell-96gb 1 | vllm | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1497343885167300718) |
| `discord-serve-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp0-329432` | qwen-qwen3-6-27b--fp8 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1536816174447329432) |
| `discord-serve-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp2-937054` | qwen-qwen3-6-27b--fp8 | rtx-pro-6000-blackwell-96gb 2 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1466898004219789502/1498408653143937054) |
| `discord-serve-qwen-qwen3-8-27b-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-982150` | qwen-qwen3-8-27b--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1539712531159982150) |
| `discord-serve-qwen-qwen3-8-27b-nvfp4-rtx-pro-6000-blackwell-96gb-tp1-719667` | qwen-qwen3-8-27b--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm | 262144 | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1540080546036719667) |
| `discord-serve-unsloth-kimi-k2-6-unknown-rtx-pro-6000-blackwell-96gb-tp8-367679` | unsloth-kimi-k2-6-unknown | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1496498909634367679) |
| `discord-serve-unsloth-qwen3-8-27b-nvfp4-nvfp4-rtx-5090-32gb-tp1-063777` | unsloth-qwen3-8-27b-nvfp4--nvfp4 | rtx-5090-32gb 1 | vllm | 50688 | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1537865289902063777) |
| `discord-serve-unsloth-qwen3-8-27b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-254410` | unsloth-qwen3-8-27b-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1538031909425254410) |
| `discord-serve-xiaomimimo-mimo-v2-5-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp4-167074` | xiaomimimo-mimo-v2-5--iq2-xxs | rtx-pro-6000-blackwell-96gb 4 | sglang | 262144 | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1500984732048167074) |
| `discord-serve-z-lab-qwen3-6-27b-dflash-q4-0-rtx-pro-6000-blackwell-96gb-tp0-410794` | z-lab-qwen3-6-27b-dflash--q4-0 | rtx-pro-6000-blackwell-96gb 1 | vllm | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1497285389168410794) |
| `discord-serve-zai-org-glm-4-7-fp8-fp8-rtx-pro-6000-blackwell-96gb-tp4-309659` | zai-org-glm-4-7-fp8--fp8 | rtx-pro-6000-blackwell-96gb 4 | sglang | 200000 | [msg](https://discord.com/channels/1466898002793857221/1472638207610065111/1476991169916309659) |
| `discord-serve-zai-org-glm-5-3-flash-exl3-3-0bpw-rtx-pro-6000-blackwell-96gb-tp0-702742` | zai-org-glm-5-3-flash--exl3-3-0bpw | rtx-pro-6000-blackwell-96gb 1 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1530694138599702742) |
| `discord-vincentzed-hf-qwen3-5-397b-a17b-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-518251` | vincentzed-hf-qwen3-5-397b-a17b-nvfp4-nvfp4 | rtx-pro-6000-blackwell-96gb 4 | vllm/vllm-openai:cu130-nightly-afd089f231d714e7fd06b |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1480652737753518251) |
| `discord-willfalco-glm-5-2-exl3-tr3-3-25bpw-exl3-rtx-pro-6000-blackwell-96gb-tp0-390140` | willfalco-glm-5-2-exl3-tr3-3-25bpw-exl3 | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm749050e-si811 |  | [msg](https://discord.com/channels/1466898002793857221/1532052969896284161/1532679248425390140) |
| `discord-xiaomimimo-mimo-v2-5-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0` | xiaomimimo-mimo-v2-5--iq2-xxs | rtx-pro-6000-blackwell-96gb 1 | kcramp858/mimo-m2.5-stable:2026-05-12 |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1504005602458734602) |
| `discord-xiaomimimo-mimo-v2-5-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0-747923` | xiaomimimo-mimo-v2-5--iq2-xxs | rtx-pro-6000-blackwell-96gb 4 | cstechdev/vllm:eldritch-enlightenment-mimo25-dflash- |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1523184672643747923) |
| `discord-xiaomimimo-mimo-v2-5-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp4-946766` | xiaomimimo-mimo-v2-5--iq2-xxs | rtx-pro-6000-blackwell-96gb 4 | lukealonso/sglang-cuda13-b12x:noloop |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1502296914865946766) |
| `discord-z-lab-qwen3-6-27b-dflash-q4-0-rtx-pro-6000-blackwell-96gb-tp1-948414` | z-lab-qwen3-6-27b-dflash--q4-0 | rtx-pro-6000-blackwell-96gb 1 | repne/vllm | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1511523879598948414) |
| `discord-zai-org-glm-4-7-fp8-fp8-b200-180gb-tp4-723166` | zai-org-glm-4-7-fp8--fp8 | b200-180gb 4 | lmsysorg/sglang:dev-cu13 | 200000 | [msg](https://discord.com/channels/1466898002793857221/1472638207610065111/1472974673120723166) |

## Extended in place

Records the registry already had that this pass added Discord evidence or notes to:

- `lil-blackwell-llm-docker-examples-docker-compose-ds41-jovian-judgement-r36-ds41`  discord-sweep-r36-numbers
- `lil-blackwell-llm-docker-examples-docker-compose-ds41-jovian-judgement-r37-ds41`  discord-sweep-r37-numbers

## Numbers reported in Discord

`72` speed sweeps carry numbers posted in the server. Each one names the recipe it belongs to, the Discord message, the
poster, and the poster's own wording for the row it measures. They are not acceptance evidence (`accepted_at` is null), so the
recipes they hang off stay `candidate`.

| recipe | sweeps |
|---|---|
| `discord-lil-lukealonso-glm-5-1-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp8-376496` | 17 |
| `discord-ds41-flash-jovian-judgement-r38-compose-rtxpro6000-ws-tp4` | 5 |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0` | 4 |
| `discord-willfalco-glm-5-2-exl3-tr3-3-25bpw-exl3-rtx-pro-6000-blackwell-96gb-tp0-390140` | 4 |
| `discord-lil-willfalco-glm-5-2-exl3-tr3-3-36bpw-unpinned-rtx-pro-6000-blackwell-96gb-tp0` | 4 |
| `discord-lil-lukealonso-glm-5-2-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0` | 4 |
| `discord-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp1-207424` | 3 |
| `discord-deepseek-ai-deepseek-v4-flash-dspark-fp8-rtx-pro-6000-blackwell-96gb-tp0-418546` | 3 |
| `lfm25-26b-bf16-rtxpro4500-sglang-tp1` | 3 |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0-267250` | 2 |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-641376` | 2 |
| `glm-5-3-exl3-tr3-3-0bpw-rtx-pro-6000-blackwell-96gb-vllm-tp4` | 2 |
| `discord-serve-lil-willfalco-glm-5-2-exl3-tr3-3-42bpw-unpinned-rtx-pro-6000-blackwell-96gb-tp0-645067` | 2 |
| `discord-madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid-nvfp4-rtx-pro-6000-blackwell-96gb-tp0-471084` | 1 |

## Serving settings and capabilities, read from the posts themselves

`enrich_serving.py` fills each record's `serving` and `capabilities` from its own launch arguments and environment:
KV cache dtype, batched tokens, chunked prefill, speculative method and depth, attention and MoE backends, GPU memory
utilisation, block size, prefix caching, context-parallel settings, vision limits, and the tool-call and reasoning parsers
(a record claims `tools` or `reasoning` only when its own launch names the corresponding parser). Every filled field carries a
fact whose note says it was read from the launch the poster published. 90 records gained fields in the last run.

Capabilities come from evidence too: `chat` and `vision` from the checkpoint's Hugging Face pipeline tag
(`enrich_capabilities.py`; `image-text-to-text` is what makes a record vision-capable), `tools` and `reasoning` only when the
launch itself names a tool-call or reasoning parser. Current counts: chat 185, vision 65, reasoning 70, tools 67 of 185 records.

## Prod checks (run on this machine, no GPUs touched)

- Hugging Face revisions resolve: `deepseek-ai/DeepSeek-V4.1-Flash` revision `dba1be0a` is the repository HEAD (`/api/models/.../revision/`  200).
- Image digests resolve: `lmsysorg/sglang@sha256:c4ca6511` and `cdea1bdb` (200 on Docker Hub, digest recomputed from the manifest).
- `localinferencelab/vllm` tags `jovian-judgement-community-20260912-r36`, `-r37`, `-r38` resolve on Docker Hub; the digests are
  pinned in the records (`sha256:23ab683d`, `sha256:88cd24e6`, `sha256:f41ca8bb`).
- **Failed**: `ghcr.io/local-inference-lab/vllm:jovian-judgement-beta` and `:jovian-judgement-beta-20260917-9b2a25a581e55533`, the tags
  two members launched with, are not anonymously pullable (404 on ghcr.io, and not on Docker Hub either). The records keep the tag and
  say so rather than inventing a digest.
- **Failed**: `lmsysorg/sglang@sha256:c4ca6511` is the base Lavd pinned, but JCartu's measured builds were local derived image IDs
  (`sha256:0bf6fb28`, `sha256:5730155e`), which are not pullable. His numbers therefore hang off a reference record.

### Weight fit against the stated hardware

For every record: the size of the weight files at the pinned revision (Hugging Face API, `?blobs=true`) against
`hardware_count x VRAM`. `over` means the weights alone exceed aggregate VRAM, so the launch necessarily relies on the
host-RAM or NVMe offload it configures (Engram tables, expert offload); `fits` means they fit with room for the KV pool.

| record | weights GB | card VRAM GB | verdict |
|---|---|---|---|
| `discord-compose-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pr` | 595.2 | 768 | fits |
| `discord-compose-lukealonso-mimo-v2-5-nvfp4-nvfp4-rtx-pro-600` | 183.5 | 384 | fits |
| `discord-compose-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-` | 55.6 | 192 | fits |
| `discord-ds41-flash-1m-context-dspark-docker-rtxpro6000-ws-tp` | 510.3 | 384 | over |
| `discord-ds41-flash-jovian-judgement-beta-docker-rtxpro6000-w` | 510.3 | 384 | over |
| `discord-ds41-flash-jovian-judgement-r38-compose-rtxpro6000-w` | 510.3 | 384 | over |

`3` records fit in VRAM outright; `3` need offload by construction.

### Launch failures members reported (kept as notes on the records)

- R36 compose on a host with mismatched NVIDIA userspace: `failed to fulfil mount request:  libnvidia-egl-wayland2.so.1.0.1` (kumioko, 2026-09-17).
- 1M-context beta launch logs `No module named 'triton_kernels.matmul_ogs'` and then serves normally; a second member confirmed the same line
  (mathppp, grumm, 2026-09-18).
- Compose defaults vs. env-var launches: `runtime/profiles/ds41-flash.yaml` keys are not read by the shipped launch scripts (kumioko, 2026-09-17).

## Not encoded (and why)

The server holds far more posted launches than this branch encodes. What is missing and why:

| reason | count (summed over passes) | what it means |
|---|---|---|
| no model repository | 0 | the checkpoint is a local directory (`/model`, `/models/...`) and the post never names a Hub repository |
| no repo | 0 | same, for messages that carry numbers or a bare serve command |
| no image | 0 | the launch reads its image from an env var set elsewhere, or is an arg list without a `docker run` |
| no hardware | 0 | neither the message nor the same author's nearby messages state the rig |
| no hardware stated | 0 | same, for attachments |
| ambiguous | 0 | more than one repository or recipe could match, so nothing is claimed |
| duplicate | 0 | the same image/hardware/tensor-parallel signature is already a record |

Counts are summed over the extraction passes, so a single message can appear under more than one reason.

Those messages are all in the dump; the highest-value clusters to encode next are the `voipmonitor/vllm:*`
Gilded Gnosis / Infernal Invocation families (ds4-flash and glm53 channels), the Qwen3.5/3.6 launch zoo in `#qwen-other`,
and the `#kimi-k2x`, `#minimax-*`, `#xiaomi-mimo` threads whose compose files are on disk.

## What is left, measured

`accounting.py` walks the dump and reports (a) the skip census summed over every extraction pass and (b) how many
launch-shaped messages are still without a record, split by which facts the post itself supplies.

| launch-shaped messages with... | count | what it means |
|---|---|---|
| repo=False,hw=False,image=False | 1446 | prose that mentions a flag, benchmark output, or a fragment: no checkpoint, no rig, no image in the post |
| repo=False,hw=False,image=True | 277 | an image tag but neither checkpoint nor rig |
| repo=False,hw=True,image=False | 106 | a rig but no checkpoint and no image |
| repo=False,hw=True,image=True | 56 | rig and image, checkpoint still only on the poster's disk |
| repo=True,hw=False,image=False | 45 | checkpoint only |
| repo=True,hw=False,image=True | 41 | checkpoint and image, rig never stated by that author |
| repo=True,hw=True,image=False | 3 | checkpoint and rig, no image (and no fenced command to quote) |
| repo=True,hw=True,image=True | 1 | complete, and already represented |

Residual total: **1975** launch-shaped messages. Represented by a record: **186**.

Skip census summed over the passes (a message can appear under several reasons):

| reason | count |
|---|---|
| no-numbers | 237588 |
| no-repo | 3786 |
| author-named-several-rigs | 1673 |
| no-hardware | 1469 |
| several-rigs-in-window | 986 |
| no-model-repository | 463 |
| no-image | 225 |
| no-hardware-stated | 93 |
| duplicate | 93 |
| ambiguous | 26 |

## Precision handling

Two records were removed after review because their source message is client code or a benchmark monitor rather
than a launch, and three earlier ones that merely asked for a command were removed the same way. A stricter
automated gate (require a whole command in one fence) was tested and rejected: it also discards real posts whose
command is split across lines or shown as a compose fragment, so the branch keeps the message as the audit trail
for every record instead.

## Counts

| thing | count |
|---|---|
| messages read | 240323 |
| channels in guild / read | 111 / 88 |
| threads enumerated / scraped | 471 / 508 |
| text attachments downloaded | 931 |
| recipes added (this branch) | 190 |
| of which executable launches | 123 |
| speed sweeps added | 72 |
| existing records extended | 2 |

## What is not verified

- No launch in this branch was executed: the four DGX Sparks and pop-os were off limits, and none of the other rigs are here.
  Every record is `candidate` for exactly that reason; `scripts/trust.py` agrees.
- Numbers are the posters' own, on their own rigs, with their own clocks; row labels keep their wording and the message link.
  They were not re-measured, and the memory arithmetic behind them was not recomputed per rig.
- Per-flag verification against the pinned engine version was NOT performed. We tried matching launch flags against
  the engines' public sources and the check is not sound: vLLM defines its OpenAI-server flags across several files, and
  SGLang generates them from a dataclass, so absence from one file proves nothing. Most of these images also carry forks
  (`B12X_*`, `VLLM_EXL3_*`, DSpark/DFlash options) whose flag sets are not public. Flags are therefore kept verbatim with
  the message as their source and nothing more is claimed about them.
- The nine VIP/moderation channels were unreachable (403) and are not represented.

