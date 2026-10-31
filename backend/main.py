"""
Enterprise Documentation Q&A Assistant - FastAPI backend

Endpoints
  GET  /api/health              status, index size, LLM configured vs last call result
  GET  /api/bootstrap           inventory, filter values (derived from metadata), example questions
  GET  /api/documents           manifest
  GET  /api/passages            paginated passage explorer
  GET  /api/passages/{id}       one passage (source drawer for citations)
  POST /api/ask                 retrieve -> analyse evidence -> answer with citations
  POST /api/ingest              upload .md/.html/.txt/.pdf (transactional, 10 MB)
  POST /api/feedback            reviewer rating (upsert per trace)
  GET  /api/audit               recent questions + feedback
  GET  /api/evaluation          latest results written by evaluate.py

Run with ONE worker (in-memory index):  uvicorn main:app --port 8000
"""

import datetime
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ingestion_and_retrieval import get_knowledge_base, scope_values, MAX_UPLOAD_BYTES
from conflict_and_fallback import analyze_evidence_state, ConflictDetail, ScopeOption, ClarificationChoice
from llm_generator import generate_grounded_answer, ValidatedCitation, AnswerSegment, LLM_STATUS, GROQ_MODEL

DATA_DIR = BASE_DIR / "data"
FEEDBACK_PATH = DATA_DIR / "feedback.json"
AUDIT_LOG_PATH = DATA_DIR / "audit_log.jsonl"
TEST_QUESTIONS_PATH = DATA_DIR / "test_questions.json"
EVAL_RESULTS_PATH = DATA_DIR / "eval_results.json"

load_dotenv(dotenv_path=BASE_DIR / ".env")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
ANALYSIS_DEPTH = 8          # passages examined for evidence/conflicts (top_k controls what is displayed)

app = FastAPI(title="Enterprise Documentation Q&A Assistant API", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
                   allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])

_file_lock = threading.Lock()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write_json_atomic(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    format_filter: Optional[str] = "ALL"
    environment: Optional[str] = None
    version: Optional[str] = None
    doc_id: Optional[str] = None
    top_k: int = Field(5, ge=1, le=10)


class AskResponse(BaseModel):
    trace_id: str
    question: str
    applied_filters: Dict[str, Any]
    status: str
    confidence_score: float          # evidence strength (key-term coverage), not a probability
    confidence_band: str
    explanation: str
    latency_ms: float
    retrieval_latency_ms: float
    llm_latency_ms: float
    answer: str
    answer_segments: List[AnswerSegment]
    citations: List[ValidatedCitation]
    retrieved_passages: List[Dict[str, Any]]
    conflict_details: List[ConflictDetail]
    clarification_options: List[str]
    clarification_choices: List[ClarificationChoice]
    scope_options: List[ScopeOption]
    model_used: str
    fallback_used: bool
    llm_note: Optional[str] = None
    index_generation: int


class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., min_length=1, max_length=40)
    rating: str
    notes: Optional[str] = Field("", max_length=1000)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@app.on_event("startup")
def _warm_index():
    get_knowledge_base()


@app.get("/api/health")
def get_health():
    kb = get_knowledge_base()
    return {
        "status": "healthy",
        "backend_version": app.version,
        "indexed_passages": len(kb.passages),
        "index_generation": kb.generation,
        "answer_mode": f"LLM ({GROQ_MODEL}) with extractive fallback" if LLM_STATUS["configured"] else "Extractive (offline)",
        "llm": LLM_STATUS,
        "load_warnings": kb.load_warnings,
        "timestamp": _now(),
    }


