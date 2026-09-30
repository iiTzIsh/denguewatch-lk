"""Day 2 practice: how try / except / else / finally behave."""


def to_int(text: str) -> int:
    """Convert text like '120' to int. Raise a CLEAR error if it can't."""
    try:
        value = int(text.strip())
    except ValueError as exc:
        # add context, keep the original error attached with "from exc"
        raise ValueError(f"Cases value '{text}' is not a whole number") from exc
    else:
        # runs ONLY if the try block had no error
        if value < 0:
            raise ValueError(f"Cases can't be negative: {value}")
        return value
    finally:
        # runs ALWAYS (error or not) - used for cleanup like closing files
        print(f"  [finally] checked '{text}'")


for raw in ["120", " 45 ", "-3", "1,200", "abc"]:
    try:
        print(f"'{raw}' ->", to_int(raw))
    except ValueError as err:
        print(f"'{raw}' -> ERROR: {err}")