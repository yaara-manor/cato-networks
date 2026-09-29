---
title: "Okta: Configuring the App Activities Integration"
slug: "okta-configuring-the-app-activities-integration"
tags: ["CASB"]
status: "new"
updated: 2026-09-14T08:15:48Z
published: 2026-09-14T08:15:48Z
canonical: "knowledge.catonetworks.com/okta-configuring-the-app-activities-integration"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Okta: Configuring the App Activities Integration

## Overview

App Activities provides you with an API-based solution for out-of-band visibility of all activity made by any user in a connected SaaS application. To provide App Activities with visibility of data within an app, you need to set up an integration with the required application. Once you create the integration, if a field has changed or expired, you can edit it from the **Resources >Integrations > Integrated Apps** page. For more information, see [What is Application Control via API with App Activities](/v1/docs/what-is-application-control-via-api-with-app-activities).

To configure the App Activities integration, you need to:

1. Configure the integration within the SaaS application
2. Create the API connector in the CMA

A CASB license is required for App Activities. This license includes [app and data control](/v1/docs/what-is-the-unified-casb-solution) and App Activities via API. For more about purchasing a CASB license, please contact your Cato representative.

### Benefits of Connecting Okta

After creating this connector, you can view and monitor activity in your Okta account, for example:

- Authentication - Successful and failed sign-ins, SSO, MFA and identity-provider authentication
- Sessions - Session termination and expiration
- User and group lifecycle - User creation, activation, suspension, deactivation, and deletion; group creation and deletion
- Membership and permissions - Users added to or removed from groups and applications
- Administrative privileges - User privilege grants, revocations, and updates
- Authentication settings - MFA factor activation, deactivation, and reset; password resets; account unlocks
- Policies and rules - Policy and policy-rule creation, updates, and deletion
- Application integrations - Application creation and activation
- Security events - Account lockouts, detected threats, and access to administrative applications

## Configuring the Okta Integration

To configure the Okta integration, create an API token.

### Prerequisites

- An active Okta organization
- A dedicated Okta admin account with the Read-Only Administrator role
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
5. In the **Capability** drop-down, select **App Activities**.
6. Add the details created during step one:
  - Okta Domain - Your Okta organization's base URL, including `https://` (not your admin console URL). Examples include:
    - `https://companyname.okta.com`
    - `https://companyname.okta-emea.com`
    - `https://companyname.oktapreview.com`
  - API Token - The token you made in Step 1
7. Click **Save**.
8. The app is visible on the **Integrated Apps** table with a **Connected** status.

After connecting your APIs, you can track the App activities in the [Cloud Activities dashboard](/v1/docs/using-the-cloud-activity-dashboard). Data may take a few minutes to appear.

### Known Limitations

- On the first collection, Cato retrieves up to the previous hour of Okta System Log activity. Older events are not backfilled automatically
- When an Okta event contains only an IPv6 client address, the source IP isn't surfaced in Cato
- Event types that do not yet have a dedicated Cato category are still collected, but appear under a generic activity category
- An SSWS token becomes invalid if its creating account is deactivated, and it expires after 30 days without use. Replace the token in Cato after rotation or expiration
