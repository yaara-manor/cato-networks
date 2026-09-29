---
title: "Cato Event Schema"
slug: "cato-event-schema"
updated: 2026-08-18T17:00:47Z
published: 2026-08-18T17:00:47Z
canonical: "knowledge.catonetworks.com/cato-event-schema"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Cato Event Schema

> [!TIP]
> **Important:** The Cato schema explorer is a reference tool. It may take time to include new fields and enum values added to the CMA after the date the article was last updated.

## Overview

Cato provides an embedded schema exploration tool that helps you understand how Cato event and flow data is structured. Use it to build and maintain SIEM parsers, agents, automations, and other integrations that rely on accurate field-level mappings.

The tool helps you explore the schema in several ways:

- **Event Type**: Understand the high-level categories of Cato events, such as Connectivity, Security, System, and AI Security. This helps you identify the right event area before reviewing specific event data.
- **Events**: Review the specific event subtypes within each event type and see which fields are included for each subtype. This helps you map integrations to the exact event data they need.
- **Event Fields**: Search and review all fields used across Cato events. This helps you validate field names, expected values, and data formats when building parsers or normalizing event data.
- **Flow Fields**: Search and review fields used in Cato flow records. This helps you map traffic and connectivity data for analytics, reporting, SIEM ingestion, and custom integrations.

You can explore the schema directly in the article, or download the data in CSV format for offline analysis, documentation, or integration development. There may be small discrepancies between the schema explorer and the CSV files.

These are descriptions of event fields for the Cato Management Application (CMA). Event fields are frequently updated, for the full list of event fields, please refer to the Cato GraphQL API Reference for [EventFieldName](https://api.catonetworks.com/documentation/#definition-EventFieldName).

For customers that use the Cato API for event data, see [Cato API Potentially Breaking Changes and EoL](https://knowledge.catonetworks.com/v1/docs/cato-api-potentially-breaking-changes-and-eol) for notifications on potentially breaking changes and end-of-life (EoL) announcements for the Cato GraphQL API schema. We recommend that you follow the article to automatically receive email notifications for updates and changes.

## Cato Data Schema Explorer

[Embedded content](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/cato_schema_explorer.html)
