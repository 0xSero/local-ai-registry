#!/usr/bin/env python3
"""Read a GGUF tensor table (header only) and report MTP tensors and effective bits per weight.

usage: gguf_meta.py MODEL.gguf [MMPROJ.gguf]   (stdlib only; reads the header, not the weights)
"""
import collections, json, struct, sys

NAMES = {0: "F32", 1: "F16", 8: "Q8_0", 10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 16: "IQ2_XXS",
         17: "IQ2_XS", 18: "IQ3_XXS", 19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S", 23: "IQ4_XS", 29: "IQ1_M", 30: "BF16"}
# ggml bytes per block, elements per block
BPB = {0: (4, 1), 1: (2, 1), 30: (2, 1), 8: (34, 32), 10: (84, 256), 11: (110, 256), 12: (144, 256), 13: (176, 256),
       14: (210, 256), 16: (66, 256), 17: (74, 256), 18: (98, 256), 19: (50, 256), 20: (18, 32), 21: (110, 256),
       22: (82, 256), 23: (136, 256), 29: (56, 256)}
SZ = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
FMT = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}


def read(path):
    f = open(path, "rb")
    u32 = lambda: struct.unpack("<I", f.read(4))[0]
    u64 = lambda: struct.unpack("<Q", f.read(8))[0]

    def s():
        return f.read(u64()).decode("utf-8", "replace")

    def val(t):
        if t == 8:
            return s()
        if t == 9:
            et, n = u32(), u64()
            if et == 8:
                for _ in range(n):
                    s()
            else:
                f.seek(SZ[et] * n, 1)
            return f"<array x{n}>"
        return struct.unpack(FMT[t], f.read(SZ[t]))[0]

    assert f.read(4) == b"GGUF", "not a GGUF file"
    u32()
    nt, nkv = u64(), u64()
    kv = {}
    for _ in range(nkv):
        k = s()
        kv[k] = val(u32())
    tensors = []
    for _ in range(nt):
        name = s()
        dims = [u64() for _ in range(u32())]
        typ = u32()
        u64()
        tensors.append((name, dims, typ))
    return kv, tensors


def summarize(tensors, keep=lambda name: True):
    params, bits, by_type = 0, 0.0, collections.Counter()
    for name, dims, typ in tensors:
        if not keep(name):
            continue
        n = 1
        for d in dims:
            n *= d
        size, block = BPB[typ]
        params += n
        bits += n * size * 8 / block
        by_type[NAMES[typ]] += n
    return params, bits, by_type


def main():
    kv, tensors = read(sys.argv[1])
    p, b, by_type = summarize(tensors)
    pn, bn, _ = summarize(tensors, lambda n: not n.startswith("blk.64."))
    pm, bm, _ = summarize(tensors, lambda n: n.startswith("blk.64."))
    out = {"metadata": {k: kv[k] for k in ("general.architecture", "general.file_type", "qwen35.block_count",
                                           "qwen35.nextn_predict_layers", "qwen35.context_length",
                                           "general.base_model.0.repo_url") if k in kv},
           "tensor_count": len(tensors),
           "mtp_block": {"tensors": [n for n, _, _ in tensors if n.startswith("blk.64.")],
                         "types": sorted({NAMES[t] for n, _, t in tensors if n.startswith("blk.64.")}),
                         "params": pm, "bits_per_weight": round(bm / pm, 2) if pm else None},
           "bits_per_weight": {"model": round(b / p, 2), "model_without_mtp_block": round(bn / pn, 2)},
           "params": {"model": p, "model_without_mtp_block": pn},
           "params_share_by_type": {k: round(v / p, 4) for k, v in by_type.most_common()}}
    if len(sys.argv) > 2:
        _, mm = read(sys.argv[2])
        pv, bv, _ = summarize(mm)
        out["params"]["mmproj"] = pv
        out["bits_per_weight"]["mmproj"] = round(bv / pv, 2)
        out["bits_per_weight"]["model_plus_mmproj"] = round((b + bv) / (p + pv), 2)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
