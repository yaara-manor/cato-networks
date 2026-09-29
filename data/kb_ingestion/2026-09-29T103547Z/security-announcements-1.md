---
title: "Security Announcements"
slug: "security-announcements-1"
type: "index"
canonical: "knowledge.catonetworks.com/security-announcements-1"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Security Announcements

18 articles

## [CVE-2025-14213 Socket WebUI: OS Command Injection](https://knowledge.catonetworks.com/docs/cve-2025-14213-socket-webui-os-command-injection.md)

Published on 2026-06-22

Description Socket versions lower than v25 contain a command injection vulnerability that allows an authenticated attacker with access to the Socket Web Interface (WebUI) to execute arbitrary...

## [CVE-2025-15040 - Open Redirect in Windows SDP client embedded browser](https://knowledge.catonetworks.com/docs/cve-2025-15040-open-redirect-in-windows-sdp-client-embedded-browser.md)

Published on 2026-06-22

Description The embedded Chromium browser in the Windows Cato Client is vulnerable to an open redirect attack using the catoias:// scheme (used by the Cato client embedded browser) , which might be...

## [Security Vulnerability (CVE-2026-12374) that Impacts macOS Client Versions Lower than 5.13.1](https://knowledge.catonetworks.com/docs/security-vulnerability-cve-2026-12374-impacts-macos-client-versions-lower-5131.md)

Published on 2026-08-10

Cato recently identified a security vulnerability ( CVE-2026-12374 ) that impacts Cato macOS Clients with versions lower than 5.13.1. This CVE can let attackers who have access to the macOS Client on...

## [CVE-2025-7012 Linux SDP Client: Local Privilege Escalation via Symbolic Link Handling](https://knowledge.catonetworks.com/docs/cve-2025-7012-linux-sdp-client-local-privilege-escalation.md)

Published on 2026-06-22

Description The cato-clientd service in the Cato Linux Client v5.4 and below writes sensitive files to the user's home directory during authentication: cato_cred.cfg.tk cato_cred.cfg, and a log file...

## [Security Vulnerability (CVE-2025-3886) that Impacts macOS Client Versions Lower than 5.8](https://knowledge.catonetworks.com/docs/security-vulnerability-cve-2025-3886-impacts-macos-client-versions-lower-5-8.md)

Published on 2026-06-22

Cato recently identified a security vulnerability ( CVE-2025-3886 ) that impacts Cato macOS Clients with versions lower than 5.8. This CVE can let attackers who have access to the macOS Client on the...

## [Security Vulnerability: CVE-2024-3661: Tunnel Vision](https://knowledge.catonetworks.com/docs/security-vulnerability-cve-2024-3661-tunnel-vision.md)

Published on 2026-06-22

On May 6th, 2024 the Leviathan Security Group published an article detailing a technique to bypass most VPN applications ( CVE-2024-3661). The technique lets attackers to trick many VPN clients into...

## [CVE-2024-6978 Windows SDP Client: Local root certificates can be installed by low-privileged users](https://knowledge.catonetworks.com/docs/cve-2024-6978-windows-sdp-client-local-root-certificates-installed.md)

Published on 2026-06-22

Description The Windows client VPN service has a security vulnerability in the handling of one of the commands that arrives from the UI process via IPC. A malicious SendManageCertificate command can...

## [CVE-2024-6977 Windows SDP Client: Sensitive data in trace logs can lead to account takeover](https://knowledge.catonetworks.com/docs/cve-2024-6977-windows-sdp-client-sensitive-data-trace-logs-account-takeover.md)

Published on 2026-06-22

Description The Client trace log files were found to contain the tunnel authentication data. This can be used to connect to the tunnel on behalf of the user. To exploit this, an attacker must have...

## [CVE-2024-6974 Windows SDP Client: Local Privilege Escalation via self-upgrade](https://knowledge.catonetworks.com/docs/cve-2024-6974-windows-sdp-client-local-privilege-escalation-via-self-upgrade.md)

