// extension/content/media-tab.js
//
// IDM-style floating "Download with Cove" pill shown near a hovered <video>.
// Inert on pages without qualifying video: no DOM is created until a video
// with a usable URL is hovered. Uses Shadow DOM for isolation; never injects
// page-context scripts and never auto-downloads.

(() => {
  "use strict";

  const browser = globalThis.browser || globalThis.chrome;
  if (!browser || !browser.runtime || !browser.runtime.id) return;

  // Detected HLS streams are tracked per tab, not per frame. Only the top
  // frame may use them as a fallback, so an unrelated iframe's blob video
  // can never offer another frame's stream URL. Direct-src videos still get
  // the pill in any frame.
  const IS_TOP_FRAME = window === window.top;

  const HIDE_DELAY_MS = 500;
  // Must outlast the background's 5s dedup window so a manual retry after
  // the window still produces a fresh native request.
  const SENT_RESET_MS = 6000;

  // HLS/M3U8 streams the background detected for this tab (Firefox only;
  // Chrome has no webRequest detection and this stays empty).
  let detectedStreams = [];

  let host = null;
  let pill = null;
  let label = null;
  let hideTimer = null;
  let resetTimer = null;
  let currentUrl = "";
  const sentUrls = new Map(); // url -> timestamp of last send

  // ---- URL selection ----

  function isHttpUrl(u) {
    return typeof u === "string" && /^https?:\/\//i.test(u);
  }

  function isDrmProtected(video) {
    // EME-protected media fails closed: no pill.
    return !!video.mediaKeys;
  }

  function candidateUrl(video) {
    if (isDrmProtected(video)) return "";
    const src = video.currentSrc || video.getAttribute("src") || "";
    if (isHttpUrl(src)) return src;
    const source = video.querySelector("source[src]");
    if (source && isHttpUrl(source.src)) return source.src;
    // blob:/data:/MSE video: only usable when the background detected an
    // HLS stream for this tab, and only from the top frame (streams are
    // tab-scoped, so subframes must not claim them).
    if (IS_TOP_FRAME && detectedStreams.length > 0 && isHttpUrl(detectedStreams[0].url)) {
      return detectedStreams[0].url;
    }
    return "";
  }

  // ---- Pill UI (created lazily, Shadow DOM) ----

  function ensurePill() {
    if (host) return;
    host = document.createElement("div");
    host.className = "cove-media-tab-host";
    const shadow = host.attachShadow({ mode: "open" });

    const style = document.createElement("style");
    style.textContent = [
      ":host { all: initial; }",
      ".cove-pill {",
      "  display: flex; align-items: center; gap: 6px;",
      "  padding: 5px 12px; border-radius: 999px;",
      "  background: #1b1b26; color: #50e6cf;",
      "  border: 1px solid #50e6cf;",
      "  font: 600 12px/1.2 system-ui, sans-serif;",
      "  cursor: pointer; user-select: none;",
      "  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);",
      "}",
      ".cove-pill:hover { background: #24243a; }",
      ".cove-pill.cove-sent {",
      "  color: #9a9ab0; border-color: #9a9ab0; cursor: default;",
      "}",
      ".cove-pill.cove-error {",
      "  color: #e66a6a; border-color: #e66a6a;",
      "}",
    ].join("\n");
    shadow.appendChild(style);

    pill = document.createElement("div");
    pill.className = "cove-pill";
    pill.setAttribute("role", "button");
    pill.title = "Download with Cove";

    label = document.createElement("span");
    label.textContent = "Download with Cove";
    pill.appendChild(label);
    shadow.appendChild(pill);

    pill.addEventListener("click", onPillClick);
    host.addEventListener("mouseenter", cancelHide);
    host.addEventListener("mouseleave", scheduleHide);

    (document.body || document.documentElement).appendChild(host);
  }

  function setPillState(state) {
    if (!pill) return;
    pill.classList.remove("cove-sent", "cove-error");
    if (state === "sent") {
      pill.classList.add("cove-sent");
      label.textContent = "Sent to Cove";
    } else if (state === "error") {
      pill.classList.add("cove-error");
      label.textContent = "Cove unavailable";
    } else {
      label.textContent = "Download with Cove";
    }
  }

  function showPill(video, url) {
    ensurePill();
    currentUrl = url;
    const last = sentUrls.get(url);
    if (last && Date.now() - last < SENT_RESET_MS) {
      setPillState("sent");
    } else {
      setPillState("ready");
    }
    const rect = video.getBoundingClientRect();
    if (rect.width < 80 || rect.height < 60) {
      hidePill();
      return;
    }
    // Top-right corner of the video, kept inside the viewport.
    const top = Math.max(4, rect.top + 8);
    const right = Math.max(4, window.innerWidth - rect.right + 8);
    host.style.top = top + "px";
    host.style.right = right + "px";
    host.style.display = "block";
    cancelHide();
  }

  function hidePill() {
    if (host) host.style.display = "none";
    currentUrl = "";
  }

  function scheduleHide() {
    cancelHide();
    hideTimer = setTimeout(hidePill, HIDE_DELAY_MS);
  }

  function cancelHide() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  // ---- Click -> one explicit download request ----

  function onPillClick() {
    const url = currentUrl;
    if (!url) return;
    const last = sentUrls.get(url);
    if (last && Date.now() - last < SENT_RESET_MS) return; // already sent
    sentUrls.set(url, Date.now());
    setPillState("sent");
    if (resetTimer) clearTimeout(resetTimer);
    resetTimer = setTimeout(() => {
      if (currentUrl === url) setPillState("ready");
    }, SENT_RESET_MS);

    Promise.resolve(
      browser.runtime.sendMessage({
        type: "downloadMedia",
        url: url,
        pageUrl: location.href,
      })
    )
      .then((resp) => {
        if (!resp || resp.ok !== true) {
          sentUrls.delete(url);
          if (currentUrl === url) setPillState("error");
        }
      })
      .catch(() => {
        sentUrls.delete(url);
        if (currentUrl === url) setPillState("error");
      });
  }

  // ---- Hover wiring (event delegation, no MutationObserver) ----

  document.addEventListener(
    "mouseover",
    (e) => {
      const t = e.target;
      if (!t || typeof t.closest !== "function") return;
      if (host && (t === host || host.contains(t))) {
        cancelHide();
        return;
      }
      const video = t.closest("video");
      if (video) {
        const url = candidateUrl(video);
        if (url) {
          showPill(video, url);
        } else {
          // Unsupported media fails closed: no pill.
          if (host && host.style.display !== "none") scheduleHide();
        }
        return;
      }
      if (host && host.style.display !== "none") scheduleHide();
    },
    true
  );

  // ---- Detected-stream sync with background (top frame only) ----

  if (IS_TOP_FRAME) {
    browser.runtime.onMessage.addListener((msg) => {
      if (msg && msg.type === "coveStreamsUpdated" && Array.isArray(msg.streams)) {
        detectedStreams = msg.streams;
      }
    });

    try {
      Promise.resolve(browser.runtime.sendMessage({ type: "getDetectedStreams" }))
        .then((streams) => {
          if (Array.isArray(streams)) detectedStreams = streams;
        })
        .catch(() => {});
    } catch {
      // Background unavailable; direct-src videos still work.
    }
  }
})();
