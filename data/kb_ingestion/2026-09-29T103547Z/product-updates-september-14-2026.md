---
title: "Product Updates - September 14, 2026"
slug: "product-updates-september-14-2026"
updated: 2026-09-14T07:01:26Z
published: 2026-09-14T07:01:26Z
canonical: "knowledge.catonetworks.com/product-updates-september-14-2026"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Product Updates - September 14, 2026

## New Features & Enhancements

- **Roadmap Tracker Added to the CMA:** Get an account-specific view of feature rollout progress directly within the CMA, showing whether a feature is in Early Availability, Rolling Out, or Available for your account.
- **Device Posture Check for Minimum OS Version:** Include a check for the minimum OS version of a device within your Device Posture Profiles. The Device Posture Profile can be included in your Client Connectivity and Security policies.
  - Supported on Windows, macOS, iOS, and Android
- **Revoke Remote User Session from Microsoft Entra:** Revoking a user session in the Microsoft Entra admin center also revokes the user’s Cato Client session. This prevents users who no longer have Entra ID access from connecting to your network.
- **Fully Customizable Block and Prompt Pages:** Upload an HTML file to show custom block and prompt pages to meet your branding and messaging requirements.
- **New Docusign Connectors:** The following capabilities now support the Docusign app.
  - **Detailed Visibility of Interconnected Apps:** View detailed information about third-party apps and plugins connected to Docusign
  - **SaaS Posture:** Gain visibility into posture gaps, misconfigurations, and exposure risks that can make your Docusign environment vulnerable
- **New Okta Connectors:** The following capabilities now support the Okta app.
  - **Application Control via API:** Understand who is accessing each app and identify suspicious activities or trends even when users are not connected to the Cato Cloud. You can now connect your Okta account to provide visibility into user activities
  - **Detailed Visibility of Interconnected Apps:** View detailed information about third-party apps and plugins connected to Okta
  - **SaaS Posture:** Gain visibility into posture gaps, misconfigurations, and exposure risks that can make your Okta environment vulnerable
- **Concurrent Editing for the DNS Settings Policy:** The DNS Settings Policy for Clients and users now supports multiple unpublished [revisions](https://knowledge.catonetworks.com/docs/working-with-policy-revisions) and concurrent editing.
  - Multiple admins can modify the policy in parallel without conflicts
  - Each admin can maintain independent drafts and publish them when ready
- **DEM Metrics for Google Meet:** [Experience Monitoring](https://knowledge.catonetworks.com/docs/using-the-experience-monitoring-page) includes application-specific metrics for UCaaS traffic. These metrics provide insights into the experience of video, audio, and screen sharing during Google Meet calls.
  - Requires Cato connectors for Google Meet
  - DEM license required
- **AI Agents in DEM:** Use Experience Monitoring to analyze AI application and model provider experience directly from network traffic including corporate and personal generative AI and coding apps.
  - DEM license required
- **Advanced Groups Now Support VLAN IDs as Group Members:** We extended support for advanced [groups](https://knowledge.catonetworks.com/v1/docs/working-with-cma-advanced-groups-and-groups) to include VLAN IDs to help reduce manual configuration and ensure consistency at scale.
  - Initial support for the LAN Firewall and Bypass policies
- **Sandbox Events:** When a file is scanned in the [Sandbox](https://knowledge.catonetworks.com/docs/scanning-files-in-the-sandbox), an event is created with the **Sub-Type** Sandbox. The event contains the verdict and file hash, which, if necessary, can be added to your [Anti-Malware Policy](https://knowledge.catonetworks.com/docs/what-is-the-cato-anti-malware-policy).

### Security Updates

- **Apps Catalog**

View more details about apps in the [Apps Catalog](/v1/docs/using-the-app-catalog).
  - New Apps: 5 new apps - Filen - Cloud Storage, Snapfish, Speaker Deck, TransfertPro, mail.com
  - Enhanced Apps:
    - Citrix
      - Signature Updated
    - EZSignUp (formerly 123SignUp)
      - Modified name from **123signup** to **EZSignUp (formerly 123SignUp)**
      - Added domain **ezsignup.com**
    - Fortiguard
      - Added domain **fortiguard.net**
    - xhost
      - Added domain **xhostd.app**
  - Category Changes:
    - Remote Access: Removed app: Cato Client Software Updates
  - These are the updates for Socket apps, from Socket v25
    - Modified 1 apps: Citrix - Signature updated
- **Application Control Policy / CASB**
  - Gmail - Send Mail (Enhancement)
  - MS Teams - Send Message (Enhancement)
  - Vercel - Add Domain (New)
  - Vercel - Add Environment Variable (New)
  - Vercel - Create Project (New)
  - Vercel - Deploy (New)
  - Vercel - Generate Prompt (New)
  - Vercel - Git Import (New)
  - Vercel - Login (New)
  - Vercel - Upload Image (New)
  - Vercel - View Logs (New)
- **IPS Signatures**

View more details about the IPS signatures and protections in the [Threats Catalog](/v1/docs/using-the-threat-catalog).
  - CVE-2021-35215 (New)
  - CVE-2024-30270 (New)
  - CVE-2024-37014 (New)
  - CVE-2024-41628 (New)
  - CVE-2024-6893 (New)
  - CVE-2025-55746 (New)
  - CVE-2026-45659 (New)
  - CVE-2026-60004 (New)
  - CVE-2026-63520 (New)
  - CVE-2026-82329 (New)
- **Dynamic Prevention**

For the full control list, please refer to the Threat Catalog on CMA.
  - Detected Source IP Communicating with Known Malicious IPs or Domains from Threat Feeds, Limiting Lateral Movement, Command and Control, Discovery and Data Exfiltration (New) - Added 78 new controls
- **TLS Inspection**
  - TLS bypass of Zalo Native (New)
- **XDR Indications of Attack**
  - Anomaly Detection
    - Delete group (New)
    - Add app role assignment grant to user (New)
    - First Seen Failed Login from New OS by User (New)
    - First Seen Failed Login from New Country by User (New)
    - First Seen Delete Group Done Outside of Typical Department (New)
    - First occurrence of AI rule trigger for user (New)
    - Repeated Block Detections (New)
- **Application Control Via API and Data Protection API Integrations**

The enhancements were made for [Application Control Via API](https://knowledge.catonetworks.com/docs/application-control-via-api-with-app-activities)
  - DocuSign - SaaS Posture (New), Third Party Apps (New), Anomalies (Enhancement) - refined alert mapping
  - Okta - Activity (New), Third Party Apps (New), SaaS Posture (New)
  - Google Meet - Experience (New) - DEM meeting-quality monitoring for Google Meet
  - Anthropic for Business - Activity (New)
  - Microsoft Defender for Cloud Apps - XOps (New)
  - Google Apps - Activity (Enhancement) - expanded Google Workspace Admin audit-log activity coverage, Third Party Apps (Enhancement)
  - Salesforce - Third Party Apps (Enhancement)
  - Azure AD - Third Party Apps (Enhancement)
  - Slack - Third Party Apps (Enhancement)
  - Zendesk - Third Party Apps (Enhancement)
  - Microsoft Defender for Endpoint - Device (Enhancement) - asset criticality score
  - Armis - Device (Enhancement) - asset criticality score
  - Microsoft Office - Email Security (Enhancement) - surface unmapped incident triage fields
  - Microsoft Exchange - Activity (Enhancement) - surface attachment file names on email delete events
  - Microsoft Teams - Experience (Enhancement)
  - GitHub - Third Party Apps (Enhancement)
  - SharePoint - Anomalies (Enhancement)
