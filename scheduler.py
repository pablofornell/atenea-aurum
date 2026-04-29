import time
from datetime import datetime, timezone


class Scheduler:
    WEEKEND_POLL   = 300   # seconds between weekend-sleep checks
    ERROR_BACKOFF  = 30    # seconds to wait after a non-fatal error

    def is_weekend_sleep(self) -> bool:
        now = datetime.now(timezone.utc)
        wd  = now.weekday()  # 0=Mon … 4=Fri, 5=Sat, 6=Sun
        h   = now.hour

        if wd == 4 and h >= 21:   # Friday from 21:00
            return True
        if wd == 5:               # Saturday all day
            return True
        if wd == 6 and h < 22:   # Sunday before 22:00
            return True
        return False

    def wait_for_candle_close(self, timeframe_minutes: int = 15):
        now     = datetime.now(timezone.utc)
        total_s = now.minute * 60 + now.second
        period  = timeframe_minutes * 60
        elapsed = total_s % period
        remaining = period - elapsed
        if remaining < 5:
            remaining += period
        time.sleep(remaining)

    def run(self, loop_fn):
        while True:
            if self.is_weekend_sleep():
                self.wait_for_weekend_end()
                continue

            try:
                loop_fn()
            except Exception as e:
                print(f"[SCHEDULER] non-fatal error: {e}")
                time.sleep(self.ERROR_BACKOFF)
                continue

            self.wait_for_candle_close(15)

    def wait_for_weekend_end(self):
        while self.is_weekend_sleep():
            now = datetime.now(timezone.utc)
            print(f"[SCHEDULER] Weekend sleep — {now.strftime('%Y-%m-%d %H:%M UTC')} — next check in {self.WEEKEND_POLL}s")
            time.sleep(self.WEEKEND_POLL)
