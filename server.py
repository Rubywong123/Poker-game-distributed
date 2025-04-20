import grpc
from concurrent import futures
import time
import threading
import queue
import uuid
import random
import socket
import card_game_pb2 as pb
import card_game_pb2_grpc as stub
from storage import Storage


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class CardGameService(stub.CardGameServiceServicer):
    def __init__(self, port, is_leader=False, leader_address=None, replica_addresses=None):
        self.port = port
        self.ip = get_local_ip()
        self.is_leader = is_leader
        self.leader_address = leader_address
        self.replica_addresses = replica_addresses or []
        self.replicas = []
        self.storage = Storage(f"cardgame-{port}.db")

        self.match_queue = {2: [], 3: [], 4: []}
        self.active_games = {}
        self.online_users = {}

        if self.is_leader:
            self.replicas = [stub.CardGameServiceStub(grpc.insecure_channel(addr)) for addr in self.replica_addresses]
        else:
            self.leader_channel = grpc.insecure_channel(self.leader_address)
            self.leader_stub = stub.CardGameServiceStub(self.leader_channel)

        threading.Thread(target=self.monitor_heartbeat, daemon=True).start()

    def monitor_heartbeat(self):
        while True:
            if self.is_leader:
                for i, replica in enumerate(self.replicas):
                    try:
                        replica.Heartbeat(pb.HeartbeatRequest())
                    except grpc.RpcError:
                        print(f"[Leader] Replica at {self.replica_addresses[i]} is down.")
            else:
                try:
                    self.leader_stub.Heartbeat(pb.HeartbeatRequest())
                except grpc.RpcError:
                    print("[Replica] Leader is down. Needs election handling here.")
            time.sleep(3)

    def Heartbeat(self, request, context):
        return pb.Response(status="alive", message="Heartbeat OK")

    def WhoIsLeader(self, request, context):
        return pb.LeaderInfoResponse(
            leader_address=f"{self.ip}:{self.port}" if self.is_leader else self.leader_address,
            is_leader=self.is_leader
        )

    def Login(self, request, context):
        response = self.storage.login_register_user(request.username, request.password)
        if response["status"] == "success":
            self.online_users[request.username] = True
        return pb.Response(status=response["status"], message=response.get("message", ""))

    def Logout(self, request, context):
        self.online_users.pop(request.username, None)
        return pb.Response(status="success", message="User logged out.")

    def DeleteAccount(self, request, context):
        response = self.storage.delete_account(request.username, request.password)
        self.online_users.pop(request.username, None)
        return pb.Response(status=response["status"], message=response["message"])

    def StartMatch(self, request, context):
        if not self.is_leader:
            return pb.Response(status="error", message="Only leader can start matches")

        num = request.num_players
        if num not in self.match_queue:
            return pb.Response(status="error", message="Invalid player count")

        self.match_queue[num].append((request.username, context))

        if len(self.match_queue[num]) == num:
            game_id = str(uuid.uuid4())[:8]
            players = [entry[0] for entry in self.match_queue[num]]
            response_contexts = [entry[1] for entry in self.match_queue[num]]
            self.match_queue[num] = []

            cards = list(range(10)) * 4
            random.shuffle(cards)
            hands = [cards[i::num] for i in range(num)]

            for i, player in enumerate(players):
                self.storage.add_player_to_game(game_id, player, hands[i])

            self.active_games[game_id] = {
                "players": players,
                "turn_index": 0,
                "last_played": [],
                "countdown": 20,
                "start_time": time.time(),
                "winner": None
            }

            self.storage.create_game(game_id)
            self.storage.update_game_turn(game_id, players[0])

            for ctx in response_contexts:
                ctx.set_trailing_metadata((('game-id', game_id),))

            return pb.Response(status="success", message=f"Game ready! ID: {game_id}")

        return pb.Response(status="waiting", message="Waiting for more players...")

    def AcceptMatch(self, request, context):
        state = self.active_games.get(request.game_id)
        if not state:
            return pb.Response(status="error", message="Invalid game ID")
        if request.username not in state["players"]:
            return pb.Response(status="error", message="User not in this game")
        return pb.Response(status="success", message="Joined game")

    def PlayCard(self, request, context):
        if not self.is_leader:
            return pb.Response(status="error", message="Only leader handles card play")

        game_id, user, cards = request.game_id, request.username, request.cards
        state = self.active_games.get(game_id)
        if not state:
            return pb.Response(status="error", message="Invalid game")

        current = state["players"][state["turn_index"]]
        if user != current:
            return pb.Response(status="error", message="Not your turn")

        hand = self.storage.get_cards(game_id, user)
        if not all(card in hand for card in cards):
            return pb.Response(status="error", message="Invalid card play")

        for c in cards:
            hand.remove(c)
        self.storage.update_cards(game_id, user, hand)
        state["last_played"] = cards

        if len(hand) == 0:
            self.storage.declare_winner(game_id, user)
            state["winner"] = user
        else:
            state["turn_index"] = (state["turn_index"] + 1) % len(state["players"])
            self.storage.update_game_turn(game_id, state["players"][state["turn_index"]])
            state["start_time"] = time.time()
        return pb.Response(status="success", message="Card played")

    def PassTurn(self, request, context):
        if not self.is_leader:
            return pb.Response(status="error", message="Only leader handles pass turn")

        game_id, user = request.game_id, request.username
        state = self.active_games.get(game_id)
        if not state or state["players"][state["turn_index"]] != user:
            return pb.Response(status="error", message="Not your turn")

        state["turn_index"] = (state["turn_index"] + 1) % len(state["players"])
        self.storage.update_game_turn(game_id, state["players"][state["turn_index"]])
        state["start_time"] = time.time()
        return pb.Response(status="success", message="Passed turn")

    def QuitGame(self, request, context):
        if not self.is_leader:
            return pb.Response(status="error", message="Only leader handles quit game")

        game_id, user = request.game_id, request.username
        self.storage.quit_game(game_id, user)
        return pb.Response(status="success", message="You quit and received a loss")

    def GetGameState(self, request, context):
        data = self.storage.get_game_state(request.game_id)
        if not data["game"]:
            return pb.GameStateResponse(status="error", message="Invalid game ID")

        g = data["game"]
        players = []
        for p in data["players"]:
            win_rate = self.storage.get_win_rate(p["username"])
            players.append(pb.PlayerInfo(
                username=p["username"],
                card_count=len(p["cards"].split(",")) if p["cards"] else 0,
                cards=[int(c) for c in p["cards"].split(",")] if p["username"] == g["current_turn"] else [],
                win_rate=win_rate,
                is_connected=bool(p["is_connected"]),
                is_current_turn=(p["username"] == g["current_turn"])
            ))

        state = self.active_games.get(request.game_id, {})
        countdown = max(0, int(20 - (time.time() - state.get("start_time", 0))))

        return pb.GameStateResponse(
            status="success",
            message="Game fetched",
            current_turn=g["current_turn"],
            last_played_cards=state.get("last_played", []),
            players=players,
            countdown_seconds=countdown,
            game_over=g["status"] == "finished",
            winner=g.get("winner", "")
        )


def serve(is_leader=False, leader_address=None, replica_addresses=None, port=50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    card_service = CardGameService(
        port=port,
        is_leader=is_leader,
        leader_address=leader_address,
        replica_addresses=replica_addresses
    )
    stub.add_CardGameServiceServicer_to_server(card_service, server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    print(f"Starting {'leader' if is_leader else 'replica'} server on port {port}...")
    server.start()
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.stop(0)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--leader', action='store_true', help="Run as leader")
    parser.add_argument('--port', type=int, default=50051)
    parser.add_argument('--leader_address', type=str, default="127.0.0.1:50051")
    parser.add_argument('--replicas', nargs='*', default=[])
    args = parser.parse_args()

    serve(
        is_leader=args.leader,
        leader_address=args.leader_address,
        replica_addresses=args.replicas,
        port=args.port
    )
