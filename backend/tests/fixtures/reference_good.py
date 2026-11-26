from typing import List, Tuple


def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Reference implementation used only to validate the hidden tests."""
    if not isinstance(intervals, list):
        raise TypeError("intervals must be a list")
    for iv in intervals:
        if not (isinstance(iv, tuple) and len(iv) == 2 and all(type(x) is int for x in iv)):
            raise TypeError("each interval must be a tuple of two ints")
        if iv[0] > iv[1]:
            raise ValueError("start > end")
    merged = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged
