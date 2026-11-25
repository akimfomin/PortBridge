use std::hint::black_box;

use anyxboxx_baseline as baseline;
use anyxboxx_candidate as candidate;

fn random(state: &mut u64) -> u64 {
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    *state
}

fn block(mode: usize, partition: u32, rotation: u32, selection: u32, state: &mut u64) -> [u8; 16] {
    let m = baseline::bc7::MODES[mode];
    let mode_bits = mode as u32 + 1;
    let rotation_at = mode_bits + m.partition_bits;
    let selection_at = rotation_at + m.rotation_bits;
    let header_bits = selection_at + m.selection_bits;
    let source = u128::from(random(state)) << 64 | u128::from(random(state));
    let fields = (1u128 << mode) | (u128::from(partition) << mode_bits)
        | (u128::from(rotation) << rotation_at) | (u128::from(selection) << selection_at);
    ((source & (!0u128 << header_bits)) | fields).to_le_bytes()
}

fn surface_blocks(width: usize, height: usize, state: &mut u64) -> Vec<u8> {
    let count = width.div_ceil(4) * height.div_ceil(4);
    (0..count).flat_map(|i| {
        let mode = i % 8;
        let m = baseline::bc7::MODES[mode];
        let partition = (random(state) as u32) & ((1 << m.partition_bits) - 1);
        let rotation = (random(state) as u32) & ((1 << m.rotation_bits) - 1);
        let selection = (random(state) as u32) & ((1 << m.selection_bits) - 1);
        block(mode, partition, rotation, selection, state)
    }).collect()
}

fn compare_blocks(state: &mut u64) -> usize {
    let mut tested = 0;
    for (mode, m) in baseline::bc7::MODES.iter().enumerate() {
        for partition in 0..(1 << m.partition_bits) {
            assert_eq!(candidate::bc7::anchors(mode, partition as usize), baseline::bc7::anchors(mode, partition as usize));
            assert_eq!(candidate::bc7::layout(mode, partition as usize), baseline::bc7::layout(mode, partition as usize));
            for rotation in 0..(1 << m.rotation_bits) {
                for selection in 0..(1 << m.selection_bits) {
                    for _ in 0..16 {
                        let bytes = block(mode, partition, rotation, selection, state);
                        assert_eq!(candidate::bc7::decode(&bytes), baseline::bc7::decode(&bytes),
                            "mode {mode}, partition {partition}, rotation {rotation}, selection {selection}");
                        tested += 1;
                    }
                }
            }
        }
    }
    for _ in 0..64 {
        let mut bytes = block(7, 0, 0, 0, state);
        bytes[0] = 0;
        assert_eq!(candidate::bc7::decode(&bytes).unwrap(), [0; 64]);
    }
    for len in (0..33).filter(|&len| len != 16) {
        let malformed = vec![1; len];
        assert_eq!(candidate::bc7::decode(&malformed), baseline::bc7::decode(&malformed));
    }
    tested
}

fn compare_surfaces(state: &mut u64) -> usize {
    let mut tested = 0;
    for width in 0..=19 {
        for height in 0..=19 {
            let blocks = surface_blocks(width, height, state);
            assert_eq!(candidate::decode_surface(&blocks, width, height), baseline::decode_surface(&blocks, width, height),
                "surface {width}×{height}");
            for wrong_length in [blocks.len().saturating_sub(1), blocks.len() + 1] {
                let bad = vec![0; wrong_length];
                assert_eq!(candidate::decode_surface(&bad, width, height), baseline::decode_surface(&bad, width, height));
            }
            tested += 1;
        }
    }
    tested
}

#[cfg(count_allocations)]
mod allocations {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed};

    struct Counter;
    static COUNTING: AtomicBool = AtomicBool::new(false);
    static ALLOCATIONS: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static ALLOCATOR: Counter = Counter;

    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            if COUNTING.load(Relaxed) { ALLOCATIONS.fetch_add(1, Relaxed); }
            unsafe { System.alloc(layout) }
        }
        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            if COUNTING.load(Relaxed) { ALLOCATIONS.fetch_add(1, Relaxed); }
            unsafe { System.alloc_zeroed(layout) }
        }
        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            if COUNTING.load(Relaxed) { ALLOCATIONS.fetch_add(1, Relaxed); }
            unsafe { System.realloc(ptr, layout, size) }
        }
        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            unsafe { System.dealloc(ptr, layout) }
        }
    }

    pub(super) fn measure<T>(decode: impl FnOnce() -> T) -> (T, usize) {
        ALLOCATIONS.store(0, Relaxed);
        COUNTING.store(true, Relaxed);
        let result = decode();
        COUNTING.store(false, Relaxed);
        (result, ALLOCATIONS.load(Relaxed))
    }
}

#[cfg(count_allocations)]
fn compare_allocations(state: &mut u64) {
    let bytes = block(2, 19, 0, 0, state);
    let (before, old) = allocations::measure(|| baseline::bc7::decode(black_box(&bytes)).unwrap());
    let (after, new) = allocations::measure(|| candidate::bc7::decode(black_box(&bytes)).unwrap());
    assert_eq!(before, after);
    assert_eq!((old, new), (1, 0));
    println!("full_block_allocations={old}->{new}");

    let blocks = surface_blocks(64, 128, state);
    let (before, old) = allocations::measure(|| baseline::decode_surface(black_box(&blocks), 64, 128).unwrap());
    let (after, new) = allocations::measure(|| candidate::decode_surface(black_box(&blocks), 64, 128).unwrap());
    assert_eq!(before, after);
    assert_eq!((old, new), (513, 1));
    println!("surface_64x128_512_blocks_allocations={old}->{new}");
}

#[cfg(not(count_allocations))]
fn benchmark(name: &str, variant: &str, state: &mut u64) {
    use std::time::Instant;
    let (width, height, repeats) = match name {
        "rgba4k" => (3840, 2160, 2),
        "rgba1080_odd" => (1919, 1079, 4),
        "thin_crop" => (257, 3, 500),
        "block" => (4, 4, 50_000),
        _ => panic!("unknown case {name}"),
    };
    let decode = match variant {
        "baseline" => baseline::decode_surface,
        "candidate" => candidate::decode_surface,
        _ => panic!("unknown variant {variant}"),
    };
    let blocks = surface_blocks(width, height, state);
    let warm = decode(&blocks, width, height).unwrap();
    let hash = warm.iter().fold(0xcbf2_9ce4_8422_2325u64, |hash, &byte| (hash ^ u64::from(byte)).wrapping_mul(0x100_0000_01b3));
    drop(warm);
    let start = Instant::now();
    for _ in 0..repeats {
        black_box(decode(black_box(&blocks), width, height).unwrap());
    }
    println!("{name},{variant},{},{hash:016x}", start.elapsed().as_nanos() / repeats);
}

fn main() {
    let mut state = 0x69be_bada_ac90_7221;
    let args: Vec<_> = std::env::args().skip(1).collect();
    #[cfg(count_allocations)]
    if args.is_empty() {
        let blocks = compare_blocks(&mut state);
        let surfaces = compare_surfaces(&mut state);
        println!("block_payloads={blocks} surfaces={surfaces} reserved=64 errors_checked=true");
        compare_allocations(&mut state);
        return;
    }
    #[cfg(not(count_allocations))]
    if let [name, variant] = &args[..] {
        benchmark(name, variant, &mut state);
        return;
    }
    panic!("incorrect fixture mode");
}
