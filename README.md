# Enterprise Documentation Q&A Assistant

Ask questions about a set of PDF, HTML, Markdown and TXT documents. The assistant answers **only from those documents**, cites the passage for every line, shows conflicting versions side by side, and says "not found" instead of guessing.

## Quick start

```bash
# Backend (Python 3.11+)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed_docs.py                                     # creates the 5 demo documents (incl. the PDF)
python evaluate.py                                      # writes EVALUATION_REPORT.md + data/eval_results.json
uvicorn main:app --port 8000                            # ONE worker: the index lives in memory

# Frontend (Node 20+)
cd frontend
npm install
npm run dev                                             # http://localhost:5173 (proxies /api to :8000)
```

Optional LLM: copy `backend/.env.example` to `backend/.env` and set `GROQ_API_KEY`. Without it everything runs offline.

## Supported formats

| Format | Parsing | Kept |
| --- | --- | --- |
| Markdown | heading-aware; fenced code is not split | heading path (`1. SSO Setup > Session Lifetimes`), list items |
| HTML | headings h1-h6, script/style removed | list items, table cells (`Production \| 500`) |
| TXT | numbered headings (`1. RATE LIMITS`), `===` rules ignored | wrapped lines re-joined, bullets |
| PDF (text layer) | pypdf, per page, numbered headings | page number |

Scanned PDFs (no text layer) are rejected with a clear message. Uploads must be UTF-8 (text formats), at most 10 MB.

## How it works

1. **Ingestion**: each document becomes sections, then passages of about 220 words split at line boundaries. Each passage keeps its title, section, page, version, environment and effective date. Uploads are parsed in memory first and committed only if parsing succeeds. A bad file never enters the corpus.
2. **Retrieval**: TF-IDF (1-2 grams) and BM25 rankings are combined with Reciprocal Rank Fusion. Filters are applied before ranking, and passages with zero matching terms are dropped. A small synonym list (e.g. `two-factor -> mfa`, `throttling -> rate limit`) handles common paraphrases. The list contains vocabulary only, never answer values.
3. **Evidence check** (`conflict_and_fallback.py`):
   - The question is split into parts ("...terms **and how do** credits work").
   - For each part, the system picks the exact lines that cover its key terms. Terms are weighted by rarity (IDF), and synonyms are allowed.
   - A part is covered only if at least 60% of the weighted key terms **and** at least half of the terms are present.
   - No part covered → **NOT_FOUND**, naming the missing terms.
   - A one-word question that matches sections in two or more documents → **CLARIFICATION_NEEDED**. The options are the real matching sections.
   - Two documents answer the same part with different numbers → **CONFLICT_DETECTED**. It is labelled *version/environment variance* when their scopes differ, otherwise *potential contradiction*.
   - Scope words in the question ("legacy", "staging", "v2.4") narrow the evidence automatically.
4. **Answer**:
   - **Offline (default):** extractive. The answer consists of the selected lines verbatim, each with a numbered citation, so it cannot contain an unsupported claim.
   - **LLM mode:** the model rephrases only GROUNDED answers. Every sentence must cite a passage that was supplied to it, and every number must appear in that passage. Otherwise the sentence is dropped. If nothing survives, the extractive answer is shown and `fallback_used=true` is reported.
5. **Evaluation** (`evaluate.py`):
   - 24 labelled questions: direct, paraphrase, conflict, ambiguous, unanswerable, and filter-excluded.
   - A case passes only if the status, facts, numbers and cited source are all correct.
   - Retrieval Hit@1/Hit@3/MRR is scored against labelled relevant sections.
   - 8 robustness checks change the corpus at test time: edit a value, remove a document, empty corpus, upload a new topic, upload a contradiction, bad upload, and a dishonest LLM.

Current result: **22/24 cases, 8/8 robustness checks**. The two failures are documented paraphrase gaps (see `EVALUATION_REPORT.md`).

## Design trade-offs

| Choice | Why | Cost |
| --- | --- | --- |
| Lexical retrieval, no embeddings | Deterministic, explainable scores, runs offline in milliseconds, nothing to download | Paraphrases with no shared words can be missed. The system then says NOT_FOUND rather than guessing. |
| Extractive answers by default | Groundedness is guaranteed and easy to verify | Less fluent; can include a neighbouring line |
| Conflicts compared by numbers | Simple, precise, works on uploads too | Non-numeric contradictions ("refunds issued" vs "not issued") are missed |
| Evidence strength = key-term coverage | Honest and explainable | Not a calibrated probability, and labelled as such |
| In-memory index, atomic swap, one worker | Simple; requests never see a half-built index | Not horizontally scalable (out of scope) |

## Assumptions

- The documents are synthetic. Metadata (version, environment, effective date) comes from the manifest or the upload form. If the uploader does not provide a value, it stays **Unknown** and is never guessed.
- "Environment = All" documents apply to every environment filter.
- No authentication: this is a local demo. Uploads and audit access would need access control in production.

## Demo script (about 5 minutes)

1. **Direct** (Direct Answer example): net-45 and prorated credits. Click a `[1]` to open the exact passage.
2. **Paraphrase**: "two-factor security key" finds the MFA hardware-token procedure.
3. **Conflict**: Legacy 100 req/min vs v2.4 500 req/min, shown side by side. Click *Only Legacy-v1* to get a scoped answer.
4. **Ambiguous**: "What is the limit?" offers real sections; pick one.
5. **Unsupported**: flight reimbursement → not found, with the missing terms named.
6. **Live upload**: in Documents, upload `sample_uploads/Billing_Policy_Update_Oct_2026.txt` with version `v3.0`, environment `Production`, date `2026-10-15`. Ask "What are the enterprise invoice payment terms?" → *potential contradiction* (net-30 vs net-45). This proves the answers come from the documents.
7. **Evaluation tab**: real results from the last run, including the two honest failures.

## API

`GET /api/health`, `GET /api/bootstrap`, `GET /api/documents`, `GET /api/passages`, `GET /api/passages/{id}`, `POST /api/ask`, `POST /api/ingest`, `POST /api/feedback`, `GET /api/audit`, `GET /api/evaluation`. Interactive docs: http://localhost:8000/docs
