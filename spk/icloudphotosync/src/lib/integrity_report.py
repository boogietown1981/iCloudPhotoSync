"""Non-mutating integrity repair previews and downloadable findings."""
import json
import os

import config_manager
import integrity_checker

_MAX_PAGE = 100


def iter_findings(account_id):
    """Stream individual findings from the most recent completed scan."""
    path = integrity_checker.report_path(account_id)
    with open(path, "r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                try:
                    finding = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(finding, dict):
                    yield finding


def report_page(account_id, offset=0, limit=25):
    """Read-only preview; never enqueue, erase or overwrite photo files."""
    if offset < 0:
        offset = 0
    limit = max(1, min(_MAX_PAGE, int(limit)))
    state = integrity_checker.status(account_id)
    if not os.path.isfile(integrity_checker.report_path(account_id)):
        return {
            "available": False, "findings": [], "offset": offset,
            "total": 0, "message": "Complete an integrity scan first"
        }
    results = []
    try:
        for i, item in enumerate(iter_findings(account_id)):
            if i >= offset and len(results) < limit:
                results.append(item)
            if i >= offset + limit:
                break
    except OSError:
        return {"available": False, "findings": [], "total": 0,
                "message": "Report not readable"}
    return {
        "available": True,
        "findings": results,
        "offset": offset,
        "total": state.get("report_issue_count", 0),
        "generated_at": state.get("report_at", 0),
        # The report could come from a prior scan if a new scan stopped.
        "status": state.get("status", "unknown"),
        "stale": state.get("status") in ("running", "starting", "stopped",
                                         "interrupted", "error", "busy")
    }


def stream_report_jsonl(account_id, output):
    """Export the complete report with a minimal, credential-free header.

    Filename paths are relative to the configured target. No Apple ID,
    credentials, signed URLs, cookie values or account UUID are exported.
    """
    state = integrity_checker.status(account_id)
    head = {"type": "integrity-summary", "generated_at": state.get("report_at", 0),
            "findings": state.get("report_issue_count", 0),
            "report_version": 1}
    output.write((json.dumps(head, ensure_ascii=False) + "\n").encode("utf-8"))
    for finding in iter_findings(account_id):
        output.write((json.dumps(finding, ensure_ascii=False) + "\n").encode("utf-8"))
