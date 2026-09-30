# Notes

## Commands

```bash
python main.py                    # send today's emails (uses .env)
python main.py --dry-run          # print emails + write email-N.html, send nothing
python main.py print              # print the whole page's menu, no email
python main.py --date 2026-09-28 --dry-run
python add_subscriber.py          # add/update a subscriber interactively
python -m pytest                  # offline tests
```

## .env (chmod 600, gitignored)

```
GMAIL_ADDRESS=...       # bot account that sends
GMAIL_APP_PASSWORD=...  # its Gmail app password
MY_EMAIL=...            # gets error/empty-day notes
DEEPL_API_KEY=...:fx    # optional fallback translator
```

## Translation

Fallback chain (swap point: `get_machine_translator()` in
snumenu/translate.py): Claude CLI → DeepL → Google. The `claude` CLI must
be logged in and on PATH. New dishes are translated once and cached in
`glossary.yaml`; `print` translates the whole page, a normal run only
subscribed cafeterias.

## Scheduling

Windows Task Scheduler task **"SNU menu email"**, daily 00:05 (KST), runs
`run.sh` in WSL — no login needed (S4U), wakes the PC from sleep (wake
timers must stay allowed in power settings; won't fire if fully shut
down). Output goes to `menu.log` — check it if no email came.

```powershell
Start-ScheduledTask -TaskName "SNU menu email"        # test now (really sends)
Get-ScheduledTaskInfo -TaskName "SNU menu email"      # LastTaskResult 0 = ok
Unregister-ScheduledTask -TaskName "SNU menu email"   # remove
# recreate (admin PowerShell):
Register-ScheduledTask -TaskName "SNU menu email" `
  -Action    (New-ScheduledTaskAction -Execute "wsl.exe" -Argument "/home/alexguo/menu-snu/run.sh") `
  -Trigger   (New-ScheduledTaskTrigger -Daily -At 12:05AM) `
  -Principal (New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U) `
  -Settings  (New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 10))
```

## Subscribers

`subscribers.csv` (gitignored, not backed up): one line per person,
`email[,cafeteria,...]` with Korean names from config's `cafeterias:`
map; email alone = all, `#` = comment. Add/change with
`python add_subscriber.py`; remove by deleting the line. Offering a new
cafeteria = one `label: Korean name` line in config.

## Glossary

`glossary.yaml`: Korean → English cache, used as-is. Edit a line to fix a
translation, delete it to retranslate. Annotation markers: `(#)` unknown
(hidden), `(뚝)` hot stone pot, `(채식변경가능)` vegetarian option,
`(추가)` extra, `(大)/(중)/(소)` sizes, `(잇템)` featured item,
`(순살변경 +)` boneless for a surcharge.
