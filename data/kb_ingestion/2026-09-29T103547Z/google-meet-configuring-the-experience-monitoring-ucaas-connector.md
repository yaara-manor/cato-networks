---
title: "Google Meet: Configuring the Experience Monitoring UCaaS Connector"
slug: "google-meet-configuring-the-experience-monitoring-ucaas-connector"
status: "new"
updated: 2026-09-14T08:19:15Z
published: 2026-09-14T08:19:15Z
canonical: "knowledge.catonetworks.com/google-meet-configuring-the-experience-monitoring-ucaas-connector"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Google Meet: Configuring the Experience Monitoring UCaaS Connector

## Overview

Experience Monitoring provides enhanced context, such as packet loss or tunnel age, to give you the information you need to determine if the issues are related to your ISP, the Cato Cloud, or other sources.

You can also configure a connector with UCaaS applications to display application-specific metrics in the CMA to monitor the user experience when using the application.

To configure the Experience Monitoring UCaaS Connector, you need to:

1. Configure the integration within the SaaS application
2. Create the API connector in the CMA

### Benefits of Connecting Google Meet

Experience Monitoring analyzes the Experience record per participant session. For each participant it reports call-quality metrics across up to six streams — Audio, Video, and Screen sharing, each in the Upstream and Downstream direction:

- Latency (round-trip time)
- Jitter
- Packet loss
- Bitrate
- Frame rate (video / screen sharing)
- MOS (Mean Opinion Score, computed from latency, jitter, and packet loss)

## Configuring the Google Meet Integration

To configure the Google Cloud integration, create the required configurations in your Google Cloud account, then configure the connector within the CMA.

### Prerequisites

- A Google Workspace subscription that includes Google Meet, with the Admin SDK Reports API available
- A Google Workspace Super Admin account

### Step 1: Configure the Integration in the Google Cloud Console

**To configure the Google Meet integration:**

1. In your [Google Cloud Console](https://console.cloud.google.com/), click **Select a Project**.
2. Click **New project**. ![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(21).png)
3. Choose a **Name, Organization,** and **Parent resource** and click **Create**.
4. Navigate to **APIs & Services > Library**.
5. Search for Admin SDK. ![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(22).png)
6. Click on **Admin SDK API** and click **Enable**.
7. Navigate to **IAM & Admin > Service Accounts**.
8. Select the project you created in step two, and click **Create service account**.
9. Add a **Service account ID** and click **Create and continue**.
10. Click **Done**.
11. In the new service account copy and save the numeric **OAuth 2.0 Client ID** to be used later in the procedure.
12. Click on the service account you created and navigate to the **Keys** tab.
13. Click **Add key > Create new key**.
14. Choose the JSON key type and click **Create**. A JSON file containing the private key is downloaded.
15. Copy and save the **Private key** so it can be added to the CMA.
16. In the [Google Admin console](https://admin.google.com/), navigate to **Security > Access and Data Control > API control**.
17. Under **Domain wide delegation**, select **Manage Domain Wide Delegation**.
18. Click **Add new**.
19. In the **Client ID** field, paste the numeric **OAuth 2.0 Client ID** you saved above.
20. In the **OAuth scopes** field, paste the following as a single comma-separated line: `http://www.googleapis.com/auth/admin.reports.audit.readonly`
21. Click **Authorize**.

### Step 2: Create the API Connector in the CMA

After you have set up an integration with the required application, add the details in the CMA.

**To create the API connector in the CMA:**

1. From the navigation menu, click **Resources > Integrations.**
2. Click the **Configured Integrations** tab.
3. Click **New**. The **New Integration** panel opens.
4. Select the **SaaS Application** you want to add. **Note:** Enter the **Private Key** in JSON format.
5. In the **Capability** drop-down select **Experience Monitoring**.
6. Add the details , during step one:
  - Service Account Key: The full contents of the JSON key file downloaded in Step 1
  - Admin Email: The email of a Google Workspace admin user that the service account can impersonate when reading reports
7. Click **Save**.

The app is visible on the **Integrated Apps** table with a **Connected** status.

## Known Limitations

- Google Meet reports whole-session aggregates only (mean/max per call). Per-minute time series are not available. The connector expands each session's aggregate into 1-minute buckets spanning the participant's session.
- Metrics Google Meet does not expose are omitted or left empty (for example internal IP, MAC address, CPU usage, Wi-Fi signal, and disconnection reason).
- Streams are only reported for media that was actually used, so a call without video or screen sharing will not show those streams.