def _filter_values(manifest: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    envs, versions = set(), set()
    for d in manifest:
        for e in (d.get("environment") or "").split(","):
            if e.strip() and e.strip().lower() not in ("all", "unknown"):
                envs.add(e.strip())
        v = (d.get("version") or "").strip()
        if v and v.lower() != "unknown":
            versions.add(v)
    return {"formats": ["ALL", "MD", "HTML", "TXT", "PDF"], "environments": sorted(envs), "versions": sorted(versions)}


@app.get("/api/bootstrap")
def get_bootstrap_data():
    kb = get_knowledge_base()
    manifest = kb.read_manifest()
    counts: Dict[str, int] = {"MD": 0, "HTML": 0, "TXT": 0, "PDF": 0}
    for d in manifest:
        counts[d.get("format", "").upper()] = counts.get(d.get("format", "").upper(), 0) + 1
    per_doc: Dict[str, int] = {}
    for p in kb.passages:
        per_doc[p.doc_id] = per_doc.get(p.doc_id, 0) + 1
    suite = _read_json(TEST_QUESTIONS_PATH, {})
    return {
        "document_count": len(manifest),
        "documents_by_format": counts,
        "document_inventory": [{**d, "passage_count": per_doc.get(d["doc_id"], 0)} for d in manifest],
        "passage_count": len(kb.passages),
        "index_generation": kb.generation,
        "demo_questions": suite.get("demo_scenarios", []),
        "available_filters": _filter_values(manifest),
    }


@app.get("/api/documents")
def get_documents():
    return get_knowledge_base().read_manifest()


@app.get("/api/passages")
def get_passages(page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
                 doc_id: Optional[str] = None, doc_format: Optional[str] = None):
    items = get_knowledge_base().passages
    if doc_id:
        items = [p for p in items if p.doc_id == doc_id]
    if doc_format and doc_format.upper() != "ALL":
        items = [p for p in items if p.doc_format.upper() == doc_format.upper()]
    start = (page - 1) * page_size
    return {"page": page, "page_size": page_size, "total": len(items),
            "total_pages": (len(items) + page_size - 1) // page_size,
            "items": [p.model_dump() for p in items[start:start + page_size]]}


@app.get("/api/passages/{passage_id}")
def get_passage(passage_id: str):
    p = get_knowledge_base().get_passage(passage_id)
    if not p:
        raise HTTPException(status_code=404, detail="Passage not found (the index may have been rebuilt).")
    return p.model_dump()


@app.get("/api/audit")
def get_audit_trail(limit: int = Query(30, ge=1, le=200)):
    entries = []
    if AUDIT_LOG_PATH.exists():
        for line in reversed(AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()):
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
            if len(entries) >= limit:
                break
    feedback = {f["trace_id"]: f for f in _read_json(FEEDBACK_PATH, []) if f.get("trace_id")}
    for e in entries:
        fb = feedback.get(e.get("trace_id"), {})
        e["rating"], e["reviewer_notes"] = fb.get("rating"), fb.get("notes")
    return {"total": len(entries), "entries": entries}


@app.get("/api/evaluation")
def get_evaluation():
    data = _read_json(EVAL_RESULTS_PATH, None)
    if data is None:
        raise HTTPException(status_code=404, detail="No evaluation run yet. Run: python backend/evaluate.py")
    return data


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------

@app.post("/api/ask", response_model=AskResponse)
def ask_question(req: AskRequest):
    t0 = time.time()
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="The question cannot be empty.")
    trace_id = f"Q-{uuid.uuid4().hex[:8].upper()}"
    kb = get_knowledge_base()
    all_passages = kb.passages            # one consistent snapshot for the whole request
    generation = kb.generation

    filters = {k: v for k, v in {
        "format": (req.format_filter or "ALL").upper() if (req.format_filter or "ALL").upper() != "ALL" else None,
        "environment": req.environment if req.environment and req.environment.lower() != "all" else None,
        "version": req.version if req.version and req.version.lower() != "all" else None,
        "doc_id": req.doc_id or None,
    }.items() if v}

    t_ret = time.time()
    retrieved = kb.find_relevant_passages(question, top_k=max(req.top_k, ANALYSIS_DEPTH), filters=filters or None)
    retrieval_ms = (time.time() - t_ret) * 1000

    analysis = analyze_evidence_state(question, retrieved, all_passages,
                                      environment=filters.get("environment"), version=filters.get("version"))
    gen = generate_grounded_answer(question, analysis, all_passages)
    total_ms = (time.time() - t0) * 1000

    _append_audit({
        "trace_id": trace_id, "timestamp": _now(), "question": question, "filters": filters,
        "index_generation": generation, "status": analysis.status,
        "evidence_strength": analysis.confidence_score, "retrieved_ids": [p.passage_id for p in retrieved[:req.top_k]],
        "cited_ids": [c.passage_id for c in gen.citations], "model_used": gen.model_used,
        "fallback_used": gen.fallback_used, "latency_ms": round(total_ms, 2),
    })

    shown = retrieved[:req.top_k]
    cited = {c.passage_id for c in gen.citations}
    shown += [p for p in retrieved[req.top_k:] if p.passage_id in cited]   # cited passages are always inspectable
    return AskResponse(
        trace_id=trace_id, question=question, applied_filters=filters, status=analysis.status,
        confidence_score=analysis.confidence_score, confidence_band=analysis.confidence_band,
        explanation=analysis.explanation, latency_ms=round(total_ms, 2), retrieval_latency_ms=round(retrieval_ms, 2),
        llm_latency_ms=gen.llm_latency_ms, answer=gen.answer, answer_segments=gen.segments, citations=gen.citations,
        retrieved_passages=[{**p.model_dump(), "rrf_score": round(p.rrf_score, 4),
                             "tfidf_similarity": round(p.tfidf_similarity, 4), "bm25_score": round(p.bm25_score, 2)}
                            for p in shown],
        conflict_details=analysis.conflict_details, clarification_options=analysis.clarification_options,
        clarification_choices=analysis.clarification_choices, scope_options=analysis.scope_options,
        model_used=gen.model_used, fallback_used=gen.fallback_used, llm_note=gen.llm_note,
        index_generation=generation,
    )


def _append_audit(entry: Dict[str, Any]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with _file_lock, open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:      # audit must never break answering
        print(f"Warning: audit log write failed: {e}")


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------

@app.post("/api/ingest")
def ingest_document(file: UploadFile = File(...), version: Optional[str] = Form(None),
                    effective_date: Optional[str] = Form(None), environment: Optional[str] = Form(None),
                    document_title: Optional[str] = Form(None)):
    content = file.file.read(MAX_UPLOAD_BYTES + 1)       # never read more than limit + 1 byte
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB upload limit.")
    try:
        return get_knowledge_base().ingest_uploaded_file(
            filename=file.filename or "upload.txt", content_bytes=content, version=version,
            environment=environment, effective_date=effective_date, document_title=document_title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:      # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {type(e).__name__}: {e}")


@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    if req.rating not in {"useful", "incorrect", "unresolved"}:
        raise HTTPException(status_code=400, detail="rating must be one of: useful, incorrect, unresolved")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _file_lock:
        items = [f for f in _read_json(FEEDBACK_PATH, []) if f.get("trace_id") != req.trace_id]
        items.append({"trace_id": req.trace_id, "rating": req.rating, "notes": req.notes or "", "timestamp": _now()})
        _write_json_atomic(FEEDBACK_PATH, items)
    return {"status": "SUCCESS"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False, workers=1)
