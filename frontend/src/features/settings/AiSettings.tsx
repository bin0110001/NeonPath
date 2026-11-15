import { FormEvent, useEffect, useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1/ai`;

interface ProviderInfo {
  label: string;
  needs_key: boolean;
  needs_endpoint: boolean;
}
interface AiConfig {
  enabled: boolean;
  provider: string;
  model: string;
  endpoint: string;
  api_key_set: boolean;
  source: string;
  providers: Record<string, ProviderInfo>;
}
interface TestResult {
  ok: boolean;
  provider: string;
  model: string;
  latency_ms: number | null;
  error: string | null;
}

export function AiSettings() {
  const [config, setConfig] = useState<AiConfig | null>(null);
  const [form, setForm] = useState({ enabled: false, provider: "fixture", model: "", endpoint: "" });
  const [result, setResult] = useState<TestResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(`${base}/config`)
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load AI settings (${response.status})`);
        return response.json() as Promise<AiConfig>;
      })
      .then((loaded) => {
        setConfig(loaded);
        setForm({ enabled: loaded.enabled, provider: loaded.provider, model: loaded.model, endpoint: loaded.endpoint });
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load AI settings"));
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const response = await fetch(`${base}/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    if (!response.ok) {
      setError(`Unable to save (${response.status})`);
      return;
    }
    setConfig((await response.json()) as AiConfig);
    setMessage("Saved.");
    setResult(null);
  }

  async function test() {
    setBusy(true);
    setResult(null);
    try {
      const response = await fetch(`${base}/test`, { method: "POST" });
      setResult((await response.json()) as TestResult);
    } catch {
      setError("Unable to reach the API");
    } finally {
      setBusy(false);
    }
  }

  if (!config) return error ? <div role="alert">{error}</div> : <p>Loading AI settings...</p>;
  const info = config.providers[form.provider];

  return (
    <section aria-label="AI settings">
      <h2>AI provider</h2>
      <p>
        AI is optional. With it off, everything except AI requirement extraction and semantic evaluation works as normal.
        Settings source: {config.source}.
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <form onSubmit={(event) => void save(event)}>
        <label>
          <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Enable AI
        </label>
        <div>
          <label htmlFor="ai-provider">Provider</label>{" "}
          <select id="ai-provider" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}>
            {Object.entries(config.providers).map(([key, value]) => (
              <option key={key} value={key}>
                {value.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="ai-model">Model</label>{" "}
          <input id="ai-model" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
        </div>
        {info?.needs_endpoint && (
          <div>
            <label htmlFor="ai-endpoint">Endpoint</label>{" "}
            <input id="ai-endpoint" value={form.endpoint} onChange={(e) => setForm({ ...form, endpoint: e.target.value })} />
          </div>
        )}
        {info?.needs_key && (
          <p>
            API key: <strong>{config.api_key_set ? "set" : "not set"}</strong>. The key is read from the{" "}
            <code>AI_API_KEY</code> environment variable and is never shown or stored here.
          </p>
        )}
        <button type="submit">Save</button>{" "}
        <button type="button" disabled={busy} onClick={() => void test()}>
          {busy ? "Testing..." : "Test connection"}
        </button>
      </form>
      {result && (
        <p role="status" data-testid="test-result">
          {result.ok
            ? `Connected to ${result.provider} (${result.model}) in ${result.latency_ms} ms.`
            : `Connection failed: ${result.error}`}
        </p>
      )}
    </section>
  );
}
