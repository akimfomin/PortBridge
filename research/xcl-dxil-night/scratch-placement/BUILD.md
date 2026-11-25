# Build provenance

All fixtures built with LLVM-MinGW 20261117 x64 UCRT, C++20, `-O2 -static -municode -Wall -Wextra -Werror`. The binaries reproduced these logs and are omitted from the source package. The runtime preflight excluded one earlier attempt before a worker started. The successful runs each used the same reviewed 512 MiB, 3 s guard and checked host memory before every child. [Compiler distribution](https://github.com/mstorsjo/llvm-mingw)

| Binary | SHA-256 of executable tested |
| --- | --- |
| 16 buffers | `407c6da8b7896d874377aaae4efb898b43c38c11d9d69ef9cc559ce55e843bdc` |
| 1 buffer | `107f1bc8c2c319b930b465997a40049eea5fa01e1bf3a7226144694a7f7e70b8` |
| 4 buffers | `bbe325d86c5ce08f935e1a32e38d81a00e0d81bca5ce7843ae1ce7fecc8c4972` |
