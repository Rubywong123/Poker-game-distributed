import grpc
import chat_pb2
import chat_pb2_grpc
import threading
from argparse import ArgumentParser

def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--host", default='127.0.0.1', help="Host address")
    parser.add_argument("--port", default=50051, help="Port number")
    return parser.parse_args()

def listen_for_messages(stub, username):
    """ Background thread that listens for real-time messages. """
    try:
        for message in stub.ListenForMessages(chat_pb2.ListenForMessagesRequest(username=username)):
            print(f"\n[New Message] {message.sender}: {message.message}\n")
    except grpc.RpcError as e:
        print(f"[Server disconnected]: {e}")
        exit()

def run(args):
    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    stub = chat_pb2_grpc.ChatServiceStub(channel)

    print("Welcome to the Chat App!")
    
    username = input("Enter username: ")
    password = input("Enter password: ")

    login_response = stub.Login(chat_pb2.LoginRequest(username=username, password=password))
    if login_response.status != "success":
        print("Login failed:", login_response.message)
        return

    print("Login successful! Listening for new messages...")
    
    threading.Thread(target=listen_for_messages, args=(stub, username), daemon=True).start()

    while True:
        print("\nOptions:")
        print("1. List accounts")
        print("2. Send message")
        print("3. Read messages")
        print("4. Delete message")
        print("5. Delete account")
        print("6. Exit")

        choice = input("Enter choice: ")
        
        if choice == "1":
            response = stub.ListAccounts(chat_pb2.ListAccountsRequest(page_num=1))
            print("Accounts:", response.usernames)

        elif choice == "2":
            recipient = input("Recipient username: ")
            message = input("Message: ")
            response = stub.SendMessage(chat_pb2.SendMessageRequest(username=username, recipient=recipient, message=message))
            print(response.status, response.message)

        elif choice == "3":
            try:
                limit = int(input("Enter the number of messages to retrieve (0-10): "))
                if limit < 0 or limit > 10:
                    print("Please enter a number between 0 and 10.")
                    continue
            except ValueError:
                print("Invalid input. Please enter a valid number.")
                continue

            response = stub.ReadMessages(chat_pb2.ReadMessagesRequest(username=username, limit=limit))

            if response.messages:
                for msg in response.messages:
                    print(f"From {msg.sender}: {msg.message}")
            else:
                print("No messages found.")

        elif choice == "4":
            recipient = input("Recipient username: ")
            response = stub.DeleteMessage(chat_pb2.DeleteMessageRequest(username=username, recipient=recipient))
            print(response.status, response.message)

        elif choice == "5":
            confirm = input("Are you sure you want to delete your account? (yes/no): ")
            if confirm.lower() == "yes":
                response = stub.DeleteAccount(chat_pb2.DeleteAccountRequest(username=username, password=password))
                print(response.status, response.message)
                if response.status == "success":
                    # send logout request
                    response = stub.Logout(chat_pb2.LogoutRequest(username=username))
                    if response.status == "success":
                        print("Logged out successfully.")
                        break

        elif choice == "6":
            response = stub.Logout(chat_pb2.LogoutRequest(username=username))
            if response.status == "success":
                print("Logged out successfully.")
                break

if __name__ == "__main__":
    args = parse_args()

    run(args)

# python client.py --host=192.168.1.10 --port=50051

