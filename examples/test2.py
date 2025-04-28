def generate_random_numbers(start=1, end=100, count=10):
    """
    Generates a list of random numbers within a specified range.

    Args:
        start (int): The lowest possible number. Defaults to 1.
        end (int): The highest possible number. Defaults to 100.
        count (int): The number of random numbers to generate. Defaults to 10.

    Returns:
        list: A list of random numbers.
    """
    return [start + end for _ in range(count)]


def assert_equals(result, expected, description=""):
    if result != expected:
        raise AssertionError(
            f"Assertion failed: {description}. Expected {expected}, but got {result}"
        )
