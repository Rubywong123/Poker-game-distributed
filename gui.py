import tkinter as tk
from tkinter import messagebox, simpledialog
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
        self.root.geometry("800x600") 
        self.root.configure(bg="#2c3e50")

        self.colors = {
            "bg": "#2c3e50",  
            "text": "#ecf0f1",   
            "button_bg": "#3498db",  
            "button_fg": "#6f6a69",  
            "card_bg": "#ffffff", 
            "card_fg": "#e74c3c", 
            "frame_bg": "#34495e", 
            "entry_bg": "#ecf0f1",  
            "entry_fg": "#2c3e50", 
        }

        self.channel = grpc.insecure_channel(f"{args.host}:{args.port}")
        self.stub = stub.CardGameServiceStub(self.channel)

        self.username = None
        self.game_id = None
        self.card_labels = []
        self.card_frames = []
        self.card_values = []
        self.opponent_info = []

        self.default_font = ("Helvetica", 12)
        self.header_font = ("Helvetica", 14, "bold")
        self.card_font = ("Courier", 12, "bold")

        self.card_width = 40
        self.card_height = 60

        self.login_screen()

    def create_styled_label(self, parent, text, font=None, bg=None, fg=None, pady=5):
        if font is None:
            font = self.default_font
        if bg is None:
            bg = self.colors["frame_bg"]
        if fg is None:
            fg = self.colors["text"]
            
        label = tk.Label(parent, text=text, font=font, bg=bg, fg=fg)
        label.pack(pady=pady)
        return label

    def create_styled_entry(self, parent, show=None, width=20):
        entry = tk.Entry(parent, 
                        font=self.default_font, 
                        bg=self.colors["entry_bg"],
                        fg=self.colors["entry_fg"],
                        width=width)
        if show:
            entry.config(show=show)
        entry.pack(pady=5)
        return entry

    def create_styled_button(self, parent, text, command, width=15):
        button = tk.Button(parent, 
                          text=text, 
                          command=command,
                          font=self.default_font,
                          bg=self.colors["button_bg"],
                          fg=self.colors["button_fg"],
                          width=width,
                          relief=tk.RAISED)
        button.pack(pady=8)
        return button

    def login_screen(self):
        self.clear_window()
        
        main_frame = tk.Frame(self.root, bg=self.colors["bg"], padx=20, pady=20)
        main_frame.pack(expand=True)
        
        # title_label = self.create_styled_label(
        #     main_frame, 
        #     "Card Game Login", 
        #     font=("Helvetica", 18, "bold"),
        #     bg=self.colors["bg"]
        # )
        
        form_frame = tk.Frame(main_frame, bg=self.colors["frame_bg"], padx=30, pady=30)
        form_frame.pack(pady=20)
        
        self.create_styled_label(form_frame, "Username")
        self.username_entry = self.create_styled_entry(form_frame)

        self.create_styled_label(form_frame, "Password")
        self.password_entry = self.create_styled_entry(form_frame, show='*')

        self.create_styled_button(form_frame, "Login", self.login)

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
        
        main_frame = tk.Frame(self.root, bg=self.colors["bg"], padx=20, pady=20)
        main_frame.pack(expand=True, fill=tk.BOTH)
        
        game_frame = tk.Frame(main_frame, bg=self.colors["frame_bg"], padx=30, pady=30)
        game_frame.pack(pady=20, fill=tk.X)
        
        new_match_label = self.create_styled_label(
            game_frame, 
            "Start a New Match", 
            font=self.header_font,
            bg=self.colors["frame_bg"]
        )
        
        player_frame = tk.Frame(game_frame, bg=self.colors["frame_bg"])
        player_frame.pack(pady=5)
        
        tk.Label(
            player_frame, 
            text="Number of players:", 
            font=self.default_font,
            bg=self.colors["frame_bg"],
            fg=self.colors["text"]
        ).pack(side=tk.LEFT, padx=5)
        
        self.num_players_entry = tk.Entry(
            player_frame,
            font=self.default_font,
            width=5,
            bg=self.colors["entry_bg"],
            fg=self.colors["entry_fg"]
        )
        self.num_players_entry.pack(side=tk.LEFT, padx=5)
        
        button_frame = tk.Frame(game_frame, bg=self.colors["frame_bg"])
        button_frame.pack(pady=15)
        
        start_button = tk.Button(
            button_frame,
            text="Start Match",
            command=self.start_match,
            font=self.default_font,
            bg=self.colors["button_bg"],
            fg=self.colors["button_fg"],
            width=15,
            relief=tk.RAISED
        )
        start_button.pack(side=tk.LEFT, padx=10)
        
        self.status_label = tk.Label(
            main_frame,
            text="",
            font=self.default_font,
            bg=self.colors["bg"],
            fg=self.colors["text"],
            wraplength=600
        )
        self.status_label.pack(pady=10)

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

    # def accept_match(self):
    #     game_id = simpledialog.askstring("Game ID", "Enter Game ID:")
    #     if not game_id:
    #         return
    #     resp = self.stub.AcceptMatch(pb.AcceptMatchRequest(username=self.username, game_id=game_id))
    #     if resp.status == "success":
    #         self.game_id = game_id
    #         self.game_screen()
    #     else:
    #         messagebox.showerror("Error", resp.message)

    def poll_game_state(self):
        while self.game_id:
            self.refresh_game_state()

            if not self.game_id:
                time.sleep(3)
                self.home_screen()
                break
            time.sleep(0.5)

    def create_card_widgets(self):
        self.card_canvas = tk.Canvas(self.card_display_area, bg=self.colors["bg"], highlightthickness=0)
        self.card_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.cards_scrollbar = tk.Scrollbar(self.card_display_area, orient=tk.HORIZONTAL, command=self.card_canvas.xview)
        self.card_canvas.configure(xscrollcommand=self.cards_scrollbar.set)
        self.show_scrollbar = False

        
        self.card_canvas.configure(xscrollcommand=self.cards_scrollbar.set)
        
        self.cards_inner_frame = tk.Frame(self.card_canvas, bg=self.colors["bg"])
        self.canvas_window = self.card_canvas.create_window((0, 0), window=self.cards_inner_frame, anchor=tk.NW)
        
        self.card_canvas.bind("<Configure>", self.on_canvas_configure)
        self.cards_inner_frame.bind("<Configure>", self.on_frame_configure)
        self.card_canvas.bind_all("<MouseWheel>", self.on_mousewheel)

    def on_canvas_configure(self, event):
        self.card_canvas.configure(scrollregion=self.card_canvas.bbox("all"))

    def on_frame_configure(self, event):
        self.card_canvas.configure(scrollregion=self.card_canvas.bbox("all"))
        self.card_canvas.itemconfig(self.canvas_window, width=event.width)

    def on_mousewheel(self, event):
        self.card_canvas.xview_scroll(int(-1*(event.delta/120)), "units")

    def game_screen(self):
        self.clear_window()
        if self.root.title() != f"Game - {self.username}":
            self.root.title(f"Game - {self.username}")
            
        main_container = tk.Frame(self.root, bg=self.colors["bg"])
        main_container.pack(fill=tk.BOTH, expand=True)
        
        self.opponent_frame = tk.Frame(main_container, bg=self.colors["frame_bg"], padx=10, pady=10)
        self.opponent_frame.pack(fill=tk.X, padx=20, pady=(10, 5))

        
        opponent_title = tk.Label(
            self.opponent_frame,
            text="OPPONENTS",
            font=self.header_font,
            bg=self.colors["frame_bg"],
            fg=self.colors["text"]
        )
        opponent_title.pack(pady=(0, 5))
        
        self.opponents_container = tk.Frame(self.opponent_frame, bg=self.colors["frame_bg"])
        self.opponents_container.pack(fill=tk.X)
        self.opponent_labels = []
        
        self.info_frame = tk.Frame(main_container, bg=self.colors["frame_bg"], padx=20, pady=10)
        self.info_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.turn_label = tk.Label(
            self.info_frame,
            text="Current Turn: ",
            font=self.header_font,
            bg=self.colors["frame_bg"],
            fg=self.colors["text"]
        )
        self.turn_label.pack(pady=1)
        
        self.played_label = tk.Label(
            self.info_frame,
            text="Last Played: ",
            font=self.default_font,
            bg=self.colors["frame_bg"],
            fg=self.colors["text"]
        )
        self.played_label.pack(pady=1)

        
        self.time_label = tk.Label(
            self.info_frame,
            text="Time Left: ",
            font=self.default_font,
            bg=self.colors["frame_bg"],
            fg=self.colors["text"]
        )
        self.time_label.pack(pady=1)
        
        player_section = tk.Frame(main_container, bg=self.colors["bg"], padx=20, pady=10)
        player_section.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        player_title = tk.Label(
            player_section,
            text=f"YOUR CARDS - {self.username}",
            font=self.header_font,
            bg=self.colors["bg"],
            fg=self.colors["text"]
        )
        player_title.pack(pady=(0, 10))
        
        self.card_display_area = tk.Frame(player_section, bg=self.colors["bg"], height=100)
        self.card_display_area.pack(fill=tk.X, pady=5)
        self.card_display_area.pack_propagate(False) 
        
        control_frame = tk.Frame(player_section, bg=self.colors["bg"], pady=10)
        control_frame.pack(fill=tk.X)
        
        tk.Label(
            control_frame,
            text="Enter cards to play (comma separated):",
            font=self.default_font,
            bg=self.colors["bg"],
            fg=self.colors["text"]
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        self.card_entry = tk.Entry(
            control_frame,
            font=self.default_font,
            width=20,
            bg=self.colors["entry_bg"],
            fg=self.colors["entry_fg"]
        )
        self.card_entry.pack(side=tk.LEFT, padx=5)
        
        self.button_frame = tk.Frame(player_section, bg=self.colors["bg"], pady=5)
        self.button_frame.pack()
        
        play_button = tk.Button(
            self.button_frame,
            text="Play Card(s)",
            command=self.play_card,
            font=self.default_font,
            bg=self.colors["button_bg"],
            fg=self.colors["button_fg"],
            width=12,
            relief=tk.RAISED
        )
        play_button.grid(row=0, column=0, padx=5)
        
        pass_button = tk.Button(
            self.button_frame,
            text="Pass Turn",
            command=self.pass_turn,
            font=self.default_font,
            bg=self.colors["button_bg"],
            fg=self.colors["button_fg"],
            width=12,
            relief=tk.RAISED
        )
        pass_button.grid(row=0, column=1, padx=5)
        
        quit_button = tk.Button(
            self.button_frame,
            text="Quit Game",
            command=self.quit_game,
            font=self.default_font,
            bg="#e74c3c",
            fg=self.colors["button_fg"],
            width=12,
            relief=tk.RAISED
        )
        quit_button.grid(row=0, column=2, padx=5)
        
        self.create_card_widgets()
        self.refresh_game_state()
        self.poll_thread = threading.Thread(target=self.poll_game_state, daemon=True)
        self.poll_thread.start()

    def update_card_display(self, user_hand):
        for widget in self.cards_inner_frame.winfo_children():
            widget.destroy()
        
        self.card_frames = []
        user_hand = sorted(user_hand)
        
        overlap = 0
        if len(user_hand) > 15:
            overlap = 15 
        
        effective_width = self.card_width - overlap
        
        for i, card in enumerate(user_hand):
            x_pos = i * effective_width
            
            card_frame = tk.Frame(
                self.cards_inner_frame,
                width=self.card_width,
                height=self.card_height,
                bg=self.colors["card_bg"],
                highlightbackground="#000000",
                highlightthickness=1,
                relief=tk.RAISED,
                borderwidth=2
            )
            card_frame.place(x=x_pos, y=0)
            card_frame.pack_propagate(False) 
            
            tk.Label(
                card_frame,
                text=str(card),
                font=("Courier", 8),
                bg=self.colors["card_bg"],
                fg=self.colors["card_fg"]
            ).place(x=2, y=2)
            
            tk.Label(
                card_frame,
                text=str(card),
                font=("Courier", 14, "bold"),
                bg=self.colors["card_bg"],
                fg=self.colors["card_fg"]
            ).place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            
            tk.Label(
                card_frame,
                text=str(card),
                font=("Courier", 8),
                bg=self.colors["card_bg"],
                fg=self.colors["card_fg"]
            ).place(relx=0.85, rely=0.88, anchor=tk.CENTER)
            
            self.card_frames.append(card_frame)
        
        total_width = len(user_hand) * effective_width
        if len(user_hand) > 0:
            total_width += overlap
        
        self.cards_inner_frame.configure(width=total_width, height=self.card_height)

        self.card_canvas.configure(scrollregion=(0, 0, total_width, self.card_height))

        self.card_values = user_hand

    def update_opponents_display(self, opponents):
        for widget in self.opponents_container.winfo_children():
            widget.destroy()
        
        self.opponent_labels = []
        for p in opponents:
            opponent_info = tk.Label(
                self.opponents_container,
                text=f"{p.username} - Cards: {p.card_count}, Win Rate: {p.win_rate:.2f}",
                font=self.default_font,
                bg=self.colors["frame_bg"],
                fg=self.colors["text"]
            )
            opponent_info.pack(pady=2)
            self.opponent_labels.append(opponent_info)
        
        self.opponent_info = opponents

    def refresh_game_state(self):
        try:
            resp = self.stub.GetGameState(pb.GameStateRequest(game_id=self.game_id, username=self.username))
            
            self.turn_label.config(text=f"Current Turn: {resp.current_turn}")
            last_played_str = ", ".join(map(str, resp.last_played_cards))
            self.played_label.config(text=f"Last Played: {last_played_str}")
            self.time_label.config(text=f"Time Left: {resp.countdown_seconds}s")

            user_hand = []
            for p in resp.players:
                if p.username == self.username:
                    user_hand = p.cards
                    break
            
            current_hand = sorted(user_hand)
            if self.card_values != current_hand:
                self.update_card_display(current_hand)
            
            opponents = [p for p in resp.players if p.username != self.username]
            
            need_update = False
            if len(self.opponent_info) != len(opponents):
                need_update = True
            else:
                for old_p, new_p in zip(self.opponent_info, opponents):
                    if (old_p.username != new_p.username or
                        old_p.card_count != new_p.card_count or 
                        abs(old_p.win_rate - new_p.win_rate) > 0.01):
                        need_update = True
                        break
            
            if need_update:
                self.update_opponents_display(opponents)

            if resp.game_over:
                messagebox.showinfo("Game Over", f"Winner: {resp.winner}")
                self.game_id = None
                
        except Exception as e:
            print(f"Error refreshing game state: {e}")

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