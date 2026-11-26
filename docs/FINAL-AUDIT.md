# What PortBridge built and what others can carry forward

26 November 2026 · [Русский](FINAL-AUDIT.ru.md) · [Letter from the founder and open discussion][future] · [Maintainer guide][maint]

PortBridge started at home with one founder, an AI agent and a question that kept coming up in independent Xbox Series compatibility projects. Had another team already investigated this same graphics failure, and could someone with a different GPU check the answer? The project now leaves behind working search, reproducible measurements, several accepted changes and named contributors who shared their time. We saw individual teams use the lab. We did not establish regular independent use sufficient to sustain the original pace. The evidence below records what a future maintainer can rely on. [First commit][start] · [Public interaction record][log]

## From finding related reports to writing a compiler change

- **24 November.** The first catalog connected public reports and their revisions. Agent preflight, a local MCP, an optional GitHub Action and a volunteer Test Lab followed. An early fixed comparison found the right link in the first five results for 7/10 queries with PortBridge and 8/10 with direct GitHub Search. Tests with two simulated agents exercised the exchange protocol. The external human runs are recorded separately below. [Initial Test Lab][lab] · [Search tasks, scores and later evaluations][search]
- **25 November.** Partitioned search, automatic report collection and Research Radar made the larger catalog usable. Physical transfer and subgroup experiments followed, then readbacks, barrier tracking and cold pipeline creation. Several plausible algorithms lost to an existing baseline. The evidence that stopped this work remains available alongside its code. [Catalog changes][radar] · [RTX transfer study][ref62] · [Readback and dependency experiments][ref74]
- **26 November.** A triangle-edge test disproved an early mask optimization. It also exposed a real error in XCL's ordinary pixel translation. We separated the correctness fix from a more conservative, opt-in compiler optimization, published exact revisions, and compared fully executed inference passes against the original shaders. [Withdrawn experiment][p77lane] · [Merged PortBridge package][main90]

## Results in other projects

| Receiving project | What was used, who supplied it, and where to reproduce it |
| --- | --- |
| AnyXboxX, WARP and D16 | LooperSalty merged PortBridge's WARP initialization correction in #144 at `becaf782`. Four pre-existing texture discrepancies remained. In #129 Skyfrye reused the expected D16 value from PortBridge's VIctory test in their own interpreter regression. The merge was `b15d8821`. The original PRs describe the focused tests and their limits. [WARP change][warp] · [Merged D16 regression][d16] · [Source test][victory] |
| AnyXboxX, rounding and FMA | KainanP authored the accepted interpreter changes. PortBridge supplied reproductions and a test probe. Lyrnc measured inactive carry bits on physical gfx1036. #133 merged at `71d4c615`, and the separate single-rounding FMA fix #203 at `6802e44b`. The physical carry result covers that instruction and configuration. [#133 merge][c133] · [Native report][lyrnc] · [#203 tests and credit][fma] |
| AnyXboxX, textures | PortBridge's BC7 change #202 merged at `0539d7f8`. A separate CPU decoder agreed for all 68,868 pixels across eight BC7 modes and cropped edges. The repository uses GPL-3.0-or-later and retains the MIT notices of the previous Xbox2Windows port. Lewandox also implemented PortBridge's coordinate-reuse suggestion at `c5ca937c` in #188. That PR closed without merge after the project changed texture backends. [Merged BC7 and commands][bc7] · [Independent decoder comparison][pillow] · [Lewandox's implementation][gfxcode] · [Disposition of #188][gfx] |
| FrameLab, VIctory and KLBF Lab | 5headsmartbtw included PortBridge's independent NVIDIA check in FrameLab's main documentation. JoeY54 supplied the AMD reports accepted for FL-07. PastiiJay from KLBF Lab took a Test Lab request and posted the XCL #1100 results for two input sets. VIctory provided the original D16 investigation and discussion used for the AnyXboxX transfer. These are confirmed examples of people using the findings. [FrameLab documentation change][frame] · [FL-07 acceptance][joe] · [KLBF participant's report][klbf] · [VIctory thread][victory] |

