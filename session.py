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
        self.countdown = 20
        
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
        # Return in the original format expected by the GUI
        return {
            "game_id": self.game_id,
            "current_turn": self.get_current_player(),
            "last_played": self.last_played,
            "winner": self.winner,
            "hands": self.hands.copy(),
            "players": self.players[:],
            "quit_players": list(self.quit_players),
            "countdown_seconds": self.countdown
        }
    
    # For server compatibility - not used by GUI directly
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
        
        # Check for win condition
        if len(self.hands[player]) == 0:
            self.winner = player
            return True, "Player won the game!"
        
        # Move to next player
        self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        while self.players[self.current_turn_index] in self.quit_players:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        
        # Reset countdown
        self.countdown = 20
            
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
        
    def update_countdown(self, seconds_remaining):
        self.countdown = seconds_remaining