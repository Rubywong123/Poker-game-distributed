import random

class GameSession:
    def __init__(self, game_id, players):
        self.game_id = game_id
        self.players = players  # List of usernames
        self.hands = {p: [] for p in players}
        self.current_turn_index = 0
        self.last_played = []
        self.winner = None
        self.quit_players = set()

        self.init_cards()

    def init_cards(self):
        cards = list(range(1, 11)) * 4  # 4 copies of 1-10 => 40 cards
        random.shuffle(cards)
        n = len(self.players)
        base = len(cards) // n
        extras = len(cards) % n

        idx = 0
        for i, player in enumerate(self.players):
            take = base + (1 if i < extras else 0)
            self.hands[player] = cards[idx:idx+take]
            idx += take

    def get_current_player(self):
        return self.players[self.current_turn_index]
    
    def get_game_state(self):
        return {
            "game_id": self.game_id,
            "current_turn": self.get_current_player(),
            "last_played": self.last_played,
            "winner": self.winner,
            "hands": self.hands.copy(),
            "players": self.players[:],
            "quit_players": list(self.quit_players)
        }

    def is_valid_play(self, cards):
        if not self.last_played:
            return True  # Any card is valid if nothing has been played
        return sum(cards) > sum(self.last_played)  # Example rule: higher total value wins

    def play_cards(self, player, cards):
        if player != self.get_current_player():
            return False, "Not your turn."
        if not all(c in self.hands[player] for c in cards):
            return False, "You don't have those cards."
        if not self.is_valid_play(cards):
            return False, "Play must beat the previous cards."

        for c in cards:
            self.hands[player].remove(c)

        self.last_played = cards
