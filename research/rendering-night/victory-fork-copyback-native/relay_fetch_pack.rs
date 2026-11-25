// SPDX-License-Identifier: GPL-3.0-or-later
//! Pack consecutive reads from one buffer and preserve the merge schedule.

const LIMIT: usize = 1024 * 1024;

pub(super) struct FetchCopy {
    /// The first logical piece supplies the source, start and destination.
    pub(super) first: usize,
    pub(super) end: usize,
}

/// Replace each piece's old destination offset with its position inside
/// the packed staging buffer. Input consists of nonempty, bounded pieces.
/// The logical pieces stay in their original order, even across overlaps.
pub(super) fn pack_reads<T>(
    pieces: &mut [(T, usize, usize, u64)],
    same: impl Fn(&T, &T) -> bool,
) -> (Vec<FetchCopy>, u64) {
    let mut copies: Vec<FetchCopy> = Vec::new();
    let mut total = 0;
    for i in 0..pieces.len() {
        let (source, from, to, _) = &pieces[i];
        let (from, to) = (*from, *to);
        if let Some(last) = copies.last_mut() {
            let (owner, start, _, at) = &pieces[last.first];
            if from >= *start && from <= last.end && to - *start <= LIMIT && same(source, owner) {
                let offset = *at + (from - *start) as u64;
                total += to.saturating_sub(last.end) as u64;
                last.end = last.end.max(to);
                pieces[i].3 = offset;
                continue;
            }
        }
        copies.push(FetchCopy { first: i, end: to });
        pieces[i].3 = total;
        total += (to - from) as u64;
    }
    (copies, total)
}
