---
title: "Socket X1600 Deployment Guide"
slug: "x1600-socket-deployment-guide-1"
updated: 2026-09-29T08:18:32Z
published: 2026-09-29T08:18:32Z
canonical: "knowledge.catonetworks.com/x1600-socket-deployment-guide-1"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Socket X1600 Deployment Guide

## Welcome to Your New Cato Socket

This guide explains how to deploy the Socket to a site and connect the site to the Cato Cloud.

You can also watch the following video tutorial on the Cato Academy: [Cato Socket Setup: Unboxing to Rack Ready](https://academy.catonetworks.com/cato-socket-setup-unboxing-to-rack-ready)

### Typical Site Topology

A typical deployment scenario is where the Cato Socket replaces the site's existing firewall. There are many other topologies and scenarios that are also supported.

The following diagram shows a typical topology for a site with two X1500 Sockets in a high availability (HA) configuration connected to two different ISPs.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-j72naag3.png)

#### Prerequisites

The following items are required before you start deploying the Socket:

- Cato Socket - The Socket model that was shipped to you
- ISP connection - the Internet connection through which the Socket connects to the Cato Cloud
- WAN IP - a DHCP or statically-assigned IP address
- Native Range - the LAN range that is directed towards the Socket
- DHCP Range - The DHCP assigned range(s) that the Socket supports (optional)
- Gateway IP - The network’s gateway's IP address
- Make sure that your networking devices and firewalls meet the requirements listed in [Cato Socket Connection Prerequisites and Known Limitations](https://support.catonetworks.com/hc/en-us/articles/360000891085-Cato-Socket-Connection-Prerequisites-and-Known-Limitations).

## Administrator Account Onboarding

- If you already have a Cato Networks account, skip to [Creating an X1600 Site in the Cato Management Application](/docs/x1600-socket-deployment-guide-1#UUIDe66eff24d389ddd27fc96434fca2cc76) (below)
- If you already have a Cato Networks account and you have created a site, skip to [Working with the X1600 Socket](/docs/x1600-socket-deployment-guide-1#UUID1f2981234e3fac763de6aef90b4a284d) (below)

After Cato opens an account for your organization, your account administrator must onboard to the Cato Management Application. This administrative access is required to create, configure, and assign the Socket with the appropriate site.

The onboarding procedure starts when your account’s administrator receives an invitation email from Cato Networks.

**To set your account password:**

1. Click the activation link to redirect to the password configuration window in your browser.
2. Set your password.
3. You will receive a second email and a link to the CMA.

## Deploying the X1600 Socket

This is a high-level overview of the process to deploy an X1600 Socket at the physical location of the site:

1. Power on the Socket and connect the WAN links to the Internet ([Connecting the X1600 Socket to the Cato Cloud](/docs/x1600-socket-deployment-guide-1#UUID290d7bbf820a8faaf93b399be08db623) - below).
2. Create the site in the Cato Management Application ([Connecting the X1600 Socket to the Cato Cloud](/docs/x1600-socket-deployment-guide-1#UUID290d7bbf820a8faaf93b399be08db623) - below).
3. In the Cato Management Application, assign the X1600 Socket to the relevant site ([Assigning the Socket to a Site](/docs/x1600-socket-deployment-guide-1#UUID4bc8ee6f5d698959f299ca4e08c98fef) - below).
4. Edit the site and define the LAN segments ([Configuring the LAN](/docs/x1600-socket-deployment-guide-1#UUID859ae672e34785ba9d65431f4d613d2b) - below).

### X1600 Socket Known Limitation

USB to LAN Adapter Compatibility – To connect an ethernet adapter via the USB port, you only connect it after the Socket is registered to your Cato account and fully upgraded to latest Socket version. Otherwise, connecting the ethernet adapter too early can cause interoperability issues.

For more information about supported add-ons, see [Supported Socket Transceivers and USB Ethernet Adapters](https://support.catonetworks.com/hc/en-us/articles/5220124178717-Supported-Socket-Transceivers-and-USB-Ethernet-Adapters).

### Connecting the X1600 Socket to the Cato Cloud

Connect the LAN and WAN ports on the X1600 front panel to the internal network and to the ISP.

1. Unbox the Socket.
2. Connect the LAN cables:
  - If the Socket is replacing a firewall, disconnect the Ethernet cable from the firewall and connect the cable to the Socket’s LAN port.
  - If the LAN is routed from a network device or existing firewall that is not being replaced, connect the Ethernet cable from the relevant port on that device to the Socket’s LAN port.
3. Connect the WAN cables:
  - If the Socket is connected directly to the ISP router, connect the Ethernet cable from the ISP device to the Socket’s port 1 (or port 1 and port 2 if you have multiple ISP connections).
4. After the LAN and WAN networks are connected, connect the power cable to the power supply input in the rear panel.

### Creating an X1600 Site in the Cato Management Application

Create a site in the Cato Management Application (CMA) for the site where you are deploying your new Socket.

**To create a new X1600 Socket site:**

1. Log in to the CMA.
2. From the navigation menu, click **Network > Sites**.
3. Click **New**. The **Add Site** panel opens.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-6wetm93n.png)

1. Configure the **General** settings for the site:
  1. Enter the **Site Name**.
  2. Select the **Site Type**. This option determines which icon is used for the site in the **Topology** window.
  3. In **Connection Type**, select **Socket X1600**.
  4. Configure the **Country**, and **State**, for the physical location of the site.
  5. **(Optional)** Customize the **Time Zone**. This setting is used to set the time frame for the Socket update Maintenance Window.
2. In the **WAN Interface Settings** section, configure the settings for the Sockets:
  1. If the site uses a link for the secondary ISP connection, select **Enable WAN2**.

**IMPORTANT:** If you are connecting a single ISP to WAN2, select this option to prevent connectivity loss when first connecting to Cato Cloud.
  2. Enter the values (in Mbps) for the **WAN1 Bandwidth** and **WAN2 Bandwidth** for **Downstream** and **Upstream**.

**Note:** Your upstream and downstream bandwidth for the WAN1 and WAN2 links are set according to the ISP bandwidth and the license that was purchased from Cato.
  3. If necessary, repeat the previous step for the **WAN2 Bandwidth**.
3. In the **LAN Interface Settings** section, configure the LAN **Native Range** for the site.

You can't use /31 or /32 CIDR blocks.

### Assigning the Socket to a Site

Once a Socket is up and running, it automatically connects to an optimal PoP in the Cato Cloud and checks if a new version of the Socket firmware is available.

**Note:** If the Socket detects that a new version of the firmware is available, it automatically performs an upgrade, and the CMA shows the **New Socket Detected** notification.

When the Socket has the latest firmware, the CMA displays the **Activate New Socket** notification and sends an email to the Activate New Socket mailing list. You can then activate and assign the Socket to the relevant site.

**To activate the Socket and assign it to a site:**

1. Click the notification icon![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/socket-x1700-deployment-guide-image-eupk6wbx.png).
2. In the list, locate the **Activate New Socket** notification and click **ACCEPT**.
3. In the **Assign Cato Socket to Site** window, in **Choose Site to assign Socket**, select the site for the new Socket and click **OK**.
4. The site is shown as connected in the **Monitoring > Topology** screen.

### Configuring the LAN

After you create the site, configure the network settings for the LAN.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-hl25t2z8.png)

**To configure the LAN settings for the site:**

1. From the navigation menu, click **Network > Sites** and select the new Socket site.
2. From the navigation menu, click **Site Configuration > Networks**.
3. Expand the LAN interface.
4. Review the **Local IP** and **DCHP Settings** for the site.

For more about configuring the settings for a site, see the [network range articles](https://support.catonetworks.com/hc/en-us/articles/4413280508433).

## Working with the X1600 Socket

### Overview of the X1600 Socket

This section describes the components on the X1600 Socket panels.

#### Front Panel Components

These are the LED indicators on the front panel of the X1600 Socket:

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-ois1bqp1.png)

| Icon | Description |
| --- | --- |
| ![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-d8zg3d3i.png) | **Socket LED** - off - Socket is powered off and disconnected from the power supply - green - Socket is powered and ready - blue - Socket OS firmware is installed - amber - Socket is powered off and connected to the power supply |
| ![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-x9bsz7ml.png) | **Network Connectivity LED** - green - Full connectivity to Internet and the Cato Cloud - blue - Full connectivity to Internet, no connectivity to the Cato Cloud - red - No network connectivity |

#### Rear Panel Components

These are the rear panel components of the X1600 Socket:

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-82xsscg1.png)

| Name | Description | LED Description |
| --- | --- | --- |
| Console | Used by Support to troubleshoot the Socket. Supports RS-232 cables, or any micro USB cable. | - RS-232 Cable connected - Left LED - N/A - Right - Green |
| 1 | 1 Gbps copper or 1 Gbps fiber for WAN traffic - You can only connect one cable - Supports auto-negotiation and full-duplex up to 1 Gbps | - Link has connectivity - Right LED - Green - Link is active - Right LED - Blinking green - 1 Gbps speed - Left LED - Orange |
| 2 | 1 Gbps copper or 1 Gbps fiber - You can only connect one cable - Supports auto-negotiation and full-duplex up to 1 Gbps | - Link has connectivity - Right LED - Green - Link is active - Right LED - Blinking green - 1 Gbps speed - Left LED - Orange |
| 3 & 4 | 10 Gbps fiber - 1 Gbps transceivers are not supported - Auto-negotiate is not supported | - Link has connectivity - Right LED - Green - Left LED - Green - Link is active - Right LED - Blinking green - Left LED - Green |
| 5 - 8 | 2.5 Gpbs copper ports By default, port 8 is the MGMT port Auto-negotiate is supported | - Link has connectivity - Right LED - Green - Link is active - Right LED - Blinking green - 1 Gbps speed - Left LED - Orange - 2.5 Gbps speed - Left LED - Green |
| 12 VDC | Power supply input | N/A |

#### Side Panel Components

These are the rear panel components of the X1600 Socket:

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-53xdqfvc.png)

| Name | Description |
| --- | --- |
| USB1 | USB 3.0 port |
| USB2 | USB 3.0 port |
| RESET F/D | Reset button - resets the Socket - Reset Socket WebUI password to **admin** - press for 5 - 15 seconds - Reset Socket, delete all configuration files, and unassign from the site - press for 25 - 35 seconds |
| Power | Power button - Powers the Socket on and off - Power off Socket - press for 10 seconds - Power on Socket - press for 3 seconds (Additional features will be added in the future) |

### Assigning a Static IP to the WAN (Optional)

If required by your Internet Service Provider, you can set a static IP for the WAN interface for the X1600 Socket.

**To set a static IP for the WAN interface:**

1. In your browser, type the URL https://[your Cato Socket's IP address]. For example: https://10.0.0.15

If this is a new Socket that has never been connected, connect your computer to port 8 (the default MGMT port), then in your browser type the following URL: https://169.254.100.1

1. Enter your login credentials.
  - If this is the first time that you are logging in to the window, use the following credentials:
  - **username** = admin
  - **password** = admin
  - You will then need to change these credentials to your own.
  - After six consecutive failed login attempts, you will be locked out of your account for at least 30 minutes.
2. In the Cato Socket Configuration window, click **Network Settings** and click **Static Address**.
3. In **IP Address**, enter the static IP address. If required, modify any other static address parameters.
4. Click **Update**.

### Connecting the Socket through PPPoE (Optional)

If required by your Internet Service Provider, you can define a PPPoE connection for the WAN interface for the X1600 Socket.

**To define a PPPoE connection for the WAN interface:**

1. In your browser, type the URL https://[your Cato Socket's IP address]. For example: https://10.0.0.15

If this is a new Socket that has never been connected, connect your computer to port 8 (the default MGMT port), then in your browser type the following URL: https://169.254.100.1

1. Enter your login credentials.
  - If this is the first time that you are logging in to the window, use the following credentials:
  - **username** = admin
  - **password** = admin
  - You will then need to change these credentials to your own.
  - After six consecutive failed login attempts, you will be locked out of your account for at least 30 minutes.
2. In the Cato Socket Configuration window, click **Network Settings** and click **PPPoE**.
3. In the **PPP account (user) name**, **PPP account secret (password)** and **Confirm password** fields, enter the information provided by your ISP. If required, modify any other PPPoE fields as instructed by your ISP.
4. Click **Update**.

## Mounting the X1600 Sockets - Rackmount

**To mount the X1600 Socket in a server rack:**

1. Insert the X1600 Socket into the rackmount bracket, oriented as shown. ![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-n0vk360a.png)

1. Align the mounting holes in the X1600 Socket with the holes located in the tabs on the rackmount bracket.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-lzi4h5lg.png)

1. Insert a screw into one of the mounting holes and snug. Do not overtighten.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-ilg82bua.png)

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-r2qd5wzb.png)

1. Insert the remaining screws into the mounting holes and snug. Do not overtighten.
  - Right-side view

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-95e76ac7.png)
  - Left-side view

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-45wsqiu6.png)
2. Install USB cables between the USB 3.0 Micro B connections on the rackmount bracket and the USB 3.0 Type A connections on the X1600 Socket.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-879598pt.png)

1. Secure the cables in place with a 300mm cable tie passed through the cable tie mounts on the rackmount bracket and snip off the excess.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-mzoq5zqi.png)

1. Route two 300mm cable ties underneath the PSU standoff on the rackmount bracket.
2. Place the PSU on the standoff with the cables oriented as shown.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-mqu6cpxj.png)

