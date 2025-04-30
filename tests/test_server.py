import grpc
import pytest
import threading
import time
import os
import sys
from concurrent import futures
from google.protobuf.empty_pb2 import Empty
from unittest.mock import MagicMock, patch


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import card_game_pb2 as pb
import card_game_pb2_grpc as stub
from server import CardGameService, GameSession
from storage import Storage

TEST_PORT = 60051
TEST_DB = f"cardgame-{TEST_PORT}.db"

TEST_USERNAME_1 = "alice2"
TEST_USERNAME_2 = "bob2"
TEST_GAME_ID = None


@pytest.fixture(scope="module")
def grpc_server():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = CardGameService(port=TEST_PORT, is_leader=True, replica_addresses=[])
    stub.add_CardGameServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"0.0.0.0:{TEST_PORT}")
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    time.sleep(1) 
    yield servicer 
    server.stop(0)
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

@pytest.fixture
def stub_client():
    channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
    return stub.CardGameServiceStub(channel)

def test_login(grpc_server, stub_client):
    resp = stub_client.Login(pb.LoginRequest(username="alice", password="pass123"))
    assert resp.status == "success"

def test_start_match(grpc_server, stub_client):
    stub_client.Login(pb.LoginRequest(username="alice2", password="pass"))
    stub_client.Login(pb.LoginRequest(username="bob2", password="pass"))

    stub_client.StartMatch(pb.MatchRequest(username="alice2", num_players=2))

    game_id = None
    for _ in range(10):
        time.sleep(0.3)
        resp = stub_client.StartMatch(pb.MatchRequest(username="bob2", num_players=2))
        if resp.status == "success":
            assert "Game ready!" in resp.message
            game_id = resp.message.split("ID: ")[1].strip()
            break
    assert game_id is not None

    global TEST_GAME_ID
    TEST_GAME_ID = game_id


def test_play_card_and_get_state(grpc_server, stub_client):
    global TEST_GAME_ID
    state = stub_client.GetGameState(pb.GameStateRequest(game_id=TEST_GAME_ID, username=TEST_USERNAME_1))
    assert state.status == "success"
    assert state.current_turn in [TEST_USERNAME_1, TEST_USERNAME_2]

    if state.current_turn == TEST_USERNAME_1:
        cards = next(p.cards for p in state.players if p.username == TEST_USERNAME_1)
    else:
        cards = next(p.cards for p in state.players if p.username == TEST_USERNAME_2)

    play = stub_client.PlayCard(pb.PlayCardRequest(
        username=state.current_turn,
        game_id=TEST_GAME_ID,
        cards=cards[:1]
    ))
    assert play.status == "success"

def test_pass_turn(grpc_server, stub_client):
    global TEST_GAME_ID
    state = stub_client.GetGameState(pb.GameStateRequest(game_id=TEST_GAME_ID, username=TEST_USERNAME_1))
    current = state.current_turn

    resp = stub_client.PassTurn(pb.GameActionRequest(username=current, game_id=TEST_GAME_ID))
    assert resp.status == "success"
    assert "passed" in resp.message or "starts a new round" in resp.message

def test_quit_game_and_check_winner(grpc_server, stub_client):
    global TEST_GAME_ID
    state = stub_client.GetGameState(pb.GameStateRequest(game_id=TEST_GAME_ID, username=TEST_USERNAME_1))
    other = TEST_USERNAME_1 if state.current_turn != TEST_USERNAME_1 else TEST_USERNAME_2

    resp = stub_client.QuitGame(pb.GameActionRequest(username=other, game_id=TEST_GAME_ID))
    assert resp.status == "success"
    assert "quit the game" in resp.message

    state2 = stub_client.GetGameState(pb.GameStateRequest(game_id=TEST_GAME_ID, username=TEST_USERNAME_1))
    assert state2.game_over
    assert state2.winner != other

def test_logout_and_relogin(grpc_server, stub_client):
    resp = stub_client.Logout(pb.LogoutRequest(username=TEST_USERNAME_1))
    assert resp.status == "success"

    relog = stub_client.Login(pb.LoginRequest(username=TEST_USERNAME_1, password="pass"))
    assert relog.status == "success"

def test_who_is_leader(grpc_server, stub_client):
    resp = stub_client.WhoIsLeader(Empty())
    assert resp.is_leader
    assert resp.leader_address.endswith(str(TEST_PORT))

def test_append_log(grpc_server, stub_client):
    fake_command = {
        "type": "play_card",
        "username": TEST_USERNAME_1,
        "game_id": TEST_GAME_ID,
        "cards": [1]
    }
    entry = pb.LogEntry(index=999, command="play_card", payload=str(fake_command))
    resp = stub_client.AppendLog(entry)
    assert resp.status == "success"

def test_register_replica(grpc_server):
    resp = grpc_server.RegisterReplica(pb.RegisterReplicaRequest(replica_address="127.0.0.1:60052"), None)
    assert resp.status == "success"

def test_update_replica_list(grpc_server):
    addresses = ["127.0.0.1:60052", "127.0.0.1:60053"]
    payload = pb.ReplicaListUpdateRequest(replica_addresses_json='["127.0.0.1:60052", "127.0.0.1:60053"]')
    resp = grpc_server.UpdateReplicaList(payload, None)
    assert resp.status == "success"
    assert grpc_server.replica_addresses == addresses

