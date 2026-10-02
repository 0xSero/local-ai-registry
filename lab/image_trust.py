#!/usr/bin/env python3
"""Verify newly introduced image digests; existing pins are not retroactively trusted."""
import argparse
import json
import re
import subprocess

# image -> (repo, workflow, source ref as a regex). llama.cpp publishes its release images (server-cuda12-bNNNN) from the
# release tag, and its nightly images from master; both are the upstream docker.yml on the upstream repo.
BUILDERS = {
    "ghcr.io/0xsero/exl3xpu": ("0xSero/exl3xpu", "release-image.yml", "refs/heads/main"),
    "ghcr.io/ggml-org/llama.cpp": ("ggml-org/llama.cpp", "docker.yml", "refs/(?:heads/master|tags/b[0-9]+)"),
    **{f"ghcr.io/0xsero/{name}": ("0xSero/local-ai-images", "release-image.yml", "refs/heads/main")
       for name in ("gateway", "sglang-exl3", "sglang-exl3-flashnext", "sglang-exl3-xpu-flashnext", "tabbyapi-exl3")},
}
PATHS = ["registry/engines", "registry/launches", "plugin/v2/recipes.json"]


def git(*args):
    return subprocess.check_output(["git", *args], text=True)


def images(ref):
    found = set()
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "image" and isinstance(child, str):
                    found.add(re.sub(r":[^/@]+(?=@sha256:)", "", child))
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for path in git("ls-tree", "-r", "--name-only", ref, "--", *PATHS).splitlines():
        if path.endswith(".json"):
            visit(json.loads(git("show", f"{ref}:{path}")))
    return found


def verify(image, run=subprocess.run):
    match = re.fullmatch(r"([^@]+)@sha256:[0-9a-f]{64}", image)
    if not match or match[1] not in BUILDERS:
        raise ValueError(f"No approved pinned builder for {image}; publish through an approved workflow")
    repo, workflow, ref = BUILDERS[match[1]]
    identity = f"^https://github.com/{re.escape(repo)}/\\.github/workflows/{re.escape(workflow)}@{ref}$"
    run(["gh", "attestation", "verify", "oci://" + image, "--repo", repo,
         "--cert-identity-regex", identity, "--deny-self-hosted-runners"],
        check=True, timeout=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    # A missing base must fail closed, not silently grandfather new images.
    added = images(args.head) - images(args.base)
    for image in sorted(added):
        verify(image)
    print(f"Image trust: verified {len(added)} new image(s); unchanged pins are grandfathered")


if __name__ == "__main__":
    main()
