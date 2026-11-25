// SPDX-License-Identifier: GPL-2.0-only
// A public synthetic four-piece fixture for 1/2-DWORD fragmentation.
fn fragmentation(out: &Path) {
    let mut lw = Lw::new();
    let tid = lw.s.flattened_thread_id_in_group();
    let offset = lw.shlc(tid, 3);
    let mem = lw.mems[0];

    let input = lw.s.raw_load(mem, offset, 1)[0];
    let early = mix(&mut lw, input, 10);
    let survivor = mix(&mut lw, input, 30);
    let second = lw.s.m.new_block();
    let third = lw.s.m.new_block();
    let fourth = lw.s.m.new_block();
    lw.s.m.br(second);

    lw.s.m.set_block(second);
    let consumed = mix(&mut lw, early, 50);
    lw.s.raw_store(mem, offset, &[consumed]);
    lw.s.m.br(third);

    lw.s.m.set_block(third);
    let inputs = lw.s.raw_load(mem, offset, 3);
    let low = mix(&mut lw, inputs[0], 70);
    let high = mix(&mut lw, inputs[1], 90);
    let i64_ty = lw.s.m.i64();
    let low = lw.s.m.cast(CastOp::ZExt, low, i64_ty);
    let high = lw.s.m.cast(CastOp::ZExt, high, i64_ty);
    let shift = lw.s.m.const_int(i64_ty, 32);
    let high = lw.s.m.bin(BinOp::Shl, high, shift);
    let pair = lw.s.m.bin(BinOp::Or, low, high);
    lw.s.m.br(fourth);

    lw.s.m.set_block(fourth);
    let i32_ty = lw.s.m.i32();
    let low = lw.s.m.cast(CastOp::Trunc, pair, i32_ty);
    let high = lw.s.m.bin(BinOp::LShr, pair, shift);
    let high = lw.s.m.cast(CastOp::Trunc, high, i32_ty);
    let together = lw.xor(low, high);
    let together = lw.add(together, survivor);
    let result = mix(&mut lw, together, 110);
    lw.s.raw_store(mem, offset, &[result]);
    lw.s.m.ret();
    lw.s.m.optimize();

    let limit = lw.s.m.blocks.iter().map(Vec::len).max().unwrap();
    let plan = lw.s.m.dispatch_plan(limit).unwrap();
    assert_eq!(plan.blocks.len(), 4);
    let lives = ranges(&lw.s.m, &plan);
    assert!(lives.iter().any(|l| l.value == early && (l.first, l.last, l.words) == (0, 1, 1)));
    assert!(lives.iter().any(|l| l.value == survivor && (l.first, l.last, l.words) == (0, 3, 1)));
    assert!(lives.iter().any(|l| l.value == pair && (l.first, l.last, l.words) == (2, 3, 2)));

    let name = "four-piece-fragmentation";
    compare(name, &lw.s, &plan, limit, None, out);
    let first_fit = strict(&lives);
    let longer_first = ordered_strict(&lives, true);
    let bound = peak(&lives, plan.blocks.len());
    assert_eq!(first_fit.0, bound + 1);
    assert_eq!(longer_first.0, bound);
    check_layout(&lives, &longer_first);
    let events = emitted(name, "longer-first", &lw.s, &plan, &longer_first, out);
    assert_eq!(events, emitted(name, "strict", &lw.s, &plan, &first_fit, out));
    let baseline = replay(&events, plan.blocks.len(), &first_fit, false);
    assert_eq!(baseline.1, 0);
    assert_eq!(baseline, replay(&events, plan.blocks.len(), &longer_first, false));
    assert_eq!(baseline, replay(&events, plan.blocks.len(), &longer_first, true));
    println!("variant,{name},{},{}", longer_first.0, baseline.0);
    for life in lives {
        println!("slot,{name},{},{}", inst(life.value).unwrap(), longer_first.1[&life.value]);
    }
}
