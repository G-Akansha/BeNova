"""
Seed Docs Generator (FR-01) - Member 2 Module
Generates the five multi-format enterprise documentation files in docs_corpus
and builds/updates document_manifest.json.
Idempotent: preserves uploaded documents and missing files.
"""

import os
import json
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors

BASE_DIR = Path(__file__).resolve().parent
DOCS_CORPUS_DIR = BASE_DIR / "docs_corpus"
DATA_DIR = BASE_DIR / "data"
MANIFEST_PATH = DATA_DIR / "document_manifest.json"

SEEDED_DOCS = [
    {
        "doc_id": "DOC-IAM",
        "title": "Identity & Access Management Manual",
        "filename": "01_Identity_Access_Manual.md",
        "format": "MD",
        "version": "v2.3",
        "effective_date": "2026-08-15",
        "environment": "All"
    },
    {
        "doc_id": "DOC-BILL",
        "title": "Billing and Refund Policy",
        "filename": "02_Billing_And_Refund_Policy.html",
        "format": "HTML",
        "version": "v3.0",
        "effective_date": "2026-09-01",
        "environment": "Production"
    },
    {
        "doc_id": "DOC-GW-LEGACY",
        "title": "API Gateway Configuration Guide (Legacy)",
        "filename": "03_API_Gateway_Config_Legacy.txt",
        "format": "TXT",
        "version": "v1.8-Legacy",
        "effective_date": "2025-04-10",
        "environment": "Legacy-v1"
    },
    {
        "doc_id": "DOC-REL-2026Q3",
        "title": "Release Notes 2026 Q3 - API Gateway v2.4",
        "filename": "04_Release_Notes_2026_Q3.md",
        "format": "MD",
        "version": "v2.4-Current",
        "effective_date": "2026-10-01",
        "environment": "Production-v2, Staging, Sandbox"
    },
    {
        "doc_id": "DOC-S3-TSG",
        "title": "Cloud Storage Troubleshooting & Operational Guide",
        "filename": "05_Cloud_Storage_Troubleshooting.pdf",
        "format": "PDF",
        "version": "v2.1",
        "effective_date": "2026-07-20",
        "environment": "All"
    }
]

