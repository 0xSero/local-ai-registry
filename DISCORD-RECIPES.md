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
- Pinned upstream imports (`lil-*` from `sources/local-inference-lab/2026-09-13.json`) stay evidence-free, so numbers reported in
  Discord for those images live on Discord reference records instead (`scripts/check_lil_import.py` enforces this).

## Added

| record | model | hardware | engine | context | source |
|---|---|---|---|---|---|
| `discord-0xsero-glm-5-2-nvfp4-reap-469b-nvfp4-reap-rtx-pro-6000-blackwell-96gb-tp0` | 0xsero-glm-5-2-nvfp4-reap-469b--nvfp4-reap | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:glm52-v11-darkdevotion-vllma86f74e- |  | [msg](https://discord.com/channels/1466898002793857221/1517182540853809162/1517222801688232027) |
| `discord-brandonmusic-glm-5-3-flash-tr3-4bpw-exl3-4bpw-rtx-pro-6000-blackwell-96gb-tp0` | brandonmusic-glm-5-3-flash-tr3-4bpw--exl3-4bpw | rtx-pro-6000-blackwell-96gb 1 | ghcr.io/tpurtell/glm-5.3-flash-exl3-4bpw-2x-rtx |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1547093497952084048) |
| `discord-cyankiwi-qwen3-6-27b-awq-int4-awq-dgx-spark-gb10-128gb-tp2` | cyankiwi-qwen3-6-27b-awq-int4--awq | dgx-spark-gb10-128gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm7e3bee1-si623 | 102400 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1530407673776967781) |
| `discord-deepseek-ai-deepseek-v4-1-flash-fp8-rtx-pro-6000-blackwell-96gb-tp0-339856` | deepseek-ai-deepseek-v4-1-flash--fp8 | rtx-pro-6000-blackwell-96gb 4 | ghcr.io/local-inference-lab/vllm:jovian-judgement-be |  | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1550242308459339856) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-fp8-e4m3-dgx-spark-gb10-128gb-tp0` | deepseek-ai-deepseek-v4-flash-0731--fp8-e4m3 | dgx-spark-gb10-128gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm0bc48c5-sieec |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1533021653934669945) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-dgx-spark-gb10-128gb-tp0-019956` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | dgx-spark-gb10-128gb 2 | voipmonitor/vllm:infernal-invocation-vllma7f04eb-b12 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1537546027073019956) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-dgx-spark-gb10-128gb-tp0-148804` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | dgx-spark-gb10-128gb 2 | docker.io/voipmonitor/vllm:infernal-invocation-vllm3 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1537061281285148804) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-dgx-spark-gb10-128gb-tp0-250178` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | dgx-spark-gb10-128gb 2 | voipmonitor/vllm:gilded-gnosis-v20-vllmfa13d33-b12x0 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1536002555669250178) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-dgx-spark-gb10-128gb-tp0-267250` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | dgx-spark-gb10-128gb 2 | voipmonitor/vllm:infernal-invocation-vllmf0fa1ce-b12 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1539582368745267250) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-dgx-spark-gb10-128gb-tp0-364885` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | dgx-spark-gb10-128gb 2 | voipmonitor/vllm:jovian-judgement-vllm28bc825-b12x8a |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1545345760227364885) |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-dgx-spark-gb10-128gb-tp0-489643` | deepseek-ai-deepseek-v4-flash-0731--iq2-xxs | dgx-spark-gb10-128gb 2 | voipmonitor/vllm:infernal-invocation-vllm7ed814e-b12 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1537436882336489643) |
| `discord-deepseek-ai-deepseek-v4-flash-dspark-fp8-dgx-spark-gb10-128gb-tp0` | deepseek-ai-deepseek-v4-flash-dspark--fp8 | dgx-spark-gb10-128gb 1 | voipmonitor/vllm:fathomless-firmament-v16-vllm8f86f4 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1526634100171997214) |
| `discord-deepseek-ai-deepseek-v4-flash-dspark-fp8-dgx-spark-gb10-128gb-tp0-418546` | deepseek-ai-deepseek-v4-flash-dspark--fp8 | dgx-spark-gb10-128gb 2 | voipmonitor/vllm:gilded-gnosis-v18-vllm264bce1-b12xb |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1528164614989418546) |
| `discord-deepseek-ai-deepseek-v4-flash-dspark-fp8-rtx-pro-6000-blackwell-96gb-tp0-266914` | deepseek-ai-deepseek-v4-flash-dspark--fp8 | rtx-pro-6000-blackwell-96gb 2 | vllm/ds4flash:dspark0713 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1526155667000266914) |
| `discord-ds41-flash-1m-context-dspark-docker-rtxpro6000-ws-tp4` | deepseek-ai-deepseek-v4-1-flash--fp8 | rtx-pro-6000-blackwell-96gb 4 | ghcr.io/local-inference-lab/vllm:jovian-judgement-be | 1048576 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1550426993453965384) |
| `discord-ds41-flash-jovian-judgement-beta-docker-rtxpro6000-ws-tp4` | deepseek-ai-deepseek-v4-1-flash--fp8 | rtx-pro-6000-blackwell-96gb 4 | ghcr.io/local-inference-lab/vllm:jovian-judgement-be | 131072 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1550242308459339856) |
| `discord-ds41-flash-jovian-judgement-r38-compose-rtxpro6000-ws-tp4` | deepseek-ai-deepseek-v4-1-flash--fp8 | rtx-pro-6000-blackwell-96gb 4 | localinferencelab/vllm:jovian-judgement-community-20 | 131072 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1548872593522565164) |
| `discord-lil-deepseek-ai-deepseek-v4-flash-vision-exp-unpinned-dgx-spark-gb10-128gb-tp0` | lil-deepseek-ai-deepseek-v4-flash-vision-exp--unpinned | dgx-spark-gb10-128gb 1 | voipmonitor/vllm:jovian-judgement-vllm08e1c7d-b12xd0 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1545881440439246879) |
| `discord-lil-deepseek-ai-deepseek-v4-flash-vision-exp-unpinned-dgx-spark-gb10-128gb-tp0-950730` | lil-deepseek-ai-deepseek-v4-flash-vision-exp--unpinned | dgx-spark-gb10-128gb 2 | voipmonitor/vllm:jovian-judgement-vllmf66599d-b12x15 |  | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1546923987441950730) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 1 | localinferencelab/vllm:jovian-judgement-community-20 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1548244373953847368) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-001558` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260906 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1546103275752001558) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-132362` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260901 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1544320517132132362) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-305792` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260908 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1546850663391305792) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-325016` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260908 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1546930555340325016) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-545832` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260902 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1544557486512545832) |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-641376` | lil-glm53-flash-nvfp4--46aaae8a8203 | rtx-pro-6000-blackwell-96gb 4 | voipmonitor/vllm:jovian-judgement-community-20260903 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1545156576195641376) |
| `discord-lil-local-inference-lab-glm-5-3-nvfp4-unpinned-dgx-spark-gb10-128gb-tp0` | lil-local-inference-lab-glm-5-3-nvfp4--unpinned | dgx-spark-gb10-128gb 1 | joninco/vllm:glm53-nvfp4-decode-opt-20260904-r34 |  | [msg](https://discord.com/channels/1466898002793857221/1542910591730192434/1545488541877014691) |
| `discord-lil-lukealonso-glm-5-1-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp8-376496` | lil-lukealonso-glm-5-1-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/sglang:cu130 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1491801217423376496) |
| `discord-lil-lukealonso-glm-5-2-nvfp4-unpinned-dgx-spark-gb10-128gb-tp0` | lil-lukealonso-glm-5-2-nvfp4--unpinned | dgx-spark-gb10-128gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllmfa13d33-b12x0 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1536381897301819485) |
| `discord-lil-lukealonso-glm-5-2-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp0` | lil-lukealonso-glm-5-2-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm2167295-si6a9 |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1529479030112522370) |
| `discord-lil-lukealonso-kimi-k3-qsrt-k2-3b98114115f1-rtx-pro-6000-blackwell-96gb-tp0` | lil-lukealonso-kimi-k3-qsrt-k2--3b98114115f1 | rtx-pro-6000-blackwell-96gb 1 | amygdala/vllm:kimi-k3-dcp8-flashinfer-fa2-nograph-20 |  | [msg](https://discord.com/channels/1466898002793857221/1528141816459689984/1537921009833869342) |
| `discord-lil-lukealonso-qwen3-5-397b-a17b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp4-884352` | lil-lukealonso-qwen3-5-397b-a17b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 4 | orthozany/vllm-qwen35-mtp:latest | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1481991865153884352) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-164274` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | orthozany/k26-0424-clean:v12 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1505873583338164274) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-624138` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | luke-sglang:blackwell |  | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1499410301672624138) |
| `discord-lil-moonshotai-kimi-k2-6-b5aabbfb2022-rtx-pro-6000-blackwell-96gb-tp8-790824` | lil-moonshotai-kimi-k2-6--b5aabbfb2022 | rtx-pro-6000-blackwell-96gb 8 | voipmonitor/vllm:kimi-v5-cu132-89da7631 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1495805489013985280/1508846127900790824) |
| `discord-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp1-504294` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:v0.17.1-cu130 | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1482131191338504294) |
| `discord-lil-sehyo-qwen3-5-122b-a10b-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp2-039610` | lil-sehyo-qwen3-5-122b-a10b-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 2 | vllm/vllm-openai:cu130-nightly | 186560 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1490084838815039610) |
| `discord-lil-willfalco-glm-5-2-exl3-tr3-3-36bpw-unpinned-rtx-pro-6000-blackwell-96gb-tp0` | lil-willfalco-glm-5-2-exl3-tr3-3-36bpw--unpinned | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:gilded-gnosis-v20-vllm4d006a4-b12xc |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1537224373931479110) |
| `discord-lukealonso-minimax-m2-7-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp2-185674` | lukealonso-minimax-m2-7-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 2 | lmsysorg/sglang:latest |  | [msg](https://discord.com/channels/1466898002793857221/1484016763124453456/1494191967507185674) |
| `discord-madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid-nvfp4-rtx-pro-6000-blackwell-96gb-tp0` | madeby561-glm-5-2-mxfp8-nvfp4-nf3-hybrid--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | voipmonitor/vllm:fathomless-firmament-v17-vllm6ccc3e |  | [msg](https://discord.com/channels/1466898002793857221/1523800435490820239/1527117187632992377) |
| `discord-nvidia-nvidia-nemotron-3-ultra-550b-a55b-nvfp4-nvfp4-mixed-rtx-pro-6000-blackwell-96gb-tp4-6133` | nvidia-nvidia-nemotron-3-ultra-550b-a55b-nvfp4--nvfp4-mixed | rtx-pro-6000-blackwell-96gb 4 | vllm/vllm-openai:cu130-nightly | 131072 | [msg](https://discord.com/channels/1466898002793857221/1494478683258490892/1512317209282613388) |
| `discord-nvidia-qwen3-6-35b-a3b-nvfp4-nvfp4-rtx-5090-32gb-tp1-960761` | nvidia-qwen3-6-35b-a3b-nvfp4--nvfp4 | rtx-5090-32gb 1 | repne/vllm:nvfp4-moe-n433m | 250000 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1512441417710960761) |
| `discord-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp1-207424` | qwen-qwen3-6-27b--fp8 | rtx-pro-6000-blackwell-96gb 2 | repne/vllm:latest | 262144 | [msg](https://discord.com/channels/1466898002793857221/1498094855442927698/1498094859167207424) |
| `discord-qwen-qwen3-8-flash-next-ud-iq3-xxs-rtx-pro-6000-blackwell-96gb-tp2` | qwen-qwen3-8-flash-next--ud-iq3-xxs | rtx-pro-6000-blackwell-96gb 1 | vllm/vllm-openai:qwen38-flash-next | 262144 | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1542211769131606047) |
| `discord-radixark-qwen3-8-flash-next-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp0` | radixark-qwen3-8-flash-next-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 1 | sglang-qwen38fn-sm120-turbo:r22 |  | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1546121824885280829) |
| `discord-reported-ds41-flash-r36-rtxpro6000-ws-tp4` | lil-deepseek-ai-deepseek-v4-1-flash--unpinned | rtx-pro-6000-blackwell-96gb 4 | localinferencelab/vllm:jovian-judgement-community-20 | 131072 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1548464464641134753) |
| `discord-reported-ds41-flash-r37-rtxpro6000-ws-tp4` | lil-deepseek-ai-deepseek-v4-1-flash--unpinned | rtx-pro-6000-blackwell-96gb 4 | localinferencelab/vllm:jovian-judgement-community-20 | 131072 | [msg](https://discord.com/channels/1466898002793857221/1547563567379906651/1548698823625277564) |
| `discord-sakamakismile-huihui-qwen3-6-27b-abliterated-nvfp4-mtp-nvfp4-rtx-5090-32gb-tp0` | sakamakismile-huihui-qwen3-6-27b-abliterated-nvfp4-mtp--nvfp4 | rtx-5090-32gb 1 | vllm/vllm-openai:cu129-nightly |  | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1534988203235475626) |
| `discord-serve-deepseek-ai-deepseek-v4-flash-2-bit-experts-vllm-moet-w2-fp8-kv-dgx-spark-gb10-128gb-tp2-586499` | deepseek-ai-deepseek-v4-flash--2-bit-experts-vllm-moet-w2-fp8-kv | dgx-spark-gb10-128gb 2 | vllm | 1048576 | [msg](https://discord.com/channels/1466898002793857221/1481304034198421515/1524159306822586499) |
| `discord-serve-lil-lukealonso-minimax-m2-5-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp2-726884` | lil-lukealonso-minimax-m2-5-nvfp4--unpinned | rtx-pro-6000-blackwell-96gb 2 | vllm | 196608 | [msg](https://discord.com/channels/1466898002793857221/1471906523960574269/1482559558084726884) |
| `discord-serve-lukealonso-glm-5-nvfp4-nvfp4-rtx-pro-6000-blackwell-96gb-tp8-343012` | lukealonso-glm-5-nvfp4--nvfp4 | rtx-pro-6000-blackwell-96gb 8 | sglang |  | [msg](https://discord.com/channels/1466898002793857221/1471527895439638528/1473136363330343012) |
| `discord-serve-moonshotai-kimi-k2-5-int4-rtx-pro-6000-blackwell-96gb-tp8-587028` | moonshotai-kimi-k2-5--int4 | rtx-pro-6000-blackwell-96gb 8 | vllm |  | [msg](https://discord.com/channels/1466898002793857221/1475421638668587028/1475421638668587028) |
| `discord-serve-qwen-qwen3-5-27b-q4-k-xl-rtx-5090-32gb-tp2-110757` | qwen-qwen3-5-27b--q4-k-xl | rtx-5090-32gb 2 | vllm | 262144 | [msg](https://discord.com/channels/1466898002793857221/1473975364727476224/1487236820487110757) |
| `discord-serve-unsloth-qwen3-8-27b-nvfp4-nvfp4-rtx-5090-32gb-tp1-063777` | unsloth-qwen3-8-27b-nvfp4--nvfp4 | rtx-5090-32gb 1 | vllm | 50688 | [msg](https://discord.com/channels/1466898002793857221/1528331644933767190/1537865289902063777) |
| `discord-xiaomimimo-mimo-v2-5-iq2-xxs-rtx-pro-6000-blackwell-96gb-tp0` | xiaomimimo-mimo-v2-5--iq2-xxs | rtx-pro-6000-blackwell-96gb 1 | kcramp858/mimo-m2.5-stable:2026-05-12 |  | [msg](https://discord.com/channels/1466898002793857221/1498377952981946548/1504005602458734602) |

## Extended in place

Records the registry already had that this pass added Discord evidence or notes to:

- `lil-blackwell-llm-docker-examples-docker-compose-ds41-jovian-judgement-r36-ds41`  discord-sweep-r36-numbers
- `lil-blackwell-llm-docker-examples-docker-compose-ds41-jovian-judgement-r37-ds41`  discord-sweep-r37-numbers

## Numbers reported in Discord

`48` speed sweeps carry numbers posted in the server. Each one names the recipe it belongs to, the Discord message, the
poster, and the poster's own wording for the row it measures. They are not acceptance evidence (`accepted_at` is null), so the
recipes they hang off stay `candidate`.

| recipe | sweeps |
|---|---|
| `discord-lil-lukealonso-glm-5-1-nvfp4-unpinned-rtx-pro-6000-blackwell-96gb-tp8-376496` | 17 |
| `discord-ds41-flash-jovian-judgement-r38-compose-rtxpro6000-ws-tp4` | 5 |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0` | 4 |
| `discord-qwen-qwen3-6-27b-fp8-rtx-pro-6000-blackwell-96gb-tp1-207424` | 3 |
| `lfm25-26b-bf16-rtxpro4500-sglang-tp1` | 3 |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-dgx-spark-gb10-128gb-tp0-250178` | 2 |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-641376` | 2 |
| `glm-5-3-exl3-tr3-3-0bpw-rtx-pro-6000-blackwell-96gb-vllm-tp4` | 2 |
| `discord-reported-ds41-flash-r37-rtxpro6000-ws-tp4` | 1 |
| `discord-deepseek-ai-deepseek-v4-flash-0731-iq2-xxs-dgx-spark-gb10-128gb-tp0-489643` | 1 |
| `discord-reported-ds41-flash-r36-rtxpro6000-ws-tp4` | 1 |
| `discord-lil-glm53-flash-nvfp4-46aaae8a8203-rtx-pro-6000-blackwell-96gb-tp0-132362` | 1 |
| `glm52-exl3-rtxpro6000-vllm-tp4` | 1 |
| `discord-ds41-flash-jovian-judgement-beta-docker-rtxpro6000-ws-tp4` | 1 |

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
| `discord-ds41-flash-1m-context-dspark-docker-rtxpro6000-ws-tp` | 510.3 | 384 | over |
| `discord-ds41-flash-jovian-judgement-beta-docker-rtxpro6000-w` | 510.3 | 384 | over |
| `discord-ds41-flash-jovian-judgement-r38-compose-rtxpro6000-w` | 510.3 | 384 | over |

