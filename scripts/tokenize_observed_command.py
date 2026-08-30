#!/usr/bin/env python3
"""Turn observed source shell strings into tokenized launch fields.

Candidate recipes stay `launch.kind: "reference"`. This never invents a
validated contract. Env prefixes become `launch.environment`; the remainder
becomes an argv array. `&&` chains become `launch.steps`.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path


TOKENIZED_LAUNCH_FIELDS = (
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
PORT_FLAG = {"--port", "--publish"}
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
DOCKER_VALUE_OPTS = {
    "--add-host",
    "--cidfile",
    "--cpus",
    "--device",
    "--entrypoint",
    "--env",
    "--env-file",
    "--gpus",
    "--hostname",
    "--ipc",
    "--label",
    "--memory",
    "--mount",
    "--name",
    "--net",
    "--network",
    "--pid",
    "--platform",
    "--publish",
    "--pull",
    "--restart",
    "--runtime",
    "--security-opt",
    "--shm-size",
    "--ulimit",
    "--user",
    "--volume",
    "--workdir",
    "-e",
    "-l",
    "-m",
    "-p",
    "-u",
    "-v",
    "-w",
}


@dataclass
class ParsedCommand:
    arguments: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    steps: list[list[str]] = field(default_factory=list)
    host_port: int | None = None
    container_port: int | None = None
    image: str | None = None
    mounts: list[dict] = field(default_factory=list)
    entrypoint: str | None = None
    ipc: str | None = None
    network_mode: str | None = None
    shm_size: str | None = None
    notes: list[str] = field(default_factory=list)
    endpoint: str | None = None
    served_model_name: str | None = None


def safe_split(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("& "):
        stripped = stripped[2:].strip()
    try:
        tokens = shlex.split(stripped, posix=True)
    except ValueError:
        try:
            tokens = shlex.split(stripped, posix=False)
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


def parse_port_token(value: str) -> tuple[int | None, int | None]:
    left, _, right = value.partition(":")
    host = left or right
    container = right or left
    try:
        host_port = int(host)
    except ValueError:
        host_port = None
    try:
        container_port = int(container)
    except ValueError:
        container_port = None
    return host_port, container_port


def extract_port(tokens: list[str], parsed: ParsedCommand) -> None:
    for index, token in enumerate(tokens):
        flag, _, attached = token.partition("=")
        if flag not in PORT_FLAG:
            continue
        value = attached or (tokens[index + 1] if index + 1 < len(tokens) else "")
        if not value or value.startswith("-"):
            continue
        host_port, container_port = parse_port_token(value)
        if host_port is not None:
            parsed.host_port = host_port
        if container_port is not None:
            parsed.container_port = container_port
        return
    if parsed.endpoint:
        match = re.search(r":(\d+)(?:/|$)", parsed.endpoint)
        if match:
            parsed.host_port = int(match.group(1))


def parse_mount(value: str) -> dict:
    parts = value.split(":")
    read_only = parts[-1] == "ro" if len(parts) >= 3 else False
    if read_only:
        parts = parts[:-1]
    source = parts[0] if parts else value
    target = parts[1] if len(parts) > 1 else parts[0]
    return {"read_only": read_only, "source": source, "target": target}


def parse_docker_run(tokens: list[str], parsed: ParsedCommand) -> list[str]:
    if len(tokens) < 2 or tokens[0] != "docker" or tokens[1] != "run":
        return tokens
    index = 2
    while index < len(tokens):
        token = tokens[index]
        flag, eq, attached = token.partition("=")
        if flag in DOCKER_VALUE_OPTS:
            value = attached if eq else (tokens[index + 1] if index + 1 < len(tokens) else "")
            index += 1 if eq else 2
            if flag in {"-e", "--env"} and "=" in value:
                key, val = value.split("=", 1)
                parsed.environment[key] = val
            elif flag in {"-v", "--volume"}:
                parsed.mounts.append(parse_mount(value))
            elif flag in {"-p", "--publish"}:
                host_port, container_port = parse_port_token(value)
                if host_port is not None:
                    parsed.host_port = host_port
                if container_port is not None:
                    parsed.container_port = container_port
            elif flag == "--entrypoint":
                parsed.entrypoint = value
            elif flag == "--ipc":
                parsed.ipc = value
            elif flag in {"--network", "--net"}:
                parsed.network_mode = value
            elif flag == "--shm-size":
                parsed.shm_size = value
            continue
        if token.startswith("-"):
            index += 1
            continue
        parsed.image = token
        return tokens[index + 1 :]
    return []


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
    for line in command_lines:
        for chunk in split_operators(line, ("&&", ";")):
            tokens, environment = peel_env(safe_split(chunk))
            parsed.environment.update(environment)
            if not tokens:
                continue
            rest = parse_docker_run(tokens, parsed)
            if tokens[:2] == ["docker", "run"]:
                if rest:
                    argv_steps.append(rest)
                continue
            argv_steps.append(tokens)
    for step in argv_steps:
        extract_port(step, parsed)
    if parsed.host_port is None:
        extract_port([], parsed)
    parsed.steps = argv_steps
    if not argv_steps:
        return parsed
    primary = next((step for step in reversed(argv_steps) if is_primary(step)), argv_steps[-1])
    parsed.arguments = primary
    if len(argv_steps) == 1:
        parsed.steps = []
    return parsed


def merge_launch(launch: dict, parsed: ParsedCommand) -> bool:
    before = json.dumps(launch, sort_keys=True)
    for key in TOKENIZED_LAUNCH_FIELDS:
        launch.pop(key, None)
    if parsed.arguments:
        launch["arguments"] = parsed.arguments
    if parsed.environment:
        launch["environment"] = parsed.environment
    if parsed.steps:
        launch["steps"] = parsed.steps
    if parsed.host_port is not None:
        launch["host_port"] = parsed.host_port
    if parsed.container_port is not None:
        launch["container_port"] = parsed.container_port
    if parsed.image:
        launch["image"] = parsed.image
    if parsed.mounts:
        launch["mounts"] = parsed.mounts
    if parsed.entrypoint:
        launch["entrypoint"] = parsed.entrypoint
    if parsed.ipc:
        launch["ipc"] = parsed.ipc
    if parsed.network_mode:
        launch["network_mode"] = parsed.network_mode
    if parsed.shm_size:
        launch["shm_size"] = parsed.shm_size
    if parsed.notes:
        launch["notes"] = parsed.notes
    if parsed.endpoint:
        launch["endpoint"] = parsed.endpoint
    if parsed.served_model_name:
        launch["served_model_name"] = parsed.served_model_name
    return json.dumps(launch, sort_keys=True) != before


def observed_snippet(recipe: dict) -> str | None:
    metadata = recipe.get("metadata") or {}
    for key in ("localmaxxing", "mlxfast"):
        block = metadata.get(key)
        if isinstance(block, dict):
            command = block.get("observed_command")
            if isinstance(command, str) and command.strip():
                return command
    return None


def apply_to_recipe(recipe: dict) -> bool:
    snippet = observed_snippet(recipe)
    if not snippet:
        return False
    launch = recipe.setdefault("launch", {})
    if not isinstance(launch, dict):
        return False
    return merge_launch(launch, parse_observed_command(snippet))


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def apply_registry(root: Path) -> int:
    updated = 0
    for path in sorted((root / "recipe").glob("*.json")):
        recipe = json.loads(path.read_text())
        if apply_to_recipe(recipe):
            write(path, recipe)
            updated += 1
    return updated


def _self_check() -> None:
    env = parse_observed_command(
        "VLLM_NVFP4_GEMM_BACKEND=cutlass vllm serve /models/Qwen --port 8000 --max-model-len 4096"
    )
    assert env.environment == {"VLLM_NVFP4_GEMM_BACKEND": "cutlass"}
    assert env.arguments[0] == "vllm"
    assert env.host_port == 8000
    assert "&&" not in env.arguments

    chain = parse_observed_command(
        "git clone https://github.com/Layr-Labs/mlxfast-gemma4-26b-a4b-engine && ./tools/fetch-benchd.sh && ./setup.sh && ./setup-gemma4-assistant.sh"
    )
    assert chain.steps == [
        ["git", "clone", "https://github.com/Layr-Labs/mlxfast-gemma4-26b-a4b-engine"],
        ["./tools/fetch-benchd.sh"],
        ["./setup.sh"],
        ["./setup-gemma4-assistant.sh"],
    ]
    assert chain.steps[-1] == ["./setup-gemma4-assistant.sh"]
    assert chain.arguments == ["./setup-gemma4-assistant.sh"]

    remote = parse_observed_command("# Remote endpoint: http://127.0.0.1:1235  servedModel: microsoft/phi-4-reasoning-plus")
    assert remote.endpoint == "http://127.0.0.1:1235"
    assert remote.served_model_name == "microsoft/phi-4-reasoning-plus"
    assert remote.host_port == 1235
    assert not remote.arguments

    docker = parse_observed_command(
        'docker run --gpus all --ipc=host -e CUTE_DSL_ARCH=sm_120a -v /models:/model:ro -p 8000:8000 vllm/vllm-openai:cu13 --model /model --served-model-name laguna'
    )
    assert docker.image == "vllm/vllm-openai:cu13"
    assert docker.environment["CUTE_DSL_ARCH"] == "sm_120a"
    assert docker.mounts[0]["target"] == "/model"
    assert docker.arguments[:2] == ["--model", "/model"]
    assert docker.host_port == 8000
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
    updated = apply_registry(Path(args.root))
    print(f"tokenized {updated} recipes")


if __name__ == "__main__":
    main()