Ahmet-Dedeler added the Test Lab to the community directory. Six on PC included PortBridge in the board configuration under the lab group. [Board source][board] PC Race declined a listing under its editorial scope. These decisions record discovery and editorial choice. They do not establish habitual use. [Directory decision][added] · [PC Race reply][declined]

## Engineering packages and the decisions still open

**1. SSA Mask Projection, experimental.** PortBridge's direct-DXIL translator can follow the four bits needed by a pixel quad through proven mask expressions, keeping full masks for scalar consumers and falling back on unknown expressions. Exact standalone fork `5d04cc10`, published evidence `2223a0b6`. The published fork passed 1,436 workspace tests, the corresponding current-main combination 1,450. Each recorded 47 ignored tests and 28 skipped subcases. Of 397 accepted shader/width pairs, 34 DXIL modules shrank, 24 grew and 339 were unchanged. Enable `XCL_DIRECT_PIXEL_MASK_PROJECTION=1` in a fresh direct-pixel process. Run `python verify.py` in the linked package to check the archived receipts. The reproduction links include source licenses for each guest and the GPL-2.0-only XCL compiler changes. [Source][ssa] · [Steps and licenses][main90] · [Pinned corpus and logs][receipt]

| Complete GPU inference pass, RTX 4070 Ti SUPER | Full masks | Previous strict projection | Expanded projection | Original Vulkan |
| --- | ---: | ---: | ---: | ---: |
| Khronos Mobile NeRF 071 | 297 µs | 193–195 µs | 163–170 µs | about 14 µs |
| Khronos Mobile NeRF 073 | 265 µs | 178–184 µs | 156–157 µs | about 14 µs |

Each translated mode reproduced both 57,600-pixel frames bit for bit. The maximum channel difference to the original shader was 2.39 × 10⁻⁷. The two workloads share substantial code, and only one physical NVIDIA adapter ran the complete passes. The full-size D3D12 attempt stopped at the memory reserve. Independent AMD or Intel timings, application frame time and the driver memory ceiling remain open. [Raw GPU samples and frame hashes][raw] · [Optional independent comparison][ask87]

**2. Wave32 Carry Fix, independent hardware confirmation.** The ordinary XCL HLSL translator could overwrite an adjacent mask at triangle edges. On our RTX, 668 incorrect pixel-draws out of 2,953 became zero. DarkPanda69 reproduced the failure on an RX 9070 XT and an RTX 3060, then checked both after the fix. On a third model, luckyteagirl passed the exact patched fixture on an RX 6800M, without running the parent or recording the physical wave width. The full PortBridge run on the fix passed 1,431 tests. To repeat, build the GPL-2.0-only XCL fork at `d3e7725f` and run `gpu_wave32_pixel_carry_preserves_adjacent_mask_at_triangle_edges` as in the linked instructions. The paired baseline/candidate title check requested by XCL and an upstream acceptance decision remain open. [Patch][wave] · [Reproduction][wrun] · [Paired independent results][dark] · [RX 6800M report][luck]

**3. XCL scratch-slot reuse, upstream draft #2322.** Kalmarv wrote the persistent-payload base merged in #2126. PortBridge supplied a separate allocator for disjoint lifetimes. On Kalmarv's earlier base, ettehn independently measured 47,712 → 20,064 DWORDs/workgroup with 12 valid pieces both times and passed eight focused hardware checks. That record has no GPU-time measurement. Preserve draft head `b3f7ab55` and its exact parent `afc5ee86` for paired reports. After a main-branch conflict, the separate compatibility fork `dfb580be` passed 11 focused checks in each allocator mode. The kit links reports from nnonno91 and luckyteagirl and includes the comparison script, build commands and requested three-workload fields. XCL patch GPL-2.0-only, Python comparator MIT. [Independent measurement][ett] · [Kit and licenses][scratch] · [Paired measurements requested][kal] · [Compatibility revision][dfb]

