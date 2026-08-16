#!/usr/bin/env bash
# Deploys all 4 MCP auth-test servers to Cloud Run in the same GCP project
# used by mcp-fileserver/7-beacons. Idempotent: safe to re-run after code
# changes (rebuilds + redeploys); reuses previously-generated test
# credentials instead of rotating them, same pattern as mcp-fileserver's own
# deploy.sh.
#
# These are throwaway test targets with nothing sensitive behind them, so
# this intentionally skips things mcp-fileserver's deploy.sh does for real
# production stakes: no dedicated per-service IAM/service accounts (default
# Compute SA is fine, since none of these touch any GCP resource beyond
# themselves), and generated credentials are kept in plain, retrievable text
# locally (not hashed) -- the whole point is pasting them into an external
# platform's auth config, not protecting something valuable.
set -euo pipefail

PROJECT_ID=project-0abb08b6-4e60-4be0-8db
PROJECT_NUMBER=751371770492
REGION=us-central1
AR_REPO=mcp-auth-test
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"
TAG="$(date +%Y%m%d%H%M%S)"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRED_DIR="${REPO_ROOT}/deploy/.credentials"
mkdir -p "$CRED_DIR"

COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "== 1/7: enabling required APIs =="
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  --project="$PROJECT_ID"

echo "== 2/7: Artifact Registry repo (shared by all 4 images) =="
if ! gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker --location="$REGION" --project="$PROJECT_ID" \
    --description="Throwaway MCP servers for testing an MCP client's auth flows"
else
  echo "Artifact Registry repo already exists, skipping"
fi

echo "== 3/7: grant the default Compute SA push access to this Artifact Registry repo =="
# gcloud builds submit runs as the default Compute Engine SA in this
# project, and Artifact Registry push access is granted per-repo -- the
# equivalent grant on mcp-fileserver's own AR repo doesn't carry over to
# this new one. Project-level grants (Cloud Build's source-staging bucket
# read, logging.logWriter) mcp-fileserver's deploy.sh already set up DO
# carry over, since those aren't scoped to a specific repo.
gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" \
  --location="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_SA}" --role="roles/artifactregistry.writer"

# generate_if_missing NAME VAR1 [VAR2 ...]: writes deploy/.credentials/NAME
# with each VAR set to a fresh random value, unless that file already
# exists (then it's sourced as-is, so re-running this script doesn't
# silently rotate credentials someone's already pasted into a platform).
generate_if_missing() {
  local name="$1"; shift
  local file="${CRED_DIR}/${name}"
  if [ ! -f "$file" ]; then
    : > "$file"
    for var in "$@"; do
      printf '%s=%s\n' "$var" "$(openssl rand -hex 12)" >> "$file"
    done
    echo "  Generated new credentials: ${file}"
  else
    echo "  Reusing existing credentials: ${file}"
  fi
}

echo "== 4/7: generating test credentials (only once; re-run keeps existing ones) =="
generate_if_missing basic-auth TEST_USERNAME TEST_PASSWORD
generate_if_missing username-password TEST_USERNAME TEST_PASSWORD
generate_if_missing api-key TEST_API_KEY
generate_if_missing oauth2 TEST_CLIENT_ID TEST_CLIENT_SECRET

# shellcheck disable=SC1090
source "${CRED_DIR}/basic-auth"
BASIC_AUTH_USERNAME="$TEST_USERNAME"; BASIC_AUTH_PASSWORD="$TEST_PASSWORD"
# shellcheck disable=SC1090
source "${CRED_DIR}/username-password"
USERNAME_PASSWORD_USERNAME="$TEST_USERNAME"; USERNAME_PASSWORD_PASSWORD="$TEST_PASSWORD"
# shellcheck disable=SC1090
source "${CRED_DIR}/api-key"
API_KEY_VALUE="$TEST_API_KEY"
# shellcheck disable=SC1090
source "${CRED_DIR}/oauth2"
OAUTH2_CLIENT_ID="$TEST_CLIENT_ID"; OAUTH2_CLIENT_SECRET="$TEST_CLIENT_SECRET"

