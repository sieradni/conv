class Board:
    def __init__(self):
        # Initialize a 3x3 board with empty spaces (None)
        self.grid = [[None for _ in range(3)] for _ in range(3)]

    def display(self):
        # Print the board to the console
        for i, row in enumerate(self.grid):
            row_str = " | ".join(['X' if cell == 'X' else 'O' if cell == 'O' else ' ' for cell in row])
            print(f"{row_str}")
            if i < 2:
                print("---")

    def is_full(self):
        # Check if the board is full
        return all(cell is not None for row in self.grid for cell in row)

    def make_move(self, row, col, player):
        # Place a marker on the board if the spot is empty
        if 0 <= row < 3 and 0 <= col < 3 and self.grid[row][col] is None:
            self.grid[row][col] = player
            return True
        return False

    def check_winner(self):
        # Check if there is a winner
        # Check rows
        for row in self.grid:
            if row[0] is not None and row[0] == row[1] == row[2]:
                return row[0]
        # Check columns
        for col in range(3):
            if self.grid[0][col] is not None and self.grid[0][col] == self.grid[1][col] == self.grid[2][col]:
                return self.grid[0][col]
        # Check diagonals
        if self.grid[0][0] is not None and self.grid[0][0] == self.grid[1][1] == self.grid[2][2]:
            return self.grid[0][0]
        if self.grid[0][2] is not None and self.grid[0][2] == self.grid[1][1] == self.grid[2][0]:
            return self.grid[0][2]
        
        return None
