#!/bin/sh
# One image, two callers.
#
# The registry recipe passes the server argv as separate arguments
# ("/opt/llama/llama-server", "--model", ...), which is exec'd directly so the
# server keeps PID 1 and receives signals. The campaign's validation bootstrap
# passes a single shell string, which is handed to /bin/sh -c.
set -e

if [ "$#" -eq 0 ]; then
    exec /opt/llama/llama-server --help
fi

if [ "$#" -eq 1 ]; then
    exec /bin/sh -c "$1"
fi

exec "$@"