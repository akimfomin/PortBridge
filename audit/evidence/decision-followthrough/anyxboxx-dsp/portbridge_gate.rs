use super::*;

#[test]
fn host_convolution_switch_controls_in_place_submit() {
    let expect_wet = std::env::var("PORTBRIDGE_EXPECT_WET").unwrap() == "1";
    let mut base = vec![0u8; 0x1_0000];
    let mut dsp = std::ptr::null_mut();
    assert_eq!(
        XDspConnectWithMaximumStreamLimit(base.as_mut_ptr().cast(), 0x1_0000, 1, 1, 1, &mut dsp),
        S_OK
    );

    // The unit impulse has spectrum 1 + 0i. The stored format omits the Nyquist bin.
    let mut ir = [0f32; 0x400];
    for bin in ir.chunks_exact_mut(2) {
        bin[0] = 1.0;
    }
    let desc = StreamDesc {
        kind: CONVOLUTION,
        options: 0,
        frames: 0x200,
        channels: 1,
        ir_floats: ir.len() as u32,
        ir: ir.as_ptr(),
    };
    let (mut status, mut stream) = (std::ptr::null(), std::ptr::null_mut());
    assert_eq!(XDspActivate(dsp, &desc, &mut status, &mut stream), S_OK);

    let mut samples = [0f32; 0x200];
    samples[0] = 0.25;
    let command = Command {
        gains: [1.0; 2],
        input: samples.as_ptr(),
        output: samples.as_mut_ptr(),
        reserved: 0,
    };
    let mut ticket = 0;
    assert_eq!(XDspSubmitCommand(stream, &command, &mut ticket), S_OK);
    assert_eq!(ticket, 1);
    // SAFETY: status is owned by the live stream and read on this same thread.
    let (submitted, completed, result) = unsafe { ((*status).submitted, (*status).completed, (*status).result) };
    assert_eq!((submitted, completed, result), (1, 1, S_OK));
    assert_eq!(XDspDeactivate(stream), S_OK);
    assert_eq!(XDspDisconnect(dsp), S_OK);

    println!("first sample = {:.8}, peak remainder = {:.8}", samples[0],
             samples[1..].iter().map(|value| value.abs()).fold(0.0f32, f32::max));
    if expect_wet {
        // The omitted Nyquist bin contributes (-1)^n / FFT length to a unit impulse.
        let nyquist = 0.25 / (2 * samples.len()) as f32;
        for (index, sample) in samples.iter().enumerate() {
            let impulse = if index == 0 { 0.25 } else { 0.0 };
            let signed_bin = if index % 2 == 0 { nyquist } else { -nyquist };
            let expected = impulse - signed_bin;
            assert!((sample - expected).abs() < 1.0e-6, "sample {index}: {sample} vs {expected}");
        }
    } else {
        assert_eq!(samples, [0f32; 0x200]);
    }
}
