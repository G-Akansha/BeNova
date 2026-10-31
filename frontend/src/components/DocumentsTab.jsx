import { useEffect, useRef, useState } from 'react';
import { UploadCloud, CheckCircle, AlertCircle } from 'lucide-react';
import { apiGet, apiPost } from '../api';

export default function DocumentsTab({ bootstrap, corpusVersion, onUploaded, onOpenPassage }) {
  const docs = bootstrap?.document_inventory || [];
  const opts = bootstrap?.available_filters || { environments: [], versions: [] };

  return (
    <div className="space-y-6">
      <UploadForm opts={opts} onUploaded={onUploaded} />
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="text-base font-bold text-slate-900">Documents ({docs.length})</h2>
        <p className="text-xs text-slate-500 mb-3">Version, scope and effective date are used for filtering and conflict detection. "Unknown" means not provided.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-500 uppercase border-b border-slate-200">
              <tr>{['Title', 'File', 'Format', 'Version', 'Scope', 'Effective', 'Passages'].map((h) => <th key={h} className="py-2 pr-3">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map((d) => (
                <tr key={d.doc_id}>
                  <td className="py-2 pr-3 font-medium text-slate-900">{d.title}{d.doc_id.startsWith('DOC-UP-') && <span className="ml-2 text-xs px-1.5 rounded bg-indigo-100 text-indigo-800">uploaded</span>}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-slate-500">{d.filename}</td>
                  <td className="py-2 pr-3">{d.format}</td>
                  <td className="py-2 pr-3">{d.version}</td>
                  <td className="py-2 pr-3">{d.environment}</td>
                  <td className="py-2 pr-3">{d.effective_date}</td>
                  <td className="py-2 pr-3">{d.passage_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <PassageExplorer docs={docs} corpusVersion={corpusVersion} onOpenPassage={onOpenPassage} />
    </div>
  );
}

function UploadForm({ opts, onUploaded }) {
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [meta, setMeta] = useState({ title: '', version: '', environment: '', effective_date: '' });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const set = (k) => (e) => setMeta({ ...meta, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (!file) { setMsg({ ok: false, text: 'Choose a .md, .html, .txt or .pdf file first.' }); return; }
    if (file.size > 10 * 1024 * 1024) { setMsg({ ok: false, text: 'File is larger than 10 MB.' }); return; }
    const fd = new FormData();
    fd.append('file', file);
    fd.append('document_title', meta.title);
    fd.append('version', meta.version);
    fd.append('environment', meta.environment);
    fd.append('effective_date', meta.effective_date);
    setBusy(true); setMsg(null);
    try {
      const r = await apiPost('/api/ingest', fd);
      setMsg({ ok: true, text: `Indexed "${r.title}" (${r.format}): ${r.passage_count} passages. It is searchable now.` });
      setFile(null);
      setMeta({ title: '', version: '', environment: '', effective_date: '' });
      if (fileRef.current) fileRef.current.value = '';      // really clear the file input
      onUploaded();
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const input = 'w-full px-2 py-1.5 text-sm border border-slate-300 rounded bg-white';
  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5">
      <h2 className="text-base font-bold text-slate-900 flex items-center gap-2"><UploadCloud className="w-5 h-5 text-indigo-600" aria-hidden /> Add a document</h2>
      <p className="text-xs text-slate-500 mb-3">.md, .html, .txt (UTF-8) or text-based .pdf, up to 10 MB. Metadata is optional - leave it blank if unknown.</p>
      <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
        <div className="sm:col-span-2 lg:col-span-1">
          <label htmlFor="up-file" className="block text-xs font-semibold text-slate-600 mb-1">File</label>
          <input id="up-file" ref={fileRef} type="file" accept=".md,.markdown,.html,.htm,.txt,.pdf"
            onChange={(e) => { const f = e.target.files?.[0] || null; setFile(f); if (f && !meta.title) setMeta((m) => ({ ...m, title: f.name.replace(/\.[^.]+$/, '').replace(/_/g, ' ') })); }}
            className="w-full text-sm" />
        </div>
        <Field id="up-title" label="Title"><input id="up-title" className={input} value={meta.title} onChange={set('title')} /></Field>
        <Field id="up-ver" label="Version">
          <input id="up-ver" className={input} list="ver-list" placeholder="Unknown" value={meta.version} onChange={set('version')} />
          <datalist id="ver-list">{opts.versions.map((v) => <option key={v} value={v} />)}</datalist>
        </Field>
        <Field id="up-env" label="Environment / scope">
          <input id="up-env" className={input} list="env-list" placeholder="Unknown" value={meta.environment} onChange={set('environment')} />
          <datalist id="env-list">{['All', ...opts.environments].map((v) => <option key={v} value={v} />)}</datalist>
        </Field>
        <Field id="up-date" label="Effective date"><input id="up-date" type="date" className={input} value={meta.effective_date} onChange={set('effective_date')} /></Field>
        <button type="submit" disabled={busy}
          className="sm:col-span-2 lg:col-span-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white font-semibold text-sm">
          {busy ? 'Parsing and indexing...' : 'Upload and index'}
        </button>
      </form>
      {msg && (
        <p role={msg.ok ? 'status' : 'alert'} className={`mt-3 p-2 rounded text-sm flex gap-2 ${msg.ok ? 'bg-emerald-50 text-emerald-800' : 'bg-rose-50 text-rose-800'}`}>
          {msg.ok ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}{msg.text}
        </p>
      )}
    </section>
  );
}

function Field({ id, label, children }) {
  return (<div><label htmlFor={id} className="block text-xs font-semibold text-slate-600 mb-1">{label}</label>{children}</div>);
}

function PassageExplorer({ docs, corpusVersion, onOpenPassage }) {
  const [docId, setDocId] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0, total_pages: 0 });
  const [error, setError] = useState(null);

  useEffect(() => {
    const ctrl = new AbortController();
    const q = new URLSearchParams({ page: String(page), page_size: '8', ...(docId ? { doc_id: docId } : {}) });
    apiGet(`/api/passages?${q}`, ctrl.signal).then((d) => { setData(d); setError(null); })
      .catch((e) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => ctrl.abort();
  }, [docId, page, corpusVersion]);   // corpusVersion -> refresh after uploads

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 className="text-base font-bold text-slate-900">Indexed passages ({data.total})</h2>
        <label className="text-sm text-slate-600 flex items-center gap-2">Document
          <select value={docId} onChange={(e) => { setDocId(e.target.value); setPage(1); }} className="px-2 py-1 border border-slate-300 rounded text-sm">
            <option value="">All</option>
            {docs.map((d) => <option key={d.doc_id} value={d.doc_id}>{d.title}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="text-sm text-rose-700">{error}</p>}
      <ul className="space-y-2">
        {data.items.map((p) => (
          <li key={p.passage_id}>
            <button onClick={() => onOpenPassage(p.passage_id)} className="w-full text-left p-3 rounded-lg border border-slate-200 hover:border-indigo-300 text-sm">
              <p className="font-semibold text-slate-900">{p.doc_title} &gt; <span className="text-indigo-700">{p.section_heading}</span></p>
              <p className="text-xs text-slate-400 font-mono">{p.passage_id} | {p.word_count} words</p>
              <p className="text-slate-600 line-clamp-2 mt-1">{p.text}</p>
            </button>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between mt-3 text-sm">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-3 py-1 border rounded disabled:opacity-40">Previous</button>
        <span className="text-slate-500">Page {page} of {Math.max(1, data.total_pages)}</span>
        <button disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)} className="px-3 py-1 border rounded disabled:opacity-40">Next</button>
      </div>
    </section>
  );
}
