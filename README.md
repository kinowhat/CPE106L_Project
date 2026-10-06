# Circles

Circles is a Django web app for coordinating schedules with friends. Each person keeps a personal calendar, joins one or more **circles** (groups), and the app shows when everyone is free, lets members propose events as polls, and adds approved events to members' calendars.

Built for CPE106L.

## Features

**Calendar**
- Weekly calendar view with an hour-by-hour grid and a schedule list
- Events that run past midnight are split across day columns
- Add, edit and delete events, including recurring events (pick weekdays and a number of weeks)
- Quick Add Event modal on the home page
- Import events from a Google Calendar export (`.ics` or the `.zip` Google provides). Repeating events are expanded up to one year ahead, duplicates are skipped, and imports are capped at 3,000 events
- Export your calendar as `.ics`
- Per-user timezone setting (defaults to `Asia/Manila`)

**Circles**
- Create a circle and invite others with a shareable invite link or code
- Availability heatmap showing how many members are free in each hour
- "Best time to meet this week" suggestion. It skips slots that have already started and ranks late-night hours lower. One click pre-fills the proposal form with that slot
- Click any time block to see who is busy (other members' private events are shown only as "Busy")
- Export a circle's approved events as `.ics`
- Circle stats: open proposals, events this month, member engagement

**Polls and voting**
- Any member can propose an event as a poll. Choose how it resolves:

  | Poll type | Passes when | Who gets the event |
  |---|---|---|
  | Majority (All Members) | More than 50% of all members vote Yes | Every member |
  | Majority (Voters Only) *(default)* | More than 50% of all members vote Yes | Only members who voted Yes |
  | Opt-in (Voters Only) | Everyone has voted (with at least one Yes), or the organizer finalizes it | Only members who voted Yes |

- Voting happens in place on the circle page (AJAX), with live Yes/No progress bars. The page reloads when a poll resolves
- Opt-in polls have a **Finalize now** button for the proposer or the circle owner
- Time-conflict warnings against your own calendar while proposing and voting
- Owners can add an event directly with **Quick Add**, which skips voting
- Email notifications for new proposals, approvals and new members (console backend in development)

**Home dashboard**
- Sync-to-Hangout: mark yourself "Free Now" for 1 to 4 hours and see how many circle members are free right now. Your circles are emailed when you go free
- "Needs your vote" list with one-click Yes/No
- Create Poll shortcut: pick a circle and jump to its proposal form
- Notifications, personal poll stats, top circles and upcoming events

**Owner tools**
- Edit or delete the circle
- Transfer ownership to another member
- Remove a member (their votes on open polls are dropped)
- Regenerate the invite code (the old link stops working)

**Accounts**
- Register, log in and log out
- Profile page with avatar upload and timezone
- Account settings to edit username and email, or delete the account (password required)

## Tech stack

- Python and Django 6.1
- SQLite
- Tailwind CSS 4 and DaisyUI 5 (compiled with the Tailwind CLI)
- [`icalendar`](https://pypi.org/project/icalendar/) for `.ics` import and export
- [`recurring-ical-events`](https://pypi.org/project/recurring-ical-events/) to expand repeating events on import
- Pillow for avatar uploads

## Getting started

### Prerequisites
- Python 3.12 or newer
- Node.js 20 or newer (the Tailwind CLI requires it)

### 1. Clone and install Python dependencies

```bash
git clone https://github.com/kinowhat/CPE106L_Project.git
cd CPE106L_Project

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install django icalendar recurring-ical-events pillow
```

### 2. Install frontend dependencies and build the CSS

```bash
npm install
npm run build
```

Use `npm run dev` instead to rebuild the CSS automatically while you edit templates. Tailwind only includes classes it finds in `CirclesApp/templates`, so rebuild whenever you use a new utility class.

### 3. Set up the database and run

```bash
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

Open http://127.0.0.1:8000/ and register an account.

## Project structure

```
Circles/                    Django project (settings, root URLs, WSGI/ASGI)
CirclesApp/
  models.py                 Circle, Membership, Event, ProposalVote, UserProfile
  views.py                  All page and action views
  forms.py                  Registration, events, proposals, polls, profile, account forms
  urls.py                   App routes
  polls.py                  Poll resolution rules (who passes, who gets the event)
  conflicts.py              Event overlap detection
  context_processors.py     Notification data for templates
  middleware.py             Activates each user's timezone
  templatetags/circle_extras.py   Calendar and heatmap template filters
  templates/                base.html, accounts/, circles_app/, confirmation pages
  static/styles/input.css   Tailwind + DaisyUI theme and form styles
  static/styles/output.css  Compiled CSS (generated by npm run build)
  migrations/
manage.py
package.json
```

## Data model

| Model | Purpose |
|---|---|
| `Circle` | Name, tag, creation date and a unique invite code |
| `Membership` | Links a user to a circle with a role (`owner` or `member`) |
| `Event` | A calendar entry. `status` is `personal`, `pending` (a poll awaiting votes) or `approved` (shared with a circle). Polls also store a `poll_type` (`majority_all`, `majority_voters` or `optin`) |
| `ProposalVote` | One Yes/No vote per user per poll |
| `UserProfile` | Timezone, avatar and `free_until` for Free Now status |

Circle ownership is stored as `Membership.role == 'owner'`. A pending poll has no `user`. When it resolves, the poll row becomes one member's calendar event (the proposer's if they qualify) and every other recipient gets a copy.

## Key routes

| Path | Description |
|---|---|
| `/` | Home dashboard |
| `/calendar/` | Personal calendar (POST adds events) |
| `/event/<id>/edit/`, `/event/<id>/delete/` | Edit or delete one of your events |
| `/calendar/import/`, `/calendar/export/` | `.ics` / `.zip` import and `.ics` export |
| `/create_circle/` | Create a circle |
| `/find_circle/` | Look up a circle by invite code (POST) |
| `/join/<code>/` | Join a circle via invite link |
| `/circles/<id>/` | Circle detail: polls, availability, members |
| `/circles/<id>/timeblock/` | Who is busy in a given hour |
| `/circles/<id>/propose/` | Propose an event (poll) |
| `/circles/<id>/quick_approve/` | Add an event for everyone, no vote (owner only) |
| `/circles/<id>/export/` | Export the circle's approved events as `.ics` |
| `/circles/<id>/edit/`, `/delete/`, `/leave/` | Manage or leave a circle |
| `/proposals/<id>/vote/` | Vote on a poll (POST, also used via AJAX) |
| `/proposals/<id>/finalize/` | Finalize an opt-in poll (proposer or owner, POST) |
| `/conflicts/check/` | JSON conflict check used by the proposal form |
| `/free/toggle/` | Toggle Free Now status (POST) |
| `/circles/<id>/members/<user_id>/transfer/` | Transfer ownership (owner only, POST) |
| `/circles/<id>/members/<user_id>/remove/` | Remove a member (owner only, POST) |
| `/circles/<id>/invite/regenerate/` | New invite code (owner only, POST) |
| `/settings/timezone/` | Profile: timezone and avatar |
| `/account_settings` | Edit or delete account |
| `/admin/` | Django admin (Circle, Membership and Event are registered) |

## Notes

- This project is configured for local development: `DEBUG = True`, an insecure `SECRET_KEY` and empty `ALLOWED_HOSTS`. Change these before deploying anywhere public.
- Emails are printed to the terminal (`EmailBackend` is set to the console backend). Configure a real email backend to send them.
- Uploaded avatars are stored in `media/`, which is git-ignored. Django serves them only when `DEBUG` is on.
- `db.sqlite3` is git-ignored, so each developer runs `migrate` to create their own database.
- Times are stored in UTC and shown in each user's own timezone.
- Automated tests have not been written yet (`CirclesApp/tests.py` is a stub).

## License

No license has been specified for this project yet.
