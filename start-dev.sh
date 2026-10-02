#!/usr/bin/env bash
# Start the Medusa backend (port 9000) with the required Node version.
set -e
cd "$(dirname "$0")"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use >/dev/null
pnpm --filter @dtc/backend dev
