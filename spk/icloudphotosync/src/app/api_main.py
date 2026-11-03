#!/usr/bin/env python3
"""
iCloud Photo Sync — API endpoint served via /webman/3rdparty/iCloudPhotoSync/api.cgi

Routes requests based on the 'method' parameter to the appropriate handler
in the lib/handlers/ directory.
"""
import json
import os
import sys
import cgi
import urllib.parse

# The app/ dir lives at /var/packages/iCloudPhotoSync/target/app/
# The lib/ dir lives at /var/packages/iCloudPhotoSync/target/lib/
PKG_TARGET = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
LIB_DIR = os.path.join(PKG_TARGET, "lib")
VENDOR_DIR = os.path.join(LIB_DIR, "vendor")
sys.path.insert(0, LIB_DIR)
if os.path.isdir(VENDOR_DIR):
    sys.path.insert(0, VENDOR_DIR)

from handlers import status as status_handler
from handlers import auth as auth_handler
from handlers import account as account_handler
from handlers import album as album_handler
from handlers import sync as sync_handler
from handlers import config as config_handler
from handlers import log as log_handler
from handlers import move as move_handler
from handlers import update as update_handler
from handlers import integrity as integrity_handler

HANDLERS = {
    "status": status_handler.handle,
    "auth": auth_handler.handle,
    "account": account_handler.handle,
    "album": album_handler.handle,
    "sync": sync_handler.handle,
    "config": config_handler.handle,
    "log": log_handler.handle,
    "move": move_handler.handle,
    "update": update_handler.handle,
    "integrity": integrity_handler.handle,
}


def respond(success, data=None, error=None, total=None):
    result = {"success": success}
    if data is not None:
        result["data"] = data
    if error is not None:
        result["error"] = error
    if total is not None:
        result["total"] = total
    body = json.dumps(result)
    print("Content-Type: application/json")
    print("Content-Length: %d" % len(body))
    print()
    print(body)


