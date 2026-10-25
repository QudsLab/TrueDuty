# Mobile (Android)

The mobile tracker is served by your TaskDash server. It is **`/m`, a tracker-only page** (login, project, start/stop) that installs as a PWA. No Google services needed. The full dashboard stays at the normal address.

**Install (no APK needed):** open `https://YOUR-SERVER/m` in Chrome / Vanadium (GrapheneOS) / any Chromium browser -> menu -> *Install app* / *Add to Home screen*.
Press Start; the page pings the server every minute, so if the phone dies the entry ends at the last ping. Turn on *Keep screen awake* if your browser throttles background tabs.
Phones don't take screenshots (by design). iOS is not supported.

## Optional: real .apk
If you want an `.apk` file to hand out, wrap the PWA as a Trusted Web Activity:

```
npm i -g @bubblewrap/cli
bubblewrap init --manifest https://YOUR-SERVER/static/manifest-m.json     # or copy twa-manifest.json from this folder and edit host
bubblewrap build                                                 # -> app-release-signed.apk (sign with your own keystore)
```
Needs a Chromium-based browser on the phone. Serve `/.well-known/assetlinks.json` from your server (bubblewrap prints the content) so the URL bar is hidden.

The tracker page uses the same fonts and appearance modes as the TaskDash panel: dark or light, color or grayscale (follows the system by default).
