# Mail rules

A rule tells Enveliq what to do with **new** email from a sender you choose. The most useful one is "archive these": weekly offers, receipts you never need, newsletters you like to keep but not look at.

## Make a rule

- **From an email.** Open an email, press its three-dot button and choose **Mail rules for this sender**. A list opens in the same pop-up (with a **Back** entry) with **Always archive these**, **Always mark these as reviewed**, **Never make tasks from this sender**, **Always apply a tag…** (opens the Tags window, see [Tags](TAGS.md)), **Block sender** and **See all my mail rules**. Choosing **Always archive these** From now on, new email from that sender is archived for you. **Block sender** is the same idea with Junk: new email from that sender goes to your mailbox's Junk folder (see [Junk mail](JUNK_MAIL.md)).
- **From Clean up.** **Always archive new ones** on a mailing list makes the same rule (see [Clean up](CLEAN_UP.md)).
- **For tasks.** Press **No tasks from this sender** on the task card (the small vertical three-dot button beside it opens the same rules list), or choose **Never make tasks from this sender** in the rules list. The rule is saved and the open task for that email is removed. Other open tasks from the same sender stay until you finish or remove them.
- **In Settings.** Open **Settings, Mail rules**. Press **Add a rule** and fill in any of the conditions below (at least one), choose what to do, press **Check** to see how many of your recent emails it would have matched (nothing is changed), then **Add rule**.

The same page lists your rules **in order** and lets you **Edit** a rule, move it with the **up and down arrows**, or remove it with the **×**. Rules made from an email (a folder or a tag) can be moved and removed, but are changed by making them again from an email.

## Conditions

A rule fits an email only when **every** condition you filled in fits. Empty ones are not asked.

- **From:** one address (`news@example.com`) or a whole website with an at sign (`@example.com`).
- **Subject has** and **Subject does not have:** words in the subject.
- **Sent to:** an address in the To or Cc line (so a rule can tell mail sent to a shared address from mail sent only to you).
- **Mailing list:** part of the email's List-Id, which mailing lists and newsletters add.
- **Has a file:** a guess from the email's headers (the same guess the file icon uses).
- **Bigger than (MB):** the size your mailbox reports for the email.

Older emails that Enveliq already held before this version have no recipients, list or size on record, so those three conditions do not match them. New mail has them.

## Order

Rules are tried from the top. The **first rule that fits and does something** is used; the rest are skipped. "Never make tasks" and "Always apply tags" sit beside the others and never stop them. Use the arrows to change the order.

## What a rule does

- **Archive it** moves the email to your mailbox's Archive folder and marks it read, exactly as pressing Archive does. Enveliq keeps a short card for a few days, as it does for anything you archive, so you can still find it.
- **Mark it reviewed** marks the email read and leaves it where it is.
- **Send it to Junk** moves the email to your mailbox's Junk or Spam folder. Nothing is deleted, and you can move it back from there.

- **Star it** sets the mailbox's own Flagged star and leaves the email in the inbox.
- **Snooze it** hides the email from the inbox for the time you choose (1 hour up to 30 days) and brings it back after.
- **Never send to Junk** (a safe sender): nothing happens to the email, and **no rule below it** touches it. Put it above a "send to Junk" rule for a whole website to keep one person safe. It is in an email's Mail rules menu too.

- **Never make tasks** leaves the email exactly where it is. It only stops Enveliq from turning email from that sender (or website, or with those subject words) into a task. The email still arrives, is still summarised and can still be archived by another rule. A sender can have both an archive rule and a never-make-tasks rule. Tasks you add by hand are never blocked, and email from your important people still makes tasks.

- **Always apply tags** puts the tags you chose on new email from that sender, in your own mailbox, as it arrives. It does not move or mark the email, so it works together with an archive rule. There is one such rule per sender: saving it again replaces the tags, and saving it with no tags removes it. You make it in the Tags window of an email (tick **Always apply these tags for this sender**) and can see and remove it in Settings, Mail rules.

## What a rule never does

- It never deletes anything. There is no rule for the Bin.
- It only acts on **new** email as it arrives, unless you press **Run on existing mail**.
- Rules you make for an **important person** do apply to them (you chose the rule on purpose). Only a muted conversation never hides an important person's email.
- It does not read the email's text. It looks only at the sender, subject, who it was sent to, the mailing list, whether it seems to have a file, and its size.
- It works on your own mailboxes only. Other people's rules never affect your mail, and yours never affect theirs.

## Good to know

- Rules work when Enveliq checks your mail. That is every few minutes, and when you press Sync mail.
- If your mail service cannot be reached at that moment, the email just stays in your inbox.
- To stop a rule, remove it. Email that was already archived stays archived.
- Your rules are kept encrypted, are part of **Export my data**, and nobody else can see them, not even an administrator.

## Move to a folder
**Always move new email from this sender into a folder** is made from an email: open the folder box (three-dot menu, **Move to folder…**, or the Folders button) and tick "Always move new email from this sender into this folder", or use **Mail rules for this sender, Always move to a folder…**. The email moves now and later email from that sender is filed in that folder as it arrives. It is listed in Settings, Mail rules, where it can be removed (it cannot be added there, because folder names must match your mailbox exactly). One sender has one such rule; choosing another folder replaces it. It applies to Important people too if you make it for them, and a folder that no longer exists is skipped. A folder takes the email out of the Inbox; for "in both", use an always-apply Tag rule instead.

## Run on existing mail

By default a rule only touches new mail. **Settings, Mail rules, Run on existing mail** tidies the email Enveliq already holds in your inbox. It first **counts** ("12 emails fit a rule: 9 to archive it, 3 to star it") and changes nothing until you confirm. It does at most 500 emails each time, skips emails that are snoozed or kept, and leaves email from a safe sender alone. Your own rules apply even to important people, as they do for new mail. It never deletes anything. It covers only the emails Enveliq already holds, not everything in your mailbox. The same count is behind **Check** on a rule you are making.
