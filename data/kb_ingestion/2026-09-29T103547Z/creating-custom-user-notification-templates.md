---
title: "Creating Custom User Notification Templates"
slug: "creating-custom-user-notification-templates"
status: "new"
updated: 2026-09-14T08:23:19Z
published: 2026-09-14T08:23:19Z
canonical: "knowledge.catonetworks.com/creating-custom-user-notification-templates"
---

> ## Documentation Index
> Fetch the complete documentation index at: https://knowledge.catonetworks.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Creating Custom User Notification Templates

## Overview

When traffic matches a security rule with a Block or Prompt action, users see a browser or Client notification explaining the reason for enforcement. These notifications let you explain each policy enforcement rule to users at the moment access is blocked or prompted. This improves user knowledge and awareness, reduces friction during security actions, and aligns security enforcement with broader business communication goals. Helping reduce confusion and support requests. For more information on User Notifications, see [Creating User Notification Templates](/v1/docs/creating-user-notification-templates).

To create a fully customized User Notification Template, you can upload an HTML file that defines the notification content and styling of the browser page.

## Creating Custom User Notifications

Create an HTML file for your user notification and upload it to the Cato Management Application.

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(209).png)

**To create custom User Notification Templates:**

1. From the navigation menu, select **Account > User Notifications**.
2. Either:
  - Use an existing template, e.g. Step Up Re Authenticate, and click **Edit**

or
  - Click **New**
3. Choose a **Template Name** and select the **Page Type**.
4. Under **Page Content Mode**, select **Custom Page**.
5. Click **Choose File** and upload an HTML file with your template design.
6. Click **Save**.

## Supported Elements

The following elements are supported in the HTML file.

### HTML Tags

**Structure**

`html`, `head`, `body`, `meta` *(charset/viewport only)*, `title`, `div`, `section`, `header`, `footer`, `main`, `article`, `aside`

**Text**

`h1`–`h6`, `p`, `span`, `br`, `hr`, `strong`, `em`, `u`, `small`, `code`, `pre`, `blockquote`

**Lists**

`ul`, `ol`, `li`

**Tables**

`table`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td`, `colgroup`, `col`

**Media & Links**

`a`, `img`

### Attributes

**Global**

`id`, `class`, `lang`, `title`

**Links**

`href`, `target`, `rel`

**Images**

`src`, `alt`, `width`, `height`

**Tables**

`colspan`, `rowspan`, `scope`

**Styling**

`style` *(only when it passes the strict CSS property allowlist)*

### Action Controls

Block/Prompt pages can contain theses actions:

- **Proceed**: On a prompt page only, this lets the end user proceed to the website
- **Report a wrong category:** The end user can report the catagory of the website that is attempted to be accessed as incorrect

This can be added to the HTML file with the `data-cato-slot` action hook. For example:

- `&lt;div data-cato-slot="proceed"&gt;&lt;/div&gt;`
- `&lt;div data-cato-slot="report-wrong-category"&gt;&lt;/div&gt;`

### URL Policy

**Links (**`a[href]`**)**

- Only `https://` URLs are allowed.
  - Outbound links are automatically forced to:

`target="_blank"`
  - `rel="noopener noreferrer"&gt;`
- For example, implement a “Go to IT Portal” button, as a CSS-styled `&lt;a&gt;` element, not a `&lt;button&gt;`

**Images (**`img[src]` **)**

- Only embedded data URIs are supported. For example, `data:image/png;base64,...`, `data:image/jpeg;base64,...`, `data:image/gif;base64,...`
- External image URLs are not supported

### Dynamic Parameters

Dynamic parameters are updated based on the action taken by the user:

`{blockedURL}` , `{reason}` , `{user}` , `{host IP}` , `{server IP}` , `{client IP}` , `{categories}`

### Validating the HTML File

When you upload an HTML file it is validated to ensure it does not contain any unsupported elements. If the validation fails, the errors are displayed

![](https://cdn.document360.io/81d0367c-2b69-4ba8-b412-1c8f46ce677e/Images/Documentation/image(210).png)