**4. Continued Vulkan #1713, upstream open and downstream reused.** DadaCap suggested a separate coalescing change. PortBridge combined adjacent rectangles with the same layout and aspect. In a controlled case the identical per-cell transitions used five barriers instead of fourteen. potatoe0100 checked head `ef9ae1fd` combined with `bcaa13dad` on RTX 4060. The three focused tests and 409 CTests passed. Leonida Ultimate took the attributed change at `e7124f97`. Its default branch `ultimate`, checked at `c9bd989e`, contained that commit with 198 subsequent commits. [Default-branch ancestry][forkline] Continued's own PR was still open. Re-run the pinned state-map and replay tests on a proposed merge with current main. Keep common mixed and singleton cases as controls. Continued code follows its GPLv3-or-later terms. A frame-rate gain has not been measured. [PR and commands][c1713] · [Fixture][cbench] · [Independent run][pot] · [Receiving fork][fork]

**5. KainanP's RDNA2 contribution, external PR #78.** KainanP supplied five source-only hardware probes at `81f607fa`. PortBridge verified assembly and linking and supplied `14bacd57` to reject unwritten outputs. Five full CPU cases passed and all 117 single omissions were rejected. The probes remain open for a physical compatible AMD GPU. Build and run from each probe's README, using the completion fix and recording the exact device/driver. #84 has a separate four-instruction runner. #85 still needs the complete published output, including A5, after earlier evidence was withdrawn. The submissions are in the MIT PortBridge repository. This handoff preserves the contributor's authorship and open PR. [Five probes and instructions][k78] · [Completeness fix][kfix] · [#84][k84] · [#85][k85]

