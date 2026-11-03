#!/usr/bin/env python3
"""Background read-only integrity scanner."""
import logging
import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, os.path.join(ROOT, "lib", "vendor"))
import config_manager
import integrity_checker
log_dir = os.path.join(config_manager.PKG_VAR, "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(filename=os.path.join(log_dir, "integrity.log"),
                    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
if __name__ == "__main__":
    if len(sys.argv) != 2 or not config_manager.get_account(sys.argv[1]):
        sys.exit(2)
    result = integrity_checker.scan(sys.argv[1])
    logging.info("Scan status=%s checked=%s missing=%s changed=%s",
                 result["status"], result["checked"], result["missing"], result["changed"])
    sys.exit(0 if result["status"] in ("complete", "issues", "stopped") else 1)
