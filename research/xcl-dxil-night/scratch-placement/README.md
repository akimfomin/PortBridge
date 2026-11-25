# XCL #2080 scratch allocation comparison

PortBridge checked an isolated D3D12 alternative to XCL's one committed scratch allocation per chained dispatch. The candidate creates one 1 MiB default heap and places disjoint 64 KiB UAV-capable buffers in it. Each placed buffer keeps its own resource identity and GPU address. The check activates each placed buffer with a documented barrier and verifies every byte after GPU copy and readback. The source uses generated data and has no XCL runtime or game dependency. [XCL #2080](https://github.com/xcl-dev/xcl/pull/2080) · [Exact reference allocation](https://github.com/Kalmarv/xcl/blob/af2bd61e39344b0db2f37f14d950c78e0022e7df/crates/xcl/src/hle/d3d12x/real/dispatch_chain.rs#L109-L146)

## RTX 4070 Ti SUPER result

Eight paired timing comparisons per count. Values are host elapsed time for resource creation, including the candidate's `CreateHeap` call. Reduction is the median of the percentage differences within pairs.

| 64 KiB buffers | Committed median | Placed median | Paired reduction | Placed wins |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 200.150 µs | 259.700 µs | −44.624% | 3/8 |
| 4 | 698.600 µs | 302.300 µs | 53.863% | 8/8 |
| 16 | 2,810.900 µs | 356.200 µs | 87.603% | 8/8 |

All 24 timing pairs and three verification pairs had complete readback, zero mismatched words and device status `S_OK`. The three counts read back 24,772,608 bytes in total. Windows 10.0.28000.0 reported NVIDIA driver 32.0.16.1714. The host used an Intel Core i5-13600KF. The optional D3D12 debug layer was unavailable (`887a002d`). [1-buffer summary](native-count-control/evidence-1/summary.log) · [4-buffer summary](native-count-control/evidence-4/summary.log) · [16-buffer summary](native/evidence-0732-timing/summary.log)

The actual number and sizes of allocations per XCL backing allocator still need measuring. The single-buffer result supports keeping the existing committed path for sparse cases. An exact threshold requires data from counts two and three and from actual allocations. Timings exclude barrier recording, copies, waits, releases and allocator resets. This comparison covers one GPU, one driver and one direct queue. It does not exercise shader dispatch, XCL runtime integration, or mixed-queue lifetime.

## Source and reproduction

- [16-buffer fixture, instructions and logs](native/README.md)
- [1- and 4-buffer fixtures, instructions and logs](native-count-control/README.md)
- [Build provenance](BUILD.md)
- [File hashes](SHA256SUMS)
