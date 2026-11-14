# Tasks in a calendar or a Home Assistant To-do list

Open **Settings, Calendar & to-do**. There are three optional ways to see your tasks somewhere else. All of them follow the task: moved when you move it, and removed or ticked off when the task is done, removed, replied to, or its email is dealt with (Reviewed, Archive, Bin, or gone from the inbox).

## 1. Calendar link (any calendar app)

Press **Create my calendar link**. Enveliq makes a long private address ending in `.ics` and shows it once. Each open task appears as an all-day event on its due date. A task that ends disappears from the link.

| App | How |
| --- | --- |
| Google Calendar | calendar.google.com on a computer: Other calendars (+), From URL, paste, Add calendar. |
| Apple Calendar | File, New Calendar Subscription, paste. Set Auto-refresh to Every hour. |
| Outlook | Add calendar, Subscribe from web, paste. |
| Thunderbird | New Calendar, On the Network, paste, Format iCalendar (ICS). |

**How quickly changes show up is up to the calendar app, not Enveliq.** Google refreshes subscribed calendars roughly once a day and Outlook about every three hours, so a finished task can stay there for hours. Apple Calendar and Thunderbird can refresh hourly. If you need a task to leave the calendar at once, use Google Calendar (instant) or CalDAV (below).

**Google and Outlook fetch the link from the internet**, so Enveliq needs a public `https://` address (see [ACCESS.md](ACCESS.md)). If you only reach Enveliq at home, those two cannot read the link; Apple Calendar, Thunderbird and CalDAV still work on your own network.

The link is the only thing that opens without signing in, so treat it like a password. It is stored only as a hash, shown once, and **Make a new link** or **Turn the link off** stops the old one working immediately. Switch off *Show task titles* if other people can see your calendar: events then say only "Enveliq task". Nothing from the email itself is ever in the feed.

## 2. Google Calendar, instantly

The link above makes Google check only about once a day. For instant changes Enveliq can write to Google Calendar itself. It makes one calendar called **Enveliq tasks** in your Google account and adds, moves and deletes the events in it. It asks Google only for the narrow permission "see, create, change and delete events on calendars Enveliq made", so it cannot see or touch the rest of your Google account.

When you press **Connect Google Calendar** you choose between two things:

* **Make a new calendar called "Enveliq tasks"** (the default). The narrow permission above. Enveliq can only see and change that one calendar.
* **Use a calendar I already have.** Google asks for a wider permission: Enveliq can see and change events on all your Google calendars and list them. After you agree, Enveliq shows your calendars (only ones you can change) and you press **Use this calendar** on one. Enveliq then only adds, moves and removes the events it made itself in that one calendar. It never touches your other events and never deletes the calendar. **Choose a different calendar** changes the pick later. **Disconnect and remove Enveliq's events** removes only Enveliq's events and cancels the permission.

Google makes every app register first. An administrator does the set-up below **once**, in their own free Google Cloud account. It takes about 10 minutes and costs nothing. You will end up with two things, a **Client ID** and a **Client secret**, to paste into Enveliq. After that, each person connects with one button.

You need: the Enveliq address you use in your browser (it starts with `https://`), a Google account, and two browser tabs: one for Enveliq and one for Google. Below, `https://enveliq.example.com` stands for your own address.

Do the steps in order. Each step is one small action. Where it says **Check**, make sure you see what it says before you go on.

### Step 1. Make a Google Cloud project

1. In a new tab open <https://console.cloud.google.com/projectcreate> and sign in with your Google account.
2. If a box asks you to agree to the terms, tick it and press **Agree and continue**.
3. Click the **Project name** box and type `Enveliq`.
4. Press the blue **Create** button.
5. Wait about 10 seconds.
6. **Check:** at the top of the page, right of the words **Google Cloud**, a button shows the project name. It must say **Enveliq**. If not, click it and click the **Enveliq** row.

### Step 2. Switch on the Calendar API

1. Open <https://console.cloud.google.com/apis/library/calendar-json.googleapis.com>.
2. Press the blue **Enable** button.
3. **Check:** the page now shows a **Manage** button. (If it showed **Manage** at the start, it was already on.)

### Step 3. Set up the consent screen

This is the page people see when they agree to connect.

1. Open <https://console.cloud.google.com/auth/overview>.
2. Look at the page:
   - **A big blue Get started button?** Press it and do the four screens below. Press **Next** at the bottom of each.
     1. **App information:** click **App name** and type `Enveliq`. Click **User support email** (a drop-down) and choose your email. **Next**.
     2. **Audience:** click the round button beside **External**. **Next**.
     3. **Contact information:** click **Email addresses**, type your email, press Enter. **Next**.
     4. **Finish:** tick **I agree to the Google API Services: User Data Policy**. Press **Continue**, then **Create**.
   - **A page called OAuth overview with charts?** This is already done. Go on to step 4.

