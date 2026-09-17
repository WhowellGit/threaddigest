"""The Jinja filters the pages share with the digest.

``when`` and ``duration`` are ``core.digest``'s own functions, registered here under the
names the digest's own templates already use. Two spellings of a timestamp would eventually
disagree about a zone or a seconds field, and a page showing a different time from the
digest of the same run is the drift this project treats as a defect; that the web needed
them too is the second concrete use N-20 asks for before a helper is made public.

``count`` prints a :class:`core.digest.Count` -- the number together with the population it
was counted out of -- and refuses anything else. The refusal is the point rather than a
safety net: "show the denominator" is a design rule, and a template reaching for a bare
integer fails loudly at render time instead of printing a number no reader can size. The
formatting itself lives in ``Count.__str__`` and is not repeated here.
"""

from __future__ import annotations

from jinja2 import Environment

from threaddigest.core.digest import Count, duration, when

__all__ = ["count", "register"]


def count(value: object) -> str:
    """``12 of 60 items seen (20%)``. Anything but a :class:`Count` is a render-time error."""
    if not isinstance(value, Count):
        msg = (
            f"the count filter takes a core.digest.Count, not {type(value).__name__}: a number "
            "printed without the population it came out of is what this filter exists to stop"
        )
        raise TypeError(msg)
    return str(value)


def register(env: Environment) -> None:
    """Install the three filters on ``env``; the names match the digest's templates."""
    env.filters.update({"when": when, "duration": duration, "count": count})
