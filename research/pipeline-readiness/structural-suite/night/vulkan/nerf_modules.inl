// SPDX-License-Identifier: MIT
// This receiver supplies physical shader addresses. Its shader pair must be the
// known Khronos vertex and one of the six translated fixtures after preparation.
std::string shader_sha(const std::vector<uint32_t>& words) {
    HCRYPTPROV provider{};
    if (!CryptAcquireContextW(&provider, nullptr, nullptr, PROV_RSA_AES, CRYPT_VERIFYCONTEXT))
        throw std::runtime_error("SHA-256 provider unavailable");
    HCRYPTHASH hash{};
    std::array<BYTE, 32> bytes{};
    DWORD size = static_cast<DWORD>(bytes.size());
    bool ok = CryptCreateHash(provider, CALG_SHA_256, 0, 0, &hash) &&
              CryptHashData(hash, reinterpret_cast<const BYTE*>(words.data()), static_cast<DWORD>(words.size() * 4), 0) &&
              CryptGetHashParam(hash, HP_HASHVAL, bytes.data(), &size, 0);
    if (hash) CryptDestroyHash(hash);
    CryptReleaseContext(provider, 0);
    if (!ok || size != bytes.size()) throw std::runtime_error("Failed to fingerprint SPIR-V");
    std::string result;
    constexpr char digits[] = "0123456789abcdef";
    for (BYTE b : bytes) { result += digits[b >> 4]; result += digits[b & 15]; }
    return result;
}

void check_nerf_modules(const std::vector<uint32_t>& vertex, const std::vector<uint32_t>& fragment) {
    if (shader_sha(vertex) != "f71776a102da871a6d287231e50532d31c40e67b129cafcff3843bea901805eb")
        throw std::runtime_error("Unexpected Mobile NeRF vertex module");
    constexpr std::string_view reviewed[] = {
        "20ed5b34446b6ee56ebdad547b0c08cbc806a80537ad96bf4508db2b168cc5e1",  // nerf71-gamma-bounded
        "ab11d670ac348ff60d4de41ffe94c3c0a4a809e54a0629946ea1557706592064",  // nerf71-gamma-typed
        "c5caa7dfa2ca35d1985b2b77d8e65b2715517e9182635ff9f4fca295b2da4458",  // nerf71-strict-bounded
        "fddd7f76ea94c8ba6bc217a5d36f35c0e2c5ce182a22bb146b8b765829c7e086",  // nerf71-strict-typed
        "8a8b7b9ee6cfb6de5b7d2c7062bf28a0caceb44360b56d440e6861a8bf4a5984",  // nerf71-whole-bounded
        "01e26c7ae50d0ccb682868b9cd2d84893df992c92b659c44daa365665dc13a79",  // nerf71-whole-typed
        "d16ba6d95135b2d0d0bc48101358e55df3972975a762f5b7556332ec34e444bb",  // nerf73-gamma-bounded
        "83ef589a44974f89c8155510a0bc5c2ca758c8fee696601f240b2464f5b7e968",  // nerf73-gamma-typed
        "bde5f4bc8052a73691a72362bd8997c7a00c76df8507c3940f839b58a68f8d91",  // nerf73-strict-bounded
        "d1e02e8e20b0c835caad408ce7502be0cbfae0f168088118f552e421d96bbcb0",  // nerf73-strict-typed
        "11db5fea6d397353a1a65b18777aaf608245d4e9b81870bfcad4e43f87dffc0a",  // nerf73-whole-bounded
        "4492aa0c9e3271a4829259b7a1f8cc1b695af84d95c4ed1375e2c9de26b497db",  // nerf73-whole-typed
    };
    const std::string identity = shader_sha(fragment);
    for (const auto allowed : reviewed) if (identity == allowed) return;
    throw std::runtime_error("Prepare a reviewed bounded Mobile NeRF fragment before drawing");
}
