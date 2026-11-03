#!/bin/sh
# Safe, read-only local NAS diagnostics for "connection to server failed".
# Does NOT print credentials, cookies, tokens, account JSON or private logs.
P="/var/packages/iCloudPhotoSync"
echo "== iCloudPhotoSync API diagnostics =="
date '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || true
if [ -f "$P/INFO" ]; then
    sed -n '/^version=/p' "$P/INFO"
else
    echo "Package INFO missing"
fi
if [ -e "$P/target/app/api.cgi" ]; then
    echo "API executable:"
    ls -l "$P/target/app/api.cgi"
    echo "API launcher first line:"
    head -n 1 "$P/target/app/api.cgi"
else
    echo "ERROR: API executable missing"
fi
if [ -f "$P/target/app/api_main.py" ]; then
    echo "Python API main: present"
else
    echo "Python API main: missing (expected on v1.9.2+)"
fi
if [ -d "$P/var" ]; then
    echo "Package var permissions:"
    ls -ld "$P/var" "$P/var/logs" 2>/dev/null
fi
for BIN in \
  /var/packages/python311/target/bin/python3 \
  /usr/bin/python3 \
  /usr/bin/python3.11 \
  /usr/bin/python3.12 \
  /usr/bin/python3.10 \
  /usr/local/bin/python3
do
  [ -x "$BIN" ] || continue
  printf "%s: " "$BIN"
  "$BIN" -c 'import sys;print(sys.version.split()[0])' 2>/dev/null || echo "not runnable"
done
for F in "$P/target/app/api.cgi" "$P/target/app/api_main.py"; do
  [ -f "$F" ] || continue
  case "$F" in *.py) : ;; *) continue ;; esac
  for BIN in /var/packages/python311/target/bin/python3 /usr/bin/python3.11 /usr/bin/python3; do
    [ -x "$BIN" ] || continue
    "$BIN" -c 'import ast,sys;ast.parse(open(sys.argv[1]).read())' "$F" >/dev/null 2>&1
    echo "Python main syntax with $BIN: $?"
  done
done
echo "== end of diagnostic; no configuration was modified =="
