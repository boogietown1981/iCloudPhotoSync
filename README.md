# Synology iCloud Photo Sync
A native Synology DSM 7.2 package that automatically mirrors your iCloud photo library to your NAS — so your memories live on storage you own, not just on Apple's servers.
Runs as a proper DSM app with its own tile, settings UI, scheduler daemon, and DSM notifications. No Docker, no cron hacks, no SSH fiddling.

Built with the [SynoCommunity/spksrc](https://github.com/SynoCommunity/spksrc) cross-compilation framework.

<img width="1851" height="1129" alt="Unbenannt-1" src="https://github.com/user-attachments/assets/d5230266-5553-4aa1-88ca-030d1ae2570d" />

## Features

- **iCloud Photostream, Albums & Shared Libraries** — incremental sync with deduplication via hardlinks
- **Multi-account** — several Apple IDs side by side, each with its own settings
- **Parallel downloads** — 1/2/4/8 configurable per account
- **Folder structure** — year / year-month / year-month-day / flat
- **Album folders** — Apple's folder tree is kept on disk and shown as a collapsible tree; a folder's checkbox selects every album below it
- **HEIC / JPG conversion** — keep originals, convert, or both
- **Live Photos** — optionally save the video part as `.MOV` next to the photo (same name, as Synology Photos and Apple's export expect)
- **Apple 2FA** via trusted-device push or SMS fallback
- **Native DSM UI** — built with SYNO.ux components
- **Multi-language** — English and German
- **Unprivileged** — runs as `iCloudPhotoSync`, not root

## Prebuild Releases

You always find the latest version under releases:

[https://github.com/Euphonique/iCloudPhotoSync/releases/latest](https://github.com/Euphonique/iCloudPhotoSync/releases/latest)

## Building

### Standalone build (recommended)

No spksrc checkout required — just run the included build script:

```bash
./build.sh
```

The resulting `.spk` file is created in the project root (e.g. `iCloudPhotoSync-1.4.4.spk`).

### Building with spksrc

Alternatively, build via the full [spksrc](https://github.com/SynoCommunity/spksrc) cross-compilation framework:

1. Clone spksrc and set up the build environment (Docker recommended):
   ```bash
   git clone https://github.com/SynoCommunity/spksrc.git
   cd spksrc
   docker build -t spksrc .
   ```

2. Copy or symlink the package directory into your spksrc checkout:
   ```bash
   cp -r /path/to/iCloudPhotoSync-spksrc/spk/icloudphotosync spk/
   ```

3. Build:
   ```bash
   cd spk/icloudphotosync
   make arch-x64-7.2
   ```

The resulting `.spk` files land in `packages/`.

## Package structure (spksrc layout)

```
spk/icloudphotosync/
  Makefile                 spksrc package definition
  PLIST                    File list for SPK contents
  src/
    service-setup.sh       DSM lifecycle hooks (start/stop/install/upgrade)
    PACKAGE_ICON.PNG       Package icons
    PACKAGE_ICON_256.PNG
    requirements-pure.txt  Python wheel dependencies
    bin/
      scheduler.py         Long-running daemon, triggers syncs per interval
      sync_runner.py       Single-sync entry point (UI sync-now button)
      move_runner.py       Target-folder migration helper
      heif/                Bundled HEIC conversion binaries (per architecture)
    lib/
      sync_engine.py       Core sync loop: list -> dedupe -> download -> verify
      icloud_client.py     iCloud API wrapper (pyicloud_ipd)
      config_manager.py    Global + per-account config with atomic file locking
      heic_converter.py    HEIC -> JPG conversion with multi-backend fallback
      handlers/            CGI request handlers
      vendor/              Bundled Python deps (pyicloud_ipd, srp, six)
    app/                   DSM SPA — Ext.js + SYNO.ux components
    conf/
      privilege            run-as: package
      resource             data-share for /volume1/iCloudPhotos
```

## v1.9.4 — visible, responsive Integrity tab

- The integrity features now live in their own DSM tab, **Integrität / Integrity**, between Logs and About rather than the crowded Logs toolbar.
- Three clearly visible action buttons are stacked vertically, so they do not disappear in narrower DSM windows.
- New translation keys are included in the DSM `preloadTexts` list and registered as a package library component.
- Shows current integrity scan status and summary on the same tab. Updates do not modify user photos or credentials.
- After upgrading the SPK, **close the DSM app window and hard-reload the DSM page** to clear cached JavaScript.

## v1.9.3 — full integrity reports and safe repair preview

- Every finding from a completed integrity scan is saved as a credential-free JSONL file, rather than keeping just the first 25 examples.
- DSM Logs tab: **Repair preview** shows the first 20 issues and suggested next steps; **Export audit report** downloads all findings as JSONL for analysis.
- Reports contain file paths only relative to the photo target and do not include Apple IDs, credentials, signed URLs, or cookies.
- Interrupted scans retain the previous completed report and mark it as potentially stale. No photos are overwritten or deleted.
- The preview is intentionally read-only: rebuilding damaged files from iCloud requires an explicitly approved recovery procedure.

## v1.9.2 — DSM web connection repair

- The DSM `api.cgi` endpoint now starts the same compatible Python family as the package service, instead of using an arbitrary `/usr/bin/env python3` interpreter.
- The full Python CGI lives in `app/api_main.py`; the launcher preserves all existing DSM authentication.
- Album logging no longer breaks even read-only API endpoints when the CGI user cannot write to `album.log`.
- The frontend reports structured authorization or Python prerequisites errors instead of a generic connection failure.
- If the web request still fails, check the HTTP response code (403 indicates a DSM authorization problem; 404 an app/CGI routing problem; 500 a backend error). Avoid changing permissions broadly or disabling CSRF.

## v1.9.1 — Python prerequisite protection

- The standalone installer and spksrc lifecycle select only Python 3.10+ interpreters and reject older Python versions before starting.
- Python 3.11 is recommended for DSM 7.2+; 1.9.0 features remain unchanged.

## v1.9.0 — streaming exports and integrity checks

- Native browser ZIP downloads: no complete ZIP buffering in the NAS CGI or browser JavaScript.
- On-demand SHA-256 photo integrity audit in the Logs tab. The first scan builds a local baseline for old files; following scans detect missing or subsequently modified files. The scan never deletes photos, and it does not claim that a legacy file originally matched iCloud.
- Per-asset temporary downloads use the package data volume, capped at 12 GiB each; the ZIP includes _EXPORT_ERRORS.txt if some items fail.
- HTTP libraries updated to modern pinned releases; only architecture-independent Python wheels are bundled.
- Requires Python **3.10+**; use Python 3.11 on DSM 7.2. Test iCloud login and 2FA with the upgraded libraries.

## v1.8.0 — stability and security hardening

- DSM administration API is now **administrator-only**. Existing non-admin DSM users will no longer be able to open/manage this package.
- Synchronization now flags failed asset downloads or incomplete CloudKit enumeration instead of incorrectly displaying a successful backup.
- Downloaded assets are checked against HTTP Content-Length and Apple's asset byte count when supplied, before the final file replaces its temporary download.
- Cross-volume moves use a verified temporary copy with SHA-256 comparison and exclusive publication; existing target files are **never** overwritten.
- An incomplete move reports an error. Standalone builds no longer create sudoers NOPASSWD rules; grant the package user's target share permissions in DSM manually.
- GitHub PR / release builds should run the regression checks in `tests/` before deployment. Existing SQLite manifests remain unchanged.

> This is a source-level hardening release. Verify on a test NAS with your own iCloud library before upgrading a production installation, and back up your manifest database first.

## Requirements

- Synology DSM **7.2** or newer
- Python 3.10+ (recommended: Python 3.11)
- An Apple ID with 2FA enabled
- **iCloud Advanced Data Protection (ADP) must be disabled** for iCloud Photos

## Known limitations

### iCloud Advanced Data Protection (ADP)

If you have ADP enabled, this app cannot access your iCloud Photos. ADP encrypts photos end-to-end so only trusted Apple devices hold decryption keys.

**Workarounds:**
1. Disable ADP: *Settings -> Apple ID -> iCloud -> Advanced Data Protection -> Turn Off*
2. Enable temporary web access at [icloud.com](https://icloud.com) (grants ~1 hour API access)

### Shared Albums (legacy)

Sadly had to remove the Shared Albums feature from Settings, Albums tab, and sync engine. Legacy Shared Albums use a separate Apple API (sharedstreams.icloud.com) that is not accessible via CloudKit. Use the iCloud Shared Library (iOS 16+) feature instead.

## Privacy & security

- Apple password is **never stored permanently** — it is only held temporarily during the 2FA handshake, encrypted with PBKDF2-derived keys and HMAC-authenticated, and kept in RAM only (`/dev/shm`). It is discarded immediately after authentication completes.
- Session cookies stored under `/var/packages/icloudphotosync/var/accounts/{id}/session/` with restrictive file permissions (owner-only)
- All API endpoints require a logged-in DSM user: every request is verified against DSM's `authenticate.cgi`, including the SynoToken when DSM's CSRF protection is enabled
- No telemetry, no analytics, no phone-home


## License

[MIT](LICENSE). Vendored third-party code keeps its original license:
- [pyicloud_ipd](https://github.com/icloud-photos-downloader/pyicloud_ipd) — MIT
- [srp](https://github.com/cocagne/pysrp) — BSD

## Disclaimer

Not affiliated with or endorsed by Apple Inc. "Apple", "iCloud", and related marks are trademarks of Apple Inc.
