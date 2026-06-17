// extension/background.js

// Cross-browser shim: Firefox exposes `browser` (promise-based); Chromium
// exposes `chrome`. Chrome MV3 APIs used here are all promise-based, so the
// same code runs on both.
const browser = globalThis.browser || globalThis.chrome;

const HOST_NAME = "cove_download_manager";

function sendNativeMessage(msg) {
  return browser.runtime.sendNativeMessage(HOST_NAME, msg).catch((err) => {
    console.error("Cove native messaging error:", err);
    return { status: "error", message: err.message || String(err) };
  });
}

// ---- Default settings ----

const DEFAULT_SETTINGS = {
  enabled: true,
  minSizeBytes: 1024 * 1024, // 1 MB
  interceptExtensions: [
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".msi", ".dmg", ".iso", ".img",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".mp3", ".flac", ".aac", ".ogg", ".wav",
    ".pdf", ".torrent",
    ".deb", ".rpm", ".appimage",
  ],
  excludedDomains: [],
};

let settings = { ...DEFAULT_SETTINGS };

async function loadSettings() {
  const stored = await browser.storage.local.get("settings");
  if (stored.settings) {
    settings = { ...DEFAULT_SETTINGS, ...stored.settings };
  }
  return settings;
}

// On MV3 the service worker is torn down and this script re-runs on wake,
// resetting `settings` to defaults. Event handlers must await this before
// reading `settings`, or they'd act on defaults (ignoring excluded domains,
// re-enabling a disabled extension, etc.).
let settingsReady = loadSettings();

function ensureSettings() {
  return settingsReady;
}

// Keep the in-memory copy fresh if another context (the options page) writes.
browser.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.settings) {
    settings = { ...DEFAULT_SETTINGS, ...(changes.settings.newValue || {}) };
    updateBadge();
  }
});

async function saveSettings(newSettings) {
  settings = { ...DEFAULT_SETTINGS, ...newSettings };
  await browser.storage.local.set({ settings });
}

// ---- Download interception ----

