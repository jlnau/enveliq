# Calendar invitations

When an email carries a calendar invitation (an `.ics` file, or the invitation Google Calendar, Outlook and Apple Calendar put inside the email), Enveliq shows a card on the open email, on the website and in the Android app. The card has **Accept**, **Maybe**, **Decline** and **Propose new time**.

## What the card shows

The title, the day and time in your own time zone, the place, who it is from, and how many people were invited. If the invitation repeats, the card says that your answer covers the whole series. The card appears only on emails that have files, and only when one of them is a real invitation.

A cancelled meeting says so and offers **Remove from my calendar** if you had accepted it. A plain calendar event with nobody to answer (no organiser) offers **Add to my calendar** instead.

## Answering

- **Accept, Maybe and Decline** send the organiser the standard calendar reply by email. It carries only your own status, never the other people's. It comes from the address the invitation was sent to, when this mailbox can send from it; otherwise from the usual reply address. It uses the same limits and the same five-second **Undo** as other sent email.
- **Propose new time** sends the organiser a normal email in plain words with the day and time you pick and an optional note. Calendar apps do not all understand a counter proposal, so it is not sent as one. Your calendar is not changed.
- The reply goes to the **organiser named in the invitation**, not to the sender. If the organiser is on a different domain from the sender, the card shows a warning and the buttons stay off until you tick **Send my answer to the organiser anyway**. This is the usual sign of a forged invitation.

## Your calendar

When you accept (or say Maybe), the meeting is added to the calendar connected under **Settings, Calendar & to-do**: Google Calendar if it is connected (in the calendar you chose there), otherwise a CalDAV calendar. Maybe is marked tentative. Declining takes the meeting out again.

- Only events Enveliq made itself are ever changed. Each is named from the invitation's own id, so answering twice updates the same event.
- If Google Calendar was connected with **Make a new calendar called "Enveliq tasks"**, meetings land in that calendar. To have them in your main calendar, choose **Use a calendar I already have** (see [Calendar](CALENDAR.md)).
- Accepted meetings stay in your calendar if you later disconnect it; disconnecting removes only Enveliq's task events.
- With no calendar connected, the answer is still sent and the card says nothing was added.
- If the calendar refuses, your answer is still sent, and the card says why the meeting was not added.
- With **Undo send** on, the calendar is changed when the answer actually goes, not before. Undo takes back both.

## Reading the file

Attached `.ics` files are now readable: **View** shows the event in plain words, and the AI summary of the email and its files can use them. The dates are read by ordinary code, not by the AI.

## What is kept

Nothing about the meeting is stored: not the title, place, people or time. The server reads the invitation from the original email each time the card is opened. The only thing kept, in the encrypted vault and per person, is your answer (Accepted, Maybe, Declined, Added, or that you suggested a new time), when you gave it, and which calendar it went to, so the card can say so after a reload. It is forgotten after 180 days.

## Limits

- Only the first event in a calendar file is read. Files over 1 MB are ignored.
- A single changed date in a repeating series (an exception) is treated as its own meeting.
- Links in the invitation are not shown as links. Open the email itself to join a call.
- The Android app uses the same server, so the card, the answers and the calendar behave the same way. The calendar itself is connected on the website.
