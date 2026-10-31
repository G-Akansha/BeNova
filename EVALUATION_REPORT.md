# Evaluation Report - Enterprise Documentation Q&A Assistant

Generated: 2026-10-31 09:50:06 UTC  
Answer mode: Extractive (offline, no LLM)  
Corpus: 5 documents, 23 passages  
Result: **22/24 labelled cases pass all checks**, 8/8 robustness checks pass.

> All documents are synthetic, written for this hackathon. Test questions and relevance labels were written by the team (see `_labelling_notes` in `backend/data/test_questions.json`).

## 1. Method

A case passes only if **all** of these hold: correct status; every expected fact is in the answer; no number in the answer is missing from its cited passage; at least one citation is from an expected source. Retrieval is scored against labelled relevant *sections*, not just files.

## 2. Aggregate metrics

| Metric | Value |
| :-- | :-- |
| Cases passing all checks | 22/24 |
| Status accuracy | 100.0% |
| Retrieval Hit@1 / Hit@3 (relevant section) | 100.0% / 100.0% |
| MRR | 1.0 |
| Source-document recall@5 | 100.0% |
| Cases with all expected facts | 22/24 |
| Citation precision (cited docs that are expected docs) | 100.0% |
| Answers containing an unsupported number | 0 |
| Latency mean / p50 / p95 | 15.89 / 13.52 / 33.22 ms |

| Status | Precision | Recall | Cases |
| :-- | :-- | :-- | :-- |
| GROUNDED_ANSWER | 100.0% | 100.0% | 15 |
| CONFLICT_DETECTED | 100.0% | 100.0% | 2 |
| CLARIFICATION_NEEDED | 100.0% | 100.0% | 2 |
| NOT_FOUND | 100.0% | 100.0% | 5 |

## 3. Per-case results

| ID | Scenario | Expected | Actual | Facts | 1st relevant rank | Result |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| DEMO-Q01 | Direct Answer - Billing Terms & Credits | GROUNDED_ANSWER | GROUNDED_ANSWER | 4/4 | 1 | PASS |
| DEMO-Q02 | Paraphrase Retrieval - MFA Hardware Key Reset | GROUNDED_ANSWER | GROUNDED_ANSWER | 4/4 | 1 | PASS |
| DEMO-Q03 | Version & Environment Conflict Detection | CONFLICT_DETECTED | CONFLICT_DETECTED | 5/5 | 1 | PASS |
| DEMO-Q04 | PDF Retrieval - S3 AccessDenied & Upload Limit | GROUNDED_ANSWER | GROUNDED_ANSWER | 4/4 | 1 | PASS |
| DEMO-Q05 | Ambiguous Query Handling - Limit Inquiry | CLARIFICATION_NEEDED | CLARIFICATION_NEEDED | 0/0 | - | PASS |
| DEMO-Q06 | Unsupported Question - Travel Reimbursement | NOT_FOUND | NOT_FOUND | 0/0 | - | PASS |
| EVAL-Q07 | Identity - Session Timeout Duration | GROUNDED_ANSWER | GROUNDED_ANSWER | 2/2 | 1 | PASS |
| EVAL-Q08 | Network - VPN Split-Tunneling Routing | GROUNDED_ANSWER | GROUNDED_ANSWER | 3/3 | 1 | PASS |
| EVAL-Q09 | Billing - Overage Notification Thresholds | GROUNDED_ANSWER | GROUNDED_ANSWER | 3/4 | 1 | FAIL: facts |
| EVAL-Q10 | Scoped Query - Production v2.4 API Limit | GROUNDED_ANSWER | GROUNDED_ANSWER | 2/2 | 1 | PASS |
| EVAL-Q11 | Scoped Query - Legacy Gateway Rate Limit | GROUNDED_ANSWER | GROUNDED_ANSWER | 2/2 | 1 | PASS |
| EVAL-Q12 | Storage - KMS Customer Managed Key Rotation | GROUNDED_ANSWER | GROUNDED_ANSWER | 2/2 | 1 | PASS |
| EVAL-Q13 | Unsupported - Office Pet Policy | NOT_FOUND | NOT_FOUND | 0/0 | - | PASS |
| EVAL-Q14 | Modern - Staging Sandbox Rate Limiting | GROUNDED_ANSWER | GROUNDED_ANSWER | 1/1 | 1 | PASS |
| EVAL-Q15 | Unsupported - Employee Annual Bonus | NOT_FOUND | NOT_FOUND | 0/0 | - | PASS |
| EVAL-Q16 | Identity - Account Lockout Troubleshooting | GROUNDED_ANSWER | GROUNDED_ANSWER | 2/2 | 1 | PASS |
| EVAL-Q17 | Unsupported (in-domain words) - SSO emergency phone | NOT_FOUND | NOT_FOUND | 0/0 | - | PASS |
| EVAL-Q18 | Ambiguous - Timeout | CLARIFICATION_NEEDED | CLARIFICATION_NEEDED | 0/0 | - | PASS |
| EVAL-Q19 | Filter excludes the answer - Invoice terms in TXT only | NOT_FOUND | NOT_FOUND | 0/0 | - | PASS |
| EVAL-Q20 | Paraphrase - Inactive session lock | GROUNDED_ANSWER | GROUNDED_ANSWER | 1/1 | 1 | PASS |
| EVAL-Q21 | Paraphrase - Money back on downgrade | GROUNDED_ANSWER | GROUNDED_ANSWER | 0/2 | 1 | FAIL: facts |
| EVAL-Q22 | Paraphrase - Clock out of sync | GROUNDED_ANSWER | GROUNDED_ANSWER | 2/2 | 1 | PASS |
| EVAL-Q23 | Direct - Legacy TLS minimum | GROUNDED_ANSWER | GROUNDED_ANSWER | 1/1 | 1 | PASS |
| EVAL-Q24 | Version-dependent - Failed webhook retention | CONFLICT_DETECTED | CONFLICT_DETECTED | 2/2 | 1 | PASS |

