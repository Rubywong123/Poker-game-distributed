import pytest
import tkinter as tk
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