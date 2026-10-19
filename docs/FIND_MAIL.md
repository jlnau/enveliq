# Find any email

Enveliq's lists only hold the emails it is helping you with. **Find any email** lets you search your whole mailbox, every folder, even for mail from years ago, and keep any email you find.

It is on for everyone and needs no setup. An administrator can switch it off for everyone, and you can switch it off for yourself, in **Settings, General, Features**.

## How to use it

1. Type at least two letters in **Search inbox**. A box appears above the list. Press **Search all my mail**.
2. The results open in the main list area, in the same place as ordinary search results (not in a pop-up), and Enveliq asks each of your mail services to search. Each mailbox shows how many it found as it goes. Gmail may take a second. Proton Mail can take about twenty seconds for a very large mailbox. **Cancel search** stops it.
3. Every match is listed with the total, newest first, 25 at a time (**Show more**). Each shows who it is from, the subject, the date, which mailbox and folder it is in, and whether it has files. Spam and Bin are left out. Tick **Include Spam and Bin** to add them.
4. **View original email** opens the whole email to read. Nothing is kept. Close it and you are back at the list.
5. Each result has a tick box on its left. Tick one, or hold **Shift** and tick another to tick everything between, or use **Select all** at the top of the results. Once two or more are ticked, a **Summarise Emails** button appears above the results: it keeps all the ticked emails in **Found emails** and adds them to the AI summary queue (up to 100 at a time), the same queue the Summarise button uses. **Clear** unticks them.
6. **Summarise** on one result keeps that one email in **Found emails** and queues its summary with the other summaries. You are told it will be kept for 60 days, or until you press **Reviewed**.

## Found emails

**Found emails** appears in the left menu once you have kept one, with a count. It lists them like any other list, and each one works the same way: open it, read the summary, reply, make a task.

- Each is kept for **60 days from the day you kept it**, then it leaves the list by itself.
- **Reviewed** removes it from the list. It does not change your mailbox. There is no Archive or Bin here, because a found email may be in Sent or another folder you do not want moved.
- A found email never raises an alert, never counts as unread, and is not summarised unless you pressed **Summarise** (or **Generate summary** later).
- Opening or summarising one reads it from the folder it is really in.

## What you can type

- Words you type are all needed: `canvas visual art` finds emails that have all three.
- Words in "quotes" must appear together, in that order: `"visual art 2"`.
- Commas are ignored.
- At most 200 letters and 12 words.
- Gmail also understands its own words, such as `from:bank`.

Each mail service decides how it matches. Proton Mail, iCloud, Yahoo, Fastmail and most others match any part of a word (`canvas` finds `canvases`). Gmail matches whole words.

## Fast search (optional)

Some mailboxes are slow to search, mostly Proton Mail through Bridge with tens of thousands of emails. **Fast search** keeps a private, locked list of the words in your emails so a search is instant.

It is off. Turn it on, for one mailbox at a time, in **Settings, General, Fast search**. A plain warning appears and you must tick **I understand** before it starts.

- **Searching by itself:** when Fast search is ready on every one of your mailboxes, you no longer need the button. Typing in the search box searches all your mail after a short pause, and the results appear in the list. If you press **Close**, the same words do not search again until you change them. If any mailbox has Fast search off or is still being built, the **Search all my mail** button stays and nothing starts by itself, because a live search of a large mailbox is slow.
- It is recommended for Proton Mail only. Other services already search quickly on their own servers.
- It gets ready in the background, newest mail first, a little at a time. It shows "Getting ready: 62% of your mail". Searching still works while it builds, just more slowly.
- It keeps itself up to date as mail arrives or goes.
- It matches the **start of a word** (`canv` finds `canvas`). A search for a long number goes to the mail service instead.
- **Rebuild** starts it again. **Turn off and delete** removes the list at once.

### What the word list holds

- For each email: which mailbox, folder and message number it is, and the words in its subject, sender, recipients and text. Not attachments.
- It does **not** keep the email text, and it skips numbers longer than 8 digits and any word longer than 30 characters, so card numbers and long codes are not in it.
- It is one file per person, locked with a key made from the vault key. It can only be read while Enveliq is unlocked. Another person, or an administrator, cannot read it or search it.
- It is not in backups or in **Export my data**. After a restore it is built again.
- It is deleted when you turn Fast search off, when the mailbox is removed, and when your account is removed.
- While Enveliq builds or searches it, the text of an email is briefly in the server's memory, as it is when an email is summarised.
- Size: roughly the same as the words in your mail. A very large mailbox can use a few hundred megabytes of the server's memory and disk.

## What stays private

- Your search words go only to your own mail service, over the connection Enveliq already uses. They are not logged, not sent to the AI, and not shown to an administrator. The audit log records only that a search happened.
- The page never chooses what to open. Each result carries a signed reference tied to you and that one search. Someone else's reference, or a made-up one, answers "not found".
- A search remembers only folder and message numbers, in the server's memory, for about 15 minutes. No email text.
- Searching never changes your mailbox and never marks anything read.
- Syncing keeps working while you search.

## Limits

- Four searches run at once on the server and you can start six a minute.
- A mailbox gets about three minutes. If it is not done, the results so far are shown with a note. Use more specific words.
- The newest 5,000 matches can be listed. The total still shows the true number.

## For administrators

The switch **Find any email** is in Administration, Features. Turning it off hides the button and Found emails for everyone, and forgets what was kept. Turning off a person's Fast search deletes their word list. See [SECURITY.md](../SECURITY.md) and [PRIVACY.md](PRIVACY.md).
