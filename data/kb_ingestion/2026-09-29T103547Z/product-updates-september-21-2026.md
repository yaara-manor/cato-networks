---
title: "Product Updates - September 21, 2026"
slug: "product-updates-september-21-2026"
updated: 2026-09-22T07:38:28Z
published: 2026-09-22T07:38:28Z
canonical: "knowledge.catonetworks.com/product-updates-september-21-2026"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Product Updates - September 21, 2026

- **Data Export Connectors for SIEM and Security Analytics Platforms:** Forward events and network flows directly to leading SIEM and security analytics platforms using turnkey integrations configured in the CMA. This brings network and security data into existing SOC workflows without custom scripts or connectors.
  - Securonix
  - SentinelOne Singularity Data Lake
  - Palo Alto Cortex
  - Elastic
- **Public API Queries for User Groups:** Retrieve user group data programmatically with two account-scoped read queries. This enables automated auditing, reporting, and membership lookups without relying on the CMA. This covers manually created, LDAP, SCIM, Integration, and Dynamic user groups. System Groups are not included.
  - `usersGroupList` for a list of groups and related metadata
  - `usersGroup` for a single group by ID or name, including its member list
- **Apply AI Security to File Attachments:** Protect sensitive data in files users upload to AI providers by applying the [User Interaction Policy](https://knowledge.catonetworks.com/docs/working-with-the-user-interaction-policy) to attachments (show me the [User Interaction Policy page](https://externallink.cc.catonetworks.com/#/account/me/endUsersProtectionsPromptsPolicy)).
  - Enforce the same data protection controls for uploaded files and prompts
  - AI Security for Users license required
- **Confidence Level Condition for Network Rules:** Apply Network Rules based on the user’s authentication confidence level to control network behavior according to their current authentication status.
- **Introducing Standardized Versioning for the Cato Terraform Provider:** The Cato Terraform provider now uses a versioning schema `(X.Y.Z)`
  - No impact on existing configurations
- **Cato Client Support for macOS 27:** The next macOS Client version (v6.1.1) will contain official support for macOS Golden Gate (version 27).
