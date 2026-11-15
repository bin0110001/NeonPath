import { useCallback, useEffect, useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface TaskItem {
  id: string;
  task_type: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  attempts: number;
  max_attempts: number;
  created_at: string;
  error_code: string | null;
  error_message: string | null;
}

export function TaskList() {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [failedOnly, setFailedOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const query = failedOnly ? "?status=FAILED" : "";

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiUrl}/api/v1/tasks${query}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Unable to load tasks (${response.status})`);
        return response.json() as Promise<TaskItem[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setTasks(data);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load tasks");
      });
    return () => {
      cancelled = true;
    };
  }, [query, tick]);

  const retry = useCallback(async (id: string) => {
    const response = await fetch(`${apiUrl}/api/v1/tasks/${id}/retry`, { method: "POST" });
    if (!response.ok) setError(`Unable to retry task (${response.status})`);
    setTick((value) => value + 1);
  }, []);

  return (
    <section aria-label="Background tasks">
      <h2>Background tasks</h2>
      <label>
        <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} /> Failed only
      </label>{" "}
      <button onClick={() => setTick((value) => value + 1)}>Refresh</button>
      {error && <p role="alert">{error}</p>}
      {tasks.length === 0 ? (
        <p>No tasks.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Status</th>
              <th>Attempts</th>
              <th>Created</th>
              <th>Error</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => (
              <tr key={task.id}>
                <td>{task.task_type}</td>
                <td>{task.status}</td>
                <td>
                  {task.attempts}/{task.max_attempts}
                </td>
                <td>{new Date(task.created_at).toLocaleString()}</td>
                <td>{task.error_code ? `${task.error_code}: ${task.error_message ?? ""}` : ""}</td>
                <td>
                  {task.status === "FAILED" && <button onClick={() => void retry(task.id)}>Retry</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