DOC_01_MD = """# Identity & Access Management Manual (IAM)

**Document ID:** DOC-IAM  
**Version:** v2.3  
**Effective Date:** 2026-08-15  
**Environment Scope:** All Corporate Environments  

---

## 1. Enterprise SSO Setup and Authentication

Enterprise Single Sign-On (SSO) is powered by corporate SAML 2.0 and OpenID Connect (OIDC) identity providers. All full-time employees, contractors, and federated business partners must authenticate through the unified corporate portal at `https://sso.enterprise.internal`.

Upon navigating to the portal, enter your corporate email address (`user@enterprise.com`) and your Active Directory password. Upon validation of primary credentials, you will be prompted for mandatory Multi-Factor Authentication (MFA).

### Session Lifetimes and Timeout Policy
- **Idle Session Timeout:** Sessions will automatically lock after 30 minutes of inactivity.
- **Enterprise Session Timeout:** The maximum session lifetime is strictly 12 hours. After 12 hours of continuous or active connection, the session expires and the employee is required to re-authenticate with primary credentials and MFA.
- Concurrent sessions from different geographical regions trigger automated security challenge prompts.

---

## 2. MFA Hardware Security Token Reset Procedure

When an employee loses, damages, or is locked out of their physical MFA hardware security token (such as a YubiKey or Titan Security Key), they must follow the hardware token reset protocol:

1. **Identity Verification:** Contact the Enterprise IT Service Desk via verified internal communications or present in person at the local IT kiosk with your physical employee badge and government photo ID.
2. **Revocation:** The technician immediately revokes the lost hardware token's digital certificate from the central identity directory.
3. **Emergency Bypass Code:** The IT Service Desk issues a temporary one-time bypass code valid for 24 hours to maintain essential business continuity.
4. **Token Re-issuance:** Within 24 hours of bypass code generation, the user must register a new hardware security token through the self-service security portal at `https://id.enterprise.internal/mfa-enroll`. Once the new hardware token is registered, the bypass code is invalidated.

---

## 3. VPN Split-Tunneling Configuration

Remote employees connecting via GlobalProtect or Cisco AnyConnect enterprise VPN clients operate under an approved split-tunneling architecture.

- **Encrypted Tunnel Routes:** Only traffic destined for corporate subnets is routed through the encrypted VPN tunnel. Corporate destination subnets include CIDR blocks `10.0.0.0/8`, `172.16.0.0/12`, and enterprise private DNS resolvers (`10.254.0.10`).
- **Direct Public Internet Traffic:** General public internet traffic, software package repositories, and authorized SaaS applications (e.g., Google Workspace, Zoom, Office 365) bypass the VPN tunnel and route directly through the user's local internet connection.
- **Split-DNS:** Corporate hostnames ending in `.enterprise.internal` resolve strictly through corporate DNS servers over the tunnel. All public domain queries resolve via standard public DNS.

---

## 4. Troubleshooting Common Login and Authentication Problems

- **Account Lockout:** Entering an incorrect password 5 consecutive times triggers an automatic 15-minute security lockout. Users can unlock their account via the self-service recovery portal using an SMS/email verification pin.
- **Clock Skew Errors:** If the client system clock drifts more than 180 seconds from NTP server `time.enterprise.internal`, SAML assertions will fail with an `InvalidAssertionTime` error. Resync system time via Windows Time Service or systemd-timesyncd.
- **Stale Browser Sessions:** Corrupted session cookies often cause infinite redirect loops. Clear cookies and cached data for `*.enterprise.internal` or attempt authentication in an incognito/private browser window.
"""

DOC_02_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Enterprise Billing and Refund Policy</title>
</head>
<body>
    <h1>Enterprise Billing and Refund Policy</h1>
    <p><strong>Document ID:</strong> DOC-BILL | <strong>Version:</strong> v3.0 | <strong>Effective Date:</strong> 2026-09-01 | <strong>Environment:</strong> Production</p>

    <h2>1. Enterprise Invoice Net-45 Payment Terms</h2>
    <p>All enterprise subscription agreements are billed on an annualized or monthly recurring basis according to the Enterprise Master Services Agreement (MSA). Enterprise invoices are generated on the 1st calendar day of each billing cycle.</p>
    <p>Standard payment terms for enterprise accounts are strictly <strong>net-45 payment terms</strong>. The full invoice balance must be remitted within 45 calendar days from the invoice issuance date. Remittance must be submitted via Automated Clearing House (ACH), Fedwire electronic transfer, or corporate procurement credit card.</p>
    <ul>
        <li>Invoices unpaid after 45 days incur a late payment interest fee of 1.5% per month or the maximum rate permitted by law.</li>
        <li>Accounts reaching 60 days overdue receive automated suspension warnings before API access restriction.</li>
    </ul>

    <h2>2. Prorated Downgrade Credits</h2>
    <p>Customers may modify or downgrade their enterprise tier service levels at any point during an active contract term. When an enterprise account downgrades to a lower subscription tier, the billing engine calculates prorated downgrade credits.</p>
    <ul>
        <li><strong>Calculation Methodology:</strong> Downgrade credits are calculated on a strict pro-rata basis for the remaining unused days in the active billing period. The credit amount equals the difference between the daily rate of the higher tier and the lower tier multiplied by the remaining days in the cycle.</li>
        <li><strong>Application of Credits:</strong> In accordance with corporate accounting policy, cash refunds or direct banking reversals are not issued for service downgrades. All prorated credits are automatically applied to the enterprise account balance and will be deducted from subsequent renewal invoices.</li>
        <li>Credits remain valid on the account for up to 24 months from the date of issuance.</li>
    </ul>

    <h2>3. Overage Billing Alerts and Notification Rules</h2>
    <p>To avoid unexpected usage expenses, the enterprise monitoring platform continuously tracks API call volume, bandwidth, and compute usage against contracted tier quotas.</p>
    <ul>
        <li><strong>80% Threshold Warning:</strong> An informational email alert is automatically dispatched to the designated billing contact when monthly quota consumption reaches 80%.</li>
        <li><strong>90% Threshold Warning:</strong> A priority notification is sent to both technical and financial administrators recommending quota expansion.</li>
        <li><strong>100% Threshold Notice:</strong> An urgent notification alerts account administrators that contracted limits have been reached and overage billing has commenced.</li>
        <li><strong>Overage Calculation:</strong> Usage beyond contracted quotas is billed at the standard rate of $0.05 per additional 1,000 requests, consolidated onto the subsequent month's invoice.</li>
    </ul>
