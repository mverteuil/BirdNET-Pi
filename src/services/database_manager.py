import sqlite3


class DatabaseManager:
    def __init__(self, db_path: str = "./scripts/birds.db"):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = (
                sqlite3.Row
            )  # Return rows as dictionary-like objects
            print(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            print(f"Error connecting to database: {e}")

    def disconnect(self):
        if self.conn:
            self.conn.close()
            print("Disconnected from database.")

    def execute_query(self, query: str, params: tuple = ()):
        if not self.conn:
            self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            self.conn.commit()
            return cursor
        except sqlite3.Error as e:
            print(f"Error executing query: {e}")
            return None

    def fetch_all(self, query: str, params: tuple = ()):
        cursor = self.execute_query(query, params)
        if cursor:
            return cursor.fetchall()
        return []

    def fetch_one(self, query: str, params: tuple = ()):
        cursor = self.execute_query(query, params)
        if cursor:
            return cursor.fetchone()
        return None
