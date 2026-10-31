# Release Notes 2026 Q3 - API Gateway v2.4

**Document ID:** DOC-REL-2026Q3  
**Version:** v2.4-Current  
**Effective Date:** 2026-10-01  
**Environment Scope:** Production-v2, Staging, Sandbox  

---

## 1. Executive Summary: Architecture Modernization

The Q3 2026 release introduces API Gateway v2.4, replacing legacy v1.8 infrastructure. This release delivers significant performance improvements, higher throughput quotas, environment-scoped policies, and intelligent retry algorithms.

> **Scope & Compatibility Notice:**  
> These release notes define settings for modern environments: **Production-v2**, **Staging**, and **Sandbox**.  
> The legacy v1.8 environment (`Legacy-v1`) remains isolated for legacy clients with its historical rate limit (100 req/min) and retry policy (3 retries). Systems migrated to v2.4 operate under the new quotas described below.

---

## 2. API Rate Limits and Burst Allowances by Environment

API Gateway v2.4 introduces distributed token-bucket rate limiting tailored to environment type:

- **Production v2.4 Enterprise API Limit:** 500 requests per minute per authenticated enterprise tenant.
- **Production Burst Limit:** Up to 1,000 requests in temporary burst windows of up to 10 seconds, accommodating traffic spikes without throttling.
- **Staging and Sandbox Limit:** 50 requests per minute across all test applications to preserve shared staging infrastructure.
- **HTTP Headers:** Responses include standard headers `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset`.

---

## 3. Webhook Delivery and Exponential Backoff

Outbound webhook event reliability has been upgraded:

- **Webhook Retries:** Increased to 5 attempts (1 initial delivery + 4 retries).
- **Exponential Backoff Algorithm:** Retries use exponential backoff with jitter:
  - Retry 1: 1 second
  - Retry 2: 2 seconds
  - Retry 3: 4 seconds
  - Retry 4: 8 seconds
  - Retry 5 (final attempt): 16 seconds
- **Dead Letter Queue (DLQ):** Events that fail all 5 delivery attempts are securely preserved in an SQS Dead Letter Queue for 14 days for manual replay.
