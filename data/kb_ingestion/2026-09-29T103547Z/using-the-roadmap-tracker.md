---
title: "Using the Roadmap Tracker"
slug: "using-the-roadmap-tracker"
updated: 2026-09-14T14:42:08Z
published: 2026-09-14T14:42:08Z
canonical: "knowledge.catonetworks.com/using-the-roadmap-tracker"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Using the Roadmap Tracker

## Overview

The Roadmap Tracker gives you an account-specific view of what's new in Cato. It shows the features Cato has recently announced and where each one stands for your account: already enabled, still on its way, or available to try through the Early Availability program.

For each feature you can also see what it does, what it requires before you can use it, such as a license or a minimum Cato Client or Socket version, and when its status last changed. Features stay on the list until 30 days after they become available in your account, so the page stays focused on what's new for you.

You can also get this information from Ask AI, without opening the page. For example, ask whether a specific feature is available in your account, or which recently announced features have not yet reached your account.

Cato announces new features in the weekly [Release Notes](/v1/docs/understanding-cato-product-updates-release-notes) and then activates them gradually across accounts, which is why a feature can appear here before it reaches you. For more information about the rollout process, see [Understanding Rollout to the Cato Cloud](/v1/docs/understanding-rollout-to-the-cato-cloud).

## Viewing the roadmap tracker

To open the page, from the navigation menu click **Account > Roadmap Tracker**.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(215).png)

The Roadmap Tracker is visible to all admins and is not restricted by RBAC permissions.

### Understanding the Feature Statuses

Each feature shows one of these statuses for your account:

| **Status** | **What it means** |
| --- | --- |
| **Available in Account** | The feature has reached General Availability (GA) and is enabled for your account |
| **Available in Account (EA)** | The feature is available for your account as part of the Early Availability program |
| **Rolling out** | The feature has reached GA and is gradually rolling out to all accounts, but is not yet enabled for your account |
| **Early Availability** | The feature is in Early Availability. To request access, email [ea@catonetworks.com](mailto:ea@catonetworks.com) |

**Notes:**

- The Roadmap Tracker never shows an estimated arrival date for a feature that is still rolling out.
- Some features are relevant only to partners. These appear in partner accounts only.
- The status shows only whether Cato has enabled the feature for your account — it doesn't account for the **License** and **Prerequisites** columns. A feature can show as **Available in Account** and still not be usable until you have the required license and the minimum Socket or Cato Client version.

## Reviewing the Feature List

The table shows the following information for each feature:

| **Column** | **Description** |
| --- | --- |
| **Domain** | The product areas the feature belongs to, such as Network, SD-WAN, or CASB. |
| **Name** | The name of the feature, as it appears in the Release Notes. |
| **Description** | A summary of what the feature does. |
| **License** | The license or licenses required to use the feature. |
| **Status Update** | The date of the most recent status change. By default, the table is sorted by this column, with the most recent change first. |
| **Prerequisites** | The minimum Cato Client, Socket, Cato Browser, or Browser Extension version required for the feature. |
| **Status** | The current status of the feature **for your account**. For features that are available in your account, this column can also show a **View** link. |

Use the **Rows per page** and page controls at the bottom of the table to move through the list.

### Opening a Feature in the CMA

Features available in your account may include a View link in the **Status** column and in the **Feature Review** panel. This is a shortcut to the feature itself, so you can try it as soon as you notice it in the tracker.

**To open a feature from the tracker:**

- Click **View**.

The feature opens in the CMA in a new browser tab, and the Roadmap Tracker stays open in the original tab. Depending on the feature, the link opens either the feature page or the page that contains it.

## Filtering the Feature List

The summary at the top of the page shows how many features are currently in each status. The **Available in Account** counter shows the features that became available in the past 30 days. To filter the list by status, click the status button in the summary, for example **Rolling out**.

## Viewing the Details for a Feature

Open a feature to see its full description and the complete list of prerequisites, including any minimum versions that are shortened in the table.

**To view the details for a feature:**

1. In the table, click the row for the feature.

The **Feature Review** panel opens.
2. Review the details for the feature:
  - **Status** and **Status Update** – the current status and the date it last changed
  - **Feature Overview** – the full description of the feature
  - **Prerequisites** – the licenses required and the minimum Cato Client, Socket, Browser Extension, and Cato Browser versions
3. To open the feature in the Cato Management Application, click **View**. For more information, see [Opening a Feature in the CMA](/docs/using-the-roadmap-tracker#opening-a-feature-in-the-cma).
4. To move to the next or previous feature without closing the panel, use the arrows at the top of the panel.

## Requesting Access to an Early Availability Feature

Features with a status of **Early Availability** are not yet generally available and are not enabled automatically. To ask to join the Early Availability program for a feature, email [ea@catonetworks.com](mailto:ea@catonetworks.com) as explained in the EA tooltip:

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(214).png)
