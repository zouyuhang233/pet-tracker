import paramiko, sys, os, time

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"
OUR_PORT = 3002

def run(ssh, cmd, timeout=30):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    out = sout.read().decode('utf-8', errors='replace')
    err = serr.read().decode('utf-8', errors='replace')
    return out, err

def run_no_read(ssh, cmd):
    """Run command without reading output (for background tasks)"""
    ssh.exec_command(cmd)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# ==================== 1. Check files ====================
print("[1] Checking files...", flush=True)
out, _ = run(ssh, "ls /opt/location-server/server.js 2>/dev/null && echo YES || echo NO")
print(f"    server.js: {out.strip()}", flush=True)

out, _ = run(ssh, "test -d /opt/location-server/node_modules && echo DEPS_OK || echo NO_DEPS")
print(f"    deps: {out.strip()}", flush=True)

# ==================== 2. Install deps if needed ====================
print("\n[2] Installing dependencies...", flush=True)
out, _ = run(ssh, "test -d /opt/location-server/node_modules/express && echo OK || echo NEED_INSTALL")
if 'NEED_INSTALL' in out:
    print("    Running npm install (this takes ~30s, please wait)...", flush=True)
    # Use a PTY to avoid pipe buffer issues, don't read output
    channel = ssh.get_transport().open_session()
    channel.get_pty()
    channel.exec_command("cd /opt/location-server && npm install --production 2>&1 | tee /tmp/npm_install.log")
    # Wait up to 90s
    for i in range(18):
        time.sleep(5)
        # Check if process is still running
        out_check, _ = run(ssh, "ps aux | grep 'npm install' | grep -v grep || echo DONE")
        if 'DONE' in out_check:
            break
        print(f"    ...{(i+1)*5}s", flush=True)
    
    # Check result
    out, _ = run(ssh, "tail -3 /tmp/npm_install.log 2>/dev/null || echo no log")
    print(f"    Result: {out.strip()[:150]}", flush=True)
else:
    print("    [OK] Dependencies already installed", flush=True)

# ==================== 3. Start Node service ====================
print(f"\n[3] Starting service on port {OUR_PORT}...", flush=True)
run(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")
out, _ = run(ssh, f"cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"    {out.strip()}", flush=True)
run(ssh, "pm2 save 2>/dev/null || true")

time.sleep(5)
out, _ = run(ssh, "pm2 status")
print(f"[PM2]\n{out}", flush=True)

out, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{OUR_PORT}/cw_dwq 2>/dev/null || echo FAIL")
print(f"[Local test] HTTP {out.strip()}", flush=True)

# ==================== 4. Fix Nginx ====================
print(f"\n[4] Fixing Nginx config...", flush=True)

sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    conf = f.read().decode('utf-8')
sftp.close()

# Remove old cw_dwq blocks
lines = conf.split('\n')
cleaned = []
skip = False
for line in lines:
    if '# ====== 定位器' in line or '# 定位器' in line:
        skip = True; continue
    if skip:
        if line.strip() == '}':
            skip = False
        continue
    cleaned.append(line)
conf = '\n'.join(cleaned)

# Insert BEFORE the catch-all `location / {`
cw_dwq_block = f"""    # ====== 定位器 /cw_dwq ======
    location /cw_dwq/ {{
        proxy_pass http://127.0.0.1:{OUR_PORT}/cw_dwq/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_cache_bypass $http_upgrade;
        proxy_redirect http://127.0.0.1:{OUR_PORT}/ /cw_dwq/;
    }}
    location /cw_dwq/ws {{
        proxy_pass http://127.0.0.1:8081/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }}

"""

idx = conf.find('\n    location / {\n')
if idx > 0:
    conf = conf[:idx] + '\n' + cw_dwq_block + conf[idx+1:]
    print("    [OK] Inserted /cw_dwq before location /", flush=True)
else:
    idx = conf.rfind('}')
    conf = conf[:idx] + cw_dwq_block + '\n}' + conf[idx+1:]
    print("    [OK] Inserted before last }", flush=True)

sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
    f.write(conf.encode('utf-8'))
sftp.close()

out, _ = run(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test] {out.strip()}", flush=True)

if "successful" in out:
    run(ssh, "sudo systemctl reload nginx")
    print("[+] Nginx reloaded!", flush=True)
else:
    print("[-] Nginx error! Rolling back...", flush=True)
    for ext in ['.bak', '.bak-deploy', '.bak2']:
        ok, _ = run(ssh, f"sudo test -f /etc/nginx/conf.d/ridge-guardian.conf{ext} && echo YES")
        if 'YES' in ok:
            sftp = ssh.open_sftp()
            with sftp.open(f'/etc/nginx/conf.d/ridge-guardian.conf{ext}', 'r') as f:
                orig = f.read()
            sftp.close()
            sftp = ssh.open_sftp()
            with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
                f.write(orig)
            sftp.close()
            run(ssh, "sudo nginx -t && sudo systemctl reload nginx")
            print(f"    Restored from {ext}", flush=True)
            break

# ==================== 5. Verify ====================
print("\n========== Result ==========", flush=True)
time.sleep(2)

for name, cmd in [
    (f"Node :{OUR_PORT}/cw_dwq", f"curl -sk -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{OUR_PORT}/cw_dwq"),
    ("Nginx /cw_dwq", "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq"),
    ("Main site /", "curl -sk -o /dev/null -w '%{http_code}' https://localhost/"),
]:
    try:
        o, _ = run(ssh, cmd)
        code = o.strip()
        tag = "OK" if code == "200" else f"HTTP {code}"
    except:
        tag = "ERR"
    print(f"  [{tag}] {name}", flush=True)

print(f"\n定位器: https://zouyuhang.online/cw_dwq", flush=True)
print("Done!", flush=True)
ssh.close()
