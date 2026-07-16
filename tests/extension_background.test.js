const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

function event() {
  const listeners = [];
  return {
    addListener(listener) { listeners.push(listener); },
    emit(...args) { return listeners.map((listener) => listener(...args)); },
  };
}

function loadBackground({ nativeResult = { status: "ok" }, settings } = {}) {
  const calls = { native: [], cancel: [], erase: [] };
  const events = {
    downloadCreated: event(),
    downloadChanged: event(),
    message: event(),
  };
  const quietEvent = () => event();
  const store = {
    async get(key) {
      if (key === "settings") return settings ? { settings } : {};
      return {};
    },
    async set() {},
  };
  const browser = {
    action: {
      async setBadgeText() {},
      async setBadgeBackgroundColor() {},
    },
    commands: { onCommand: quietEvent() },
    contextMenus: { create() {}, onClicked: quietEvent() },
    cookies: { async getAll() { return []; } },
    downloads: {
      onCreated: events.downloadCreated,
      onChanged: events.downloadChanged,
      async cancel(id) { calls.cancel.push(id); },
      async erase(query) { calls.erase.push(query); },
      async download() {},
    },
    notifications: { async create() {} },
    runtime: {
      lastError: null,
      onInstalled: quietEvent(),
      onMessage: events.message,
      async sendNativeMessage(_host, message) {
        calls.native.push(message);
        return typeof nativeResult === "function" ? nativeResult(message) : nativeResult;
      },
    },
    storage: {
      local: store,
      session: store,
      onChanged: quietEvent(),
    },
    tabs: {
      async query() { return []; },
      async sendMessage() {},
      onRemoved: quietEvent(),
      onUpdated: quietEvent(),
      onActivated: quietEvent(),
    },
    webRequest: { onHeadersReceived: quietEvent() },
  };
  const context = vm.createContext({
    browser,
    console: { log() {}, error() {} },
    navigator: { userAgent: "test" },
    URL,
    setTimeout,
    clearTimeout,
  });
  const source = fs.readFileSync("extension/background.js", "utf8");
  vm.runInContext(source, context, { filename: "extension/background.js" });
  return { calls, events };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

test("restored Chrome download history is never sent to Cove", async () => {
  const { calls, events } = loadBackground();
  await settle();
  calls.native.length = 0; // Ignore the startup ping.

  events.downloadCreated.emit({
    id: 1,
    url: "https://example.test/archive.zip",
    filename: "archive.zip",
    state: "complete",
    startTime: new Date().toISOString(),
    totalBytes: 2_000_000,
  });
  events.downloadCreated.emit({
    id: 2,
    url: "https://example.test/old.zip",
    filename: "old.zip",
    state: "in_progress",
    startTime: new Date(Date.now() - 60_000).toISOString(),
    totalBytes: 2_000_000,
  });
  await settle();

  assert.equal(calls.native.length, 0);
  assert.deepEqual(calls.cancel, []);
});

test("a fresh eligible download is sent once and then cancelled", async () => {
  const { calls, events } = loadBackground();
  await settle();
  calls.native.length = 0;
  const item = {
    id: 3,
    url: "https://example.test/fresh.zip",
    filename: "fresh.zip",
    state: "in_progress",
    startTime: new Date().toISOString(),
    totalBytes: 2_000_000,
  };

  events.downloadCreated.emit(item);
  events.downloadCreated.emit({ ...item, id: 4 });
  await settle();

  assert.equal(calls.native.filter((message) => message.action === "download").length, 1);
  assert.deepEqual(calls.cancel, [3]);
});

test("native rejection leaves the browser download running", async () => {
  const { calls, events } = loadBackground({ nativeResult: { status: "error", message: "offline" } });
  await settle();
  calls.native.length = 0;

  events.downloadCreated.emit({
    id: 5,
    url: "https://example.test/fallback.zip",
    filename: "fallback.zip",
    state: "in_progress",
    startTime: new Date().toISOString(),
    totalBytes: 2_000_000,
  });
  await settle();

  assert.equal(calls.native.filter((message) => message.action === "download").length, 1);
  assert.deepEqual(calls.cancel, []);
});

test("detected stream reports native-host failure instead of false success", async () => {
  const { events } = loadBackground({ nativeResult: { status: "error", message: "offline" } });
  await settle();
  let response;

  events.message.emit(
    { type: "downloadStream", url: "https://example.test/live.m3u8", filename: "live.mp4" },
    {},
    (value) => { response = value; },
  );
  await settle();

  assert.equal(response.ok, false);
  assert.equal(response.error, "offline");
});
