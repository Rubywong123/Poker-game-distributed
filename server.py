import grpc
from concurrent import futures
import time
import threading
import uuid
import random
import socket
import card_game_pb2 as pb
import card_game_pb2_grpc as stub
from storage import Storage
from session import GameSession


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
        self.match_results = {}
        self.online_users = {}
        self.active_games = {}  # game_id -> GameSession

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

        if request.username in self.match_results:
            game_id = self.match_results.pop(request.username)
            return pb.Response(status="success", message=f"Game ready! ID: {game_id}")

        if request.username not in self.match_queue[num]:
            self.match_queue[num].append(request.username)

        if len(self.match_queue[num]) == num:
            players = self.match_queue[num]
            self.match_queue[num] = []
            game_id = str(uuid.uuid4())[:8]

            self.active_games[game_id] = GameSession(game_id, players)

            for player in players:
                self.match_results[player] = game_id

        return pb.Response(status="waiting", message="Waiting for more players...")

    def AcceptMatch(self, request, context):
        if request.game_id not in self.active_games:
            return pb.Response(status="error", message="Invalid game ID")
        if request.username not in self.active_games[request.game_id].players:
            return pb.Response(status="error", message="User not in this game")
        return pb.Response(status="success", message="Joined game")

    def PlayCard(self, request, context):
        session = self.active_games.get(request.game_id)
        if not session:
            return pb.Response(status="error", message="Game not found")

        success, msg = session.play_cards(request.username, list(request.cards))
        return pb.Response(status="success" if success else "error", message=msg)

    def PassTurn(self, request, context):
        session = self.active_games.get(request.game_id)
        if not session:
            return pb.Response(status="error", message="Game not found")

        success, msg = session.pass_turn(request.username)
        return pb.Response(status="success" if success else "error", message=msg)

    def QuitGame(self, request, context):
        session = self.active_games.get(request.game_id)
        if not session:
            return pb.Response(status="error", message="Game not found")

        session.quit_game(request.username)
        return pb.Response(status="success", message="You quit and received a loss")

    def GetGameState(self, request, context):
        session = self.active_games.get(request.game_id)
        if not session:
            return pb.GameStateResponse(status="error", message="Invalid game ID")

        state = session.get_game_state()
        players = []
        for user in state["players"]:
            hand = state["hands"].get(user, [])
            players.append(pb.PlayerInfo(
                username=user,
                card_count=len(hand),
                cards=hand if user == request.username else [],
                win_rate=self.storage.get_win_rate(user),
                is_connected=True,
                is_current_turn=(user == state["current_turn"])
            ))

        return pb.GameStateResponse(
            status="success",
            message="Fetched",
            current_turn=state["current_turn"],
            last_played_cards=state["last_played"],
            players=players,
            countdown_seconds=state["countdown_seconds"],
            game_over=bool(state["winner"]),
            winner=state["winner"] or ""
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