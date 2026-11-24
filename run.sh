#!/bin/sh
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m modbroom "$@"
fi
exec python3 -m modbroom "$@"
