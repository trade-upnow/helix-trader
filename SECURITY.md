# Security Policy

## Secrets

Never commit or publish:

- Exchange API keys / secrets / passphrases
- JWT secrets or access tokens
- `backend/.env` contents
- Account screenshots or IP whitelist details

Use `backend/.env.example` as a template. Copy to `backend/.env` locally and keep it private.

## Agent / MCP usage

- Prefer environment variables or local interactive input for credentials.
- Do not paste secrets into public chats, issues, listings, or any public page.
- Tooling only reports whether sensitive env vars are present; it must not echo values.
- Default to testnet. Live trading requires both `HELIX_ALLOW_LIVE_TRADING=true` and explicit confirmation.

## Reporting

If you discover a vulnerability, report privately to the maintainers. Do not include live credentials in the report.
