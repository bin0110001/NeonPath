import { FormEvent, useCallback, useEffect, useState } from "react";
import { type ItemKind, type Record_, profileApi } from "./api";
import { type Field, type Values, toForm, toPayload } from "./fields";

export function ItemsEditor({
  profileId,
  kind,
  title,
  fields,
  summary,
}: {
  profileId: string;
  kind: ItemKind;
  title: string;
  fields: Field[];
  summary: (record: Record_) => string;
}) {
  const [items, setItems] = useState<Record_[]>([]);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<Values>(toForm(fields));
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    profileApi
      .items(profileId, kind)
      .then((loaded) => {
        if (!cancelled) {
          setItems(loaded);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : `Unable to load ${title.toLowerCase()}`);
      });
    return () => {
      cancelled = true;
    };
  }, [profileId, kind, title, tick]);

  const open = useCallback(
    (record?: Record_) => {
      setEditing(record ? record.id : "new");
      setForm(toForm(fields, record));
      setError(null);
    },
    [fields],
  );

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const payload = toPayload(fields, form);
      if (editing === "new") await profileApi.addItem(profileId, kind, payload);
      else if (editing) await profileApi.saveItem(profileId, kind, editing, payload);
      setEditing(null);
      setTick((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save");
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await profileApi.deleteItem(profileId, kind, id);
      setTick((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to delete");
    }
  }

  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      {error && <p role="alert">{error}</p>}
      {items.length === 0 ? <p>None yet.</p> : (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              {summary(item)} <button onClick={() => open(item)}>Edit</button>{" "}
              <button onClick={() => void remove(item.id)}>Delete</button>
            </li>
          ))}
        </ul>
      )}
      {editing === null ? (
        <button onClick={() => open()}>Add {title.toLowerCase().replace(/s$/, "")}</button>
      ) : (
        <form onSubmit={(event) => void save(event)} aria-label={`${title} form`}>
          {fields.map((f) => (
            <div key={f.name}>
              {f.type === "checkbox" ? (
                <label>
                  <input type="checkbox" checked={Boolean(form[f.name])} onChange={(e) => setForm({ ...form, [f.name]: e.target.checked })} /> {f.label}
                </label>
              ) : (
                <>
                  <label htmlFor={`${kind}-${f.name}`}>{f.label}</label>{" "}
                  {f.type === "textarea" ? (
                    <textarea id={`${kind}-${f.name}`} rows={3} value={String(form[f.name])} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} />
                  ) : (
                    <input
                      id={`${kind}-${f.name}`}
                      type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                      required={f.required}
                      value={String(form[f.name])}
                      onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
                    />
                  )}
                  {f.type === "list" && <small> (comma separated)</small>}
                </>
              )}
            </div>
          ))}
          <button type="submit">Save</button> <button type="button" onClick={() => setEditing(null)}>Cancel</button>
        </form>
      )}
    </section>
  );
}