</body>
</html>
"""

DOC_03_TXT = """API Gateway Configuration Guide (Legacy Architecture)
Document ID: DOC-GW-LEGACY
Version: v1.8-Legacy
Effective Date: 2025-04-10
Environment Scope: Legacy-v1

================================================================================
1. LEGACY API GATEWAY RATE LIMITS
================================================================================
In the legacy API Gateway architecture (v1.8), rate limiting is enforced globally
by the edge proxy layer across all client connections and tiers:

- Enterprise API Rate Limit: Exactly 100 requests per minute across all tiers.
- Per-IP Concurrency Limit: Maximum of 10 concurrent HTTP/1.1 connections.
- Exceeding the 100 requests per minute limit triggers an HTTP 429 (Too Many Requests)
  response with a static header 'Retry-After: 60'.
- There is no burst capacity or burst token bucket in the v1.8 legacy deployment.

================================================================================
2. WEBHOOK RETRY SPECIFICATIONS (LEGACY)
================================================================================
For asynchronous event delivery and outbound webhook dispatches:
- Webhook Retries: 3 attempts total (1 initial delivery + 2 retry attempts).
- Retry Interval: Fixed 60-second delay between attempts.
- If the endpoint fails to return an HTTP 2xx status code after 3 attempts,
  the webhook event is permanently discarded to the legacy dead-letter drop.
- Exponential backoff is NOT supported in legacy v1.8.

================================================================================
3. CONFIGURATION AND TROUBLESHOOTING NOTES
================================================================================
- Upstream gateway timeout is set to 30 seconds.
- Clients must support TLS 1.2 minimum. Deprecated SSLv3 and TLS 1.0 are rejected.
- To inspect legacy rate limits, review client headers: X-Legacy-RateLimit-Limit (100)
  and X-Legacy-RateLimit-Remaining.
