# SPDX-License-Identifier: MIT
"""Build deterministic features and weights for the two published mobile NeRF MLP stages."""

import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np


def output_weights():
    # Four reproducible, distinct networks. Binary fractions are exact in float32.
    state = 0x992DB591
    entries = []
    for _ in range(4 * 532):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        entries.append(((state >> 24) - 128) / 256)
    return np.asarray(entries, dtype="<f4").reshape(4, 532)


def inputs(width, height):
    y, x = np.mgrid[:height, :width]
    u, v = (x + .5) / width, (y + .5) / height
    f0 = np.stack([u, v, (u * .25 + v * .75), (u + 2 * v) % 1], -1)
    f1 = np.stack([(1-u) * v, (u * 3) % 1, (u + v) % 1, (v * 4 + .125) % 1], -1)
    direction = np.stack((2*u-1, 1-2*v, np.full_like(u, -1.25)), -1)
    direction /= np.linalg.norm(direction, axis=-1, keepdims=True)
    hole = ((u-.53)**2 + (v-.42)**2 < .015) | ((x + 3*y) % 23 == 0)
    alpha = np.where(hole, .375, .625 + .375*(.25*u+.75*v))
    direction = np.concatenate([direction, alpha[...,None]], axis=-1)
    # Alternate uniform regions with per-quad disagreement in the indexed UBO.
    region = (x // 9 + y // 6) % 4
    alternating = (x + y // 2) % 4
    index = np.where(u < .5, region, alternating)
    return [a.astype("<f4") for a in (f0, f1, direction)], index.astype("<u4")


def reference(textures, indices, weights, morpheus):
    f0, f1, direction = [texture.reshape(-1, 4).astype("f8") for texture in textures]
    f0[:, 3] = 2*f0[:, 3]-1
    f1[:, 3] = 2*f1[:, 3]-1
    view_features = direction[:, [0, 2, 1]] * [1, -1, 1]
    if morpheus:
        view_features = (1+view_features)/2
    feature = np.concatenate([f0, f1, view_features], axis=1)
    live = direction[:, 3] >= .6
    blend = 2*direction[:, 3:4]-1
    output = np.full((len(live), 4), -3, dtype="<f4")
    counters = []
    for i, model in enumerate(weights.astype("f8")):
        observed = live & (indices.ravel() == i)
        one = feature[observed] @ model[:176].reshape(11,16) + model[496:512]
        two = np.maximum(one,0) @ model[176:432].reshape(16,16) + model[512:528]
        logits = np.maximum(two,0) @ model[432:496].reshape(16,4) + model[528:532]
        srgb = 1 / (1 + np.exp(-logits[:, :3])) * blend[observed] + (1-blend[observed])
        linear = np.where(srgb <= .04045, srgb / 12.92, np.power((srgb+.055)/1.055, 2.4))
        output[observed,:3] = linear
        output[observed,3] = 1
        counters.append(dict(model=i, active=int(observed.sum()),
                             positive_hidden1=(one>0).sum(0).tolist(), positive_hidden2=(two>0).sum(0).tolist()))
    return output, counters


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    a = p.parse_args()
    if not (8<=a.width<=640 and 8<=a.height<=360):
        p.error("bounded input extent required")
    a.out.mkdir(parents=True, exist_ok=False)
    textures, indices = inputs(a.width, a.height)
    weights = output_weights()
    arrays = dict(zip(("features0.rgba32f","features1.rgba32f","direction.rgba32f"), textures))
    arrays.update({"indices.r32u":indices,"weights.bin":weights})
    receipt = {"width":a.width,"height":a.height,"clear":[-3]*4,"model_count":len(weights),
               "weights_float32_per_model":532,"input_origin":"top-left","profiles":{}}
    for mode in ("mlp_combo","mlp_morpheus_combo"):
        rgba, count = reference(textures, indices, weights, mode=="mlp_morpheus_combo")
        arrays[mode+".cpu.rgba32f"]=rgba
        receipt["profiles"][mode]={"models":count,"discarded":int(np.sum(rgba[:,3]==-3)),
                                 "distinct_rgb8":int(len(np.unique(np.rint(rgba[rgba[:,3]==1,:3]*255),axis=0)))}
    receipt["sha256"]={}
    for name, arr in arrays.items():
        data=arr.tobytes(order="C")
        (a.out/name).write_bytes(data)
        receipt["sha256"][name]=hashlib.sha256(data).hexdigest()
    (a.out/"manifest.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(a.width,a.height,[(k,v["discarded"],v["distinct_rgb8"]) for k,v in receipt["profiles"].items()])


if __name__=="__main__":
    main()