`0` records fit in VRAM outright; `3` need offload by construction.

### Launch failures members reported (kept as notes on the records)

- R36 compose on a host with mismatched NVIDIA userspace: `failed to fulfil mount request:  libnvidia-egl-wayland2.so.1.0.1` (kumioko, 2026-09-17).
- 1M-context beta launch logs `No module named 'triton_kernels.matmul_ogs'` and then serves normally; a second member confirmed the same line
  (mathppp, grumm, 2026-09-18).
- Compose defaults vs. env-var launches: `runtime/profiles/ds41-flash.yaml` keys are not read by the shipped launch scripts (kumioko, 2026-09-17).

## Not encoded (and why)

The server holds far more posted launches than this branch encodes. What is missing and why:

| reason | count | what it means |
|---|---|---|
| attachment carries no resolvable image | 62 messages | the launch reads its image from an env var set elsewhere, or is an arg list without a `docker run` |
| no model repository in the message or file | 492 messages | the checkpoint lives on the poster's disk (`/model`, `/models/...`) and is named only in the image tag |
| hardware not stated in the message | 61 messages | in a thread the rig is assumed, not written down |
| already covered by an existing record | remainder | the same image/hardware/TP signature is already in the registry |

Those messages are all in the dump; the highest-value clusters to encode next are the `voipmonitor/vllm:*`
Gilded Gnosis / Infernal Invocation families (ds4-flash and glm53 channels), the Qwen3.5/3.6 launch zoo in `#qwen-other`,
and the `#kimi-k2x`, `#minimax-*`, `#xiaomi-mimo` threads whose compose files are on disk.

## Counts

| thing | count |
|---|---|
| messages read | 240323 |
| channels in guild / read | 111 / 88 |
| threads enumerated / scraped | 471 / 508 |
| text attachments downloaded | 931 |
| recipes added (this branch) | 55 |
| of which executable launches | 47 |
| speed sweeps added | 48 |
| existing records extended | 2 |

## What is not verified

- No launch in this branch was executed: the four DGX Sparks and pop-os were off limits, and none of the other rigs are here.
  Every record is `candidate` for exactly that reason; `scripts/trust.py` agrees.
- Numbers are the posters' own, on their own rigs, with their own clocks; row labels keep their wording and the message link.
  They were not re-measured, and the memory arithmetic behind them was not recomputed per rig.
- Flags were kept verbatim from the messages; they were not diffed against each pinned engine version's `--help`,
  because most of these images carry forks (`B12X_*`, `VLLM_EXL3_*`) whose flag sets are not in any public tree yet.
- The nine VIP/moderation channels were unreachable (403) and are not represented.

