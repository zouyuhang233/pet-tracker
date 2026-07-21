import paramiko, sys, time

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"
NEW_TCP_PORT = 18080  # 避开被占用的 8080

def run(ssh, cmd, timeout=20):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# ==================== 1. Fix TCP port in server.js ====================
print(f"[1] Changing TCP port to {NEW_TCP_PORT}...", flush=True)
sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'r') as f:
    js = f.read().decode('utf-8')
sftp.close()

js = js.replace('const TCP_PORT = 8080;', f'const TCP_PORT = {NEW_TCP_PORT};')
print(f"    Changed TCP_PORT to {NEW_TCP_PORT}", flush=True)

sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'w') as f:
    f.write(js.encode('utf-8'))
sftp.close()

# ==================== 2. Kill the process occupying port 8080 ====================
print("\n[2] Freeing port 8080...", flush=True)
out, _ = run(ssh, "sudo ss -tlnp | grep :8080")
print(f"    Current 8080 users: {out.strip()}", flush=True)

# Kill whatever is on 8080 (probably a python3 process from earlier deploy attempt)
out, _ = run(ssh, "sudo fuser -k 8080/tcp 2>/dev/null; echo 'killed' || echo 'nothing to kill'")
print(f"    {out.strip()}", flush=True)

time.sleep(1)

# ==================== 3. Restart service ====================
print("\n[3] Restarting service...", flush=True)
run(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")
out, _ = run(ssh, "cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"    {out.strip()}", flush=True)
run(ssh, "pm2 save 2>/dev/null || true")

time.sleep(4)

# Check logs
out, _ = run(ssh, "pm2 logs location-server --lines 10 --nostream 2>&1")
print(f"\n[Logs]\n{out[:1500]}", flush=True)

out, _ = run(ssh, "pm2 status")
print(f"[PM2]\n{out}", flush=True)

# ==================== 4. Test ====================
print("\n[4] Testing...", flush=True)

out, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:3002/cw_dwq 2>/dev/null || echo FAIL")
print(f"    Web :3002/cw_dwq -> HTTP {out.strip()}", flush=True)

out, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{NEW_TCP_PORT}/ 2>/dev/null || echo FAIL")
print(f"    TCP :{NEW_TCP_PORT} -> HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq 2>/dev/null || echo FAIL")
print(f"    Nginx /cw_dwq -> HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/ 2>/dev/null || echo FAIL")
print(f"    Main site / -> HTTP {out.strip()}", flush=True)

# ==================== 5. Verify Nginx config ====================
print("\n[5] Nginx config check...", flush=True)
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    conf = f.read().decode('utf-8')
sftp.close()

# Count cw_dwq occurrences
count = conf.count('/cw_dwq')
print(f"    /cw_dwq blocks in config: {count}", flush=True)

# Show relevant lines
for i, line in enumerate(conf.split('\n'), 1):
    if 'cw_dwq' in line:
        print(f"    L{i}: {line.strip()}", flush=True)

print(f"\n定位器: https://zouyuhang.online/cw_dwq", flush=True)
print("Done!", flush=True)
ssh.close()
