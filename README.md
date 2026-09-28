# SNU menu mailer

Emails subscribers a daily English translation of the Seoul National
University cafeteria menu, scraped from <https://snumenu.gerosyab.net>.
Friends sign up (and pick their cafeterias) through a Google Form. Runs
every morning at 7:00 KST as a Windows scheduled task that launches the
script in WSL.

## How it works

1. `snumenu/scrape.py` fetches the menu page for today (Asia/Seoul) — one
   polite request per run — and parses it with BeautifulSoup.
2. `snumenu/translate.py` translates each dish: exact glossary match first,
   then compound names are split on `&`, `*`, `+`, `,`, `OR` and translated
   per component. Parenthetical markers like `(뚝)` get their own glosses.
   Anything still unknown is machine-translated (Google, via deep-translator)
   and saved to `glossary.yaml` as unreviewed.
3. `snumenu/subscribers.py` reads the signup form's response sheet
   (published as CSV) to learn who gets which cafeterias.
4. `snumenu/emailer.py` builds a phone-friendly HTML + plain-text email and
   sends it through Gmail SMTP — one email per distinct cafeteria selection,
   with that group's subscribers in BCC.

If there is no menu (weekend/holiday) or scraping fails, subscribers get
nothing; a short note goes to `MY_EMAIL` instead.

## Setup

```bash
pip install -r requirements.txt
python -m pytest                       # run the tests
python main.py --dry-run               # print today's email, write email.html
python main.py --dry-run --date 2026-09-28
python main.py print                   # just print the translated menu
```

To send for real, put the settings in `.env` (copy `.env.example`) — or
export them as environment variables, which take precedence — and run
`python main.py`:

| Variable | Meaning |
| --- | --- |
| `GMAIL_ADDRESS` | the Gmail account that sends the email |
| `GMAIL_APP_PASSWORD` | an app password for that account (see below) |
| `MY_EMAIL` | where error/empty-day notes go (just you) |

### Creating a Gmail app password

1. Turn on 2-Step Verification for the Gmail account
   (myaccount.google.com → Security).
2. Go to <https://myaccount.google.com/apppasswords>, create a password named
   e.g. "snu-menu", and copy the 16-character string — that's
   `GMAIL_APP_PASSWORD`. Your normal password won't work with SMTP.

### Scheduling (Windows Task Scheduler + WSL)

Cron inside WSL only fires while the WSL VM happens to be running, so the
schedule lives in Windows Task Scheduler, which boots WSL on demand.

1. In WSL, put the credentials in a local env file (gitignored) and make the
   wrapper executable:

   ```bash
   cp .env.example .env && chmod 600 .env   # then edit .env
   chmod +x run.sh
   ```

   `main.py` reads `.env` itself; `run.sh` just runs it and appends the
   output to `menu.log`.

2. In **PowerShell** (no admin needed), register a daily 7:00 task — adjust
   the distro name (`wsl -l` shows it), username, and path if yours differ:

   ```powershell
   $action   = New-ScheduledTaskAction -Execute "wsl.exe" `
               -Argument "-d Ubuntu -u alexguo -- /home/alexguo/menu-snu/run.sh"
   $trigger  = New-ScheduledTaskTrigger -Daily -At 7:00AM
   $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
               -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
   Register-ScheduledTask -TaskName "SNU menu email" -Action $action `
       -Trigger $trigger -Settings $settings
   ```

   `-StartWhenAvailable` catches up a run missed while the PC was asleep.
   The time is Windows local time — this assumes the PC is set to KST.

   Useful afterwards:

   ```powershell
   Start-ScheduledTask -TaskName "SNU menu email"        # test it now
   Unregister-ScheduledTask -TaskName "SNU menu email"   # remove it
   ```

   Caveats: the task runs only while you're logged in to Windows, and the PC
   must be on (or waking) around 7:00. Check `menu.log` if an email doesn't
   arrive.

New glossary entries now simply accumulate in the local `glossary.yaml` —
no commit step needed.

### The signup form

Subscriptions live in a Google Form with two questions, in this order:

1. **Email** — short answer (or turn on the form's "Collect email
   addresses" setting).
2. **Which cafeterias do you want?** — checkboxes, one option per label in
   `config.yaml`'s `cafeterias:` map, written *exactly* the same (labels
   must not contain commas). Leave the question optional, and make it the
   last question on the form.

Then link the form to a response Sheet (Responses tab → Sheets icon), and in
that sheet: File → Share → **Publish to web** → pick the responses tab +
**CSV**, and paste the URL into `subscribers_csv:` in `config.yaml`.

Rules the script applies each run:

- A person's **latest** submission wins — resubmitting the form changes
  their cafeterias, and resubmitting with nothing checked unsubscribes them.
- Everyone with the same cafeteria selection shares one email, BCC'd, so
  subscribers never see each other's addresses.
- Cafeterias appear in the email in `cafeterias:` (config) order, whatever
  order the form boxes were ticked in.

Adding a cafeteria to offer = add a `label: Korean name` line to
`cafeterias:` in `config.yaml` **and** the same label as a checkbox option
on the form.

**Privacy note:** a published-to-web CSV is readable by anyone who has the
URL. The URL is long, unguessable, and unindexed, but it does contain
subscribers' email addresses — don't post it anywhere. (The private
alternative is a Google service account + the Sheets API, at the cost of
some setup.)

## The glossary

`glossary.yaml` is the heart of the project — hand-maintained Korean →
English translations. It has three sections, each kept sorted so diffs stay
clean:

- **`dishes:`** — translations you've reviewed. Shown as-is.
- **`unreviewed:`** — machine translations added automatically whenever a new
  dish appears. These show up in the email with a small `*` footnote.
- **`annotations:`** — parenthetical markers, e.g. `뚝: served in a hot stone
  pot`. An empty value hides the marker entirely. Unknown markers are left
  as-is in the email.

To review: run

```bash
python main.py review
```

fix the English of each listed entry in `glossary.yaml`, and move the line
from `unreviewed:` up into `dishes:`. That's the whole workflow.

Markers seen on the site so far: `(#)` (no legend on the site — currently
hidden), `(뚝)` hot stone pot, `(채식변경가능)` vegetarian option,
`(추가)` extra, `(大)/(중)/(소)` sizes, `(잇템)` featured item,
`(순살변경 +)` boneless for an extra charge.

## Swapping the machine translator

`get_machine_translator()` in `snumenu/translate.py` is the single switch
point. Replace its body with anything that maps Korean text → English text
(Argos Translate, an LLM call, …).
