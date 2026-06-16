import unittest
from math_utils import divide

class TestMathUtils(unittest.TestCase):
    def test_divide_success(self):
        self.assertEqual(divide(10, 2), 5)
        self.assertEqual(divide(-6, 3), -2)
        self.assertEqual(divide(5, 1), 5)

    def test_divide_by_zero(self):
        with self.assertRaises(ValueError) as cm:
            divide(10, 0)
        self.assertEqual(str(cm.exception), "Division by zero is not allowed")

if __name__ == '__main__':
    unittest.main()