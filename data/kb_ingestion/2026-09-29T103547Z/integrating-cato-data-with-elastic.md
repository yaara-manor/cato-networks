---
title: "Integrating Cato Data with Elastic"
slug: "integrating-cato-data-with-elastic"
status: "new"
updated: 2026-09-27T11:11:45Z
published: 2026-09-27T11:11:45Z
canonical: "knowledge.catonetworks.com/integrating-cato-data-with-elastic"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Integrating Cato Data with Elastic

> [!TIP]
> Important:
> 
> This integration is a preview and subject to change. The certification process is underway.

## **Overview**

Use the Elastic integration to include Cato network and security data in your existing observability and security workflows. The native integration sends data directly from Cato to your Elastic deployment, so you can analyze Cato activity alongside data from other sources in a centralized platform. This helps you build dashboards, searches, and alerts in Kibana without requiring additional data collection mechanisms.

## **Elastic Data Sources**

The Elastic integration supports two data sources:

- **Events** - Generated when specific activity occurs in the network or system, such as when a policy rule is matched or a threat is detected. These records provide discrete, real-time insights into security and policy enforcement. The data is sent using Cato's [event schema](https://api.catonetworks.com/documentation/#definition-EventFieldName).
- **Flows** - Originate as network flows (5-tuple) and are enriched with application-level information as it becomes available from Cato engines. In addition to application and user context, flows include aggregated session data such as bytes, packets, and duration, providing a complete view of network activity over time. The [appStats schema](https://api.catonetworks.com/documentation/#definition-AppStatsFieldName) represents the full set of flow fields.

By default, new integrations export only **Events**. The **Flows** data source can generate significantly more data than the Events data source. The exact volume depends on your traffic. You can configure multiple integrations in the CMA to send different data sources as needed.

## **Use Cases**

### **Events**

Sample Company uses Elastic for centralized security monitoring and observability. As a Cato customer, it has Cato data about network activity, threats, user data, devices, and all other aspects of traffic traversing the Cato platform. The admin uses this integration to send that data directly to Elastic, where the SOC and NOC teams work with it alongside their other sources.

### **Flows**

A security analyst at Sample Company identifies a suspicious event where a user accessed a high-risk application that may be associated with data exfiltration. Using Cato events alone, the analyst can see the policy decision, user identity, and application, but not how much data was transferred or how long the session lasted.

With aggregated flow data, the analyst can view the full session context, including total bytes transferred, packet count, and session duration. This lets the analyst determine whether the activity involved minimal interaction or a large data transfer that may indicate exfiltration.

## **Prerequisites**

- To add a connector, you must have editor permission for **Integrations** (in the **Resources** section). For more information, see [Managing Admin Roles Using RBAC](/v1/docs/managing-admin-roles-using-rbac).
- An Elastic deployment (Elastic Cloud or self-managed) with permission to create an API key.
- Your Elastic endpoint URL, for example `https://&lt;your-elastic-endpoint&gt;`.
- A target index to receive Cato data, for example `logs-cato.events-default`. You can create it in advance or let Elastic create it on first write.
- Review the prerequisites for all Cato event integrations in [Getting Started with Event Integrations](/v1/docs/getting-started-with-event-integrations).

## **Creating the Elastic Integration**

To send Cato data to Elastic, create an API key in Elastic, confirm that the endpoint accepts data, and then create the integration in the CMA.

### **Step 1: Create an Elastic API Key**

**To create the API key:**

1. Log in to your Elastic deployment (Kibana).
2. Go to **Stack Management > API Keys**.
3. Click **Create API key**, enter a descriptive name such as `Cato Integration`, and click **Create API key**.
4. Copy the **API Key** value and store it securely.
5. Note your Elastic endpoint URL and the index you plan to use.

> [!TIP]
> Note:
> 
> Elastic displays the API key value once, when it is created. Copy it before you close the dialog. If you lose it, create a new key and use that instead.

### **Step 2: Test the Endpoint with curl**

Before you configure the integration in the CMA, confirm that your API key, endpoint, and index work. This helps isolate Elastic-side issues from issues with the CMA integration.

The Elastic bulk ingestion API authenticates with the `Authorization: ApiKey &lt;KEY&gt;` header and expects `application/x-ndjson` content:

```bash
curl -X POST "https://<your-elastic-endpoint>/_bulk" \
  -H "Authorization: ApiKey <KEY>" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary $'{"create":{"_index":"logs-cato.events-default"}}\n{"message":"test event from curl","event_type":"test"}\n'
```

Replace `&lt;your-elastic-endpoint&gt;` with your endpoint URL, `&lt;KEY&gt;` with the API key from Step 1, and `logs-cato.events-default` with your index.

A successful request returns HTTP `200 OK` with no item-level errors. In **Kibana > Discover**, filter to the target index and search for `test event from curl` to confirm that the document arrived.

### **Step 3: Create the Integration in the CMA**

**To create the Elastic integration:**

1. From the navigation menu, select **Resources > Integrations**.
2. On the **Configured Integrations** tab, click **New**. The **New Integration** panel opens.
3. Select **Elasticsearch**. The **Capability** is set to **Data Export** automatically.
4. In the **Auth** drop-down, select **API Key**.
5. Enter a **Name** for this integration and an optional **Description**.
6. Enter the **Endpoint URL** that you tested with curl above.
7. Enter the **API Key** that you created in Elastic.
8. Enter the **Index** that receives the data from Cato, for example, `logs-cato.events-default`.
9. Under **Data Sources**, select **Events**, **Flows**, or both.
10. **(Optional)** Add filters to control which data is sent to Elastic, [as described below](/docs/integrating-cato-data-with-elastic#filters).
11. Click **Save**.

Refresh the **Integrations** page. The integration appears in the **Configured Integrations** table with a **Connected** status.

## **Filters**

Use filters to control which Cato data is exported to Elastic. This helps reduce ingestion costs, minimize noise, and focus investigations on the data that is most relevant to specific sites, users, or regions. You can also use filters to route different subsets of data to different SIEM environments.

Use filter groups to define filters based on any [Event Field](/v1/docs/cato-event-schema) or combination of fields. Conditions within each group use AND logic. OR logic is applied between groups.

- **Events Filter** - Click **Add Filter** to define a condition, or **Add Group** to add a filter group.
- **Flows Filter** - Available when **Flows** is selected as a data source. It follows the same logic as the Events Filter.

Filters that are too narrow can exclude everything without showing any error. If no data arrives in Elastic after you save the integration, check the filter configuration first.

## **Troubleshooting**

| **Issue** | **Solution** |
| --- | --- |
| The integration shows a **Connectivity Error** | Check that the Endpoint URL, API Key, and Index are entered correctly, and that they match what you tested in Step 2. Confirm that the API key has not been revoked and still has write permission on the index. |
| No events arrive in Elastic | Check the Events Filter. A filter that is too narrow can exclude all data without reporting an error. |
| No flows arrive in Elastic | Confirm that **Flows** is selected under **Data Sources**, and check the Flows Filter for conditions that are too restrictive. |
| The integration doesn't show a **Connected** status after you save it | Refresh the **Integrations** page. If the status does not change, verify the API key permissions and the index name in Elastic. |