def test_sync_all_games(grpc_server, stub_client):
    resp = stub_client.SyncAllGames(Empty())
    assert resp.status == "success"

def test_delete_account(grpc_server, stub_client):
    stub_client.Login(pb.LoginRequest(username="user_del", password="pwd"))
    resp = stub_client.DeleteAccount(pb.DeleteAccountRequest(username="user_del", password="pwd"))
    assert resp.status == "success"

def test_start_match_not_leader():
    from server import CardGameService
    follower = CardGameService(port=60052, is_leader=False, leader_address="127.0.0.1:60051")
    request = pb.MatchRequest(username="test", num_players=2)
    resp = follower.StartMatch(request, None)
    assert resp.status == "error"

def test_request_vote_lower_term(grpc_server):
    grpc_server.current_term = 5
    grpc_server.voted_for = None
    request = pb.VoteRequest(term=3, candidate_id="nodeA")
    context = None
    resp = grpc_server.RequestVote(request, context)
    assert not resp.vote_granted
    assert resp.term == 5

def test_request_vote_grant(grpc_server):
    grpc_server.current_term = 3
    grpc_server.voted_for = None
    request = pb.VoteRequest(term=4, candidate_id="nodeA")
    context = None
    resp = grpc_server.RequestVote(request, context)
    assert resp.vote_granted
    assert grpc_server.voted_for == "nodeA"
    assert grpc_server.state == "follower"
    assert grpc_server.current_term == 4

def test_request_vote_already_voted_for_other(grpc_server):
    grpc_server.current_term = 4
    grpc_server.voted_for = "nodeB"
    request = pb.VoteRequest(term=4, candidate_id="nodeA")
    context = None
    resp = grpc_server.RequestVote(request, context)
    assert not resp.vote_granted
    assert resp.term == 4

def test_announce_leader(grpc_server):
    request = pb.CoordinatorMessage(new_leader_address="127.0.0.1:12345")
    context = None

    response = grpc_server.AnnounceLeader(request, context)

    assert response.status == "success"
    assert response.message == "Leader updated."
    assert grpc_server.leader_address == "127.0.0.1:12345"
    assert isinstance(grpc_server.leader_stub, stub.CardGameServiceStub)
    assert grpc_server.is_leader is False
    assert grpc_server.state == "follower"

def test_apply_command_play_card(grpc_server):
    session = GameSession("testgame", ["alice", "bob"])
    grpc_server.active_games["testgame"] = session
    session.hands["alice"] = [3]
    session.current_turn_index = 0

    command = {
        "type": "play_card",
        "username": "alice",
        "game_id": "testgame",
        "cards": [3]
    }
    success, msg = grpc_server.apply_command(command)
    assert success
    assert "won the game" in msg or "successfully" in msg


def test_apply_command_pass_turn(grpc_server):
    session = GameSession("testgame2", ["alice", "bob"])
    grpc_server.active_games["testgame2"] = session

    command = {
        "type": "pass_turn",
        "username": "alice",
        "game_id": "testgame2"
    }
    success, msg = grpc_server.apply_command(command)
    assert success
    assert "passed" in msg or "starts a new round" in msg


def test_apply_command_quit_game(grpc_server):
    session = GameSession("testgame3", ["alice", "bob"])
    grpc_server.active_games["testgame3"] = session

    command = {
        "type": "quit_game",
        "username": "bob",
        "game_id": "testgame3"
    }
    success, msg = grpc_server.apply_command(command)
    assert success
    assert "quit" in msg


def test_apply_command_unknown_type(grpc_server):
    session = GameSession("testgame4", ["alice", "bob"])
    grpc_server.active_games["testgame4"] = session

    command = {
        "type": "invalid_type",
        "username": "alice",
        "game_id": "testgame4"
    }
    success, msg = grpc_server.apply_command(command)
    assert not success
    assert msg == "Unknown command"


def test_apply_command_game_not_found(grpc_server):
    command = {
        "type": "pass_turn",
        "username": "ghost",
        "game_id": "nonexistent"
    }
    success, msg = grpc_server.apply_command(command)
    assert not success
    assert msg == "Game not found"

def test_initiate_election_wins(grpc_server):
    grpc_server.replica_addresses = ["127.0.0.1:9999", "127.0.0.1:8888"]

    with patch("server.stub.CardGameServiceStub") as mock_stub_cls:
        mock_stub = MagicMock()
        mock_stub.RequestVote.return_value = pb.VoteResponse(term=1, vote_granted=True)
        mock_stub_cls.return_value = mock_stub

        grpc_server.initiate_election()

        assert grpc_server.is_leader is True
        assert grpc_server.state == "leader"

def test_forward_to_leader_successful_forward(grpc_server):
    grpc_server.is_leader = False

    mock_stub = MagicMock()
    mock_stub.FakeRPC.return_value = pb.Response(status="success", message="Handled by leader")
    grpc_server.leader_stub = mock_stub

    response = grpc_server.forward_to_leader("FakeRPC", pb.LoginRequest())
    assert response.status == "success"
    assert response.message == "Handled by leader"