## 4. Robustness checks (corpus changed at test time)

| Check | Result | Detail |
| :-- | :-- | :-- |
| Edited document value (net-45 -> net-30) is reflected | PASS | GROUNDED_ANSWER; answer mentions net-30=True, net-45=False |
| Removing the legacy document removes the conflict | PASS | status=GROUNDED_ANSWER |
| Empty corpus returns NOT_FOUND (no fabricated conflict) | PASS | status=NOT_FOUND |
| Uploaded pet policy makes the pet question answerable | PASS | before=NOT_FOUND, after=GROUNDED_ANSWER |
| Same-scope contradicting upload is flagged, not silently resolved | PASS | status=CONFLICT_DETECTED, types=['UNRESOLVED_CONTRADICTION'] |
| Invalid UTF-8 upload is rejected and the index still rebuilds | PASS | rejected=True, passages 26->26, file left behind=False |
| LLM sentence with unknown source id is rejected | PASS | fallback_used=True |
| LLM sentence with a number not in the cited passage is rejected | PASS | fallback_used=True |

## 5. Failure cases

### EVAL-Q09 - Billing - Overage Notification Thresholds
- Question: *When are overage billing alerts triggered and what is the extra unit rate?*
- Expected GROUNDED_ANSWER, got GROUNDED_ANSWER; failed checks: facts
- Missing facts: ['0.05']; unsupported numbers: none
- Answer given:

```
**When are overage billing alerts triggered?**
- 80% Threshold Warning: An informational email alert is automatically dispatched to the designated billing contact when monthly quota consumption reaches 80%. [1]
- 90% Threshold Warning: A priority notification is sent to both technical and financial administrators recommending quota expansion. [1]
- 100% Threshold Notice: An urgent notification alerts account administrators that contracted limits have been reached and overage billing has commenced. [1]

_Not found in the documents: "what is the extra unit rate?"_
```

### EVAL-Q21 - Paraphrase - Money back on downgrade
- Question: *Can I get my money back if I move to a lower subscription tier?*
- Expected GROUNDED_ANSWER, got GROUNDED_ANSWER; failed checks: facts
- Missing facts: ['cash refunds', 'account balance']; unsupported numbers: none
- Answer given:

