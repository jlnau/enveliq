# Your inbox, day to day

The small things that make the inbox calm to use.

## Buttons inside an email

The Tag, Task, Reply and other email actions have a fine oval outline so they are easier to recognise as buttons. The outline is drawn inside each existing button, without changing its size or spacing. The same design works in light and dark mode.

## Opening the menu on a phone

Swipe inward from the left edge of the screen to open the mailbox menu. Swipe left across the open menu to close it. The browser Back button, including the phone's system Back button, closes the open menu rather than leaving the current page. The menu button and the dimmed area outside the menu still work as before.

## Action confirmations## Attachment summaries in the reading pane

Expanding an attachment's AI summary keeps the current email selected in the reading pane. The summary arrow only opens or closes that attachment's details; it does not close the email. This also works when the attachment is collapsed again.



Enveliq uses the same small feedback message for routine actions, including tagging and syncing. A successful action shows a short confirmation, while a failure explains what went wrong. Sending and replying continue to use the existing Undo Send countdown, and archive, Reviewed and Bin keep their existing Undo bars; these are never replaced by a success message. When one of those email action countdowns finishes in the background, it updates only that email. If you have opened a different email or its original content meanwhile, that view stays open and unchanged.

In **View → Feedback**, **Show action confirmations** starts on. Turn it off if you prefer not to see routine success popups. Important errors, Undo buttons and sending countdowns always remain visible. The preference is saved for your own account in the encrypted vault and applies on all your devices.

## Live updates between devices

While Enveliq is open, Server-Sent Events tell each signed-in browser when mail metadata changes. New emails, tags, reviewed and archived states, deleted messages, mailbox folder changes and opened indicators refresh automatically without reloading the page. The events contain no email contents or subjects. Enveliq re-reads only your own mailbox data with the existing authentication and permissions. The connection reconnects automatically, and a one-minute check plus visibility and network-return checks recover from dropped connections. An open email and the inbox scroll location stay in place where the email remains available.

## Returning to the same place

Enveliq remembers where you were in the inbox and the email you had selected. When you return from reading a message, or refresh the page, it restores the list position on that device. The selected email is remembered for your own account in the encrypted vault, so your other devices can find the same email. Scroll positions stay on the device because phone and desktop screens have different sizes. If the email is no longer available, the inbox still works normally.

## When new mail appears

