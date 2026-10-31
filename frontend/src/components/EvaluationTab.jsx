import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiGet, STATUS_META } from '../api';

const pct = (x) => (x === null || x === undefined ? 'n/a' : `${(x * 100).toFixed(0)}%`);

// Shows the LATEST real run of backend/evaluate.py (nothing hard-coded) plus recent questions.
export default function EvaluationTab() {
  const [evalData, setEvalData] = useState(null);
  const [evalError, setEvalError] = useState(null);
  const [audit, setAudit] = useState([]);
  const [openRow, setOpenRow] = useState(null);

  const load = useCallback(async () => {
    try { setEvalData(await apiGet('/api/evaluation')); setEvalError(null); } catch (e) { setEvalError(e.message); }
    try { setAudit((await apiGet('/api/audit?limit=25')).entries || []); } catch { setAudit([]); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const m = evalData?.metrics;
  const rob = evalData?.robustness || [];
  return (
    <div className="space-y-6">
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold text-slate-900">Evaluation results</h2>
            <p className="text-xs text-slate-500">
              {evalData ? `${evalData.generated_at} | ${evalData.mode} | ${evalData.corpus.documents} documents, ${evalData.corpus.passages} passages` : 'Latest run of backend/evaluate.py'}
            </p>
          </div>
          <button onClick={load} className="px-3 py-1.5 text-sm rounded-lg border border-slate-300 flex items-center gap-1"><RefreshCw className="w-4 h-4" /> Reload</button>
        </div>
        {evalError && (
          <p className="mt-3 text-sm text-slate-600">{evalError} <code className="ml-1">python backend/evaluate.py</code></p>
        )}
        {m && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-4">
              <Card label="Cases passing all checks" value={`${m.passed}/${m.cases}`} />
              <Card label="Status accuracy" value={pct(m.status_accuracy)} />
              <Card label="Retrieval Hit@1" value={pct(m.hit_at_1)} />
              <Card label="MRR" value={m.mrr ?? 'n/a'} />
              <Card label="Unsupported numbers" value={m.answers_with_unsupported_numbers} />
              <Card label="Robustness checks" value={`${rob.filter((r) => r.passed).length}/${rob.length}`} />
            </div>
            <p className="text-xs text-slate-500 mt-2">
              A case passes only if the status is right, all expected facts are in the answer, every number is in a cited passage, and an expected source is cited.
            </p>
            <div className="overflow-x-auto mt-4">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-slate-500 uppercase border-b border-slate-200">
                  <tr>{['ID', 'Scenario', 'Expected', 'Actual', 'Facts', 'Result'].map((h) => <th key={h} className="py-2 pr-3">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {evalData.rows.map((r) => (
                    <FragmentRow key={r.id} r={r} open={openRow === r.id} onToggle={() => setOpenRow(openRow === r.id ? null : r.id)} />
                  ))}
                </tbody>
              </table>
            </div>
            <h3 className="text-sm font-bold text-slate-800 mt-6 mb-2">Robustness (documents changed at test time)</h3>
            <ul className="space-y-1 text-sm">
              {rob.map((r) => (
                <li key={r.check} className="flex gap-2"><span className={`font-bold ${r.passed ? 'text-emerald-700' : 'text-rose-700'}`}>{r.passed ? 'PASS' : 'FAIL'}</span>{r.check} <span className="text-slate-400">({r.detail})</span></li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="text-base font-bold text-slate-900 mb-3">Recent questions</h2>
        {audit.length === 0 ? <p className="text-sm text-slate-500">No questions logged yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-500 uppercase border-b border-slate-200">
                <tr>{['Time', 'Question', 'Result', 'Mode', 'Feedback'].map((h) => <th key={h} className="py-2 pr-3">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {audit.map((e) => (
                  <tr key={e.trace_id}>
                    <td className="py-2 pr-3 text-xs text-slate-500 whitespace-nowrap">{e.timestamp?.replace('T', ' ').slice(0, 19)}</td>
                    <td className="py-2 pr-3">{e.question}</td>
                    <td className="py-2 pr-3 whitespace-nowrap">{STATUS_META[e.status]?.label || e.status}</td>
                    <td className="py-2 pr-3 text-xs">{e.model_used}</td>
                    <td className="py-2 pr-3 text-xs">{e.rating || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Card({ label, value }) {
  return (<div className="p-3 rounded-lg bg-slate-50 border border-slate-200"><p className="text-xs text-slate-500">{label}</p><p className="text-xl font-bold text-slate-900">{value}</p></div>);
}

function FragmentRow({ r, open, onToggle }) {
  return (
    <>
      <tr className="cursor-pointer hover:bg-slate-50" onClick={onToggle}>
        <td className="py-2 pr-3 font-mono text-xs">{r.id}</td>
        <td className="py-2 pr-3">{r.name}</td>
        <td className="py-2 pr-3 text-xs">{r.expected_status}</td>
        <td className="py-2 pr-3 text-xs">{r.actual_status}</td>
        <td className="py-2 pr-3">{r.fact_coverage}</td>
        <td className={`py-2 pr-3 font-bold ${r.passed ? 'text-emerald-700' : 'text-rose-700'}`}>{r.passed ? 'PASS' : `FAIL (${r.failed_checks.join(', ')})`}</td>
      </tr>
      {open && (
        <tr><td colSpan={6} className="pb-3">
          <p className="text-xs text-slate-500 mb-1">Q: {r.question}{r.missing_facts?.length ? ` | missing facts: ${r.missing_facts.join(', ')}` : ''}</p>
          <pre className="text-xs whitespace-pre-wrap bg-slate-50 border border-slate-200 rounded p-2">{r.answer}</pre>
        </td></tr>
      )}
    </>
  );
}
