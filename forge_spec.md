# Forge IDE — VSCode Extension
## Complete Technical Specification & Build Guide

> **Purpose of this doc:** This is the single source of truth for building the Forge VSCode extension. Read every section before writing any code. Follow the build order in Section 19 exactly. Do not invent architecture — use what is specified here.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Goals & Success Metrics](#3-goals--success-metrics)
4. [User Personas & Stories](#4-user-personas--stories)
5. [MVP Scope](#5-mvp-scope)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [Tech Stack](#7-tech-stack)
8. [Architecture — HLD (Three-Process Model)](#8-architecture--hld)
9. [Extension Host — LLD](#9-extension-host--lld)
10. [Webview Layer — LLD](#10-webview-layer--lld)
11. [Python Backend — LLD](#11-python-backend--lld)
12. [IPC Message Protocol](#12-ipc-message-protocol)
13. [REST API Contract](#13-rest-api-contract)
14. [Database Schema](#14-database-schema)
15. [Model Router (Complete)](#15-model-router-complete)
16. [Context Engine — RAG Pipeline](#16-context-engine--rag-pipeline)
17. [MCP Manager (Complete)](#17-mcp-manager-complete)
18. [Key Vault Design](#18-key-vault-design)
19. [Complete Folder Structure](#19-complete-folder-structure)
20. [Complete Code — Extension Host](#20-complete-code--extension-host)
21. [Complete Code — Python Backend](#21-complete-code--python-backend)
22. [Complete Code — React Webviews](#22-complete-code--react-webviews)
23. [Package.json — Complete Manifest](#23-packagejson--complete-manifest)
24. [Build Order & Phases](#24-build-order--phases)
25. [Free Tier Strategy](#25-free-tier-strategy)
26. [Provider Configuration Reference](#26-provider-configuration-reference)
27. [Testing Checklist](#27-testing-checklist)

---

## 1. Project Overview

**Name:** Forge IDE  
**Type:** VSCode Extension + local Python backend service  
**Tagline:** Zero-config AI coding. Paste key, pick model, start coding.  
**Core promise:** A developer should be able to install Forge and have a fully working AI coding assistant — with MCP tools, inline completions, and codebase awareness — in under 60 seconds, completely free.

### What makes Forge different from Cursor, Windsurf, Kiro

| Feature | Cursor | Windsurf | Kiro | **Forge** |
|---|---|---|---|---|
| MCP setup | Manual JSON | Manual | Manual | **One click** |
| Free tier | Limited | Limited | AWS-tied | **Forever free (free APIs)** |
| Bring your own key | Partial | No | No | **Yes — all providers** |
| Provider switching | Claude/GPT only | Fixed | AWS only | **Groq, Gemini, NVIDIA, OpenRouter, Ollama** |
| Budget mode | No | No | No | **Yes — auto-route to free** |
| Student/OSS free | No | No | No | **Yes — permanent** |
| Cost tracker | No | No | No | **Status bar, real-time** |
| Learning mode | No | No | No | **Yes — explains changes** |

---

## 2. Problem Statement

**Primary pain:** MCP setup requires reading 3 separate docs, editing JSON config files manually, managing environment variables, and debugging silent failures with zero error messages. Most developers give up before they finish.

**Secondary pain:** Using free LLM providers (Groq, Cerebras, NVIDIA NIM, OpenRouter free tier) with AI coding tools requires manual configuration that most developers cannot figure out. Every provider has different auth formats, base URLs, and model naming conventions.

**Cost pain:** Cursor costs $20/month before writing a line of code. For Indian students and solo devs, this is a non-starter.

**Result:** Most developers either overpay for Cursor, spend hours configuring tools that still half-work, or give up on AI-assisted coding entirely.

---

## 3. Goals & Success Metrics

### Phase 1 Goals (VSCode Extension)

| Metric | Target | Measurement |
|---|---|---|
| VSCode Marketplace installs (month 1) | 500 | Marketplace analytics |
| MCP setup completion rate | >60% | Local telemetry (opt-in) |
| First-token latency (Groq path, p95) | <800ms | Backend timing logs |
| Daily active users (month 2) | 200 | Extension activation events |
| GitHub stars | 100 | GitHub API |
| Zero server cost | $0/month | No cloud infra needed |

### Definition of success (month 3)
A BTech student with a Groq API key should be able to: install extension → paste key → ask "explain this function" → get a streaming response in their codebase — all within 90 seconds of first install.

---

## 4. User Personas & Stories

### Persona 1: Ayush (target user)
BTech CS student, has free API keys from Groq/Gemini, uses VSCode, builds open source projects, cannot afford Cursor.

### Persona 2: Indie dev
Solo developer building a SaaS, has paid for Cursor but wants flexibility to use cheaper models for routine tasks and expensive models only for complex work.

### Persona 3: OSS maintainer
Maintains a GitHub project with contributors, wants AI context shared across the team without everyone paying individually.

### User Stories (MVP — must ship in v1)

| ID | Story | Acceptance criteria |
|---|---|---|
| US-1 | As a dev, I want to paste my Groq API key and immediately chat with my codebase | Key stored in OS keychain, first response within 800ms on Groq |
| US-2 | As a dev, I want ghost text completions like Copilot but free | Inline suggestion appears within 500ms of 300ms typing pause |
| US-3 | As a dev, I want to install the filesystem MCP in one click with no terminal | Click install → wizard collects path → MCP running, green checkmark shown |
| US-4 | As a dev, I want the AI to automatically know what file I'm editing | Active file + selection injected into every chat context, shown as badge |
| US-5 | As a dev, I want to see how much my session has cost in real time | Status bar shows token count + cost, updated after each response |
| US-6 | As a dev, I want the extension to auto-switch to free models when I'm over budget | Daily budget setting, auto-routes to free tier models when approaching limit |
| US-7 | As a dev, I want to explain this entire repository in one click | "Explain repo" command reads all files, generates README + architecture summary |
| US-8 | As a student, I want this free forever | Student tier gated by GitHub Student Pack webhook check |

---

## 5. MVP Scope

### In v1 (build this)

- AI chat panel (streaming, markdown rendering, code blocks with copy)
- Inline ghost text completions (FIM — Fill in Middle)
- Model router supporting: Groq, Gemini Flash, OpenRouter (free models)
- MCP one-click install for 10 pre-built MCPs:
  - `@modelcontextprotocol/server-filesystem`
  - `@modelcontextprotocol/server-github`
  - `@modelcontextprotocol/server-gitlab`
  - `@modelcontextprotocol/server-brave-search`
  - `@modelcontextprotocol/server-memory`
  - `@modelcontextprotocol/server-puppeteer`
  - `@modelcontextprotocol/server-postgres`
  - `@modelcontextprotocol/server-slack`
  - `@modelcontextprotocol/server-google-maps`
  - `mcp-server-git`
- API Key Vault using VSCode SecretStorage (OS keychain)
- Codebase RAG: index workspace with ChromaDB, inject top-8 chunks per query
- Real-time cost + token tracker in status bar
- Budget mode: daily $ cap, auto-routes to free models on threshold
- "Explain this repo" command

### Out of scope for v1

- MCP Marketplace (browse community MCPs) — v2
- Voice coding — v2
- Team context sharing — paid v1
- Multi-file diff application — v2
- Cloud sync of settings — paid
- Custom language server — v2
- Building our own model inference — never

---

## 6. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Extension activation time | < 2 seconds (backend spawns async) |
| Backend startup time | < 800ms (from spawn to /health response) |
| Ghost text latency (p95) | < 500ms (300ms debounce + 200ms inference) |
| Chat first token (Groq path, p95) | < 800ms |
| Extension bundle size | < 15MB |
| Memory footprint (backend) | < 200MB RAM |
| Python version | 3.11+ |
| Node.js version | 18+ (ships with VSCode, no separate install) |
| Telemetry | Opt-in only. Zero data leaves machine by default |
| Offline capability | Full functionality with local Ollama. Graceful degradation otherwise |
| OS support | Windows 10+, macOS 12+, Ubuntu 20.04+ |
| VSCode version | >= 1.85.0 |
| Cold boot (first install) | Backend deps install on first activation, progress shown |

---

## 7. Tech Stack

### Extension Host (TypeScript)

| Package | Version | Purpose |
|---|---|---|
| `vscode` | bundled | VSCode extension API |
| `typescript` | ^5.3 | Language |
| `webpack` | ^5 | Bundling (separate bundles: extension + each webview) |
| `@types/vscode` | ^1.85 | Type definitions |
| `@types/node` | ^18 | Node types |

### Webview UI (React)

| Package | Version | Purpose |
|---|---|---|
| `react` | ^18 | UI framework |
| `react-dom` | ^18 | DOM rendering |
| `@vscode/webview-ui-toolkit` | ^1.4 | VSCode-themed components |
| `react-markdown` | ^9 | Render markdown in chat |
| `react-syntax-highlighter` | ^15 | Code block highlighting |
| `tailwindcss` | ^3 | Styling |

### Python Backend (FastAPI)

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | ^0.111 | HTTP API framework |
| `uvicorn` | ^0.29 | ASGI server |
| `openai` | ^1.35 | OpenAI-compatible client (works with all providers) |
| `chromadb` | ^0.5 | Local vector store for RAG |
| `sentence-transformers` | ^3.0 | nomic-embed-text embeddings (local, free) |
| `tree-sitter` | ^0.22 | AST-based code parsing for smart chunking |
| `watchdog` | ^4 | Filesystem watcher for incremental re-indexing |
| `aiofiles` | ^23 | Async file I/O |
| `httpx` | ^0.27 | Async HTTP (used for provider health checks) |
| `cryptography` | ^42 | Fernet encryption for key vault backup |
| `sqlalchemy` | ^2 | ORM for SQLite |
| `pydantic` | ^2 | Request/response models |
| `python-dotenv` | ^1 | Env var loading |

### Why not do everything in TypeScript?

Three concrete reasons:
1. `chromadb`, `sentence-transformers`, `tree-sitter` Python bindings do not have JS equivalents that work at this quality
2. Python async streaming (FastAPI + SSE) is more ergonomic and battle-tested than Node.js streaming
3. Separation of concerns: swapping the backend from Python to Go/Rust later does not require touching the extension

### Why FastAPI over Flask/Django?

FastAPI has native async support, automatic OpenAPI schema generation, and `StreamingResponse` for SSE built in. Flask requires Quart for async. Django is too heavy. FastAPI is the correct choice.

---

## 8. Architecture — HLD

### The Three-Process Model

A VSCode extension runs across three separate OS processes. This is VSCode's security architecture and cannot be changed.

```
┌─────────────────────────────────────────────────────┐
│  VSCode                                             │
│                                                     │
│  ┌──────────────────┐      ┌─────────────────────┐  │
│  │  Renderer process │      │  Extension host     │  │
│  │  (sandboxed iframe│ IPC  │  (Node.js)          │  │
│  │  React webviews) │◄────►│  TypeScript code    │  │
│  │                  │      │                     │  │
│  └──────────────────┘      └──────────┬──────────┘  │
│                                        │ HTTP/SSE    │
└────────────────────────────────────────┼────────────┘
                                         │
                            ┌────────────▼────────────┐
                            │  Python backend          │
                            │  FastAPI on :7822        │
                            │  (child process)         │
                            └────────────┬────────────┘
                                         │ HTTP
                            ┌────────────▼────────────┐
                            │  LLM Providers           │
                            │  Groq, Gemini, NVIDIA,   │
                            │  OpenRouter, Ollama       │
                            └─────────────────────────┘
```

### Process 1: Renderer (webview)

- Sandboxed iframe. No filesystem. No network. No Node.js.
- Communicates with Extension Host ONLY via `vscode.postMessage()` and `window.addEventListener('message')`
- Contains: Chat panel UI, MCP manager UI, model selector
- Technology: React + Tailwind, compiled by webpack

### Process 2: Extension Host (TypeScript/Node.js)

- Has full OS access. Runs all VSCode API calls.
- Spawns the Python backend as a child process
- Bridges webview messages to backend HTTP calls
- Registers: commands, inline completion provider, code action provider, status bar
- Technology: TypeScript compiled to CommonJS

### Process 3: Python Backend (FastAPI)

- Runs on `localhost:7822`
- Handles all AI operations, indexing, MCP management
- Spawned by extension host, killed on deactivation
- Technology: Python 3.11+, FastAPI, uvicorn

### Communication Channels

| Channel | Protocol | Used for |
|---|---|---|
| Renderer ↔ Extension Host | `postMessage` JSON | User actions, streaming chunks, status updates |
| Extension Host ↔ Backend | HTTP REST | Commands, settings, one-shot queries |
| Extension Host ↔ Backend | HTTP SSE | Streaming chat completions |
| Backend ↔ Providers | HTTP REST | All LLM API calls |

### Startup Sequence

```
1. VSCode loads extension (activation event: onStartupFinished)
2. Extension Host: show "Forge starting..." in status bar
3. Extension Host: spawn Python process
   → python3 backend/main.py --port 7822
4. Extension Host: poll GET /api/health every 200ms
5. Backend: FastAPI starts, loads ChromaDB, init SQLite
6. Backend: /api/health returns 200 OK (usually ~800ms)
7. Extension Host: register all commands + providers
8. Extension Host: update status bar to "$(sparkle) Forge | [model]"
9. Extension Host: send workspace path to backend for indexing
10. Background: backend starts incremental file indexing
```

---

## 9. Extension Host — LLD

### 9.1 extension.ts (entry point)

```typescript
// src/extension.ts
import * as vscode from 'vscode';
import { BackendService } from './services/backendService';
import { ContextService } from './services/contextService';
import { StatusBarService } from './services/statusBarService';
import { ChatPanel } from './views/chatPanel';
import { MCPPanel } from './views/mcpPanel';
import { SidebarProvider } from './views/sidebarProvider';
import { InlineCompleter } from './providers/inlineCompleter';
import { registerCommands } from './commands';

let backend: BackendService;
let statusBar: StatusBarService;

export async function activate(ctx: vscode.ExtensionContext) {
  // 1. Start Python backend (async — don't block UI)
  backend = new BackendService(ctx);
  const contextService = new ContextService(backend);
  statusBar = new StatusBarService(ctx);

  statusBar.setStarting();

  // Fire-and-forget startup — UI shows immediately
  backend.start().then(() => {
    statusBar.setReady(backend.getActiveModel());
    // Index workspace after backend is ready
    const wsPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (wsPath) backend.indexWorkspace(wsPath);
  }).catch((err) => {
    statusBar.setError();
    vscode.window.showErrorMessage(`Forge backend failed to start: ${err.message}`);
  });

  // 2. Register inline completion (ghost text)
  ctx.subscriptions.push(
    vscode.languages.registerInlineCompletionItemProvider(
      { pattern: '**' },
      new InlineCompleter(backend, contextService)
    )
  );

  // 3. Register sidebar webview provider
  ctx.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      'forge.chat',
      new SidebarProvider(ctx, backend, contextService)
    )
  );

  // 4. Register all forge.* commands
  registerCommands(ctx, backend, contextService);
}

export function deactivate() {
  backend?.stop();
}
```

### 9.2 Commands (src/commands/index.ts)

```typescript
// src/commands/index.ts
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { ContextService } from '../services/contextService';
import { ChatPanel } from '../views/chatPanel';
import { MCPPanel } from '../views/mcpPanel';

export function registerCommands(
  ctx: vscode.ExtensionContext,
  backend: BackendService,
  contextService: ContextService
) {
  const cmds = [
    ['forge.chat.open', () => ChatPanel.createOrShow(ctx, backend, contextService)],
    ['forge.mcp.open', () => MCPPanel.createOrShow(ctx, backend)],
    ['forge.index.workspace', async () => {
      const wsPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!wsPath) return;
      vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Forge: indexing workspace...' },
        async () => { await backend.indexWorkspace(wsPath); }
      );
    }],
    ['forge.explain.repo', async () => {
      const wsPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!wsPath) return;
      ChatPanel.createOrShow(ctx, backend, contextService);
      // Send special command to the panel
      await backend.sendExplainRepo(wsPath);
    }],
    ['forge.add.provider', async () => {
      const provider = await vscode.window.showQuickPick(
        ['groq', 'gemini', 'openrouter', 'nvidia', 'cerebras', 'anthropic', 'ollama'],
        { placeHolder: 'Select provider' }
      );
      if (!provider) return;
      const key = await vscode.window.showInputBox({
        prompt: `Enter ${provider} API key`,
        password: true,
        ignoreFocusOut: true
      });
      if (!key) return;
      await ctx.secrets.store(`forge.${provider}.apiKey`, key);
      await backend.registerProvider(provider, key);
      vscode.window.showInformationMessage(`Forge: ${provider} configured ✓`);
    }],
    ['forge.set.model', async () => {
      const models = await backend.getAvailableModels();
      const picked = await vscode.window.showQuickPick(
        models.map(m => ({ label: m.display_name, description: m.is_free ? '● free' : `$${m.cost_per_1k_output}/1k`, detail: m.id })),
        { placeHolder: 'Select model' }
      );
      if (!picked) return;
      await backend.setModel(picked.detail);
    }],
  ];

  for (const [cmd, handler] of cmds) {
    ctx.subscriptions.push(vscode.commands.registerCommand(cmd, handler));
  }
}
```

### 9.3 InlineCompleter (src/providers/inlineCompleter.ts)

```typescript
// src/providers/inlineCompleter.ts
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { ContextService } from '../services/contextService';

export class InlineCompleter implements vscode.InlineCompletionItemProvider {
  private debounceTimer: NodeJS.Timeout | undefined;

  constructor(
    private backend: BackendService,
    private context: ContextService
  ) {}

  async provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _context: vscode.InlineCompletionContext
  ): Promise<vscode.InlineCompletionList> {
    if (this.debounceTimer) clearTimeout(this.debounceTimer);

    return new Promise((resolve) => {
      this.debounceTimer = setTimeout(async () => {
        try {
          // Get ~2000 chars of prefix (before cursor)
          const prefixStart = new vscode.Position(Math.max(0, position.line - 60), 0);
          const prefix = document.getText(new vscode.Range(prefixStart, position));

          // Get ~500 chars of suffix (after cursor)
          const suffixEnd = new vscode.Position(position.line + 15, 0);
          const suffix = document.getText(new vscode.Range(position, suffixEnd));

          const completion = await this.backend.complete({
            prefix,
            suffix,
            language: document.languageId,
            filepath: document.fileName,
          });

          if (!completion || completion.trim() === '') {
            return resolve({ items: [] });
          }

          resolve({
            items: [
              new vscode.InlineCompletionItem(
                completion,
                new vscode.Range(position, position)
              )
            ]
          });
        } catch {
          resolve({ items: [] });
        }
      }, 300);
    });
  }
}
```

### 9.4 BackendService (src/services/backendService.ts)

```typescript
// src/services/backendService.ts
import * as cp from 'child_process';
import * as vscode from 'vscode';
import * as path from 'path';

const PORT = 7822;
const BASE_URL = `http://localhost:${PORT}`;
const HEALTH_POLL_INTERVAL_MS = 200;
const HEALTH_TIMEOUT_MS = 12_000;

export class BackendService {
  private proc: cp.ChildProcess | undefined;
  private activeModel = 'groq/llama-3.3-70b-versatile';

  constructor(private ctx: vscode.ExtensionContext) {}

  async start(): Promise<void> {
    const config = vscode.workspace.getConfiguration('forge');
    const pythonPath = config.get<string>('pythonPath', 'python3');
    const backendPath = this.ctx.asAbsolutePath('backend/main.py');

    // Inject stored API keys as env vars
    const env = await this.buildEnv();

    this.proc = cp.spawn(pythonPath, [backendPath, '--port', String(PORT)], {
      env,
      stdio: 'pipe',
      cwd: this.ctx.asAbsolutePath('backend'),
    });

    this.proc.stderr?.on('data', (d: Buffer) => {
      const msg = d.toString().trim();
      if (msg) console.error('[forge-backend]', msg);
    });

    this.proc.on('exit', (code) => {
      if (code !== 0 && code !== null) {
        console.error(`[forge-backend] exited with code ${code}`);
      }
    });

    await this.waitForHealth();
  }

  private async buildEnv(): Promise<NodeJS.ProcessEnv> {
    const providers = ['groq', 'gemini', 'openrouter', 'nvidia', 'cerebras', 'anthropic', 'ollama'];
    const env: NodeJS.ProcessEnv = { ...process.env };

    for (const p of providers) {
      const key = await this.ctx.secrets.get(`forge.${p}.apiKey`);
      if (key) env[`FORGE_${p.toUpperCase()}_KEY`] = key;
    }

    return env;
  }

  private async waitForHealth(): Promise<void> {
    const deadline = Date.now() + HEALTH_TIMEOUT_MS;
    while (Date.now() < deadline) {
      try {
        const res = await fetch(`${BASE_URL}/api/health`, { signal: AbortSignal.timeout(500) });
        if (res.ok) {
          const data = await res.json() as { model: string };
          this.activeModel = data.model ?? this.activeModel;
          return;
        }
      } catch {
        // Backend not ready yet
      }
      await new Promise(r => setTimeout(r, HEALTH_POLL_INTERVAL_MS));
    }
    throw new Error(`Backend did not respond within ${HEALTH_TIMEOUT_MS}ms`);
  }

  getActiveModel() { return this.activeModel; }

  // ─── Streaming chat ────────────────────────────────────────────────────────

  async *streamChat(payload: {
    messages: { role: string; content: string }[];
    model_id?: string;
    context_chunks?: string[];
    conversation_id: string;
  }): AsyncGenerator<string> {
    const res = await fetch(`${BASE_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error(`Chat API error: ${res.status}`);

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const text = decoder.decode(value, { stream: true });
      for (const line of text.split('\n')) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data === '[DONE]') return;
          try {
            const parsed = JSON.parse(data) as { content: string };
            if (parsed.content) yield parsed.content;
          } catch { /* ignore malformed SSE lines */ }
        }
      }
    }
  }

  // ─── Inline completions ────────────────────────────────────────────────────

  async complete(payload: {
    prefix: string;
    suffix: string;
    language: string;
    filepath: string;
  }): Promise<string | null> {
    try {
      const res = await fetch(`${BASE_URL}/api/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(3000),
      });
      if (!res.ok) return null;
      const data = await res.json() as { completion: string };
      return data.completion ?? null;
    } catch {
      return null;
    }
  }

  // ─── Workspace indexing ────────────────────────────────────────────────────

  async indexWorkspace(workspacePath: string): Promise<void> {
    await fetch(`${BASE_URL}/api/index`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_path: workspacePath }),
    });
  }

  // ─── Provider management ───────────────────────────────────────────────────

  async registerProvider(provider: string, apiKey: string): Promise<void> {
    await fetch(`${BASE_URL}/api/providers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: provider, api_key: apiKey }),
    });
  }

  async getAvailableModels(): Promise<{ id: string; display_name: string; is_free: boolean; cost_per_1k_output: number }[]> {
    const res = await fetch(`${BASE_URL}/api/models`);
    return res.json();
  }

  async setModel(modelId: string): Promise<void> {
    this.activeModel = modelId;
    await fetch(`${BASE_URL}/api/settings`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ default_model: modelId }),
    });
  }

  async getUsage(): Promise<{ today_usd: number; today_tokens: number }> {
    const res = await fetch(`${BASE_URL}/api/usage`);
    return res.json();
  }

  async getMCPList(): Promise<{ id: string; display_name: string; status: string }[]> {
    const res = await fetch(`${BASE_URL}/api/mcp/list`);
    return res.json();
  }

  async installMCP(mcpId: string, config: Record<string, string>): Promise<{ status: string; error?: string }> {
    const res = await fetch(`${BASE_URL}/api/mcp/install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mcp_id: mcpId, config }),
    });
    return res.json();
  }

  async sendExplainRepo(workspacePath: string): Promise<void> {
    await fetch(`${BASE_URL}/api/explain-repo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_path: workspacePath }),
    });
  }

  async queryContext(query: string, k = 8): Promise<{ content: string; file: string; line: number }[]> {
    const res = await fetch(`${BASE_URL}/api/context/chunks?q=${encodeURIComponent(query)}&k=${k}`);
    return res.json();
  }

  stop(): void {
    this.proc?.kill('SIGTERM');
  }
}
```

### 9.5 ContextService (src/services/contextService.ts)

```typescript
// src/services/contextService.ts
import * as vscode from 'vscode';
import { BackendService } from './backendService';

export interface ContextSnapshot {
  activeFile: string | null;
  language: string | null;
  selection: string | null;
  ragChunks: { content: string; file: string; line: number }[];
  tokenEstimate: number;
}

export class ContextService {
  constructor(private backend: BackendService) {}

  async gatherContext(userQuery: string): Promise<ContextSnapshot> {
    const editor = vscode.window.activeTextEditor;
    let activeFile: string | null = null;
    let language: string | null = null;
    let selection: string | null = null;

    if (editor) {
      activeFile = editor.document.getText();
      language = editor.document.languageId;
      const sel = editor.document.getText(editor.selection);
      if (sel.trim()) selection = sel;
    }

    // RAG: get relevant chunks from indexed codebase
    let ragChunks: { content: string; file: string; line: number }[] = [];
    try {
      ragChunks = await this.backend.queryContext(userQuery, 8);
    } catch {
      // RAG unavailable (indexing not complete yet) — proceed without
    }

    // Estimate tokens (rough: 1 token ~ 4 chars)
    const totalChars = (activeFile?.length ?? 0) + (selection?.length ?? 0) +
      ragChunks.reduce((s, c) => s + c.content.length, 0);

    return {
      activeFile: activeFile ? activeFile.slice(0, 6000) : null, // cap at ~1500 tokens
      language,
      selection,
      ragChunks,
      tokenEstimate: Math.ceil(totalChars / 4),
    };
  }

  getActiveFilePath(): string | null {
    return vscode.window.activeTextEditor?.document.fileName ?? null;
  }
}
```

### 9.6 StatusBarService (src/services/statusBarService.ts)

```typescript
// src/services/statusBarService.ts
import * as vscode from 'vscode';

export class StatusBarService {
  private item: vscode.StatusBarItem;

  constructor(ctx: vscode.ExtensionContext) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.item.command = 'forge.chat.open';
    this.item.show();
    ctx.subscriptions.push(this.item);
  }

  setStarting() {
    this.item.text = '$(loading~spin) Forge starting...';
    this.item.tooltip = 'Forge is initializing...';
  }

  setReady(modelId: string) {
    const shortModel = modelId.split('/').pop() ?? modelId;
    this.item.text = `$(sparkle) Forge | ${shortModel}`;
    this.item.tooltip = `Active model: ${modelId}\nClick to open chat`;
  }

  setError() {
    this.item.text = '$(error) Forge error';
    this.item.tooltip = 'Forge failed to start. Check output panel.';
  }

  updateUsage(tokens: number, costUsd: number) {
    const costStr = costUsd > 0 ? ` | $${costUsd.toFixed(4)}` : '';
    const modelPart = this.item.text.split('|')[1]?.trim() ?? '';
    this.item.text = `$(sparkle) Forge | ${modelPart}${costStr} | ${tokens.toLocaleString()}t`;
  }
}
```

---

## 10. Webview Layer — LLD

### Architecture

Each webview is a separate React app, compiled by webpack into `out/webview/chat.js` and `out/webview/mcp.js`. They are loaded into `vscode.WebviewPanel` instances.

### 10.1 ChatPanel.ts (view manager)

```typescript
// src/views/chatPanel.ts
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { ContextService } from '../services/contextService';
import { WebviewToExtension, ExtensionToWebview } from '../types';
import * as path from 'path';
import * as fs from 'fs';

export class ChatPanel {
  static currentPanel: ChatPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private conversationHistory: { role: string; content: string }[] = [];

  static createOrShow(
    ctx: vscode.ExtensionContext,
    backend: BackendService,
    context: ContextService
  ) {
    const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;
    if (ChatPanel.currentPanel) {
      ChatPanel.currentPanel.panel.reveal(column);
      return;
    }
    const panel = vscode.window.createWebviewPanel('forge.chat', 'Forge Chat', column, {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(path.join(ctx.extensionPath, 'out'))],
      retainContextWhenHidden: true, // keep React state alive when hidden
    });
    ChatPanel.currentPanel = new ChatPanel(panel, ctx, backend, context);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    private ctx: vscode.ExtensionContext,
    private backend: BackendService,
    private contextService: ContextService
  ) {
    this.panel = panel;
    this.panel.webview.html = this.getHtml();

    this.panel.webview.onDidReceiveMessage(async (msg: WebviewToExtension) => {
      await this.handleMessage(msg);
    });

    this.panel.onDidDispose(() => {
      ChatPanel.currentPanel = undefined;
    });
  }

  private async handleMessage(msg: WebviewToExtension) {
    switch (msg.type) {
      case 'SEND_MESSAGE': {
        // Gather context
        const snapshot = await this.contextService.gatherContext(msg.content);

        // Add to conversation history
        this.conversationHistory.push({ role: 'user', content: msg.content });

        // Build messages with context injection
        const systemContent = this.buildSystemPrompt(snapshot);
        const messages = [
          { role: 'system', content: systemContent },
          ...this.conversationHistory.slice(-20), // keep last 20 turns
        ];

        let assistantContent = '';

        // Stream response
        try {
          for await (const chunk of this.backend.streamChat({
            messages,
            model_id: msg.modelId,
            conversation_id: msg.conversationId,
          })) {
            assistantContent += chunk;
            this.post<ExtensionToWebview>({
              type: 'STREAM_CHUNK',
              chunk,
              conversationId: msg.conversationId,
            });
          }
        } catch (err: any) {
          this.post<ExtensionToWebview>({
            type: 'STREAM_ERROR',
            error: err.message,
            conversationId: msg.conversationId,
          });
          return;
        }

        this.conversationHistory.push({ role: 'assistant', content: assistantContent });

        this.post<ExtensionToWebview>({
          type: 'STREAM_DONE',
          conversationId: msg.conversationId,
        });

        // Update usage in status bar
        const usage = await this.backend.getUsage();
        this.post<ExtensionToWebview>({
          type: 'USAGE_UPDATE',
          tokensUsed: usage.today_tokens,
          costUsd: usage.today_usd,
        });
        break;
      }

      case 'REQUEST_CONTEXT': {
        const snapshot = await this.contextService.gatherContext('');
        this.post<ExtensionToWebview>({
          type: 'CONTEXT_UPDATE',
          files: snapshot.activeFile ? [this.contextService.getActiveFilePath() ?? ''] : [],
          tokenCount: snapshot.tokenEstimate,
          ragChunkCount: snapshot.ragChunks.length,
        });
        break;
      }

      case 'CLEAR_CONVERSATION': {
        this.conversationHistory = [];
        break;
      }
    }
  }

  private buildSystemPrompt(snapshot: ReturnType<ContextService['gatherContext']> extends Promise<infer T> ? T : never): string {
    const parts = ['You are Forge, an expert AI coding assistant.'];

    if (snapshot.activeFile) {
      parts.push(`\nActive file (${snapshot.language}):\n\`\`\`${snapshot.language}\n${snapshot.activeFile}\n\`\`\``);
    }

    if (snapshot.selection) {
      parts.push(`\nSelected code:\n\`\`\`\n${snapshot.selection}\n\`\`\``);
    }

    if (snapshot.ragChunks.length > 0) {
      parts.push('\nRelevant codebase context:');
      for (const chunk of snapshot.ragChunks) {
        parts.push(`\n// ${chunk.file}:${chunk.line}\n\`\`\`\n${chunk.content}\n\`\`\``);
      }
    }

    return parts.join('\n');
  }

  private post<T>(msg: T) {
    this.panel.webview.postMessage(msg);
  }

  private getHtml(): string {
    const scriptUri = this.panel.webview.asWebviewUri(
      vscode.Uri.file(path.join(this.ctx.extensionPath, 'out', 'webview', 'chat.js'))
    );
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${this.panel.webview.cspSource}; style-src ${this.panel.webview.cspSource} 'unsafe-inline';">
  <title>Forge Chat</title>
</head>
<body>
  <div id="root"></div>
  <script src="${scriptUri}"></script>
</body>
</html>`;
  }
}
```

### 10.2 React Chat App (webview-src/chat/App.tsx)

```tsx
// webview-src/chat/App.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';

declare const acquireVsCodeApi: () => {
  postMessage: (msg: unknown) => void;
  getState: () => unknown;
  setState: (state: unknown) => void;
};

const vscode = acquireVsCodeApi();

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [contextFiles, setContextFiles] = useState<string[]>([]);
  const [tokenCount, setTokenCount] = useState(0);
  const [costUsd, setCostUsd] = useState(0);
  const conversationId = useRef(crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Request initial context
    vscode.postMessage({ type: 'REQUEST_CONTEXT' });

    const handler = (event: MessageEvent) => {
      const msg = event.data;
      switch (msg.type) {
        case 'STREAM_CHUNK':
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last?.role === 'assistant' && last.streaming) {
              return [...prev.slice(0, -1), { ...last, content: last.content + msg.chunk }];
            }
            return [...prev, { id: crypto.randomUUID(), role: 'assistant', content: msg.chunk, streaming: true }];
          });
          break;
        case 'STREAM_DONE':
          setIsStreaming(false);
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last?.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
            return prev;
          });
          break;
        case 'STREAM_ERROR':
          setIsStreaming(false);
          setMessages(prev => [...prev, {
            id: crypto.randomUUID(), role: 'assistant',
            content: `Error: ${msg.error}`
          }]);
          break;
        case 'CONTEXT_UPDATE':
          setContextFiles(msg.files);
          setTokenCount(msg.tokenCount);
          break;
        case 'USAGE_UPDATE':
          setTokenCount(msg.tokensUsed);
          setCostUsd(msg.costUsd);
          break;
      }
    };

    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(() => {
    if (!input.trim() || isStreaming) return;
    const content = input.trim();
    setInput('');
    setIsStreaming(true);
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', content }]);
    vscode.postMessage({
      type: 'SEND_MESSAGE',
      content,
      conversationId: conversationId.current,
    });
  }, [input, isStreaming]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'var(--vscode-font-family)' }}>
      {/* Context badge */}
      {contextFiles.length > 0 && (
        <div style={{ padding: '4px 12px', fontSize: 11, color: 'var(--vscode-descriptionForeground)', borderBottom: '1px solid var(--vscode-panel-border)' }}>
          {contextFiles.map(f => f.split('/').pop()).join(', ')} · ~{tokenCount.toLocaleString()} tokens
          {costUsd > 0 && ` · $${costUsd.toFixed(4)} today`}
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
        {messages.map(msg => (
          <div key={msg.id} style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, color: 'var(--vscode-descriptionForeground)', textTransform: 'uppercase' }}>
              {msg.role === 'user' ? 'You' : 'Forge'}
            </div>
            <div style={{ color: 'var(--vscode-foreground)' }}>
              <ReactMarkdown components={{
                code({ className, children }) {
                  const match = /language-(\w+)/.exec(className || '');
                  return match ? (
                    <SyntaxHighlighter language={match[1]} PreTag="div">
                      {String(children)}
                    </SyntaxHighlighter>
                  ) : (
                    <code style={{ background: 'var(--vscode-textBlockQuote-background)', padding: '2px 4px', borderRadius: 3 }}>
                      {children}
                    </code>
                  );
                }
              }}>
                {msg.content}
              </ReactMarkdown>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: '8px 12px', borderTop: '1px solid var(--vscode-panel-border)' }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          placeholder="Ask Forge anything... (Enter to send, Shift+Enter for newline)"
          disabled={isStreaming}
          rows={3}
          style={{
            width: '100%', resize: 'none', boxSizing: 'border-box',
            background: 'var(--vscode-input-background)',
            color: 'var(--vscode-input-foreground)',
            border: '1px solid var(--vscode-input-border)',
            borderRadius: 4, padding: '6px 8px', fontSize: 13,
            fontFamily: 'inherit', outline: 'none',
          }}
        />
      </div>
    </div>
  );
}
```

---

## 11. Python Backend — LLD

### 11.1 main.py

```python
# backend/main.py
import argparse, asyncio, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from router.model_router import ModelRouter
from context.indexer import ContextEngine
from mcp.manager import MCPManager
from db import init_db, get_session
from db.models import Settings
from schemas import (
    ChatRequest, CompleteRequest, IndexRequest,
    MCPInstallRequest, ProviderRequest, SettingsPatch
)

model_router = ModelRouter()
context_engine = ContextEngine()
mcp_manager = MCPManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await context_engine.start_watcher()
    yield
    await mcp_manager.stop_all()
    await context_engine.stop_watcher()


app = FastAPI(title='Forge Backend', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['vscode-webview://*'], allow_methods=['*'], allow_headers=['*'])


@app.get('/api/health')
async def health():
    return {'status': 'ok', 'model': model_router.get_default_model()}


@app.post('/api/chat')
async def chat(body: ChatRequest):
    async def generate():
        async for chunk in model_router.stream(body.messages, body.model_id, body.context_chunks or []):
            yield f'data: {chunk}\n\n'
        yield 'data: [DONE]\n\n'
    return StreamingResponse(generate(), media_type='text/event-stream')


@app.post('/api/complete')
async def complete(body: CompleteRequest):
    result = await model_router.complete_fim(body.prefix, body.suffix, body.language)
    return {'completion': result}


@app.post('/api/index')
async def index(body: IndexRequest):
    asyncio.create_task(context_engine.index(body.workspace_path))
    return {'status': 'indexing_started'}


@app.get('/api/index/status')
async def index_status():
    return context_engine.get_status()


@app.get('/api/context/chunks')
async def context_chunks(q: str, k: int = 8):
    return context_engine.search(q, k)


@app.post('/api/providers')
async def add_provider(body: ProviderRequest):
    model_router.register_provider(body.provider_id, body.api_key)
    return {'status': 'ok'}


@app.get('/api/models')
async def list_models():
    return model_router.list_models()


@app.post('/api/mcp/install')
async def install_mcp(body: MCPInstallRequest):
    result = await mcp_manager.install(body.mcp_id, body.config)
    return result


@app.get('/api/mcp/list')
async def list_mcp():
    return mcp_manager.list_all()


@app.delete('/api/mcp/{mcp_id}')
async def uninstall_mcp(mcp_id: str):
    await mcp_manager.uninstall(mcp_id)
    return {'status': 'ok'}


@app.get('/api/usage')
async def usage():
    return model_router.get_usage_stats()


@app.patch('/api/settings')
async def patch_settings(body: SettingsPatch):
    with get_session() as db:
        if body.default_model:
            db.merge(Settings(key='default_model', value=body.default_model))
        db.commit()
    if body.default_model:
        model_router.set_default_model(body.default_model)
    return {'status': 'ok'}


@app.post('/api/explain-repo')
async def explain_repo(body: IndexRequest):
    """Generate README + architecture doc for entire workspace."""
    summary = await context_engine.summarize_repo(body.workspace_path)
    return {'summary': summary}


if __name__ == '__main__':
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=7822)
    args = parser.parse_args()
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
```

---

## 12. IPC Message Protocol

All messages between Renderer and Extension Host are typed JSON objects. Define these in `src/types.ts` and import in both sides.

```typescript
// src/types.ts

// ─── Renderer → Extension Host ─────────────────────────────────────────────

export type WebviewToExtension =
  | {
      type: 'SEND_MESSAGE';
      content: string;
      conversationId: string;
      modelId?: string;
    }
  | {
      type: 'INSTALL_MCP';
      mcpId: string;
      config: Record<string, string>;
    }
  | {
      type: 'SET_MODEL';
      modelId: string;
    }
  | {
      type: 'REQUEST_CONTEXT';
    }
  | {
      type: 'CLEAR_CONVERSATION';
    }
  | {
      type: 'OPEN_FILE';
      path: string;
    }
  | {
      type: 'REQUEST_MODELS';
    }
  | {
      type: 'REQUEST_MCP_LIST';
    };

// ─── Extension Host → Renderer ─────────────────────────────────────────────

export type ExtensionToWebview =
  | {
      type: 'STREAM_CHUNK';
      chunk: string;
      conversationId: string;
    }
  | {
      type: 'STREAM_DONE';
      conversationId: string;
    }
  | {
      type: 'STREAM_ERROR';
      error: string;
      conversationId: string;
    }
  | {
      type: 'CONTEXT_UPDATE';
      files: string[];
      tokenCount: number;
      ragChunkCount: number;
    }
  | {
      type: 'USAGE_UPDATE';
      tokensUsed: number;
      costUsd: number;
    }
  | {
      type: 'MCP_STATUS';
      mcpId: string;
      status: 'installing' | 'ready' | 'error';
      error?: string;
    }
  | {
      type: 'MODELS_LIST';
      models: { id: string; display_name: string; is_free: boolean }[];
    }
  | {
      type: 'MCP_LIST';
      mcps: { id: string; display_name: string; status: string }[];
    };
```

---

## 13. REST API Contract

All endpoints live on `http://localhost:7822`. Extension host is the only client.

| Method | Path | Request Body | Response | Notes |
|---|---|---|---|---|
| `GET` | `/api/health` | — | `{status, model}` | Polled on startup every 200ms |
| `POST` | `/api/chat` | `{messages[], model_id?, context_chunks?[]}` | SSE stream: `data: {content}` | `[DONE]` terminates stream |
| `POST` | `/api/complete` | `{prefix, suffix, language, filepath}` | `{completion}` | Ghost text, max 3s timeout |
| `POST` | `/api/index` | `{workspace_path}` | `{status}` | Async, starts background task |
| `GET` | `/api/index/status` | — | `{status, files_indexed, total_files}` | Poll during indexing |
| `GET` | `/api/context/chunks` | query: `?q=...&k=8` | `[{content, file, line}]` | Manual RAG search |
| `POST` | `/api/providers` | `{provider_id, api_key}` | `{status}` | Register provider |
| `GET` | `/api/models` | — | `[{id, display_name, is_free, cost_per_1k}]` | All available models |
| `POST` | `/api/mcp/install` | `{mcp_id, config{}}` | `{status, error?}` | Full MCP install flow |
| `GET` | `/api/mcp/list` | — | `[{id, display_name, status}]` | All MCPs + state |
| `DELETE` | `/api/mcp/{id}` | — | `{status}` | Kill + remove config |
| `GET` | `/api/usage` | — | `{today_usd, today_tokens, by_model[]}` | Session stats |
| `PATCH` | `/api/settings` | `{default_model?, daily_budget_usd?}` | `{status}` | Update settings |
| `POST` | `/api/explain-repo` | `{workspace_path}` | `{summary}` | Full repo summary |

---

## 14. Database Schema

SQLite database at `~/.forge/forge.db`. Use SQLAlchemy ORM.

```python
# backend/db/models.py
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Provider(Base):
    __tablename__ = 'providers'
    id = Column(String, primary_key=True)        # 'groq', 'gemini', 'openrouter'
    display_name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_free = Column(Boolean, default=False)
    rpm_limit = Column(Integer, nullable=True)   # requests per minute
    tpm_limit = Column(Integer, nullable=True)   # tokens per minute
    rpd_limit = Column(Integer, nullable=True)   # requests per day
    created_at = Column(DateTime, default=datetime.utcnow)


class Model(Base):
    __tablename__ = 'models'
    id = Column(String, primary_key=True)         # 'groq/llama-3.3-70b-versatile'
    provider_id = Column(String, nullable=False)
    model_id = Column(String, nullable=False)     # provider's model string
    display_name = Column(String, nullable=False)
    context_window = Column(Integer, default=8192)
    supports_vision = Column(Boolean, default=False)
    supports_tools = Column(Boolean, default=False)
    supports_fim = Column(Boolean, default=False) # fill-in-middle for completions
    is_free = Column(Boolean, default=False)
    cost_per_1k_input = Column(Float, default=0.0)
    cost_per_1k_output = Column(Float, default=0.0)
    recommended_for = Column(Text, default='[]')  # JSON array: ["coding","quick"]


class MCPServer(Base):
    __tablename__ = 'mcp_servers'
    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    description = Column(Text)
    category = Column(String)                      # 'filesystem','git','web','memory'
    install_command = Column(String)               # 'npx @mcp/server-filesystem'
    config_template = Column(Text)                 # JSON template
    required_env_keys = Column(Text, default='[]') # JSON array
    is_installed = Column(Boolean, default=False)
    is_running = Column(Boolean, default=False)
    installed_at = Column(DateTime, nullable=True)


class UsageLog(Base):
    __tablename__ = 'usage_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(String)
    model_id = Column(String)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    task_type = Column(String)                     # 'chat', 'complete', 'explain'
    conversation_id = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Settings(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(Text)
    # Stored keys: default_model, daily_budget_usd, telemetry_enabled, student_mode
```

```python
# backend/db/__init__.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from pathlib import Path
from .models import Base, Model, Provider, MCPServer

DB_PATH = Path.home() / '.forge' / 'forge.db'
DB_PATH.parent.mkdir(exist_ok=True)
engine = create_engine(f'sqlite:///{DB_PATH}', connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)
    _seed_defaults()


def _seed_defaults():
    """Seed model catalog and provider defaults on first run."""
    with get_session() as db:
        if db.query(Model).count() > 0:
            return  # already seeded

        providers = [
            Provider(id='groq', display_name='Groq', base_url='https://api.groq.com/openai/v1', is_free=True, rpm_limit=30, rpd_limit=1000),
            Provider(id='gemini', display_name='Google Gemini', base_url='https://generativelanguage.googleapis.com/v1beta/openai', is_free=True),
            Provider(id='cerebras', display_name='Cerebras', base_url='https://api.cerebras.ai/v1', is_free=True),
            Provider(id='openrouter', display_name='OpenRouter', base_url='https://openrouter.ai/api/v1', is_free=True),
            Provider(id='nvidia', display_name='NVIDIA NIM', base_url='https://integrate.api.nvidia.com/v1'),
            Provider(id='anthropic', display_name='Anthropic', base_url='https://api.anthropic.com/v1'),
            Provider(id='ollama', display_name='Local Ollama', base_url='http://localhost:11434/v1', is_free=True),
        ]
        db.add_all(providers)

        models = [
            Model(id='groq/llama-3.3-70b-versatile', provider_id='groq', model_id='llama-3.3-70b-versatile', display_name='Llama 3.3 70B (Groq)', is_free=True, context_window=32768, recommended_for='["quick","coding"]'),
            Model(id='groq/llama-3.1-8b-instant', provider_id='groq', model_id='llama-3.1-8b-instant', display_name='Llama 3.1 8B Instant (Groq)', is_free=True, supports_fim=True, recommended_for='["fim"]'),
            Model(id='gemini/gemini-2.5-flash', provider_id='gemini', model_id='gemini-2.5-flash', display_name='Gemini 2.5 Flash', is_free=True, context_window=1000000, supports_vision=True, recommended_for='["long","vision"]'),
            Model(id='cerebras/llama-3.3-70b', provider_id='cerebras', model_id='llama3.3-70b', display_name='Llama 3.3 70B (Cerebras)', is_free=True, recommended_for='["quick"]'),
            Model(id='openrouter/qwen3-32b:free', provider_id='openrouter', model_id='qwen/qwen3-32b:free', display_name='Qwen3 32B (Free)', is_free=True, recommended_for='["coding","long"]'),
        ]
        db.add_all(models)
        db.commit()


@contextmanager
def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 15. Model Router (Complete)

```python
# backend/router/model_router.py
import asyncio, json, os
from openai import AsyncOpenAI
from db import get_session
from db.models import UsageLog, Settings

TASK_PROFILES = {
    'quick':   ['groq/llama-3.3-70b-versatile', 'cerebras/llama-3.3-70b', 'gemini/gemini-2.5-flash'],
    'coding':  ['groq/llama-3.3-70b-versatile', 'openrouter/qwen3-32b:free', 'gemini/gemini-2.5-flash'],
    'long':    ['gemini/gemini-2.5-flash', 'openrouter/qwen3-32b:free'],
    'vision':  ['gemini/gemini-2.5-flash'],
    'fim':     ['groq/llama-3.1-8b-instant', 'groq/llama-3.3-70b-versatile'],
}

PROVIDER_CONFIGS = {
    'groq':       {'base_url': 'https://api.groq.com/openai/v1',                         'env_key': 'FORGE_GROQ_KEY'},
    'gemini':     {'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai', 'env_key': 'FORGE_GEMINI_KEY'},
    'cerebras':   {'base_url': 'https://api.cerebras.ai/v1',                              'env_key': 'FORGE_CEREBRAS_KEY'},
    'openrouter': {'base_url': 'https://openrouter.ai/api/v1',                            'env_key': 'FORGE_OPENROUTER_KEY'},
    'nvidia':     {'base_url': 'https://integrate.api.nvidia.com/v1',                     'env_key': 'FORGE_NVIDIA_KEY'},
    'anthropic':  {'base_url': 'https://api.anthropic.com/v1',                            'env_key': 'FORGE_ANTHROPIC_KEY'},
    'ollama':     {'base_url': 'http://localhost:11434/v1',                                'env_key': None},
}


class ModelRouter:
    def __init__(self):
        self._clients: dict[str, AsyncOpenAI] = {}
        self._rate_limited: set[str] = set()
        self._default_model = 'groq/llama-3.3-70b-versatile'
        self._daily_budget_usd = 0.0  # 0 = unlimited
        self._today_cost_usd = 0.0
        self._today_tokens = 0
        self._load_settings()

    def _load_settings(self):
        with get_session() as db:
            s = db.query(Settings).filter_by(key='default_model').first()
            if s: self._default_model = s.value
            b = db.query(Settings).filter_by(key='daily_budget_usd').first()
            if b: self._daily_budget_usd = float(b.value)

    def _get_client(self, provider: str) -> AsyncOpenAI:
        if provider not in self._clients:
            cfg = PROVIDER_CONFIGS[provider]
            key = os.environ.get(cfg['env_key'] or '', 'ollama') if cfg['env_key'] else 'ollama'
            self._clients[provider] = AsyncOpenAI(api_key=key, base_url=cfg['base_url'])
        return self._clients[provider]

    def _is_free(self, model_id: str) -> bool:
        # Simple heuristic: known free models
        free_prefixes = ['groq/', 'cerebras/', 'openrouter/qwen3-32b:free', 'ollama/']
        return any(model_id.startswith(p) for p in free_prefixes) or 'gemini-2.5-flash' in model_id

    def _should_use_free_only(self) -> bool:
        if self._daily_budget_usd <= 0: return False
        return self._today_cost_usd >= self._daily_budget_usd * 0.9  # 90% threshold

    def _classify_task(self, text: str) -> str:
        text_lower = text.lower()
        if len(text) > 8000: return 'long'
        coding_words = ['fix', 'write', 'implement', 'debug', 'refactor', 'test', 'function', 'class', 'error', 'bug']
        if any(w in text_lower for w in coding_words): return 'coding'
        return 'quick'

    def _get_candidates(self, task_type: str, model_id: str | None) -> list[str]:
        if model_id:
            return [model_id] + [m for m in TASK_PROFILES.get(task_type, []) if m != model_id]
        candidates = TASK_PROFILES.get(task_type, TASK_PROFILES['quick'])
        if self._should_use_free_only():
            candidates = [c for c in candidates if self._is_free(c)]
        return candidates

    async def stream(self, messages: list, model_id: str | None, context_chunks: list[str]):
        if context_chunks:
            ctx = '\n\n'.join(f'```\n{c}\n```' for c in context_chunks)
            messages = [{'role': 'system', 'content': f'Relevant code from codebase:\n{ctx}'}] + messages

        task_type = self._classify_task(messages[-1].get('content', '') if messages else '')
        candidates = self._get_candidates(task_type, model_id)

        for candidate in candidates:
            if candidate in self._rate_limited: continue

            provider, model = candidate.split('/', 1)
            try:
                client = self._get_client(provider)
                stream = await client.chat.completions.create(
                    model=model, messages=messages, stream=True, max_tokens=4096
                )
                tokens_out = 0
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ''
                    if delta:
                        tokens_out += len(delta) // 4
                        yield f'{{"content": {json.dumps(delta)}}}'

                # Log usage
                self._today_tokens += tokens_out
                self._log_usage(provider, candidate, 0, tokens_out, task_type)
                return

            except Exception as e:
                err_str = str(e)
                if '429' in err_str or 'rate limit' in err_str.lower():
                    self._rate_limited.add(candidate)
                    asyncio.create_task(self._clear_rate_limit(candidate, 60))
                elif 'auth' in err_str.lower() or '401' in err_str:
                    continue  # No key for this provider
                else:
                    continue

        yield f'{{"content": "Error: all configured providers exhausted. Add an API key via forge.add.provider"}}'

    async def complete_fim(self, prefix: str, suffix: str, language: str) -> str | None:
        candidates = TASK_PROFILES['fim']
        prompt = f'<PRE>{prefix}<SUF>{suffix}<MID>'  # Standard FIM format
        for candidate in candidates:
            if candidate in self._rate_limited: continue
            provider, model = candidate.split('/', 1)
            try:
                client = self._get_client(provider)
                resp = await client.completions.create(
                    model=model, prompt=prompt, max_tokens=256, temperature=0.1,
                    stop=['\n\n', '<EOT>']
                )
                return resp.choices[0].text or None
            except Exception:
                continue
        return None

    def register_provider(self, provider_id: str, api_key: str):
        os.environ[f'FORGE_{provider_id.upper()}_KEY'] = api_key
        # Reset cached client to use new key
        self._clients.pop(provider_id, None)

    def set_default_model(self, model_id: str):
        self._default_model = model_id

    def get_default_model(self) -> str:
        return self._default_model

    def list_models(self) -> list:
        from db.models import Model
        with get_session() as db:
            return [
                {
                    'id': m.id, 'display_name': m.display_name,
                    'is_free': m.is_free, 'cost_per_1k_output': m.cost_per_1k_output,
                    'recommended_for': json.loads(m.recommended_for or '[]'),
                }
                for m in db.query(Model).all()
            ]

    def get_usage_stats(self) -> dict:
        return {
            'today_usd': round(self._today_cost_usd, 6),
            'today_tokens': self._today_tokens,
        }

    def _log_usage(self, provider: str, model_id: str, tokens_in: int, tokens_out: int, task_type: str):
        with get_session() as db:
            db.add(UsageLog(
                provider_id=provider, model_id=model_id,
                tokens_in=tokens_in, tokens_out=tokens_out,
                task_type=task_type
            ))
            db.commit()

    async def _clear_rate_limit(self, model_id: str, delay_s: int):
        await asyncio.sleep(delay_s)
        self._rate_limited.discard(model_id)
```

---

## 16. Context Engine — RAG Pipeline

### How it works

1. On workspace open: walk all files, skip `.forgeignore` + `.gitignore` patterns
2. Parse each file with tree-sitter → extract meaningful chunks (functions, classes, blocks)
3. Embed each chunk with `nomic-embed-text` (local model, no API call, runs on CPU)
4. Store vectors + metadata in ChromaDB
5. At inference time: embed user query → similarity search → return top-K chunks
6. Incremental: `watchdog` watches filesystem, re-embeds only changed files

```python
# backend/context/indexer.py
import asyncio, hashlib, os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import chromadb
from sentence_transformers import SentenceTransformer

IGNORE_PATTERNS = [
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build',
    '.next', '.cache', '*.min.js', '*.min.css', '*.lock', '*.map',
    '*.png', '*.jpg', '*.gif', '*.svg', '*.ico', '*.woff', '*.ttf'
]
CHUNK_LINES = 40
CHUNK_OVERLAP = 10
MAX_FILE_SIZE_KB = 500

chroma_client = chromadb.PersistentClient(path=str(Path.home() / '.forge' / 'chroma'))
embedder = SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)


class ContextEngine:
    def __init__(self):
        self._collection = chroma_client.get_or_create_collection('forge_index')
        self._observer = None
        self._status = {'status': 'idle', 'files_indexed': 0, 'total_files': 0}
        self._indexed_hashes: dict[str, str] = {}  # filepath → content hash

    async def start_watcher(self):
        pass  # observer started when workspace is indexed

    async def stop_watcher(self):
        if self._observer:
            self._observer.stop()

    async def index(self, workspace_path: str):
        self._status['status'] = 'indexing'
        files = self._collect_files(workspace_path)
        self._status['total_files'] = len(files)
        self._status['files_indexed'] = 0

        for filepath in files:
            await self._index_file(filepath)
            self._status['files_indexed'] += 1

        self._status['status'] = 'ready'
        self._start_file_watcher(workspace_path)

    def _collect_files(self, workspace_path: str) -> list[str]:
        result = []
        for root, dirs, files in os.walk(workspace_path):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if not self._is_ignored(d)]
            for f in files:
                fpath = os.path.join(root, f)
                if not self._is_ignored(f) and os.path.getsize(fpath) < MAX_FILE_SIZE_KB * 1024:
                    result.append(fpath)
        return result

    def _is_ignored(self, name: str) -> bool:
        import fnmatch
        return any(fnmatch.fnmatch(name, p) for p in IGNORE_PATTERNS)

    async def _index_file(self, filepath: str):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return

        content_hash = hashlib.md5(content.encode()).hexdigest()
        if self._indexed_hashes.get(filepath) == content_hash:
            return  # unchanged, skip

        # Remove old chunks for this file
        try:
            self._collection.delete(where={'file': filepath})
        except Exception:
            pass

        chunks = self._chunk_content(content, filepath)
        if not chunks:
            return

        texts = [c['content'] for c in chunks]
        embeddings = embedder.encode(texts, batch_size=32, show_progress_bar=False).tolist()

        self._collection.add(
            ids=[f'{filepath}:{c["start_line"]}' for c in chunks],
            embeddings=embeddings,
            documents=texts,
            metadatas=[{'file': filepath, 'line': c['start_line']} for c in chunks],
        )
        self._indexed_hashes[filepath] = content_hash

    def _chunk_content(self, content: str, filepath: str) -> list[dict]:
        lines = content.split('\n')
        chunks = []
        i = 0
        while i < len(lines):
            end = min(i + CHUNK_LINES, len(lines))
            chunk_text = '\n'.join(lines[i:end])
            if chunk_text.strip():
                chunks.append({'content': chunk_text, 'start_line': i + 1})
            i += CHUNK_LINES - CHUNK_OVERLAP
        return chunks

    def search(self, query: str, k: int = 8) -> list[dict]:
        if self._collection.count() == 0:
            return []
        embedding = embedder.encode([query]).tolist()
        results = self._collection.query(query_embeddings=embedding, n_results=min(k, self._collection.count()))
        output = []
        for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
            output.append({'content': doc, 'file': meta['file'], 'line': meta['line']})
        return output

    def get_status(self) -> dict:
        return self._status

    def _start_file_watcher(self, workspace_path: str):
        handler = ForgeFileEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, workspace_path, recursive=True)
        self._observer.start()

    async def summarize_repo(self, workspace_path: str) -> str:
        # Collect representative files: README, main files, config files
        key_files = []
        for pattern in ['README.md', 'package.json', 'pyproject.toml', 'setup.py', 'main.py', 'index.ts', 'app.py']:
            candidates = list(Path(workspace_path).rglob(pattern))
            if candidates:
                key_files.append(candidates[0])

        file_contents = []
        for f in key_files[:10]:
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')[:2000]
                file_contents.append(f'## {f.name}\n{content}')
            except Exception:
                pass

        return '\n\n'.join(file_contents)


class ForgeFileEventHandler(FileSystemEventHandler):
    def __init__(self, engine: ContextEngine):
        self.engine = engine

    def on_modified(self, event):
        if not event.is_directory:
            asyncio.create_task(self.engine._index_file(event.src_path))
```

---

## 17. MCP Manager (Complete)

```python
# backend/mcp/manager.py
import subprocess, json, asyncio, os
from pathlib import Path
from db import get_session
from db.models import MCPServer

MCP_REGISTRY = {
    'filesystem': {
        'display_name': 'Filesystem',
        'description': 'Read and write local files',
        'category': 'filesystem',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-filesystem', '{WORKSPACE_PATH}'],
        'required_env_keys': [],
    },
    'github': {
        'display_name': 'GitHub',
        'description': 'Search repos, PRs, issues via GitHub API',
        'category': 'git',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-github'],
        'required_env_keys': ['GITHUB_TOKEN'],
    },
    'brave-search': {
        'display_name': 'Brave Search',
        'description': 'Web search via Brave',
        'category': 'web',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-brave-search'],
        'required_env_keys': ['BRAVE_API_KEY'],
    },
    'memory': {
        'display_name': 'Memory',
        'description': 'Persistent AI memory across sessions',
        'category': 'memory',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-memory'],
        'required_env_keys': [],
    },
    'puppeteer': {
        'display_name': 'Puppeteer (Browser)',
        'description': 'Control a browser, scrape web pages',
        'category': 'web',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-puppeteer'],
        'required_env_keys': [],
    },
    'git': {
        'display_name': 'Git',
        'description': 'Git operations on local repos',
        'category': 'git',
        'command': 'uvx',
        'args': ['mcp-server-git', '--repository', '{WORKSPACE_PATH}'],
        'required_env_keys': [],
    },
    'postgres': {
        'display_name': 'PostgreSQL',
        'description': 'Query PostgreSQL databases',
        'category': 'database',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-postgres', '{DATABASE_URL}'],
        'required_env_keys': ['DATABASE_URL'],
    },
    'slack': {
        'display_name': 'Slack',
        'description': 'Read Slack channels and messages',
        'category': 'communication',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-slack'],
        'required_env_keys': ['SLACK_BOT_TOKEN'],
    },
    'gitlab': {
        'display_name': 'GitLab',
        'description': 'GitLab projects, MRs, issues',
        'category': 'git',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-gitlab'],
        'required_env_keys': ['GITLAB_PERSONAL_ACCESS_TOKEN'],
    },
    'google-maps': {
        'display_name': 'Google Maps',
        'description': 'Location search and directions',
        'category': 'web',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-google-maps'],
        'required_env_keys': ['GOOGLE_MAPS_API_KEY'],
    },
}


class MCPManager:
    def __init__(self):
        self._processes: dict[str, subprocess.Popen] = {}

    async def install(self, mcp_id: str, config: dict) -> dict:
        if mcp_id not in MCP_REGISTRY:
            return {'status': 'error', 'error': f'Unknown MCP: {mcp_id}'}

        spec = MCP_REGISTRY[mcp_id]

        # Validate required config keys
        for key in spec['required_env_keys']:
            if key not in config:
                return {'status': 'error', 'error': f'Missing required config: {key}'}

        # Substitute variables into args
        args = [a.format(**config) for a in spec['args']]

        # Write config to .forge/mcp.json in workspace
        workspace = config.get('WORKSPACE_PATH', '.')
        config_path = Path(workspace) / '.forge' / 'mcp.json'
        config_path.parent.mkdir(exist_ok=True)

        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except Exception:
                pass

        existing[mcp_id] = {
            'command': spec['command'],
            'args': args,
            'env': {k: config[k] for k in spec['required_env_keys'] if k in config},
        }
        config_path.write_text(json.dumps(existing, indent=2))

        # Spawn the MCP server process
        env = {**os.environ, **{k: config[k] for k in spec['required_env_keys'] if k in config}}
        try:
            proc = subprocess.Popen(
                [spec['command']] + args,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            return {'status': 'error', 'error': f'{spec["command"]} not found. Install Node.js and npm.'}

        self._processes[mcp_id] = proc

        # Health check: wait 1s, verify process is alive
        await asyncio.sleep(1.0)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode(errors='ignore')
            return {'status': 'error', 'error': stderr or 'Process exited immediately'}

        # Update database
        with get_session() as db:
            db.merge(MCPServer(
                id=mcp_id,
                display_name=spec['display_name'],
                description=spec['description'],
                category=spec['category'],
                is_installed=True,
                is_running=True,
            ))
            db.commit()

        return {'status': 'ready'}

    async def uninstall(self, mcp_id: str):
        if mcp_id in self._processes:
            self._processes[mcp_id].terminate()
            del self._processes[mcp_id]
        with get_session() as db:
            server = db.query(MCPServer).filter_by(id=mcp_id).first()
            if server:
                server.is_installed = False
                server.is_running = False
                db.commit()

    def list_all(self) -> list:
        result = []
        for mcp_id, spec in MCP_REGISTRY.items():
            proc = self._processes.get(mcp_id)
            is_running = proc is not None and proc.poll() is None
            result.append({
                'id': mcp_id,
                'display_name': spec['display_name'],
                'description': spec['description'],
                'category': spec['category'],
                'required_keys': spec['required_env_keys'],
                'status': 'running' if is_running else ('installed' if self._is_installed(mcp_id) else 'not_installed'),
            })
        return result

    def _is_installed(self, mcp_id: str) -> bool:
        with get_session() as db:
            s = db.query(MCPServer).filter_by(id=mcp_id).first()
            return s is not None and s.is_installed

    async def stop_all(self):
        for proc in self._processes.values():
            try:
                proc.terminate()
            except Exception:
                pass
```

---

## 18. Key Vault Design

**Primary storage:** `vscode.ExtensionContext.secrets` — this uses the OS keychain on all platforms:
- macOS: Keychain Access
- Windows: Credential Manager
- Linux: libsecret (GNOME Keyring / KWallet)

**Key naming convention:**
```
forge.groq.apiKey
forge.gemini.apiKey
forge.openrouter.apiKey
forge.nvidia.apiKey
forge.cerebras.apiKey
forge.anthropic.apiKey
forge.slack.botToken
forge.github.token
...
```

**How keys reach the backend:** The extension host reads all stored keys and injects them as environment variables when spawning the backend subprocess. The backend process reads them from `os.environ`. Keys never touch disk as plaintext.

```typescript
// In BackendService.buildEnv():
const key = await ctx.secrets.get(`forge.${provider}.apiKey`);
if (key) env[`FORGE_${provider.toUpperCase()}_KEY`] = key;
```

**Adding a key (user flow):**
1. User runs `forge.add.provider` command
2. Extension shows QuickPick with provider list
3. User enters key in InputBox with `password: true` (hidden input)
4. Extension stores via `ctx.secrets.store(name, key)`
5. Extension calls `backend.registerProvider(provider, key)` to update live process

**Backup encryption (optional):** For settings export, use Fernet encryption in the Python backend:
```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()  # store this separately
f = Fernet(key)
encrypted = f.encrypt(api_key.encode())
```

---

## 19. Complete Folder Structure

```
forge-vscode/
├── .vscodeignore              # exclude backend/, webview-src/ from vsix
├── .gitignore
├── package.json               # extension manifest (see Section 23)
├── tsconfig.json
├── webpack.config.js          # 3 entry points: extension, chat webview, mcp webview
├── tailwind.config.js
│
├── src/                       # Extension Host (TypeScript)
│   ├── extension.ts           # activate() + deactivate()
│   ├── types.ts               # IPC message types
│   ├── commands/
│   │   └── index.ts           # registerCommands()
│   ├── providers/
│   │   ├── inlineCompleter.ts # ghost text
│   │   └── codeActionProvider.ts  # "Fix with Forge" lightbulb
│   ├── views/
│   │   ├── chatPanel.ts       # WebviewPanel manager
│   │   ├── mcpPanel.ts        # MCP marketplace panel
│   │   └── sidebarProvider.ts # ActivityBar webview view
│   └── services/
│       ├── backendService.ts  # subprocess + HTTP client
│       ├── contextService.ts  # gather file/selection/RAG
│       └── statusBarService.ts
│
├── webview-src/               # React apps (compiled → out/webview/)
│   ├── chat/
│   │   ├── index.tsx          # webpack entry
│   │   ├── App.tsx            # main chat component
│   │   ├── MessageList.tsx
│   │   ├── InputBar.tsx
│   │   ├── ModelSelector.tsx
│   │   └── ContextBadge.tsx
│   └── mcp/
│       ├── index.tsx
│       ├── App.tsx
│       ├── MCPCard.tsx
│       └── InstallWizard.tsx  # step-by-step key wizard
│
├── backend/                   # Python FastAPI service
│   ├── main.py                # FastAPI app entry
│   ├── schemas.py             # Pydantic request/response models
│   ├── requirements.txt
│   ├── router/
│   │   └── model_router.py
│   ├── context/
│   │   └── indexer.py
│   ├── mcp/
│   │   └── manager.py
│   └── db/
│       ├── __init__.py        # init_db(), get_session()
│       └── models.py          # SQLAlchemy ORM models
│
├── out/                       # compiled output (gitignored)
│   ├── extension.js
│   └── webview/
│       ├── chat.js
│       └── mcp.js
│
└── media/
    ├── icon.png               # 128x128 extension icon
    └── forge-logo.svg
```

---

## 20. Complete Code — Extension Host

### webpack.config.js

```javascript
// webpack.config.js
'use strict';
const path = require('path');

const extensionConfig = {
  target: 'node',
  mode: 'none',
  entry: './src/extension.ts',
  output: {
    path: path.resolve(__dirname, 'out'),
    filename: 'extension.js',
    libraryTarget: 'commonjs2',
  },
  externals: { vscode: 'commonjs vscode' },
  resolve: { extensions: ['.ts', '.js'] },
  module: { rules: [{ test: /\.ts$/, loader: 'ts-loader' }] },
  devtool: 'nosources-source-map',
};

const chatWebviewConfig = {
  target: 'web',
  mode: 'none',
  entry: './webview-src/chat/index.tsx',
  output: {
    path: path.resolve(__dirname, 'out', 'webview'),
    filename: 'chat.js',
  },
  resolve: { extensions: ['.tsx', '.ts', '.js'] },
  module: {
    rules: [
      { test: /\.tsx?$/, loader: 'ts-loader' },
      { test: /\.css$/, use: ['style-loader', 'css-loader', 'postcss-loader'] },
    ],
  },
  devtool: 'nosources-source-map',
};

const mcpWebviewConfig = {
  ...chatWebviewConfig,
  entry: './webview-src/mcp/index.tsx',
  output: {
    path: path.resolve(__dirname, 'out', 'webview'),
    filename: 'mcp.js',
  },
};

module.exports = [extensionConfig, chatWebviewConfig, mcpWebviewConfig];
```

### tsconfig.json

```json
{
  "compilerOptions": {
    "module": "commonjs",
    "target": "ES2020",
    "outDir": "./out",
    "lib": ["ES2020", "DOM"],
    "sourceMap": true,
    "rootDir": "./src",
    "strict": true,
    "noImplicitAny": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "exclude": ["node_modules", ".vscode-test", "webview-src"]
}
```

---

## 21. Complete Code — Python Backend

### requirements.txt

```
fastapi==0.111.0
uvicorn==0.29.0
openai==1.35.0
chromadb==0.5.0
sentence-transformers==3.0.0
tree-sitter==0.22.0
watchdog==4.0.0
aiofiles==23.2.0
httpx==0.27.0
cryptography==42.0.0
sqlalchemy==2.0.30
pydantic==2.7.0
python-dotenv==1.0.0
```

### schemas.py

```python
# backend/schemas.py
from pydantic import BaseModel
from typing import Optional


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model_id: Optional[str] = None
    context_chunks: Optional[list[str]] = None
    conversation_id: Optional[str] = None


class CompleteRequest(BaseModel):
    prefix: str
    suffix: str
    language: str
    filepath: Optional[str] = None


class IndexRequest(BaseModel):
    workspace_path: str


class MCPInstallRequest(BaseModel):
    mcp_id: str
    config: dict[str, str] = {}


class ProviderRequest(BaseModel):
    provider_id: str
    api_key: str


class SettingsPatch(BaseModel):
    default_model: Optional[str] = None
    daily_budget_usd: Optional[float] = None
    telemetry_enabled: Optional[bool] = None
```

---

## 22. Complete Code — React Webviews

### webview-src/chat/index.tsx

```tsx
// webview-src/chat/index.tsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';  // Tailwind base

const root = createRoot(document.getElementById('root')!);
root.render(<App />);
```

### webview-src/mcp/App.tsx (MCP Manager)

```tsx
// webview-src/mcp/App.tsx
import React, { useState, useEffect } from 'react';

declare const acquireVsCodeApi: () => { postMessage: (msg: unknown) => void };
const vscode = acquireVsCodeApi();

interface MCP {
  id: string;
  display_name: string;
  description: string;
  category: string;
  required_keys: string[];
  status: 'running' | 'installed' | 'not_installed';
}

export default function MCPApp() {
  const [mcps, setMcps] = useState<MCP[]>([]);
  const [installing, setInstalling] = useState<string | null>(null);
  const [wizardMcp, setWizardMcp] = useState<MCP | null>(null);
  const [keyValues, setKeyValues] = useState<Record<string, string>>({});

  useEffect(() => {
    vscode.postMessage({ type: 'REQUEST_MCP_LIST' });
    window.addEventListener('message', (e) => {
      if (e.data.type === 'MCP_LIST') setMcps(e.data.mcps);
      if (e.data.type === 'MCP_STATUS') {
        if (e.data.status === 'ready' || e.data.status === 'error') setInstalling(null);
        vscode.postMessage({ type: 'REQUEST_MCP_LIST' });
      }
    });
  }, []);

  const startInstall = (mcp: MCP) => {
    if (mcp.required_keys.length === 0) {
      doInstall(mcp, {});
    } else {
      setWizardMcp(mcp);
      setKeyValues({});
    }
  };

  const doInstall = (mcp: MCP, config: Record<string, string>) => {
    setInstalling(mcp.id);
    setWizardMcp(null);
    vscode.postMessage({ type: 'INSTALL_MCP', mcpId: mcp.id, config });
  };

  const statusColor = (status: string) => ({
    running: '#4caf50', installed: '#ff9800', not_installed: 'var(--vscode-descriptionForeground)'
  }[status] ?? 'gray');

  return (
    <div style={{ padding: 16, fontFamily: 'var(--vscode-font-family)' }}>
      <h2 style={{ fontSize: 14, marginBottom: 16, color: 'var(--vscode-foreground)' }}>MCP Servers</h2>

      {mcps.map(mcp => (
        <div key={mcp.id} style={{ marginBottom: 12, padding: 12, background: 'var(--vscode-editor-background)', border: '1px solid var(--vscode-panel-border)', borderRadius: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{mcp.display_name}</div>
              <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)' }}>{mcp.description}</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 10, color: statusColor(mcp.status) }}>● {mcp.status}</span>
              {mcp.status === 'not_installed' && (
                <button
                  onClick={() => startInstall(mcp)}
                  disabled={installing === mcp.id}
                  style={{ padding: '4px 10px', background: 'var(--vscode-button-background)', color: 'var(--vscode-button-foreground)', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}
                >
                  {installing === mcp.id ? 'Installing...' : 'Install'}
                </button>
              )}
            </div>
          </div>
        </div>
      ))}

      {/* Key wizard modal */}
      {wizardMcp && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: 'var(--vscode-editor-background)', padding: 20, borderRadius: 8, width: 320 }}>
            <h3 style={{ marginBottom: 12 }}>Configure {wizardMcp.display_name}</h3>
            {wizardMcp.required_keys.map(k => (
              <div key={k} style={{ marginBottom: 10 }}>
                <label style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>{k}</label>
                <input
                  type="password"
                  value={keyValues[k] ?? ''}
                  onChange={e => setKeyValues(prev => ({ ...prev, [k]: e.target.value }))}
                  style={{ width: '100%', padding: '4px 8px', boxSizing: 'border-box', background: 'var(--vscode-input-background)', color: 'var(--vscode-input-foreground)', border: '1px solid var(--vscode-input-border)', borderRadius: 4 }}
                />
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={() => doInstall(wizardMcp, keyValues)} style={{ flex: 1, padding: '6px', background: 'var(--vscode-button-background)', color: 'var(--vscode-button-foreground)', border: 'none', borderRadius: 4, cursor: 'pointer' }}>Install</button>
              <button onClick={() => setWizardMcp(null)} style={{ flex: 1, padding: '6px', background: 'var(--vscode-button-secondaryBackground)', color: 'var(--vscode-button-secondaryForeground)', border: 'none', borderRadius: 4, cursor: 'pointer' }}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

---

## 23. Package.json — Complete Manifest

```json
{
  "name": "forge-ide",
  "displayName": "Forge — Zero-config AI Coding",
  "description": "AI coding assistant with one-click MCP setup and free model routing",
  "version": "0.1.0",
  "publisher": "coders-ogs",
  "repository": "https://github.com/Coder-s-OG-s/forge-vscode",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["AI", "Machine Learning", "Programming Languages"],
  "keywords": ["ai", "copilot", "mcp", "groq", "gemini", "claude", "coding", "llm", "free"],
  "icon": "media/icon.png",
  "activationEvents": ["onStartupFinished"],
  "main": "./out/extension.js",
  "contributes": {
    "commands": [
      { "command": "forge.chat.open",       "title": "Forge: Open chat",           "icon": "$(comment-discussion)" },
      { "command": "forge.mcp.open",        "title": "Forge: Manage MCPs",         "icon": "$(extensions)" },
      { "command": "forge.index.workspace", "title": "Forge: Index workspace" },
      { "command": "forge.explain.repo",    "title": "Forge: Explain this repo" },
      { "command": "forge.add.provider",    "title": "Forge: Add AI provider",     "icon": "$(key)" },
      { "command": "forge.set.model",       "title": "Forge: Switch model" }
    ],
    "viewsContainers": {
      "activitybar": [
        {
          "id": "forge",
          "title": "Forge AI",
          "icon": "media/forge-logo.svg"
        }
      ]
    },
    "views": {
      "forge": [
        { "type": "webview", "id": "forge.chat",    "name": "Chat",     "icon": "$(comment-discussion)" },
        { "type": "webview", "id": "forge.mcpList", "name": "MCPs",     "icon": "$(extensions)" }
      ]
    },
    "menus": {
      "editor/context": [
        {
          "command": "forge.chat.open",
          "group": "forge",
          "when": "editorHasSelection"
        }
      ]
    },
    "configuration": {
      "title": "Forge",
      "properties": {
        "forge.pythonPath": {
          "type": "string",
          "default": "python3",
          "description": "Path to Python 3.11+ executable"
        },
        "forge.defaultModel": {
          "type": "string",
          "default": "groq/llama-3.3-70b-versatile",
          "description": "Default model ID (e.g. groq/llama-3.3-70b-versatile)"
        },
        "forge.dailyBudgetUsd": {
          "type": "number",
          "default": 0,
          "description": "Daily spend cap in USD. 0 = unlimited. Auto-routes to free models near limit."
        },
        "forge.telemetry": {
          "type": "boolean",
          "default": false,
          "description": "Send anonymous usage telemetry to improve Forge. Off by default."
        },
        "forge.completions.enabled": {
          "type": "boolean",
          "default": true,
          "description": "Enable inline code completions (ghost text)"
        },
        "forge.indexing.enabled": {
          "type": "boolean",
          "default": true,
          "description": "Enable codebase indexing for context-aware AI"
        }
      }
    }
  },
  "scripts": {
    "vscode:prepublish": "npm run package",
    "compile": "webpack",
    "watch": "webpack --watch",
    "package": "webpack --mode production --devtool hidden-source-map",
    "lint": "eslint src --ext ts"
  },
  "devDependencies": {
    "@types/vscode": "^1.85.0",
    "@types/node": "^18.0.0",
    "@types/react": "^18.0.0",
    "@types/react-dom": "^18.0.0",
    "typescript": "^5.3.0",
    "webpack": "^5.0.0",
    "webpack-cli": "^5.0.0",
    "ts-loader": "^9.0.0",
    "css-loader": "^6.0.0",
    "style-loader": "^3.0.0",
    "postcss-loader": "^7.0.0",
    "tailwindcss": "^3.0.0",
    "autoprefixer": "^10.0.0"
  },
  "dependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0",
    "@vscode/webview-ui-toolkit": "^1.4.0",
    "react-markdown": "^9.0.0",
    "react-syntax-highlighter": "^15.0.0",
    "@types/react-syntax-highlighter": "^15.0.0"
  }
}
```

---

## 24. Build Order & Phases

### Phase 1: Core loop working (Weeks 1–2)
**Goal:** Extension activates, backend spawns, health check passes, basic chat works.

1. `npm init` + install devDependencies
2. Create `tsconfig.json` and `webpack.config.js` (from spec)
3. Create `package.json` with manifest (from spec)
4. Create `src/extension.ts` — just activation, status bar, spawn backend
5. Create `src/services/backendService.ts` — subprocess + health check only
6. Create `backend/main.py` — FastAPI with only `/api/health` and `/api/chat`
7. Create `backend/requirements.txt` and `backend/schemas.py`
8. Create `backend/router/model_router.py` — Groq only first, no fallback
9. Create `backend/db/__init__.py` and `backend/db/models.py`
10. Create minimal chat webview (just input + output, no markdown yet)
11. Wire webview → extension host → backend → Groq → stream back

**Verify:**
- `F5` in VSCode launches extension
- Status bar shows "Forge starting..." then "Forge | llama-3.3-70b-versatile"
- Chat panel opens
- Typing a message gets a streaming response from Groq

### Phase 2: Inline completions (Week 3)
1. Add `InlineCompleter` provider
2. Add `/api/complete` endpoint to backend (FIM)
3. Test: ghost text appears after 300ms pause while coding

### Phase 3: Full model router (Week 4)
1. Implement full `ModelRouter` with fallback chain (Groq → Cerebras → Gemini → OpenRouter)
2. Add `forge.add.provider` command
3. Add `forge.set.model` command with model picker
4. Test rate limit handling (mock a 429, verify fallback)

### Phase 4: Codebase RAG (Weeks 5–6)
1. Implement `ContextEngine` with ChromaDB + nomic-embed-text
2. Add file watcher for incremental re-indexing
3. Wire context into chat (top-8 chunks injected)
4. Add context badge in chat UI
5. Test: ask "where is the user authentication logic?" — relevant files appear

### Phase 5: MCP one-click install (Week 7)
1. Implement `MCPManager` with all 10 MCPs
2. Build MCP manager webview with install wizard
3. Wire `INSTALL_MCP` IPC message
4. Test: install filesystem MCP with no terminal, verify process running

### Phase 6: Budget mode + usage tracking (Week 8)
1. Add usage logging to model router
2. Implement budget threshold detection + free-model routing
3. Add `/api/usage` endpoint
4. Update status bar with cost display
5. Add `forge.dailyBudgetUsd` setting

### Phase 7: Polish + publish (Weeks 9–10)
1. "Explain this repo" command
2. Error handling for all failure modes
3. First-install flow (check Python version, install backend deps)
4. Write CHANGELOG.md and README.md for Marketplace
5. Package with `vsce package`
6. Publish to VSCode Marketplace

---

## 25. Free Tier Strategy

### Zero server cost architecture

Everything runs locally on the user's machine:
- Extension: VSCode hosts it, no cost
- Backend: Python process on user's machine, no cost
- Database: SQLite at `~/.forge/forge.db`, no cost
- Embeddings: `nomic-embed-text` runs locally on CPU, no cost
- Vector store: ChromaDB runs locally, no cost

**Total monthly cost to run Forge for 1000 users: $0**

### Free LLM API tiers (as of mid-2026)

| Provider | Free tier | Best free model |
|---|---|---|
| Groq | 30 RPM, 1000 RPD, 100K TPD | llama-3.3-70b-versatile |
| Google Gemini | 1500 RPD, 1M context | gemini-2.5-flash |
| Cerebras | ~1M tokens/day | llama-3.3-70b |
| OpenRouter | 30+ free models | qwen3-32b:free, llama-3.1-70b:free |
| NVIDIA NIM | Limited free credits | llama-3.1-70b-instruct |
| Ollama | Unlimited local | any model user downloads |

**A developer using Forge for 8 hours/day with reasonable usage will hit $0 in API costs** using the free tier routing.

### Permanent free tiers

- **Students:** GitHub Student Pack integration (check `github.com/education` API)
- **Open source:** Projects with public GitHub repos get free Forge Pro features
- **Solo devs:** Core features free forever (chat, MCP, inline completions)

### Monetization path (when you have users)

| Tier | Price | Features |
|---|---|---|
| Free | $0 | Chat, completions, 10 MCPs, free model routing |
| Pro | ₹499/mo | Cloud key sync, unlimited history, priority support |
| Team | ₹1999/seat/mo | Shared conventions, team context, audit logs |
| Enterprise | Custom | SSO, compliance, dedicated support |

---

## 26. Provider Configuration Reference

### All supported providers and their base URLs

```python
# Use these exact base_url values with the OpenAI SDK
PROVIDERS = {
    'groq': {
        'base_url': 'https://api.groq.com/openai/v1',
        'key_env':  'FORGE_GROQ_KEY',
        'free':     True,
        'models':   ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'gemma2-9b-it'],
    },
    'gemini': {
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'key_env':  'FORGE_GEMINI_KEY',
        'free':     True,
        'models':   ['gemini-2.5-flash', 'gemini-2.5-pro'],
    },
    'cerebras': {
        'base_url': 'https://api.cerebras.ai/v1',
        'key_env':  'FORGE_CEREBRAS_KEY',
        'free':     True,
        'models':   ['llama3.3-70b', 'llama3.1-8b'],
    },
    'openrouter': {
        'base_url': 'https://openrouter.ai/api/v1',
        'key_env':  'FORGE_OPENROUTER_KEY',
        'free':     True,
        'models':   ['qwen/qwen3-32b:free', 'meta-llama/llama-3.1-70b-instruct:free'],
    },
    'nvidia': {
        'base_url': 'https://integrate.api.nvidia.com/v1',
        'key_env':  'FORGE_NVIDIA_KEY',
        'free':     False,
        'models':   ['meta/llama-3.1-70b-instruct', 'mistralai/codestral-22b-instruct-v0.1'],
    },
    'anthropic': {
        'base_url': 'https://api.anthropic.com/v1',
        'key_env':  'FORGE_ANTHROPIC_KEY',
        'free':     False,
        'models':   ['claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5'],
    },
    'ollama': {
        'base_url': 'http://localhost:11434/v1',
        'key_env':  None,  # No key needed
        'free':     True,
        'models':   ['llama3.2', 'codellama', 'qwen2.5-coder'],
    },
}
```

---

## 27. Testing Checklist

### Phase 1 — Core (must pass before moving on)
- [ ] `F5` in VSCode launches the extension without errors
- [ ] Status bar shows "Forge starting..." within 1 second
- [ ] Status bar updates to active model name within 3 seconds
- [ ] Chat panel opens with `forge.chat.open` command
- [ ] Typing a message and pressing Enter sends it to Groq
- [ ] Response streams character-by-character
- [ ] No response on empty Groq key → error message shown

### Phase 2 — Completions
- [ ] Ghost text appears after 300ms pause in any file type
- [ ] Tab accepts the completion
- [ ] Escape dismisses it
- [ ] Completions disabled in comments and strings (optional v1)

### Phase 3 — Model Router
- [ ] `forge.add.provider` prompts for key, stores it, works immediately
- [ ] `forge.set.model` shows all configured models
- [ ] Switching to Gemini works without restart
- [ ] When Groq rate-limited (mock 429), auto-switches to Cerebras

### Phase 4 — RAG
- [ ] Status bar shows "indexing..." during workspace index
- [ ] After indexing, chat responses reference actual project files
- [ ] Context badge in chat shows files being referenced
- [ ] File changes trigger re-indexing

### Phase 5 — MCP
- [ ] MCP manager panel opens
- [ ] Filesystem MCP installs with no terminal
- [ ] MCPs requiring API keys show wizard
- [ ] MCP status shows "running" with green dot
- [ ] Uninstall stops the process

### Phase 6 — Budget
- [ ] Cost appears in status bar after first response
- [ ] Setting `dailyBudgetUsd: 0.01` and spending that amount triggers free-model routing
- [ ] Usage resets at midnight (or on workspace reload)

---

*End of Forge IDE Extension Specification*

**Version:** 1.0 — July 2026  
**Maintained by:** Coder's OG's (github.com/Coder-s-OG-s)  
**Lead:** Ayush Patel (github.com/Ayush-Patel-56)
