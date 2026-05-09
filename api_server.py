from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import uvicorn, asyncio, json

app = FastAPI()
app.mount("/", StaticFiles(directory="gui", html=True), name="gui")
clients = set()

@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            data = await ws.receive_text()
            # Forward to ARIA main loop
            print(f"[Dashboard] {data}")
            await ws.send_text(json.dumps({"type":"ack","msg":"received"}))
    finally:
        clients.remove(ws)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)