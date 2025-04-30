import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from session import GameSession, get_pattern_type

def test_game_initialization():
    session = GameSession("game1", ["alice", "bob"])
    assert set(session.players) == {"alice", "bob"}
    assert sum(len(cards) for cards in session.hands.values()) == 40
    assert session.get_current_player() in session.players

def test_get_current_player_rotates():
    session = GameSession("game2", ["alice", "bob"])
    first = session.get_current_player()
    session.pass_turn(first)
    second = session.get_current_player()
    assert first != second
    assert second in session.players

def test_valid_card_play():
    session = GameSession("game3", ["alice", "bob"])
    player = session.get_current_player()
    cards = session.hands[player][:1]
    success, msg = session.play_cards(player, cards)
    assert success
    assert msg == "Cards played successfully" or "Player won the game!" in msg

def test_invalid_card_play_not_your_turn():
    session = GameSession("game4", ["alice", "bob"])
    not_turn = [p for p in session.players if p != session.get_current_player()][0]
    success, msg = session.play_cards(not_turn, [1])
    assert not success
    assert msg == "Not your turn."

def test_invalid_card_play_wrong_cards():
    session = GameSession("game5", ["alice", "bob"])
    player = session.get_current_player()
    success, msg = session.play_cards(player, [99])
    assert not success
    assert msg == "You don't have those cards."

def test_pass_turn_logic():
    session = GameSession("game6", ["alice", "bob"])
    player = session.get_current_player()
    success, msg = session.pass_turn(player)
    assert success
    assert "passed the turn" in msg or "starts a new round" in msg

def test_quit_game_and_win_by_default():
    session = GameSession("game7", ["alice", "bob"])
    player = session.get_current_player()
    other = [p for p in session.players if p != player][0]
    session.quit_game(other)
    assert session.winner == player

def test_winning_condition():
    session = GameSession("game8", ["alice", "bob"])
    player = session.get_current_player()
    session.hands[player] = [3] 
    success, msg = session.play_cards(player, [3])
    assert success
    assert session.winner == player
    assert "won the game" in msg

def test_get_pattern_type_invalid():
    assert get_pattern_type([]) == ("invalid", None)       
    assert get_pattern_type([1, 2]) == ("invalid", None)   
    assert get_pattern_type([2, 2, 3]) == ("invalid", None)   
    assert get_pattern_type([4, 4, 4, 5]) == ("triple_plus_one", 4)

def test_bomb_beats_non_bomb():
    session = GameSession("game9", ["alice", "bob"])
    player = session.get_current_player()
    session.last_played = [2] 
    session.last_played_player = "bob" 

    session.hands[player] = [9, 9, 9, 9]
    success, msg = session.play_cards(player, [9, 9, 9, 9])
    assert success

def test_same_pattern_higher_rank():
    session = GameSession("game10", ["alice", "bob"])
    player = session.get_current_player()
    session.last_played = [3, 3]
    session.last_played_player = "bob"
    session.hands[player] = [5, 5]
    success, _ = session.play_cards(player, [5, 5])
    assert success

def test_serialize_deserialize_roundtrip():
    session = GameSession("game12", ["alice", "bob"])
    data = session.serialize()
    new_session = GameSession.deserialize(data)
    assert new_session.players == session.players
    assert new_session.hands == session.hands
