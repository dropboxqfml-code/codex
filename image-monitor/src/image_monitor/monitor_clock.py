"""Wait for the monitor's service deadline while allowing a cooperative stop."""


def stop_requested(should_stop):
    if should_stop is None:
        return False
    stopped = should_stop()
    if type(stopped) is not bool:
        raise ValueError("The monitor stop condition must return a boolean")
    return stopped


def wait_until(clock, due, should_stop):
    """Return True when due, or False when a stop is requested before then."""
    now = clock.now()
    while not stop_requested(should_stop):
        remaining = (due - now).total_seconds()
        if remaining <= 0:
            return True
        clock.wait(remaining if should_stop is None else min(remaining, 0.5))
        advanced = clock.now()
        if advanced <= now:
            if stop_requested(should_stop):
                return False
            raise ValueError("Monitor clock did not advance during its wait")
        now = advanced
    return False
