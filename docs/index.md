# Local AI Registry

**One question:** what should I run on the machine I own?

**One answer per machine.** The registry maps a hardware id to one validated recipe: an exact model revision, an exact engine image digest, the launch arguments, and the measured evidence that it ran and answered.

Read in order:

1. **This page**, two minutes. What it is and why it is shaped this way.
2. [System and schema](system.md), five minutes. The collections, how they link, and what `validated` means.
3. [Deep breakdown](deep.md). Every rule, every script, how a recipe moves from candidate to recommended.
4. [Contributing](https://github.com/0xSero/local-ai-registry/blob/main/CONTRIBUTING.md). How to add hardware, a recipe, or evidence.

## Why a registry

The hard part of local inference is not downloading a model. A working setup is a tested combination of exact hardware, model revision and weight format, inference engine and version, container image digest, launch arguments, context and concurrency ceilings, and measured correctness and speed. Those combinations are expensive to discover and easy to get subtly wrong. The registry preserves them as immutable recipes so no one has to rediscover them.

## Three rules

- **Policy lives in the registry; execution lives in the recipe; experience lives in the client.** The registry never runs anything. A client (the Omarchy plugin, a CLI, a website) reads a recipe and decides whether this machine can run it right now.
- **`validated` is derived, never asserted.** A recipe is validated when, and only when, the record itself proves it: pinned revision, pinned image, an acceptance run or a commit-pinned campaign sweep, no forbidden flags. Anyone can rerun `scripts/trust.py` and get the same answer.
- **A blank metric means unmeasured, never zero.** Imported observations from LocalMaxxing, local.ai, and mlx.fast are kept as `candidate` compatibility evidence. They are useful. They are not a promise.

## Where it is used

- **Omarchy plugin**: one bar button. Detects the GPU, loads the recommended recipe, proves a real completion, hands the endpoint to every installed coding agent.
- **local.ai**: the public benchmark site, which measures the Apple side and can read the same recommendation file.
- **Anything else** that speaks HTTP: `GET /api/v1/recommendations` returns the whole contract in one request.

Source: [github.com/0xSero/local-ai-registry](https://github.com/0xSero/local-ai-registry). Browser: [local-ai-registry.vercel.app](https://local-ai-registry.vercel.app).
