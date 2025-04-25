import random
import time
import threading
from collections import Counter

def get_pattern_type(cards):
    counter = Counter(cards)
    counts = sorted(counter.values(), reverse=True)
    
    if len(cards) == 1:
        return "single", cards[0]
    elif len(cards) == 2 and counts == [2]:
        return "pair", cards[0]
    elif len(cards) == 3 and counts == [3]:
        return "triple", cards[0]
    elif len(cards) == 4 and counts == [3, 1]:
        return "triple_plus_one", [k for k, v in counter.items() if v == 3][0]
    elif len(cards) == 4 and counts == [4]:
        return "bomb", cards[0]
    else:
        return "invalid", None

class GameSession:
    def __init__(self, game_id, players):
        self.game_id = game_id
        self.players = players  # List of usernames
        self.hands = {p: [] for p in players}
        self.current_turn_index = 0
        self.last_played = []
        self.last_played_player = None
        self.winner = None
        self.quit_players = set()
        self.turn_start_time = time.time()

        
        self.init_cards()

        self.game_loop_thread = threading.Thread(target=self._game_loop, daemon=True)
        self.game_loop_thread.start()
    
    def init_cards(self):
        cards = list(range(1, 11)) * 4 
        random.shuffle(cards)
        n = len(self.players)
        base = len(cards) // n
        extras = len(cards) % n
        
        idx = 0
        for i, player in enumerate(self.players):
            take = base + (1 if i < extras else 0)
            self.hands[player] = cards[idx:idx+take]
            idx += take

    def pass_turn(self, player):
        if player != self.get_current_player():
            return False, "Not your turn."

        original_turn = self.current_turn_index

        # Advance to the next active player
        while True:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
            next_player = self.players[self.current_turn_index]
            if next_player not in self.quit_players:
                break
            if self.current_turn_index == original_turn:
                # Only one player left
                self.winner = player
                return True, f"{player} wins by default!"

        self.turn_start_time = time.time()

        # If everyone else passed and it's back to the last player who played,
        # reset the round
        if self.players[self.current_turn_index] == self.last_played_player:
            self.last_played = []
            self.last_played_player = None
            return True, f"Everyone else passed. {self.get_current_player()} starts a new round."

        return True, f"{player} passed the turn."

    def _game_loop(self):
        while not self.winner:
            time.sleep(1)

            now = time.time()
            elapsed = now - self.turn_start_time
            self.countdown = max(0, int(20 - elapsed))

            if elapsed >= 20:
                current_player = self.get_current_player()
                print(f"[AutoPass] {current_player} took too long. Auto-passing.")
                self.pass_turn(current_player)
                self.turn_start_time = time.time()


    def get_current_player(self):
        return self.players[self.current_turn_index]
    
    def get_game_state(self):
        max_turn_duration = 20
        time_elapsed = time.time() - self.turn_start_time
        countdown = max(0, int(max_turn_duration - time_elapsed))

        return {
            "game_id": self.game_id,
            "current_turn": self.get_current_player(),
            "last_played": self.last_played,
            "winner": self.winner,
            "hands": self.hands.copy(),
            "players": self.players[:],
            "quit_players": list(self.quit_players),
            "countdown_seconds": countdown
        }
    
    def get_server_state(self, requesting_player=None):
        player_info = []
        for player in self.players:
            is_current = player == self.get_current_player()
            should_show_cards = (player == requesting_player) or (is_current and requesting_player is None)
            
            player_info.append({
                "username": player,
                "card_count": len(self.hands[player]),
                "cards": self.hands[player] if should_show_cards else [],
                "is_current_turn": is_current,
                "is_connected": player not in self.quit_players
            })
            
        return {
            "game_id": self.game_id,
            "current_turn": self.get_current_player(),
            "last_played": self.last_played,
            "winner": self.winner,
            "players": player_info,
            "countdown_seconds": self.countdown,
            "game_over": self.winner is not None
        }
    
    def is_valid_play(self, cards, player):
        if not self.last_played or player == self.last_played_player:
            return get_pattern_type(cards)[0] != "invalid"  # allow any valid pattern to start round

        current_type, current_rank = get_pattern_type(cards)
        previous_type, previous_rank = get_pattern_type(self.last_played)

        if current_type == "invalid":
            return False

        # Bomb beats anything except higher bomb
        if current_type == "bomb":
            if previous_type != "bomb":
                return True
            else:
                return current_rank > previous_rank

        # Must match pattern and be higher rank
        return current_type == previous_type and current_rank > previous_rank
    
    def play_cards(self, player, cards):
        if player != self.get_current_player():
            return False, "Not your turn."
        if not all(c in self.hands[player] for c in cards):
            return False, "You don't have those cards."
        if not self.is_valid_play(cards, player):
            return False, "Invalid play: must beat previous play with same number and higher rank"
        
        for c in cards:
            self.hands[player].remove(c)
        
        self.last_played = cards
        self.last_played_player = player
        
        # Check for win condition
        if len(self.hands[player]) == 0:
            self.winner = player
            return True, "Player won the game!"
        
        # Move to next player
        self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        while self.players[self.current_turn_index] in self.quit_players:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.players)

        self.turn_start_time = time.time()
        return True, "Cards played successfully"
        
    def player_quit(self, player):
        if player not in self.players:
            return False, "Player not in game"
            
        self.quit_players.add(player)
        
        # If current player quit, move to next
        if player == self.get_current_player():
            self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
            while self.players[self.current_turn_index] in self.quit_players:
                self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        
        # Check if only one player remains
        active_players = [p for p in self.players if p not in self.quit_players]
        if len(active_players) == 1:
            self.winner = active_players[0]
            
        return True, f"{player} quit the game"
    
    def quit_game(self, player):
        return self.player_quit(player)
        
    def update_countdown(self, seconds_remaining):
        self.countdown = seconds_remaining

    def serialize(self):
        """Convert GameSession into a simple dictionary for syncing."""
        return {
            "game_id": self.game_id,
            "players": self.players,
            "hands": self.hands,
            "current_turn_index": self.current_turn_index,
            "last_played": self.last_played,
            "last_played_player": self.last_played_player,
            "winner": self.winner,
            "quit_players": list(self.quit_players),
            "turn_start_time": self.turn_start_time
        }

    @staticmethod
    def deserialize(data):
        """Create a GameSession from a dictionary."""
        session = GameSession(data["game_id"], data["players"])
        session.hands = data["hands"]
        session.current_turn_index = data["current_turn_index"]
        session.last_played = data["last_played"]
        session.last_played_player = data["last_played_player"]
        session.winner = data["winner"]
        session.quit_players = set(data["quit_players"])
        session.turn_start_time = data["turn_start_time"]
        return session
