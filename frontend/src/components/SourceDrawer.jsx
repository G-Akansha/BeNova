import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { apiGet } from '../api';

// Opens any passage by id (works for citations that are not in the top-5 list).
export default function SourceDrawer({ passageId, onClose }) {
  const [state, setState] = useState({ loading: false, passage: null, error: null });

  useEffect(() => {
    if (!passageId) return;
    const ctrl = new AbortController();
    setState({ loading: true, passage: null, error: null });
    apiGet(`/api/passages/${encodeURIComponent(passageId)}`, ctrl.signal)
      .then((p) => setState({ loading: false, passage: p, error: null }))
      .catch((e) => { if (e.name !== 'AbortError') setState({ loading: false, passage: null, error: e.message }); });
    return () => ctrl.abort();
  }, [passageId]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!passageId) return null;
  const p = state.passage;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Source passage">
      <button className="absolute inset-0 bg-slate-900/30" onClick={onClose} aria-label="Close" />
      <div className="relative w-full max-w-lg h-full bg-white shadow-xl overflow-y-auto p-5">
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-base font-bold text-slate-900">Source passage</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100" aria-label="Close"><X className="w-5 h-5" /></button>
        </div>
        {state.loading && <p className="mt-4 text-sm text-slate-500">Loading...</p>}
        {state.error && <p className="mt-4 text-sm text-rose-700">{state.error}</p>}
        {p && (
          <div className="mt-4 space-y-3 text-sm">
            <div>
              <p className="font-semibold text-slate-900">{p.doc_title}</p>
              <p className="text-indigo-700">{p.section_heading}{p.page_number ? ` (page ${p.page_number})` : ''}</p>
            </div>
            <dl className="grid grid-cols-2 gap-2 text-xs">
              {[['File', p.source_filename], ['Format', p.doc_format], ['Version', p.version], ['Scope', p.environment],
                ['Effective date', p.effective_date], ['Passage id', p.passage_id]].map(([k, v]) => (
                <div key={k}><dt className="text-slate-400">{k}</dt><dd className="font-mono text-slate-800 break-all">{v}</dd></div>
              ))}
            </dl>
            <p className="p-3 rounded-lg bg-slate-50 border border-slate-200 whitespace-pre-line leading-relaxed text-slate-800">{p.text}</p>
          </div>
        )}
      </div>
    </div>
  );
}
