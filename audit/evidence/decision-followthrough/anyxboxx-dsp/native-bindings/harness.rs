#![allow(non_snake_case)]

mod registry;
pub use registry::{HleExport, HleModule, registry};

mod modules {
    mod dsp;
    mod dsp_convolve;

    mod xasync {
        pub const E_INVALIDARG: i32 = 0x8007_0057u32 as i32;
    }
    mod xgameruntime {
        pub type HRESULT = i32;
        pub const S_OK: i32 = 0;
    }

    pub(crate) fn all() -> Vec<crate::HleModule> {
        vec![dsp::module()]
    }

    #[test]
    fn chad_dll_resolves_all_five_dsp_exports() {
        use self::dsp::*;
        use crate::registry::lookup;

        for (name, address) in [
            ("XDspConnectWithMaximumStreamLimit", XDspConnectWithMaximumStreamLimit as *const () as usize),
            ("XDspDisconnect", XDspDisconnect as *const () as usize),
            ("XDspActivate", XDspActivate as *const () as usize),
            ("XDspDeactivate", XDspDeactivate as *const () as usize),
            ("XDspSubmitCommand", XDspSubmitCommand as *const () as usize),
        ] {
            assert_eq!(lookup("CHAD.DLL", name), Some(address));
        }
        assert_eq!(lookup("chad.dll", "XDspUnknown"), None);
    }
}
