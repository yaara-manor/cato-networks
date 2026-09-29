---
title: "Using the Cato Mobile CMA App (EA)"
slug: "using-the-cato-mobile-cma-app"
status: "new"
updated: 2026-09-27T11:58:07Z
published: 2026-09-27T11:58:07Z
canonical: "knowledge.catonetworks.com/using-the-cato-mobile-cma-app"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Using the Cato Mobile CMA App (EA)

> [!TIP]
> **Note:** This is an Early Availability (EA) feature that is only available for limited release. For more information, contact your Cato Networks representative or send an email to [ea@catonetworks.com](mailto:ea@catonetworks.com).

## **Overview**

Cato Mobile CMA is a mobile app that shows you the current state of your Cato environment on your mobile device. It gives you key metrics, recent trends, and the top items that need attention. This lets you check your environment when you are away from your desk.

The app is read-only. You can look at your account, but you cannot change configuration, run troubleshooting steps, or open support tickets from the app. Mobile CMA helps you quickly determine whether your environment needs attention. Use the browser-based CMA to investigate issues and make changes.

> [!TIP]
> Note:
> 
> Mobile CMA does not provide remote connectivity to your network, and it is not related to the Cato Client. You do not need the Cato Client installed to use it.

### **Who Uses Mobile CMA**

The app is built for two kinds of users:

- An executive away from the office who wants key metrics and recent trends, and confirmation that nothing urgent is happening, without going into detail.
- An admin away from their laptop who wants an overall view of the state of their networking and security.

For anything beyond that picture, including full lists, detailed analysis, and any configuration changes, use the browser-based CMA.

## **Install the App**

Mobile CMA is available for iOS and Android, with the same features on each.

During Early Availability, Cato Mobile CMA is not published in the public app stores. Program participants receive a download link for their device.

During EA, Cato distributes the iOS app through Apple TestFlight. Install TestFlight from the App Store, and then open the link you receive.

At General Availability, install Mobile CMA directly from the Apple App Store or Google Play.

## **Sign In to Mobile CMA**

You sign in with the same admin credentials that you use for the browser-based CMA. There is no separate mobile account to create.

To sign in to Mobile CMA:

1. Open the app and enter your admin email address. The app uses the address to identify your account.
2. Authenticate the same way you do for the browser-based CMA. If your account uses single sign-on, the SSO flow runs as usual, on a page sized for your mobile device.

Your CMA permissions still apply to what you can see. If your admin role does not include a particular area, the tiles for that area do not appear. Regardless of your role, the app itself is read-only.

> [!TIP]
> Note:
> 
> Sign in with an admin that belongs to a single account. The app does not present a list of accounts to choose from. Partner admins, system admins, and other multi-account admins cannot select which account to open. They should create unique admin accounts for each tenant.

## **The Home Page**

The home page opens on a summary of your account for the selected time period.

![The Mobile CMA home screen, showing the main widget, the throughput graph, and the first attention tile.](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(232).png)

### **The Main Widget**

At the top of the home page, a widget shows total traffic in the center, surrounded by counts for **Sites**, **Users**, **Apps**, and **Devices**. A badge on one of these counts indicates that the category needs attention.

Tap any of the four counts to redraw the graph immediately below the widget for that category. The count you tap is highlighted, and the graph title changes (for example, to **Users Max Throughput**). With nothing selected, the graph shows **Account Max Throughput**. **Devices** has no throughput graph, so the graph does not change when you tap it.

Use the time selector at the top of the page to change the period. You can choose **1 hr**, **2 hr**, **24 hr**, or **7 days**. These periods cover recent activity, which is what the app is for. To look further back, use the browser-based CMA.

### **Attention Tiles**

Below the graph, tiles are grouped into carousels, starting with **Needs Your Attention**. Each carousel covers one topic, such as your account risk score, posture checks, entities, throughput, and AI security. Swipe a carousel sideways to move between its tiles.

What appears depends on your account:

- Tiles for an area that your admin role does not cover are not shown.
- Tiles for a feature that your account is not licensed for are replaced by a tile describing the feature.

The layout is the same for everyone. You cannot reorder, add, or dismiss tiles.

## **Feed**

The **Feed** tab lists the items that need attention, on two tabs:

- **Stories** - the open stories for your account, each with its severity, source, and the time it opened. This tab requires an XOps license.
- **Posture** - the failed posture checks for your account, each with its severity and the area it applies to.

On each tab, use the category filters to narrow the list. The heading above the list shows how many items you are seeing out of the total. Mobile CMA shows only the top items. To work through everything, use the browser-based CMA.

![The Feed tab showing open stories and failed posture checks, and the Entities tab showing top sites.](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(233).png)

## **Entities**

The **Entities** tab lists the objects behind the tiles on the home page, on separate tabs for **Sites**, **Users**, **Apps**, and **Devices**. Each tab has its own sort options suited to that entity. For example, sort sites by stories, status, or traffic, and sort applications by usage, risk, or experience. Tap an entry to see the details for that entity.

As with the Feed tab, these are the top entries, not the complete list.

## **AI Agent**

The **AI Agent** answers questions about your account in short replies suited to a small screen. Tap one of the suggested prompts or type your own question.

The app’s AI Agent is separate from Ask AI in the browser-based CMA. The two do not share conversation history, so a question you ask on your mobile device does not appear in the browser-based CMA, and the reverse. The AI Agent produces text-only answers. For charts, visualizations, and agentic capabilities, use Ask AI in the browser-based CMA.

## **Refresh the Data**

Mobile CMA reads from the same account as the browser-based CMA, so any change made in the account is reflected in the app. For example, if a colleague brings a site back up, the related story clears in the app when you refresh the data.

You can manually refresh at any time with the standard pull-down action familiar from many other mobile apps.

## **Settings**

Open the menu at the top of the page and select **Settings**. The page shows the account and admin you are signed in with.

- **Appearance** - choose **System**, **Light**, or **Dark**. **System** follows your device's appearance setting.
- **Sign Out** - sign out of the app.

## **Known Limitations**

- No notifications. Push notifications are not supported in Mobile CMA, and there’s no connection to the notification subscriptions or mailing lists configured in the browser-based CMA. Check the app to see the current state of your account.
- The **Security** tab is not available in this release.
