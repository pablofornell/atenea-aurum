import time
from datetime import datetime, timedelta, timezone


class Scheduler:
    CYCLE_INTERVAL = 900  # 15 minutes between cycles
    ERROR_BACKOFF  = 30   # seconds to wait after a non-fatal error

    def is_weekend_sleep(self) -> bool:
        now = datetime.now(timezone.utc)
        wd  = now.weekday()   # 0=Mon … 4=Fri, 5=Sat, 6=Sun
        h   = now.hour
        if wd == 4 and h >= 21:
            return True
        if wd == 5:
            return True
        if wd == 6 and h < 22:
            return True
        return False

    def is_in_killzone(self, cfg) -> bool:
        killzones = getattr(cfg, "KILLZONES", None)
        if not killzones:
            return True

        now = datetime.now(timezone.utc)
        wd  = now.weekday()
        h   = now.hour

        fri_cutoff = getattr(cfg, "KILLZONE_FRI_CUTOFF", 19)
        mon_start  = getattr(cfg, "KILLZONE_MON_START",  2)

        if wd == 4 and h >= fri_cutoff:
            return False
        if wd == 0 and h < mon_start:
            return False

        return any(start <= h < end for start, end in killzones)

    def _seconds_until_open(self) -> float:
        """Seconds until next market open (Sunday 22:00 UTC)."""
        now = datetime.now(timezone.utc)
        days_until_sunday = (6 - now.weekday()) % 7
        open_dt = (now + timedelta(days=days_until_sunday)).replace(
            hour=22, minute=0, second=0, microsecond=0
        )
        if open_dt <= now:
            open_dt += timedelta(weeks=1)
        return max((open_dt - now).total_seconds(), 0)

    def _seconds_until_killzone(self, cfg) -> float:
        """Seconds until the next killzone window opens."""
        killzones  = cfg.KILLZONES
        fri_cutoff = getattr(cfg, "KILLZONE_FRI_CUTOFF", 19)
        mon_start  = getattr(cfg, "KILLZONE_MON_START",  2)
        now        = datetime.now(timezone.utc)

        for delta_m in range(1, 7 * 24 * 60 + 1):
            t  = now + timedelta(minutes=delta_m)
            wd = t.weekday()
            h  = t.hour
            if wd == 5 or (wd == 6 and h < 22):      # weekend
                continue
            if wd == 4 and h >= fri_cutoff:
                continue
            if wd == 0 and h < mon_start:
                continue
            if any(start <= h < end for start, end in killzones):
                return (t - now).total_seconds()

        return 3600.0

    def run(self, loop_fn, cfg=None, on_sleep=None, on_error=None):
        while True:
            if self.is_weekend_sleep():
                self._weekend_wait(on_sleep)
                continue

            if cfg is not None and not self.is_in_killzone(cfg):
                self._killzone_wait(cfg, on_sleep)
                continue

            try:
                next_secs = loop_fn()
            except Exception as e:
                if on_error:
                    try:
                        on_error(e)
                    except Exception:
                        pass
                time.sleep(self.ERROR_BACKOFF)
                continue

            secs = (
                next_secs
                if isinstance(next_secs, (int, float)) and next_secs > 0
                else self.CYCLE_INTERVAL
            )
            if on_sleep:
                try:
                    on_sleep(secs)
                except Exception:
                    pass
            time.sleep(secs)

    def _weekend_wait(self, on_sleep=None):
        secs = self._seconds_until_open()
        if on_sleep:
            try:
                on_sleep(secs, weekend=True)
            except Exception:
                pass
        time.sleep(secs)

    def _killzone_wait(self, cfg, on_sleep=None):
        secs = self._seconds_until_killzone(cfg)
        if on_sleep:
            try:
                on_sleep(secs, killzone=True)
            except Exception:
                pass
        time.sleep(secs)
