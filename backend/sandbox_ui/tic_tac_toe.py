class TicTacToe:
    def __init__(self):
        self.board = [[" ", " ", " "] for _ in range(3)]
        self.current_player = "X"

    def make_move(self, row, col):
        if not (0 <= row < 3 and 0 <= col < 3) or self.board[row][col] != " ":
            return False
        self.board[row][col] = self.current_player
        if not self.is_winner():
            self.current_player = "O" if self.current_player == "X" else "X"
        return True

    def is_winner(self):
        # Rows and columns
        for i in range(3):
            if all(cell == self.current_player for cell in self.board[i]): return True
            if all(self.board[j][i] == self.current_player for j in range(3)): return True
        # Diagonals
        if all(self.board[i][i] == self.current_player for i in range(3)):
            return True
        if all(self.board[i][2-i] == self.current_player for i in range(3)):
            return True
        return False