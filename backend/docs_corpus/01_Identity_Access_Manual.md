# Identity & Access Management Manual (IAM)

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
