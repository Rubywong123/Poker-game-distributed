import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import threading
import chat_pb2
import chat_pb2_grpc
import grpc
from argparse import ArgumentParser
from google.protobuf.empty_pb2 import Empty
import time

def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--host", default='127.0.0.1', help="Host address")
    parser.add_argument("--port", default=50051, help="Port number")
    return parser.parse_args()

class ChatGUI:
    def __init__(self, root, args):
        self.root = root
        self.root.title("Chat App")
        

        # gRPC channel and stub
        self.channel = grpc.insecure_channel(f"{args.host}:{args.port}")
        self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
        self.username = None
        self.password = None

        # add procedure to handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self.handle_close)
        self.replica_addresses = []

        # Show login screen first
        self.show_login_window()

        self.server_disconnected = threading.Event()
        threading.Thread(target=self.monitor_connection, daemon=True).start()

    def show_login_window(self):
        """Display login screen."""
        self.clear_window()
        self.root.title("Chat App")

        tk.Label(self.root, text="Username:").pack()
        self.username_entry = tk.Entry(self.root)
        self.username_entry.pack()

        tk.Label(self.root, text="Password:").pack()
        self.password_entry = tk.Entry(self.root, show="*")
        self.password_entry.pack()

        login_button = tk.Button(self.root, text="Login / Register", command=self.login)
        login_button.pack()

    def login(self):
        """Authenticate user and open chat window."""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            messagebox.showerror("Error", "Username and password cannot be empty")
            return

        response = self.stub.Login(chat_pb2.LoginRequest(username=username, password=password))

        if response.status == "success":
            self.username = username
            self.password = password
            messagebox.showinfo("Success", "Login successful!")
            self.show_chat_window()
            threading.Thread(target=self.listen_for_messages, daemon=True).start()
            threading.Thread(target=self.listen_for_server_info, daemon=True).start()
        else:
            messagebox.showerror("Login Failed", response.message)

    def show_chat_window(self):
        """Display the main chat interface with proper placeholder text behavior."""
        self.clear_window()

        # change the title into "Chat App - [username]"
        self.root.title(f"Chat App - {self.username}")

        self.chat_display = scrolledtext.ScrolledText(self.root, width=50, height=20, state=tk.DISABLED)
        self.chat_display.pack()

        # Recipient input field
        self.recipient_entry = tk.Entry(self.root, width=30, fg="grey")
        self.recipient_entry.pack()
        self.recipient_entry.insert(0, "Enter recipient")
        self.recipient_entry.bind("<FocusIn>", lambda event: self.on_focus_in(self.recipient_entry, "Enter recipient"))
        self.recipient_entry.bind("<FocusOut>", lambda event: self.on_focus_out(self.recipient_entry, "Enter recipient"))

        # Message input field
        self.message_entry = tk.Entry(self.root, width=30, fg="grey")
        self.message_entry.pack()
        self.message_entry.insert(0, "Enter message")
        self.message_entry.bind("<FocusIn>", lambda event: self.on_focus_in(self.message_entry, "Enter message"))
        self.message_entry.bind("<FocusOut>", lambda event: self.on_focus_out(self.message_entry, "Enter message"))

        send_button = tk.Button(self.root, text="Send Message", command=self.send_message)
        send_button.pack()

        read_button = tk.Button(self.root, text="Read Messages", command=self.read_messages)
        read_button.pack()

        list_accounts_button = tk.Button(self.root, text="List Accounts", command=self.list_accounts)
        list_accounts_button.pack()

        delete_message_button = tk.Button(self.root, text="Delete Most Recent Message With ...", command=self.delete_message)
        delete_message_button.pack()

        delete_account_button = tk.Button(self.root, text="Delete Account", command=self.delete_account)
        delete_account_button.pack()

        logout_button = tk.Button(self.root, text="Logout", command=self.logout)
        logout_button.pack()

    def on_focus_in(self, entry, placeholder):
        """Remove placeholder text and change color to black when user clicks the field."""
        if entry.get() == placeholder:
            entry.delete(0, tk.END) 
            entry.config(fg="black")

    def on_focus_out(self, entry, placeholder):
        """Restore placeholder text if the user leaves the field empty."""
        if not entry.get().strip():
            entry.insert(0, placeholder)
            entry.config(fg="grey")


    def send_message(self):
        """Send a message and reset placeholders correctly."""
        recipient = self.recipient_entry.get().strip()
        message = self.message_entry.get().strip()

        if recipient == "Enter recipient" or message == "Enter message":
            messagebox.showerror("Error", "Please enter a valid recipient and message.")
            return

        response = self.stub.SendMessage(
            chat_pb2.SendMessageRequest(username=self.username, recipient=recipient, message=message)
        )

        if response.status == "success":
            self.recipient_entry.delete(0, tk.END)
            self.recipient_entry.insert(0, "Enter recipient")
            self.recipient_entry.config(fg="grey")

            self.message_entry.delete(0, tk.END)
            self.message_entry.insert(0, "Enter message")
            self.message_entry.config(fg="grey")

        messagebox.showinfo("Message Status", response.message)


    def read_messages(self):
        """Retrieve messages with a user-specified limit."""
        try:
            limit = simpledialog.askinteger("Input", "Enter the number of messages to retrieve (0-10):", minvalue=0, maxvalue=10)
            if limit is None:
                return

            response = self.stub.ReadMessages(chat_pb2.ReadMessagesRequest(username=self.username, limit=limit))

            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, "\n--- Messages ---\n")
            for msg in response.messages:
                self.chat_display.insert(tk.END, f"From {msg.sender}: {msg.message}\n")
            self.chat_display.config(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def list_accounts(self):
        """List available user accounts."""
        response = self.stub.ListAccounts(chat_pb2.ListAccountsRequest(page_num=1))
        messagebox.showinfo("Accounts", "\n".join(response.usernames))

    def delete_message(self):
        """Delete Most recent message, given the recipient."""
        try:
            recipient = simpledialog.askstring("Input", "Enter recipient username:")

            if not recipient:
                return

            response = self.stub.DeleteMessage(chat_pb2.DeleteMessageRequest(username=self.username, recipient=recipient))
            messagebox.showinfo("Delete Status", response.message)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def delete_account(self):
        """Delete the user's account."""
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete your account?")
        if confirm:
            response = self.stub.DeleteAccount(chat_pb2.DeleteAccountRequest(username=self.username, password=self.password))
            messagebox.showinfo("Account Deletion", response.message)
            if response.status == "success":
                self.show_login_window()

    def listen_for_messages(self):
        """Listen for incoming real-time messages."""
        try:
            for message in self.stub.ListenForMessages(chat_pb2.ListenForMessagesRequest(username=self.username)):
                self.display_message(f"\n[New Message] {message.sender}: {message.message}\n")
        except grpc.RpcError as e:
            # self.display_message("[Server disconnected]\n")
            print("[Warning] Lost connection to ListenForMessages stream: ", e)
            self.server_disconnected.set()

    def listen_for_server_info(self):
        while not self.server_disconnected.is_set():
            try:
                response = self.stub.GetReplicaAddresses(Empty())
                if response.replica_addresses != self.replica_addresses:
                    print("[System] Replica list updated:", response.replica_addresses)
                    self.replica_addresses = list(response.replica_addresses)
            except grpc.RpcError as e:
                print("[Warning] Failed to fetch replica list:", e)
                self.server_disconnected.set()
                break
            time.sleep(2)  # Polling interval (in seconds)

    def monitor_connection(self):
        while True:
            if self.server_disconnected.is_set():
                print("[System] Attempting to reconnect to a new leader...")

                for address in self.replica_addresses:
                    try:
                        new_channel = grpc.insecure_channel(address)
                        new_stub = chat_pb2_grpc.ChatServiceStub(new_channel)
                        response = new_stub.WhoIsLeader(Empty())
                        leader_addr = response.leader_address

                        self.channel = grpc.insecure_channel(leader_addr)
                        self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)

                        print(f"[System] Reconnected to new leader: {leader_addr}")

                        # Clear the flag and restart threads
                        self.server_disconnected.clear()
                        threading.Thread(target=self.listen_for_messages, daemon=True).start()
                        threading.Thread(target=self.listen_for_server_info, daemon=True).start()
                        break

                    except grpc.RpcError:
                        continue

                time.sleep(3)  # wait before retrying in case all replicas fail
            else:
                time.sleep(1)
            

    def display_message(self, msg):
        """Display a message in the chat window."""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, msg)
        self.chat_display.config(state=tk.DISABLED)

    def logout(self):
        """Logout the user and display the login screen."""
        response = self.stub.Logout(chat_pb2.LogoutRequest(username=self.username))
        if response.status == "success":
            self.show_login_window()
        else:
            messagebox.showerror("Error", response.message)

    def clear_window(self):
        """Clear all widgets in the window."""
        for widget in self.root.winfo_children():
            widget.destroy()

    def handle_close(self):
        """Handles the window close event by sending a logout request before exiting."""
        if self.username:
            try:
                self.stub.Logout(chat_pb2.LogoutRequest(username=self.username))
            except grpc.RpcError:
                pass  # Ignore errors if the server is unreachable

        self.channel.close()  # Properly close the gRPC channel
        self.root.destroy()  # Close the Tkinter window


if __name__ == "__main__":
    args = parse_args()
    root = tk.Tk()
    app = ChatGUI(root, args)
    root.mainloop()

# python gui.py --host=192.168.1.10 --port=50051