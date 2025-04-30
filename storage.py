import sqlite3
import bcrypt
import threading

class Storage:
    def __init__(self, db_name):
        self.db_name = db_name
        self.local = threading.local()
        self.initialize_database()

    def get_connection(self):
        if not hasattr(self.local, "conn"):
            self.local.conn = sqlite3.connect(self.db_name, check_same_thread=False)
            self.local.conn.row_factory = sqlite3.Row
        return self.local.conn

    def initialize_database(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash BLOB NOT NULL,
                num_win INTEGER DEFAULT 0,
                num_lost INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                status TEXT,            
                current_turn TEXT,     
                winner TEXT        
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_players (
                game_id TEXT,
                username TEXT,
                cards TEXT,   
                is_connected INTEGER DEFAULT 1,
                PRIMARY KEY (game_id, username),
                FOREIGN KEY (game_id) REFERENCES games(game_id),
                FOREIGN KEY (username) REFERENCES users(username)
            )
        """)
        conn.commit()
        conn.close()

    def execute_query(self, query, params=(), commit=False):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit()
        return cursor

    def login_register_user(self, username, password):
        cursor = self.execute_query("SELECT password_hash FROM users WHERE username=?", (username,))
        user = cursor.fetchone()
        if user:
            if bcrypt.checkpw(password.encode(), user[0]):
                return {"status": "success"}
            return {"status": "error", "message": "Invalid credentials"}
        else:
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            self.execute_query(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
                commit=True
            )
            return {"status": "success"}

    def create_game(self, game_id):
        self.execute_query(
            "INSERT INTO games (game_id, status) VALUES (?, 'waiting')",
            (game_id,),
            commit=True
        )
        return {"status": "success"}

    def add_player_to_game(self, game_id, username, cards):
        self.execute_query(
            "INSERT INTO game_players (game_id, username, cards) VALUES (?, ?, ?)",
            (game_id, username, ','.join(map(str, cards))),
            commit=True
        )
        return {"status": "success"}

    def update_cards(self, game_id, username, cards):
        self.execute_query(
            "UPDATE game_players SET cards=? WHERE game_id=? AND username=?",
            (','.join(map(str, cards)), game_id, username),
            commit=True
        )

    def update_game_turn(self, game_id, current_turn):
        self.execute_query(
            "UPDATE games SET current_turn=? WHERE game_id=?",
            (current_turn, game_id),
            commit=True
        )

    def declare_winner(self, game_id, winner):
        self.execute_query(
            "UPDATE games SET status='finished', winner=? WHERE game_id=?",
            (winner, game_id),
            commit=True
        )
        self.execute_query(
            "UPDATE users SET num_win = num_win + 1 WHERE username=?",
            (winner,),
            commit=True
        )
        self.execute_query(
            "UPDATE users SET num_lost = num_lost + 1 WHERE username IN (SELECT username FROM game_players WHERE game_id=? AND username != ?)",
            (game_id, winner),
            commit=True
        )

    def get_game_state(self, game_id):
        cursor = self.execute_query("SELECT * FROM games WHERE game_id=?", (game_id,))
        game = cursor.fetchone()
        players_cursor = self.execute_query("SELECT username, cards, is_connected FROM game_players WHERE game_id=?", (game_id,))
        players = players_cursor.fetchall()
        return {
            "game": dict(game) if game else None,
            "players": [dict(row) for row in players]
        }
    
    def get_win_rate(self, username):
        cursor = self.execute_query("SELECT num_win, num_lost FROM users WHERE username=?", (username,))
        row = cursor.fetchone()
        if row:
            wins, losses = row["num_win"], row["num_lost"]
            total = wins + losses
            return wins / total if total > 0 else 0.0
        return 0.0

    def quit_game(self, game_id, username):
        """Handles a player quitting the game."""
        self.execute_query(
            "UPDATE game_players SET is_connected=0 WHERE game_id=? AND username=?",
            (game_id, username),
            commit=True
        )
        self.execute_query(
            "UPDATE users SET num_lost = num_lost + 1 WHERE username=?",
            (username,),
            commit=True
        )

        return {"status": "success", "message": f"{username} quit the game and received a loss."}

    def delete_account(self, username, password):
        cursor = self.execute_query("SELECT password_hash FROM users WHERE username=?", (username,))
        row = cursor.fetchone()
        if row:
            if bcrypt.checkpw(password.encode(), row["password_hash"]):
                self.execute_query("DELETE FROM users WHERE username=?", (username,), commit=True)
                return {"status": "success", "message": "Account deleted"}
            else:
                return {"status": "error", "message": "Incorrect password"}
        return {"status": "error", "message": "User not found"}
