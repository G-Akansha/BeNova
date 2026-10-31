import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

// Right-hand panel: the ranked passages retrieval returned for the current question.
export default function EvidencePassagesPanel({ result, highlightedId, onOpenPassage }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const passages = result?.retrieved_passages || [];
  const cited = new Set((result?.citations || []).map((c) => c.passage_id));

  const toggle = (id) => setExpanded((prev) => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  return (
    <section className="bg-white rounded-xl border border-slate-200" aria-label="Retrieved passages">
      <div className="p-4 border-b border-slate-100">
        <h2 className="text-sm font-bold text-slate-800">Retrieved passages</h2>
        <p className="text-xs text-slate-500">
          Hybrid lexical ranking (TF-IDF + BM25, fused with reciprocal rank). Passages with no matching terms are never shown.
        </p>
      </div>
      {passages.length === 0 ? (
        <p className="p-6 text-sm text-slate-500">
          {result ? 'No passage matched this question and scope.' : 'The ranking for your question will appear here.'}
        </p>
      ) : (
        <ol className="p-3 space-y-2">
          {passages.map((p) => {
            const open = expanded.has(p.passage_id);
            return (
              <li key={p.passage_id}
                className={`p-3 rounded-lg border text-sm ${highlightedId === p.passage_id ? 'border-indigo-400 ring-2 ring-indigo-200' : 'border-slate-200'}`}>
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="w-5 h-5 rounded-full bg-slate-800 text-white flex items-center justify-center font-bold">{p.rank}</span>
                  <span className="px-1.5 py-0.5 rounded bg-slate-100 font-semibold">{p.doc_format}{p.page_number ? ` p.${p.page_number}` : ''}</span>
                  {cited.has(p.passage_id) && <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-semibold">cited</span>}
                  <span className="text-slate-400 font-mono">{p.passage_id}</span>
                </div>
                <p className="mt-1 font-semibold text-slate-900">{p.doc_title} <span className="text-slate-400">&gt;</span> <span className="text-indigo-700">{p.section_heading}</span></p>
                <p className="text-xs text-slate-500">version {p.version} | scope {p.environment}</p>
                <p className={`mt-1 text-slate-700 whitespace-pre-line ${open ? '' : 'line-clamp-3'}`}>{p.text}</p>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                  <button onClick={() => toggle(p.passage_id)} className="text-indigo-700 hover:underline flex items-center gap-0.5">
                    {open ? <>Less <ChevronUp className="w-3 h-3" /></> : <>More <ChevronDown className="w-3 h-3" /></>}
                  </button>
                  <button onClick={() => onOpenPassage(p.passage_id)} className="text-indigo-700 hover:underline">Open</button>
                  <span title="Reciprocal rank fusion score (ranking only, not a probability)">RRF {p.rrf_score}</span>
                  <span>TF-IDF {p.tfidf_similarity}</span>
                  <span>BM25 {p.bm25_score}</span>
                </div>
                {p.matched_terms?.length > 0 && (
                  <p className="mt-1 text-xs text-slate-500">Matched: {p.matched_terms.join(', ')}</p>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
