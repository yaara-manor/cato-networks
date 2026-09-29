---
title: "Integrating Cato Data with Palo Alto Cortex"
slug: "integrating-cato-data-with-cortex"
status: "new"
updated: 2026-09-27T11:15:28Z
published: 2026-09-27T11:15:28Z
canonical: "knowledge.catonetworks.com/integrating-cato-data-with-cortex"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Integrating Cato Data with Palo Alto Cortex

> [!TIP]
> Important:
> 
> This integration is a preview and subject to change. The certification process is underway.

## **Overview**

Use the Palo Alto Cortex integration to include Cato network and security data in your existing monitoring, correlation, and investigation workflows. The native integration sends data directly from Cato to your Cortex tenant, so you can analyze Cato activity alongside data from other sources in a centralized platform. This helps your SOC correlate data, create alerts, and hunt for threats without requiring additional data collection mechanisms.

## **Palo Alto Cortex Data Sources**

The Palo Alto Cortex integration supports two data sources:

- **Events** - Generated when specific activity occurs in the network or system, such as when a policy rule is matched or a threat is detected. These records provide discrete, real-time insights into security and policy enforcement. The data is sent using Cato's [event schema](https://api.catonetworks.com/documentation/#definition-EventFieldName).
- **Flows** - Originate as network flows (5-tuple) and are enriched with application-level information as it becomes available from Cato engines. In addition to application and user context, flows include aggregated session data such as bytes, packets, and duration, providing a complete view of network activity over time. The [appStats schema](https://api.catonetworks.com/documentation/#definition-AppStatsFieldName) represents the full set of flow fields.

By default, new integrations export only **Events**. The **Flows** data source can generate significantly more data than the Events data source. The exact volume depends on your traffic. You can configure multiple integrations in the CMA to send different data sources as needed.

## **Use Cases**

### **Events**

Sample Company uses Cortex for centralized security monitoring. As a Cato customer, it has Cato data about network activity, threats, user data, devices, and all other aspects of traffic traversing the Cato platform. The admin uses this integration to send that data directly to Cortex, where the SOC team works with it alongside their other sources.

### **Flows**

A security analyst at Sample Company identifies a suspicious event where a user accessed a high-risk application that may be associated with data exfiltration. Using Cato events alone, the analyst can see the policy decision, user identity, and application, but not how much data was transferred or how long the session lasted.

With aggregated flow data, the analyst can view the full session context, including total bytes transferred, packet count, and session duration. This lets the analyst determine whether the activity involved minimal interaction or a large data transfer that may indicate exfiltration.

## **Prerequisites**

- To add a connector, you must have editor permission for **Integrations** (in the **Resources** section). For more information, see [Managing Admin Roles Using RBAC](/v1/docs/managing-admin-roles-using-rbac).
- A Cortex tenant with permission to add a **Custom - HTTP based Collector** data source.
- Your Cortex ingestion URL and HTTP collector token.
- Review the prerequisites for all Cato event integrations in [Getting Started with Event Integrations](/v1/docs/getting-started-with-event-integrations).

## **Creating the Palo Alto Cortex Integration**

To send Cato data to Cortex, create an HTTP collector in Cortex, confirm that the endpoint accepts data, and then create the integration in the CMA.

### **Step 1: Create the HTTP Collector in Cortex**

**To create the collector:**

1. Log in to your Cortex tenant.
2. Go to **Custom - HTTP based Collector** and click **Add Instance**.
3. In the **Enable HTTP Log Collection** dialog, enter a **Name**, such as `Cato Networks`.
4. Set **Compression** to **uncompressed** and **Log Format** to **JSON**.
5. **(Optional)** Set **Vendor** and **Product** to `Cato_Networks`.
6. Click **Save & Generate Token**.
7. Copy the token value and store it securely, and note the ingestion URL for the collector.

> [!TIP]
> Note:
> 
> Cortex displays the token value only when it is generated. Copy it before you close the dialog. If you lose it, generate a new token and use that instead.

### **Step 2: Test the Endpoint with curl**

Before you configure the integration in the CMA, confirm that your API key, endpoint, and index work. This helps isolate Cortex-side issues from issues with the CMA integration.

The Cortex HTTP collector parses the request body as newline-delimited JSON, so the request must carry the `Content-Type: application/x-ndjson` header:

```bash
curl -X POST "https://<your-collector-url>" \
  -H "Authorization: <TOKEN>" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary $'{"message":"test event from curl","event_type":"test"}\n'
```

Replace `&lt;your-collector-url&gt;` with your collector URL and `&lt;TOKEN&gt;` with the token from Step 1.

A successful request returns an HTTP 2xx status. In Cortex, search for `test event from curl` to confirm that the document arrived.

### **Step 3: Create the Integration in the CMA**

**To create the Palo Alto Cortex integration:**

1. From the navigation menu, select **Resources > Integrations**.
2. On the **Configured Integrations** tab, click **New**. The **New Integration** panel opens.
3. Select **Palo Alto Cortex**. The **Capability** is set to **Data Export** automatically.
4. In the **Auth** drop-down, select **HTTP collector token authentication for Palo Alto Cortex**.
5. Enter a **Name** for this integration and an optional **Description**.
6. Enter the **Ingestion URL** that you tested in Step 2, for example `https://api-tenant.xdr.us.paloaltonetworks.com/logs/v1/event`.
7. Enter the **HTTP Collector Token** that you generated in Cortex.
8. Under **Data Sources**, select **Events**, **Flows**, or both.
9. **(Optional)** Add filters to control which data is sent to Cortex, [as described below](/docs/integrating-cato-data-with-cortex#filters).
10. Click **Save**.

Refresh the **Integrations** page. The integration appears in the **Configured Integrations** table with a **Connected** status.

## **Filters**

Use filters to control which Cato data is exported to Cortex. This helps reduce ingestion costs, minimize noise, and focus investigations on the data that is most relevant to specific sites, users, or regions. You can also use filters to route different subsets of data to different SIEM environments.

Use filter groups to define filters based on any [Event Field](/v1/docs/cato-event-schema) or combination of fields. Conditions within each group use AND logic. OR logic is applied between groups.

- **Events Filter** - Click **Add Filter** to define a condition, or **Add Group** to add a filter group.
- **Flows Filter** - Available when **Flows** is selected as a data source. It follows the same logic as the Events Filter.

Filters that are too narrow can exclude everything without showing any error. If no data arrives in Cortex after you save the integration, check the filter configuration first.

## **Troubleshooting**

| **Issue** | **Solution** |
| --- | --- |
| The integration shows a **Connectivity Error** | Check that the Ingestion URL and HTTP Collector Token are entered correctly, and that they match what you tested in Step 2. Confirm that the token has not been revoked in Cortex. |
| Events arrive but appear as raw text instead of parsed fields | Confirm that the collector is set to the **JSON** log format and to **uncompressed**, as described in Step 1. |
| No events arrive in Cortex | Check the Events Filter. A filter that is too narrow can exclude all data without reporting an error. |
| No flows arrive in Cortex | Confirm that **Flows** is selected under **Data Sources**, and check the Flows Filter for conditions that are too restrictive. |
| The integration doesn't show a **Connected** status after you save it | Refresh the **Integrations** page. If the status does not change, verify the HTTP collector token and the ingestion URL in Cortex. |
