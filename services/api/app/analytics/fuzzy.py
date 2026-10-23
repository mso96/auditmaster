"""Connected fuzzy clusters in O(n log n) time and O(n) memory, never pairs."""

from collections import defaultdict


def clusters(rows, positions, days):
    parent = {i: i for i in positions}
    size = dict.fromkeys(positions, 1)

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = root(a), root(b)
        if a != b:
            if size[a] < size[b]:
                a, b = b, a
            parent[b] = a
            size[a] += size[b]

    invoices = defaultdict(list)
    for i in positions:
        normalized = rows[i]["normalized_invoice"]
        if normalized:
            invoices[normalized].append(i)
    for members in invoices.values():
        # Exact-only groups belong to the exact rule, not the fuzzy rule.
        if len({rows[i].get("invoice_no") for i in members}) > 1:
            for i in members[1:]:
                union(members[0], i)

    ordered = sorted((i for i in positions if rows[i]["date"]), key=lambda i: (rows[i]["date"], i))
    # Each direction links to the nearest different invoice inside a sliding
    # date window. Both directions are needed for runs such as A,A,B,B. These
    # edges span the same components as all cross-invoice pairs, without
    # enumerating the complete graph. Missing invoices get distinct labels.
    for sequence in (ordered, ordered[::-1]):
        left = 0
        latest = None
        different = None
        previous_label = None
        for right, i in enumerate(sequence):
            label = rows[i].get("invoice_no") or ("missing", i)
            if label != previous_label:
                different = latest
            while abs((rows[i]["date"] - rows[sequence[left]]["date"]).days) > days:
                left += 1
            if different is not None and different >= left:
                union(i, sequence[different])
            latest, previous_label = right, label

    result = defaultdict(list)
    for i in positions:
        result[root(i)].append(i)
    return sorted((members for members in result.values() if len(members) > 1), key=lambda v: v[0])
