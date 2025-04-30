import pytest
import tkinter as tk
from unittest.mock import MagicMock
from unittest import mock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from gui import CardGameGUI

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