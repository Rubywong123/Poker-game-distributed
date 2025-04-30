import os
import pytest
import sys
import sqlite3

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from storage import Storage

TEST_DB = "test_cardgame.db"

@pytest.fixture
def storage():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    s = Storage(TEST_DB)
    yield s
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_register_user(storage):
    res = storage.login_register_user("alice", "password")
    assert res["status"] == "success"

def test_login_success(storage):
    storage.login_register_user("bob", "pass")
    res = storage.login_register_user("bob", "pass")
    assert res["status"] == "success"

def test_login_fail(storage):
    storage.login_register_user("charlie", "secret")
    res = storage.login_register_user("charlie", "wrong")
    assert res["status"] == "error"

def test_create_game(storage):
    res = storage.create_game("game123")
    assert res["status"] == "success"

def test_add_player(storage):
    storage.create_game("game123")
    res = storage.add_player_to_game("game123", "dave", [1, 2, 3])
    assert res["status"] == "success"

def test_update_cards(storage):
    storage.create_game("game123")
    storage.add_player_to_game("game123", "eve", [1, 2])
    storage.update_cards("game123", "eve", [5, 6])
    row = storage.execute_query("SELECT cards FROM game_players WHERE username='eve'").fetchone()
    assert row["cards"] == "5,6"

def test_declare_winner(storage):
    storage.login_register_user("winner", "pw")
    storage.login_register_user("loser", "pw")
    storage.create_game("gameX")
    storage.add_player_to_game("gameX", "winner", [1])
    storage.add_player_to_game("gameX", "loser", [2])
    storage.declare_winner("gameX", "winner")
    stats = storage.execute_query("SELECT num_win, num_lost FROM users WHERE username='winner'").fetchone()
    assert stats["num_win"] == 1
    assert stats["num_lost"] == 0
