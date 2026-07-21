import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Check public directory
out, _ = run(ssh, "ls -la /opt/location-server/public/")
print("=== public/ ===")
print(out)

out, _ = run(ssh, "cat /opt/location-server/public/index.html | head -5")
print("=== index.html exists? ===")
print(out[:200])

# Check what happens when we request /cw_dwq/
out, _ = run(ssh, "curl -s http://127.0.0.1:3002/cw_dwq/ | head -10")
print("=== Response from /cw_dwq/ ===")
print(out[:300])

out, _ = run(ssh, "curl -s http://127.0.0.1:3002/cw_dwq/index.html | head -5")
print("=== Response from /cw_dwq/index.html ===")
print(out[:300])

# Check the server.js path logic
sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'r') as f:
    js = f.read().decode('utf-8')
sftp.close()

# Find the file serving part
for i, line in enumerate(js.split('\n'), 1):
    if 'filePath' in line or 'public' in line or 'readFile' in line or 'index.html' in line:
        print(f"  JS L{i}: {line.strip()}")

ssh.close()
