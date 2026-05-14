# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please **do NOT open a public issue**.

Email the details to the maintainers. We will respond within 48 hours.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.10.x  | ✅ Active |
| < 0.10  | ❌ No longer supported |

## Security Design

Minerva follows these security principles:

- **Local-first**: All data stays on your machine by default. No telemetry.
- **API keys via env vars**: All credentials use `${ENV_VAR}` substitution. Never hardcoded.
- **Input validation**: Web API validates query size (≤2KB), body size (≤64KB).
- **Rate limiting**: 30 requests/minute/IP on research endpoints.
- **Optional API key auth**: Set `MINERVA_API_KEY` to enable endpoint protection.
- **Degraded mode**: If LLM is unavailable, knowledge search still works.

## Known Limitations

- Web endpoints are unauthenticated by default (localhost-only)
- MCP server has no built-in authentication
- Ollama is assumed to be on localhost without auth
