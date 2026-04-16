# Instruction Manual

This project fetches substitution plan data from DSBMobile.

## Important file names

- `in.py` means `dsbapi/__init__.py`
- `run.py` is the command-line entry point

## Setup

Install dependencies:

```powershell
pip install -r requirements.txt
```

If `pip` does not install Pillow correctly, install it manually:

```powershell
pip install pillow
```

## Basic usage

Run the script with username and password:

```powershell
py run.py --username YOUR_USERNAME --password YOUR_PASSWORD
```

Example:

```powershell
py run.py --username 161382 --password Fokus42
```

You can also use environment variables:

```powershell
$env:DSB_USERNAME='161382'
$env:DSB_PASSWORD='Fokus42'
py run.py
```

## Filter by type

Show only entries where `type` is `7e`:

```powershell
py run.py --username 161382 --password Fokus42 --type 7e
```

## Date logic

`run.py` uses Germany time by default.

Default behavior:

- After `08:00`, it shows the next school day
- Before `08:00`, it still shows the same target school day as the previous evening
- Friday after `08:00` moves to Monday

Examples:

- Thursday 18:00 -> Friday plan
- Friday 07:30 -> Friday plan
- Friday 10:00 -> Monday plan

## Timezone option

The default timezone is hard-coded Berlin time with daylight saving support.

You can still override it with a fixed UTC offset:

```powershell
py run.py --username 161382 --password Fokus42 --timezone UTC+2
py run.py --username 161382 --password Fokus42 --timezone UTC+1
```

## Other options

Set a different cutoff hour:

```powershell
py run.py --username 161382 --password Fokus42 --cutoff-hour 9
```

Force a specific date:

```powershell
py run.py --username 161382 --password Fokus42 --date 2026-04-17
```

Include image OCR:

```powershell
py run.py --username 161382 --password Fokus42 --include-images
```

Use multiple options together:

```powershell
py run.py --username 161382 --password Fokus42 --type 7e --cutoff-hour 8
```

## Output

The script prints JSON with:

- `timezone`
- `target_date`
- `current_time`
- `filters`
- `entries`

## What was fixed in `in.py`

The file `dsbapi/__init__.py` was cleaned up to fix several problems:

- missing imports
- broken image handling
- duplicate imports
- bad response parsing
- missing HTTP error handling
- broken text decoding for umlauts
- safer timetable parsing
- request timeout support

## Common problems

### `Unknown timezone`

Use the default with no `--timezone`, or pass a fixed offset like `UTC+2`.

### Broken German characters

This was fixed in `in.py`. If text still looks wrong, run the command again and verify your terminal encoding.

### Login or fetch failure

Check:

- username and password are correct
- the DSBMobile service is reachable
- your school account still has data available

## Files

- `dsbapi/__init__.py`: main API code
- `run.py`: CLI runner
- `requirements.txt`: dependencies
- `INSTRUCTION_MANUAL.md`: this manual
