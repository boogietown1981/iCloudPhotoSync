"""Account-scoped API for non-destructive integrity scanning."""
import os
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import config_manager
import integrity_checker


def handle(params):
    action = params.getvalue("action", "")
    account_id = params.getvalue("account_id", "").strip()
    if not account_id or not config_manager.get_account(account_id):
        return {"success": False, "error": {"code": 404, "message": "Account not found"}}
    if action == "status":
        return {"success": True, "data": integrity_checker.status(account_id)}
    if action == "stop":
        if not integrity_checker.is_running(account_id):
            return {"success": False, "error": {"code": 409, "message": "No active scan"}}
        with open(os.path.join(config_manager.get_account_dir(account_id),
                               ".stop_integrity"), "w") as f:
            f.write("stop")
        return {"success": True, "data": {"message": "Stop requested"}}
    if action == "start":
        if integrity_checker.is_running(account_id):
            return {"success": False, "error": {"code": 409, "message": "Scan running"}}
        from sync_engine import runner_alive
        if runner_alive(account_id):
            return {"success": False, "error": {"code": 409, "message": "Sync running"}}
        target = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        runner = os.path.join(target, "bin", "integrity_runner.py")
        log_path = os.path.join(config_manager.PKG_VAR, "logs", "integrity.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        try:
            with open(log_path, "a") as log:
                subprocess.Popen([sys.executable, runner, account_id], stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, start_new_session=True)
        except OSError as exc:
            return {"success": False, "error": {"code": 500, "message": str(exc)}}
        return {"success": True, "data": {"status": "starting"}}
    return {"success": False, "error": {"code": 101, "message": "Unknown action"}}
