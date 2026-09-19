#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_step() {
  printf "\n==> %s\n" "$*"
  "$@"
}

echo "pyMC_Glass easy start"

run_step make -C "$ROOT_DIR" init-env
run_step make -C "$ROOT_DIR" init-prod-env
run_step make -C "$ROOT_DIR" dev-up

echo
echo "Waiting for backend health at http://localhost:8080/healthz ..."
for _ in $(seq 1 45); do
  if curl -fsS "http://localhost:8080/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if curl -fsS "http://localhost:8080/healthz" >/dev/null 2>&1; then
  echo "Backend is healthy."
else
  echo "Backend health endpoint is not ready yet. You can watch logs with:"
  echo "  make -C \"$ROOT_DIR\" dev-logs"
fi

if command -v git-cliff >/dev/null 2>&1; then
  if git -C "$ROOT_DIR" rev-parse --verify HEAD >/dev/null 2>&1; then
    run_step make -C "$ROOT_DIR" changelog
  else
    echo "Skipping changelog generation (no commits yet)."
  fi
else
  echo "Skipping changelog generation (git-cliff not installed)."
  echo "Install with: brew install git-cliff"
fi

cat <<'EOF'

Done.
Open:
  Frontend: http://localhost:5173
  Backend health: http://localhost:8080/healthz

Default login:
  Email: admin@pymc.glass
  Password: admin12345678
EOF
