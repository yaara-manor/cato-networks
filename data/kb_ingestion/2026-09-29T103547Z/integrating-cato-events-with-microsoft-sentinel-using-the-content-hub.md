---
title: "Integrating Cato Events with Microsoft Sentinel Using the Microsoft Content Hub (EA)"
slug: "integrating-cato-events-with-microsoft-sentinel-using-the-content-hub"
status: "new"
updated: 2026-09-24T09:09:53Z
published: 2026-09-24T09:09:53Z
canonical: "knowledge.catonetworks.com/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Integrating Cato Events with Microsoft Sentinel Using the Microsoft Content Hub (EA)

> [!NOTE]
> **Note:** This is an Early Availability (EA) feature that is only available for limited release. For more information, contact your Cato Networks representative or send an email to [ea@catonetworks.com](mailto:ea@catonetworks.com).

## Overview

This integration is installed from the Microsoft Sentinel Content Hub rather than from the CMA. It suits organizations that want the Entra application registered under their own control and that prefer to grant Cato the narrowest possible access: permission to write events into one Data Collection Rule, and nothing else.

Cato is listed in the Content Hub as a Microsoft-supported partner connector, built on the Codeless Connector Framework (CCF). This means the connector appears in the Sentinel data connectors gallery with native connector health monitoring, alongside your other Sentinel connectors. You keep the event schema current.