Published on 2026-06-22

Description The self-upgrade mechanism in the Windows SDP client saves a client installation file in C:\Windows\Temp . This folder is writeable by all users, even low-privileged ones. When the...

## [CVE-2024-6975 Windows SDP Client: Local Privilege Escalation via openssl configuration file](https://knowledge.catonetworks.com/docs/cve-2024-6975-windows-sdp-client-local-privilege-escalation-openssl.md)

Published on 2026-06-22

Description When the Windows VPN service starts, it tries to load an OpenSSL configuration file from a non-existing path: C:\Work\WinVPNClient\ThirdParty\openssl\openssl-3.1.1\VS2022\SSL64\openssl.cnf...

## [CVE-2024-6973 Windows SDP Client: Remote Code Execution via crafted URLs](https://knowledge.catonetworks.com/docs/cve-2024-6973-windows-sdp-client-remote-code-execution-via-crafted-urls.md)

Published on 2026-06-22

Description In the catoias:// URL scheme, that are parsed by the Windows SDP Clients, there are no sufficient validations on the external_browser parameter, which is controlled by the Client. This is...

## [Security Vulnerability (CVE-2023-43976) that Impacts macOS Client v5.3.x](https://knowledge.catonetworks.com/docs/security-vulnerability-cve-2023-43976-that-impacts-macos-client-v5-3-x.md)

Published on 2026-06-22

Overview We are letting you know of a security vulnerability (CVE-2023-43976) that was recently identified and impacts Cato macOS Clients v5.3.x. This CVE can let attackers who have access to the...

## [CVE-2022-28199 - NVIDIA DPDK Vulnerability](https://knowledge.catonetworks.com/docs/cve-2022-28199-nvidia-dpdk-vulnerability.md)

Published on 2026-06-22

Overview This article will discuss information pertaining to the critical NVIDIA DPDK vulnerability, which may impact vSockets running on virtual machines in Microsoft Azure. In addition, the article...

## [CVE-2021-44228: Apache Log4J RCE](https://knowledge.catonetworks.com/docs/cve-2021-44228-apache-log4j-rce.md)

Published on 2026-06-22

Overview This article will discuss information pertaining to the Log4j Remote Code Execution (RCE) vulnerability, and steps that Cato have taken to ensure that our customers stay protected. This...

## [Ransomware: The Kaseya VSA Supply Chain Attack](https://knowledge.catonetworks.com/docs/ransomware-the-kaseya-vsa-supply-chain-attack.md)

Published on 2026-06-22

Overview This article will discuss information pertaining to the Kaseya VSA Supply-Chain Ransomware attack, and steps that Cato have taken to ensure that our customers stay protected. As of July 7th...

## [CVE-2021-1675 and CVE-2021-34527: PrintNightmare - Windows Print Spooler RCE](https://knowledge.catonetworks.com/docs/cve-2021-1675-and-cve-2021-34527-printnightmare-windows-print-spooler-rce.md)

Published on 2026-06-22

Overview This article will discuss information relating to the following vulnerabilities: Background There are currently two CVEs of note: In June 2021, a remote code execution (RCE) vulnerability in...

## [CVE-2021-21972 VMware vCenter RCE](https://knowledge.catonetworks.com/docs/cve-2021-21972-vmware-vcenter-rce.md)

Published on 2026-06-22

Overview On February 23 2021, VMware released a security advisory (VMSA-2021-0002) to address two vulnerabilities in vCenter Server , as well as a vulnerability in the VMWare ESXi hypervisor. Impact...

## [SolarWinds SUNBURST Malware and the Cato Cloud](https://knowledge.catonetworks.com/docs/solarwinds-sunburst-malware-and-the-cato-cloud.md)

Published on 2026-06-22

On Sunday, December 13 2020, FireEye released information related to a highly evasive attack in the SolarWinds Supply Chain. SolarWinds was the victim of a cyberattack, where malware (SUNBURST) was...
