// src/services/backendService.ts
import * as cp from 'child_process';
import * as vscode from 'vscode';
import { StatusBarService } from './statusBarService';
import { ForgeStreamEvent } from '../types';

const PORT = 7822;
const BASE_URL = `http://localhost:${PORT}`;
const HEALTH_POLL_INTERVAL_MS = 200;
const HEALTH_TIMEOUT_MS = 60_000;
const MIN_PYTHON_MAJOR = 3;
const MIN_PYTHON_MINOR = 11;
const MAX_AUTO_RESTART_OFFERS = 2;

export class BackendService {
  private proc: cp.ChildProcess | undefined;
  private activeModel = 'groq/llama-3.3-70b-versatile';
  private readonly outputChannel = vscode.window.createOutputChannel('Forge Backend');
  private pythonExecutable = 'python3';
  private stopRequested = false;
  private restartOffersUsed = 0;
  private statusBar: StatusBarService | undefined;

  constructor(private ctx: vscode.ExtensionContext) {}

  setStatusBarService(statusBar: StatusBarService): void {
    this.statusBar = statusBar;
  }

  async start(): Promise<void> {
    this.stopRequested = false;

    const pythonExecutable = await this.resolvePython();
    this.pythonExecutable = pythonExecutable;

    await this.ensureDependencies(pythonExecutable);

    const backendPath = this.ctx.asAbsolutePath('backend/main.py');

    // Inject stored API keys as env vars
    const env = await this.buildEnv();

    this.proc = cp.spawn(pythonExecutable, [backendPath, '--port', String(PORT)], {
      env,
      stdio: 'pipe',
      cwd: this.ctx.asAbsolutePath('backend'),
    });

    this.proc.stderr?.on('data', (d: Buffer) => {
      const msg = d.toString().trim();
      if (msg) {
        console.error('[forge-backend]', msg);
        this.outputChannel.appendLine(msg);
      }
    });

    this.proc.on('exit', (code) => {
      if (code !== 0 && code !== null) {
        console.error(`[forge-backend] exited with code ${code}`);
        this.outputChannel.appendLine(`[forge-backend] exited with code ${code}`);
        if (!this.stopRequested) {
          this.handleUnexpectedExit(code);
        }
      }
    });

    await this.waitForHealth();
  }

  // --- First-install experience -----------------------------------------------

  /**
   * Resolve a usable Python 3.11+ executable. Tries the configured
   * forge.pythonPath first, then falls back to plain 'python'.
   */
  private async resolvePython(): Promise<string> {
    const config = vscode.workspace.getConfiguration('forge');
    const configured = config.get<string>('pythonPath', 'python3');

    if (await this.isPythonUsable(configured)) return configured;
    if (configured !== 'python' && await this.isPythonUsable('python')) return 'python';

    throw new Error('Forge needs Python 3.11+ — install it and/or set forge.pythonPath');
  }

  private async isPythonUsable(exe: string): Promise<boolean> {
    try {
      const out = await this.runCommand(exe, ['--version'], 10_000);
      const match = out.match(/(\d+)\.(\d+)/);
      if (!match) return false;
      const major = parseInt(match[1], 10);
      const minor = parseInt(match[2], 10);
      return major > MIN_PYTHON_MAJOR || (major === MIN_PYTHON_MAJOR && minor >= MIN_PYTHON_MINOR);
    } catch {
      return false;
    }
  }

