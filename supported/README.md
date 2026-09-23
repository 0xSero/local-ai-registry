# Supported GPUs

Local AI runs a validated model on 36 GPUs: 33 NVIDIA, 1 Intel, 2 AMD.
Each one was tested on that exact card before it was listed; a card that is not here shows Coming soon.

| GPU | Model | Engine | Context | Decode |
|---|---|---|---|---|
| [AMD Instinct MI300X 192 GB](amd/mi300x-192gb.md) | Qwen3.8-27B | SGLang | 128K | – |
| [AMD Radeon RX 6800 XT 16 GB](amd/rx-6800-xt-16gb.md) | Qwen3.5-9B-Base | llama.cpp | 64K | – |
| [Intel Arc Pro B70 32 GB](intel/intel-arc-pro-b70-32gb.md) | Qwen3.8-27B | vLLM | 256K | 74 tok/s |
| [GeForce RTX 3060 12 GB](nvidia/rtx-3060-12gb.md) | Qwen3.5-9B | TabbyAPI (ExLlamaV3) | 128K | 81 tok/s |
| [GeForce RTX 3060 Ti 8 GB](nvidia/rtx-3060-ti-8gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [GeForce RTX 3070 8 GB](nvidia/rtx-3070-8gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [GeForce RTX 3070 Ti 8 GB](nvidia/rtx-3070-ti-8gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [GeForce RTX 3080 10 GB](nvidia/rtx-3080-10gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [GeForce RTX 3080 Ti 12 GB](nvidia/rtx-3080-ti-12gb.md) | Qwen3.5-9B | TabbyAPI (ExLlamaV3) | 128K | 128 tok/s |
| [GeForce RTX 3090 24 GB](nvidia/rtx-3090-24gb.md) | Qwen3.8-27B | SGLang | 200K | 147 tok/s |
| [GeForce RTX 3090 Ti 24 GB](nvidia/rtx-3090-ti-24gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 256K | 67 tok/s |
| [GeForce RTX 4060 8 GB](nvidia/rtx-4060-8gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [GeForce RTX 4060 Laptop GPU 8 GB](nvidia/rtx-4060-laptop-8gb.md) | LFM2.5-2.6B | llama.cpp | 8K | 124 tok/s |
| [GeForce RTX 4060 Ti 16 GB](nvidia/rtx-4060-ti-16gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 128K | 38 tok/s |
| [GeForce RTX 4060 Ti 8 GB](nvidia/rtx-4060-ti-8gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [GeForce RTX 4070 12 GB](nvidia/rtx-4070-12gb.md) | Qwen3.5-9B | TabbyAPI (ExLlamaV3) | 128K | 118 tok/s |
| [GeForce RTX 4070 SUPER 12 GB](nvidia/rtx-4070-super-12gb.md) | Qwen3.5-9B | TabbyAPI (ExLlamaV3) | 128K | – |
| [GeForce RTX 4070 Ti 12 GB](nvidia/rtx-4070-ti-12gb.md) | Qwen3.5-9B | TabbyAPI (ExLlamaV3) | 128K | 103 tok/s |
| [GeForce RTX 4070 Ti SUPER 16 GB](nvidia/rtx-4070-ti-super-16gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 128K | 63 tok/s |
| [GeForce RTX 4080 16 GB](nvidia/rtx-4080-16gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 128K | 57 tok/s |
| [GeForce RTX 4080 SUPER 16 GB](nvidia/rtx-4080-super-16gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 128K | 77 tok/s |
| [GeForce RTX 4090 24 GB](nvidia/rtx-4090-24gb.md) | Qwen3.8-27B | SGLang | 200K | 135 tok/s |
| [GeForce RTX 5060 8 GB](nvidia/rtx-5060-8gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [GeForce RTX 5060 Ti 16 GB](nvidia/rtx-5060-ti-16gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 128K | 39 tok/s |
| [GeForce RTX 5060 Ti 8 GB](nvidia/rtx-5060-ti-8gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [GeForce RTX 5070 12 GB](nvidia/rtx-5070-12gb.md) | Qwen3.5-9B | TabbyAPI (ExLlamaV3) | 128K | 146 tok/s |
| [GeForce RTX 5070 Ti 16 GB](nvidia/rtx-5070-ti-16gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 128K | 76 tok/s |
| [GeForce RTX 5080 16 GB](nvidia/rtx-5080-16gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 128K | 78 tok/s |
| [GeForce RTX 5090 32 GB](nvidia/rtx-5090-32gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 256K | 117 tok/s |
| [RTX 2000 Ada Generation 16 GB](nvidia/rtx-2000-ada-16gb.md) | LFM2.5-2.6B | SGLang | 128K | – |
| [RTX 4000 Ada Generation 20 GB](nvidia/rtx-4000-ada-20gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 128K | 37 tok/s |
| [RTX 6000 Ada Generation 48 GB](nvidia/rtx-6000-ada-48gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 256K | 71 tok/s |
| [RTX A6000 48 GB](nvidia/rtx-a6000-48gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 256K | 58 tok/s |
| [RTX PRO 4000 Blackwell 24 GB](nvidia/rtx-pro-4000-blackwell-24gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 256K | 57 tok/s |
| [RTX PRO 4500 Blackwell 32 GB](nvidia/rtx-pro-4500-blackwell-32gb.md) | Qwen3.8-27B | TabbyAPI (ExLlamaV3) | 256K | 64 tok/s |
| [RTX PRO 6000 Blackwell 96 GB](nvidia/rtx-pro-6000-blackwell-96gb.md) | Qwen3.8-27B | SGLang | 128K | 88 tok/s |
