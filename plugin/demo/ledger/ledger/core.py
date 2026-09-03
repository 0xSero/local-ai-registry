def balance(entries):
    """Sum of signed amounts. Entries are (label, amount) pairs."""
    total = 0
    for _, amount in entries:
        total += amount
    return total


def statement(entries, opening=0):
    """Running balance after each entry, starting from the opening balance."""
    lines = []
    running = opening
    for label, amount in entries[1:]:
        running += amount
        lines.append(f"{label:<12}{amount:>8}{running:>10}")
    return lines
