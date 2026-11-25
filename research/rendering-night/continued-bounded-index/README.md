# Continued main shader index. Bounded file input and measured loading cost

OreoFR's [first-use measurement](https://github.com/ubiquitarianism/leonida/pull/1308#issuecomment-7148830079) identified a 29,187-entry main shader index. PortBridge's [first patch](https://github.com/akimfomin/PortBridge/blob/0026f46715fa6cb3be97c65fc6572fbf96a5a043/research/rendering-night/continued-shader-index/README.md) limited retained JSON nodes to one record at a time while continuing to read the whole file into a string. This independent extension reads only the main index in 16 KiB blocks with short lookahead. It uses the same grammar for both the main and optional indexes, preserves duplicate order, and publishes the new main index after reading and validating the complete file.

The optional short-integer patch uses the existing complete scanner token. Unsigned decimals up to 15 digits are exact in binary64. Signs, fractions, exponents and longer inputs use the original conversion. The memory result comes from bounded file input.

| Generated main index | Stock / bounded / both, ms | Stock / bounded / both, peak process commit |
| --- | ---: | ---: |
| 64 rows, 42,264 bytes | 0.977 / 0.777 / 0.700 | 2.35 / 1.88 / 1.89 MB |
| 8,000 rows, 10,425,351 bytes | 148.51 / 88.36 / 81.21 | 81.38 / 10.22 / 10.21 MB |
| 29,187 rows, 57,357,214 bytes | 802.78 / 470.43 / 442.52 | 459.15 / 34.64 / 34.67 MB |

Each path used the same optimized Windows load probe, one untimed run per arm and all six arm orders in fresh processes. Every expected row and metadata value was then checked. Timing includes file I/O and uses normal OS filesystem caching. The three native parsers agreed over 111,211 synthetic numeric tokens. Controls cover split tokens, duplicate rows, BOM, the depth limit, a malformed tail and an OS-locked byte beyond a completed root. A failed main load preserves the previous state. The locked-tail method follows sodove's [#1218](https://github.com/ubiquitarianism/leonida/pull/1218). Kadamitas's [#1108](https://github.com/ubiquitarianism/leonida/pull/1108) applies in a source-only check; the table does not include it. Full runtime start, platform variation and optional-index timing remain open.

[Measurements](three-arm.json) · [Number results](verified-numbers.json) · [Cursor controls](stream-controls.log) · [Load controls](prior-controls.log)

## Reproduce on Windows

Use Git, Python 3.11+, LLVM-MinGW Clang and the exact open Continued checkout at [`871e4b8`](https://github.com/ubiquitarianism/leonida/commit/871e4b8b990bb9424c6f3c06175259d1a548239c), with LF endings. The script builds C++20 probes in a new output folder and checks the SHA-256 of every patched header. Pass `-Measure` for a new balanced run. The timed processes each require 3 GiB of commit and 6 GiB of physical memory available at admission.

```powershell
.\reproduce.ps1 -SourceCheckout .\continued -Compiler C:\llvm-mingw\bin\clang++.exe -OutputDirectory .\new-index-proof
```

The [main-only reference](00-main-only-reference.patch) goes first, then the [bounded cursor patch](bounded-main-index.patch), then the [optional short-decimal patch](bounded-cursor-short-decimal.patch). [Source license](LICENSE)
