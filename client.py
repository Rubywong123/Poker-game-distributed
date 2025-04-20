import grpc
import threading
import time
from argparse import ArgumentParser

import card_game_pb2 as pb
import card_game_pb2_grpc as stub

def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--host", default='127.0.0.1', help="Host address")
    parser.add_argument("--port", default=50051, help="Port number")
    return parser.parse_args()

class CardGameClient:
    def __init__(self, channel):
        self.stub = stub.CardGameServiceStub(channel)
        self.username = None
        self.game_id = None

    def login(self):
        self.username = input("Username: ")
        password = input("Password: ")
        response = self.stub.Login(pb.LoginRequest(username=self.username, password=password))
        print(response.message)
        return response.status == "success"

    def logout(self):
        if self.username:
            self.stub.Logout(pb.LogoutRequest(username=self.username))
            print("Logged out.")

    def start_match(self):
        n = int(input("Number of players (2-4): "))
        response = self.stub.StartMatch(pb.MatchRequest(username=self.username, num_players=n))
        print(response.message)

    def accept_match(self):
        gid = input("Enter game ID to accept: ")
        response = self.stub.AcceptMatch(pb.AcceptMatchRequest(username=self.username, game_id=gid))
        print(response.message)
        if response.status == "success":
            self.game_id = gid

    def get_game_state(self):
        if not self.game_id:
            print("Not in a game.")
            return
        resp = self.stub.GetGameState(pb.GameStateRequest(game_id=self.game_id))
        print(f"\nGame ID: {self.game_id}")
        print(f"Current Turn: {resp.current_turn}")
        for p in resp.players:
            print(f"Player: {p.username} | Cards: {p.card_count} | Connected: {p.is_connected} | Win Rate: {p.win_rate:.2f}")
            if p.username == self.username:
                print(f"Your hand: {p.cards}")
        if resp.last_played_cards:
            print("Last played:", resp.last_played_cards)
        if resp.game_over:
            print(f"\nGame Over! Winner: {resp.winner}")

    def play_card(self):
        if not self.game_id:
            print("Not in a game.")
            return
        try:
            cards = list(map(int, input("Enter cards to play (comma-separated): ").split(",")))
        except ValueError:
            print("Invalid card list.")
            return
        resp = self.stub.PlayCard(pb.PlayCardRequest(username=self.username, game_id=self.game_id, cards=cards))
        print(resp.message)

    def pass_turn(self):
        if not self.game_id:
            print("Not in a game.")
            return
        resp = self.stub.PassTurn(pb.GameActionRequest(username=self.username, game_id=self.game_id))
        print(resp.message)

    def quit_game(self):
        if not self.game_id:
            print("Not in a game.")
            return
        resp = self.stub.QuitGame(pb.GameActionRequest(username=self.username, game_id=self.game_id))
        print(resp.message)
        self.game_id = None

    def run(self):
        if not self.login():
            return

        try:
            while True:
                print("\nOptions:")
                print("1. Start Match")
                print("2. Accept Match")
                print("3. View Game State")
                print("4. Play Card")
                print("5. Pass Turn")
                print("6. Quit Game")
                print("7. Logout and Exit")

                choice = input("Choose option: ")
                if choice == "1":
                    self.start_match()
                elif choice == "2":
                    self.accept_match()
                elif choice == "3":
                    self.get_game_state()
                elif choice == "4":
                    self.play_card()
                elif choice == "5":
                    self.pass_turn()
                elif choice == "6":
                    self.quit_game()
                elif choice == "7":
                    self.logout()
                    break
                else:
                    print("Invalid option.")
        except KeyboardInterrupt:
            self.logout()

if __name__ == "__main__":
    args = parse_args()
    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    client = CardGameClient(channel)
    client.run()

# python client.py --host=192.168.1.10 --port=50051

