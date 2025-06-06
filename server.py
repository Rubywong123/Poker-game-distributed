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
from google.protobuf.empty_pb2 import Empty
import json

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

        if not self.is_leader:
            try:
                self.leader_stub.RegisterReplica(pb.RegisterReplicaRequest(
                    replica_address=f"{self.ip}:{self.port}"
                ))
                print(f"[Replica] Registered self to leader at {self.leader_address}")
                
                response = self.leader_stub.SyncDatabase(Empty())
                if response.status == "success":
                    with open(self.storage.db_name, "wb") as f:
                        f.write(response.database_dump)
                    print(f"[Replica] Synced database from leader.")
                else:
                    print("[Replica] Failed to sync database.")
            except grpc.RpcError as e:
                print(f"[Replica] Failed to register to leader: {e}")


        # log entry
        self.log = []
        self.commit_index = -1
        self.next_log_index = 0

        # Raft state
        self.current_term = 0
        self.voted_for = None
        self.state = "follower" 
        self.last_heartbeat = time.time()
        self.election_timeout = random.uniform(3, 5)

        threading.Thread(target=self.monitor_heartbeat, daemon=True).start()

    def monitor_heartbeat(self):
        while True:
            if self.is_leader:
                to_remove = []
                for i, replica in enumerate(self.replicas):
                    try:
                        replica.Heartbeat(pb.HeartbeatRequest())
                    except grpc.RpcError:
                        print(f"[Leader] Replica at {self.replica_addresses[i]} is down.")
                        to_remove.append(i)
                # Remove dead replicas
                for idx in sorted(to_remove, reverse=True):
                    del self.replica_addresses[idx]
                    del self.replicas[idx]

                if to_remove:
                    self.broadcast_replica_list()

            else:
                try:
                    self.leader_stub.Heartbeat(pb.HeartbeatRequest())
                except grpc.RpcError:
                    print("[Replica] Leader is down. Needs election handling here.")
                    self.initiate_election()

                self.pull_games_from_leader()
            time.sleep(3)

    def replicate_and_apply(self, command):
        """
        Leader: append command to log, replicate to followers, commit if majority ACKs.
        """
        if not self.is_leader:
            return False, "Not the leader"

        entry = (self.next_log_index, command)
        self.log.append(entry)
        self.next_log_index += 1
        # count self
        acks = 1

        for replica in self.replicas:
            try:
                replica.AppendLog(pb.LogEntry(index=entry[0], command=command["type"], payload=str(command)))
                acks += 1
            except grpc.RpcError:
                pass  # log failure

        # quorum
        if acks >= (len(self.replicas) + 1) // 2 + 1:
            self.commit_index = entry[0]
            return self.apply_command(command)
        else:
            return False, "Failed to replicate"
        
    def apply_command(self, command):
        game_id = command["game_id"]
        session = self.active_games.get(game_id)
        if not session:
            return False, "Game not found"

        if command["type"] == "play_card":
            success, msg = session.play_cards(command["username"], command["cards"])
        elif command["type"] == "pass_turn":
            success, msg = session.pass_turn(command["username"])
        elif command["type"] == "quit_game":
            success, msg = session.quit_game(command["username"])
        else:
            return False, "Unknown command"

        if session.winner:
            self.storage.declare_winner(game_id, session.winner)

        return success, msg 
    
    def _persist_game(self, game_id, session: GameSession):
        self.storage.create_game(game_id)
        for player in session.players:
            self.storage.add_player_to_game(
                game_id,
                player,
                session.hands[player]
            )



    def forward_to_leader(self, rpc_name, request):
        if self.is_leader:
            return getattr(self, rpc_name)(request)

        try:
            stub_fn = getattr(self.leader_stub, rpc_name)
            return stub_fn(request)
        except grpc.RpcError:
            return pb.Response(status="error", message="Leader unavailable")
        
    def initiate_election(self):
        self.state = "candidate"
        self.current_term += 1
        self.voted_for = f"{self.ip}:{self.port}"
        votes = 1
        majority = (len(self.replica_addresses) + 1) // 2 + 1

        for addr in self.replica_addresses:
            try:
                replica_stub = stub.CardGameServiceStub(grpc.insecure_channel(addr))
                res = replica_stub.RequestVote(pb.VoteRequest(term=self.current_term, candidate_id=f"{self.ip}:{self.port}"))
                if res.vote_granted:
                    votes += 1
            except grpc.RpcError:
                continue

        if votes >= majority:
            print(f"[Election] Won with {votes} votes. Becoming leader.")
            self.become_leader()
        else:
            print(f"[Election] Lost with {votes} votes.")
            self.state = "follower"

    def become_leader(self):
        self.is_leader = True
        self.state = "leader"
        self.voted_for = None
        self.last_heartbeat = time.time()

        for addr in self.replica_addresses:
            try:
                replica_stub = stub.CardGameServiceStub(grpc.insecure_channel(addr))
                replica_stub.AnnounceLeader(pb.CoordinatorMessage(new_leader_address=f"{self.ip}:{self.port}"))
                self.leader_address = f"{self.ip}:{self.port}"
                self.leader_stub = None
            except grpc.RpcError:
                continue
        
        self.broadcast_replica_list()

    def pull_games_from_leader(self):
        if self.is_leader:
            return

        try:
            res = self.leader_stub.SyncAllGames(Empty())
            if res.status == "success":
                games_data = json.loads(res.message)
                self.active_games.clear()
                for gid, session_dict in games_data.items():
                    self.active_games[gid] = GameSession.deserialize(session_dict)
                print("[Replica] Synced games from leader.")
        except grpc.RpcError as e:
            print(f"[Replica] Failed to pull games from leader: {e}")


    def Heartbeat(self, request, context):
        return pb.Response(status="alive", message="Heartbeat OK")
    
    def RegisterReplica(self, request, context):
        if not self.is_leader:
            return pb.Response(status="error", message="Not the leader")

        new_replica_address = request.replica_address
        print(f"[Leader] Registering new replica: {new_replica_address}")

        if new_replica_address not in self.replica_addresses:
            self.replica_addresses.append(new_replica_address)
            self.replicas.append(stub.CardGameServiceStub(grpc.insecure_channel(new_replica_address)))
            self.broadcast_replica_list(exclude_address=new_replica_address)


        return pb.Response(status="success", message="Replica registered.")

    def UpdateReplicaList(self, request, context):
        new_list = json.loads(request.replica_addresses_json)
        
        # remove if the new list contains its own address
        if f"{self.ip}:{self.port}" in new_list:
            new_list.remove(f"{self.ip}:{self.port}")

        print(f"[Replica] Updating replica list: {new_list}")
        self.replica_addresses = new_list
        return pb.Response(status="success", message="Replica list updated.")

    def broadcast_replica_list(self, exclude_address=None):
        
        replica_list_json = json.dumps(self.replica_addresses)

        for addr in self.replica_addresses:
            if addr == exclude_address:
                continue  # Skip the newly joined replica

            try:
                replica_stub = stub.CardGameServiceStub(grpc.insecure_channel(addr))
                replica_stub.UpdateReplicaList(pb.ReplicaListUpdateRequest(replica_addresses_json=replica_list_json))
            except grpc.RpcError as e:
                print(f"[Leader] Failed to update replica {addr}: {e}")



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
    
    def AppendLog(self, request, context):
        command = eval(request.payload) 
        self.log.append((request.index, command))

        if request.index > self.commit_index:
            self.commit_index = request.index
            self.apply_command(command)
        return pb.Response(status="success", message="Appended")

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
            session = GameSession(game_id, players)

            self.active_games[game_id] = GameSession(game_id, players)
            self._persist_game(game_id, session)

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
        if not self.is_leader:
            return self.forward_to_leader("PlayCard", request)

        command = {
            "type": "play_card",
            "username": request.username,
            "game_id": request.game_id,
            "cards": list(request.cards)
        }
        success, msg = self.replicate_and_apply(command)
        return pb.Response(status="success" if success else "error", message=msg)

    def PassTurn(self, request, context):
        if not self.is_leader:
            return self.leader_stub.PassTurn(request)

        session = self.active_games.get(request.game_id)
        if not session:
            return pb.Response(status="error", message="Game not found")

        success, msg = session.pass_turn(request.username)

        if success:
            # replicate to replicas
            for replica in self.replicas:
                try:
                    replica.PassTurn(request)
                except grpc.RpcError as e:
                    print(f"[Replication] Failed to replicate PassTurn to replica: {e}")

        return pb.Response(status="success" if success else "error", message=msg)


    def QuitGame(self, request, context):
        if not self.is_leader:
            return self.leader_stub.QuitGame(request)

        session = self.active_games.get(request.game_id)
        if not session:
            return pb.Response(status="error", message="Game not found")

        success, msg = session.quit_game(request.username)
        if success:
            self.storage.quit_game(request.game_id, request.username)

            if session.winner:
                self.storage.declare_winner(request.game_id, session.winner)

            for replica in self.replicas:
                try:
                    replica.QuitGame(request)
                except grpc.RpcError as e:
                    print(f"[Replication] Failed to replicate QuitGame: {e}")

        return pb.Response(status="success" if success else "error", message=msg)



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
    
    def SyncAllGames(self, request, context):
        if not self.is_leader:
            return pb.SyncResponse(status="error", message="Not leader")

        games_data = {gid: session.serialize() for gid, session in self.active_games.items()}
        return pb.SyncResponse(
            status="success",
            # send as a JSON string
            message=json.dumps(games_data)
        )
    
    def SyncDatabase(self, request, context):
        if not self.is_leader:
            return pb.SyncDatabaseResponse(status="error", database_dump=b"")

        with open(self.storage.db_name, "rb") as f:
            db_bytes = f.read()
        return pb.SyncDatabaseResponse(status="success", database_dump=db_bytes)


    
    def RequestVote(self, request, context):
        if request.term < self.current_term:
            return pb.VoteResponse(term=self.current_term, vote_granted=False)

        if self.voted_for is None or self.voted_for == request.candidate_id:
            self.voted_for = request.candidate_id
            self.current_term = request.term
            self.state = "follower"
            return pb.VoteResponse(term=self.current_term, vote_granted=True)

        return pb.VoteResponse(term=self.current_term, vote_granted=False)


    def AnnounceLeader(self, request, context):
        print(f"[Election] New leader announced: {request.new_leader_address}")
        self.leader_address = request.new_leader_address
        self.leader_channel = grpc.insecure_channel(self.leader_address)
        self.leader_stub = stub.CardGameServiceStub(self.leader_channel)
        self.is_leader = False
        self.state = "follower"
        return pb.Response(status="success", message="Leader updated.")


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