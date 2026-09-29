---
title: "Docusign: Configuring the SaaS Posture Integration"
slug: "docusign-configuring-the-saas-posture-integration"
status: "update"
updated: 2026-09-14T09:24:07Z
published: 2026-09-14T09:24:07Z
canonical: "knowledge.catonetworks.com/docusign-configuring-the-saas-posture-integration"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Docusign: Configuring the SaaS Posture Integration

## Overview

SaaS Posture integrations provide visibility into the configuration and security posture of your connected SaaS applications. Cato continuously reviews the application settings and compares them to the recommended posture defined by Cato’s research team. This helps identify misconfigurations that can increase risk, such as authentication settings, third-party integrations, and data-sharing controls.

Posture data appears in the Applications dashboard, where you can view posture scores and the highest-severity findings across connected applications. You can review each posture check from the Posture page, including the issue details, status, and remediation action required to pass the check.

For more information, see [Reviewing the Security Posture of Your SaaS Applications.](https://knowledge.catonetworks.com/v1/docs/understanding-the-security-posture-of-your-saas-applications)

To configure the SaaS Posture integration, you need to:

1. Configure the required settings in the SaaS application
2. Create the API connector in the CMA

A CASB license is required for SaaS Posture integrations.

## Configuring the Docusign Integration

To configure the Docusign integration, create an application in the DocuSign admin portal.

### Prerequisites

- Your DocuSign account must have an Organization configured (DocuSign Admin / Organization Management)
- The authenticating user must have the Organization Administrator role
- Standard eSignature account access is used, for account-level security settings, password rules, users, and Connect webhook configuration

### Step 1: Configure the Integration in the Docusign Admin Portal

In the Docusign admin portal, configure a user and application.

#### Creating a User

The first step in configuring the integration is to create a user with the required roles.

**To create a user:**

1. In the [Docusign Admin Portal](https://apps.docusign.com/admin/users) create a user. For more information, see the [Docusign documentation](https://support.docusign.com/s/document-item?language=en_US&amp;bundleId=pik1583277475390&amp;topicId=jpz1583277424305.html&amp;_LANG=enus).
2. Assign the user the Organization Administrator or Security Reports Administrator role.
3. On the User's page, copy and save the **User ID** so that it can be entered into the CMA.

#### Configure an Application

The next step is to create an Integration key and Private key.

**To configure an application:**

1. In the [Docusign Admin Portal](https://apps.docusign.com/admin/apps-and-keys), navigate **Settings > Integrations > Apps and Keys**.
2. Click **Add App and Integration Key**.

![image__73_.png](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/33893067649181.png)
3. Add the following:
  - App Name: Choose a name for the app
  - Integration Type: Third-party integration key

![image__74_.png](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/33893060805789.png)
  - Redirect URIs: Click **Add URI** and enter:

`https://cc.catonetworks.com/redirect/cas/appconnector/callback`
  - Allowed HTTP Methods: Check GET and POST
4. Copy and save the **Integration Key** so it can be entered into the CMA.
5. In the **Service Integration** section, click **Generate RSA**. Copy and save the **Private Key** so it can be entered into the CMA.

**Note**: This is only displayed once.
6. Click **Save**.

### Step 2: Create the API Connector in the CMA

After you have set up an integration with the required application, add the details in the CMA.

**To create the API connector in the CMA:**

1. From the navigation menu, click **Resources > Integrations**.
2. Click the **Configured Integrations** tab.
3. Click **New**.

The **New Integration** panel opens.
4. Select the **SaaS Application** you want to add.
5. In the **Capability** drop down select **SaaS Posture**.
6. Add the details created during step one.
7. If you are integrating with a development environment, check the **Is Dev Environment** box, if you are integrating with a production environment, leave this box unchecked.
8. In the **Consent Endpoint** field:
  - For production environments, add: [https://account.docusign.com/](https://account.docusign.com/)
  - For developer environments, add: [https://account-d.docusign.com/](https://account-d.docusign.com/)
9. Click **Save**.

The Docusign consent flow opens.
10. Grant consent for these scopes:
  - signature
  - impersonation
  - user_read
  - organization_read
  - account_read
  - group_read
  - permission_read
  - identity_provider_read
  - domain_read
11. The app is visible on the **Integrated Apps** table with a **Connected** status.
