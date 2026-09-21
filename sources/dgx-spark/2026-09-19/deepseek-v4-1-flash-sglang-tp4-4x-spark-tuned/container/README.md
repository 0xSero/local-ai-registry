# Lifecycle container for the tuned 4x DGX Spark DeepSeek-V4.1-Flash recipe

This image is the **operator** for the recipe, not the server. It runs on the head node and drives
the whole lifecycle: check the fleet, obtain the weights, obtain and build the engine image on every
node, stage the adaptive-verify patch, pack the Engram shards, publish the checkpoint, serve,
smoke-test, tear down.

It exists because the recipe is not a single `docker run`. It is four nodes, a 476 GiB checkpoint, a
locally built engine overlay, per-rank Engram shards packed on NVMe, and a six-file patch that has to
be present on all four nodes. Reproducing that by hand from a README is where the mistakes happen.

## What it is not

It is **not** the serving container, and this recipe is therefore still registered as
`launch.kind: "script"` rather than `"docker"`. Two reasons:

1. The engine image (`dsv41-4x-spark:canary-roce`, 33.5 GB) is built locally from
   `lmsysorg/sglang:dev-dsv41` plus the Engram overlay. Until that image is published and
   digest-pinned, a `kind: "docker"` record cannot satisfy
   `scripts/validate_registry.py:219-266`, which requires `launch.image` to end in
   `@sha256:<64hex>` when `container.state` is `digest-pinned`.
2. This operator needs the host Docker socket, and `scripts/check_plugin_gate.py:35-56` restricts
   validated docker mounts to `${MODEL_ROOT}`, `${CACHE_ROOT}`, the HF cache and `/dev/dri`. A
   socket mount would be rejected, correctly.

Publishing the engine image and adding a second, `kind: "docker"` record — one container per node
with `--nnodes 4 --node-rank ${NODE_RANK}`, in the shape of
`registry/recipe/glm53-flash-nvfp4-dgxspark-sglang-tp4.json` — is the natural follow-up. It is a
deliberate, outward-facing publish of a 33.5 GB artifact and is not done here.

## Build

```bash
docker build -t dsv41-recipe-runner:local .
```

Verified to build on `linux/arm64` (GB10). Both local patches apply cleanly to pristine upstream
`a544a0f1d00fc46d595e8a52766fec0dbefee5f8`; the build fails loudly if they ever stop applying, which
is the point of pinning rather than vendoring.

## Run

```bash
cp site.env.example site.env        # then fill in the SITE block
docker run --rm -it --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD/site.env:/etc/dsv41/site.env:ro" \
  -v "$HOME/.ssh/id_ed25519:/run/secrets/fleet_key:ro" \
  -v /var/lib/dsv41:/var/lib/dsv41 \
  -e HF_TOKEN \
  dsv41-recipe-runner:local up
```

`up` runs doctor → weights → engine → engram → publish → serve → smoke. Every verb is idempotent:
run `up` against a healthy fleet and it re-verifies and returns without touching anything.

### Two requirements that will bite you

**Paths must match the host.** The serving containers this operator launches are ordinary host
containers created through the mounted socket, so every path handed to them is resolved by the host
daemon, not inside this container. `MODEL_DIR` and `ENGRAM_DIR` must be mounted here at the *same*
path they have on the host. The entrypoint warns when `MODEL_DIR` is not visible.

**The ssh key is mounted, never baked.** This image contains no credentials. `bin/dsv41` installs
whatever is at `/run/secrets/fleet_key` to `/root/.ssh/id_ed25519` at start. Without it only
single-node verbs work.

## Weights: download, or use what is already there

`weights` is safe to run repeatedly. It considers the checkpoint complete when `config.json` exists
and at least `EXPECTED_SHARDS` (48) `model-*-of-*.safetensors` are present, and in that case
downloads nothing. Otherwise it resumes `hf download` at the pinned revision
`fb2764a5cf321eaa5070ca8f9e892818f477c16d` — about 476 GiB — and fails if the result is still short.
Pass `HF_TOKEN` if the repository is gated for your account.

## Engine

`engine` pulls `lmsysorg/sglang:dev-dsv41` on all four nodes, builds the Engram overlay, then runs
`bin/stage-adaptive`, which:

1. copies the six target files out of the built image,
2. applies `adaptive-verify/adaptive-verify.patch`,
3. refuses to continue if any file came back unchanged (a silently no-op patch is worse than a loud
   failure),
4. distributes the result to `/var/tmp/dsv41-adaptive` on every node,
5. installs the profiled SPS cost table into the state directory.

The patch is applied by bind-mount at serve time rather than baked into the image. Baking it in
would be cleaner, but the published measurements were taken with the bind-mount form, and a rebuilt
image is a different artifact that would have to be re-measured before it could carry those numbers.

## Fleets with mixed accounts

`WORKER_USERS` gives a per-node ssh account, aligned with `WORKER_HOSTS`. Upstream `start.sh` honours
this; upstream `stop.sh` did not — it used a single `WORKER_USER`, and `scripts/remote.py` accepts
only one `--user`, so `stop` silently left the engine running on every node whose account differed.
That is `patches/stop-per-node-users.patch`. Symptom, if you hit it elsewhere: the next `serve` dies
with `docker: container name "/dsv41-worker" is already in use`.

## Contents

| path | what |
|---|---|
| `Dockerfile` | arm64 operator image; clones upstream at the pinned SHA and applies `patches/` |
| `bin/dsv41` | lifecycle entrypoint |
| `bin/stage-adaptive` | derives and distributes the adaptive-verify files |
| `bin/vision_smoke.py` | one multimodal request; fails if the vision path is broken |
| `patches/start-local-patch.patch` | per-node ssh users, ssh by host name, local checkpoint copies, `EXTRA_DOCKER_ARGS` passthrough |
| `patches/stop-per-node-users.patch` | teardown reaches nodes with differing accounts |
| `adaptive-verify/` | the six-file patch and the profiled SPS cost table |
| `site.env.example` | site config; the TUNED block is measured, the SITE block is yours |
