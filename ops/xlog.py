#!/usr/bin/env python3
"""Shared xlog-format line parser for both the DGL_MILESTONES file and
crawl's own end-of-game `logfile` (PLAN.md §6). Mirrors hiscores.cc's
_xlog_split_fields/_xlog_unescape: fields are ':'-separated key=value pairs,
and a literal ':' inside a value is escaped as '::'.

Factored out of ops/telemetry-test.py (which verified this algorithm against
a real milestones file) so ops/runner.py can reuse it for the logfile row
without duplicating the escape-handling logic.
"""


def parse_line(line):
    fields = {}
    parts = []
    start = 0
    i = 0
    n = len(line)
    while i < n:
        if line[i] == ":":
            if i + 1 < n and line[i + 1] == ":":
                i += 2
                continue
            parts.append(line[start:i])
            i += 1
            start = i
            continue
        i += 1
    parts.append(line[start:])
    for part in parts:
        if "=" not in part:
            continue
        key, _, val = part.partition("=")
        fields[key] = val.replace("::", ":")
    return fields
