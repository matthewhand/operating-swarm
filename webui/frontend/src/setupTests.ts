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

afterEach(() => {
    resetChatConnection();
    resetExpectedSpaVersion();
    resetGithubReleaseCache();
    setBakedSpaVersionForTests(null);
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
