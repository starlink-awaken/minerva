# Support

## Getting Help

### Documentation

- [README](README.md) — overview and quick start
- [Architecture](docs/ARCHITECTURE.md) — system design and component relationships
- [Design](docs/DESIGN.md) — design philosophy and decisions
- [TUI Guide](docs/TUI.md) — terminal interface usage
- [Changelog](CHANGELOG.md) — version history
- [Security Policy](SECURITY.md) — vulnerability reporting

### Common Issues

**Q: Ollama models not found?**
```bash
ollama pull qwen3.6:27b
minerva check  # verify setup
```

**Q: Port 8765 already in use?**
```bash
lsof -i :8765  # find the process
kill -9 <PID>  # or use a different port
MINERVA_PORT=8766 minerva web
```

**Q: LanceDB search returning empty results?**
The vector index may need initialization. Run a full L1+ research once or rebuild the index via `minerva maintenance`.

**Q: MCP tools not responding?**
Ensure the MCP server is running: `minerva mcp`. The server auto-initializes the executor on startup. If SQLite is unavailable, it falls back to degraded mode (knowledge_search + knowledge_ingest only).

### Supported Versions

| Version | Status |
|---------|--------|
| 0.10.x | Active support |
| < 0.10 | No longer supported |

### Reporting Security Issues

See [SECURITY.md](SECURITY.md). Do NOT open a public issue for security vulnerabilities.

### Feature Requests & Bug Reports

Open an issue on [GitHub Issues](https://github.com/minerva/minerva/issues) using the appropriate template.
