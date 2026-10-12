# Your inbox, day to day

The small things that make the inbox calm to use.

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

## Reviewed, Archive and Bin

On a computer the three small buttons on a row show when you point at the email. Press one and the email stays in the list, slightly grey and pulsing, for five seconds while a thin line runs across it. Press **Undo** in the bar at the bottom to bring it back. On a phone, swipe a row. See [Undo](UNDO.md).

## Ticking several emails

Tick one email's box, then hold **Shift** and tick another one a few emails up or down, and every email between them is ticked too. Shift and untick clears the range the same way. Ticking without Shift works one email at a time. Once two or more are ticked, a bar appears with **Reviewed**, **Archive** and **Bin** for all of them at once (one Undo covers them all). **Clear selection** starts again.

## A new install starts empty

On a real Enveliq server, a person with no mailbox connected sees an empty inbox. There are no sample emails or sample accounts. A short banner says the inbox is empty because no mailbox is connected yet, and the list links to the setup guide. The sample emails still appear in the hosted demo and in the no-server preview, where they are made up on purpose.

## The version number

The Enveliq version is a small grey line at the bottom of the left panel, above **Terms**, **Privacy** and **Security**. It is hidden when the panel is collapsed. Administrators also see a small card above it when a newer version has been published. See [Knowing when a new version is out](UPDATES.md).

## Staying signed in

Normally Enveliq signs you out after 30 minutes without use. If an administrator has turned on **Keep me signed in on this device** (Administration, Sign-in rules, from 1 to 14 days), the sign-in page shows a tick-box for it. Tick it only on a device that is yours. It needs Enveliq to unlock itself from a key file (see [Unlock by itself after a restart](VAULT_KEY.md)); restarting Enveliq still signs everyone out.

## Calm mode

For days when numbers make everything feel urgent. At the bottom of the menu, just above **Agent**, press **Calm mode** to turn it on (press it again to turn it off). It is remembered in that browser, and each person chooses for themselves.

When it is on:

- The numbers beside My inbox, Needs action, Tasks and Attachments are hidden, and so are the counts in the greeting ("2 emails to look at, 2 need you") and the AI queue bar.
- The greeting says "Take it one at a time. Nothing here is urgent."
- The Today card is headed **Start here** and shows one task. The rest wait under **Later**, without a count.
- "Waiting since Thu" becomes "When you can", and the amber needs-action dots turn grey.
- Movement on the page is turned off.

Nothing is hidden for good: every email, task and list is still there, and **Needs action** still works.
