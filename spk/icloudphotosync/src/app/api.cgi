#!/bin/sh
# DSM's web server starts this CGI without using the package service's Python.
# Do not rely on /usr/bin/env python3: it may resolve Python 3.8/3.9 or 3.13.
# Use an installed compatible interpreter and let the original Python CGI
# authenticate the DSM session; this launcher never bypasses auth.
PKG_TARGET="/var/packages/iCloudPhotoSync/target"
MAIN="$PKG_TARGET/app/api_main.py"

for PYTHON in \
    "$PKG_TARGET/env/bin/python3" \
    /var/packages/python311/target/bin/python3 \
    /usr/bin/python3.11 \
    /usr/local/bin/python3.11 \
    /var/packages/python3/target/usr/bin/python3 \
    /usr/bin/python3.12 \
    /usr/bin/python3.10 \
    /usr/local/bin/python3 \
    /usr/bin/python3 \
    /var/packages/py3k/target/usr/bin/python3
do
    [ -x "$PYTHON" ] || continue
    if "$PYTHON" -c 'import sys, cgi; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)' >/dev/null 2>&1; then
        exec "$PYTHON" "$MAIN"
    fi
done

# Fail visibly if the NAS has no compatible Python interpreter.
printf 'Status: 503 Service Unavailable\r\n'
printf 'Content-Type: application/json\r\n'
printf 'Cache-Control: no-store\r\n\r\n'
printf '%s\n' '{"success":false,"error":{"code":503,"message":"Compatible Python 3.10-3.12 missing (Python 3.11 recommended)."}}'
exit 0
