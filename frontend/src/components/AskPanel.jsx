import { Send, X } from 'lucide-react';
import { EMPTY_FILTERS } from '../api';

// Short tag for an example question, taken from its name ("Direct Answer - Billing ..." -> "Direct Answer").
const tagOf = (name = '') => name.split(' - ')[0];

export default function AskPanel({ input, setInput, filters, setFilters, loading, onAsk, bootstrap, docTitles }) {
  const examples = bootstrap?.demo_questions || [];
  const opts = bootstrap?.available_filters || { formats: ['ALL'], environments: [], versions: [] };
  const filtered = filters.format !== 'ALL' || filters.environment || filters.version || filters.doc_id;
  const set = (k) => (e) => setFilters({ ...filters, [k]: e.target.value });

  return (
    <section className="p-4 bg-white rounded-xl border border-slate-200 space-y-3" aria-label="Ask a question">
      {examples.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 mb-2">Try an example</p>
          <div className="flex flex-wrap gap-2">
            {examples.map((ex) => (
              <button
                key={ex.id}
                onClick={() => onAsk(ex.question, { ...EMPTY_FILTERS, ...(ex.filters || {}) })}
                title={ex.question}
                className="text-left px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:border-indigo-300 hover:bg-indigo-50 text-sm text-slate-700 max-w-full"
              >
                <span className="font-semibold text-indigo-700">{tagOf(ex.name)}:</span>{' '}
                <span className="line-clamp-1 inline">{ex.question}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); onAsk(input, filters); }} className="space-y-3">
        <label htmlFor="question" className="sr-only">Question</label>
        <div className="flex gap-2">
          <textarea
            id="question"
            rows={2}
            maxLength={500}
            placeholder="Ask about access, billing, limits, configuration or troubleshooting..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onAsk(input, filters); } }}
            className="flex-1 px-3 py-2 text-base rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="self-stretch px-4 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white font-semibold flex items-center gap-2"
          >
            {loading ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" aria-label="Loading" /> : <Send className="w-4 h-4" aria-hidden />}
            <span className="hidden sm:inline">Ask</span>
          </button>
        </div>

        <fieldset className="flex flex-wrap items-center gap-2 text-sm">
          <legend className="sr-only">Optional scope</legend>
          <span className="text-slate-500 text-xs font-semibold">Scope (optional):</span>
          <Select id="f-format" label="Format" value={filters.format} onChange={set('format')}
            options={opts.formats.map((f) => [f, f === 'ALL' ? 'All formats' : f])} />
          <Select id="f-env" label="Environment" value={filters.environment} onChange={set('environment')}
            options={[['', 'All environments'], ...opts.environments.map((e) => [e, e])]} />
          <Select id="f-ver" label="Version" value={filters.version} onChange={set('version')}
            options={[['', 'All versions'], ...opts.versions.map((v) => [v, v])]} />
          <Select id="f-doc" label="Document" value={filters.doc_id} onChange={set('doc_id')}
            options={[['', 'All documents'], ...Object.entries(docTitles)]} />
          {filtered && (
            <button type="button" onClick={() => setFilters(EMPTY_FILTERS)} className="text-xs text-indigo-700 hover:underline flex items-center gap-1">
              <X className="w-3 h-3" aria-hidden /> Clear scope
            </button>
          )}
        </fieldset>
      </form>
    </section>
  );
}

function Select({ id, label, value, onChange, options }) {
  return (
    <>
      <label htmlFor={id} className="sr-only">{label}</label>
      <select id={id} value={value} onChange={onChange}
        className="px-2 py-1 rounded-md border border-slate-300 bg-white text-slate-700 text-sm max-w-[12rem]">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </>
  );
}
