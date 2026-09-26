"""Create a reproducible, tokenizer-counted retrieval workload (runtime deps required).

Run with the pinned MLX-VLM virtualenv. This does not load model weights.
The server's usage.prompt_tokens remains the authoritative measured length.
"""

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

from transformers import AutoTokenizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="runs/qwen38/models/Qwen3.8-27B-4bit")
    parser.add_argument("--tokens", type=int, default=200000)
    parser.add_argument("--with-image", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 128 <= args.tokens <= 200512:
        parser.error("--tokens must be between 128 and 200512")
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    needles = ["ALPHA=maple-7429", "BETA=harbor-6183", "GAMMA=violet-9052"]
    filler = (
        "This is an ordinary archive entry about a workshop. The team inspected "
        "the shelves, recorded the weather, checked the inventory, and closed the "
        "doors. No retrieval keys appear in this entry.\n"
    )
    image_url = None
    if args.with_image:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        from probe_apple_qwen38 import vision_png
        image_url = "data:image/png;base64," + base64.b64encode(vision_png()).decode("ascii")

    def messages(repeats):
        sections = ["Read the entire archive. Retain the three retrieval keys.\n"]
        # Keys near the start, one-third, and two-thirds exercise distant retrieval.
        for key in needles:
            sections.extend(["\nRETRIEVAL KEY: " + key + "\n", filler * repeats])
        sections.append(
            "\nReturn the values of ALPHA, BETA and GAMMA from the retrieval keys, "
            "in that order, exactly as three comma-separated values. No explanation."
        )
        if image_url:
            sections.append(
                " After the three keys, give the two solid colors in the attached image "
                "from left to right. Return all five values on one comma-separated line."
            )
            content = [{"type": "image_url", "image_url": {"url": image_url}},
                       {"type": "text", "text": "".join(sections)}]
        else:
            content = "".join(sections)
        return [{"role": "user", "content": content}]

    def count(msgs):
        token_ids = tokenizer.apply_chat_template(
            msgs, tokenize=True, add_generation_prompt=True, enable_thinking=False,
            return_dict=False,
        )
        if not isinstance(token_ids, list) or not all(type(i) is int for i in token_ids):
            raise TypeError("Expected a flat token-id list from the pinned tokenizer")
        return len(token_ids)

    low, high = 0, max(1, args.tokens // 50)
    if count(messages(high)) < args.tokens:
        raise RuntimeError("Initial bounded fixture is unexpectedly too short")
    while low < high:
        mid = (low + high) // 2
        if count(messages(mid)) < args.tokens:
            low = mid + 1
        else:
            high = mid
    body = {
        "model": args.model, "messages": messages(low), "temperature": 0,
        "max_tokens": 128, "enable_thinking": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "stream": True, "stream_options": {"include_usage": True},
    }
    raw = (json.dumps(body, ensure_ascii=False, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(json.dumps({
        "path": str(args.output), "request_sha256": hashlib.sha256(raw).hexdigest(),
        "tokenizer_prompt_tokens": count(body["messages"]), "repeats_per_section": low,
        "expected": "maple-7429, harbor-6183, violet-9052" + (", red, blue" if image_url else ""),
        "image_included": args.with_image,
        "tokenizer_count_excludes_image_expansion": args.with_image,
        "kind": "synthetic-retrieval-smoke-not-a-quality-benchmark",
    }, indent=2))


if __name__ == "__main__":
    main()