1. Secure the PSU to the rackmount bracket with the cable ties and snip off the excess. Screw the power cable into the X1600 Socket.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-zs4jzfdc.png)

1. Route five 99mm cable ties through the cable tie mounts on the rackmount bracket where shown.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-r5m1ojea.png)
2. Bundle the PSU cables and route them around the rackmount bracket as shown.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-h3pgin4t.png)

1. Secure the PSU cables with the cable ties. If necessary, bundle any excess cable slack and secure with the remaining 99mm cable tie. Snip off the excess.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-gdqer8a2.png)

## Mounting the X1600 Sockets - Wallmount

The mounting brackets can be mounted in two different positions. They can protrude out from the unit in the “Outboard” position, or for a cleaner look, they can be mounted in the “Inboard” position behind the unit as shown below.

- **Outboard Position** - Brackets can be installed before mounting the unit to the wall

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-wzfez3cy.png)
- **Inboard Position** - The brackets must be mounted to the wall before mounting the unit to the wall

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-923zgva4.png)

**Note:** The airflow for the X1600 is inbound through the rear panel (where the ports are located) and outbound through the sides of the socket. Make sure that these areas are not blocked or obstructed to enable proper cooling and venting of the Socket.

**To mount the X1600 Socket on a wall mount:**

1. Mount the power supply to the Power Supply mounting bracket using two cable ties as shown below.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-qno70mnr.png)

