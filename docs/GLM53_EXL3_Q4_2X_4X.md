# GLM-5.3 Flash EXL3 Q4: two- and four-GPU status

The public artifact is [`0xSero/GLM-5.3-Flash-EXL3-Q4`](https://huggingface.co/0xSero/GLM-5.3-Flash-EXL3-Q4), pinned here at revision `99cccdf0e8741715662c383828a9ea601990c125`.

## Four RTX PRO 6000 Blackwell GPUs

The TP4/EP1 SGLang path is runtime-tested with CUDA graphs enabled, FP8 E4M3 KV, a 262,144-token configured context, model discovery, endpoint health, and a generated completion. Its accepted matched 256-token prose screen produced 73.4979 output tokens per second. A virtual-slice EP4 candidate produced 68.4659 output tokens per second and was rejected as a 6.85% regression. An MTP5 candidate was also rejected.

The recipe remains `candidate`, rather than `validated`, because its locally built runtime image has not been published by content digest and tool/vision execution has not been accepted.

## Two RTX PRO 6000 Blackwell GPUs

There is no honest working TP2 recipe yet. The checkpoint metadata fixes `tensor_parallel_size` at 4 and uses independently rotated rank slices. The current loader therefore cannot simply change `--tp-size 4` to `--tp-size 2`.

A correct TP2 adaptation would pair sealed source ranks 0+1 and 2+3, preserve each rotation as a virtual slice, and expand top-8 routing to top-16 before the two physical ranks reduce their partial outputs. The four-GPU runtime measured 53.18 GB of prepared weights per rank for one 288-slice kernel slab. Pairing two slabs projects to roughly 106.36 GB per physical rank before KV cache and runtime workspace, which is already above 96 GB.

For that reason the TP2 registry row is a non-launchable compatibility record with a blocked sweep, not fabricated throughput. A future TP2 claim requires a lower-memory packing path or offload design, real-weight parity, full load, CUDA-graph capture, endpoint acceptance, and a fresh speed sweep.

No power-limit changes are part of either recipe.
