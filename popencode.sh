#!/usr/bin/env bash
# Run OpenCode with speech input via popencode.py and the project venv.
#
# Resolves symlinks, so it can be linked anywhere (e.g. into /usr/local/bin
# as `popencode`).
set -euo pipefail

script_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_dir="$(dirname -- "$script_path")"

python_bin="${script_dir}/.venv/bin/python"
popencode_py="${script_dir}/popencode.py"

if [[ ! -x "$python_bin" ]]; then
    printf 'popencode: venv python not found at %s\nrun "uv sync" first\n' "$python_bin" >&2
    exit 1
fi

exec "$python_bin" "$popencode_py" "$@"