```
- When an enterprise account downgrades to a lower subscription tier, the billing engine calculates prorated downgrade credits. [1]
- Calculation Methodology: Downgrade credits are calculated on a strict pro-rata basis for the remaining unused days in the active billing period. The credit amount equals the difference between the daily rate of the higher tier and the lower tier multiplied by the remaining days in the cycle. [1]
```

## 6. Demo examples (actual output)

**DEMO-Q01 - Direct Answer - Billing Terms & Credits** (GROUNDED_ANSWER)

```
**What are the enterprise invoice payment terms?**
- Standard payment terms for enterprise accounts are strictly net-45 payment terms. [1]
- Invoices unpaid after 45 days incur a late payment interest fee of 1.5% per month or the maximum rate permitted by law. [1]

**How do prorated downgrade credits work?**
- Customers may modify or downgrade their enterprise tier service levels at any point during an active contract term. [2]
- When an enterprise account downgrades to a lower subscription tier, the billing engine calculates prorated downgrade credits. [2]
- Calculation Methodology: Downgrade credits are calculated on a strict pro-rata basis for the remaining unused days in the active billing period. The credit amount equals the difference between the daily rate of the higher tier and the lower tier multiplied by the remaining days in the cycle. [2]
- Application of Credits: In accordan
```

**DEMO-Q02 - Paraphrase Retrieval - MFA Hardware Key Reset** (GROUNDED_ANSWER)

```
- When an employee loses, damages, or is locked out of their physical MFA hardware security token (such as a YubiKey or Titan Security Key), they must follow the hardware token reset protocol: [1]
- 1. Identity Verification: Contact the Enterprise IT Service Desk via verified internal communications or present in person at the local IT kiosk with your physical employee badge and government photo ID. [1]
- 2. Revocation: The technician immediately revokes the lost hardware token's digital certificate from the central identity directory. [1]
- 3. Emergency Bypass Code: The IT Service Desk issues a temporary one-time bypass code valid for 24 hours to maintain essential business continuity. [1]
- 4. Token Re-issuance: Within 24 hours of bypass code generation, the user must register a new hardware security token through the self-service security portal at `https://id.enterprise.internal/mfa-
```

**DEMO-Q03 - Version & Environment Conflict Detection** (CONFLICT_DETECTED)

```
**What is the maximum API rate limit per minute? - documents disagree**
- API Gateway Configuration Guide (Legacy) (Version v1.8-Legacy | Scope Legacy-v1): Enterprise API Rate Limit: Exactly 100 requests per minute across all tiers. Per-IP Concurrency Limit: Maximum of 10 concurrent HTTP/1.1 connections. [1]
- Release Notes 2026 Q3 - API Gateway v2.4 (Version v2.4-Current | Scope Production-v2, Staging, Sandbox): Production v2.4 Enterprise API Limit: 500 requests per minute per authenticated enterprise tenant. Production Burst Limit: Up to 1,000 requests in temporary burst windows of up to 10 seconds, accommodating traffic spikes without throttling. [2]

**How many times do webhooks retry? - documents disagree**
- API Gateway Configuration Guide (Legacy) (Version v1.8-Legacy | Scope Legacy-v1): Webhook Retries: 3 attempts total (1 initial delivery + 2 retry attempts). Retry Interval: Fix
```

**DEMO-Q06 - Unsupported Question - Travel Reimbursement** (NOT_FOUND)

```
The documents do not contain an answer to this question (the closest passages do not mention: class, flight, reimbursement).
```

## 7. Limitations

1. Retrieval and evidence selection are lexical (TF-IDF + BM25 + a small synonym list). Paraphrases with no shared vocabulary (e.g. 'out of sync' vs 'drifts more than 180 seconds') can be missed; the system then says NOT_FOUND rather than guessing.
2. Conflict detection compares numbers in the best line from each document. Contradictions without numbers (e.g. 'refunds are issued' vs 'not issued') are not detected.
3. The extractive answer quotes lines verbatim; it can include an extra neighbouring line. The optional LLM mode rephrases, but every sentence is validated against the cited passage (ids and numbers).
4. Evidence strength is key-term coverage, not a calibrated probability.
5. Scanned PDFs (no text layer) are rejected; OCR is out of scope. Single process / single worker only.

## 8. Reproduce

```bash
python backend/seed_docs.py
python backend/evaluate.py
```