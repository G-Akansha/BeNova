import { useEffect, useState } from 'react';
import { AlertTriangle, HelpCircle, SearchX, ChevronRight, Copy, Check } from 'lucide-react';
import { apiPost, STATUS_META, EMPTY_FILTERS } from '../api';

// Renders `code` spans safely (no HTML injection).
export function InlineText({ text }) {
  const parts = String(text).split(/(`[^`]+`)/g);
  return parts.map((p, i) =>
    p.startsWith('`') && p.endsWith('`')
      ? <code key={i} className="px-1 rounded bg-slate-100 text-[0.9em]">{p.slice(1, -1)}</code>
      : <span key={i}>{p}</span>);
}

function CiteButtons({ numbers, ids, onOpen }) {
  return numbers.map((n, i) => (
    <button key={`${n}-${i}`} onClick={() => onOpen(ids[i] ?? ids[0])}
      className="ml-1 align-super text-[11px] font-bold text-indigo-700 hover:underline"
      aria-label={`Open source ${n}`}>[{n}]</button>
  ));
}

export default function AnswerPanel({ result, loading, docTitles, onOpenPassage, onAsk, currentFilters }) {
  if (!result && !loading) {
    return (
      <div className="p-6 bg-white rounded-xl border border-dashed border-slate-300 text-sm text-slate-500">
        Ask a question or pick an example. Every answer line links to the exact passage it came from.
        If the documents do not contain the answer, the assistant says so instead of guessing.
      </div>
    );
  }
  if (!result) {
    return <div className="p-6 bg-white rounded-xl border border-slate-200 text-sm text-slate-500" aria-live="polite">Searching the documents...</div>;
  }

  const meta = STATUS_META[result.status] || STATUS_META.NOT_FOUND;
  const f = result.applied_filters || {};
  const scopeChips = [f.format, f.environment, f.version, f.doc_id && (docTitles[f.doc_id] || f.doc_id)].filter(Boolean);

  return (
    <section className={`bg-white rounded-xl border border-slate-200 ${loading ? 'opacity-50' : ''}`} aria-live="polite" aria-busy={loading}>
      <div className="p-5 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs text-slate-500">{loading ? 'Previous question' : 'Question'}</p>
            <h2 className="text-base font-semibold text-slate-900 break-words">{result.question}</h2>
            {scopeChips.length > 0 && (
              <p className="text-xs text-slate-500 mt-1">Scope: {scopeChips.join(' | ')}</p>
            )}
          </div>
          <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${meta.cls}`}>{meta.label}</span>
        </div>

        {result.status === 'GROUNDED_ANSWER' || result.status === 'CONFLICT_DETECTED' ? (
          <>
            <Strength score={result.confidence_score} band={result.confidence_band} note={result.explanation} />
            <AnswerBody segments={result.answer_segments} onOpen={onOpenPassage} />
          </>
        ) : null}

        {result.status === 'CONFLICT_DETECTED' && (
          <ConflictCard result={result} onOpen={onOpenPassage} onAsk={onAsk} currentFilters={currentFilters} />
        )}

        {result.status === 'CLARIFICATION_NEEDED' && (
          <div className="p-4 rounded-lg border border-sky-200 bg-sky-50">
            <p className="text-sm font-semibold text-sky-950 flex items-center gap-2"><HelpCircle className="w-4 h-4" aria-hidden />{result.explanation}</p>
            <div className="mt-3 space-y-2">
              {result.clarification_choices.map((c) => (
                <button key={c.question} onClick={() => onAsk(c.question, { ...EMPTY_FILTERS, doc_id: c.doc_id })}
                  className="w-full text-left p-3 rounded-lg bg-white border border-sky-200 hover:border-sky-400 text-sm flex items-center justify-between gap-2">
                  <span>{c.label}</span><ChevronRight className="w-4 h-4 text-sky-600 shrink-0" aria-hidden />
                </button>
              ))}
            </div>
          </div>
        )}

        {result.status === 'NOT_FOUND' && (
          <div className="p-4 rounded-lg border border-slate-300 bg-slate-50 text-sm text-slate-800 flex gap-3">
            <SearchX className="w-5 h-5 text-slate-500 shrink-0" aria-hidden />
            <div>
              <p className="font-semibold">The documents do not answer this.</p>
              <p className="text-slate-600 mt-1">{result.explanation}</p>
              {scopeChips.length > 0 && <p className="text-slate-600 mt-1">A scope filter is active; clearing it may help.</p>}
            </div>
          </div>
        )}

        {result.citations?.length > 0 && <Sources citations={result.citations} onOpen={onOpenPassage} />}
      </div>
      <TechnicalDetails result={result} />
    </section>
  );
}

