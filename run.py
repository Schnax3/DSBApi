import argparse
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from dsbapi import DSBApi


DEFAULT_CUTOFF_HOUR = 8
DEFAULT_TIMEZONE = "Europe/Berlin"
SCHOOL_WEEKDAYS = {0, 1, 2, 3, 4}
FIXED_OFFSET_PATTERN = re.compile(r"^UTC(?P<sign>[+-])(?P<hours>\d{1,2})(?::(?P<minutes>\d{2}))?$", re.IGNORECASE)


class BerlinTimezone(tzinfo):
    def tzname(self, dt):
        return "CEST" if self._is_dst(dt) else "CET"

    def utcoffset(self, dt):
        return timedelta(hours=2 if self._is_dst(dt) else 1)

    def dst(self, dt):
        return timedelta(hours=1 if self._is_dst(dt) else 0)

    def fromutc(self, dt):
        standard_time = (dt + timedelta(hours=1)).replace(tzinfo=self)
        if self._is_dst(standard_time):
            return (dt + timedelta(hours=2)).replace(tzinfo=self)
        return standard_time

    def _is_dst(self, dt):
        if dt is None:
            return False

        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)

        year = dt.year
        start = self._last_sunday(year, 3, 2)
        end = self._last_sunday(year, 10, 3)
        return start <= dt < end

    @staticmethod
    def _last_sunday(year, month, hour):
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)
        while last_day.weekday() != 6:
            last_day -= timedelta(days=1)
        return datetime.combine(last_day, time(hour=hour))


BERLIN_TZ = BerlinTimezone()


def build_parser():
    parser = argparse.ArgumentParser(description="Fetch DSBMobile substitution plan entries.")
    parser.add_argument("--username", default=os.getenv("DSB_USERNAME"), help="DSB username")
    parser.add_argument("--password", default=os.getenv("DSB_PASSWORD"), help="DSB password")
    parser.add_argument(
        "--tablemapper",
        nargs="*",
        help="Optional column mapping override, for example: --tablemapper class lesson subject",
    )
    parser.add_argument(
        "--type",
        dest="entry_type",
        help="Only include entries whose type exactly matches this value, for example: 7e",
    )
    parser.add_argument(
        "--timezone",
        default=os.getenv("DSB_TIMEZONE", DEFAULT_TIMEZONE),
        help="Timezone used for day selection. Supports Europe/Berlin and fixed offsets like UTC+2.",
    )
    parser.add_argument(
        "--cutoff-hour",
        type=int,
        default=DEFAULT_CUTOFF_HOUR,
        help="Keep showing the same next school day until this hour on that day, default: 8",
    )
    parser.add_argument(
        "--date",
        help="Optional explicit target date in YYYY-MM-DD format. Overrides automatic next-day logic.",
    )
    parser.add_argument(
        "--include-images",
        action="store_true",
        help="Run OCR on linked JPG timetable images as well.",
    )
    return parser


def filter_entries(entries, entry_type=None, target_date=None):
    if isinstance(entries, list) and entries and all(isinstance(item, dict) for item in entries):
        return [entry for entry in entries if entry_matches(entry, entry_type, target_date)]

    if isinstance(entries, list):
        filtered = []
        for group in entries:
            if isinstance(group, list):
                matches = [entry for entry in group if isinstance(entry, dict) and entry_matches(entry, entry_type, target_date)]
                if matches:
                    filtered.append(matches)
        return filtered

    return entries


def entry_matches(entry, entry_type=None, target_date=None):
    if entry_type and entry.get("type") != entry_type:
        return False
    if target_date and parse_entry_date(entry.get("date")) != target_date:
        return False
    return True


def parse_entry_date(value):
    if not value:
        return None

    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_cli_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"Invalid --date value '{value}'. Use YYYY-MM-DD.") from exc


def resolve_timezone(name):
    normalized = name.strip()
    if normalized.lower() in {"europe/berlin", "berlin", "germany", "de"}:
        return BERLIN_TZ, DEFAULT_TIMEZONE

    match = FIXED_OFFSET_PATTERN.match(normalized)
    if match:
        hours = int(match.group("hours"))
        minutes = int(match.group("minutes") or 0)
        if hours > 23 or minutes > 59:
            raise SystemExit(f"Invalid timezone '{name}'. Use Europe/Berlin or a fixed offset like UTC+2.")
        total_minutes = hours * 60 + minutes
        if match.group("sign") == "-":
            total_minutes *= -1
        tz = timezone(timedelta(minutes=total_minutes))
        label = f"UTC{match.group('sign')}{hours:02d}:{minutes:02d}"
        return tz, label

    raise SystemExit(f"Unknown timezone '{name}'. Use Europe/Berlin or a fixed offset like UTC+2.")


def next_school_day(start_date):
    candidate = start_date + timedelta(days=1)
    while candidate.weekday() not in SCHOOL_WEEKDAYS:
        candidate += timedelta(days=1)
    return candidate


def resolve_target_date(timezone_name, cutoff_hour, explicit_date=None):
    tz, timezone_label = resolve_timezone(timezone_name)
    if explicit_date is not None:
        return explicit_date, None, timezone_label

    now = datetime.now(timezone.utc).astimezone(tz)
    anchor_date = now.date() if now.hour >= cutoff_hour else now.date() - timedelta(days=1)
    return next_school_day(anchor_date), now, timezone_label


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.username or not args.password:
        parser.error("username and password are required, either as flags or via DSB_USERNAME / DSB_PASSWORD")
    if not 0 <= args.cutoff_hour <= 23:
        parser.error("cutoff-hour must be between 0 and 23")

    explicit_date = parse_cli_date(args.date) if args.date else None
    target_date, now, timezone_label = resolve_target_date(args.timezone, args.cutoff_hour, explicit_date)

    client = DSBApi(args.username, args.password, tablemapper=args.tablemapper)

    try:
        entries = client.fetch_entries(images=args.include_images)
        entries = filter_entries(entries, args.entry_type, target_date)
    except Exception as exc:
        print(f"Failed to fetch entries: {exc}", file=sys.stderr)
        return 1

    output = {
        "timezone": timezone_label,
        "target_date": target_date.isoformat(),
        "current_time": now.isoformat() if now else None,
        "filters": {
            "type": args.entry_type,
            "cutoff_hour": args.cutoff_hour,
        },
        "entries": entries,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
