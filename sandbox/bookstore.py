class Bookstore:
    def __init__(self, inventory):
        self.inventory = inventory

    def check_stock(self, title):
        quantity = self.inventory.get(title)
        if quantity is None or quantity <= 0:
            return f"{title} is out of stock."
        return f"{title} has {quantity} in stock."