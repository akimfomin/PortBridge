#![allow(dead_code, non_snake_case, clippy::upper_case_acronyms)]

extern crate self as tracing;
extern crate self as windows_sys;

#[macro_export]
macro_rules! debug { ($($tokens:tt)*) => {}; }
#[macro_export]
macro_rules! info { ($($tokens:tt)*) => {}; }
#[macro_export]
macro_rules! hle_export { ($symbol:ident) => { stringify!($symbol) }; }

pub struct HleModule {
    pub name: &'static str,
    pub dlls: &'static [&'static str],
    pub exports: Vec<&'static str>,
}

pub mod Win32 {
    pub mod System {
        pub mod Diagnostics {
            pub mod Debug {
                #[link(name = "kernel32")]
                unsafe extern "system" {
                    pub fn ReadProcessMemory(
                        process: *mut std::ffi::c_void,
                        address: *const std::ffi::c_void,
                        buffer: *mut std::ffi::c_void,
                        size: usize,
                        read: *mut usize,
                    ) -> i32;
                }
            }
        }
        pub mod Threading {
            #[link(name = "kernel32")]
            unsafe extern "system" {
                pub fn GetCurrentProcess() -> *mut std::ffi::c_void;
            }
        }
    }
}

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
}
