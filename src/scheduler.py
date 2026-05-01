import time
from datetime import datetime, timezone


class Scheduler:
    CYCLE_INTERVAL = 900  # 15 minutes between cycles
    WEEKEND_POLL   = 60   # seconds between checks during weekend sleep
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

    def run(self, loop_fn, on_sleep=None, on_error=None):
        while True:
            if self.is_weekend_sleep():
                self._weekend_wait(on_sleep)
                continue

            try:
                loop_fn()
            except Exception as e:
                if on_error:
                    try:
                        on_error(e)
                    except Exception:
                        pass
                time.sleep(self.ERROR_BACKOFF)
                continue

            secs = self.CYCLE_INTERVAL
            if on_sleep:
                try:
                    on_sleep(secs)
                except Exception:
                    pass
            time.sleep(secs)

    def _weekend_wait(self, on_sleep=None):
        while self.is_weekend_sleep():
            # time until Sunday 22:00 UTC
            now  = datetime.now(timezone.utc)
            secs = self.WEEKEND_POLL
            if on_sleep:
                try:
                    on_sleep(secs, weekend=True)
                except Exception:
                    pass
            time.sleep(secs)
