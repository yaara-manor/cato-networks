---
title: "Configuring CrowdStrike Device Risk Score Checks for Device Posture"
slug: "configuring-crowdstrike-device-risk-score-checks-for-device-posture"
status: "new"
updated: 2026-09-27T14:35:04Z
published: 2026-09-27T14:35:04Z
canonical: "knowledge.catonetworks.com/configuring-crowdstrike-device-risk-score-checks-for-device-posture"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Configuring CrowdStrike Device Risk Score Checks for Device Posture

## Overview

Device Posture checks let you evaluate the security state of a device before allowing access to network resources or applications. You can use these checks in access policies to enforce conditional access based on attributes such as Client status, operating system, or security configuration.

Cato retrieves the CrowdStrike Zero Trust Assessment (ZTA) score for each device and lets you build posture checks around it, so access decisions reflect the risk level that CrowdStrike has already calculated for the device. This means you can apply risk-based access control without maintaining a second set of posture logic in the Cato Management Application (CMA).

This capability is available as part of the Cato ZTNA license. No additional license is required.

### Prerequisites

- The [CrowdStrike Device Management integration](https://knowledge.catonetworks.com/docs/crowdstrike-configuring-the-device-management-integration) is configured in your account and shows a **Connected** status
- The initial synchronization between Cato and CrowdStrike is complete, so that devices have a risk score in Cato
- The CrowdStrike Falcon agent is installed on the device and is reporting a ZTA score
- You have appropriate permissions in the CMA to configure Device Posture

### Supported Operating Systems

CrowdStrike Device Risk Score checks are supported for devices running these operating systems:

- Windows:
  - Fully supported for all devices with and without the Cato Client
  - For devices using, or connected through, multiple Network Interface Cards (NICs) at once, Cato Client version 6.8 or higher is required
- macOS:
  - Fully supported for all devices with and without the Cato Client
  - Not supported on devices using, or connected through, multiple NICs at once

Devices running iOS, Android, and Linux are not evaluated by this check. For these devices, the outcome is determined by the **Pass the check when the device risk score is unavailable** setting in the check (see [Handling Devices Without a Risk Score](/v1/docs/configuring-crowdstrike-device-risk-score-checks-for-device-posture#handling-devices-without-a-risk-score1)).

## Use Case

Sample Company has an admin who is responsible for controlling access to sensitive internal applications, such as the finance and HR systems. The company already runs CrowdStrike Falcon on its endpoints, and the security team treats the CrowdStrike risk score as the authoritative measure of how risky a device is. Until now, that signal lived only in CrowdStrike: access decisions in Cato were based on posture checks that the admin had to define and maintain separately, and a device that CrowdStrike had flagged as risky could still reach protected applications.

The Device Risk Score check removes that gap. Cato retrieves the risk score for each device through the CrowdStrike connector, so the admin can build access rules directly on the score that the security team already trusts, without recreating the same risk logic a second time in Cato.

The admin creates a Device Risk Score check in **Resources > Device Posture > Device Checks** with the criteria **Risk Score is above (inclusive) 76 (low)**, and adds the check to a Device Posture profile. Applying that profile in the company's access policies produces the following behavior:

- Devices with a score of 76 or higher (Low risk) pass the check, and the profile allows them to access protected applications through ZTNA policies
- Devices with a lower score fail the check, and access is not permitted unless other rules apply
- Devices with no recognized risk score fail the check, so unmanaged or unreported devices do not gain access by default

Sample Company can also build a graduated model by creating more than one check and using each one in a different profile: for example, a Low-risk check in a profile that grants full access, and a Medium-risk check in a profile that grants limited access only.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(216).png)

## About the CrowdStrike Risk Score

CrowdStrike continuously calculates a ZTA score for each device with a Falcon agent, and Cato retrieves this score through the CrowdStrike connector. CrowdStrike Risk Scores range from 1 to 100, where **1 is the most risky, and 100 indicates no risk**.

Cato groups the score into four risk levels:

| Risk level | Score range |
| --- | --- |
| Critical | 1 - 25 |
| High | 26 - 50 |
| Medium | 51 - 75 |
| Low | 76 - 100 |

When you configure the check, you set the criteria as **Risk Score is** [operator] [threshold]:

- **above (inclusive)** – the device passes the check when its score is equal to or higher than the threshold, in other words when it is at the selected risk level or safer. The available thresholds are `1 (critical)`, `26 (high)`, `51 (medium)`, and `76 (low)`. For example, `above (inclusive)` + `76 (low)` passes devices with a score of 76 or higher.
- **below (inclusive)** – the device passes the check when its score is equal to or lower than the threshold, in other words when it is at the selected risk level or riskier. The available thresholds are `100 (low)`, `75 (medium)`, `50 (high)`, and `25 (critical)`. For example, `below (inclusive)` + `25 (critical)` passes only devices with a score of 25 or lower.

In each case, the threshold is the boundary score of the risk level in the direction of the operator, so you select a risk level rather than typing a number. This means the list of thresholds changes when you change the operator: **above (inclusive)** offers the lowest score in each risk level, and **below (inclusive)** offers the highest.

## Creating a New Device Posture Check for CrowdStrike Device Risk Score

### Handling Devices Without a Risk Score

A device can have no recognized risk score for several reasons: the Falcon agent is not installed, the device has not yet synchronized with Cato, or the operating system is not covered by this check.

The **Pass the check when the device risk score is unavailable** setting controls what happens in these cases:

- **Cleared (default)** – the check fails. Access is denied unless another check in the policy allows it. Use this for a strict, fail-closed posture.
- **Selected** – the check passes. Use this if you are rolling the check out gradually, or if your account includes devices that CrowdStrike does not cover and you do not want to block them.

Create a device posture check based on the CrowdStrike device risk score. After you create the check, you can apply it to new or existing [posture profiles](https://knowledge.catonetworks.com/docs/creating-device-posture-profiles-and-device-checks).

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(217).png)

### Configuring a CrowdStrike Device Risk Score check

1. In the CMA, go to **Resources > Device Posture** and in the **Device Checks** tab, click **New**.
2. In the **General** section, provide the **Name** and **Description** of this check.
  1. Set the **Source** to **3rd Party Vendor**.
  2. Set the **Type** to **Device Risk Score**.
3. In the **Vendor** section, set the **Vendor Name** to **CrowdStrike (ZTA)**. To confirm that the connector for this vendor is set up, click **View integrations**.
4. In the **Criteria & Additional Settings** section, use the **Risk Score is** fields to select the operator and risk score threshold that the device must satisfy to pass this check:
  - In the operator field, select **above (inclusive)** or **below (inclusive)**
  - In the threshold field, select the risk level. The values offered depend on the operator: **1 (critical)**, **26 (high)**, **51 (medium)**, and **76 (low)** for **above (inclusive)**, or **100 (low)**, **75 (medium)**, **50 (high)**, and **25 (critical)** for **below (inclusive)**.
  - For example, select **above (inclusive)** and **76 (low)** so that only devices with a score of 76 or higher pass the check.
5. If you want to let the check pass when Cato has no risk score for the device, select **Pass the check when the device risk score is unavailable** from **Additional Settings.**
6. Click **Apply**.

The new check is added to the **Device Checks** table, where the **Category** column shows **Device Risk Score**, the **Vendor** column shows **CrowdStrike (ZTA)**, and the **Criteria** column shows the operator and threshold you selected.

## Next Steps

After you create the check, add it to a device posture profile and use that profile in your policies:

1. Add the check to a new or existing profile in the **Device Posture Profiles** tab. For more information, see [Creating Device Posture Profiles and Device Checks](https://knowledge.catonetworks.com/docs/creating-device-posture-profiles-and-device-checks).
2. Use the profile in your access policies, such as the [Client Connectivity Policy](https://knowledge.catonetworks.com/docs/client-connectivity-policy-continuous-posture-checks-check-policy), Internet Firewall, or WAN Firewall rules.
