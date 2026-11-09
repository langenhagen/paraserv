#!/usr/bin/env bash
# Run Claude Code with speech input via pclaude.py and the project venv.
#
# Resolves symlinks, so it can be linked anywhere (e.g. into /usr/local/bin
# as `pclaude`).
set -euo pipefail

script_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_dir="$(dirname -- "$script_path")"

python_bin="${script_dir}/.venv/bin/python"
pclaude_py="${script_dir}/pclaude.py"

if [[ ! -x "$python_bin" ]]; then
    printf 'pclaude: venv python not found at %s\nrun "uv sync" first\n' "$python_bin" >&2
    exit 1
fi

exec "$python_bin" "$pclaude_py" "$@"
