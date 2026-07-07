# Changelog

All notable changes to the Forge extension are documented here.

## [0.1.0] — 2026-07-07

Initial release.

### Added
- **Codebase-aware chat** with local RAG: workspace indexing (ChromaDB + local embeddings), file-watcher incremental re-indexing, and relevant-code injection into every conversation, with a context badge showing files, chunks, and token counts.
- **Inline ghost-text completions** with 300ms debounce and fill-in-the-middle prompting.
- **Multi-provider model router**: Groq, Gemini, Cerebras, OpenRouter, NVIDIA, Anthropic, and local Ollama, with automatic fallback to the next free provider on rate limits and a model picker (`Forge: Switch model`).
- **One-click MCP manager**: install, start, and uninstall 10 popular MCP servers from a visual panel, with a key wizard for servers that need credentials, and automatic relaunch of installed servers on startup.
- **MCP tool calling in chat**: tools from running MCP servers are exposed to the model and executed transparently, with results rendered inline.
- **Budget mode and cost tracking**: daily USD cap with automatic free-model routing near the limit, plus real-time token and cost display in the status bar.
- **Secure key storage** in the OS keychain via VSCode SecretStorage (`Forge: Add AI provider`).
- **Explain this repo** command: generates a guided tour of the workspace (purpose, architecture, key modules, README outline) directly in chat.
- **First-install experience**: Python 3.11+ detection with fallback, guided one-click install of backend dependencies with streamed progress, and crash notifications with one-click backend restart via the Forge Backend output channel.