1. For the outboard position, follow these steps:

Continue with step 4 below.
  1. Attach the brackets to the unit using the M4 x 30mm screws.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-m8hp5xdl.png)
  2. Mark the four holes on the wall for the installation.

For more information about distance between the mounting holes, see [X1600 Wallmount Reference Diagrams](/docs/x1600-socket-deployment-guide-1#UUIDc93e59c644aa2f514cabc565a4561ca3).
  3. If needed, install the four plastic self-drilling dry wall anchors into the wall at the marked locations.
  4. Mount the unit to the wall using four M3.5x38mm screws.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-hylijbal.png)

1. For the inbound position, follow these steps:

Continue with step 4 below.
  1. Mark the four holes on the wall for the installation

For more information about the distance between the mounting holes, see [X1600 Wallmount Reference Diagrams](/docs/x1600-socket-deployment-guide-1#UUIDc93e59c644aa2f514cabc565a4561ca3).
  2. If needed, install the four plastic self-drilling dry wall anchors into the wall at the marked locations.
  3. Install the mounting brackets to the wall using four M3.5x38mm screws.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-25f8i57g.png)
  4. Install the X1600 Socket to the mounting brackets using the M4 x 30mm screws.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-ov42a1hm.png)

1. Mount the power supply to the wall next to the X1600 Socket using four M3.5x38mm screws and plug the power cable into the unit.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-t33ehwob.png)
2. Connect the desired cables (Ethernet, Console, USB).
3. Plug the power cord barrel connector into the 12 VDC input on the unit and tighten the lock ring.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-ta52gpxh.png)
4. Plug the power cord into a properly grounded outlet.

### X1600 Wallmount Reference Diagrams

These drawings are provided for reference when marking the mounting holes.

#### Outboard Position

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-myka0gfr.png)

#### Inboard Position

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/x1600-socket-deployment-guide-image-lq8jffzq.png)