echo "== 5/7: build + push all 4 images via Cloud Build =="
gcloud builds submit --project="$PROJECT_ID" --tag="${IMAGE_BASE}/basic-auth-server:${TAG}" "${REPO_ROOT}/basic-auth"
gcloud builds submit --project="$PROJECT_ID" --tag="${IMAGE_BASE}/api-key-server:${TAG}" "${REPO_ROOT}/api-key"
gcloud builds submit --project="$PROJECT_ID" --tag="${IMAGE_BASE}/oauth2-server:${TAG}" "${REPO_ROOT}/oauth2"

echo "== 6/7: deploy to Cloud Run =="
# --allow-unauthenticated on all four: Cloud Run's own IAM layer stays open,
# same as mcp-fileserver -- the actual auth enforcement is each app's own
# middleware, which is the entire thing being tested here.
gcloud run deploy mcp-test-basic-auth \
  --image="${IMAGE_BASE}/basic-auth-server:${TAG}" \
  --region="$REGION" --platform=managed --project="$PROJECT_ID" \
  --allow-unauthenticated --port=8080 \
  --set-env-vars="TEST_USERNAME=${BASIC_AUTH_USERNAME},TEST_PASSWORD=${BASIC_AUTH_PASSWORD}" \
  --quiet

gcloud run deploy mcp-test-username-password \
  --image="${IMAGE_BASE}/basic-auth-server:${TAG}" \
  --region="$REGION" --platform=managed --project="$PROJECT_ID" \
  --allow-unauthenticated --port=8080 \
  --set-env-vars="TEST_USERNAME=${USERNAME_PASSWORD_USERNAME},TEST_PASSWORD=${USERNAME_PASSWORD_PASSWORD}" \
  --quiet

gcloud run deploy mcp-test-api-key \
  --image="${IMAGE_BASE}/api-key-server:${TAG}" \
  --region="$REGION" --platform=managed --project="$PROJECT_ID" \
  --allow-unauthenticated --port=8080 \
  --set-env-vars="TEST_API_KEY=${API_KEY_VALUE},API_KEY_HEADER_NAME=X-API-Key" \
  --quiet

# --max-instances=1: the OAuth2 server keeps issued auth codes/access tokens
# in this process's memory (see oauth.py) -- a second instance wouldn't see
# tokens issued by the first, breaking the /oauth/authorize -> /oauth/token
# -> protected-route round trip whenever a request landed on a different
# instance than the one that issued the token. Same reasoning mcp-fileserver
# applies to its own session store.
gcloud run deploy mcp-test-oauth2 \
  --image="${IMAGE_BASE}/oauth2-server:${TAG}" \
  --region="$REGION" --platform=managed --project="$PROJECT_ID" \
  --allow-unauthenticated --port=8080 --max-instances=1 \
  --set-env-vars="TEST_CLIENT_ID=${OAUTH2_CLIENT_ID},TEST_CLIENT_SECRET=${OAUTH2_CLIENT_SECRET}" \
  --quiet

echo "== 7/7: done -- service URLs and test credentials below =="
echo ""

BASIC_AUTH_URL="$(gcloud run services describe mcp-test-basic-auth --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
USERNAME_PASSWORD_URL="$(gcloud run services describe mcp-test-username-password --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
API_KEY_URL="$(gcloud run services describe mcp-test-api-key --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
OAUTH2_URL="$(gcloud run services describe mcp-test-oauth2 --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"

cat <<EOF
--- Basic Auth ---
Server URL:  ${BASIC_AUTH_URL}/sse
Email/Username: ${BASIC_AUTH_USERNAME}
API Token/Password: ${BASIC_AUTH_PASSWORD}

--- Username & Password ---
Server URL:  ${USERNAME_PASSWORD_URL}/sse
Username: ${USERNAME_PASSWORD_USERNAME}
Password: ${USERNAME_PASSWORD_PASSWORD}

--- API Key ---
Server URL:  ${API_KEY_URL}/sse
Header Name: X-API-Key
API Key:     ${API_KEY_VALUE}

--- OAuth 2.0 ---
Server URL:        ${OAUTH2_URL}/sse
Client ID:          ${OAUTH2_CLIENT_ID}
Client Secret:       ${OAUTH2_CLIENT_SECRET}
Authorization URL:  ${OAUTH2_URL}/oauth/authorize
Token URL:           ${OAUTH2_URL}/oauth/token
(or let your platform auto-detect both via ${OAUTH2_URL}/.well-known/oauth-authorization-server)

All credentials are also saved locally in deploy/.credentials/ (gitignored) --
re-running this script reuses them instead of rotating.
EOF
