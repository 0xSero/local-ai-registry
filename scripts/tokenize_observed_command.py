#!/usr/bin/env python3
"""Tokenize observed source shell strings into metadata, not the launch contract.

Candidate recipes stay `launch.kind: "reference"`. Derived argv is stored at
`metadata.<source>.tokenized` beside `observed_command`. Lossy splits emit
fidelity=lossy and no tokens. This never writes image/mounts/ports onto a
reference launch and never invents a validated contract.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path


# Fields that belong on a docker/native contract, never on a reference launch.
REFERENCE_LAUNCH_FORBIDDEN = (
    "arguments",
    "container_port",
    "endpoint",
    "entrypoint",
    "environment",
    "host_port",
    "image",
    "ipc",
    "mounts",
    "network_mode",
    "notes",
    "served_model_name",
    "shm_size",
    "steps",
)

ENV_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
REMOTE_ENDPOINT = re.compile(
    r"Remote endpoint:\s*(\S+)(?:\s+servedModel:\s*(\S+))?",
    re.I,
)
ENV_COMMENT = re.compile(r"^#\s*env:\s*(.+)$", re.I)
WINDOWS_SHELL = re.compile(r"\\|\.exe\b|\^", re.I)
DANGEROUS_IN_TOKEN = re.compile(r"\$\(|`|\$\(\(")
SHELL_ONLY_TOKENS = {";", "|", ">", "<", "^", "&&"}
PRIMARY_HEAD = {
    "hipfire",
    "llama-bench",
    "llama-cli",
    "llama-perplexity",
    "llama-server",
    "lms",
    "mlx",
    "ollama",
    "python",
    "python3",
    "sglang",
    "vllm",
}


@dataclass
class ParsedCommand:
    arguments: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    steps: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    endpoint: str | None = None
    served_model_name: str | None = None
    fidelity: str = "faithful"


def windows_shell(text: str) -> bool:
    return bool(WINDOWS_SHELL.search(text))


def safe_split(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("& "):
        stripped = stripped[2:].strip()
    posix = not windows_shell(stripped)
    try:
        tokens = shlex.split(stripped, posix=posix)
    except ValueError:
        try:
            tokens = shlex.split(stripped, posix=not posix)
        except ValueError:
            tokens = stripped.split()
    return [token for token in tokens if token and token != "&"]


def split_operators(text: str, operators: tuple[str, ...]) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        matched = next((op for op in operators if text.startswith(op, i)), None)
        if matched:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            i += len(matched)
            continue
        buf.append(ch)
        i += 1
    part = "".join(buf).strip()
    if part:
        parts.append(part)
    return parts


def join_continuations(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\\[ \t]*\n[ \t]*", " ", text)
    text = re.sub(r"`[ \t]*\n[ \t]*", " ", text)
    text = re.sub(r"\^[ \t]*\n[ \t]*", " ", text)
    return text


def peel_env(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    environment: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        match = ENV_ASSIGN.match(tokens[index])
        if not match:
            break
        environment[match.group(1)] = match.group(2)
        index += 1
    return tokens[index:], environment


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def chunk_is_lossy(original: str, tokens: list[str]) -> bool:
    if not tokens:
        return bool(collapse(original))
    if any(token in SHELL_ONLY_TOKENS or DANGEROUS_IN_TOKEN.search(token) for token in tokens):
        return True
    if "\\" in original and "\\" not in "".join(tokens):
        return True
    if any(token == "^" for token in tokens):
        return True
    if tokens[0].startswith("-") and not original.lstrip().startswith(("-", "'", '"')):
        return True
    words = original.split()
    return len(tokens) == 1 and len(words) > 3


def take_env_tokens(text: str, parsed: ParsedCommand) -> None:
    for token in safe_split(text):
        match = ENV_ASSIGN.match(token)
        if match:
            parsed.environment[match.group(1)] = match.group(2)


def parse_comment(line: str, parsed: ParsedCommand) -> None:
    remote = REMOTE_ENDPOINT.search(line)
    if remote:
        parsed.endpoint = remote.group(1)
        if remote.group(2):
            parsed.served_model_name = remote.group(2)
        return
    env_line = ENV_COMMENT.match(line)
    if env_line:
        take_env_tokens(env_line.group(1), parsed)
        return
    note = re.sub(r"^#\s*", "", line).strip()
    if note:
        parsed.notes.append(note)


def is_primary(tokens: list[str]) -> bool:
    if not tokens:
        return False
    head = Path(tokens[0]).name.lower()
    return head in PRIMARY_HEAD or "serve" in head or "server" in head or head.startswith("llama")


def parse_observed_command(raw: str | None) -> ParsedCommand:
    parsed = ParsedCommand()
    if not isinstance(raw, str) or not raw.strip():
        return parsed
    text = join_continuations(raw)
    command_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("["):
            parsed.notes.append(stripped)
            continue
        if stripped.startswith("#"):
            parse_comment(stripped, parsed)
            continue
        command_lines.append(stripped)
    argv_steps: list[list[str]] = []
    lossy = False
    for line in command_lines:
        for chunk in split_operators(line, ("&&",)):
            tokens, environment = peel_env(safe_split(chunk))
            reconstructed = [f"{key}={value}" for key, value in environment.items()] + tokens
            if chunk_is_lossy(chunk, reconstructed if reconstructed else tokens):
                lossy = True
                continue
            parsed.environment.update(environment)
            if tokens:
                argv_steps.append(tokens)
    if lossy:
        parsed.fidelity = "lossy"
        parsed.arguments = []
        parsed.steps = []
        parsed.environment = {}
        return parsed
    parsed.steps = argv_steps
    if not argv_steps:
        return parsed
    primary = next((step for step in reversed(argv_steps) if is_primary(step)), argv_steps[-1])
    parsed.arguments = primary
    if len(argv_steps) == 1:
        parsed.steps = []
    return parsed


def tokenized_record(parsed: ParsedCommand) -> dict:
    record: dict = {"fidelity": parsed.fidelity}
    if parsed.fidelity != "faithful":
        return record
    if parsed.arguments:
        record["arguments"] = parsed.arguments
    if parsed.environment:
        record["environment"] = parsed.environment
    if parsed.steps:
        record["steps"] = parsed.steps
    if parsed.notes:
        record["notes"] = parsed.notes
    if parsed.endpoint:
        record["endpoint"] = parsed.endpoint
    if parsed.served_model_name:
        record["served_model_name"] = parsed.served_model_name
    return record


def strip_reference_launch(launch: dict) -> bool:
    changed = False
    for key in REFERENCE_LAUNCH_FORBIDDEN:
        if key in launch:
            launch.pop(key)
            changed = True
    return changed


def metadata_source_key(recipe: dict) -> str | None:
    source = recipe.get("recipe_source")
    if source == "mlxfast":
        return "mlxfast"
    if source == "localmaxxing":
        return "localmaxxing"
    return None


def observed_snippet(recipe: dict) -> str | None:
    key = metadata_source_key(recipe)
    if not key:
        return None
    block = (recipe.get("metadata") or {}).get(key)
    if isinstance(block, dict):
        command = block.get("observed_command")
        if isinstance(command, str) and command.strip():
            return command
    return None


def apply_to_recipe(recipe: dict) -> bool:
    key = metadata_source_key(recipe)
    if not key:
        return False
    changed = False
    launch = recipe.setdefault("launch", {})
    if isinstance(launch, dict) and strip_reference_launch(launch):
        changed = True
    snippet = observed_snippet(recipe)
    block = recipe.setdefault("metadata", {}).setdefault(key, {})
    if not isinstance(block, dict):
        return changed
    record = tokenized_record(parse_observed_command(snippet)) if snippet else None
    if record != block.get("tokenized"):
        if record:
            block["tokenized"] = record
        else:
            block.pop("tokenized", None)
        changed = True
    return changed


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def apply_registry(root: Path) -> tuple[int, int, int]:
    updated = 0
    faithful = 0
    lossy = 0
    for path in sorted((root / "recipe").glob("*.json")):
        recipe = json.loads(path.read_text())
        if apply_to_recipe(recipe):
            write(path, recipe)
            updated += 1
        key = metadata_source_key(recipe)
        if not key:
            continue
        tokenized = ((recipe.get("metadata") or {}).get(key) or {}).get("tokenized") or {}
        if tokenized.get("fidelity") == "lossy":
            lossy += 1
        elif tokenized.get("fidelity") == "faithful":
            faithful += 1
    return updated, faithful, lossy


def _self_check() -> None:
    env = parse_observed_command(
        "VLLM_NVFP4_GEMM_BACKEND=cutlass vllm serve /models/Qwen --port 8000 --max-model-len 4096"
    )
    assert env.fidelity == "faithful"
    assert env.environment == {"VLLM_NVFP4_GEMM_BACKEND": "cutlass"}
    assert env.arguments[:2] == ["vllm", "serve"]

    chain = parse_observed_command(
        "git clone https://github.com/Layr-Labs/mlxfast-gemma4-26b-a4b-engine && ./tools/fetch-benchd.sh && ./setup.sh && ./setup-gemma4-assistant.sh"
    )
    assert chain.fidelity == "faithful"
    assert chain.steps[0] == ["git", "clone", "https://github.com/Layr-Labs/mlxfast-gemma4-26b-a4b-engine"]
    assert chain.steps[-1] == ["./setup-gemma4-assistant.sh"]

    remote = parse_observed_command("# Remote endpoint: http://127.0.0.1:1235  servedModel: microsoft/phi-4-reasoning-plus")
    assert remote.fidelity == "faithful"
    assert remote.endpoint == "http://127.0.0.1:1235"
    assert not remote.arguments

    docker = parse_observed_command(
        "docker run --gpus all --ipc=host -e CUTE_DSL_ARCH=sm_120a -v /models:/model:ro vllm/vllm-openai:cu13 --model /model"
    )
    assert docker.fidelity == "faithful"
    assert docker.arguments[0] == "docker"
    assert docker.arguments[1] == "run"

    windows = parse_observed_command(
        r"C:\llama.cpp\build\bin\Release\llama-server.exe ^"
        "\n  --model C:\\models\\foo.gguf ^"
        "\n  --port 8001"
    )
    assert windows.fidelity == "faithful", windows
    assert "llama-server.exe" in windows.arguments[0]
    assert "\\" in windows.arguments[0]
    assert "^" not in windows.arguments

    eaten = parse_observed_command("C:\\llama.cpp\\bin\\llama-server.exe --port 8001")
    assert eaten.fidelity == "faithful"
    assert "llama-server.exe" in eaten.arguments[0]
    caret = parse_observed_command("llama-server.exe ^\n  --port 8001")
    assert caret.fidelity == "faithful"
    assert caret.arguments == ["llama-server.exe", "--port", "8001"]
    print("tokenize_observed_command self-check passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="registry")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check or not args.apply:
        _self_check()
        if not args.apply:
            return
    updated, faithful, lossy = apply_registry(Path(args.root))
    print(f"updated {updated} recipes; faithful={faithful} lossy={lossy}")


if __name__ == "__main__":
    main()
