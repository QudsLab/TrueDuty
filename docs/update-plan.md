# Update system plan (server and app)

Status: plan only, nothing here is implemented yet.
Goal: update TaskDash server code and the TrueDuty app in place, without reinstalling, without losing data, and with a way back if an update breaks something.

---

## 1. Shared ideas

**Releases are signed bundles.** Every release is a zip plus a manifest:

```json
{
  "product": "taskdash-server",          // or "trueduty-app"
  "version": "2.1.0",
  "channel": "stable",                    // stable | beta
  "min_from": "2.0.0",                    // oldest version that may update straight to this one
  "files": {"taskdash/core.py": "sha256...", "static/js/panel.js": "sha256..."},
  "migrations": ["2.1.0_001_add_tags.sql"],
  "notes": "Short release notes",
  "created": 1793000000
}
```

The manifest is signed with an Ed25519 release key. Only the public key ships with the product, so a compromised download host cannot push code. The private key lives with the maintainer (or a GitHub Actions secret used only by the release job).

**Where updates come from.** GitHub Releases of `QudsLab/TaskDash` and `QudsLab/TrueDuty` (already used by the download page). A mirror URL can be set in `settings.py` for air gapped installs.

**Version check.** `GET https://api.github.com/repos/<repo>/releases/latest`, at most every 6 hours, cached in the `kv` table (server) or the app's local `kv`.

---

## 2. Server (TaskDash, Python)

### Layout change

```
/srv/taskdash/
  settings.py              stays outside releases, never touched by updates
  data/                    stays outside releases
  releases/
    2.0.0/                 one folder per installed version (code, templates, static)
    2.1.0/
  current -> releases/2.1.0   symlink used by gunicorn / run.py
```

`settings.py` and `data/` are never part of a bundle, so secrets and uploads survive every update untouched.

### Flow

1. **Check**: a background thread (the existing janitor) compares the installed version with the latest release and stores the result. Owners see "Update 2.1.0 available" in Settings, Server, with the release notes.
2. **Download**: owner clicks Update (or runs `python run.py --update`). The server downloads the bundle into `releases/2.1.0.tmp/`, verifies the Ed25519 signature on the manifest and the sha256 of every file, then renames the folder to `releases/2.1.0/`.
3. **Pre flight**: imports the new code in a subprocess (`python -c "import taskdash; taskdash.create_app(check_only=True)"`) to catch syntax or import errors before switching.
4. **Database**: takes a `mysqldump` of the schema and the tables the migrations touch into `data/backups/<version>-<time>.sql.gz`. Then runs the new migrations in order. Every migration is recorded in a `schema_migrations` table (name, applied time) so it runs once. Migrations are additive where possible (new columns with defaults, new tables) so the old code still runs against the new schema during the switch.
5. **Switch**: points `current` to the new folder atomically (`os.replace` on a temporary symlink), then asks the process manager to reload:
   - gunicorn: `kill -HUP <master pid>` reloads workers with zero downtime.
   - systemd: `systemctl reload taskdash` (unit uses `ExecReload=/bin/kill -HUP $MAINPID`).
   - `python run.py` (dev): the process re-execs itself.
6. **Health check**: after reload the updater calls `/api/status` and a few internal checks for 60 seconds. If they fail it switches `current` back to the previous folder and reloads again. The database stays migrated (migrations are additive), and the owner gets a notice with the error.
7. **Cleanup**: keeps the last 3 release folders and the last 5 database backups.

### Small fixes without a full release

A "patch" bundle may contain only changed files. It is still signed and still goes through steps 2 to 6; the updater copies the unchanged files from the current release into the new folder first. Static files get a new `?v=` query (the version) so browsers fetch them again.

### Safety rules

- Only owners can start an update, and the action is in the audit log.
- Updates never edit `settings.py`. New settings get defaults in code; the release notes say when a new setting is worth setting.
- Downgrade is allowed only to versions still in `releases/` (no migrations are reversed; old code must accept newer additive schema).
- Shared hosting without symlinks: same flow, but the switch renames folders (`app` to `app.old`, `app.new` to `app`) and the reload is done by touching `wsgi.py` (Passenger) or restarting the app from the hosting panel.

---

## 3. Desktop app (TrueDuty)

### Two update kinds

1. **Full update** (new executable). Needed when Python, Nuitka or native libraries change.
2. **Code update** (hot patch). The app's own `.py` files and assets, delivered as a signed zip. Small and fast.

### Code updates

- The executable contains a tiny launcher. On start it looks in `<config dir>/code/<version>/` for a newer verified code bundle and imports `main` from there; otherwise it uses the code built into the executable.
- Bundles are verified with the Ed25519 public key compiled into the launcher. A bundle whose `min_launcher` is above the launcher's version is ignored, which forces a full update instead.
- If the new code crashes during start (exception before the main window shows, three times in a row), the launcher marks that version bad and falls back to the previous one. Crash count is kept in a small file next to the bundles.

### Full updates

- The app checks GitHub Releases (or the connected TaskDash server's `/api/releases`) every 6 hours and on start.
- It downloads the asset for its platform, checks the `.sha256` file and the signature, then:
  - **Windows**: downloads to `TrueDuty-new.exe`, starts a small helper (`TrueDuty.exe --swap`) which waits for the old process to exit, renames the old exe to `.old`, moves the new one in place and starts it. The `.old` file is removed on the next start.
  - **macOS**: replaces the `.app` bundle the same way (both are in the user's Applications folder), then re-signs nothing; bundles are signed in CI.
  - **Linux**: replaces the binary in place (rename is atomic on the same filesystem) and restarts.
- The timer is never interrupted by surprise: the app installs only when no timer is running, or asks first ("Update now and restart? Your timer will continue after restart."). A running entry is stopped and a new one started after restart, so no time is lost; the signed log already covers both entries.

### Team controlled versions

- Admins can set a minimum app version in the panel (Settings, App). The `/config` response already carries policy, so `min_app` is one more field. Older apps then show "Please update" and keep tracking locally until updated, so no time is lost.
- Admins can pin a channel (stable or beta) for the team.

### Data safety

- The local database (`trueduty.db`) has its own `schema_version` in `kv`. New code migrates it on start after copying it to `trueduty.db.bak-<version>`.
- The signed outbox is never altered by migrations. Records already in the chain stay byte for byte the same, so updates cannot break the chain.

---

## 4. CI changes needed

- Release job signs `manifest.json` with the Ed25519 key from a GitHub secret and uploads `manifest.json`, `manifest.sig`, the code bundle and the executables.
- Server repo gets its own release workflow that zips `taskdash/`, `templates/`, `static/`, `run.py`, `wsgi.py`, `requirements.txt` and the migrations, without `settings.py` and `data/`.

## 5. Order of work

1. `schema_migrations` table and migration runner (server), `schema_version` (app).
2. Release signing in CI, public key in both products.
3. Server updater with symlink switch, health check and rollback.
4. App launcher with code bundles and fallback.
5. Full app updates with the swap helper.
6. Panel UI: update banner, release notes, minimum app version.
