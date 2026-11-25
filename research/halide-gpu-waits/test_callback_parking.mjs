import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createCallbackParking } from './callback_parking.mjs';

test('waits for all callbacks and preserves rejection completion', async () => {
    const woke = [];
    const noTimer = () => assert.fail('created a timer while callbacks were pending');
    const park = createCallbackParking(() => true, noTimer, wake => wake());
    let completeValidation;
    let rejectMemory;
    const validation = new Promise(resolve => { completeValidation = resolve; });
    const memory = new Promise((resolve, reject) => { rejectMemory = reject; });
    park.watch(validation.then(() => { woke.push('validation'); }));
    park.watch(memory.then(undefined, () => {
        woke.push('memory');
        throw Error('callback rejected');
    }));
    park.sleep(() => woke.push('wake'), 1);
    rejectMemory();
    await Promise.resolve();
    await Promise.resolve();
    assert.deepEqual(woke, ['memory']);
    completeValidation();
    await Promise.resolve();
    await Promise.resolve();
    assert.deepEqual(woke, ['memory', 'validation', 'wake']);
});

test('keeps stock timers when disabled, idle or waiting on another delay', async () => {
    const timers = [];
    const callback = () => {};
    let enabled = false;
    const park = createCallbackParking(() => enabled,
        (wake, delay) => timers.push([wake, delay]), () => assert.fail('unexpected wake'));
    park.watch(Promise.resolve());
    park.sleep(callback, 1);
    enabled = true;
    park.sleep(callback, 1);
    park.watch(Promise.resolve());
    park.sleep(callback, 10);
    assert.deepEqual(timers, [[callback, 1], [callback, 1], [callback, 10]]);
});
