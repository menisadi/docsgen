def add_numbers(a, b):
    return a + b


def multiply_numbers(a, b):
    return a * b


def greet(name):
    """Returns a greeting message."""
    return f"Hello, {name}!"


if __name__ == "__main__":

    def inner_func(x):
        print(multiply_numbers(x, x))

    print(add_numbers(3, 5))
    print(multiply_numbers(4, 7))
    print(greet("Alice"))
