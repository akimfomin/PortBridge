// SPDX-License-Identifier: GPL-2.0-only
//! Model of a shared Windows commit budget for XCL's background driver lanes.

use std::sync::{Condvar, Mutex};
use std::time::Duration;

const CHECK_INTERVAL: Duration = Duration::from_millis(50);
pub const MIB: u64 = 1 << 20;
const PRODUCTION_FLOOR: u64 = 3 * 1024 * MIB;
const ESTIMATED_DRIVER_MINIMUM: u64 = 1536 * MIB;

#[derive(Clone, Copy)]
pub enum Lane {
    Huge = 0,
    Giant = 1,
}

#[derive(Clone, Copy)]
pub struct Request {
    lane: Lane,
    lane_limit: usize,
    wanted_limit: Option<usize>,
    minimum_headroom: u64,
    estimated_cost: u64,
}

impl Request {
    pub fn cold_background(lane: Lane, lane_limit: usize, dxil_bytes: usize) -> Self {
        assert!(lane_limit != 0);
        let scaled = (dxil_bytes as u64).saturating_mul(512);
        Self {
            lane,
            lane_limit,
            wanted_limit: None,
            minimum_headroom: PRODUCTION_FLOOR.max(scaled),
            estimated_cost: ESTIMATED_DRIVER_MINIMUM.max(scaled),
        }
    }

    pub fn with_wanted_limit(mut self, wanted_limit: usize) -> Self {
        assert!(wanted_limit >= self.lane_limit);
        self.wanted_limit = Some(wanted_limit);
        self
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct Running {
    pub any_lane_bytes: u64,
    pub slots: [usize; 2],
}

pub struct Gate {
    running: Mutex<Running>,
    changed: Condvar,
}

impl Gate {
    pub const fn new() -> Self {
        Self {
            running: Mutex::new(Running { any_lane_bytes: 0, slots: [0; 2] }),
            changed: Condvar::new(),
        }
    }

    pub fn enter(
        &self,
        request: Request,
        free_commit: impl Fn() -> Option<u64>,
        wanted: impl Fn() -> bool,
    ) -> Option<Reservation<'_>> {
        let lane = request.lane as usize;
        let mut active = self.running.lock().unwrap();
        loop {
            let is_wanted = wanted();
            let limit = if is_wanted { request.wanted_limit? } else { request.lane_limit };
            let projected = active.any_lane_bytes.checked_add(request.estimated_cost);
            if active.slots[lane] < limit
                && let Some(projected) = projected
                && (is_wanted || free_commit().is_none_or(|free| free >= request.minimum_headroom.max(projected)))
            {
                active.slots[lane] += 1;
                active.any_lane_bytes = projected;
                return Some(Reservation { gate: self, lane, cost: request.estimated_cost });
            }
            active = self.changed.wait_timeout(active, CHECK_INTERVAL).unwrap().0;
        }
    }

    pub fn snapshot(&self) -> Running {
        *self.running.lock().unwrap()
    }
}

pub struct Reservation<'a> {
    gate: &'a Gate,
    lane: usize,
    cost: u64,
}

impl Drop for Reservation<'_> {
    fn drop(&mut self) {
        let mut state = self.gate.running.lock().unwrap();
        state.slots[self.lane] -= 1;
        state.any_lane_bytes -= self.cost;
        drop(state);
        self.gate.changed.notify_all();
    }
}
