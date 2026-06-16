def divide(a, b):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise ValueError("Both arguments must be numeric")
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b