On this page, a dark column on the **left** lists: **Overview, Branding, Audience, Clients, Data access, Verification centre, Settings**. The next steps use those words.

### Step 4. Choose who may connect

1. In the **left** column click **Audience**.
2. **Check:** under **User type** it says **External**. A greyed-out **Make internal** button is normal for a personal Google account; leave it alone. (If it says **Internal**, press **Make external**, then **Confirm**.)
3. Scroll down to the heading **Test users**.
4. Press **Add users**. A panel slides in from the **right**.
5. Click the box in that panel, type your Gmail address and press Enter.
6. Do the same for each family member who will use Enveliq, one at a time.
7. Press the blue **Save** at the bottom of the panel.
8. **Check:** your addresses are listed under **Test users**.

### Step 5. Fill in the Branding page

Google will not let you publish until this is done.

1. In the **left** column click **Branding**.
2. Scroll down to the heading **App domain**.
3. Click **Application home page** and type your Enveliq address, for example `https://enveliq.example.com`.
4. Click **Application privacy policy link** and type the same address.
5. Scroll to the bottom and press the blue **Save**.
6. If a red message under **Authorised domains** asks for your domain, press **Add domain**, type the main part of your address (for `https://enveliq.example.com` that is `example.com`), and press **Save** again.

### Step 6. Publish the app

Without this, Google disconnects everyone every 7 days. Publishing does not make anything public: only people you give the Enveliq address to can use it, and Google does not review a personal app.

1. In the **left** column click **Audience**.
2. Under **Publishing status** it says **Testing**. Press **Publish app**. (If the button is greyed out, do Step 5 first.)
3. In the box that opens press **Confirm**.
4. **Check:** **Publishing status** now says **In production**.

### Step 7. Give Enveliq permission to make its own calendar

1. In the **left** column click **Data access**.
2. Press the blue **Add or remove scopes** button. A big panel slides in from the **right**.
3. Scroll to the **very bottom** of that panel (ignore the long list of scopes). Find **Manually add scopes** and the empty text box under it.
4. Click in the box and paste exactly this:

   ```
   https://www.googleapis.com/auth/calendar.app.created
   ```

5. Press **Add to table**. The scope appears in the table at the top of the panel with a tick.
6. Press **Update** at the bottom of the panel. The panel closes.
7. Scroll to the bottom of the page and press the blue **Save**.
8. **Optional, for "Use a calendar I already have":** repeat steps 2 to 7 and add these two scopes as well (one per line in the box). Without them, that choice fails with "Google did not give every permission asked for":

   ```
   https://www.googleapis.com/auth/calendar.events
   https://www.googleapis.com/auth/calendar.calendarlist.readonly
   ```

   Google lists them under **Your sensitive scopes**. Anyone who connects before this step is done, or who connected earlier, must press **Connect Google Calendar** again.
9. **Check:** under **Your non-sensitive scopes** you see `.../auth/calendar.app.created`, and the **Save** button is greyed out.

### Step 8. Copy the redirect address from Enveliq

1. Switch to your Enveliq tab and sign in.
2. Click **Administration**, then **Reminders**.
3. Scroll down to the heading **Google Calendar**.
4. Find the box **Redirect address**. It is read-only (you cannot type in it), on purpose. It looks like `https://enveliq.example.com/api/v1/sync/google/callback`.
5. Click in the box, press Ctrl+A, then Ctrl+C. Keep this tab open.

If the address starts with `http://` (and is not `localhost`), Google will refuse it. Change `ENVELIQ_PUBLIC_URL` in the compose file, redeploy, and look again (see [ACCESS.md](ACCESS.md)).

### Step 9. Make the Client ID and Client secret

1. Switch back to the Google tab. In the **left** column click **Clients**.
2. Press the blue **Create client** button near the top.
3. Click the **Application type** drop-down and choose **Web application**.
4. Click the **Name** box and type `Enveliq`.
5. Leave **Authorised JavaScript origins** empty.
6. Scroll down to **Authorised redirect URIs** and press **Add URI**.
7. In the box that appears press Ctrl+V to paste the address from Step 8. It must match exactly, with no space and no extra `/` at the end.
8. Leave **Use this client for an AI-powered agent** unticked.
9. Press the blue **Create** button.
10. A box called **OAuth client created** shows a **Client ID** and a **Client secret**, each with a small copy icon. Copy each one into a note on your computer. Google shows the secret in full only this once. (If you lose it, open the client from the **Clients** list, press **Add secret** and use the new one.)

### Step 10. Paste them into Enveliq

1. Switch to the Enveliq tab: **Administration**, **Reminders**, **Google Calendar**.
2. Click the **Client ID** box and paste the Client ID (it ends in `.apps.googleusercontent.com`).
3. Click the **Client secret** box and paste the secret.
4. Make sure **Allow Google Calendar** is ticked.
5. Press the blue **Save Google Calendar** button.
6. **Check:** a message says **Saved**.

