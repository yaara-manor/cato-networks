---
title: "Revoking a Remote Users Session from Entra ID"
slug: "revoking-a-remote-users-session-from-entra-id"
status: "new"
updated: 2026-09-14T07:57:18Z
published: 2026-09-14T07:57:18Z
canonical: "knowledge.catonetworks.com/revoking-a-remote-users-session-from-entra-id"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Revoking a Remote Users Session from Entra ID

## Overview

To maintain compliance of remote users connecting to your network, you can create a connector that automatically revokes a remote user session if their session is revoked in Microsoft Entra ID. For example, when an admin revokes a user's sessions in Entra ID (such as after a security incident, when a user leaves the organization, or as part of an automated flow), the user's session in the Cato Client is also revoked. This ensures your Entra ID security actions are consistently enforced across your Cato environment, reducing the risk of unauthorized access.

Within a few minutes of the session being revoked in Entra ID, the Client is disconnected, and the remote user is prompted to authenticate in the Client using their configured [authentication method](/v1/docs/configuring-the-authentication-policy-for-cato-clients). This functionality applies only to remote users connecting with the Cato Client. It does not apply to the [Enterprise Browser](/v1/docs/what-is-the-cato-enterprise-browser) or [Browser Extension](/v1/docs/what-is-the-cato-browser-extension).

For more information on revoking a remote user session in the Cato Client, see [Revoking a Remote User Session](/v1/docs/revoking-a-remote-user-session). For more information on revoking a user session in Entra ID, see the [Microsoft documentation](https://learn.microsoft.com/en-us/entra/identity/users/users-revoke-access).

## Prerequisites

- The remote user must be provisioned from Entra ID and use Entra ID SSO for authentication. For more information, see [SCIM Provisioning with Entra ID](/v1/docs/scim-provisioning-with-entra-id-formerly-azure)
- To revoke a session from an automated flow in Entra ID, a Microsoft Entra ID P2 license is required

## Configuring the Revoke Session Connector

To configure the Revoke Session connector, you need to:

1. Create a Microsoft 365 Tenant integration as the parent connector
2. Create the API connector for Revoke Session

#### 

#### Step 1: Create the Microsoft 365 Tenant Integration

First, configure the Microsoft 365 Tenant integration as the parent connector. This connector can be used for all Microsoft integrations. If you have already created the parent connector, go to step 2.

**To create the Microsoft 365 Tenant integration:**

1. From the navigation menu, select **Resources > Integrations** and click the **Integrated Apps** tab.
2. Click **New**. The **New Connector** panel opens.
3. In the **New Connector** panel, select the **Microsoft 365 (New Tenant)** app.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(208).png)
4. Enter the **Connector Name**.
5. Click **Authorize and Save**.

A new browser tab opens to the Microsoft 365 app.
6. In the new browser tab, authenticate to the Microsoft 365 app:
  1. Select the Microsoft account for the Microsoft 365 app.

Otherwise, there may be a Microsoft authentication error.
  2. Enter the password for the app and approve it.
  3. **Accept** the permissions to let Cato access the Microsoft 365 app.
  4. The screen shows that you have successfully applied the permissions for the app.

![Success_Connector_Permissions.png](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/33643826043933.png)

You can close the browser tab and return to the Cato Management Application.
7. The Microsoft 365 SaaS application is added to the **Integrated Apps** tab.

#### Step 2: Create the API connector for Revoke Session

After you have set up the parent connector, add the details of the Interconnected Apps integration in the CMA.

**To create the API connector in the CMA:**

1. From the navigation menu, click **Resources > Integrations**.
2. Click the **Configured Integrations** tab.
3. Click **New**.

The **New Integration** panel opens.
4. Select **Microsoft Entra ID**.
5. Choose **Entra Revoke Session**. ![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(199).png)
6. In the **Auth** drop-down, select the **Microsoft Primary Tenant** that was created in Step 1.
7. Add a **Name** for the connector.
8. Click **Save**.

The CMA connects to the vendor
9. Click **Authorize**.

![image-20250826-133358.png](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/33643864561565.png)

A Microsoft permissions screen will appear.
10. Review the requested permissions and click **Accept**.
11. The app is visible on the **Integrated Apps** table with a **Connected** status.
