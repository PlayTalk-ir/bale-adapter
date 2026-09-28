#!/usr/bin/env bash
# Print suggested BALE_ADAPTER_API_TOKENS and BALE_PHONE_PEPPER for .env.secrets
set -euo pipefail
echo "# Paste into .env.secrets (comma-separate multiple API tokens if rotating):"
echo "BALE_ADAPTER_API_TOKENS=$(openssl rand -hex 32)"
echo "BALE_PHONE_PEPPER=$(openssl rand -hex 32)"
