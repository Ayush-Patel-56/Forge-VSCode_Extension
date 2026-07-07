# Forge — Zero-config AI Coding

**Paste a key, pick a model, and chat with your codebase — in under 60 seconds, completely free.**

Forge turns VSCode into a full AI coding environment: codebase-aware chat, inline ghost-text completions, one-click MCP tool installs, and a multi-provider model router that keeps you on free tiers by default. Everything runs locally on your machine.

## Features

- **Chat with your codebase** — Forge indexes your workspace locally (ChromaDB + local embeddings) and injects the most relevant code into every conversation. Ask "where is the auth logic?" and get answers grounded in *your* files.
- **Inline completions** — ghost-text suggestions appear as you type, powered by fast free-tier models. Tab to accept, Escape to dismiss.
- **One-click MCP installs with tool calling** — install any of 10 popular MCP servers (GitHub, Filesystem, Brave Search, Puppeteer, and more) from a visual panel, no JSON editing. Installed MCP tools are callable directly from chat: ask Forge to search the web or read a file and it uses the running server.
- **Multi-provider model router** — bring your own key for Groq, Gemini, Cerebras, OpenRouter, NVIDIA, Anthropic, or run fully offline with Ollama. Rate-limited? Forge automatically falls back to the next available free provider.
- **Budget mode** — set a daily spend cap and Forge auto-routes to free models as you approach it.
- **Real-time cost tracker** — live token and dollar usage in the status bar and chat, per model.
- **Secure key storage** — API keys live in your OS keychain (via VSCode SecretStorage), never in settings files or on disk in plain text.
- **Explain this repo** — one command generates a guided tour of any repository: purpose, architecture, key modules, and a suggested README outline.

## Quick start

1. Install Forge from the Marketplace.
2. Run **`Forge: Add AI provider`** from the Command Palette (`Ctrl+Shift+P`).
3. Pick **groq** and paste a free API key from [console.groq.com](https://console.groq.com) (takes ~30 seconds to create).
4. Open chat with **`Forge: Open chat`** (or click the Forge icon in the status bar) and start coding.

That's it. Forge indexes your workspace in the background and your chat becomes codebase-aware automatically.

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| VSCode | ≥ 1.85 | |
| Python | 3.11+ | Powers the local backend. Forge offers to install its Python dependencies on first run. |
| Node.js | 18+ | Only needed for `npx`-based MCP servers (ships with most dev setups). |
| `uv` / `uvx` | optional | Only needed for the Git MCP server. |

## Settings

| Setting | Default | Description |
|---|---|---|
| `forge.pythonPath` | `python3` | Path to a Python 3.11+ executable. Forge falls back to `python` automatically. |
| `forge.defaultModel` | `groq/llama-3.3-70b-versatile` | Default model ID used for chat and completions. |
| `forge.dailyBudgetUsd` | `0` | Daily spend cap in USD. `0` = unlimited. Near the cap, Forge auto-routes to free models. |
| `forge.telemetry` | `false` | Anonymous usage telemetry. **Off by default** — nothing is sent unless you opt in. |
| `forge.completions.enabled` | `true` | Enable inline ghost-text completions. |
| `forge.indexing.enabled` | `true` | Enable local codebase indexing for context-aware chat. |

## One-click MCP servers

Install from the **Forge AI → MCPs** panel. Servers that need an API key show a short wizard; the rest install with a single click.

| MCP | What it does | Requires |
|---|---|---|
| Filesystem | Read and write local files | — |
| GitHub | Search repos, PRs, issues | GitHub token |
| Brave Search | Web search | Brave API key |
| Memory | Persistent AI memory across sessions | — |
| Puppeteer (Browser) | Control a browser, scrape pages | — |
| Git | Git operations on local repos | `uvx` |
| PostgreSQL | Query PostgreSQL databases | Connection URL |
| Slack | Read Slack channels and messages | Slack bot token |
| GitLab | GitLab projects, MRs, issues | GitLab token |
| Google Maps | Location search and directions | Maps API key |

Once a server is running, its tools are available in chat — Forge decides when to call them and shows you the results inline.

## Privacy

- **Everything runs locally.** The backend, the vector index, embeddings, and your chat history all live on your machine. The only network traffic is to the LLM provider you configured.
- **Keys stay in the OS keychain.** Forge uses VSCode's SecretStorage (Windows Credential Manager / macOS Keychain / libsecret).
- **Telemetry is off by default.** Zero data leaves your machine unless you explicitly opt in.
- **Fully offline option.** Point Forge at a local Ollama server and nothing ever leaves your machine.

## Troubleshooting

- **First startup takes a while (~25s or more).** On first run the backend downloads a local embedding model for codebase search. Subsequent startups are fast. Watch progress in the **Forge Backend** output channel (View → Output).
- **"Forge needs Python 3.11+"** — install Python 3.11 or newer and/or point `forge.pythonPath` at the right executable.
- **Backend dependencies missing** — Forge prompts to install them (~2GB including PyTorch). You can also run `python -m pip install -r <extension folder>/backend/requirements.txt` yourself.
- **Git MCP won't install** — it runs via `uvx`. Install [uv](https://docs.astral.sh/uv/) first, then retry.
- **Backend stopped unexpectedly** — check the **Forge Backend** output channel for the error, then click **Restart** in the notification.
- **No response in chat** — make sure you've added at least one provider key via `Forge: Add AI provider`.

## License

MIT
