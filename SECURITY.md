# Container image admission

CI verifies every newly introduced image reference in engine profiles, launch
profiles, and the plugin export against its parent/base revision. New images
must use SHA-256 digests and carry GitHub build attestations from the explicitly
approved repository, workflow and default branch in `lab/image_trust.py`.
Verification failures, missing attestations and timeouts fail the required
`verify` check. New publishers require a reviewed policy change. Rebuild
third-party images through an approved workflow before adding their digests.

This gate establishes build identity, not that the source is harmless. Review
Dockerfiles, dependencies, runtime downloads, mounts, devices, capabilities,
network access and entrypoints before accepting an image or launch change.
Attestation alone is not a runtime or hardware acceptance test. Changes to this
gate and its workflow require the same security review as builder changes.

Existing exact image pins are grandfathered, not retroactively verified. The
2026-09-29 audit of the ten plugin image digests verified five through GitHub
attestations; five could not be verified through their expected publishers.
Those images remain compatibility exceptions until rebuilt and hardware-tested.
The gateway and some other verified images were built on feature branches;
new digests must instead use the approved default branch. Do not describe the
catalog as fully attested, sandboxed, or free from malicious code.

Digest pinning prevents a moved tag from replacing an image. It does not stop a
running container from changing its writable layer or downloading code. Runtime
restrictions belong to the consuming controller/plugin and must be tested per
engine. In particular, model engines still need further nonroot, read-only root
filesystem and outbound-network compatibility testing.
