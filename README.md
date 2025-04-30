# 🃏 Distributed Card Game System ♠️♦️
This is the final project for CS262: Introduction to Distributed Computing. It is a distributed, turn-based card game system that allows multiple players to connect and play from different machines. The game allows players to enjoy a simplified Poker-style card game with friends while practicing their card-playing strategies. Players connect to the system via a graphical user interface (GUI), which communicates with replicated backend servers. The game logic includes turn-taking, valid card combinations, and winning conditions. Players are notified of game events in real time, which creats a smooth and engaging multiplayer experience. Under the hood, the system maintains a consistent and synchronized game state across all nodes by implementing the Raft consensus algorithm. The architecture is fault-tolerant, capable of withstanding server failures without disrupting gameplay. 

## ✨ Features

- **Login Crendential** Users must log in with a username and password to join the game. Passwords are securely hashed before being stored in the SQLite database, ensuring that raw passwords are never saved in plain text.
- **User-Specified Game Participants:** Players can initiate a new game by specifying the number of participants, allowing flexibility in game setup based on user's preference.
- **Real-time Game State update:** The GUI polls the backend periodically to retrieve the most recent game state, including card hands, turns, timers, opponent stats, and win rates. This ensures a responsive and smooth user experience.
- **Leader-Follower Architecture:** The system adopts a centralized leadership model, where one server acts as the leader and others act as followers. The leader handles all game logic, state changes, and client updates. Followers replicate data from the leader and serve as standbys for failover. 
- **Leader Election & Failover:** When the leader becomes unreachable, followers detect this via heartbeat timeouts and trigger a Raft-style election so that a new leader is elected using a voting mechanism.
- **Persistent Storage:** Each server uses an independent SQLite database to persist user data and game metadata. On startup or leader change, followers request a full database sync from the leader. Win/loss records, user accounts, and ongoing game states are all persisted across restarts.

## 🕹️ Front-end Overview
- **Login Screen:** 
    - The landing page once the user starts the card game system. On the login page, users enter their username and password to access the game. New users can create an account by registering their credentials for the first time. This ensures that only authenticated players can participate in the game. 
- **Home Screen:** 
    - On the home page, users can choose their preferred game style by specifying the number of players. The system automatically matches users with the same preference into a game. Once the required number of players is met, the status changes from "waiting for more players" to entering the game.
- **Game Screen:** Once matched, players are transitioned to the game screen, which includes:
    - Opponent Panel: Shows each opponent's username, card count, and win rate.
    - Game Info Bar: Displays whose turn it is, the last played cards, and a countdown timer.
    - Your Cards Panel: Dynamically renders each player's hand with styled cards in a scrollable frame.
    - Control Panel: Provides input for playing cards, passing, or quitting the game.

## 📡 gRPC Overview

gRPC is used to define and implement all server-client and inter-replica communication:
- Remote procedures are defined in `card_game.proto`.
- Core gameplay (e.g. `PlayCard`, `GetGameState`) and matchmaking are handled via RPCs.
- Replication and coordination use `AppendLog`, `SyncAllGames`, and `Heartbeat` for Raft-based leader election and state syncing.

## ⚙️ Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Rubywong123/Poker-game-distributed.git
   ```
2. Compile the protobuf definitions:
   ```bash
   python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat.proto
   ```
3. Start a leader server on port 50051:
   ```bash
   python server.py --leader --port 50051
   ```
4. Start replica servers:
   ```bash
    python server.py --port 50052 --leader_address $LEADER_HOST:50051
    python server.py --port 50053 --leader_address $LEADER_HOST:50051
   ```
5. Run the GUI client:
   ```bash
   python gui.py --host $LEADER_HOST --port 50051
   ```


## 🎨 Design Highlights
- Each server runs a `CardGameService` class that unifies leader and follower roles, controlled by the is_leader flag.
- Followers monitor leader heartbeats and trigger Raft-style elections using `RequestVote` when the leader becomes unresponsive.
- The GUI handles failures by calling `WhoIsLeader()` across known replicas to reconnect to the current leader automatically.


## 📝 Test Covereage

To run the tests and generate a coverage report, use the following command:

```bash
pytest --cov=. tests/
```

The test coverage statistics for the codebase are as follows:

| File              | Statements | Missing | Coverage |
|------------------|------------|----------|------------|
| gui.py           | 308        | 103      | 67%        |
| server.py        | 344        | 70       | 80%        |
| session.py       | 145        | 23       | 84%        |
| storage.py       | 79         | 9        | 89%        |
| **TOTAL**        | **876**    | **205**   | **77%**    |

The test coverage for gui.py is lower than other files because it primarily contains UI-related functions such as `home_screen()`, which involve extensive use of stylized buttons and labels. Since these elements rely heavily on Tkinter’s layout system and visual rendering, they are less critical to cover with unit tests compared to core logic or backend functionality.

