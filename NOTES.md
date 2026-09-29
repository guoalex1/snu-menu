## Everyday commands

```bash
python -m pytest                  # offline tests (saved page fixture)
python main.py --dry-run          # print today's emails, write email-N.html
python main.py print              # just print the translated menu
python main.py --date 2026-09-28 --dry-run
python main.py                    # actually send (needs .env)
```

The machine-translation fallback is swappable in one place:
`get_machine_translator()` in `snumenu/translate.py`. Currently: the
Claude CLI translates all unknown names in one batch call (best quality;
runs on the Claude Code subscription, so `claude` must be logged in and on
PATH for the scheduled task); if that fails, DeepL (when `DEEPL_API_KEY`
is in `.env`; called via its REST API directly, since the deep-translator
wrapper lacks Korean) and then Google take over. Google 429-blocks this
ISP's IP range with its "unusual traffic" wall — may lift on its own.
Claude stays primary on purpose: DeepL tested well on descriptive names
but outputs bare romanization ("Seopsan-jeok") for culturally-specific
dishes, and doesn't follow the glossary's romanized-name + gloss style.

DeepL setup: sign up for the **DeepL API Free** plan at
<https://www.deepl.com/pro-api> (needs an email and a card for identity
verification — it is not charged; free quota is 500k chars/month, orders
of magnitude more than this uses). Then Account → **API Keys** → copy the
key (free-plan keys end in `:fx`) and add `DEEPL_API_KEY=...:fx` to
`.env`. Without the key the chain just skips DeepL.
The daily run only translates cafeterias someone subscribes to; `print`
translates the whole page (useful to pre-warm the glossary before offering
a new cafeteria). After 3 consecutive translator failures a run gives up
and shows Korean names, retrying next day.

## Environment (.env)

| Variable | Meaning |
| --- | --- |
| `GMAIL_ADDRESS` | the Gmail account that sends the email (dedicated bot account) |
| `GMAIL_APP_PASSWORD` | app password for that account (see below) |
| `MY_EMAIL` | where error/empty-day notes go (just me) |

`main.py` reads `.env` itself; real environment variables take precedence.
Keep `.env` at `chmod 600`. If the app password ever leaks: revoke it at
<https://myaccount.google.com/apppasswords> — it can't be used to take over
the account, only to read/send mail until revoked.

### Creating a Gmail app password

1. Turn on 2-Step Verification for the account (myaccount.google.com →
   Security). App passwords are hidden until 2SV is on.
2. Go to <https://myaccount.google.com/apppasswords>, create one named
   e.g. "snu-menu", copy the 16 characters. The normal password won't work
   with SMTP.

## Scheduling (Windows Task Scheduler + WSL)

Cron inside WSL only fires while the WSL VM happens to be running, so the
schedule lives in Windows Task Scheduler, which boots WSL on demand.
`run.sh` runs `main.py` and appends output to `menu.log`.

Registered task: **"SNU menu email"**, daily 7:00 (Windows local time; PC
is on KST). Created with (PowerShell, no admin):

```powershell
$action   = New-ScheduledTaskAction -Execute "wsl.exe" `
            -Argument "-d Ubuntu -u alexguo -- /home/alexguo/menu-snu/run.sh"
$trigger  = New-ScheduledTaskTrigger -Daily -At 7:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "SNU menu email" -Action $action `
    -Trigger $trigger -Settings $settings
```

- `-StartWhenAvailable` catches up a run missed while the PC was asleep.
- Defaults work, so `-d Ubuntu -u alexguo --` could be dropped, but they're
  the first thing to put back if the task runs in the wrong distro/user.
- Caveats: runs only while logged in to Windows; PC must be on around 7:00.
  Check `menu.log` if an email doesn't arrive.

```powershell
Start-ScheduledTask -TaskName "SNU menu email"        # test it now
Unregister-ScheduledTask -TaskName "SNU menu email"   # remove it
```

To pin the trigger to UTC instead of local time (survives timezone
changes): after creating `$trigger`, set
`$trigger.StartBoundary = "2026-09-29T22:00:00Z"` (22:00 UTC = 07:00 KST).

## Subscribers

`subscribers.csv` (path set by `subscribers_file:` in `config.yaml`), one
line per person: email first, then optionally the cafeterias they want,
using the Korean names from the `cafeterias:` map. An email alone means
all cafeterias; `#` lines are comments.

```csv
# email[, cafeteria, cafeteria, ...]
alexguoxh@gmail.com
friend@example.com,301동식당,예술계식당(아름드리)
```

- Everyone with the same selection shares one email, BCC'd, so subscribers
  never see each other's addresses.
- Cafeterias always appear in `cafeterias:` (config) order.
- A typo'd cafeteria name or a malformed line makes the run exit with an
  error naming it, rather than silently dropping someone.
- The label in `cafeterias:` doubles as the cafeteria's English name in
  the email (trailing parenthetical stripped): `Bldg 301 cafeteria
  (301동식당)` → heading "Bldg 301 cafeteria".

Adding a cafeteria to offer = one `label: Korean name` line in
`cafeterias:`. Anyone with no explicit list ("all") starts receiving it
automatically.

The file is gitignored so friends' addresses stay off GitHub; it lives
only on this machine (remember it's not backed up by the repo).

## The glossary

`glossary.yaml` is a translation cache: hand-maintained seed translations
plus every machine translation, added automatically the first time a dish
appears. Each name is only ever translated once. To fix a bad translation,
just edit its line — whatever is in the file is used as-is (and to force a
retranslation, delete the line). Sections stay sorted; an empty
`annotations:` value hides that marker.

Markers seen on the site so far: `(#)` (no legend on the site — currently
hidden), `(뚝)` hot stone pot, `(채식변경가능)` vegetarian option, `(추가)`
extra, `(大)/(중)/(소)` sizes, `(잇템)` featured item, `(순살변경 +)`
boneless for an extra charge.
