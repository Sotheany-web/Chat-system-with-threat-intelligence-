# backend/main.py
from fastapi import FastAPI, WebSocket

app = FastAPI()

# Simple REST route
@app.get("/")
def home():
    return {"message": "Chat server is running!"}

# Example REST route for messages
@app.get("/messages")
def get_messages():
    # Later you’ll connect this to your database
    return [{"sender": "Alice", "content": "Hello!"}, {"sender": "Bob", "content": "Hi!"}]

# WebSocket route for real-time chat
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        # Echo back the message for now
        await websocket.send_text(f"Message received: {data}")
