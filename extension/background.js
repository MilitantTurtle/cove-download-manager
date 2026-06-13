// extension/background.js

const HOST_NAME = "cove_download_manager";

function sendNativeMessage(msg) {
  return browser.runtime.sendNativeMessage(HOST_NAME, msg).catch((err) => {
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

browser.downloads.onCreated.addListener((downloadItem) => {
  if (!settings.enabled) return;
  if (downloadItem.url.startsWith("blob:") || downloadItem.url.startsWith("data:")) return;
  if (isDomainExcluded(downloadItem.url)) return;

  const ext = getExtension(downloadItem.url);
  if (ext && settings.interceptExtensions.includes(ext)) {
    interceptDownload(downloadItem);
    return;
  }

  // Can't decide yet - wait for onChanged to get fileSize/filename.
  pendingDownloads.set(downloadItem.id, downloadItem);
});

browser.downloads.onChanged.addListener((delta) => {
  if (!pendingDownloads.has(delta.id)) return;
  const item = pendingDownloads.get(delta.id);

  if (delta.totalBytes) {
    item.totalBytes = delta.totalBytes.current;
  }
  if (delta.filename) {
    item.filename = delta.filename.current;
  }

  // Check filename extension now that we have it.
  if (delta.filename) {
    const name = delta.filename.current || "";
    const dot = name.lastIndexOf(".");
    if (dot !== -1) {
      const ext = name.substring(dot).toLowerCase();
      if (settings.interceptExtensions.includes(ext)) {
        pendingDownloads.delete(delta.id);
        interceptDownload(item);
        return;
      }
    }
  }

  // Check size threshold.
  if (item.totalBytes && item.totalBytes >= settings.minSizeBytes) {
    pendingDownloads.delete(delta.id);
    interceptDownload(item);
    return;
  }

  // If download completed or errored without matching, stop tracking.
  if (delta.state && (delta.state.current === "complete" || delta.state.current === "interrupted")) {
    pendingDownloads.delete(delta.id);
  }
});

async function interceptDownload(downloadItem) {
  pendingDownloads.delete(downloadItem.id);

  // Cancel the browser download.
  try {
    await browser.downloads.cancel(downloadItem.id);
    await browser.downloads.erase({ id: downloadItem.id });
  } catch {
    // Already completed or cancelled.
  }

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

  const result = await sendNativeMessage({
    action: "download",
    url: downloadItem.url,
    filename: filename,
    referrer: downloadItem.referrer || "",
    cookies: cookieStr,
    fileSize: downloadItem.totalBytes || 0,
  });

  if (result.status === "ok") {
    showNotification("Download sent to Cove", filename || downloadItem.url);
  } else {
    showNotification("Cove error", result.message || "Failed to send download");
  }
}

// ---- Context menu ----

browser.contextMenus.create({
  id: "download-with-cove",
  title: "Download with Cove",
  contexts: ["link", "image", "video", "audio"],
});

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "download-with-cove") return;

  const url = info.linkUrl || info.srcUrl;
  if (!url) return;

  let cookieStr = "";
  try {
    const cookies = await browser.cookies.getAll({ url });
    cookieStr = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    // No cookies.
  }

  let filename = null;
  try {
    const pathname = new URL(url).pathname;
    const parts = pathname.split("/");
    const last = parts[parts.length - 1];
    if (last && last.includes(".")) filename = decodeURIComponent(last);
  } catch {
    // Invalid URL.
  }

  const result = await sendNativeMessage({
    action: "download",
    url: url,
    filename: filename,
    referrer: info.pageUrl || "",
    cookies: cookieStr,
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

function updateBadge() {
  if (!settings.enabled) {
    browser.browserAction.setBadgeText({ text: "OFF" });
    browser.browserAction.setBadgeBackgroundColor({ color: "#6b6b80" });
  } else {
    browser.browserAction.setBadgeText({ text: "" });
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
