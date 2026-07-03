// src/services/backendService.ts
import * as cp from 'child_process';
import * as vscode from 'vscode';

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

  // --- Streaming chat ---------------------------------------------------------

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

  // --- Inline completions ------------------------------------------------------

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

  // --- Workspace indexing --------------------------------------------------------

  async indexWorkspace(workspacePath: string): Promise<void> {
    await fetch(`${BASE_URL}/api/index`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_path: workspacePath }),
    });
  }

  // --- Provider management -------------------------------------------------------

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