  /** Verify required backend packages are importable; offer to install if not. */
  private async ensureDependencies(pythonExecutable: string): Promise<void> {
    const REQUIRED_MODULES = ['fastapi', 'uvicorn', 'openai', 'chromadb', 'sentence_transformers', 'sqlalchemy', 'watchdog'];
    const checkScript = `import ${REQUIRED_MODULES.join(', ')}`;

    try {
      await this.runCommand(pythonExecutable, ['-c', checkScript], 30_000);
      return; // all good
    } catch {
      // fall through to install prompt
    }

    const choice = await vscode.window.showInformationMessage(
      'Forge: backend dependencies missing. Install now? (~2GB, includes PyTorch)',
      'Install',
      'Cancel'
    );

    if (choice !== 'Install') {
      throw new Error('Forge backend dependencies are missing. Choose "Install" when prompted, or install backend/requirements.txt manually.');
    }

    const requirementsPath = this.ctx.asAbsolutePath('backend/requirements.txt');

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'Forge: installing backend dependencies...' },
      async () => {
        await this.pipInstall(pythonExecutable, requirementsPath);
      }
    );
  }

  private pipInstall(pythonExecutable: string, requirementsPath: string): Promise<void> {
    this.outputChannel.show(true);
    this.outputChannel.appendLine(`[forge-backend] installing dependencies: ${pythonExecutable} -m pip install -r ${requirementsPath}`);

    return new Promise((resolve, reject) => {
      const proc = cp.spawn(pythonExecutable, ['-m', 'pip', 'install', '-r', requirementsPath], { stdio: 'pipe' });

      const streamLines = (d: Buffer) => {
        const text = d.toString();
        for (const line of text.split(/\r?\n/)) {
          if (line) this.outputChannel.appendLine(line);
        }
      };

      proc.stdout?.on('data', streamLines);
      proc.stderr?.on('data', streamLines);
      proc.on('error', (err) => reject(err));
      proc.on('exit', (code) => {
        if (code === 0) resolve();
        else reject(new Error(`pip install failed with exit code ${code}. See "Forge Backend" output for details.`));
      });
    });
  }

  /** Spawn a short-lived command and collect combined stdout+stderr, with a timeout. */
  private runCommand(exe: string, args: string[], timeoutMs: number): Promise<string> {
    return new Promise((resolve, reject) => {
      let out = '';
      let proc: cp.ChildProcess;
      try {
        proc = cp.spawn(exe, args, { stdio: 'pipe' });
      } catch (err) {
        reject(err);
        return;
      }

      const timer = setTimeout(() => {
        proc.kill();
        reject(new Error(`Command timed out: ${exe} ${args.join(' ')}`));
      }, timeoutMs);

      proc.stdout?.on('data', (d: Buffer) => (out += d.toString()));
      proc.stderr?.on('data', (d: Buffer) => (out += d.toString()));
      proc.on('error', (err) => {
        clearTimeout(timer);
        reject(err);
      });
      proc.on('exit', (code) => {
        clearTimeout(timer);
        if (code === 0) resolve(out);
        else reject(new Error(`Command exited with code ${code}: ${out.trim()}`));
      });
    });
  }

  // --- Crash visibility ---------------------------------------------------------

  private handleUnexpectedExit(code: number | null): void {
    this.statusBar?.setError();

    if (this.restartOffersUsed >= MAX_AUTO_RESTART_OFFERS) {
      vscode.window.showErrorMessage(`Forge backend stopped unexpectedly (code ${code}). See Forge Backend output.`);
      return;
    }

    this.restartOffersUsed++;
    void vscode.window.showErrorMessage(
      `Forge backend stopped unexpectedly (code ${code}). See Forge Backend output.`,
      'Restart'
    ).then((choice) => {
      if (choice !== 'Restart') return;
      this.start().then(() => {
        this.statusBar?.setReady(this.getActiveModel());
      }).catch((err) => {
        this.statusBar?.setError();
        vscode.window.showErrorMessage(`Forge: restart failed — ${err.message}`);
      });
    });
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
    workspace_path?: string;
    thinking?: boolean;
    effort?: string;
    images?: { name: string; mime: string; dataBase64: string }[];
    mode?: 'manual' | 'auto' | 'edit' | 'plan';
    autoFallback?: boolean;
  }): AsyncGenerator<string | ForgeStreamEvent> {
    const { images, mode, autoFallback, ...rest } = payload;
    const body = {
      ...rest,
      images: images?.map(img => ({ name: img.name, mime: img.mime, data_base64: img.dataBase64 })),
      mode,
      auto_fallback: autoFallback,
    };
    const res = await fetch(`${BASE_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
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
            const parsed = JSON.parse(data) as { content?: string } & Partial<ForgeStreamEvent>;
            if (parsed.event) {
              yield parsed as ForgeStreamEvent;
            } else if (parsed.content) {
              yield parsed.content;
            }
          } catch { /* ignore malformed SSE lines */ }
        }
      }
    }
  }

  async sendApproval(approvalId: string, decision: 'allow' | 'deny' | 'other', detail?: string): Promise<void> {
    await fetch(`${BASE_URL}/api/chat/approval`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approval_id: approvalId, decision, detail }),
    });
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

  async getIndexStatus(): Promise<{ status: string; files_indexed: number; total_files: number }> {
    try {
      const res = await fetch(`${BASE_URL}/api/index/status`, {
        signal: AbortSignal.timeout(2000),
      });
      if (!res.ok) throw new Error(`Index status API error: ${res.status}`);
      return await res.json();
    } catch {
      return { status: 'unknown', files_indexed: 0, total_files: 0 };
    }
  }

  // --- Provider management -------------------------------------------------------

  async registerProvider(provider: string, apiKey: string, baseUrl?: string): Promise<void> {
    await fetch(`${BASE_URL}/api/providers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: provider, api_key: apiKey, base_url: baseUrl }),
    });
  }

  async getAvailableModels(): Promise<{ id: string; display_name: string; is_free: boolean; cost_per_1k_output: number }[]> {
    const res = await fetch(`${BASE_URL}/api/models`);
    return res.json();
  }

  async addModel(payload: {
    provider_id: string;
    model_id: string;
    display_name?: string;
    base_url?: string;
    is_free?: boolean;
    context_window?: number;
  }): Promise<{ id: string; display_name: string; is_free: boolean; context_window: number }> {
    const res = await fetch(`${BASE_URL}/api/models`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Add-model API error: ${res.status}`);
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

  async getUsage(): Promise<{ today_usd: number; today_tokens: number; by_model?: { model_id: string; tokens_in: number; tokens_out: number; cost_usd: number }[] }> {
    const res = await fetch(`${BASE_URL}/api/usage`);
    return res.json();
  }

  async setDailyBudget(usd: number): Promise<void> {
    try {
      await fetch(`${BASE_URL}/api/settings`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ daily_budget_usd: usd }),
      });
    } catch {
      // Backend may not be up yet; non-fatal
    }
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

  async uninstallMCP(mcpId: string): Promise<void> {
    await fetch(`${BASE_URL}/api/mcp/${mcpId}`, { method: 'DELETE' });
  }

  async startMCP(mcpId: string, workspacePath: string): Promise<{ status: string; error?: string }> {
    const res = await fetch(`${BASE_URL}/api/mcp/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mcp_id: mcpId, workspace_path: workspacePath }),
    });
    return res.json();
  }

  async relaunchMCPs(workspacePath: string): Promise<void> {
    try {
      await fetch(`${BASE_URL}/api/mcp/relaunch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace_path: workspacePath }),
      });
    } catch {
      // Non-fatal; MCPs simply stay unstarted
    }
  }

  async sendExplainRepo(workspacePath: string): Promise<string> {
    const res = await fetch(`${BASE_URL}/api/explain-repo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_path: workspacePath }),
    });
    if (!res.ok) throw new Error(`Explain-repo API error: ${res.status}`);
    const data = await res.json() as { summary: string };
    return data.summary ?? '';
  }

  async queryContext(query: string, k = 8): Promise<{ content: string; file: string; line: number }[]> {
    const res = await fetch(`${BASE_URL}/api/context/chunks?q=${encodeURIComponent(query)}&k=${k}`);
    return res.json();
  }

  stop(): void {
    this.stopRequested = true;
    this.proc?.kill('SIGTERM');
  }
}
