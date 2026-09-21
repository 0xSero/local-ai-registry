# DeepSeek-V4.1-Flash on 4x DGX Spark (GB10) — recipe lifecycle runner.
#
# This image does NOT serve the model. It is the operator that drives the whole lifecycle on the
# head node: check the fleet, obtain weights, obtain/build the engine image on every node, pack the
# Engram shards, publish the checkpoint, serve, smoke-test and tear down.
#
# It contains NO credentials. The ssh key that reaches the worker nodes is mounted at run time.
#
# It must run on the head node with the host Docker socket, because the serving containers it
# launches are ordinary host containers. Consequently every host path it passes through to those
# containers (weights, Engram, state) MUST be mounted here at the SAME path as on the host.
#
#   docker run --rm -it --network host \
#     -v /var/run/docker.sock:/var/run/docker.sock \
#     -v "$HOME/.ssh/id_ed25519:/run/secrets/fleet_key:ro" \
#     -v /var/lib/dsv41:/var/lib/dsv41 \
#     -v "$MODEL_DIR:$MODEL_DIR" \
#     --env-file ./site.env \
#     ghcr.io/0xsero/dsv41-4xspark-recipe:<tag> up
#
# arm64 only: GB10 is aarch64 and the engine image is linux/arm64.

FROM debian:bookworm-slim

ARG UPSTREAM_REPO=https://github.com/knapcio/DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4
# Pinned upstream commit. Changing this changes the recipe and must be re-measured.
ARG UPSTREAM_SHA=a544a0f1d00fc46d595e8a52766fec0dbefee5f8
ARG DOCKER_CLI_VERSION=5:27.3.1-1~debian.12~bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    RECIPE_ROOT=/opt/recipe \
    PATH=/opt/recipe/bin:$PATH

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        bash ca-certificates curl git gnupg jq openssh-client patch python3 python3-pip \
        python3-venv rsync iproute2 procps; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg; \
    chmod a+r /etc/apt/keyrings/docker.gpg; \
    echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends docker-ce-cli="${DOCKER_CLI_VERSION}"; \
    rm -rf /var/lib/apt/lists/*

# huggingface_hub supplies the `hf` CLI that the recipe's download step requires.
RUN pip install --no-cache-dir --break-system-packages "huggingface_hub[cli]==0.35.3"

# Pinned upstream recipe. Cloned rather than vendored so provenance stays verifiable and upstream
# keeps its own licence.
RUN set -eux; \
    git clone --filter=blob:none "${UPSTREAM_REPO}" "${RECIPE_ROOT}/upstream"; \
    cd "${RECIPE_ROOT}/upstream"; \
    git checkout --detach "${UPSTREAM_SHA}"; \
    git rev-parse HEAD > "${RECIPE_ROOT}/UPSTREAM_SHA"; \
    rm -rf "${RECIPE_ROOT}/upstream/.git"

# Local deltas measured on this fleet. See patches/README.md for what each one is and why.
COPY patches/ ${RECIPE_ROOT}/patches/
RUN set -eux; \
    cd "${RECIPE_ROOT}/upstream"; \
    for p in "${RECIPE_ROOT}"/patches/*.patch; do \
        [ -e "$p" ] || continue; \
        echo "applying $(basename "$p")"; \
        patch -p1 --forward --batch < "$p"; \
    done

COPY adaptive-verify/ ${RECIPE_ROOT}/adaptive-verify/
COPY bin/ ${RECIPE_ROOT}/bin/
COPY site.env.example ${RECIPE_ROOT}/site.env.example
RUN chmod +x ${RECIPE_ROOT}/bin/*

LABEL org.opencontainers.image.title="DeepSeek-V4.1-Flash 4x DGX Spark TP4 recipe runner" \
      org.opencontainers.image.description="Lifecycle operator for the tuned TP4/EP2 DeepSeek-V4.1-Flash stack on four DGX Sparks" \
      org.opencontainers.image.licenses="Apache-2.0" \
      ai.localregistry.recipe="deepseek-v4-1-flash-native-dgxspark-sglang-tp4-tuned" \
      ai.localregistry.upstream.sha="${UPSTREAM_SHA}"

ENTRYPOINT ["/opt/recipe/bin/dsv41"]
CMD ["help"]
