#!/usr/bin/env bash
# Run pi with speech input via ppi.py and the project venv.
#
# Resolves symlinks, so it can be linked anywhere (e.g. into /usr/local/bin
# as `ppi`).
set -euo pipefail

script_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_dir="$(dirname -- "$script_path")"

python_bin="${script_dir}/.venv/bin/python"
ppi_py="${script_dir}/ppi.py"

if [[ ! -x "$python_bin" ]]; then
    printf 'ppi: venv python not found at %s\nrun "uv sync" first\n' "$python_bin" >&2
    exit 1
fi

exec "$python_bin" "$ppi_py" "$@"
