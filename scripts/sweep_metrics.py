"""Derive an honest metrics summary from speed-sweep rows.

Only aggregates that follow directly from the rows are computed; every
field the source did not report stays null. Importers that already carry
a richer source-provided metrics block (the Postgres publication) keep it.
"""


def _numbers(rows, key):
    return [row[key] for row in rows if isinstance(row.get(key), (int, float))]


def _peak(rows, key):
    values = _numbers(rows, key)
    return max(values) if values else None


def derive_metrics(rows, latest_point_at=None):
    return {
        "concurrency": _peak(rows, "concurrency"),
        "point_count": len(rows),
        "max_context_tokens": _peak(rows, "context_tokens"),
        "peak_generation_tps": _peak(rows, "decode_tok_s"),
        "peak_prompt_tps": _peak(rows, "prefill_tok_s"),
        "latest_point_at": latest_point_at,
    }
