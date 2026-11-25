// SPDX-License-Identifier: GPL-3.0-or-later
//! Rectangles for posting an already updated 2D staging buffer to D3D12.

use std::ops::Range;

use crate::texture::{Dimension, Error, Layout, Swizzle};

const MAX_BOXES: usize = 8;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Rect {
    pub left: u32,
    pub top: u32,
    pub right: u32,
    pub bottom: u32,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Plan {
    Unchanged,
    Full,
    Regions(Vec<Rect>),
}

/// Dirty byte intervals are sorted and disjoint, relative to the full
/// tiled allocation. The caller already updated the persistent linear
/// staging buffer and must check D3D12 format and plane eligibility.
pub fn plan(
    layout: &Layout,
    mip: u32,
    slice: u32,
    color_partial_copy_supported: bool,
    dirty: &[Range<u64>],
) -> Result<Plan, Error> {
    let m = layout.mips.get(mip as usize).ok_or(Error::Invalid)?;
    let desc = &layout.desc;
    if slice >= layout.slices || (desc.dimension == Dimension::Tex3d && slice != 0) {
        return Err(Error::Invalid);
    }
    if dirty.iter().any(|r| r.start > r.end || r.end > layout.size)
        || dirty.windows(2).any(|rs| rs[0].end > rs[1].start)
    {
        return Err(Error::Invalid);
    }
    if dirty.iter().all(Range::is_empty) {
        return Ok(Plan::Unchanged);
    }

    let side = desc.block;
    let width = (desc.width >> mip).max(1);
    let height = (desc.height >> mip).max(1);
    if !color_partial_copy_supported
        || desc.dimension != Dimension::Tex2d
        || desc.samples != 1
        || !layout.addressable()
        || desc.swizzle == Swizzle::LINEAR
        || m.tail.is_some()
        || !width.is_multiple_of(side)
        || !height.is_multiple_of(side)
    {
        return Ok(Plan::Full);
    }

    let [block_w, block_h, _] = layout.block;
    let blocks_per_row = u64::from(m.pitch / block_w);
    let bytes_per_block = layout.alignment;
    let base = u64::from(slice) * layout.slice_size + m.offset;
    let size = blocks_per_row * u64::from(m.rows / block_h) * bytes_per_block;
    let end = base + size;
    let clipped = dirty.iter().filter_map(|range| {
        let a = range.start.max(base);
        let b = range.end.min(end);
        (a < b).then(|| ((a - base) / bytes_per_block)..((b - base).div_ceil(bytes_per_block)))
    });

    let mut boxes = Vec::<Rect>::new();
    let mut pending: Option<Range<u64>> = None;
    let mut append = |tiles: Range<u64>| {
        let mut at = tiles.start;
        while at < tiles.end {
            let row = at / blocks_per_row;
            let col = at % blocks_per_row;
            let (rows, cols) = if col == 0 && tiles.end - at >= blocks_per_row {
                ((tiles.end - at) / blocks_per_row, blocks_per_row)
            } else {
                (1, (tiles.end - at).min(blocks_per_row - col))
            };
            at += rows * cols;
            let left = col as u32 * block_w * side;
            let top = row as u32 * block_h * side;
            let right = ((col + cols) as u32 * block_w * side).min(width);
            let bottom = ((row + rows) as u32 * block_h * side).min(height);
            if left >= right || top >= bottom {
                continue;
            }

            if let Some(last) = boxes.last_mut()
                && last.left == left && last.right == right && last.bottom == top
            {
                last.bottom = bottom;
                continue;
            }
            if boxes.len() == MAX_BOXES {
                return false;
            }
            boxes.push(Rect { left, top, right, bottom });
        }
        true
    };

    for tiles in clipped {
        if let Some(previous) = pending.as_mut()
            && tiles.start <= previous.end
        {
            previous.end = previous.end.max(tiles.end);
            continue;
        }
        if let Some(previous) = pending.replace(tiles)
            && !append(previous)
        {
            return Ok(Plan::Full);
        }
    }
    if let Some(last) = pending
        && !append(last)
    {
        return Ok(Plan::Full);
    }
    let area = |r: &Rect| u64::from(r.right - r.left) * u64::from(r.bottom - r.top);
    let total = u64::from(width) * u64::from(height);
    let covered = boxes.iter().map(area).sum::<u64>();
    Ok(if covered == 0 {
        Plan::Unchanged
    } else if covered * 4 >= total * 3 {
        Plan::Full
    } else {
        Plan::Regions(boxes)
    })
}
