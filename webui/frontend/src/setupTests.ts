import '@testing-library/jest-dom';
import { resetChatConnection } from './lib/chatConnection';
import { resetExpectedSpaVersion } from './lib/spaHello';
import { resetGithubReleaseCache } from './lib/githubRelease';
import { setBakedSpaVersionForTests } from './lib/spaVersion';

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
if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function () {
        this.open = false;
        const event = new Event('close');
        this.dispatchEvent(event);
    };
}
