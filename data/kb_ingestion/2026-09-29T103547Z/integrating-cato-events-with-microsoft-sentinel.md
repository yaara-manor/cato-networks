---
title: "Integrating Cato Events with Microsoft Sentinel"
slug: "integrating-cato-events-with-microsoft-sentinel"
status: "new"
updated: 2026-09-27T11:15:01Z
published: 2026-09-27T11:15:01Z
canonical: "knowledge.catonetworks.com/integrating-cato-events-with-microsoft-sentinel"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Integrating Cato Events with Microsoft Sentinel

## **Overview**

Cato offers two ways to send event data to Microsoft Sentinel. This article explains what separates them, so you can pick the one that fits your environment before you start the setup.

The integration is push-based, whichever method you choose: Cato sends events directly to a Data Collection Rule in your Azure tenant, which writes them into a custom table in your Log Analytics workspace, where you can query them alongside the rest of your Sentinel data. Nothing polls the Cato API, so ingestion is not subject to API limits and high event volumes are supported. Filter groups in the CMA control which events are sent. The methods differ in who owns the Microsoft Entra application, how much access Cato receives in your tenant, and who keeps the event schema up to date as Cato adds new fields.

The two methods are:

- The native turnkey integration
- The Content Hub integration

The native turnkey integration is the simpler of the two to run. Cato creates and maintains the app registration in your tenant, rotates its certificate, and can keep the event schema current for you, so there is little to do after setup.

The Content Hub integration (currently EA) exists for organizations that need to keep control of what a vendor can do in their tenant. You own the Entra application, Cato is granted permission to write events into one Data Collection Rule and nothing else, and keeping the event schema current is a task you perform.

## **Comparing the Methods**

| **Consideration** | **Native turnkey** | [**Content Hub**](/v1/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub) **(EA)** |
| --- | --- | --- |
| Where you start | The CMA | The Sentinel Content Hub |
| Entra application | Created and managed by Cato in your tenant | Created in your tenant by the Content Hub deployment, and owned by you |
| Authentication | Certificate, rotated by Cato | Client secret that you create, hold, and rotate |
| Access granted to Cato | Monitoring Metrics Publisher on the Data Collection Rule, plus two custom least-privilege roles that allow schema updates | Monitoring Metrics Publisher on one Data Collection Rule |
| MS Tenant connector required | Yes | No |
| Table name | You define it (Cato appends `_CL`) | Fixed: `CatoNetworksEvents_CL` |
| Table retention | Set in the CMA when you create the integration | Workspace default; change it in Log Analytics at any time |
| Schema updates | Cato applies them automatically when you turn on **Auto Update Schema**. **Note:** This is an EA feature. By default it is set to **Off**. | You apply an update template |

## **When to Choose Each Method**

### **Native turnkey**

Choose this unless you have a specific reason not to. Cato creates the app registration in your tenant, manages its certificate, and can apply schema updates for you, so the integration needs almost no ongoing attention after setup.

This method requires that Cato holds:

- a certificate for an application it created in your tenant
- write access to the Data Collection Rule and table so that it can apply schema changes

See [Integrating Cato Events with Microsoft Sentinel Using the Turnkey Integration](https://knowledge.catonetworks.com/docs/integrating-cato-events-with-microsoft-sentinel-using-the-turnkey-integration).

### **Microsoft Content Hub**

> [!TIP]
> **Note:** This is an Early Availability (EA) feature that is only available for limited release. For more information, contact your Cato Networks representative or send an email to [ea@catonetworks.com](mailto:ea@catonetworks.com).

Choose this if your organization requires that applications registered in your tenant are created and owned by you, or if you want to grant Cato the narrowest access that still allows it to send events. Cato receives one role assignment, scoped to a single Data Collection Rule, which permits writing events and nothing else. Cato cannot read your data, list your resources, or change anything in your tenant.

Choose it also if you want the connector to appear in the Sentinel Content Hub with native connector health monitoring.

The trade-off is that you hold the client secret and rotate it, and you apply schema updates yourself when you want event fields that Cato has added since your last update.

See [Integrating Cato Events with Microsoft Sentinel Using the Microsoft Content Hub](/v1/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub).

## **Two Ways to Run the Native Turnkey Integration**

The native turnkey integration has an **Auto Update Schema** setting, which gives it two modes of operation. The setting is off by default, on new and existing integrations.

> [!TIP]
> **Note:** This is an Early Availability (EA) feature that is only available for limited release. For more information, contact your Cato Networks representative or send an email to [ea@catonetworks.com](mailto:ea@catonetworks.com).

| **Auto Update Schema** | **What happens when Cato adds event fields** |
| --- | --- |
| **On** | Cato adds the new fields to your Data Collection Rule and table automatically. No action needed |
| **Off** | Your table keeps its current columns. New event fields are not stored until you turn the setting on |

Turning the setting on means that Cato modifies the Data Collection Rule and the custom table in your Log Analytics workspace whenever the event schema changes. Many organizations do not allow a vendor to make changes in their workspace, and for them leaving the setting off is the right choice.

Leaving it off has a cost. Event fields that Cato adds after your integration is deployed are not stored, and Cato does not provide a self-service way to apply them on this method. If you need both control over your workspace and a way to keep the schema current, use the [Content Hub integration](/v1/docs/integrating-cato-events-with-microsoft-sentinel-using-the-content-hub), where you apply the schema update yourself.

Note that the roles that allow Cato to make these changes are granted when you deploy the ARM template, whether or not the setting is on. The setting controls only whether Cato uses them. To remove that access altogether, remove the two custom roles after deployment; event ingestion continues without them.

For more information, see [Keeping the Event Schema Up to Date](https://knowledge.catonetworks.com/docs/integrating-cato-events-with-microsoft-sentinel-using-the-turnkey-integration#keeping-the-event-schema-up-to-date).

## **Running Both Integrations**

You can run both Sentinel integrations at the same time. They write to different tables and are configured independently.

Bear in mind that each integration ingests its own full copy of the events you select, and Log Analytics bills on ingested volume. Before running both in parallel, apply filters so that each one carries only the events you need from it.
