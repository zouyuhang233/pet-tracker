import socket
import threading
from datetime import datetime

def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    line = f'[{t}] {msg}'
    print(line)
    with open('/tmp/tcp_server.log', 'a') as f:
        f.write(line + '\n')

def handle(conn, addr):
    log(f'New connection: {addr}')
    while True:
        try:
            data = conn.recv(1024)
            if not data:
                break
            log(f'Received from {addr}: {data}')
            response = f'OK: received {len(data)} bytes'
            conn.send(response.encode())
            log(f'Replied: {response}')
        except Exception as e:
            log(f'Error: {e}')
            break
    conn.close()
    log(f'Disconnected: {addr}')

log('=' * 50)
log('TCP Server started on port 8080')
log('=' * 50)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 8080))
server.listen(5)

while True:
    conn, addr = server.accept()
    threading.Thread(target=handle, args=(conn, addr), daemon=True).start()
