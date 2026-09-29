---
title: "Product Updates - September 28, 2026"
slug: "product-updates-september-28-2026"
updated: 2026-09-28T07:50:13Z
published: 2026-09-28T07:50:13Z
canonical: "knowledge.catonetworks.com/product-updates-september-28-2026"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Product Updates - September 28, 2026

## New Features & Enhancements

- **Windows Client v6.16:** During the week of Sept. 27, 2026, we will begin rolling out Windows Client version 6.16. This version includes stability improvements, security updates, and bug fixes.
- **Client Support for macOS 27 and iOS 27:** The following Client versions support macOS 27 Golden Gate or iOS 27:
  - macOS Client v6.1.1 - rolling out during the week of Sept. 27, 2026
  - iOS Client v5.9
- **Multiple DHCP Ranges for Site VLANs**: Configure multiple DHCP ranges on any site VLAN to support more flexible IP allocation across segmented networks.
  - Previously supported only for native ranges
  - Supported from Socket v27 and higher
- **CrowdStrike Device Risk Score for Device Posture:** Incorporate CrowdStrike device risk scores into [Device Posture checks](https://knowledge.catonetworks.com/docs/configuring-crowdstrike-device-risk-score-checks-for-device-posture), enforcing conditional access based on the risk level assigned to a device by CrowdStrike.

### In Case You Missed It

- **Intune Compliance for Device Posture:** Create [Device Posture checks](https://knowledge.catonetworks.com/docs/creating-device-posture-profiles-and-device-checks) based on compliance statuses reported by Microsoft Intune via a Cato connector. This lets you enforce access policies based on your organization's MDM compliance posture.
  - Use Intune-reported compliance signals as posture checks in Access policies
  - Applies to all devices, no additional license required

### Security Updates

- **Apps Catalog**

View more details about apps in the [Apps Catalog](https://knowledge.catonetworks.com/docs/using-the-app-catalog).
  - New Apps: 6 new apps: Speaker Deck, TransfertPro, Filen, Snapfish, Netflix, Teamviewer
    - Netflix
      - Now supported in IP-based socket bypass rules.
    - Teamviewer
      - Now supported in both FQDN-based and IP-based socket bypass rules.
  - Enhanced Apps:
    - SWARM Protocol
      - The SWARM protocol signature is now also recognized by ports, introducing faster appid detection and thus also faster action in FW.
- **IPS Signatures**

View more details about the IPS signatures and protections in the [Threats Catalog](https://knowledge.catonetworks.com/docs/using-the-threat-catalog).
  - CVE-2026-0768 (new)
  - CVE-2026-41948 (new)
  - CVE-2026-45454 (new)
  - CVE-2025-41242 (new)
  - CVE-2025-68668 (new)
  - CVE-2025-12055 (new)
  - CVE-2025-26399 (new)
  - CVE-2023-3450 (new)
- **Application Control Policy**
  - Vercel - Login (Enhancement)
  - ChatGPT Conversation (Enhancement)
- **TLS Inspection**
  - TikTok (Added global bypass exception to more browesers)
  - Trend Micro(Added global bypass)
- **Device Inventory**

These are the updates to the [Device Inventory](https://knowledge.catonetworks.com/docs/using-the-device-inventory-page) detection engine:
  - New Devices (5 new devices)
    - IoT
      - IP Camera
        - Genetec AutoVu SharpV
        - VusionGroup Captana Shelf Camera
      - IoT Gateway
        - Artila Electronics
      - Payment Terminal
        - Windcave Payment Terminal
    - OT
      - Digital IO
        - Xytronix WebRelay
  - Updated Devices (1 updated devices)
    - Networking
      - Switch
        - TP-Link
          - New signals added
- **Application Control Via API and Data Protection API Integrations**

The enhancements were made for [Application Control Via API](https://knowledge.catonetworks.com/docs/application-control-via-api-with-app-activities)
  - Armis | Device (Enhancement)
    - Added a business-criticality field to device inventory records
    - Stopped surfacing devices with an all-zero or invalid MAC address.
  - Atlassian Marketplace | Third Party Apps (Enhancement)
    - Migrated app permission enrichment to the Marketplace v3 API, exposing previously-unavailable MANAGE-level scopes and removing null permission descriptions.
  - Google Apps | Third Party Apps (Enhancement)
  - Zendesk | Activity (Enhancement)
    - Added a source.user.type field to Activity events to flag external end-users (requesters/partners) versus internal staff.