"""

DOC_04_MD = """# Release Notes 2026 Q3 - API Gateway v2.4

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
"""

def generate_pdf_doc(output_path: Path):
    """Generates 05_Cloud_Storage_Troubleshooting.pdf using ReportLab (valid, single page, extractable)."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#1a365d')
    )
    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading2'],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#2b6cb0'),
        spaceBefore=10,
        spaceAfter=4
    )
    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontSize=8,
        leading=12,
        textColor=colors.HexColor('#4a5568')
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#2d3748'),
        spaceAfter=6
    )

    story = []
    story.append(Paragraph("Cloud Storage Troubleshooting & Operational Guide", title_style))
    story.append(Paragraph("<b>Document ID:</b> DOC-S3-TSG | <b>Version:</b> v2.1 | <b>Effective Date:</b> 2026-07-20 | <b>Environment:</b> All", meta_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1. S3 Bucket 403 AccessDenied Error Troubleshooting", h2_style))
    story.append(Paragraph(
        "HTTP 403 AccessDenied errors typically stem from misaligned IAM policies, S3 Bucket Policies, or KMS access restrictions. "
        "To resolve: (a) Check user/role IAM permissions for 's3:GetObject', 's3:PutObject', and 's3:ListBucket'. "
        "(b) Verify S3 Bucket Policy does not contain explicit Deny statements that override role permissions. "
        "(c) Ensure VPC Endpoint policies allow traffic from the caller's VPC. "
        "(d) For cross-account access, verify that both the source IAM role and target bucket policy explicitly permit the action.",
        body_style
    ))

    story.append(Paragraph("2. IAM Permissions & Bucket-Policy Verification", h2_style))
    story.append(Paragraph(
        "Run the policy simulator command 'aws iam simulate-principal-policy' to test action evaluation against the target ARN. "
        "Verify that S3 Public Access Block settings are enabled on buckets holding private data, and confirm AWS Organizations SCPs "
        "do not restrict S3 actions in the designated AWS region.",
        body_style
    ))

    story.append(Paragraph("3. AWS KMS Key Rotation Guidance", h2_style))
    story.append(Paragraph(
        "Enterprise storage buckets are encrypted server-side using customer-managed AWS KMS keys (SSE-KMS). "
        "Customer-managed KMS keys rotate automatically every 365 days (1 year) when automatic key rotation is enabled. "
        "During rotation, previous key material is retained to decrypt existing ciphertexts. "
        "Ensure calling principals possess 'kms:Decrypt' and 'kms:GenerateDataKey' permissions on the KMS key policy.",
        body_style
    ))

    story.append(Paragraph("4. Storage Upload Limits and Object Sizing", h2_style))
    story.append(Paragraph(
        "Maximum single-upload object size: The maximum allowable file size for a single S3 PUT upload operation is strictly 50 GB. "
        "For objects exceeding 50 GB and up to the total storage ceiling of 5 TB, clients must use the AWS S3 Multipart Upload API. "
        "Multipart uploads recommend part sizes between 10 MB and 100 MB for optimal network recovery and transfer velocity.",
        body_style
    ))

    doc.build(story)


def seed_all_documents(force: bool = False):
    """Creates the seeded documents idempotently and generates document_manifest.json."""
    DOCS_CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 01_Identity_Access_Manual.md
    p1 = DOCS_CORPUS_DIR / "01_Identity_Access_Manual.md"
    if force or not p1.exists():
        p1.write_text(DOC_01_MD, encoding="utf-8")
        print(f"Generated {p1.name}")

    # 2. 02_Billing_And_Refund_Policy.html
    p2 = DOCS_CORPUS_DIR / "02_Billing_And_Refund_Policy.html"
    if force or not p2.exists():
        p2.write_text(DOC_02_HTML, encoding="utf-8")
        print(f"Generated {p2.name}")

    # 3. 03_API_Gateway_Config_Legacy.txt
    p3 = DOCS_CORPUS_DIR / "03_API_Gateway_Config_Legacy.txt"
    if force or not p3.exists():
        p3.write_text(DOC_03_TXT, encoding="utf-8")
        print(f"Generated {p3.name}")

    # 4. 04_Release_Notes_2026_Q3.md
    p4 = DOCS_CORPUS_DIR / "04_Release_Notes_2026_Q3.md"
    if force or not p4.exists():
        p4.write_text(DOC_04_MD, encoding="utf-8")
        print(f"Generated {p4.name}")

    # 5. 05_Cloud_Storage_Troubleshooting.pdf
    p5 = DOCS_CORPUS_DIR / "05_Cloud_Storage_Troubleshooting.pdf"
    if force or not p5.exists():
        generate_pdf_doc(p5)
        print(f"Generated {p5.name}")

    # Load existing manifest to preserve user uploads
    existing_manifest = []
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                existing_manifest = json.load(f)
        except Exception:
            existing_manifest = []

    existing_filenames = {d.get("filename") for d in existing_manifest}
    manifest = list(existing_manifest)

    for item in SEEDED_DOCS:
        if item["filename"] not in existing_filenames:
            manifest.append(item)

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest written to {MANIFEST_PATH} ({len(manifest)} documents registered).")

if __name__ == "__main__":
    seed_all_documents()

