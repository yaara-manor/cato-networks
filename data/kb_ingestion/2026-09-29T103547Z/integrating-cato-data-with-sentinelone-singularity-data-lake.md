---
title: "Integrating Cato Data with SentinelOne Singularity Data Lake"
slug: "integrating-cato-data-with-sentinelone-singularity-data-lake"
status: "new"
updated: 2026-09-27T11:13:04Z
published: 2026-09-27T11:13:04Z
canonical: "knowledge.catonetworks.com/integrating-cato-data-with-sentinelone-singularity-data-lake"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Integrating Cato Data with SentinelOne Singularity Data Lake

> [!TIP]
> Important:
> 
> This integration is a preview and subject to change. The certification process is underway.

## **Overview**

Use the SentinelOne Singularity Data Lake integration to include Cato network and security data in your existing monitoring, correlation, and investigation workflows. The native integration sends data directly from Cato to your Singularity Data Lake deployment, so you can analyze Cato activity alongside data from other sources in a centralized platform. This helps your SOC correlate data, create alerts, and hunt for threats without requiring additional data collection mechanisms.

## **SentinelOne Data Sources**

The SentinelOne integration supports two data sources:

- **Events** - Generated when specific activity occurs in the network or system, such as when a policy rule is matched or a threat is detected. These records provide discrete, real-time insights into security and policy enforcement. The data is sent using Cato's [event schema](https://api.catonetworks.com/documentation/#definition-EventFieldName).
- **Flows** - Originate as network flows (5-tuple) and are enriched with application-level information as it becomes available from Cato engines. In addition to application and user context, flows include aggregated session data such as bytes, packets, and duration, providing a complete view of network activity over time. The [appStats schema](https://api.catonetworks.com/documentation/#definition-AppStatsFieldName) represents the full set of flow fields.

By default, new integrations export only **Events**. The **Flows** data source can generate significantly more data than the Events data source. The exact volume depends on your traffic. You can configure multiple integrations in the CMA to send different data sources as needed.

## **Use Cases**

### **Events**

Sample Company uses Singularity Data Lake for centralized security monitoring. As a Cato customer, it has Cato data about network activity, threats, user data, devices, and all other aspects of traffic traversing the Cato platform. The admin uses this integration to send that data directly to Singularity Data Lake, where the SOC team works with it alongside their other sources.

### **Flows**

A security analyst at Sample Company identifies a suspicious event where a user accessed a high-risk application that may be associated with data exfiltration. Using Cato events alone, the analyst can see the policy decision, user identity, and application, but not how much data was transferred or how long the session lasted.

With aggregated flow data, the analyst can view the full session context, including total bytes transferred, packet count, and session duration. This lets the analyst determine whether the activity involved minimal interaction or a large data transfer that may indicate exfiltration.

## **Prerequisites**

- To add a connector, you must have editor permission for **Integrations** (in the **Resources** section). For more information, see [Managing Admin Roles Using RBAC](/v1/docs/managing-admin-roles-using-rbac).
- A SentinelOne Singularity Data Lake deployment with permission to generate a bearer token.
- Your Singularity Data Lake ingestion URL.
- Review the prerequisites for all Cato event integrations in [Getting Started with Event Integrations](/v1/docs/getting-started-with-event-integrations).

## **Creating the SentinelOne Singularity Data Lake Integration**

To send Cato data to Singularity Data Lake, generate a bearer token in Singularity Data Lake, confirm that the endpoint accepts data, and then create the integration in the CMA.

### **Step 1: Generate a Singularity Data Lake Bearer Token**

**To generate the bearer token:**

1. Log in to your SentinelOne Singularity Data Lake deployment.
2. Generate a bearer token for ingestion, giving it a descriptive name such as `Cato Integration`. For token management instructions, see the SentinelOne documentation.
3. Copy the **Bearer Token** value and store it securely.
4. Note your Singularity Data Lake ingestion URL.

> [!TIP]
> Note:
> 
> Singularity Data Lake may display the token value only when it is created. Copy it before you leave the page. If you lose it, generate a new token and use that instead.

### **Step 2: Test the Endpoint with curl**

Before you configure the integration in the CMA, confirm that your API key, endpoint, and index work. This helps isolate SentinelOne-side issues from issues with the CMA integration.

The Singularity Data Lake ingestion API authenticates with the `Authorization: Bearer &lt;TOKEN&gt;` header:

```bash
curl -X POST "https://<your-ingestion-url>" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  --data '{"message":"test event from curl","event_type":"test"}'
```

Replace `&lt;your-ingestion-url&gt;` with your ingestion URL and `&lt;TOKEN&gt;` with the bearer token from Step 1.

A successful request returns an HTTP 2xx status. In Singularity Data Lake, search for `test event from curl` to confirm that the document arrived.

### **Step 3: Create the Integration in the CMA**

**To create the SentinelOne Singularity Data Lake integration:**

1. From the navigation menu, select **Resources > Integrations**.
2. On the **Configured Integrations** tab, click **New**. The **New Integration** panel opens.
3. Select **SentinelOne Singularity Data Lake**. The **Capability** is set to **Data Export** automatically.
4. In the **Auth** drop-down, select **Bearer token authentication for SentinelOne Singularity Data Lake**.
5. Enter a **Name** for this integration and an optional **Description**.
6. Enter the **Ingestion URL** that you tested with curl above.
7. Enter the **Bearer Token** that you generated in Singularity Data Lake.
8. Under **Data Sources**, select **Events**, **Flows**, or both.
9. **(Optional)** Add filters to control which data is sent to Singularity Data Lake, [as described below](/docs/integrating-cato-data-with-sentinelone-singularity-data-lake#filters).
10. Click **Save**.

Refresh the **Integrations** page. The integration appears in the **Configured Integrations** table with a **Connected** status.

## **Filters**

Use filters to control which Cato data is exported to Singularity Data Lake. This helps reduce ingestion costs, minimize noise, and focus investigations on the data that is most relevant to specific sites, users, or regions. You can also use filters to route different subsets of data to different SIEM environments.

Use filter groups to define filters based on any [Event Field](/v1/docs/cato-event-schema) or combination of fields. Conditions within each group use AND logic. OR logic is applied between groups.

- **Events Filter** - Click **Add Filter** to define a condition, or **Add Group** to add a filter group.
- **Flows Filter** - Available when **Flows** is selected as a data source. It follows the same logic as the Events Filter.

Filters that are too narrow can exclude everything without showing any error. If no data arrives in Singularity Data Lake after you save the integration, check the filter configuration first.

## **Troubleshooting**

| **Issue** | **Solution** |
| --- | --- |
| The integration shows a **Connectivity Error** | Check that the Ingestion URL and Bearer Token are entered correctly, and that they match what you tested in Step 2. Confirm that the token has not expired or been revoked in Singularity Data Lake. |
| No events arrive in Singularity Data Lake | Check the Events Filter. A filter that is too narrow can exclude all data without reporting an error. |
| No flows arrive in Singularity Data Lake | Confirm that **Flows** is selected under **Data Sources**, and check the Flows Filter for conditions that are too restrictive. |
| The integration doesn't show a **Connected** status after you save it | Refresh the **Integrations** page. If the status does not change, verify the bearer token and the ingestion URL in Singularity Data Lake. |
