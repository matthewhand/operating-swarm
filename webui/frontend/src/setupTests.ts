import { afterEach, beforeEach } from 'vitest'
import { configure } from '@testing-library/dom'
import { resetRemotesFetchCacheForTests } from './lib/api'
import { resetChatConnection } from './lib/chatConnection';
import { resetExpectedSpaVersion } from './lib/spaHello';
import { __resetUserPrefsCacheForTests } from './lib/userPrefs';
import { resetGithubReleaseCache } from './lib/githubRelease';
import { setBakedSpaVersionForTests } from './lib/spaVersion';

import '@testing-library/jest-dom';

// #592: default 1000ms findBy*/waitFor window is too tight for heavy mounts
// in a full parallel run (machine-speed flaky, membership moved between runs).
// See TESTING.md.
configure({ asyncUtilTimeout: 4000 })

// #581: drop the coalesced /v1/remotes/ cache after every test — the
// module-level TTL cache must never leak a previous test's remotes payload
// into the next mount (that made the remote-backed-teams test order-dependent).
afterEach(() => {
    resetRemotesFetchCacheForTests()
})

// #1098: some Node + jsdom combinations ship `window.innerWidth` (and its
// innerHeight/outerWidth/outerHeight siblings) as getter-only accessors, so
// the widespread test idiom `window.innerWidth = N` throws
// "Cannot assign to read only property" and dozens of suites fail for
// environment reasons, not code reasons. Normalizing via defineProperty here
// makes every viewport assignment in the suite legal again; a test that
// defineProperty'd a custom value still wins (configurable: true).
if (typeof window !== 'undefined') {
    for (const prop of ['innerWidth', 'innerHeight', 'outerWidth', 'outerHeight'] as const) {
        // The getter-only accessor may be an own property of `window` or live on
        // its prototype chain — find it wherever it is, then shadow it with an
        // own, writable, configurable data property on `window` itself.
        let holder: object | null = window
        while (holder && !Object.getOwnPropertyDescriptor(holder, prop)) {
            holder = Object.getPrototypeOf(holder)
        }
        if (!holder) continue
        const desc = Object.getOwnPropertyDescriptor(holder, prop)
        const current = (window as unknown as Record<typeof prop, number>)[prop]
        if (!desc || (desc.configurable === false && !('value' in desc))) continue
        Object.defineProperty(window, prop, {
            configurable: true,
            writable: true,
            value: current,
        })
    }
}

afterEach(() => {
    resetChatConnection();
    resetExpectedSpaVersion();
    resetGithubReleaseCache();
    setBakedSpaVersionForTests(null);
    if (typeof window !== 'undefined') {
        // #1098: a bare assignment throws on getter-only innerWidth accessors
        // (jsdom/Node combos + tests that defineProperty'd it). defineProperty
        // works in both cases.
        Object.defineProperty(window, 'innerWidth', {
            configurable: true,
            value: 1024,
        });
    }
});

// Some Node + jsdom combinations (e.g. Node 26 with jsdom 29) do not expose
// window.localStorage as a bare global. Provide a tiny in-memory store so
// storage-backed tests (avatar theme, combo, sections, …) run anywhere. CI
// environments that already expose localStorage skip this branch entirely.
if (typeof globalThis.localStorage === 'undefined') {
    const store = new Map<string, string>()
    const shim = {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => { store.set(key, String(value)) },
        removeItem: (key: string) => { store.delete(key) },
        clear: () => { store.clear() },
        key: (index: number) => [...store.keys()][index] ?? null,
        get length() { return store.size },
    }
    globalThis.localStorage = shim
    if (typeof window !== 'undefined') {
        Object.defineProperty(window, 'localStorage', { value: shim, configurable: true })
    }
}

if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () {
        this.open = true;
    };
}

// #726: fetchUserPrefs dedupes via module-level cache/promise. Reset it before
// every test so re-stubbed fetch payloads are always observed.
beforeEach(() => {
    __resetUserPrefsCacheForTests();
});
if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function () {
        this.open = false;
        const event = new Event('close');
        this.dispatchEvent(event);
    };
}