function Strength({ score, band, note }) {
  const pct = Math.round((score || 0) * 100);
  const color = band === 'HIGH' ? 'bg-emerald-500' : band === 'MEDIUM' ? 'bg-amber-500' : 'bg-rose-500';
  return (
    <div className="text-xs text-slate-600">
      <div className="flex items-center gap-2" title="Share of the question's key terms found in the cited lines. A heuristic, not a probability.">
        <span className="font-semibold">Evidence strength: {band.toLowerCase()}</span>
        <span className="flex-1 max-w-40 h-1.5 rounded bg-slate-200 overflow-hidden"><span className={`block h-full ${color}`} style={{ width: `${pct}%` }} /></span>
      </div>
      {note && <p className="mt-1">{note}</p>}
    </div>
  );
}

function AnswerBody({ segments: all = [], onOpen }) {
  // Conflict sides are shown in the comparison card below, not repeated here.
  const segments = all.filter((s) => s.kind !== 'conflict' && s.kind !== 'conflict_part');
  const facts = segments.filter((s) => s.kind !== 'part');
  if (!facts.length) return null;
  return (
    <div className="text-[15px] leading-relaxed text-slate-800 space-y-1">
      {segments.map((s, i) => {
        if (s.kind === 'part') return <h3 key={i} className="pt-2 font-semibold text-slate-900">{s.text}</h3>;
        if (s.kind === 'note') return <p key={i} className="p-2 rounded bg-amber-50 border border-amber-200 text-sm text-amber-900">{s.text}</p>;
        return (
          <p key={i} className="pl-3 border-l-2 border-indigo-200">
            <InlineText text={s.text} />
            <CiteButtons numbers={s.citation_numbers} ids={s.citation_ids} onOpen={onOpen} />
          </p>
        );
      })}
    </div>
  );
}

