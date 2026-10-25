# TrueDuty

Open source time and activity tracker for Windows, macOS and Linux. It works on its own (local mode) and can connect to a [TaskDash](https://github.com/QudsLab/TaskDash) team for timesheets, payroll and team reports.

```
app/       Desktop tracker (Python, customtkinter)        python app/main.py
mobile/    Notes for the Android PWA / TWA wrapper         the page itself is served by TaskDash at /m
docs/      Update plan for the app
```

The server, website and panel now live in the TaskDash repository. The old `web-py` and `web-php` servers are gone.

## Run from source

```
cd app
pip install -r requirements.txt
python main.py
```

Linux needs `python3-tk`. The app stores its database and settings in `%APPDATA%\trueduty` on Windows and `~/.config/trueduty` elsewhere.

## Local mode

With no server connected TrueDuty still tracks: projects you add in Settings, activity per minute (keyboard and mouse event counts, never keys), the active app and, if you allow it, window titles. Insights shows day, week, month, year and any custom range. Short ranges use bars, long ranges a stacked line with work at the bottom, not work above it and unrated on top. Nothing leaves the computer.

## Connected mode

Settings, Connect to a team. Type the server address, check the key fingerprint against the panel, then sign in with one of:

- **Code**: the six digit code from the panel (Settings, App and devices), or a team code `ABCD-EFGH` from your admin. With a team code the app asks for your name, e-mail and a password and creates the account in one step.
- **Password**: e-mail and password.
- **Google**: your browser opens, you approve the computer there, the app finishes by itself.

Traffic uses a hybrid X25519 + ML-KEM-768 handshake with AES-256-GCM and a pinned server key.

### Offline and the signed log

Every record (entries, activity minutes, breaks, idle gaps) is written to a local outbox chained by HMAC-SHA256 with a key only this device and the server know. When the server is unreachable the app keeps tracking and the outbox grows. On sync the server accepts records only in sequence and only when each one's MAC and back-link match. Deleting, editing or reordering records breaks the chain; the server then marks the device and tells the admins. This makes tampering detectable, not impossible: someone with full control of the machine can still choose not to run the app.

The device key and token are wrapped with Windows DPAPI on Windows. On macOS and Linux the config file is readable only by your user.

### Team rules the app follows

- Idle: after the team's idle limit the timer stops. Default rule "start from the max point": time up to the limit counts, the rest becomes a gap you can add back or dismiss.
- Overtime is never blocked. The daily target only colours the ring.
- Screenshots are off by default. They are taken only when the team allows them **and** you agreed in your Privacy page in the panel. Pause for an hour from Settings (logged, admins are told). Every view of a screenshot, including your own, is logged and shown to you.
- Breaks: one click; a daily allowance only warns, it never stops you.

## Builds and releases

`.github/workflows/release.yml` builds the app with Nuitka on every push to `main` that touches `app/`, for Windows x64, macOS (Apple silicon and Intel) and Linux x64, then publishes release `v2.0.<run number>` with `.sha256` files. The TaskDash download page lists these releases automatically.

Local build: `cd app && python build.py` (signing is optional, see the top of `build.py`).

## License

MIT.
