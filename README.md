# 🃏 Distributed Card Game System ♠️♦️
This is the final project for CS262: Introduction to Distributed Computing. This is a distributed, turn-based card game system that allows multiple players to connect and play from different machines. The game allows players to enjoy a simplified Poker-style card game with friends while practicing their card-playing strategies. Under the hood, the system maintains a consistent and synchronized game state across all nodes by implementing the Raft consensus algorithm. The architecture is fault-tolerant, capable of withstanding server failures without disrupting gameplay.

## Features

- **Leader-Follower Architecture:** Backend servers operate in either leader or follower mode. The leader handles all write operations and broadcasts state updates, while followers handle read requests, replicate the leader’s state, and monitor for failover.
- **Leader Election & Failover:** Followers perform heartbeat checks and automatically elect a new leader (highest port) upon failure.
- **Persistent Storage:** Each server maintains its own SQLite database. Followers sync state from the leader during startup and failover.
- **Real-time Messaging:** Online users receive messages instantly via streaming. Offline messages are stored and retrievable later.
- **GUI Frontend:** Users interact through a Tkinter-based GUI that supports sending/receiving messages, listing users, and account management.
- **Automatic Reconnection:** Upon leader failure, the client discovers the new leader via replicas and reconnects seamlessly.

## gRPC Overview

gRPC is used to define and implement all server-client and inter-replica communication:
- Remote procedures are defined in `chat.proto`.
- Streaming is used for real-time message delivery.
- Server replication and synchronization happen via `SyncData` and `Broadcast_Sync`.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Rubywong123/CS262-HW
   cd CS262-HW/HW4
   ```
2. Compile the protobuf definitions:
   ```bash
   python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat.proto
   ```
3. Start a leader server on port 50051:
   ```bash
   python server.py --leader --port 50051 --replicas 127.0.0.1:50052 127.0.0.1:50053
   ```
4. Start replica servers:
   ```bash
    python server.py --port 50052 --leader_address 127.0.0.1:50051
    python server.py --port 50053 --leader_address 127.0.0.1:50051
   ```
5. Run the GUI client:
   ```bash
   python gui.py --host 127.0.0.1 --port 50051
   ```

## Usage
- Launch the GUI and log in or register.
- Available GUI options:
    - Send Message: Sends message to another user (real-time if online).
    - Read Messages: Retrieve up to 10 recent messages.
    - List Accounts: View all user accounts.
    - Delete Message: Remove most recent message to a recipient.
    - Delete Account: Permanently delete your account.
- The client will monitor the backend cluster. If the leader fails, it queries replicas and reconnects to the new leader automatically.


## Design Highlights
- Each server has a ChatService class combining leader and follower logic, controlled by a boolean flag `is_leader`.
- Followers use heartbeat monitoring and StartElection to trigger failover.
- GUI listens for cluster changes using `ListenForServerInfo()` and recovers from failures by calling `WhoIsLeader()` across replicas.


## Test Covereage

To run the tests and generate a coverage report, use the following command:

```bash
pytest --cov=. tests/
```

The test coverage statistics for the codebase are as follows:

| File              | Statements | Missing | Coverage |
|------------------|------------|----------|------------|
| client.py        | 81         | 18       | 77%        |
| gui.py           | 199        | 47       | 76%        |
| server.py        | 232        | 59       | 75%        |
| storage.py       | 93         | 7        | 92%        |
| **TOTAL**        | **605**    | **131**   | **78%**    |