function getExtension(url) {
  try {
    const pathname = new URL(url).pathname;
    const dot = pathname.lastIndexOf(".");
    if (dot === -1) return "";
    return pathname.substring(dot).toLowerCase().split(/[?#]/)[0];
  } catch {
    return "";
  }
}

function isDomainExcluded(url) {
  try {
    const hostname = new URL(url).hostname;
    return settings.excludedDomains.some(
      (d) => hostname === d || hostname.endsWith("." + d)
    );
  } catch {
    return false;
  }
}

// Dedup guard: URLs intercepted recently (prevents re-intercept after
// cancel). Timestamp-based + pruned on read, so it survives without a
// setTimeout (unreliable in an MV3 service worker that may sleep).
const DEDUP_WINDOW_MS = 5000;
const recentIntercepted = new Map(); // url -> timestamp
function markIntercepted(url) {
  recentIntercepted.set(url, Date.now());
}
function wasRecentlyIntercepted(url) {
  const ts = recentIntercepted.get(url);
  if (ts === undefined) return false;
  if (Date.now() - ts > DEDUP_WINDOW_MS) {
    recentIntercepted.delete(url);
    return false;
  }
  return true;
}

// Extension of the file being downloaded, preferring the suggested filename
// and falling back to the URL path. Returns "" when none can be determined.
function downloadExtension(item) {
  const name = (item.filename || item.url || "").split(/[?#]/)[0];
  const slash = Math.max(name.lastIndexOf("/"), name.lastIndexOf("\\"));
  const dot = name.lastIndexOf(".");
  if (dot === -1 || dot < slash) return "";
  return name.substring(dot).toLowerCase();
}

browser.downloads.onCreated.addListener((downloadItem) => {
  // Don't await here; the handler kicks off async work itself.
  handleCreated(downloadItem);
});

async function handleCreated(downloadItem) {
  await ensureSettings();
  const url = downloadItem.url || "";
  if (!settings.enabled) return;
  if (url.startsWith("blob:") || url.startsWith("data:")) return;
  if (isDomainExcluded(url)) return;
  if (wasRecentlyIntercepted(url)) return;

  // Size filter: only when the size is known. Small files are left to the
  // browser per the user's minimum-size setting.
  const size = downloadItem.totalBytes;
  if (typeof size === "number" && size > 0 && size < settings.minSizeBytes) return;

  // Extension allowlist: only grab configured file types. An empty list
  // means "intercept everything".
  const exts = settings.interceptExtensions || [];
  if (exts.length && !exts.includes(downloadExtension(downloadItem))) return;

  interceptDownload(downloadItem);
}

// Download ids we cancelled and still want erased from the browser's list.
// The erase is driven by downloads.onChanged (below) so it doesn't depend on
// setTimeout, which an MV3 service worker may never run if it sleeps.
const interceptedIds = new Set();

browser.downloads.onChanged.addListener((delta) => {
  if (!interceptedIds.has(delta.id)) return;
  const state = delta.state && delta.state.current;
  if (state === "interrupted" || state === "complete") {
    browser.downloads.erase({ id: delta.id }).catch(() => {});
    interceptedIds.delete(delta.id);
  }
});

async function interceptDownload(downloadItem) {
  markIntercepted(downloadItem.url);

  // Cancel the browser download and scrub it from the browser's list. The
  // cancel flips it to "interrupted", which the onChanged listener erases.
  const dlId = downloadItem.id;
  interceptedIds.add(dlId);
  try {
    await browser.downloads.cancel(dlId);
  } catch {}
  browser.downloads.erase({ id: dlId }).catch(() => {});

  // Gather cookies for the download URL.
  let cookieStr = "";
  try {
    const cookies = await browser.cookies.getAll({ url: downloadItem.url });
    cookieStr = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    // No cookies available.
  }

  // Extract filename from the download item.
  let filename = null;
  if (downloadItem.filename) {
    const parts = downloadItem.filename.replace(/\\/g, "/").split("/");
    filename = parts[parts.length - 1] || null;
  }

  console.log("Cove: intercepting download", downloadItem.url);

  const result = await sendNativeMessage({
    action: "download",
    url: downloadItem.url,
    filename: filename,
    referrer: downloadItem.referrer || "",
    cookies: cookieStr,
    fileSize: downloadItem.totalBytes || 0,
    userAgent: navigator.userAgent,
  });

  console.log("Cove: native host response", JSON.stringify(result));

  if (result.status === "ok") {
    showNotification("Download sent to Cove", filename || downloadItem.url);
  } else {
    showNotification("Cove error", result.message || "Failed to send download");
  }
}

// ---- Context menu ----

// Register the context menu on install/update. Doing this at top level
// would throw "duplicate id" every time an MV3 service worker wakes, since
// the script re-runs on each wake.
browser.runtime.onInstalled.addListener(() => {
  browser.contextMenus.create(
    {
      id: "download-with-cove",
      title: "Download with Cove",
      contexts: ["link", "image", "video", "audio"],
    },
    () => {
      if (browser.runtime.lastError) {
        console.error("Cove: context menu create error:", browser.runtime.lastError);
      } else {
        console.log("Cove: context menu registered");
      }
    }
  );
});

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  console.log("Cove: context menu clicked", info.menuItemId, info.linkUrl || info.srcUrl);
  if (info.menuItemId !== "download-with-cove") return;

  const url = info.linkUrl || info.srcUrl;
  if (!url) return;

  let cookieStr = "";
  try {
    const cookies = await browser.cookies.getAll({ url });
    cookieStr = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {}

  let filename = null;
  try {
    const pathname = new URL(url).pathname;
    const parts = pathname.split("/");
    const last = parts[parts.length - 1];
    if (last && last.includes(".")) filename = decodeURIComponent(last);
  } catch {}

  const result = await sendNativeMessage({
    action: "download",
    url: url,
    filename: filename,
    referrer: info.pageUrl || "",
    cookies: cookieStr,
    userAgent: navigator.userAgent,
  });

  if (result.status === "ok") {
    showNotification("Download sent to Cove", filename || url);
  } else {
    showNotification("Cove error", result.message || "Failed to send download");
  }
});

// ---- Keyboard shortcut ----

browser.commands.onCommand.addListener(async (command) => {
  if (command === "toggle-intercept") {
    await ensureSettings();  // toggle from the real value, not defaults
    await saveSettings({ ...settings, enabled: !settings.enabled });
    updateBadge();
    showNotification(
      "Cove Interception",
      settings.enabled ? "Download interception enabled" : "Download interception disabled"
    );
  }
});

// ---- Badge ----

// MV3 renamed browserAction -> action; fall back for MV2 Firefox.
const browserAction = browser.action || browser.browserAction;

function updateBadge() {
  if (!settings.enabled) {
    browserAction.setBadgeText({ text: "OFF" });
    browserAction.setBadgeBackgroundColor({ color: "#6b6b80" });
  } else {
    browserAction.setBadgeText({ text: "" });
  }
}

// ---- Notifications ----

function showNotification(title, message) {
  browser.notifications.create({
    type: "basic",
    iconUrl: "icons/icon-96.png",
    title: title,
    message: message,
  });
}

// ---- Message handler for popup/options ----

browser.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "getSettings") {
    ensureSettings().then(() => sendResponse(settings));
    return true; // async: wait for settings to load before responding
  }
  if (msg.type === "saveSettings") {
    saveSettings(msg.settings).then(() => {
      updateBadge();
      sendResponse({ ok: true });
    });
    return true; // async
  }
  if (msg.type === "getStatus") {
    sendNativeMessage({ action: "status" }).then(sendResponse);
    return true; // async
  }
  if (msg.type === "ping") {
    sendNativeMessage({ action: "ping" }).then(sendResponse);
    return true;
  }
});

// ---- Init ----

settingsReady.then(updateBadge);

// Startup connectivity test
sendNativeMessage({ action: "ping" }).then((r) => {
  console.log("Cove startup ping:", JSON.stringify(r));
}).catch((e) => {
  console.error("Cove startup ping FAILED:", e);
});
