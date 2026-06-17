# Privacy Policy — Cove Download Manager (browser extension)

_Last updated: 2026-06-17_

Cove Download Manager is a browser extension that hands your downloads off to
the Cove Download Manager desktop application. This policy explains what data
the extension accesses and what it does with it.

## Summary

The extension does **not** have its own servers, does **not** use analytics,
and does **not** send any data to the developer or to any third party. All
data it touches is passed only to the Cove desktop application running on your
own computer, over Chrome's native messaging channel, for the sole purpose of
performing the download you requested.

## What the extension accesses

When you download a file (or choose "Download with Cove" from the right-click
menu), the extension reads the following and forwards it to the local Cove
desktop app:

- **The download URL** — so the app knows what to download.
- **Cookies for that URL** — so downloads that require a logged-in session
  succeed when the app re-requests the file.
- **The page referrer and your browser's user-agent string** — so the server
  serves the file the same way it would to the browser.

It also stores your **extension settings** (interception on/off, minimum file
size, intercepted file types, excluded domains) in the browser's local
storage on your device.

## How the data is used

- All of the above is sent **only** to the Cove desktop application on the
  same computer, via native messaging, and only at the moment a download is
  handed off.
- The extension does **not** transmit any data over the network itself.
- The extension does **not** collect browsing history, does **not** track your
  activity, and does **not** read the content of the pages you visit.
- Settings never leave your device.

## Data sharing

We do not sell or transfer your data to third parties. We do not use or
transfer your data for any purpose unrelated to performing downloads, and we
do not use it for creditworthiness or lending purposes.

## Contact

Questions: open an issue at
https://github.com/Sin213/cove-download-manager/issues
