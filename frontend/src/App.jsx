import { useCallback, useEffect, useRef, useState } from 'react';
import { FileText, MessageSquare, Layers, BarChart3, RefreshCw } from 'lucide-react';
import { apiGet, apiPost, EMPTY_FILTERS } from './api';
import AskPanel from './components/AskPanel';
import AnswerPanel from './components/AnswerPanel';
import EvidencePassagesPanel from './components/EvidencePassagesPanel';
import DocumentsTab from './components/DocumentsTab';
import EvaluationTab from './components/EvaluationTab';
import SourceDrawer from './components/SourceDrawer';

const TABS = [
  { id: 'ask', label: 'Ask', icon: MessageSquare },
  { id: 'documents', label: 'Documents', icon: Layers },
  { id: 'evaluation', label: 'Evaluation', icon: BarChart3 },
];

export default function App() {
  const [tab, setTab] = useState('ask');
  const [health, setHealth] = useState({ state: 'connecting', info: null });
  const [bootstrap, setBootstrap] = useState(null);
  const [corpusVersion, setCorpusVersion] = useState(0); // bumps after uploads so lists refresh

  const [input, setInput] = useState('');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [openPassageId, setOpenPassageId] = useState(null);

  const requestSeq = useRef(0);
  const abortRef = useRef(null);

  const loadStatus = useCallback(async () => {
    setHealth((h) => ({ ...h, state: 'connecting' }));
    try {
      const [h, b] = await Promise.all([apiGet('/api/health'), apiGet('/api/bootstrap')]);
      setHealth({ state: 'connected', info: h });
      setBootstrap(b);
    } catch {
      setHealth({ state: 'disconnected', info: null });
    }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus, corpusVersion]);

  // One function builds the COMPLETE request from explicit values, so a click never uses stale state.
  const ask = useCallback(async (question, nextFilters) => {
    const q = (question ?? '').trim();
    if (!q) return;
    const f = { ...EMPTY_FILTERS, ...nextFilters };
    setInput(q);
    setFilters(f);
    setError(null);
    setLoading(true);
    setOpenPassageId(null);

    abortRef.current?.abort();               // only the newest request may update the screen
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const seq = ++requestSeq.current;
    try {
      const data = await apiPost('/api/ask', {
        question: q,
        format_filter: f.format,
        environment: f.environment || null,
        version: f.version || null,
        doc_id: f.doc_id || null,
        top_k: 5,
      }, ctrl.signal);
      if (seq === requestSeq.current) setResult(data);
    } catch (e) {
      if (e.name !== 'AbortError' && seq === requestSeq.current) setError(e.message || 'Request failed');
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, []);

  const docTitles = Object.fromEntries((bootstrap?.document_inventory || []).map((d) => [d.doc_id, d.title]));

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white">
                <FileText className="w-5 h-5" aria-hidden />
              </div>
              <div>
                <h1 className="text-base sm:text-lg font-bold text-slate-900 leading-tight">Enterprise Documentation Q&amp;A</h1>
                <p className="text-xs text-slate-500">Answers only from your documents, with citations</p>
              </div>
            </div>
            <StatusPill health={health} onRetry={loadStatus} />
          </div>
          <nav className="flex gap-1 -mb-px overflow-x-auto" aria-label="Sections">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                aria-current={tab === id ? 'page' : undefined}
                className={`px-3 py-2.5 text-sm font-semibold border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
                  tab === id ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                <Icon className="w-4 h-4" aria-hidden /> {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto w-full px-4 sm:px-6 py-6 flex-1">
        {health.state === 'disconnected' && (
          <div role="alert" className="mb-4 p-3 rounded-lg border border-rose-200 bg-rose-50 text-sm text-rose-800">
            Cannot reach the backend at /api. Start it with <code>uvicorn main:app --port 8000</code> in <code>backend/</code>, then press Retry.
          </div>
        )}

        {tab === 'ask' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <div className="lg:col-span-7 space-y-4">
              <AskPanel
                input={input}
                setInput={setInput}
                filters={filters}
                setFilters={setFilters}
                loading={loading}
                onAsk={ask}
                bootstrap={bootstrap}
                docTitles={docTitles}
              />
              {error && (
                <div role="alert" className="p-3 rounded-lg border border-rose-200 bg-rose-50 text-sm text-rose-800">{error}</div>
              )}
              <AnswerPanel
                result={result}
                loading={loading}
                docTitles={docTitles}
                onOpenPassage={setOpenPassageId}
                onAsk={ask}
                currentFilters={filters}
              />
            </div>
            <aside className="lg:col-span-5 lg:sticky lg:top-28 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto">
              <EvidencePassagesPanel
                result={result}
                highlightedId={openPassageId}
                onOpenPassage={setOpenPassageId}
              />
            </aside>
          </div>
        )}

        {tab === 'documents' && (
          <DocumentsTab
            bootstrap={bootstrap}
            corpusVersion={corpusVersion}
            onUploaded={() => setCorpusVersion((v) => v + 1)}
            onOpenPassage={setOpenPassageId}
          />
        )}

        {tab === 'evaluation' && <EvaluationTab />}
      </main>

      <SourceDrawer passageId={openPassageId} onClose={() => setOpenPassageId(null)} />
    </div>
  );
}

function StatusPill({ health, onRetry }) {
  const { state, info } = health;
  const dot = state === 'connected' ? 'bg-emerald-500' : state === 'connecting' ? 'bg-amber-400 animate-pulse' : 'bg-rose-500';
  const text = state === 'connected' ? 'Connected' : state === 'connecting' ? 'Connecting...' : 'Disconnected';
  return (
    <div className="flex items-center gap-2 text-xs" aria-live="polite">
      <span className="flex items-center gap-2 px-3 py-1 rounded-full bg-slate-100 border border-slate-200">
        <span className={`w-2 h-2 rounded-full ${dot}`} aria-hidden />
        <span className="font-semibold text-slate-700">{text}</span>
        {info && (
          <span className="text-slate-500 hidden sm:inline">
            | {info.indexed_passages} passages | {info.answer_mode}
            {info.llm?.configured && info.llm?.last_call_ok === false ? ' (LLM failing - using extractive)' : ''}
          </span>
        )}
      </span>
      {state === 'disconnected' && (
        <button onClick={onRetry} className="px-2 py-1 rounded-md border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1">
          <RefreshCw className="w-3 h-3" aria-hidden /> Retry
        </button>
      )}
    </div>
  );
}
