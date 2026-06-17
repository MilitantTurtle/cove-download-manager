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
}

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

// Track downloads we've seen but are waiting for metadata on.
const pendingDownloads = new Map();

// Dedup guard: URLs intercepted recently (prevents re-intercept after cancel).
const recentIntercepted = new Set();
function markIntercepted(url) {
  recentIntercepted.add(url);
  setTimeout(() => recentIntercepted.delete(url), 5000);
}

browser.downloads.onCreated.addListener((downloadItem) => {
  console.log("Cove: onCreated fired", downloadItem.url, "enabled:", settings.enabled);
  if (!settings.enabled) return;
  if (downloadItem.url.startsWith("blob:") || downloadItem.url.startsWith("data:")) return;
  if (isDomainExcluded(downloadItem.url)) return;
  if (recentIntercepted.has(downloadItem.url)) return;

  interceptDownload(downloadItem);
});

async function interceptDownload(downloadItem) {
  markIntercepted(downloadItem.url);

  // Cancel the browser download and scrub it from Firefox's download list.
  const dlId = downloadItem.id;
  try {
    await browser.downloads.cancel(dlId);
  } catch {}
  // Erase once Firefox registers the cancellation, then retry to be sure.
  const eraseIt = () => browser.downloads.erase({ id: dlId }).catch(() => {});
  eraseIt();
  setTimeout(eraseIt, 300);
  setTimeout(eraseIt, 1000);

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

browser.commands.onCommand.addListener((command) => {
  if (command === "toggle-intercept") {
    settings.enabled = !settings.enabled;
    saveSettings(settings);
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
    sendResponse(settings);
    return;
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

loadSettings().then(updateBadge);

// Startup connectivity test
sendNativeMessage({ action: "ping" }).then((r) => {
  console.log("Cove startup ping:", JSON.stringify(r));
}).catch((e) => {
  console.error("Cove startup ping FAILED:", e);
});
