from typing import List, Tuple

def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Merge overlapping or touching intervals in a list of (start, end) tuples.
    
    Parameters:
    intervals (List[Tuple[int, int]]): A list of (start, end) tuples.
    
    Returns:
    List[Tuple[int, int]]: A new list of merged (start, end) tuples.
    
    Raises:
    TypeError: If intervals is not a list or any element is not a tuple of exactly two integers.
    ValueError: If any interval has start > end.
    """
    if not isinstance(intervals, list):
        raise TypeError("Input must be a list of intervals.")
    
    merged = []
    for interval in intervals:
        if not isinstance(interval, tuple) or len(interval) != 2:
            raise TypeError("Each interval must be a tuple of exactly two integers.")
        if interval[0] > interval[1]:
            raise ValueError("Interval start must not be greater than end.")
        
        if not merged or merged[-1][1] < interval[0]:
            merged.append(interval)
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], interval[1]))
    
    return merged

def run_tests():
    assert merge_intervals([(1, 3), (2, 6), (8, 10), (15, 18)]) == [(1, 6), (8, 10), (15, 18)]
    assert merge_intervals([(1, 4), (4, 5)]) == [(1, 5)]
    assert merge_intervals([]) == []
    assert merge_intervals([(5, 7), (1, 3), (2, 4)]) == [(1, 4), (5, 7)]
    try:
        merge_intervals("not a list")
    except TypeError as e:
        assert str(e) == "Input must be a list of intervals."
    try:
        merge_intervals([(1, 3), (2, "not an int")])
    except TypeError as e:
        assert str(e) == "Each interval must be a tuple of exactly two integers."
    try:
        merge_intervals([(1, 3), (4, 2)])
    except ValueError as e:
        assert str(e) == "Interval start must not be greater than end."

if __name__ == "__main__":
    run_tests()
