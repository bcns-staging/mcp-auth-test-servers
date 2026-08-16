# mcp-auth-test-servers

Four minimal, throwaway MCP servers, each implementing exactly one authentication
mechanism, for testing an MCP client/platform's support for that auth type end to
end. None of these do anything useful once connected -- each exposes a single
`ping()` tool that returns `"pong"`, just enough to confirm the connection and auth
actually worked.

| Server | Auth mechanism | Deployed as |
|---|---|---|
| `basic-auth/` | HTTP Basic Auth (`Authorization: Basic base64(user:pass)`) | `mcp-test-basic-auth` and `mcp-test-username-password` (same code, two deployments -- see below) |
| `api-key/` | Custom header (default `X-API-Key`) | `mcp-test-api-key` |
| `oauth2/` | OAuth 2.0 authorization-code flow, with `/oauth/authorize`, `/oauth/token`, and `.well-known/oauth-authorization-server` discovery | `mcp-test-oauth2` |

## Why `basic-auth/` is deployed twice

"Basic Auth" and "Username & Password" are, at the wire protocol level, the same
mechanism -- there's no other standard way to send a raw username+password pair on
every request without an initial login/session step. One codebase, deployed as two
separate Cloud Run services with independently-generated test credentials, gives
each dropdown option in a platform's auth-type picker its own clean URL to test
against without duplicating code that would only ever behave identically.

## OAuth 2.0 server: what it deliberately isn't

`oauth2/` implements a real authorization-code flow (issues single-use codes,
exchanges them for time-limited access tokens, validates those tokens on protected
routes) but is not a production-grade authorization server:

- `/oauth/authorize` auto-approves immediately -- no login or consent screen, since
  there's no real end-user here to prompt.
- `redirect_uri` is trusted as given by the caller, not checked against a
  pre-registered allowlist, so any platform can test against this server without
  us knowing its callback URL in advance.

Both are acceptable only because nothing behind the issued tokens is real or
sensitive -- this exists purely to prove a client's OAuth implementation works.

## Deploying

```
./deploy/deploy.sh
```

Deploys all 4 services to the same GCP project as mcp-fileserver/7-beacons
(`project-0abb08b6-4e60-4be0-8db`, `us-central1`). Generates test credentials on
first run and reuses them on subsequent runs (saved locally, gitignored, in
`deploy/.credentials/`) so re-running the script after a code change doesn't
rotate credentials you've already pasted into a platform. Prints every service's
URL and credentials at the end.

Requires `gcloud` authenticated against that project already (same account used
for mcp-fileserver).

## Local development

Each server is a standalone Python package:

```
cd basic-auth   # or api-key, or oauth2
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e . pytest
./.venv/Scripts/python.exe -m pytest -q
```
