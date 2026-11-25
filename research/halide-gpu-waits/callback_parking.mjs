// A single Asyncify instance parks until the WebGPU callbacks it has issued finish.
export function createCallbackParking(enabled, scheduleTimer, invoke) {
    let pending = 0;
    let resume = null;

    function settled() {
        --pending;
        if (pending === 0 && resume !== null) {
            const wake = resume;
            resume = null;
            invoke(wake);
        }
    }

    return {
        watch(callbackFinished) {
            if (enabled()) {
                ++pending;
                callbackFinished.then(settled, settled);
            }
        },

        sleep(wake, milliseconds) {
            if (milliseconds === 1 && pending !== 0 && resume === null) {
                resume = wake;
            } else {
                scheduleTimer(wake, milliseconds);
            }
        },
    };
}
