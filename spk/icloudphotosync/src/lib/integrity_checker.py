"""Non-destructive local SHA-256 checks against a durable baseline.

First scan: establish a baseline for legacy files (not proof of iCloud content).
Subsequent scans: detect missing and changed files. Never delete user photos.
"""
import contextlib
import fcntl
import hashlib
import json
import logging
import os
import time
import tempfile

import config_manager
import sync_manifest

LOG = logging.getLogger("integrity")
_TABLE = """CREATE TABLE IF NOT EXISTS local_checksums (
    local_path TEXT PRIMARY KEY, byte_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL, checked_at INTEGER NOT NULL)"""


def _paths(account_id):
    root = config_manager.get_account_dir(account_id)
    return (os.path.join(root, "integrity_progress.json"),
            os.path.join(root, ".integrity.lock"),
            os.path.join(root, ".sync.lock"),
            os.path.join(root, ".stop_integrity"))


def report_path(account_id):
    """Complete issue inventory for the last fully finished audit."""
    return os.path.join(config_manager.get_account_dir(account_id),
                        "integrity_findings.jsonl")


def _save(account_id, state):
    config_manager.atomic_write_json(_paths(account_id)[0], state)


def is_running(account_id):
    fd = os.open(_paths(account_id)[1], os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def status(account_id):
    try:
        with open(_paths(account_id)[0]) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {"status": "idle"}
    if s.get("status") == "running" and not is_running(account_id):
        s["status"] = "interrupted"
    return s


@contextlib.contextmanager
def _exclusive_scan(account_id):
    """Take scan and synchronization locks to avoid hashing changing files."""
    fds = []
    try:
        for path in _paths(account_id)[1:3]:
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            fds.append(fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        for fd in reversed(fds):
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(fd)


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _within_target(path, target):
    try:
        return (os.path.isabs(path) and not os.path.islink(path) and
                os.path.commonpath([os.path.realpath(path), target]) == target)
    except (ValueError, OSError):
        return False


def scan(account_id):
    if not config_manager.get_account(account_id):
        return {"status": "error", "error": "Account not found"}
    os.makedirs(config_manager.get_account_dir(account_id), exist_ok=True)
    stop_file = _paths(account_id)[3]
    previous = status(account_id)
    state = {
        "status": "running", "started_at": int(time.time()), "finished_at": 0,
        "total": 0, "checked": 0, "verified": 0, "baselined": 0,
        "missing": 0, "changed": 0, "errors": 0, "bytes_read": 0,
        "samples": [], "error": "",
        "report_at": previous.get("report_at", 0),
        "report_issue_count": previous.get("report_issue_count", 0)
    }
    staged_path = None
    try:
        with _exclusive_scan(account_id):
            try:
                os.unlink(stop_file)
            except FileNotFoundError:
                pass
            _save(account_id, state)
            target = os.path.realpath(config_manager.get_sync_config(account_id).get(
                "target_dir", config_manager.DEFAULT_TARGET_DIR))
            conn = sync_manifest._connect(account_id)
            try:
                conn.execute(_TABLE)
                state["total"] = conn.execute(
                    "SELECT COUNT(DISTINCT local_path) FROM synced_photos "
                    "WHERE local_path IS NOT NULL AND local_path != ''").fetchone()[0]
                cursor = conn.execute(
                    "SELECT DISTINCT local_path FROM synced_photos "
                    "WHERE local_path IS NOT NULL AND local_path != '' ORDER BY local_path")
                # Stage a complete findings report. Publish it ONLY after a
                # fully successful scan; stopped/crashed runs keep the last
                # good report for post-mortem inspection.
                with tempfile.NamedTemporaryFile(
                        mode="w", encoding="utf-8", dir=root, prefix=".integrity-",
                        suffix=".jsonl.tmp", delete=False) as staged:
                    staged_path = staged.name
                cache = {}
                last_save = 0.0
                with open(staged_path, "w", encoding="utf-8") as report:
                    for row in cursor:
                        if os.path.exists(stop_file):
                            state["status"] = "stopped"
                            break
                        path = row[0]
                        state["checked"] += 1
                        issue = None
                        try:
                            if not _within_target(path, target):
                                state["errors"] += 1
                                issue = "outside target or symlink"
                            elif not os.path.isfile(path):
                                state["missing"] += 1
                                issue = "missing"
                            else:
                                before = os.stat(path)
                                known = conn.execute(
                                    "SELECT byte_size, sha256 FROM local_checksums "
                                    "WHERE local_path=?", (path,)).fetchone()
                                if known and before.st_size != known["byte_size"]:
                                    state["changed"] += 1
                                    issue = "size differs"
                                else:
                                    key = (before.st_dev, before.st_ino, before.st_size,
                                           before.st_mtime_ns)
                                    digest = cache.get(key)
                                    if digest is None:
                                        digest = _digest(path)
                                        state["bytes_read"] += before.st_size
                                        if len(cache) < 8192:
                                            cache[key] = digest
                                    after = os.stat(path)
                                    if (before.st_size, before.st_mtime_ns) != (
                                            after.st_size, after.st_mtime_ns):
                                        state["errors"] += 1
                                        issue = "modified while auditing"
                                    elif known:
                                        if digest == known["sha256"]:
                                            state["verified"] += 1
                                        else:
                                            state["changed"] += 1
                                            issue = "SHA-256 differs"
                                    else:
                                        conn.execute(
                                            "INSERT OR IGNORE INTO local_checksums "
                                            "(local_path,byte_size,sha256,checked_at) "
                                            "VALUES(?,?,?,?)",
                                            (path, before.st_size, digest, int(time.time())))
                                        state["baselined"] += 1
                        except OSError as exc:
                            state["errors"] += 1
                            issue = "I/O: " + type(exc).__name__
                        if issue:
                            kind = ("missing" if issue == "missing"
                                    else "changed" if issue in ("size differs", "SHA-256 differs")
                                    else "unsafe" if issue == "outside target or symlink"
                                    else "error")
                            # Never export arbitrary locations outside the
                            # configured photo root, even for crafted manifest rows.
                            safe_path = (os.path.relpath(path, target)
                                         if kind != "unsafe" else "[outside target]")
                            finding = {
                                "path": safe_path, "kind": kind, "detail": issue,
                                "suggested_action": (
                                    "review_and_redownload_from_icloud"
                                    if kind in ("missing", "changed")
                                    else "manual_review")
                            }
                            report.write(json.dumps(finding, ensure_ascii=False) + "\n")
                            if len(state["samples"]) < 25:
                                state["samples"].append(finding)
                        if state["checked"] % 100 == 0:
                            conn.commit()
                        if time.monotonic() - last_save > 1.5:
                            _save(account_id, state)
                            last_save = time.monotonic()

                    # Persist checksum baselines before publishing the report.
                    conn.commit()
                    if state["status"] == "running":
                        report.flush()
                        os.fsync(report.fileno())
                        os.replace(staged_path, report_path(account_id))
                        staged_path = None
                        state["report_at"] = int(time.time())
                        state["report_issue_count"] = (
                            state["missing"] + state["changed"] + state["errors"])
                conn.commit()
            finally:
                conn.close()
            if state["status"] == "running":
                state["status"] = ("issues" if
                    (state["missing"] or state["changed"] or state["errors"])
                    else "complete")
    except BlockingIOError:
        state["status"] = "busy"
        state["error"] = "Synchronization or integrity scan already running"
    except Exception as exc:
        LOG.exception("Integrity scan failed for account %s", account_id)
        state["status"] = "error"
        state["error"] = type(exc).__name__ + ": " + str(exc)
    if staged_path:
        try:
            os.unlink(staged_path)
        except OSError:
            pass
    state["finished_at"] = int(time.time())
    if state["status"] != "busy":
        _save(account_id, state)
    return state
