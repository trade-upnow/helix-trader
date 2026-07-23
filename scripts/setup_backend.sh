#!/usr/bin/env bash
# One-shot local backend bootstrap for Helix Trader.
# Creates .venv, installs dependencies, and copies .env.example -> .env when missing.
# Network: try OKX direct → configured proxy → default 7890; use working proxy for pip.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
DEFAULT_PROXY="http://127.0.0.1:7890"
OKX_PROBE_URL="https://www.okx.com/api/v5/public/time"
# Newer ccxt / deps often break on macOS system python3 (= 3.9). Prefer 3.12.
MIN_PY_MAJOR=3
MIN_PY_MINOR=10
INSTALL_PROXY=""
OKX_PROBE_UA=""
PYTHON_BIN=""

cd "${BACKEND_DIR}"

python_version_ok() {
  local bin="$1"
  "${bin}" -c "import sys; raise SystemExit(0 if sys.version_info >= (${MIN_PY_MAJOR}, ${MIN_PY_MINOR}) else 1)" 2>/dev/null
}

resolve_python() {
  local candidate
  # Prefer explicit modern interpreters; never blindly trust macOS /usr/bin/python3 (often 3.9).
  for candidate in \
    "${HELIX_PYTHON:-}" \
    python3.12 \
    python3.11 \
    python3.10 \
    python3
  do
    [[ -z "${candidate}" ]] && continue
    if ! command -v "${candidate}" >/dev/null 2>&1; then
      continue
    fi
    candidate="$(command -v "${candidate}")"
    if python_version_ok "${candidate}"; then
      PYTHON_BIN="${candidate}"
      return 0
    fi
    echo "[setup] Skipping ${candidate} (need Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR}; got $("${candidate}" -c 'import sys; print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo unknown))"
  done
  echo "[setup] ERROR: need Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR} (recommend 3.12)." >&2
  echo "[setup] macOS system python3 is often 3.9 and may fail installing ccxt/deps." >&2
  echo "[setup] Install e.g. Homebrew python@3.12, then re-run:" >&2
  echo "[setup]   brew install python@3.12" >&2
  echo "[setup]   HELIX_PYTHON=python3.12 bash scripts/setup_backend.sh" >&2
  echo "[setup]   # or: python3.12 -m venv backend/.venv" >&2
  return 1
}

read_env_proxy() {
  local env_file="${BACKEND_DIR}/.env"
  if [[ ! -f "${env_file}" ]]; then
    return 0
  fi
  # shellcheck disable=SC1090
  set -a
  eval "$(grep -E '^(EXCHANGE_PROXY_URL|EXCHANGE_HTTPS_PROXY|EXCHANGE_HTTP_PROXY|HTTPS_PROXY|HTTP_PROXY|https_proxy|http_proxy)=' "${env_file}" 2>/dev/null || true)"
  set +a
}

load_okx_probe_ua() {
  # Same User-Agent as doctor/ccxt probes — never urllib/curl defaults (Cloudflare 1010).
  OKX_PROBE_UA="$(python -c 'from app.agent.okx_probe import okx_probe_user_agent; print(okx_probe_user_agent())')"
}

probe_okx() {
  local proxy="${1:-}"
  if [[ -z "${OKX_PROBE_UA}" ]]; then
    echo "[setup] ERROR: OKX probe User-Agent not loaded" >&2
    return 1
  fi
  if command -v curl >/dev/null 2>&1; then
    if [[ -n "${proxy}" ]]; then
      curl -fsS --max-time 5 -x "${proxy}" -A "${OKX_PROBE_UA}" -H "Accept: application/json" "${OKX_PROBE_URL}" >/dev/null 2>&1
    else
      curl -fsS --max-time 5 -A "${OKX_PROBE_UA}" -H "Accept: application/json" "${OKX_PROBE_URL}" >/dev/null 2>&1
    fi
    return $?
  fi
  PROXY_FOR_PY="${proxy}" OKX_PROBE_URL="${OKX_PROBE_URL}" python - <<'PY'
import os
import urllib.request
from app.agent.okx_probe import okx_probe_request_headers

proxy = os.environ.get("PROXY_FOR_PY") or ""
url = os.environ["OKX_PROBE_URL"]
headers = okx_probe_request_headers()
req = urllib.request.Request(url, headers=headers)
if proxy:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener.open(req, timeout=5).read()
else:
    urllib.request.urlopen(req, timeout=5).read()
PY
}

