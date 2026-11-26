from typing import List, Tuple

def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Merges overlapping or touching intervals in a list of (start, end) tuples.

    :param intervals: List of (start, end) tuples of integers.
    :return: A new list of merged (start, end) tuples, sorted by start.
    """
    if not isinstance(intervals, list):
        raise TypeError("Input must be a list of intervals.")
    for interval in intervals:
        if not isinstance(interval, tuple) or len(interval) != 2:
            raise TypeError("Each interval must be a tuple of two integers.")
        if not all(isinstance(x, int) for x in interval):
            raise TypeError("Each interval must be a tuple of integers.")
        if interval[0] > interval[1]:
            raise ValueError("Interval start must not be greater than end.")

    intervals.sort(key=lambda x: x[0])
    merged = []
    for current in intervals:
        if not merged or merged[-1][1] < current[0]:
            merged.append(current)
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], current[1]))
    return merged

def run_tests():
    assert merge_intervals([(1, 3), (2, 6), (8, 10), (15, 18)]) == [(1, 6), (8, 10), (15, 18)]
    assert merge_intervals([(1, 4), (4, 5)]) == [(1, 5)]
    assert merge_intervals([(6, 8), (1, 9), (2, 4), (4, 7)]) == [(1, 9)]
    assert merge_intervals([]) == []
    assert merge_intervals([(5, 5)]) == [(5, 5)]

if __name__ == "__main__":
    run_tests()
