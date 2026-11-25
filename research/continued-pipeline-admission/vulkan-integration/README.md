# Continued pipeline admission · Vulkan integration

Six source-generated, descriptor-free Vulkan compute shaders return immediately. The four names sorted first contain `OpNop` padding and fall above a 300-byte threshold. The last two fall below it. The checker only creates and destroys shader modules and pipelines. It creates no dispatch. The assembly stage validates every module against Vulkan 1.1 and rejects submissions above 1 KiB. Both arms use the same binaries for the shader inputs. [Existing Continued fixture and index format](https://github.com/ubiquitarianism/leonida/blob/507029d1ea8dc65f1fabb68739605d6821843bf1/tests/test_vk_pipeline_check_isolate.py)

`stock` builds the checker and gate byte-for-byte from `507029d1ea8dc65f1fabb68739605d6821843bf1` and the local reviewed candidate. `observed` adds the same small logging and hold fixture to both checker copies. A holder marks admission before its real Vulkan calls and holds its original permit for one second after those calls and object cleanup. No new mechanism admits work. The candidate is expected to complete at least one small pipeline before the first held permit is released. The baseline is expected to complete both small pipelines after that point. Both must still complete six pipelines. The observed comparison verifies order under a controlled saturated gate. Normal driver caches, the artificial hold and tiny shaders preclude throughput conclusions.

Run preparation, compilation and execution separately from this directory. Place this directory at `local-verification/vulkan-integration/` under a separate Continued checkout at the pinned revision and apply [the reviewed patch](../continued-pipeline-ready-work-reviewed.patch). Set the paths at the top of `check.py` to your LLVM-MinGW, Vulkan-Headers and SPIR-V Tools installations. The recorded test uses the stated RTX adapter; update `ADAPTER` to select a different GPU. The saved commands use relative paths for portability. Each compilation or checker invocation is sequential and time-bounded. No application cache path is supplied. Logs and hashes land in `generated/`.

```powershell
python -I -B check.py prepare
python -I -B check.py assemble
python -I -B check.py build --mode stock
python -I -B check.py build --mode observed
python -I -B check.py run --mode stock
python -I -B check.py run --mode observed
```

The GPU invocations use `--jobs 4 --large-parallel 2 --large-module-bytes 300 --max-bytes 1024 --stage cs`. `LEONIDA_VK_DEVICE` is set for the child process only. [Vulkan pipeline creation](https://docs.vulkan.org/spec/latest/chapters/pipelines.html#vkCreateComputePipelines)

## Local result

Vulkan 1.1 validation passed for all six modules. The four large fixtures were 524 bytes each, and the two small fixtures were 140 bytes each. The stock baseline sources match the pinned Git blobs byte for byte. The two observed checker files each add the same 10 fixture lines and use the same gate headers as their stock counterparts. The source and shader hashes are in [source-hashes.json](generated/source-hashes.json) and [fixture-hashes.json](generated/fixture-hashes.json).

Both stock checkers created all six modules and pipelines on an NVIDIA GeForce RTX 4070 Ti SUPER, with zero failures and zero skips. Both observed checkers did the same. The baseline completed zero small pipelines before the first held large permit reached its release point. The candidate completed both small pipelines before either held permit reached its release point. [Stock logs and executable hashes](generated/stock-results.json) · [Observed event sequences](generated/observed-results.json)

The controlled hold verifies dispatch order through the Vulkan path. Its timing does not measure natural throughput. The reviewed patch SHA-256 remained `b587fb6300b6525090eade38838a64e5e178a8b7bf5cfbbe38ce6098356d6ff0`.