function ConflictCard({ result, onOpen, onAsk, currentFilters }) {
  return (
    <div className="p-4 rounded-lg border border-amber-300 bg-amber-50 space-y-3">
      <p className="text-sm font-semibold text-amber-950 flex items-center gap-2">
        <AlertTriangle className="w-4 h-4" aria-hidden /> Side-by-side comparison
      </p>
      {result.conflict_details.map((c, ci) => (
        <div key={ci} className="space-y-2">
          <p className="text-sm text-amber-950"><span className="font-semibold">{c.topic}?</span>
            <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-amber-200">{c.conflict_type === 'VERSION_ENVIRONMENT_VARIANCE' ? 'depends on version / environment' : 'potential contradiction'}</span>
          </p>
          <p className="text-xs text-amber-900">{c.description}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {c.competing_passages.map((side) => (
              <div key={side.doc_id} className="p-3 rounded-lg bg-white border border-amber-200 text-sm">
                <p className="font-semibold text-slate-900">{side.doc_title}</p>
                <p className="text-xs text-slate-500 mb-2">{side.scope_type} | effective {side.effective_date}</p>
                {side.lines.map((l, i) => (
                  <p key={i} className="text-slate-800">
                    <InlineText text={l.text} />
                    <button onClick={() => onOpen(l.passage_id)} className="ml-1 text-[11px] text-indigo-700 hover:underline">source</button>
                  </p>
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
      {result.scope_options?.length > 0 && (
        <div className="pt-2 border-t border-amber-200 flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-amber-950">Answer for one scope:</span>
          {result.scope_options.map((o) => (
            <button key={o.label}
              onClick={() => onAsk(result.question, { ...EMPTY_FILTERS, format: currentFilters.format, environment: o.environment || '', version: o.version || '', doc_id: o.doc_id || '' })}
              className="px-2.5 py-1 text-xs font-semibold rounded-md bg-white border border-amber-400 text-amber-900 hover:bg-amber-100">
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Sources({ citations, onOpen }) {
  return (
    <div className="pt-3 border-t border-slate-100">
      <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Sources</h3>
      <ol className="space-y-2">
        {citations.map((c) => (
          <li key={c.passage_id}>
            <button onClick={() => onOpen(c.passage_id)}
              className="w-full text-left p-3 rounded-lg border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/40">
              <p className="text-sm font-semibold text-slate-900">[{c.number}] {c.formatted_label}</p>
              <p className="text-xs text-slate-500">{c.source_filename} | {c.doc_format} | version {c.version} | scope {c.environment} | {c.passage_id}</p>
              <p className="text-sm text-slate-600 mt-1 line-clamp-2">"{c.excerpt}"</p>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

function TechnicalDetails({ result }) {
  const [rating, setRating] = useState('');
  const [notes, setNotes] = useState('');
  const [saved, setSaved] = useState(null);     // {rating, notes} last saved
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => { setRating(''); setNotes(''); setSaved(null); setErr(null); }, [result.trace_id]);

  const dirty = rating && (!saved || saved.rating !== rating || saved.notes !== notes);
  const submit = async () => {
    setErr(null);
    try {
      await apiPost('/api/feedback', { trace_id: result.trace_id, rating, notes });
      setSaved({ rating, notes });
    } catch (e) { setErr(e.message); }
  };

  return (
    <details className="border-t border-slate-100 px-5 py-3 text-sm">
      <summary className="cursor-pointer text-xs font-semibold text-slate-500">Technical details & feedback</summary>
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3 text-xs">
        <Item k="Trace">
          {result.trace_id}
          <button onClick={() => { navigator.clipboard?.writeText(result.trace_id); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
            className="ml-1 align-middle" aria-label="Copy trace id">{copied ? <Check className="w-3 h-3 inline" /> : <Copy className="w-3 h-3 inline" />}</button>
        </Item>
        <Item k="Answer mode">{result.model_used}{result.fallback_used ? ' (LLM fallback)' : ''}</Item>
        <Item k="Evidence strength">{Math.round(result.confidence_score * 100)}% ({result.confidence_band})</Item>
        <Item k="Retrieval">{result.retrieval_latency_ms} ms</Item>
        <Item k="Answering">{result.llm_latency_ms} ms</Item>
        <Item k="Total">{result.latency_ms} ms</Item>
        <Item k="Index version">{result.index_generation}</Item>
        {result.llm_note && <Item k="LLM note">{result.llm_note}</Item>}
      </dl>
      <div className="mt-3 p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
        <p className="text-xs font-semibold text-slate-700">Was this answer correct and supported?</p>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Rating">
          {[['useful', 'Correct & supported'], ['incorrect', 'Incorrect'], ['unresolved', 'Did not answer']].map(([v, l]) => (
            <button key={v} role="radio" aria-checked={rating === v} onClick={() => setRating(v)}
              className={`px-2.5 py-1 rounded-md border text-xs ${rating === v ? 'bg-slate-800 text-white border-slate-800' : 'bg-white border-slate-300'}`}>{l}</button>
          ))}
        </div>
        <div className="flex gap-2">
          <label htmlFor="fb-notes" className="sr-only">Notes</label>
          <input id="fb-notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000}
            placeholder="Optional notes" className="flex-1 px-2 py-1 text-xs border border-slate-300 rounded bg-white" />
          <button disabled={!dirty} onClick={submit}
            className="px-3 py-1 text-xs font-semibold rounded bg-indigo-600 text-white disabled:bg-slate-300">
            {saved ? 'Update' : 'Submit'}
          </button>
        </div>
        {saved && !dirty && <p className="text-xs text-emerald-700">Feedback saved.</p>}
        {err && <p className="text-xs text-rose-700" role="alert">Could not save feedback: {err}</p>}
      </div>
    </details>
  );
}

function Item({ k, children }) {
  return (<div><dt className="text-slate-400">{k}</dt><dd className="text-slate-800 font-mono break-all">{children}</dd></div>);
}
