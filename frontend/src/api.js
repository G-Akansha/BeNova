// Small fetch helpers shared by all components. All calls go through the Vite /api proxy.

export function errorText(detail, status) {
  if (!detail) return `Request failed (HTTP ${status})`;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('; '); // FastAPI 422
  return JSON.stringify(detail);
}

export async function apiGet(path, signal) {
  const res = await fetch(path, { signal });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(data.detail, res.status));
  return data;
}

export async function apiPost(path, body, signal) {
  const isForm = body instanceof FormData;
  const res = await fetch(path, {
    method: 'POST',
    headers: isForm ? undefined : { 'Content-Type': 'application/json' },
    body: isForm ? body : JSON.stringify(body),
    signal,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(data.detail, res.status));
  return data;
}

export const STATUS_META = {
  GROUNDED_ANSWER: { label: 'Answered from documents', cls: 'bg-emerald-100 text-emerald-800 border-emerald-200' },
  CONFLICT_DETECTED: { label: 'Documents disagree', cls: 'bg-amber-100 text-amber-900 border-amber-200' },
  CLARIFICATION_NEEDED: { label: 'Needs clarification', cls: 'bg-sky-100 text-sky-900 border-sky-200' },
  NOT_FOUND: { label: 'Not found in documents', cls: 'bg-slate-200 text-slate-800 border-slate-300' },
};

export const EMPTY_FILTERS = { format: 'ALL', environment: '', version: '', doc_id: '' };
