#[path = "budget.rs"]
mod budget;

#[test]
fn small_profile_has_an_inclusive_boundary() {
    assert!(budget::small_host(Some(16 * budget::GIB), false));
    assert!(!budget::small_host(Some(16 * budget::GIB + 1), false));
    assert!(budget::small_host(None, true));
}

#[test]
fn crossing_the_spare_threshold_reduces_the_cap() {
    let capacity = 8_000 * budget::MIB;
    let limit = capacity * 85 / 100;
    assert_eq!(budget::texture_spares(Some([capacity, limit - 1, 0, 0]), true, true), 4);
    assert_eq!(budget::texture_spares(Some([capacity, limit, 0, 0]), true, true), 2);
    assert_eq!(budget::texture_spares(Some([capacity, limit + 1, 0, 0]), true, true), 2);
}
