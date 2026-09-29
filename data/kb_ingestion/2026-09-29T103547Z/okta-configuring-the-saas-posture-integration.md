---
title: "Okta: Configuring the SaaS Posture Integration"
slug: "okta-configuring-the-saas-posture-integration"
status: "new"
updated: 2026-09-14T08:17:18Z
published: 2026-09-14T08:17:18Z
canonical: "knowledge.catonetworks.com/okta-configuring-the-saas-posture-integration"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Okta: Configuring the SaaS Posture Integration

## Overview

SaaS Posture integrations provide visibility into the configuration and security posture of your connected SaaS applications. Cato continuously reviews the application settings and compares them to the recommended posture defined by Cato’s research team. This helps identify misconfigurations that can increase risk, such as authentication settings, third-party integrations, and data-sharing controls.

Posture data appears in the Applications dashboard, where you can view posture scores and the highest-severity findings across connected applications. You can review each posture check from the Posture page, including the issue details, status, and remediation action required to pass the check.

For more information, see [Reviewing the Security Posture of Your SaaS Applications.](https://knowledge.catonetworks.com/v1/docs/understanding-the-security-posture-of-your-saas-applications)

To configure the SaaS Posture integration, you need to:

1. Configure the required settings in the SaaS application
2. Create the API connector in the CMA

A CASB license is required for SaaS Posture integrations.

## Configuring the Okta Integration

To configure the Okta integration, create an API token.

### Prerequisites

- An active Okta organization
- A dedicated Okta admin account with the Super Administrator role
- Access to the Okta Admin Console and permission to create an API token

### Step 1: Configure the Integration in the Okta Admin Console

In your Okta Admin Console, create an API token.

**To configure the Okta Integration:**

1. In your Okta Admin Console, navigate to **Security > API**.
2. On the **Tokens** tab, click **Create token**.
3. Add a description.
4. Configure the token's network-zone restriction according to your organization's security policy. Ensure the selected restriction allows the Cato service to connect to your Okta organization.
5. Click **Create token**.
6. Copy and save the token so it can be entered into the CMA.

### Step 2: Create the API Connector in the CMA

After you have set up an integration with the required application, add the details in the CMA.

**To create the API connector in the CMA:**

1. From the navigation menu, click **Resources > Integrations**.
2. Click the **Integrated Apps** tab.
3. Click **New**.

The **New Integration** panel opens.
4. Select the **SaaS Application** you want to add.
5. In the **Capability** drop-down, select **SaaS Posture**.
6. Add the details created during step one:
  - Okta Domain - Your Okta organization's base URL, including `https://` (not your admin console URL). Examples include:
    - `https://companyname.okta.com`
    - `https://companyname.okta-emea.com`
    - `https://companyname.oktapreview.com`
  - API Token - The token you made in Step 1
7. Click **Save**.
8. The app is visible on the **Integrated Apps** table with a **Connected** status.

### Known Limitations

- Okta's default List all users API omits users in DEPROVISIONED status unless a search or filter is used. The connector's user list may not include every deprovisioned account; suspended accounts returned by Okta are evaluated
- The connector token is created by a Super Administrator so it can read all required organization-wide sources. As a result, that token can appear in No Super Admin-Owned API Tokens - Okta. Treat it as a documented connector exception, protect it as a privileged credential, and rotate it according to your organization's policy.