resolve_install_proxy() {
  read_env_proxy
  local candidate="${EXCHANGE_HTTPS_PROXY:-${EXCHANGE_PROXY_URL:-${EXCHANGE_HTTP_PROXY:-${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}}}}"

  echo "[setup] Checking OKX connectivity to decide whether pip needs a proxy..."
  if probe_okx ""; then
    echo "[setup] Direct OKX access works — installing without proxy."
    INSTALL_PROXY=""
    return 0
  fi

  if [[ -n "${candidate}" ]] && probe_okx "${candidate}"; then
    echo "[setup] Using configured proxy for installs: ${candidate}"
    INSTALL_PROXY="${candidate}"
    return 0
  fi

  if [[ "${candidate}" != "${DEFAULT_PROXY}" ]] && probe_okx "${DEFAULT_PROXY}"; then
    echo "[setup] Direct failed; default proxy ${DEFAULT_PROXY} works — using it for installs."
    INSTALL_PROXY="${DEFAULT_PROXY}"
    return 0
  fi

  echo "[setup] WARNING: cannot reach www.okx.com (direct or ${DEFAULT_PROXY})."
  echo "[setup] If dependency download fails, provide a proxy and re-run, e.g.:"
  echo "[setup]   export EXCHANGE_PROXY_URL=http://127.0.0.1:PORT"
  echo "[setup]   bash scripts/setup_backend.sh"
  INSTALL_PROXY="${candidate}"
}

ensure_proxy_in_env() {
  local proxy="$1"
  [[ -z "${proxy}" || ! -f .env ]] && return 0
  if grep -qE '^EXCHANGE_PROXY_URL=.+' .env; then
    return 0
  fi
  if grep -qE '^EXCHANGE_PROXY_URL=' .env; then
    sed -i.bak "s|^EXCHANGE_PROXY_URL=.*|EXCHANGE_PROXY_URL=${proxy}|" .env
    rm -f .env.bak
  else
    echo "EXCHANGE_PROXY_URL=${proxy}" >> .env
  fi
  echo "[setup] Wrote EXCHANGE_PROXY_URL=${proxy} into backend/.env"
}

resolve_python
echo "[setup] Using Python: ${PYTHON_BIN} ($("${PYTHON_BIN}" -c 'import sys; print("%d.%d.%d"%sys.version_info[:3])'))"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  if ! python_version_ok .venv/bin/python; then
    echo "[setup] ERROR: existing backend/.venv is too old (need >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR})." >&2
    echo "[setup] Recreate with: rm -rf backend/.venv && HELIX_PYTHON=python3.12 bash scripts/setup_backend.sh" >&2
    exit 1
  fi
  echo "[setup] Local Python environment already present."
else
  echo "[setup] Preparing local Python environment (needed for OKX probe headers)..."
  "${PYTHON_BIN}" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
load_okx_probe_ua

resolve_install_proxy

# Avoid empty-array expansion under macOS bash 3.2 + set -u ("unbound variable").
echo "[setup] Installing backend requirements"
if [[ -n "${INSTALL_PROXY}" ]]; then
  export http_proxy="${INSTALL_PROXY}"
  export https_proxy="${INSTALL_PROXY}"
  export HTTP_PROXY="${INSTALL_PROXY}"
  export HTTPS_PROXY="${INSTALL_PROXY}"
  python -m pip install --upgrade pip --proxy "${INSTALL_PROXY}"
  pip install --proxy "${INSTALL_PROXY}" -r requirements.txt
else
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY || true
  python -m pip install --upgrade pip
  pip install -r requirements.txt
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[setup] Created backend/.env from example (edit secrets locally; do not commit)"
fi

ensure_proxy_in_env "${INSTALL_PROXY}"

echo
echo "[setup] Done."
echo "Agent next: start API, save exchange credentials, then offer optional local web UI."
echo
