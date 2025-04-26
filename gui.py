import tkinter as tk
from tkinter import messagebox
import grpc
import threading
import time
from argparse import ArgumentParser
from google.protobuf.empty_pb2 import Empty

import card_game_pb2 as pb
import card_game_pb2_grpc as stub

class CardGameGUI:
    def __init__(self, root, args):
        self.root = root
        self.root.title("Card Game App")


        self.channel = grpc.insecure_channel(f"{args.host}:{args.port}")
        self.stub = stub.CardGameServiceStub(self.channel)

        self.username = None
        self.game_id = None
        self.card_labels = []

        self.login_screen()

    def login_screen(self):
        self.clear_window()
        tk.Label(self.root, text="Username").pack()
        self.username_entry = tk.Entry(self.root)
        self.username_entry.pack()

        tk.Label(self.root, text="Password").pack()
        self.password_entry = tk.Entry(self.root, show='*')
        self.password_entry.pack()

        tk.Button(self.root, text="Login", command=self.login).pack()

    def update_leader_stub(self):
        known_ports = [50051, 50052, 50053]
        for port in known_ports:
            try:
                channel = grpc.insecure_channel(f"127.0.0.1:{port}")
                candidate_stub = stub.CardGameServiceStub(channel)
                res = candidate_stub.WhoIsLeader(Empty())
                if res.is_leader:
                    print(f"[GUI] Current leader at {res.leader_address}")
                    self.channel = grpc.insecure_channel(res.leader_address)
                    self.stub = stub.CardGameServiceStub(self.channel)
                    return
                if res.leader_address:
                    print(f"[GUI] Current leader at {res.leader_address}")
                    self.channel = grpc.insecure_channel(res.leader_address)
                    self.stub = stub.CardGameServiceStub(self.channel)
                    return
            except grpc.RpcError:
                continue
        print("[GUI] Failed to find a leader.")

    def start_leader_monitor(self):
        def monitor():
            while True:
                time.sleep(5)
                self.update_leader_stub()
        threading.Thread(target=monitor, daemon=True).start()

    def login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        resp = self.stub.Login(pb.LoginRequest(username=username, password=password))
        if resp.status == "success":
            self.username = username
            self.start_leader_monitor()
            self.home_screen()
        else:
            messagebox.showerror("Login Failed", resp.message)

    def home_screen(self):
        self.clear_window()
        tk.Label(self.root, text=f"Welcome {self.username}").pack()

        tk.Label(self.root, text="Number of players").pack()
        self.num_players_entry = tk.Entry(self.root)
        self.num_players_entry.pack()

        tk.Button(self.root, text="Start Match", command=self.start_match).pack()
        tk.Button(self.root, text="Accept Match", command=self.accept_match).pack()

        self.status_label = tk.Label(self.root, text="")
        self.status_label.pack()

    

    def with_leader_retry(rpc_fn):
        def wrapper(self, *args, **kwargs):
            try:
                return rpc_fn(self, *args, **kwargs)
            except grpc.RpcError as e:
                print("[GUI] RPC failed. Attempting to reconnect to leader...")
                self.update_leader_stub()
                return rpc_fn(self, *args, **kwargs)
        return wrapper

    def start_match(self):
        try:
            n = int(self.num_players_entry.get())
            self.status_label.config(text="Waiting for players...")
            self.root.update()

            while True:
                resp = self.stub.StartMatch(pb.MatchRequest(username=self.username, num_players=n))
                self.status_label.config(text=resp.message)
                self.root.update()

                if resp.status == "success":
                    game_id = resp.message.split("ID: ")[-1]
                    self.game_id = game_id.strip()
                    self.game_screen()
                    break
                elif resp.status == "error":
                    break

                time.sleep(2)
        except ValueError:
            messagebox.showerror("Error", "Enter a valid number")

    def accept_match(self):
        game_id = tk.simpledialog.askstring("Game ID", "Enter Game ID:")
        if not game_id:
            return
        resp = self.stub.AcceptMatch(pb.AcceptMatchRequest(username=self.username, game_id=game_id))
        if resp.status == "success":
            self.game_id = game_id
            self.game_screen()
        else:
            messagebox.showerror("Error", resp.message)

    def poll_game_state(self):
        while self.game_id:
            self.refresh_game_state()

            if not self.game_id:  # Set to None in refresh_game_state on game over
                time.sleep(3)
                self.home_screen()
                break
            time.sleep(0.5)

    def game_screen(self):
        self.clear_window()
        if self.root.title() != f"Game - {self.username}":
            self.root.title(f"Game - {self.username}")
        self.opponent_frame = tk.Frame(self.root, pady=5)
        self.opponent_frame.pack()
        self.opponent_labels = []

        self.info_frame = tk.Frame(self.root, padx=10, pady=10)
        self.info_frame.pack()

        self.turn_label = tk.Label(self.info_frame, font=("Helvetica", 14))
        self.turn_label.pack()
        self.played_label = tk.Label(self.info_frame, font=("Helvetica", 12))
        self.played_label.pack()
        self.time_label = tk.Label(self.info_frame, font=("Helvetica", 12))
        self.time_label.pack()

        self.card_frame = tk.Frame(self.root, pady=10)
        self.card_frame.pack()

        self.card_entry = tk.Entry(self.root)
        self.card_entry.pack()
        self.button_frame = tk.Frame(self.root, pady=10)
        self.button_frame.pack()

        tk.Button(self.button_frame, text="Play Card(s)", command=self.play_card, width=12).grid(row=0, column=0, padx=5)
        tk.Button(self.button_frame, text="Pass Turn", command=self.pass_turn, width=12).grid(row=0, column=1, padx=5)
        tk.Button(self.button_frame, text="Quit Game", command=self.quit_game, width=12).grid(row=0, column=2, padx=5)

        self.refresh_game_state()
        self.poll_thread = threading.Thread(target=self.poll_game_state, daemon=True)
        self.poll_thread.start()

    def refresh_game_state(self):
        try:
            resp = self.stub.GetGameState(pb.GameStateRequest(game_id=self.game_id, username=self.username))
            self.turn_label.config(text=f"Current Turn: {resp.current_turn}")
            self.played_label.config(text=f"Last Played: {resp.last_played_cards}")
            self.time_label.config(text=f"Time Left: {resp.countdown_seconds}s")

            user_hand = sorted([p.cards for p in resp.players if p.username == self.username][0])

            if len(self.card_labels) != len(user_hand):
                for widget in self.card_frame.winfo_children():
                    widget.destroy()
                self.card_labels = []
                for i, card in enumerate(user_hand):
                    card_label = tk.Label(self.card_frame, text=str(card), borderwidth=2, relief="solid", width=4, height=2)
                    card_label.grid(row=0, column=i, padx=5)
                    self.card_labels.append(card_label)
            else:
                # Just update the card values
                for i, card in enumerate(user_hand):
                    self.card_labels[i].config(text=str(card))
            
            opponents = [p for p in resp.players if p.username != self.username]
            if len(self.opponent_labels) != len(opponents):
                for widget in self.opponent_frame.winfo_children():
                    widget.destroy()
                self.opponent_labels = []
                for p in opponents:
                    label = tk.Label(
                        self.opponent_frame,
                        text=f"{p.username} - Cards: {p.card_count}, Win Rate: {p.win_rate:.2f}",
                        font=("Helvetica", 11)
                    )
                    label.pack()
                    self.opponent_labels.append(label)
            else:
                for label, p in zip(self.opponent_labels, opponents):
                    label.config(text=f"{p.username} - Cards: {p.card_count}, Win Rate: {p.win_rate:.2f}")

            if resp.game_over:
                messagebox.showinfo("Game Over", f"Winner: {resp.winner}")
                self.game_id = None
        except Exception as e:
            print(e)


    def clear_hand_display(self):
        for widget in self.card_frame.winfo_children():
            widget.destroy()

    @with_leader_retry
    def play_card(self):
        try:
            card_str = self.card_entry.get()
            cards = list(map(int, card_str.strip().split(",")))
            resp = self.stub.PlayCard(pb.PlayCardRequest(username=self.username, game_id=self.game_id, cards=cards))
            messagebox.showinfo("Result", resp.message)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    @with_leader_retry
    def pass_turn(self):
        resp = self.stub.PassTurn(pb.GameActionRequest(username=self.username, game_id=self.game_id))
        messagebox.showinfo("Pass", resp.message)

    @with_leader_retry
    def quit_game(self):
        resp = self.stub.QuitGame(pb.GameActionRequest(username=self.username, game_id=self.game_id))
        self.game_id = None
        messagebox.showinfo("Quit", resp.message)
        self.home_screen()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

if __name__ == "__main__":
    def parse_args():
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=50051)
        return parser.parse_args()

    args = parse_args()
    root = tk.Tk()
    app = CardGameGUI(root, args)
    root.mainloop()

# python gui.py --host=192.168.1.10 --port=50051