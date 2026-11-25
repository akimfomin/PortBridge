#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct CacheKey(blake3::Hash);

impl CacheKey {
    pub fn from_parts(id: &str, version: u32, input: &[&[u8]]) -> Self {
        let mut h = blake3::Hasher::new();
        h.update(id.as_bytes());
        h.update(&[0]);
        h.update(&version.to_le_bytes());
        for part in input {
            h.update(part);
        }
        CacheKey(h.finalize())
    }

    pub fn to_hex(&self) -> String {
        self.0.to_hex().to_string()
    }
}

fn canonical_container(bytes: &[u8]) -> &[u8] {
    if bytes.starts_with(b"DXBC")
        && let Some(size) = bytes.get(0x18..0x1c)
    {
        let size = u32::from_le_bytes(size.try_into().expect("four bytes")) as usize;
        if size >= 0x20
            && let Some(container) = bytes.get(..size)
        {
            return container;
        }
    }
    bytes
}

fn shader_key(build: &[u8; 32], [wave, view_limit]: [u32; 2], container: &[u8]) -> CacheKey {
    // Bump the format version if the serialized HostShader or refusal changes.
    CacheKey::from_parts(
        "shader.dxil",
        2,
        &[
            build,
            &wave.to_le_bytes(),
            &view_limit.to_le_bytes(),
            container,
        ],
    )
}

pub(crate) fn name(kind: &str, root: &[u8], code: &[&[u8]], state: &str) -> String {
    let mut h = blake3::Hasher::new();
    for part in [kind.as_bytes(), root].into_iter().chain(code.iter().copied()).chain([state.as_bytes()]) {
        h.update(&(part.len() as u64).to_le_bytes());
        h.update(part);
    }
    h.finalize().to_hex()[..32].to_owned()
}
