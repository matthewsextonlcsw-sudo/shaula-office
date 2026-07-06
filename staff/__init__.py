"""staff — the AI-staff engine for the box.

Each "staff member" (blog, front desk, customer service, marketer, ...) is a
`StaffTask` that turns a practice dict (the same one build_practice.py produces)
into a validated `StaffResult`. Honesty is enforced once, in the base class, for
every member: the SAME banned-claim linter the website engine uses (engine/
generate.py `lint`) runs over the whole output before anything is returned.

Today only BlogScaffold is live. It produces an honest editorial *brief*, not a
finished post (see staff/blog.py for why). The rest are roadmap.

Import the base contract from here; import concrete members from their module
(e.g. ``from staff.blog import BlogScaffold``) so running ``python3 -m staff.blog``
does not double-import the package.
"""
from __future__ import annotations

from .base import StaffHonestyError, StaffResult, StaffTask

__all__ = ["StaffTask", "StaffResult", "StaffHonestyError"]