If the mailbox uses AI summaries, a new email is not shown in your inbox until its summary, and the summaries of any attached files, are ready. A small bar at the bottom of the page shows the AI queue (*1 being written, 2 waiting*). If a summary fails after a few tries, the email is shown anyway with **Could not summarise** and a **Try again** button. [The AI guide](AI_SUMMARIES.md#the-ai-queue) has the details.

## What each email shows

- **Sender, subject and a short summary.** Anything the AI wrote is labelled as such.
- **The date and time** on the right. Under it, a small **paperclip** means the email has attached files. Point at the paperclip (or tap it on a phone) to see how many.
- **A "Be careful" label** when something about the email looks odd. See [the Be careful flag](SCAM_WARNING.md).

### The paperclip

Enveliq never keeps your attachments. It keeps whether an email has files and how many, encrypted, with the rest of that email's record. Once the files have been summarised it also keeps each file's name, size and summary (see below).

- When an email first arrives only its headers have been read, so the paperclip is a careful guess. Its tooltip then says **May have an attachment**, because a few newsletters are built the same way as emails with files.
- When the AI summary is made, Enveliq counts the files exactly (pictures that are part of the text are not counted) and the paperclip becomes certain, for example **Has 2 attachments**.
- Emails fetched before this existed show a paperclip once they are fetched again or summarised.
- The **Attachments** entry in the left menu, its number and its filter use the same count.

### Attached files, summarised

Open an email and its files are listed under the summary, above the task: one row per file with its name, kind, size and a one-line summary. Press a row to read a longer summary in parts. **View** opens the file itself. Every summary is labelled **Summary written by AI**, and the file itself is not stored.

- A file that could not be summarised says **Not summarised** and, if the AI could not be reached, offers **Try again**.
- An email is never shown with a number of files and nothing beside it. If its files were left alone (the attachment switch is off, the email is too large) each file is listed as **Not summarised** with the reason. If Enveliq has not read the files at all, the email says so and offers **Read the files again**. The server log has one line saying why (`files of … not read`).
- PDF (with text), Word (.docx), text and CSV files are read, however long. Scans and pictures are not read yet.
- Administrators control this under Administration, AI model. See [the AI guide](AI_SUMMARIES.md#summaries-of-attached-files) for the limits and the cloud-service rule.
- Attachment file rows and summaries use names that do not get mistaken for advertisements, so they remain visible with common ad blockers enabled.

## Reviewed, Archive and Bin

On a computer the three small buttons on a row show when you point at the email. Press one and the email stays in the list, slightly grey and pulsing, for five seconds while a thin line runs across it. Press **Undo** in the bar at the bottom to bring it back. On a phone, swipe a row. See [Undo](UNDO.md).

## Ticking several emails

Tick one email's box, then hold **Shift** and tick another one a few emails up or down, and every email between them is ticked too. Shift and untick clears the range the same way. Ticking without Shift works one email at a time. Once two or more are ticked, a bar appears with **Reviewed**, **Archive** and **Bin** for all of them at once (one Undo covers them all). **Clear selection** starts again.

## A new install starts empty

On a real Enveliq server, a person with no mailbox connected sees an empty inbox. There are no sample emails or sample accounts. A short banner says the inbox is empty because no mailbox is connected yet, and the list links to the setup guide. The sample emails still appear in the hosted demo and in the no-server preview, where they are made up on purpose.

## The picture behind the top of the page

On a computer or tablet, the top of every page sits on a quiet picture: a night sky with a moon and soft hills in dark mode, and a morning sky with a low sun and pale hills in light mode. The heading, the search box and the first row of cards (Start here, Also important today) sit on it, and the cards are slightly see-through so the picture shows faintly behind them. The picture fades out above the email list, and it scrolls away with the page. On a phone there is no picture, so nothing takes up room.

The pictures are drawn in code and held inside the page, so Enveliq downloads nothing extra to show them. In light mode the logo sits straight on the sidebar colour, with no white box behind it. To change the pictures, edit `scripts/make_backdrops.mjs`, run it, and paste its output over the `--backdrop` lines in `prototype/index.html`.

## Picking several emails on a phone

On a phone, press and hold an email for about half a second. A box appears on the left of every email (the emails move to the right to make room), and the email you held is ticked. Tap any other email to tick or untick it; tapping does not open it while you are picking. The count, **Clear** and the **Reviewed**, **Archive** and **Bin** buttons appear under the "Recent emails" title. These work like the buttons on a single email, so **Undo** is still offered. **Clear** leaves picking, and so does unticking the last email. A quick tap still opens an email, and swiping still works when you are not picking. Wide screens keep the tick boxes they always had. `scripts/check_phone_select.mjs` checks this.

## Clearing the Undo bar on a phone

If the Undo bar at the bottom is covering an email, swipe it left or right and it goes. The action goes through straight away, so there is no Undo after that. A short nudge springs it back. The same swipe hides the **AI queue** bar. That only hides the bar: the summaries keep being written, and the bar comes back the next time the AI starts work. (`scripts/check_phone_select.mjs` checks this.)

## Ticked emails: where the buttons show

When you tick two or more emails on a computer, **Reviewed**, **Archive** and **Bin** appear in the "Recent emails" panel, so you can still see them while **Inbox options** is closed. When Inbox options is open they sit in its bar instead, never in both places.

## The side panel, and opening and closing the lists

- The round arrow that narrows or widens the side panel sits on the panel's edge line. When the panel is narrow the logo is centred in it, and the **More** icon carries its own small arrow inside it (it flips when More is open).
- Narrowing the side panel never changes the user button in the top right: it keeps your picture, name and role. Your picture is also kept between refreshes, so it no longer blinks out while it reloads.
- The **Coming up** panel has an arrow on its right that is always there. It points up when the panel is open and down when it is closed. In Calm mode the **Later** box has the same arrow and starts open. (On a phone these panels already had their own arrow.)

- The account menu (your picture, top right) has a **Customise** button. It closes the menu and opens the panel on the right that changes how the inbox looks.

`scripts/check_rail_and_folds.mjs` checks all of this.

## The version number

The Enveliq version is a small grey line at the bottom of the left panel, above **Terms**, **Privacy** and **Security**. It is hidden when the panel is collapsed. Administrators also see a small card above it when a newer version has been published. See [Knowing when a new version is out](UPDATES.md).

## Staying signed in

Normally Enveliq signs you out after 30 minutes without use. If an administrator has turned on **Keep me signed in on this device** (Administration, Sign-in rules, from 1 to 14 days), the sign-in page shows a tick-box for it. Tick it only on a device that is yours. It needs Enveliq to unlock itself from a key file (see [Unlock by itself after a restart](VAULT_KEY.md)); a sign-in made with the tick also survives a restart of Enveliq (an update or a redeploy), until the days you chose are up. Sign-ins made without the tick end at a restart.

## Finding your way around

The main inbox shows **Needs action**, **Today**, **Packages**, and **Waiting** at the top. These open the corresponding views. The **Today** section shows tasks that need attention; **Coming up** shows the next tasks due later. On a phone, the task sections start folded so you can reach the email list sooner; tap a section heading or its arrow to open it.

The **All emails** switch fetches inbox headers from the last 60 days without a message count limit, across connected mailboxes. Entries from this view are quiet until you choose to generate a summary. It reads headers only and does not store original email bodies or attachments. Larger inboxes may take longer to load on the first request. The Sent, Drafts and other views retain their existing limits.

**Found emails** lists the emails you found with **Search all my mail** and chose to keep. Each stays for 60 days, or until you press **Reviewed**. See [Find any email](FIND_MAIL.md).

The **Recent emails** section lists your mail. **Inbox options** starts closed on computers and phones. Press it to show the mailbox filter, sorting, **All emails**, **Expand all**, and the other available inbox controls; press it again to hide them. On phones, **Recent emails** can also be expanded or collapsed.

The left menu leads to **My inbox**, **Needs action**, **Tasks**, **Shipping**, **Waiting for reply**, and **Attachments**. The **More** section contains other views, including Sent, Reviewed, and Archived where available. Collapsing the desktop menu keeps the icons; the compact Calm mode control remains available.

## Bigger windows for emails and attachments

The window that shows an original email, an attachment, a picture or a PDF now grows with your browser window (up to a sensible size) instead of staying a fixed size, and always stays inside the browser window. On a big monitor you see much more of the email at once. The email stays a readable column in the middle. PDF pages are drawn larger and fit the width of the window; the **−** and **+** buttons zoom from there. Phones are unchanged (full screen).

Web addresses in the text of an email can be clicked, but they never open by themselves: you are first asked where it goes (see "Where does this link go?" in the Be careful guide).

## Getting back to My inbox
- The Sent page uses the same header as the other pages (Back button, title, then a line saying it shows your last 14 days of sent mail). The page keeps room for its scroll bar, so nothing moves sideways when the emails finish loading.
- On every page other than My inbox (Needs action, Tasks, Shipping, Waiting for reply, Attachments, Reviewed, Archived, Sent and so on), a **Back to My inbox** button sits above the page title. The title now shows the name of the page you are on instead of "My inbox".
- Needs action, Attachments, Reviewed and Archived show the same **Recent emails** panel with **Inbox options** as My inbox, so the options fold away in the same way everywhere.
- On **Waiting for reply**, the **Closed** section is folded away until you open it with its arrow, so the page does not look like a long list of open items.
- With **Open full screen**, on a computer the email sits beside the left menu and below the top bar, and **Reviewed**, **Archive** and **Bin** are normal buttons centred along the bottom (they used to be stretched across the screen and partly hidden).

## The top stays in view while you scroll
- On a computer, the bar with the search box, Sync mail, the help button and your name stays at the top of the page when you scroll down a long list. The "Recent emails" bar with **Inbox options** (and the buttons for ticked emails) stays right under it. Only the emails move.
- The title, the four count tiles and the picture behind them scroll away as before, so you get more room for the emails.
- The top bar is never a solid block. It stays see-through the whole time, so the picture behind it always shows. Emails, tiles and titles that scroll up to it fade out softly just below its lower edge (no hard cut-off line), so no text is ever seen through it. The Recent emails bar itself is never faded.
- Phones are unchanged. They already have their own bar at the top of the screen.

## Nothing in the wrong place when the page loads

While the page starts up, only the background shows. Nothing else is drawn (no menu, no boxes, no buttons) until everything is in its right place, and then the whole page fades in together. This is why a quick refresh, or several in a row, no longer shows parts of the page jumping into position. If loading takes more than a moment, a calm "Getting your inbox ready…" line appears, and after a few seconds the page is shown anyway so it can never stay blank. People who prefer less motion get no fade.

## Even gaps on the main screen
- On a computer, the boxes on the main screen (the four count tiles, Today, Coming up, the cards for deliveries, subscriptions, trips, replies and messages, and the Recent emails bar) are all separated by the same small gap, so no space is wasted between them.

## Light mode and pictures
- In light mode, the Shipping, Subscriptions, Trips and Waiting for reply cards (on their own pages and on the home page) and the New email button now use light colours. They used to keep their dark colours.
- The Tasks page uses the full width, like the other pages.
- The pictures in the guides, the README and the website were retaken in the current design, in dark and light (see `website/README.md`).

## Calm mode

Calm mode is on by default in a browser that has never chosen a mode. Each browser remembers the choice, and you can turn Calm mode off from the bottom of the left menu or from the account menu.

When Calm mode is on:

- The extra counts and distracting dashboard summary cards are hidden, and the header uses a gentler message on desktop.
- **Start here** highlights one task; **Also important today** and **Later** keep other tasks available without putting them all in front of you at once.
- On a phone, the decorative Calm mode banner is omitted. **Start here**, **Also important today**, and **Later** all start collapsed, and you can open each when needed.
- On a computer screen, **Start here** is a short, compact card with smaller **Open email**, **Snooze** and **Mark done** buttons. When it is the only panel it uses the full width. When there is also something in **Also important today**, that shows as a slim strip along the bottom of the same card instead of a separate panel beside it. This is only a change to how it looks; phones keep their own layout.
- The rest of the inbox, its mail, and its tasks remain accessible. Calm mode does not change, delete, or hide any underlying mailbox records.

You can switch back to the regular dashboard at any time. Turning Calm mode off does not remove tasks or reset your data.

## Light and dark themes

Open the account menu at the top right to choose **Dark**, **Light**, or **System**. System follows the device setting. Theme and Calm mode are independent choices.

## Profile pictures

Under **Settings, Profile**, you can choose your own picture. New uploads of transparent PNG images preserve the clear areas, so the panel colour shows through around and inside a logo. An image previously uploaded before this was fixed may have been saved with a white background; uploading the **original transparent PNG again** is the most reliable way to restore transparency. The **Remove white background** action in Settings, Profile is an optional repair for an older saved image, not something a correctly uploaded transparent image needs.

## On a phone, emails open full screen

On a phone, whichever layout is chosen in the View panel (List, Reading pane on the right, Reading pane below, One screen at a time, Cards), tapping an email opens it on its own, filling the whole screen. There is one **✕ Close** button at the top left. To read the next email, close this one and tap the next in the list; there are no Next and Previous buttons. **Reviewed**, **Archive** and **Bin** stay along the bottom. When you press **Reviewed**, **Archive** or **Bin**, the email closes at once and you are back in the list. The usual **Undo** bar still shows at the bottom for five seconds, so you can bring the email back. The layout you chose is not changed: on a bigger screen (or if you turn a tablet sideways) it comes back. Browser check: `scripts/check_phone_reader.mjs`.

## Adding your own task to an email

Every email has a **Task** button beside Reply and Snooze (and in the full screen email on a phone), even when the AI found nothing to do. Press it, write what you want to remember (for example "ring the plumber when I get home"), choose a day (today unless you pick another) and press **Add task**. Enter does the same, and Escape or **Cancel** closes the box without adding anything. The task shows under the email as **Your task** and on the Tasks page with the AI's tasks. An email can have several tasks. Unlike a task the AI made, yours does **not** finish by itself when you reply to, archive or bin the email: only you finish it (tick it on the Tasks page). The email is kept in Enveliq while one of your own tasks on it is open, like any email with an open task. Your task text is stored only in your own encrypted task record. Server: `POST /api/v1/me/tasks` (`backend/mail/task_routes.py`, `TaskBook.add` in `backend/mail/tasks.py`). Checks: `tests/test_tasks.py` and `scripts/check_task_add.mjs`.

## Adding a parcel by hand (Shipping)

At the top of the Shipping page, **Add a parcel** opens a small form for a parcel that did not start from an email: **Who is it from?** (required), **Tracking number** (if you have one) and **Where is it up to?** (Waiting to be shipped, Shipped, Out for delivery or Delivered). The parcel appears as a card like the others, marked "Waiting to be shipped" and so on. Because no emails follow it, you move it along yourself with the **Where is it up to?** list on its card, and **Remove** takes it off the list (nothing is remembered about it afterwards). A parcel you mark Delivered is not asked "did it arrive?". A tracking number must be 8 to 40 letters or digits, and the same number cannot be added twice. There is no carrier box, so no Track button is offered for these cards; the number is shown with a **Copy number** button. Server: `POST /api/v1/me/shipping`, `PUT /api/v1/me/shipping/<id>/status` and the `remove` action (`backend/mail/shipping.py`, `shipping_routes.py`). Checks: `tests/test_shipping.py` and `scripts/check_shipping.mjs`.

## The phone's top bar

On a phone the top bar holds only the menu button, the logo, the bell, Search and Sync, so all of them are always on the screen. **New email** (the pencil) and **News feeds** are in the menu instead: open it with the three lines at the top left. New email is at the top of the menu, and News feeds sits above Settings with its number badge. An email that is open full screen never makes the page wider than the screen, so the page no longer looks zoomed in: long words and addresses wrap, the browser is told not to enlarge text by itself, and a double tap does not zoom (pinching still works).

## Your first view, and remembering it

When someone signs in for the first time, the inbox starts with the **reading panel on the right**: the list on the left and the open email beside it. Any change you make under **View** (layout, spacing, width, open rows, preview) is saved for you on the server, encrypted, and used on every device you sign in from. It survives restarts and updates, and nobody else's choice ever changes yours. **Reset** in the View panel goes back to the first view. The right and bottom reading panels begin with nothing selected for a person who has never opened an email. After someone selects an email, that choice is remembered through refreshes and across their signed-in devices if the message is still available. On a phone every email still opens full screen.

## New emails glow until you open them

An email you have not opened yet has a soft blue glow. Opening it, from the list or from a notification link, clears the glow, and that is remembered on all your devices. It is only a mark inside Enveliq: nothing changes in your mail provider.

## Which mailbox an email came from

When more than one of your mailboxes is connected, each email in the list carries a small coloured label with the mailbox's name (for example "Proton test" or "Gmail test"), and the open email has a **Mailbox** line in its details with the same label. Each mailbox keeps its own colour. Hold the pointer over a label (or long-press it) to see the provider and the address. With only one mailbox there is no label, so a single mailbox stays uncluttered. On a phone the label shows in the list and in the full screen email. Browser check: `scripts/check_mailbox_label.mjs`.

## Renaming a mailbox

The name you gave a mailbox when you connected it (for example "Proton Test") can be changed at any time. Open **Mailboxes**, press **Rename** on that mailbox, type the new name and press **Save name**. **Cancel** keeps the old one. The new name shows straight away on the Mailboxes page, in the mailbox label on each email, and in the mailbox lists. Only the name changes: your mail, summaries, tasks, tags and settings stay as they are, and you do not have to connect again. Only the person who connected a mailbox can rename it.

### Choosing the label's colour

On the same Mailboxes card, the **Label colour** drop-down picks the colour of that mailbox's label: Blue, Green, Orange, Pink, Red, Teal, Purple or Lime. **Automatic** (the start) lets Enveliq choose one for you. The choice is saved at once and shows in the mail list and in the open email the next time the inbox loads. It is only a colour; nothing else about the mailbox changes.

## Searching your tasks

The Tasks page has a **Search your tasks** box under its title. Type part of a task's words (its title, its details or who it is from; capital letters do not matter) and the page lists only the tasks that have them, open ones under **To do** and finished ones under **Done**, with a line saying how many match. Clear the box to get your usual view back. It works in the Focus, List and Calendar views. Browser check: `scripts/check_task_search.mjs`.

## Forms on a phone

A form or pop-up that asks you to type something (Add a parcel, Task, News feeds, Tags, and the ones to come) opens full screen on a phone. The title and **✕ Close** stay fixed at the top, the buttons (Add parcel, Add task) stay fixed at the bottom, and only the middle scrolls, so you never have to hunt for them. On a computer they are small boxes as before. `scripts/check_shipping.mjs` and `scripts/check_task_add.mjs` check this.

## The Back button

Moving to another section (Sent, Reviewed, Tasks and so on) adds a step to the browser's history, so the **Back** button of the browser, or a phone's back gesture, returns to the section you were in before, inside Enveliq, instead of leaving it. **Forward** works too. Back also closes Settings and Administration if they are open. Moving between the tabs of Settings does not add steps, so one Back leaves Settings. On a computer, opening or closing an email does not add steps. **On a phone, an email that is open full screen has its own step**: Back (or the back gesture) closes the email and shows the list again, instead of leaving Enveliq. Closing it with the **✕ Close** button, or with Reviewed, Archive or Bin, leaves no extra step behind. `scripts/check_back_button.mjs` checks this.

## Reading pane on the right (computer)

Choose **Reading pane on the right** in the View panel (the tab on the right edge). The open email fills the whole right side of the screen, from just under the search bar to the bottom of the window, and **Reviewed**, **Archive** and **Bin** stay along its bottom edge. The left column holds the page title, the four counts in one slim row, **Today** and **Coming up** side by side, the **Recent emails** bar and the list. **Today** shows its first two things; **Coming up** shows the soonest two, in a box the same height and shade (neither box has the round tick buttons in this view; use the Tasks page to mark things done), and **Coming up · N more** is a link to the Tasks page (in the other layouts it still folds open and closed). In Calm mode this view has no Calm mode bar on top and no icon in Start here, the cards are shorter, and Also important today sits under Later on the right. The left column scrolls by itself; the page does not. This applies to every page that lists emails. On a phone, or a window narrower than 900 pixels, the email appears under the list as before. The other layouts are unchanged. Browser check: `scripts/check_split_reading.mjs`.