Cato also offers a native turnkey integration that you install from the CMA. With that method, Cato creates and maintains the app registration in your tenant, rotates its certificate, and can keep the event schema current for you. For a full comparison, review the guidance in [Integrating Cato Events with Microsoft Sentinel](https://knowledge.catonetworks.com/docs/integrating-cato-events-with-microsoft-sentinel).

### Process and Owners

| **Step** | **What happens** | **Owner** |
| --- | --- | --- |
| 1. [Install the solution](/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub#installing-and-deploying-the-connector) | Install Cato Networks from the Sentinel Content Hub. | Customer |
| 2. [Deploy the connector resources](/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub#installing-and-deploying-the-connector) | The connector page's **Deploy** action registers an Entra application, creates the data collection endpoint, Data Collection Rule, and custom table, and assigns the application the Monitoring Metrics Publisher role on that rule. | Customer |
| 3. [Connect the Cato side](/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub#creating-the-integration-in-the-cma) | Copy six connection values from the connector page into a new Microsoft Sentinel integration in the CMA. | Customer |
| 4. [Apply the current schema](/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub#keeping-the-event-schema-up-to-date) | Bring the table and Data Collection Rule up to Cato's current event schema. Do this once during setup, and again when you want fields added since. | Customer |

### Prerequisites

- An existing Log Analytics workspace with Microsoft Sentinel enabled, and read and write permissions on that workspace.
- Permission in Microsoft Entra ID to register an application and create a client secret. This typically requires the **Application Developer** role or higher.
- Permission in Azure to assign the **Monitoring Metrics Publisher** role on a Data Collection Rule. This typically requires the **Owner** or **User Access Administrator** role.
- **Editor** permission for **Integrations** (in the **Resources** section) in the CMA. For more information, see [Managing Admin Roles Using RBAC](/v1/docs/managing-admin-roles-using-rbac).
- Review the prerequisites for all Cato event integrations in [Getting Started with Event Integrations](/v1/docs/getting-started-with-event-integrations).

The MS Tenant connector is not required for this integration. That connector exists so that Cato can create app registrations in your tenant. With this integration method, you create the application yourself.

### What the Deployment Creates

Everything below is created in your subscription by the **Deploy** action on the connector page. You do not create any of it manually.

| Resource | Purpose |
| --- | --- |
| Entra application and client secret | The identity Cato authenticates as when sending events. Registered in your tenant, owned by you. The secret created at deployment is valid for two years. |
| Data collection endpoint | The address Cato sends events to. It is shared by every Codeless Connector Framework connector in the workspace. |
| Data Collection Rule | Declares the incoming event schema and the transformation into the table. |
| Custom table `CatoNetworksEvents_CL` | Where Cato events are stored. |
| Role assignment | Grants the application the built-in **Monitoring Metrics Publisher** role, scoped to the Data Collection Rule only. Cato receives no other permission: it cannot read your data, enumerate your resources, or modify anything in your tenant. |

## Setting Up the Integration

### Installing and Deploying the Connector

**To install and deploy the connector:**

1. In Microsoft Sentinel, select your workspace and go to **Content management > Content hub**.
2. Search for **Cato Networks** and install the solution.

In the installation wizard, select the subscription, resource group, and workspace that hold your Sentinel deployment, and then click **Review + create**. You can also view the solution as [Cato Networks for Microsoft Sentinel](https://marketplace.microsoft.com/en-us/product/catonetworks.cato-networks-sentinel-ccf-push) in the Microsoft Marketplace.
3. Go to **Configuration > Data connectors** and select **Cato Networks Events (Push)**.
4. Click **Open connector page**.

If you cannot see **Open connector page** or **Deploy**, zoom the browser out. The connector page can render below the visible area of the window, with no page scrollbar.
5. Copy the **Tenant ID**. This value is available before you deploy.
6. Click **Deploy**, review the resources listed, and confirm.

A warning appears first, explaining that a data collection endpoint will be created if one does not already exist. This is expected.

### Copying the Connection Values

When the deployment finishes, the connector page shows six values, each with a copy button.

| Value | Notes |
| --- | --- |
| **Tenant ID** | Available before deployment |
| **Entra App Registration Application ID** |  |
| **Entra App Registration Secret** | Copy it before you leave the page |
| **Data Collection Endpoint Uri** |  |
| **Data Collection Rule Immutable ID** |  |
| **Events Stream Name** | Fixed by the solution |

> [!WARNING]
> **Warning:**
> 
> Copy the **Entra App Registration Secret** as soon as the deployment finishes. The connector page reloads automatically within about a minute, and the secret is not shown again: Microsoft never displays a client secret after it is created, and the page has no option to reveal it. Handle and store it as you would any other credential.
> 
> If you miss it, you do not have to reinstall the solution. See [What if I lose the client secret?](/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub#what-if-i-lose-the-client-secret) in the FAQ for the two ways to recover.

### Creating the Integration in the CMA

**To create the Sentinel integration:**

1. From the CMA's navigation menu, select **Resources > Integrations**.
2. On the **Configured Integrations** tab, click **New**. The **New Integration** panel opens.
3. Select **Microsoft Sentinel**.
4. In the **Auth** field, select **Content Hub (CCF push) authentication for Microsoft Sentinel**. ![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(228).png)
5. Enter a **Name** for this integration, and optionally a **Description**.
6. Enter the values you copied from the connector page:
  - **Directory (Tenant) ID**
  - **Application (Client) ID**
  - **Client Secret**
  - **Data Collection Endpoint Uri**
  - **Data Collection Rule Immutable ID**
  - **Events Stream Name**
7. Optional: Add filters to control which Cato events are sent to Microsoft Sentinel, [as described below](/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub#configure-filters).
8. Click **Save**.

### Keeping the Event Schema Up to Date

The solution in the Content Hub carries the event schema as it stood when that version was published. Cato adds event fields more often than the solution is republished, so after installing, you apply the current schema separately.

Do this once as part of setup, and again whenever you want fields that Cato has added since. Installing a newer version of the solution does not do it for you: the table and Data Collection Rule belong to your subscription and were created by your **Deploy** action, so only this template changes them.

**To apply the current schema:**

1. Open the schema update template. In the **Keeping the schema up to date** section of the connector page, click **Deploy the schema update**. Alternatively, go to the [Cato Sentinel CCF repository](https://github.com/catonetworks/cato-sentinel-ccf) and click **Deploy to Azure**.
2. Select the subscription and the resource group that holds your Sentinel workspace.
3. Enter the workspace name. This is the only value you supply.
4. Click **Review + create**.

The update preserves your ingestion endpoint, Data Collection Rule immutable ID, Entra application, client secret, table retention, and all data already ingested. Nothing has to be re-entered in the CMA, and ingestion continues throughout.

A Log Analytics workspace holds one Cato connector, so if you run the connector in more than one workspace, apply the update once per workspace.

**Allow up to 30 minutes for new fields to start arriving.** The ingestion endpoint caches the previous schema briefly, and during that window events are accepted normally with the new fields left empty. Verify with a query rather than assuming the update failed:

```plaintext
CatoNetworksEvents_CL
| where TimeGenerated > ago(1h)
| take 10
```

If the new fields are still empty after an hour, contact Cato support with your account ID and the name of your Log Analytics workspace.

The schema only ever grows. Columns are added, never removed or retyped, so an update cannot break an existing workbook, analytics rule, or saved query.

### Verifying the Integration Is Working

After setup, confirm:

- The table `CatoNetworksEvents_CL` appears in your Log Analytics workspace under **Tables**
- The connector page in Sentinel shows the connector as **Connected**
- Events appear within a few minutes of traffic. Query with `CatoNetworksEvents_CL | take 10` in Log Analytics

> [!NOTE]
> **Note:**
> 
> The **Connected** status in Sentinel is based on data arriving in the table over the previous seven days, not on whether the credentials are still valid. A connector whose secret has expired can continue to show as Connected for up to seven days. Use a query against the table to confirm that events are still arriving.

### Configure Filters

Use filters to control which Cato events are exported to Microsoft Sentinel. This helps reduce ingestion costs, minimize noise, and focus investigations on the events that are most relevant to specific sites, users, or regions. You can also use filters to route different subsets of events to different SIEM environments.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/36659121973661.png)

Use filter groups to define filters based on any [Event Field](/v1/docs/understanding-event-fields) or combination of fields. Conditions within each group use AND logic. OR logic is applied between groups. The filters in the screenshot configure the integration to export:

- Events that **originate** from Paris or Madrid, are of **sub-type** Internet Firewall, and resulted in **actions** other than Monitor or Prompt
- **Username** contains Test

### Event Field Reference

The columns in `CatoNetworksEvents_CL` mirror the Cato event fields. See [Cato Event Schema](/v1/docs/cato-event-schema) for the fields each event type carries, and [Understanding Event Fields](/v1/docs/understanding-event-fields) for the field definitions.

Two names differ because Log Analytics reserves them:

| Cato field | Column in Sentinel |
| --- | --- |
| `time` | `TimeGenerated` |
| `title` | `activity_title` |

## Known Limitations

- **The packaged schema is a starting point.** The solution carries the event schema as of its release. Fields that Cato adds afterwards reach your table only when you apply the schema update. See [Keeping the Event Schema Up to Date](/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub#keeping-the-event-schema-up-to-date).
- **One connector per workspace.** The Data Collection Rule and the custom table are named from the workspace, so deploying the connector again in the same Log Analytics workspace reuses the existing resources rather than creating a second set. Events from several Cato accounts can share one connector, and are distinguished by `account_id` and `account_name`. To keep feeds in separate tables, with their own retention or access control, use a separate workspace for each.
- **Fixed table name.** Events are always written to `CatoNetworksEvents_CL`. The table name is fixed by the published solution and cannot be changed, because the connector's health status in Sentinel is determined by a query against that table.
- **Large event limitation.** Some XOps events can include extensive story information in the `raw_data` field, which may cause the event to exceed Microsoft Sentinel ingestion size limits (approximately 1 MB). When this occurs, Cato still forwards the event to Sentinel, but omits the `raw_data` field.
- **Uninstalling does not clean up.** Deleting the connector leaves the Data Collection Rule, the custom table and its data, and the Entra application in place. Remove them in Azure if you no longer need them.

---

### FAQ

#### Which Sentinel integration should I choose?

Choose the native turnkey integration unless you have a specific reason not to. It requires the least ongoing effort: Cato manages the app registration, rotates its certificate, and can apply schema updates for you.

Choose the Content Hub integration if your organization requires that app registrations in your tenant are created and owned by you, or if you want to grant Cato the narrowest possible access. In exchange, you hold the client secret, and you apply schema updates. See [Integrating Cato Events with Microsoft Sentinel](/v1/docs/integrating-cato-events-with-microsoft-sentinel).

#### Does this integration need the MS Tenant connector?

No. The MS Tenant connector exists so that Cato can create app registrations in your tenant. In this integration you create the application yourself, so that consent is not involved.

#### What access does Cato have with this integration?

One role assignment: the built-in **Monitoring Metrics Publisher** role, scoped to the single Data Collection Rule created for this connector. That permits sending events to that rule. It does not permit reading data, listing resources, or changing anything in your tenant.

#### What if I lose the client secret?

You have two ways to recover, and neither requires you to reinstall the solution.

**Create a new secret in Entra ID.** Go to the application under **App registrations**, open **Certificates & secrets**, select **New client secret**, and paste the new value into the CMA integration. An application can hold several valid secrets at once, so ingestion is not interrupted. The secret is the only value that changes, so it is the only one you re-enter in the CMA.

**Or click Revoke Access on the connector page, and then Deploy again.** This is often simpler if you are still on the connector page, because you stay in one place. It re-registers the application, so you get a new **Entra App Registration Application ID** as well as a new secret, and both have to be updated in the CMA. Your data collection endpoint, Data Collection Rule, and its immutable ID are unchanged, so nothing else needs re-entering.

#### How do I rotate the client secret?

Create a new client secret on the application in Entra ID, under **App registrations > Certificates & secrets > New client secret**. Paste the new value into the CMA integration, and then delete the old secret in Entra ID. An application can hold several valid secrets at the same time, so there is no gap in ingestion.

Note that creating a secret on an application requires directory permissions. The application created by **Deploy** has no owners, so you may need Application Administrator rights, or to add yourself as an owner first.

#### Why do I need to apply a schema update after installing the connector?

The solution in the Content Hub carries the event schema as of its release, and Cato adds event fields more often than the solution is republished. Applying the update brings your table and Data Collection Rule to the current schema. See [Keeping the Event Schema Up to Date](/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub#keeping-the-event-schema-up-to-date).

#### Do I have to apply every schema update?

No. The update is only needed to store fields that Cato has added since you last applied one. Skipping it does not impact ingestion of the fields you already have, and updates can be applied in any order, since the schema only grows.

#### Can I run this and the native turnkey integration at the same time?

Yes. They write to different tables and are configured independently. Bear in mind that each ingests a full copy of the events you select, and Log Analytics bills on ingested volume.

#### Can I change the table name or its retention?

The table name is fixed at `CatoNetworksEvents_CL` and cannot be changed. Retention is set to the workspace default at deployment, and you can change it in Log Analytics at any time. Applying a schema update does not reset it.