def _is_icloud_url(url):
    """Validate that url points to an Apple iCloud content domain."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        # China accounts are served from icloud-content.com.cn
        return (
            parsed.scheme == "https"
            and any(host == d or host.endswith("." + d)
                    for d in ("icloud-content.com", "icloud-content.com.cn"))
        )
    except Exception:
        return False


def proxy_thumb():
    """Proxy iCloud thumbnail to avoid mixed-content browser block."""
    params = cgi.FieldStorage()
    url = params.getvalue("url", "")
    if not url or not _is_icloud_url(url):
        print("Status: 400 Bad Request")
        print("Content-Type: text/plain")
        print()
        print("Invalid URL")
        return

    import requests
    try:
        r = requests.get(url, timeout=15)
        ct = r.headers.get("Content-Type", "image/jpeg")
        sys.stdout.buffer.write(("Content-Type: %s\r\n" % ct).encode())
        sys.stdout.buffer.write(("Content-Length: %d\r\n" % len(r.content)).encode())
        sys.stdout.buffer.write(("Cache-Control: public, max-age=86400\r\n").encode())
        sys.stdout.buffer.write(b"\r\n")
        sys.stdout.buffer.write(r.content)
    except Exception:
        print("Status: 502 Bad Gateway")
        print("Content-Type: text/plain")
        print()
        print("Fetch failed")


def _safe_filename(name, fallback="photo.jpg"):
    """Strip path separators and control chars from filename."""
    if not name:
        return fallback
    name = name.replace("\\", "_").replace("/", "_").replace("\r", "").replace("\n", "")
    name = name.strip(". ")
    return name or fallback


def download_photo():
    """Stream a single iCloud asset to the browser as file download."""
    params = cgi.FieldStorage()
    url = params.getvalue("url", "")
    filename = _safe_filename(params.getvalue("filename", ""))
    if not url or not _is_icloud_url(url):
        print("Status: 400 Bad Request")
        print("Content-Type: text/plain")
        print()
        print("Invalid URL")
        return

    import requests
    try:
        r = requests.get(url, timeout=60, stream=True)
        ct = r.headers.get("Content-Type", "application/octet-stream")
        cl = r.headers.get("Content-Length")
        sys.stdout.buffer.write(("Content-Type: %s\r\n" % ct).encode())
        if cl:
            sys.stdout.buffer.write(("Content-Length: %s\r\n" % cl).encode())
        sys.stdout.buffer.write(
            ('Content-Disposition: attachment; filename="%s"\r\n' % filename).encode()
        )
        sys.stdout.buffer.write(b"\r\n")
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                sys.stdout.buffer.write(chunk)
    except Exception:
        print("Status: 502 Bad Gateway")
        print("Content-Type: text/plain")
        print()
        print("Fetch failed")


def _parse_export_request(raw_body, content_type):
    """Accept browser-native form POSTs and legacy JSON AJAX callers."""
    if "application/x-www-form-urlencoded" in content_type:
        fields = urllib.parse.parse_qs(raw_body, max_num_fields=5)
        return json.loads(fields.get("payload", ["{}"])[0])
    return json.loads(raw_body or "{}")


def _stream_export_zip(items, output, requests_module=None, temp_dir=None):
    """Bounded-memory ZIP writer; never loads a whole video or ZIP into RAM.

    One temporary media file is stored on the package data volume at a time
    so failed/incomplete downloads cannot poison the ZIP. Output itself is
    written to a non-seekable CGI stream. Failed items are listed in-ZIP.
    """
    import zipfile
    import tempfile
    import shutil
    import requests as requests_lib
    import config_manager

    requests_module = requests_module or requests_lib
    temp_dir = temp_dir or config_manager.PKG_VAR
    os.makedirs(temp_dir, exist_ok=True)
    max_asset_bytes = 12 * 1024 ** 3
    reserve_bytes = 128 * 1024 ** 2
    failed = []
    used = set()
    succeeded = 0

    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for it in items:
            raw_name = _safe_filename(it.get("filename", "photo"))
            stem, ext = os.path.splitext(raw_name)
            name = raw_name
            seq = 2
            while name.lower() in used or name == "_EXPORT_ERRORS.txt":
                name = "%s_%d%s" % (stem, seq, ext)
                seq += 1
            used.add(name.lower())
            try:
                with requests_module.get(it["url"], timeout=(15, 45), stream=True) as resp:
                    resp.raise_for_status()
                    declared = resp.headers.get("Content-Length")
                    declared_size = int(declared) if declared and declared.isdigit() else None
                    if declared_size is not None and declared_size > max_asset_bytes:
                        raise IOError("Asset exceeds 12 GiB export limit")
                    with tempfile.TemporaryFile(mode="w+b", dir=temp_dir) as tmp:
                        received = 0
                        for chunk in resp.iter_content(chunk_size=256 * 1024):
                            if not chunk:
                                continue
                            received += len(chunk)
                            if received > max_asset_bytes:
                                raise IOError("Asset exceeds 12 GiB export limit")
                            if shutil.disk_usage(temp_dir).free < reserve_bytes:
                                raise IOError("Insufficient free disk space for export")
                            tmp.write(chunk)
                        if (declared_size is not None
                                and not resp.headers.get("Content-Encoding")
                                and received != declared_size):
                            raise IOError("Incomplete asset transfer")
                        tmp.seek(0)
                        with zf.open(name, "w", force_zip64=True) as entry:
                            shutil.copyfileobj(tmp, entry, length=1024 * 1024)
                        succeeded += 1
            except Exception as exc:
                # URL often contains signed private query parameters: never
                # include it or the exception string in exported diagnostics.
                import logging
                logging.getLogger("api.export").warning(
                    "ZIP export skipped item %s (%s)", raw_name,
                    type(exc).__name__)
                failed.append(raw_name)

        if failed:
            text = ("iCloud Photo Sync: %d of %d assets could not be exported.\n"
                    "Retry these files or their expired download URLs.\n\n" %
                    (len(failed), len(items)))
            zf.writestr("_EXPORT_ERRORS.txt", text + "\n".join(failed) + "\n")
    return {"exported": succeeded, "failed": len(failed)}


def download_zip(raw_body):
    """Stream ZIP directly to browser; multipart asset buffering is disk-only."""
    try:
        payload = _parse_export_request(raw_body, os.environ.get("CONTENT_TYPE", ""))
        items = payload.get("items", [])
        if not isinstance(items, list) or not 0 < len(items) <= 5000:
            raise ValueError("Expected 1 to 5000 items")
        if any(not isinstance(it, dict) or
               not isinstance(it.get("url"), str) or
               not _is_icloud_url(it["url"]) for it in items):
            raise ValueError("Invalid Apple asset URL")
        zipname = _safe_filename(payload.get("zipname") or "photos.zip", "photos.zip")
    except (ValueError, TypeError, AttributeError) as exc:
        print("Status: 400 Bad Request")
        print("Content-Type: text/plain")
        print()
        print("Invalid export request")
        return

    sys.stdout.buffer.write(b"Content-Type: application/zip\r\n")
    sys.stdout.buffer.write(
        ('Content-Disposition: attachment; filename="%s"\r\n' % zipname).encode("utf-8"))
    sys.stdout.buffer.write(b"Cache-Control: private, no-store\r\n\r\n")
    _stream_export_zip(items, sys.stdout.buffer)


def _log_sanitizer():
    """Build a (text) -> text function that scrubs account-identifying data.

    We ship this ZIP to support requests / GitHub issues, so anything that
    leaks the user's Apple ID, account UUID, or session tokens is a privacy
    bug. The scrubber runs per-line and keeps a stable alias (apple-id-1,
    account-1) so multi-account logs remain correlatable after redaction.
    """
    import re
    import config_manager

    email_aliases = {}
    account_aliases = {}

    # Preload known account IDs + Apple IDs from config so redaction is
    # consistent even if they don't happen to appear in this particular
    # log file (and to keep numbering stable across multiple exports).
    try:
        cfg = config_manager.load_config() or {}
        for i, acc in enumerate(cfg.get("accounts") or [], 1):
            apple_id = (acc.get("apple_id") or "").strip().lower()
            if apple_id:
                email_aliases[apple_id] = "<apple-id-%d>" % i
            account_id = acc.get("id") or ""
            if account_id:
                account_aliases[account_id] = "<account-%d>" % i
    except Exception:
        pass

    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    uuid_re = re.compile(r"\b[0-9a-fA-F]{8}\b")  # 8-hex account-id prefix style
    # Catch auth-sensitive key=value chunks on a single line. We look for the
    # key name and nuke the rest of the token up to whitespace / quote / comma.
    secret_kv_re = re.compile(
        r"(?i)(password|passwd|pwd|token|cookie|authorization|x-apple-[\w-]*|"
        r"session[_-]?id|trust[_-]?token|srp[_-]?[a-z]*|apple[_-]?id[_-]?(?:\w*))"
        r"\s*[:=]\s*['\"]?([^\s,'\")}]+)",
    )
    # Authorization-style header values: "Bearer <tok>".
    bearer_re = re.compile(r"(?i)\bBearer\s+\S+")

    def alias_email(match):
        addr = match.group(0).lower()
        if addr not in email_aliases:
            email_aliases[addr] = "<apple-id-%d>" % (len(email_aliases) + 1)
        return email_aliases[addr]

    def alias_uuid(match):
        uuid = match.group(0)
        # Don't alias short hex chunks that are unlikely to be account ids —
        # timestamps / log levels like "INFO" aren't hex anyway. We only
        # redact values that appear in known_account_ids; unrecognised hex
        # (git SHAs, request IDs) is safe to leave alone.
        if uuid in account_aliases:
            return account_aliases[uuid]
        return uuid

    def sanitize(text):
        text = email_re.sub(alias_email, text)
        text = uuid_re.sub(alias_uuid, text)
        text = secret_kv_re.sub(lambda m: "%s=<redacted>" % m.group(1), text)
        text = bearer_re.sub("Bearer <redacted>", text)
        return text

    return sanitize


def _build_diagnostics(sanitize):
    """Build a diagnostics report with per-account state for support.

    Includes sync_progress.json, manifest DB stats, sync config excerpt,
    and file timestamps — enough to debug issues even when logs are empty.
    """
    import time as _time
    import config_manager

    lines = []
    lines.append("=== iCloud Photo Sync Diagnostics ===")
    lines.append("Generated: %s" % _time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")

    # Global config excerpt (non-sensitive)
    try:
        cfg = config_manager.load_config() or {}
        lines.append("--- Global config ---")
        lines.append("log_level: %s" % cfg.get("log_level", "INFO"))
        lines.append("log_retention_days: %s" % cfg.get("log_retention_days", 7))
        lines.append("accounts: %d" % len(cfg.get("accounts") or []))
        lines.append("")
    except Exception as e:
        lines.append("Global config error: %s" % e)
        lines.append("")

    # Per-account diagnostics
    accounts = config_manager.get_accounts()
    for i, acc in enumerate(accounts, 1):
        acc_id = acc.get("id", "")
        lines.append("=" * 50)
        lines.append("Account %d: %s" % (i, sanitize(acc.get("apple_id", "?"))))
        lines.append("Status: %s" % acc.get("status", "?"))
        acc_dir = config_manager.get_account_dir(acc_id)
        lines.append("Account dir exists: %s" % os.path.isdir(acc_dir))
        lines.append("")

        # sync_progress.json
        prog_path = os.path.join(acc_dir, "sync_progress.json")
        lines.append("  --- sync_progress.json ---")
        try:
            stat = os.stat(prog_path)
            lines.append("  mtime: %s" % _time.strftime(
                "%Y-%m-%d %H:%M:%S", _time.localtime(stat.st_mtime)))
            lines.append("  size: %d bytes" % stat.st_size)
            import json as _json
            with open(prog_path, "r") as f:
                prog = _json.load(f)
            for k in ("status", "started_at", "finished_at", "total_photos",
                       "synced_photos", "skipped_photos", "failed_photos",
                       "current_album", "error"):
                v = prog.get(k, "")
                if k in ("started_at", "finished_at") and v:
                    v = "%s (%s)" % (v, _time.strftime(
                        "%Y-%m-%d %H:%M:%S", _time.localtime(v)))
                lines.append("  %s: %s" % (k, v))
            if prog.get("warnings"):
                lines.append("  warnings: %s" % sanitize(
                    str(prog["warnings"][:5])))
        except FileNotFoundError:
            lines.append("  (file not found)")
        except Exception as e:
            lines.append("  error reading: %s" % e)
        lines.append("")

        # Manifest DB stats
        lines.append("  --- Manifest DB ---")
        db_path = os.path.join(acc_dir, "sync_manifest.db")
        try:
            stat = os.stat(db_path)
            lines.append("  mtime: %s" % _time.strftime(
                "%Y-%m-%d %H:%M:%S", _time.localtime(stat.st_mtime)))
            lines.append("  size: %d bytes" % stat.st_size)
            import sync_manifest
            stats = sync_manifest.get_stats(acc_id)
            for k, v in stats.items():
                if k == "last_sync" and v:
                    v = "%s (%s)" % (v, _time.strftime(
                        "%Y-%m-%d %H:%M:%S", _time.localtime(v)))
                lines.append("  %s: %s" % (k, v))
        except FileNotFoundError:
            lines.append("  (file not found)")
        except Exception as e:
            lines.append("  error reading: %s" % e)
        lines.append("")

        # Sync config excerpt (non-sensitive fields only)
        lines.append("  --- Sync config ---")
        try:
            sc = config_manager.get_sync_config(acc_id)
            lines.append("  target_dir: %s" % sanitize(
                sc.get("target_dir", "")))
            lines.append("  sync_interval: %s" % sc.get("sync_interval", ""))
            ps = sc.get("photostream", {})
            lines.append("  photostream.enabled: %s" % ps.get("enabled", ""))
            lines.append("  photostream.folder_structure: %s" % ps.get(
                "folder_structure", ""))
            ab = sc.get("albums", {})
            lines.append("  albums.enabled: %s" % ab.get("enabled", ""))
            selected = ab.get("selected", {})
            lines.append("  albums.selected: %d album(s)" % len(
                [v for v in selected.values() if v]))
            sl = sc.get("shared_library", {})
            if sl:
                lines.append("  shared_library.enabled: %s" % sl.get(
                    "enabled", ""))
            lines.append("  parallel_downloads: %s" % sc.get(
                "parallel_downloads", ""))
            lines.append("  file_format: %s" % sc.get("file_format", ""))
            lines.append("  filename_format: %s" % sc.get(
                "filename_format", ""))
            lines.append("  conflict_resolution: %s" % sc.get(
                "conflict_resolution", ""))
        except Exception as e:
            lines.append("  error reading: %s" % e)
        lines.append("")

        # Album cache
        lines.append("  --- Album cache ---")
        cache_path = os.path.join(acc_dir, "album_cache.json")
        try:
            stat = os.stat(cache_path)
            lines.append("  mtime: %s" % _time.strftime(
                "%Y-%m-%d %H:%M:%S", _time.localtime(stat.st_mtime)))
            import json as _json
            with open(cache_path, "r") as f:
                cache = _json.load(f)
            lines.append("  albums cached: %d" % len(
                cache.get("counts", {})))
            lines.append("  has_shared_library: %s" % cache.get(
                "has_shared_library", False))
            lines.append("  updated: %s" % (
                _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(
                    cache["updated"])) if cache.get("updated") else "never"))
        except FileNotFoundError:
            lines.append("  (file not found)")
        except Exception as e:
            lines.append("  error reading: %s" % e)
        lines.append("")

        # Scheduler marker
        lines.append("  --- Scheduler ---")
        marker = os.path.join(acc_dir, "last_sync_run")
        try:
            stat = os.stat(marker)
            lines.append("  last_sync_run mtime: %s" % _time.strftime(
                "%Y-%m-%d %H:%M:%S", _time.localtime(stat.st_mtime)))
        except FileNotFoundError:
            lines.append("  last_sync_run: (not found)")
        except Exception as e:
            lines.append("  error: %s" % e)
        lines.append("")

    # Log file sizes and mtimes
    lines.append("=" * 50)
    lines.append("--- Log files ---")
    log_dir = os.path.join(config_manager.PKG_VAR, "logs")
    try:
        for name in sorted(os.listdir(log_dir)):
            path = os.path.join(log_dir, name)
            if os.path.isfile(path):
                stat = os.stat(path)
                lines.append("  %s: %d bytes, mtime %s" % (
                    name, stat.st_size,
                    _time.strftime("%Y-%m-%d %H:%M:%S",
                                   _time.localtime(stat.st_mtime))))
    except Exception as e:
        lines.append("  error: %s" % e)

    return "\n".join(lines) + "\n"


def export_logs_zip():
    """Stream all package logs + INFO + version as a ZIP for support reports.

    Used by the "Export logs" button in the Logs tab. Every text file is
    passed through a sanitizer that strips Apple IDs, account UUIDs, and
    auth-shaped key=value tokens before it lands in the ZIP. We never
    include config.json or session cookie files.
    """
    import zipfile
    import io
    import time as _time
    import config_manager

    log_dir = os.path.join(config_manager.PKG_VAR, "logs")
    pkg_dir = "/var/packages/iCloudPhotoSync"
    sanitize = _log_sanitizer()

    def _sanitize_and_add(zf, src_path, arcname):
        try:
            with open(src_path, "r", errors="replace") as f:
                content = sanitize(f.read())
        except OSError:
            return
        zf.writestr(arcname, content)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Every file in var/logs/ (sync.log, scheduler.log, cron.log,
        # startup-error.log, etc.). We read as text and sanitize — any
        # binary artifact in logs/ (shouldn't exist, but just in case) is
        # skipped by the errors="replace" read.
        if os.path.isdir(log_dir):
            for name in sorted(os.listdir(log_dir)):
                path = os.path.join(log_dir, name)
                if os.path.isfile(path):
                    _sanitize_and_add(zf, path, "logs/" + name)

        # INFO is the pkg metadata (version, maintainer). It doesn't contain
        # user data, but run it through the sanitizer anyway for defence in
        # depth (the maintainer email is there but that's public).
        info = os.path.join(pkg_dir, "INFO")
        if os.path.isfile(info):
            _sanitize_and_add(zf, info, "INFO")

        # A small environment snapshot so a support report has DSM version,
        # architecture, and the detected Python path in one place. We
        # explicitly do NOT include serial numbers from /proc/cpuinfo —
        # ARM-j boards sometimes expose the NAS serial there.
        try:
            lines = []
            lines.append("timestamp: %s" % _time.strftime("%Y-%m-%d %H:%M:%S"))
            lines.append("python: %s" % sys.version.replace("\n", " "))
            lines.append("platform: %s" % sys.platform)
            try:
                import platform as _p
                lines.append("machine: %s" % _p.machine())
                lines.append("system: %s %s" % (_p.system(), _p.release()))
            except Exception:
                pass
            try:
                with open("/etc.defaults/VERSION", "r") as f:
                    lines.append("---- /etc.defaults/VERSION ----")
                    for ln in f.read().splitlines():
                        # unique= and upnpmodelname= contain NAS-identifying
                        # values; strip them. Everything else (majorversion,
                        # build, etc.) is useful for debugging.
                        low = ln.lower()
                        if low.startswith("unique=") or "upnp" in low or \
                           "serial" in low or "mac" in low:
                            continue
                        lines.append(ln)
            except OSError:
                pass
            try:
                with open("/proc/cpuinfo", "r") as f:
                    lines.append("---- /proc/cpuinfo (architecture only) ----")
                    for ln in f.read().splitlines():
                        low = ln.lower()
                        # Keep arch/feature info; drop serial / hardware IDs.
                        if low.startswith(("serial", "hardware", "revision")):
                            continue
                        lines.append(ln)
                        if len(lines) > 400:
                            break
            except OSError:
                pass
            zf.writestr("environment.txt", "\n".join(lines))
        except Exception:
            pass

        # Per-account diagnostics: sync_progress, manifest stats, config
        # excerpt, and file timestamps — enough to debug issues even when
        # the logs are empty (e.g. after log rotation).
        try:
            diag = _build_diagnostics(sanitize)
            zf.writestr("diagnostics.txt", diag)
        except Exception:
            pass

        # Also include a one-line note that the archive was sanitized so
        # anyone receiving it knows Apple IDs are aliases, not the originals.
        zf.writestr(
            "README.txt",
            "iCloud Photo Sync support bundle\n"
            "Generated: %s\n\n"
            "Email addresses (Apple IDs) have been replaced with aliases\n"
            "like <apple-id-1>. Account UUIDs, auth tokens, passwords, and\n"
            "trust cookies have been redacted. config.json and session\n"
            "cookie files are never included in this archive.\n" %
            _time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    data = buf.getvalue()
    zipname = "iCloudPhotoSync-logs-%s.zip" % _time.strftime("%Y%m%d-%H%M%S")
    sys.stdout.buffer.write(b"Content-Type: application/zip\r\n")
    sys.stdout.buffer.write(("Content-Length: %d\r\n" % len(data)).encode())
    sys.stdout.buffer.write(
        ('Content-Disposition: attachment; filename="%s"\r\n' % zipname).encode()
    )
    sys.stdout.buffer.write(b"\r\n")
    sys.stdout.buffer.write(data)


def _query_param(name):
    """Parse one value from QUERY_STRING without touching stdin."""
    qs = os.environ.get("QUERY_STRING", "")
    parsed = urllib.parse.parse_qs(qs)
    vals = parsed.get(name, [])
    return vals[0] if vals else ""


def _method_from_query():
    """Parse the 'method' value from QUERY_STRING without touching stdin."""
    return _query_param("method")


AUTHENTICATE_CGI = "/usr/syno/synoman/webman/modules/authenticate.cgi"


def _dsm_user():
    """Return the DSM user who sent this request, or "" if not logged in.

    DSM does not authenticate CGIs under /webman/3rdparty/ by itself (#77).
    Synology's developer guide says to ask authenticate.cgi, which checks
    the session cookie and — with CSRF protection enabled — the SynoToken.
    It reads the token from QUERY_STRING, so the token the frontend sends
    (X-SYNO-TOKEN header for Ajax, SynoToken param for <img>/downloads)
    is passed on that way. It must never see our POST body.
    """
    import subprocess
    # DSM's own Ajax hook sends the token URI-encoded; parse_qs already
    # decodes the query parameter
    token = urllib.parse.unquote(os.environ.get("HTTP_X_SYNO_TOKEN", "")) or \
        _query_param("SynoToken")
    env = dict(os.environ)
    env["QUERY_STRING"] = ("SynoToken=" + urllib.parse.quote(token)) if token else ""
    env["REQUEST_METHOD"] = "GET"
    env.pop("CONTENT_LENGTH", None)
    env.pop("CONTENT_TYPE", None)
    try:
        result = subprocess.run(
            [AUTHENTICATE_CGI], env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = [ln.strip() for ln in result.stdout.decode("utf-8", "replace").splitlines()]
    lines = [ln for ln in lines if ln]
    return lines[-1] if lines else ""


def _is_dsm_admin(user):
    """Authorize DSM administrators only, not merely logged-in DSM users."""
    try:
        import grp
        import pwd
        account = pwd.getpwnam(user)
        admin_group = grp.getgrnam("administrators")
        if account.pw_gid == admin_group.gr_gid or user in admin_group.gr_mem:
            return True
        return admin_group.gr_gid in os.getgrouplist(user, account.pw_gid)
    except (KeyError, OSError, AttributeError):
        return False


def _deny():
    body = json.dumps({"success": False, "error": {
        "code": 403, "message": "DSM administrator permissions required."}})
    print("Status: 403 Forbidden")
    print("Content-Type: application/json")
    print("Content-Length: %d" % len(body))
    print()
    print(body)


def main():
    # Every endpoint touches Apple credentials, the user's photos or the
    # filesystem — none may be reachable without a DSM login (#77).
    user = _dsm_user()
    if not user or not _is_dsm_admin(user):
        _deny()
        return
    # Lets handlers resolve /home/... paths for the requesting user
    os.environ["ICS_DSM_USER"] = user

    # Read the method from QUERY_STRING first so POST bodies (download_zip)
    # aren't accidentally consumed by cgi.FieldStorage before the handler runs.
    method = _method_from_query()

    if method == "thumb":
        proxy_thumb()
        return
    if method == "download":
        download_photo()
        return
    if method == "download_zip":
        try:
            length = int(os.environ.get("CONTENT_LENGTH", "0") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > 2 * 1024 * 1024:
            print("Status: 413 Payload Too Large")
            print("Content-Type: text/plain")
            print()
            print("Export selection too large")
            return
        raw_body = sys.stdin.read(length) if length else ""
        download_zip(raw_body)
        return
    if method == "log_export":
        export_logs_zip()
        return
    if method == "integrity_export":
        import integrity_checker
        import integrity_report
        import config_manager
        account_id = _query_param("account_id")
        if not config_manager.get_account(account_id):
            print("Status: 404 Not Found")
            print("Content-Type: text/plain")
            print()
            print("Account not found")
            return
        if not os.path.isfile(integrity_checker.report_path(account_id)):
            print("Status: 404 Not Found")
            print("Content-Type: text/plain")
            print()
            print("No completed integrity report")
            return
        sys.stdout.buffer.write(b"Content-Type: application/x-ndjson\r\n")
        sys.stdout.buffer.write(
            b'Content-Disposition: attachment; filename="iCloudPhotoSync-integrity-report.jsonl"\r\n')
        sys.stdout.buffer.write(b"Cache-Control: private, no-store\r\n\r\n")
        integrity_report.stream_report_jsonl(account_id, sys.stdout.buffer)
        return

    params = cgi.FieldStorage()

    # POST requests put params (incl. method) in the body, not QUERY_STRING.
    if not method:
        method = params.getvalue("method", "") or ""

    handler = HANDLERS.get(method)

    if not handler:
        respond(False, error={"code": 100, "message": "Unknown method: %s" % method})
        return

    try:
        result = handler(params)
        respond(**result)
    except Exception as e:
        # The album handler wires the root logger to album.log on import;
        # without this the error only reached the browser (#68).
        import logging
        logging.getLogger("api").exception("Unhandled error in method %r", method)
        respond(False, error={"code": 500, "message": str(e)})


if __name__ == "__main__":
    main()
