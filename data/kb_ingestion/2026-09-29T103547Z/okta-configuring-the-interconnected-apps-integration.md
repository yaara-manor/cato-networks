---
title: "Okta: Configuring the Interconnected Apps Integration"
slug: "okta-configuring-the-interconnected-apps-integration"
status: "new"
updated: 2026-09-14T08:16:31Z
published: 2026-09-14T08:16:31Z
canonical: "knowledge.catonetworks.com/okta-configuring-the-interconnected-apps-integration"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Okta: Configuring the Interconnected Apps Integration

## Overview

Interconnected Apps provides you with visibility into third-party plugins connected to sanctioned SaaS applications. To provide Cato with visibility of data within an app, you need to set up an integration with the required application. For more information, see [Viewing and Analyzing Interconnected Apps](/v1/docs/viewing-and-analyzing-interconnected-apps).

To configure the Interconnected Apps integration, you need to:

1. Configure the integration within the SaaS application
2. Create the API connector in the Cato Management Application (CMA)

A CASB license is required for Interconnected Apps. For more information about purchasing a CASB license, please contact your Cato representative.

### Benefits of Connecting Okta

After creating this connector, Cato collects and correlates the following data points. These inputs help you identify broadly assigned applications, powerful Okta API grants, shared or user-managed SWA credentials, and high-privilege API tokens:

- Active applications configured in Okta, including application name, identifier, creation time, and sign-on method such as OIDC, SAML, or Secure Web Authentication (SWA)
- Assigned user identities, including user ID, name, email address, and user principal name
- Whether an application assignment is direct to a user or provided through a group
- Active Okta API grants associated with OIDC applications, including the granted okta.* permission scopes
- SAML identity attributes and SWA credential configuration that Okta exposes for an application
- Active SSWS API-token inventory, the token creator, and the creator's active administrator roles

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
5. In the **Capability** drop-down, select **3rd Party Apps**.
6. Add the details created during step one:
  - Okta Domain - Your Okta organization's base URL, including `https://` (not your admin console URL). Examples include:
    - `https://companyname.okta.com`
    - `https://companyname.okta-emea.com`
    - `https://companyname.oktapreview.com`
  - API Token - The token you made in Step 1
7. Click **Save**.
8. The app is visible on the **Integrated Apps** table with a **Connected** status.

### Known Limitations

- Only applications with an **ACTIVE** status are included
- OAuth/OIDC permission detail is based on Okta application-level grants. Per-user OAuth consent grants are not included
- For custom Okta administrator roles, the role name is shown but its individual underlying permissions are not expanded
- An active application with no assigned users and no detectable permission information may not appear in the inventory