**6. NVIDIA Vulkan mipmap portability, reported.** PortBridge showed that workgroup indices need not match subgroup positions. With an intentionally permuted logical mapping on an RTX, the original sample changed 14,194 output bytes; the guarded rewrite restored the reference. Three unmodified open textures gave 8,388,604 matching bytes on the ordinary mapping. akeley98, a former NVIDIA employee, replied unofficially that they knew of no 1D hardware example. No physical driver selecting the counterexample or upstream adoption was established. Reproduce on fixed full subgroups from the Apache-2.0 NVIDIA sample at `6c248f55`, with the model and texture provenance in PortBridge at `cb0faec3`. A naturally different mapping would be new evidence. [Original sample][nvrepo] · [Exact experiment][mip] · [Author's response][nv]

## Preserved branches and negative results

The [public revision inventory](engineering-inventory.json) lists 68 PortBridge pull requests, 89 branch and tag references, and 22 research and contribution guides as they stood before the handover release. The recorded pull-request heads and guides point to exact revisions.

| Package | Reason to keep it and what would justify more work |
| --- | --- |
| GPU-resident geometry · draft #75 · `88cede55` | The Blender implementation saved/reopened a correct native point cloud and rendered previews of the licensed 6.385-million-point Tokyo input. Fused CPU upload was slower, but the strongest resident GPU comparison gave no consistent advantage. Repeat the common renderer and geometry hashes only for a new use case. The report carries the Tokyo CC BY attribution and identifies Blender dependencies. [Integration, source and commands][bl] |
| Halide WebGPU previews · draft #76 · `c0775045` | Callback completion reduced two input-to-bitmap medians from 33.08 to 5.51 ms and 43.76 to 9.19 ms in the serialized Halide 22.1.0 path. Matched CPU SIMD took 0.885 and 6.334 ms. This remains a reference for users of that older runtime. Halide's pinned license grants an MIT-style permission. The astronaut photograph has no known copyright restrictions and the Hubble image is public domain. [Input provenance][halinputs] · [Halide license][hallicense] [Revisions, inputs and reproduction][hal] |
| Cold Pipeline Readiness · draft #77 · `64280ea4` | Hosts ordered recording, Read Guard Fusion, root/UMA specializations, performance receipts and withdrawn mask experiments. Read Guard Fusion's 11.4× result was synthetic. In the initial external set it applied to 1/72 configurations with one memory window and 0/72 with four. Broad Lane-local Masks failed at triangle edges. Use the later SSA package for new experiments. Start with the status table and original baselines before copying a patch. [Status and attribution][pr77] · [Pinned research tree][arch77] · [Counterexample][p77lane] |
| Earlier reference components | The exact Buffer Transfer Planner beat greedy zero times among 596 changed uncapped observations. Subgroup transport, switch dispatch, tail factoring and transient slots have bounded reference tests. Observation-scoped/adaptive readbacks and compute dependencies preserve ordering and lifetime experiments. Their READMEs pin the workloads and contain reproduction commands. Reopening needs a workload that actually exercises the documented bottleneck. [Planner][ref62] · [Compiler and memory studies][ref67] · [Readback and dependencies][ref74] |

PortBridge's original tooling uses the [MIT license][license]. Patches for other repositories and external shaders, sample images and fixtures retain the notices identified at their source revisions. A public comparison or an index entry does not grant permission to redistribute external assets. Keep the license files, revision, command, device, skips and negative controls together when continuing a result.

## Ecosystem at handoff

The snapshot below queried public Git default-branch heads on 26 November at 02:23 UTC for the 45 catalog entries plus associated addresses, deduplicated. Forty-two of 48 addresses returned a head. A failed lookup means that this route gave no usable revision at this time. Historical records remain available. Default-branch availability says nothing about technical maturity, private activity or acceptance of PortBridge code. KLBF's separate beta points contributors back to KLBF Lab. Forked reports may share ancestry. For tracker links and individual origins use the earlier [source audit][eco] and the [live source health][coverage].

| Public origin | Default branch | Revision |
| --- | --- | --- |
| [0x0007b/XBVK](https://github.com/0x0007b/XBVK) | main | [858cd6abf](https://github.com/0x0007b/XBVK/commit/858cd6abf750af0616a29a1d3f62c564ef1f408c) |
| [5headsmartbtw/leonida-framelab](https://github.com/5headsmartbtw/leonida-framelab) | main | [c3d404b65](https://github.com/5headsmartbtw/leonida-framelab/commit/c3d404b65ff31f3377a16dc4483774cc0711239d) |
| [7jycwjmbfn-eng/scenegate-vi](https://github.com/7jycwjmbfn-eng/scenegate-vi) | — | Unavailable on this check |
| [Aoody743/MetalVI](https://github.com/Aoody743/MetalVI) | main | [c6e693a83](https://github.com/Aoody743/MetalVI/commit/c6e693a833d4a490a3db2a9749a5da800e72e61e) |
| [Batushn/KestrelX](https://github.com/Batushn/KestrelX) | main | [cd55dac83](https://github.com/Batushn/KestrelX/commit/cd55dac8376ab94e7c88290eefcd3559420779c1) |
| [Belobug/VIctory-Belobug-AMD](https://github.com/Belobug/VIctory-Belobug-AMD) | rx9070xt | [81ebb7bdc](https://github.com/Belobug/VIctory-Belobug-AMD/commit/81ebb7bdc9b7ca6ec2f3169973f50be77c7c803c) |
| [DesignWithTommy/Neonbridge](https://github.com/DesignWithTommy/Neonbridge) | main | [762a13d01](https://github.com/DesignWithTommy/Neonbridge/commit/762a13d011bb35cee861802f9f285e9ae1f7dcbf) |
| [Geckomacabre/vx-layer](https://github.com/Geckomacabre/vx-layer) | main | [ac69b9647](https://github.com/Geckomacabre/vx-layer/commit/ac69b96477ee4f59fcfcd16b9cd0a0862c467cc2) |
| [IAmNotSiob/leonida-ce](https://github.com/IAmNotSiob/leonida-ce) | main | [b3c6eadfc](https://github.com/IAmNotSiob/leonida-ce/commit/b3c6eadfc428eca06c2235d4383c8dbe3dd69cb6) |
| [Its3rr0rsWRLD/XPortPC](https://github.com/Its3rr0rsWRLD/XPortPC) | main | [40218cd69](https://github.com/Its3rr0rsWRLD/XPortPC/commit/40218cd69af60186b1a3fe707f208d368599f25b) |
| [JMAN730/project-flamingo](https://github.com/JMAN730/project-flamingo) | main | [d7aa42a45](https://github.com/JMAN730/project-flamingo/commit/d7aa42a45a0a63423db29086f798ace539301f0c) |
| [Joaco9020/mangrove](https://github.com/Joaco9020/mangrove) | main | [8c7bb8581](https://github.com/Joaco9020/mangrove/commit/8c7bb85813ab9c62d1249a7d53e115778e5e7771) |
| [KretliJ/victory-monitor](https://github.com/KretliJ/victory-monitor) | main | [b8c25227d](https://github.com/KretliJ/victory-monitor/commit/b8c25227df61a5dfcfa1db66b28f7cb152053099) |
| [LeonidaReforge/Leonida](https://github.com/LeonidaReforge/Leonida) | — | Unavailable on this check |
| [LooperSalty/AnyXboxX](https://github.com/LooperSalty/AnyXboxX) | main | [c4c93bdc4](https://github.com/LooperSalty/AnyXboxX/commit/c4c93bdc413191a9dc909998d2d53080a3f0c880) |
| [Marvisak/VIctory](https://github.com/Marvisak/VIctory) | main | [63bcca43c](https://github.com/Marvisak/VIctory/commit/63bcca43c6a00a758510398fa43096ce7e4f7df0) |
| [MiamiGame/XTP](https://github.com/MiamiGame/XTP) | main | [9b822f588](https://github.com/MiamiGame/XTP/commit/9b822f58870e351613666129ca5621c6a4955fb7) |
| [OpenCommunityEdition/OpenScarlett](https://github.com/OpenCommunityEdition/OpenScarlett) | main | [e043ba44c](https://github.com/OpenCommunityEdition/OpenScarlett/commit/e043ba44c9b894656939f21d4d33ef2c97e5f081) |
| [PastiiJay/klbf-lab](https://github.com/PastiiJay/klbf-lab) | main | [420e1e124](https://github.com/PastiiJay/klbf-lab/commit/420e1e12485f0f652bfc2989723a273cab51669a) |
| [PastiiJay/klbf-lab-beta](https://github.com/PastiiJay/klbf-lab-beta) | klbf-lab | [b6ba1c50d](https://github.com/PastiiJay/klbf-lab-beta/commit/b6ba1c50dc8d89fcb43f758333ec843c0a9a9123) |
| [R0Y00/Xbox2Windows](https://github.com/R0Y00/Xbox2Windows) | main | [e76f8acd5](https://github.com/R0Y00/Xbox2Windows/commit/e76f8acd5a269bfec48ea65203f2b7868fb14df3) |
| [ReverendOzmund/xseries-wine](https://github.com/ReverendOzmund/xseries-wine) | main | [89aa2462c](https://github.com/ReverendOzmund/xseries-wine/commit/89aa2462ce57c96fa3b1584c05e3d5dd6b7d8b84) |
| [ThatRecompDev/five-star-recomp](https://github.com/ThatRecompDev/five-star-recomp) | main | [397a2335e](https://github.com/ThatRecompDev/five-star-recomp/commit/397a2335ebf950303f0a9629fd1b2a7b2214726f) |
| [Zettrox/ztrx](https://github.com/Zettrox/ztrx) | — | Unavailable on this check |
| [ZigZagBoi1/ScarlettPort](https://github.com/ZigZagBoi1/ScarlettPort) | main | [771f5ce51](https://github.com/ZigZagBoi1/ScarlettPort/commit/771f5ce51f783e0f11916f9086a2b203a0bb62ef) |
| [akimfomin/PortBridge](https://github.com/akimfomin/PortBridge) | main | [2223a0b6a](https://github.com/akimfomin/PortBridge/commit/2223a0b6a4dbaac1e98f8f90204b190296c4ef75) |
| [boykopovar/AnyBox](https://github.com/boykopovar/AnyBox) | main | [9c0347351](https://github.com/boykopovar/AnyBox/commit/9c03473518fbfdd9b354c4ceff7a787ed55d481c) |
| [brcly/TuxBox](https://github.com/brcly/TuxBox) | main | [4f7fa84c0](https://github.com/brcly/TuxBox/commit/4f7fa84c0e1667bcb164986c13d6c1fe9876e349) |
| [californiaAlmonds/OpenScarlett](https://github.com/californiaAlmonds/OpenScarlett) | main | [7220ce949](https://github.com/californiaAlmonds/OpenScarlett/commit/7220ce949800a959535086ce175b1e13b738aa16) |
| [clquwu/leonida-ultimate](https://github.com/clquwu/leonida-ultimate) | ultimate | [c9bd989ee](https://github.com/clquwu/leonida-ultimate/commit/c9bd989eef71eb0513292b9a405d2c5912a1c069) |
| [cmyk-ux/r4y](https://github.com/cmyk-ux/r4y) | main | [034bf2e1f](https://github.com/cmyk-ux/r4y/commit/034bf2e1fb2f708dc612225a733e00ee05426dbb) |
| [fablinoo/palmwave](https://github.com/fablinoo/palmwave) | — | Unavailable on this check |
| [fxceless/victory-fork](https://github.com/fxceless/victory-fork) | main | [18ea64478](https://github.com/fxceless/victory-fork/commit/18ea644783b3dfe82082d52c9f3dc600a9f176a9) |
| [idvwork/rebox](https://github.com/idvwork/rebox) | — | Unavailable on this check |
| [jadeowaowa/scarlett-layer](https://github.com/jadeowaowa/scarlett-layer) | main | [0e436b3e1](https://github.com/jadeowaowa/scarlett-layer/commit/0e436b3e1c654765b193c1cb705918fbf101b10b) |
| [mewiof/Holy-Interoperability](https://github.com/mewiof/Holy-Interoperability) | main | [a991f51c6](https://github.com/mewiof/Holy-Interoperability/commit/a991f51c6726b390ba85bbfed1b27434f28201b1) |
| [myokex/victory-amd](https://github.com/myokex/victory-amd) | vi-fx3 | [aa8399e5b](https://github.com/myokex/victory-amd/commit/aa8399e5b5e96af2cab80d01aa636c772cdae54e) |
| [nvpro-samples/vk_compute_mipmaps](https://github.com/nvpro-samples/vk_compute_mipmaps) | main | [6c248f554](https://github.com/nvpro-samples/vk_compute_mipmaps/commit/6c248f554e91329875e9860f2258019a32b44ee9) |
| [pablogonz12/Scarlight](https://github.com/pablogonz12/Scarlight) | main | [9a432787b](https://github.com/pablogonz12/Scarlight/commit/9a432787b6f40411063517363afa71a6ba86674e) |
| [pragyaangaur/VIctory-macOS](https://github.com/pragyaangaur/VIctory-macOS) | main | [b6dd0b184](https://github.com/pragyaangaur/VIctory-macOS/commit/b6dd0b184277fc307b93a4cc90d23dca9f05e7b3) |
| [rpatty-dev/PercyScarlett](https://github.com/rpatty-dev/PercyScarlett) | main | [e44c465e4](https://github.com/rpatty-dev/PercyScarlett/commit/e44c465e47ab5b29ca87777cd00875e2ae0d8c0d) |
| [sammwyy/xvalkyrie](https://github.com/sammwyy/xvalkyrie) | main | [ae50d83e8](https://github.com/sammwyy/xvalkyrie/commit/ae50d83e8117446d557d0d96ca53f720c797b71f) |
| [scarlett-commons/scarlett-commons](https://github.com/scarlett-commons/scarlett-commons) | main | [fa6ad1d45](https://github.com/scarlett-commons/scarlett-commons/commit/fa6ad1d452b937e2544a9190f9418e219b3dc84a) |
| [sub-north/xbox-hle-lab](https://github.com/sub-north/xbox-hle-lab) | main | [8863028b4](https://github.com/sub-north/xbox-hle-lab/commit/8863028b486dedf660303fcd3c756b05bbbebf91) |
| [ubiquitarianism/leonida](https://github.com/ubiquitarianism/leonida) | main | [3abb99cad](https://github.com/ubiquitarianism/leonida/commit/3abb99cad9e2cc3a356a7f78eb310b6ca93aae00) |
| [uiliannn/VItoriaBr](https://github.com/uiliannn/VItoriaBr) | main | [85615ad3d](https://github.com/uiliannn/VItoriaBr/commit/85615ad3d78b8efc9c42d34538f9099a6d3cb30a) |
| [vitutu1/victory-perf](https://github.com/vitutu1/victory-perf) | — | Unavailable on this check |
| [xcl-dev/xcl](https://github.com/xcl-dev/xcl) | main | [b49be1836](https://github.com/xcl-dev/xcl/commit/b49be1836844fe0b0cdb3211dce3cb7fb4e21ac7) |

The founder's [central discussion][future] welcomes anyone taking ownership of a check, source or component. A proposed continuation needs only a named package, an exact revision and one result another person can verify. [Run the project][maint] · [Open Test Lab][forms]

[start]: https://github.com/akimfomin/PortBridge/commit/ea9caeb024211b55330b1c8663233974fd60ed81
[lab]: https://github.com/akimfomin/PortBridge/commit/0f09c81f56c999d52715a8dbb5fd72258b16ec9f
[search]: SEARCH-EVALUATION.md
[radar]: https://github.com/akimfomin/PortBridge/commit/ec513d743cfa80c04d58dd9d9a3de237a2194db5
[log]: COMMUNITY-COORDINATION.md
[d16]: https://github.com/LooperSalty/AnyXboxX/commit/b15d8821bffcd8fbc98e56f41daf07fc91118192
[warp]: https://github.com/LooperSalty/AnyXboxX/commit/becaf7829d2aa03c293e0b52125fc740c5590ea1
[bc7]: https://github.com/LooperSalty/AnyXboxX/pull/202
[pillow]: https://github.com/akimfomin/PortBridge/blob/b1c330e5c03f3467a73a593cb7a4edcc8180dafd/research/anyxboxx-188-textures/BC7-INDEPENDENT.md
[fma]: https://github.com/LooperSalty/AnyXboxX/pull/203
[c133]: https://github.com/LooperSalty/AnyXboxX/commit/71d4c615c6981280b95c11290fd48ef015b5d4cb
[lyrnc]: https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663
[gfx]: https://github.com/LooperSalty/AnyXboxX/pull/188#issuecomment-7166158013
[gfxcode]: https://github.com/LooperSalty/AnyXboxX/commit/c5ca937c371d8b21e56feb36f3d009ecffe5765a
[frame]: https://github.com/5headsmartbtw/leonida-framelab/commit/d1da938ecf7b4e3d3faf40e5046907ba48986125
[joe]: https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160148587
[klbf]: https://github.com/xcl-dev/xcl/pull/1100#issuecomment-7144197194
[victory]: https://github.com/Marvisak/VIctory/pull/571#issuecomment-7128201680
[main90]: https://github.com/akimfomin/PortBridge/tree/2223a0b6a4dbaac1e98f8f90204b190296c4ef75/research/pipeline-readiness/ssa-quad-projection
[ssa]: https://github.com/akimfomin/xcl/commit/5d04cc10fa11654179d4bde0c1fcdc1d7ffb2cbc
[raw]: https://github.com/akimfomin/PortBridge/blob/806a4c0dec2364c8881e1efb437964ac4aa42b27/research/pipeline-readiness/structural-suite/night/vulkan/mobile-nerf/translated/measurements.json
[receipt]: ../research/pipeline-readiness/structural-suite/night/ssa-mask-projection/consumer-demand
[ask87]: https://github.com/akimfomin/PortBridge/issues/87
[wave]: https://github.com/akimfomin/xcl/commit/d3e7725f9f48c39c18e7b6e011ec76423edb0004
[dark]: https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7178879816
[luck]: https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7179418085
[wrun]: https://github.com/akimfomin/PortBridge/blob/6b772bc2805809e966ddc42bb933f10546e361ec/research/pipeline-readiness/structural-suite/night/wave32-carry/precise/README.md
[scratch]: ../research/xcl-compact-scratch-adoption
[kal]: https://github.com/xcl-dev/xcl/pull/2322#issuecomment-7167441435
[ett]: https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7162128623
[dfb]: https://github.com/akimfomin/xcl/commit/dfb580beccbc1fe4353544a5068245d502de9bfa
[c1713]: https://github.com/ubiquitarianism/leonida/pull/1713
[pot]: https://github.com/ubiquitarianism/leonida/pull/1713#issuecomment-7161475134
[fork]: https://github.com/clquwu/leonida-ultimate/commit/e7124f97bff187968a30931fb31e7c42bd88622b
[cbench]: https://github.com/akimfomin/PortBridge/tree/049b46286518c20d98dc74ae700e66599110d964/research/continued-layout-range-coalescing
[k78]: https://github.com/akimfomin/PortBridge/pull/78
[kfix]: https://github.com/akimfomin/PortBridge/commit/14bacd57bca9d7244f8ba964b5ce499248f21bc2
[k84]: https://github.com/akimfomin/PortBridge/issues/84#issuecomment-7179304828
[k85]: https://github.com/akimfomin/PortBridge/issues/85#issuecomment-7175680680
[nv]: https://github.com/nvpro-samples/vk_compute_mipmaps/issues/4#issuecomment-7171169383
[mip]: https://github.com/akimfomin/PortBridge/blob/cb0faec3b66e9d97f120de17288f1e5435757156/research/mipmap-contract/benchmark/OPEN-TEXTURES.md
[nvrepo]: https://github.com/nvpro-samples/vk_compute_mipmaps/tree/6c248f554e91329875e9860f2258019a32b44ee9
[bl]: https://github.com/akimfomin/PortBridge/tree/88cede556d9613a6e09964a1c7fdc15fc9449a0c/research/geometry-residency/viewport
[hal]: https://github.com/akimfomin/PortBridge/tree/c07750453d6b0b70218a5f94edd851deb1500b8f/research/halide-gpu-waits
[arch77]: https://github.com/akimfomin/PortBridge/tree/64280ea4688f152100360403adb33f527f36c0a9/research/pipeline-readiness
[pr77]: https://github.com/akimfomin/PortBridge/pull/77
[p77lane]: https://github.com/akimfomin/PortBridge/blob/9c2616998e176806565ee1a0076dc4efb7ae4dc1/research/pipeline-readiness/structural-suite/LANE-MASKS.md
[ref62]: https://github.com/akimfomin/PortBridge/tree/1c74fd6253bcb5c20ab8be7db56e5ee4df61f7e3/research/transfer-planner/physical
[ref67]: https://github.com/akimfomin/PortBridge/tree/52934fc07afd5039f1234fc58450afea41e9bc26/research
[ref74]: https://github.com/akimfomin/PortBridge/tree/d78d300a3659e6ecb7a621a607aacaa88af4a64b/research
[eco]: ECOSYSTEM-AUDIT-2026-11-25.md
[license]: ../LICENSE
[future]: https://github.com/akimfomin/PortBridge/issues/91
[maint]: PASSIVE-MAINTENANCE.md
[forms]: https://akimfomin.github.io/PortBridge/#/lab
[coverage]: https://akimfomin.github.io/PortBridge/data/health.json

[forkline]: https://github.com/clquwu/leonida-ultimate/compare/e7124f97bff187968a30931fb31e7c42bd88622b...c9bd989eef71eb0513292b9a405d2c5912a1c069
[added]: https://github.com/Ahmet-Dedeler/awesome-gta6-reverse-engineering/issues/25#issuecomment-7164547746
[declined]: https://github.com/vuyp/gta6-pc-race/issues/6#issuecomment-7160857502
[halinputs]: https://github.com/akimfomin/PortBridge/blob/c07750453d6b0b70218a5f94edd851deb1500b8f/research/halide-gpu-waits/REPRODUCTION_INPUTS.md
[hallicense]: https://github.com/halide/Halide/blob/v22.1.0/LICENSE.txt
[board]: https://github.com/Github-Samuel/sixonpc/blob/e721e0f98d4baf3dd0a95e70c4555410f33a98c2/board.mjs#L187
