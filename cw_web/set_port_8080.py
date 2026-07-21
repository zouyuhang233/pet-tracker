import paramiko, sys, time

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Change TCP port from 18080 to 8080
print("[*] Changing TCP port to 8080...", flush=True)
sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'r') as f:
    js = f.read().decode('utf-8')
sftp.close()

js = js.replace('const TCP_PORT = 18080;', 'const TCP_PORT = 8080;')

sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'w') as f:
    f.write(js.encode('utf-8'))
sftp.close()
print("    [OK] TCP port set to 8080", flush=True)

# Kill anything on 8080 first
run(ssh, "sudo fuser -k 8080/tcp 2>/dev/null; echo 'cleaned'")
time.sleep(1)

# Restart
print("[*] Restarting service...", flush=True)
run(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")
out, _ = run(ssh, "cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"    {out.strip()}", flush=True)
run(ssh, "pm2 save 2>/dev/null || true")

time.sleep(4)

# Check logs
out, _ = run(ssh, "pm2 logs location-server --lines 10 --nostream 2>&1")
print(f"[Logs]\n{out[:1000]}", flush=True)

out, _ = run(ssh, "pm2 status")
print(f"[PM2]\n{out}", flush=True)

# Test
out, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3002/cw_dwq/ 2>/dev/null || echo FAIL")
print(f"\nWeb /cw_dwq -> HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "sudo ss -tlnp | grep ':8080'")
print(f"Port 8080 listeners:\n{out}", flush=True)

print("\nDone!", flush=True)
ssh.close()
