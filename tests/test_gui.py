import tkinter as tk
import pytest
import grpc
from google.protobuf.empty_pb2 import Empty
from tkinter import messagebox
from unittest.mock import MagicMock
from unittest import mock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from gui import CardGameGUI
import card_game_pb2 as pb

@pytest.fixture
def gui_app():
    root = tk.Tk()
    args = type("Args", (), {"host": "127.0.0.1", "port": 50051})
    app = CardGameGUI(root, args)
    yield app
    root.destroy()

def test_login_success(gui_app, mocker):
    mock_response = MagicMock()
    mock_response.status = "success"
    mock_response.message = ""
    mocker.patch.object(gui_app.stub, "Login", return_value=mock_response)
    gui_app.username_entry.insert(0, "testuser")
    gui_app.password_entry.insert(0, "testpass")

    gui_app.login()

    assert gui_app.username == "testuser"
    assert gui_app.root.title() == "Card Game App" 

def test_login_failure(gui_app, mocker):
    mock_response = MagicMock()
    mock_response.status = "error"
    mock_response.message = "Invalid credentials"
    mocker.patch.object(gui_app.stub, "Login", return_value=mock_response)

    gui_app.username_entry.insert(0, "wronguser")
    gui_app.password_entry.insert(0, "wrongpass")

    mocker.patch("tkinter.messagebox.showerror")

    gui_app.login()

    assert gui_app.username is None

def test_clear_window(gui_app):
    frame = tk.Frame(gui_app.root)
    frame.pack()
    gui_app.clear_window()
    assert len(gui_app.root.winfo_children()) == 0

def test_update_card_display_logic(gui_app):
    gui_app.cards_inner_frame = tk.Frame(gui_app.root)
    gui_app.card_canvas = mock.Mock()
    gui_app.card_values = []
    gui_app.update_card_display([1, 2, 3])
    assert gui_app.card_values == [1, 2, 3]


def test_start_match_success(gui_app):
    gui_app.username = "test_user"
    gui_app.num_players_entry = mock.Mock()
    gui_app.num_players_entry.get.return_value = "2"
    gui_app.status_label = mock.Mock()
    gui_app.root.update = mock.Mock()

    mock_resp_waiting = pb.Response(status="waiting", message="Waiting for players...")
    mock_resp_success = pb.Response(status="success", message="Game ready! ID: game123")

    with mock.patch.object(gui_app.stub, 'StartMatch', side_effect=[mock_resp_waiting, mock_resp_success]):
        with mock.patch.object(gui_app, 'game_screen') as mock_game_screen:
            with mock.patch("time.sleep", return_value=None): 
                gui_app.start_match()
                assert gui_app.game_id == "game123"
                mock_game_screen.assert_called_once()

def test_start_match_invalid_input(gui_app):
    gui_app.num_players_entry = mock.Mock()
    gui_app.num_players_entry.get.return_value = "abc" 
    with mock.patch.object(messagebox, "showerror") as mock_error:
        gui_app.start_match()
        mock_error.assert_called_once_with("Error", "Enter a valid number")


def test_poll_game_state_exits_and_calls_home_screen(gui_app):
    gui_app.game_id = "test-game"
    with mock.patch.object(gui_app, "refresh_game_state") as mock_refresh, \
         mock.patch.object(gui_app, "home_screen") as mock_home_screen, \
         mock.patch("time.sleep", return_value=None):

        def refresh_side_effect():
            gui_app.game_id = None 

        mock_refresh.side_effect = refresh_side_effect

        gui_app.poll_game_state()

        mock_refresh.assert_called()
        mock_home_screen.assert_called_once()


def test_refresh_game_state(gui_app):
    gui_app.username = "alice"
    gui_app.game_id = "game123"
    gui_app.card_values = []
    gui_app.opponent_info = []

    gui_app.turn_label = mock.Mock()
    gui_app.played_label = mock.Mock()
    gui_app.time_label = mock.Mock()
    gui_app.update_card_display = mock.Mock()
    gui_app.update_opponents_display = mock.Mock()

    players = [
        pb.PlayerInfo(username="alice", cards=[1, 2, 3], card_count=3, win_rate=0.5, is_connected=True, is_current_turn=True),
        pb.PlayerInfo(username="bob", cards=[], card_count=5, win_rate=0.2, is_connected=True, is_current_turn=False)
    ]

    mock_response = pb.GameStateResponse(
        status="success",
        current_turn="alice",
        last_played_cards=[4],
        players=players,
        countdown_seconds=10,
        game_over=True,
        winner="alice"
    )

    with mock.patch.object(gui_app.stub, "GetGameState", return_value=mock_response), \
         mock.patch("tkinter.messagebox.showinfo") as mock_info:

        gui_app.refresh_game_state()

    gui_app.turn_label.config.assert_called_with(text="Current Turn: alice")
    gui_app.played_label.config.assert_called_with(text="Last Played: 4")
    gui_app.time_label.config.assert_called_with(text="Time Left: 10s")
    gui_app.update_card_display.assert_called_once_with([1, 2, 3])
    gui_app.update_opponents_display.assert_called_once()
    mock_info.assert_called_once_with("Game Over", "Winner: alice")
    assert gui_app.game_id is None

def test_update_opponents_display(gui_app):
    class FakePlayer:
        def __init__(self, username, card_count, win_rate):
            self.username = username
            self.card_count = card_count
            self.win_rate = win_rate

    opponents = [
        FakePlayer("bob", 5, 0.6),
        FakePlayer("carol", 3, 0.4)
    ]

    fake_widget1 = mock.Mock()
    fake_widget2 = mock.Mock()
    gui_app.opponents_container = mock.Mock()
    gui_app.opponents_container.winfo_children.return_value = [fake_widget1, fake_widget2]

    with mock.patch("tkinter.Label") as mock_label:
        mock_label_instance = mock.Mock()
        mock_label.return_value = mock_label_instance

        gui_app.update_opponents_display(opponents)

    fake_widget1.destroy.assert_called_once()
    fake_widget2.destroy.assert_called_once()

    assert mock_label.call_count == 2
    assert all(lbl.pack.called for lbl in gui_app.opponent_labels)
    assert gui_app.opponent_info == opponents

def test_update_leader_stub_no_leader(gui_app):
    with mock.patch("grpc.insecure_channel"), \
         mock.patch("card_game_pb2_grpc.CardGameServiceStub") as mock_stub:

        stub_instance = mock.Mock()
        stub_instance.WhoIsLeader.side_effect = grpc.RpcError("Connection failed")
        mock_stub.return_value = stub_instance

        with mock.patch("builtins.print") as mock_print:
            gui_app.update_leader_stub()
            mock_print.assert_any_call("[GUI] Failed to find a leader.")