### Step 11. Connect (everyone does this, including you)

1. In Enveliq open **Settings**, then **Calendar & to-do**.
2. Find **Google Calendar (instant)**, choose **Make a new calendar** or **Use a calendar I already have**, and press **Connect Google Calendar**. (If you chose an existing calendar, pick it from the list when you come back.)
3. Google opens. Choose your Google account.
4. Google shows **"Google hasn't verified this app"**. This is normal: the app is yours. Press **Advanced**, then **Go to Enveliq (unsafe)**.
5. Press **Continue** to allow it.
6. **Check:** you are back in Enveliq and **Google Calendar (instant)** shows **Working**. In Google Calendar, the left list has a calendar called **Enveliq tasks** with a tick beside it, and your tasks show on their due dates.

**Disconnect and delete the calendar** (in the same place) removes the calendar and cancels the permission.

### If something goes wrong

| What you see | Fix |
| --- | --- |
| Google says **Error 400: redirect_uri_mismatch** | The address in Step 9 is not exactly the one Enveliq shows in Step 8. Copy it again, paste it with no spaces, press **Save** on the client, wait a minute and retry. |
| **Access blocked: Enveliq has not completed the Google verification process** or **Error 403: access_denied** | The person's address is not in **Audience, Test users** (Step 4). Add it and retry. |
| Enveliq says the **Google Calendar API is switched off** | Do Step 2 and wait a minute. Make sure the project picker shows the same project that holds your client. |
| Enveliq says the client ID or secret is wrong | Paste them again with no spaces. The ID ends in `.apps.googleusercontent.com`. If you lost the secret, add a new one on the client in Google (Step 9). |
| It stops working after about a week | The app is still in *Testing*. Do Step 6. Then each person presses **Connect Google Calendar** once more. |
| You cannot find a button | Google renames its menus now and then. The page address links above go to the right place; look for the words in **bold**. |

## 3. Instant calendar (CalDAV)

Works with Nextcloud, Radicale, Baikal, Fastmail and other CalDAV services. Enveliq writes each event itself and deletes it as soon as the task ends, usually within a minute, and moves it when you move the task.

1. Make a calendar just for Enveliq. Enveliq only ever adds and removes its own events (named `enveliq-<id>.ics`).
2. Copy the calendar's address: Nextcloud, Calendar app, the three dots beside the calendar, **Copy private link**.
3. Make an app password if the service offers one.
4. Enter address, user name and password, then **Save and test**.

Passwords are write-only and stored encrypted. Google Calendar has its own connection (above).

## 4. Home Assistant To-do list

1. In Home Assistant add a To-do list (Settings, Devices & services, Add integration, **Local To-do**) and note its name, such as `todo.family`.
2. Profile (bottom left), Security, **Long-lived access tokens**, Create token.
3. Enter the Home Assistant address, the token and the list name in Enveliq, then **Save and test**.

New tasks are added with their due date. Done, replied-to and dealt-with tasks are ticked off; removed tasks are deleted. Ticking an item in Home Assistant finishes the task in Enveliq too. If you delete an item in Home Assistant, Enveliq leaves it deleted.

## Trips in your calendar

If you use Trips (see [Trips](TRIPS.md)), your flights, stays and hire cars go in the same calendar as your tasks, through the calendar link, Google Calendar or CalDAV, whichever you set up. They are not added to a Home Assistant To-do list, which is for tasks.

A flight with a departure time is a timed entry. The times are the clock times written in the email, for the place they are for, because Enveliq does not guess a time zone. A stay covers its nights, and a hire car covers its days. If you turn on **Keep titles private**, each entry says only *Enveliq trip*. Switch **Put my trips in my calendar** off on the Trips page to take them out again.

## Home networks

Enveliq will not call an address on your own network unless an administrator allows it (**Administration, Reminders, Allowed addresses**, or `ENVELIQ_NOTIFY_ALLOWED_HOSTS` in the compose file). This applies to CalDAV and Home Assistant too. See [NOTIFICATIONS.md](NOTIFICATIONS.md).

Syncing runs while Enveliq is unlocked, checks about every 30 seconds after a change and at least every five minutes otherwise, and tries again by itself after a failure.

## Tasks view: Calendar

**Tasks, Calendar** shows the month as a grid with each task on its due date (finished ones struck through). Choose a day to see its tasks underneath, tick them off or move them. The arrows change month and Today returns to this month.

## Emails with a task stay

An email that has an open task is never removed from Enveliq, even if it is older than 14 days or you read or deleted it in another app. It goes only after the task is done or removed.

## Meetings from email invitations

The Google Calendar and CalDAV connections above are also where meetings you **accept** from an email invitation go (see [Calendar invitations](INVITES.md)). Google Calendar is used first when both are connected. These meetings are not tasks: they are not removed when a task ends, and they stay if you disconnect the calendar.
