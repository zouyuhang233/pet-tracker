import paramiko, sys, os, time

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"
OUR_PORT = 3002

def run(ssh, cmd, timeout=30):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# ==================== 1. Check if files exist ====================
print("[1] Checking deployed files...", flush=True)
out, _ = run(ssh, "ls /opt/location-server/server.js 2>/dev/null && echo 'EXISTS' || echo 'NOT FOUND'")
print(f"    {out.strip()}", flush=True)

out, _ = run(ssh, "ls /opt/location-server/node_modules/ 2>/dev/null | head -3 || echo 'NO node_modules'")
print(f"    node_modules: {out.strip()[:100]}", flush=True)

# ==================== 2. Fix server.js port if needed ====================
print(f"\n[2] Setting port to {OUR_PORT}...", flush=True)
sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'r') as f:
    js = f.read().decode('utf-8')
sftp.close()

if f'const WEB_PORT = {OUR_PORT};' not in js:
    js = js.replace('const WEB_PORT = 3000;', f'const WEB_PORT = {OUR_PORT};')
    # Also fix BASE_PATH
    if "const BASE_PATH = '/cw_dwq';" not in js:
        js = js.replace("const BASE_PATH = '/cw_dwq';", "const BASE_PATH = '/cw_dwq';")
    sftp = ssh.open_sftp()
    with sftp.open('/opt/location-server/server.js', 'w') as f:
        f.write(js.encode('utf-8'))
    sftp.close()
    print(f"    [OK] Port set to {OUR_PORT}", flush=True)
else:
    print(f"    [OK] Port already {OUR_PORT}", flush=True)

# ==================== 3. Install deps & start service ====================
print(f"\n[3] Starting Node.js service on port {OUR_PORT}...", flush=True)

# Check if deps are installed
out, _ = run(ssh, "test -d /opt/location-server/node_modules/express && echo 'DEPS_OK' || echo 'NO_DEPS'")
has_deps = 'DEPS_OK' in out

if not has_deps:
    print("    Installing npm dependencies (background)...", flush=True)
    run(ssh, "cd /opt/location-server && nohup npm install --production > /tmp/npm.log 2>&1 &")
    print("    Waiting 60s for npm...", flush=True)
    time.sleep(60)
    out, _ = run(ssh, "tail -3 /tmp/npm.log 2>/dev/null")
    print(f"    npm: {out.strip()[:120]}", flush=True)
else:
    print("    [OK] Dependencies already installed", flush=True)

# Start service
run(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")
out, _ = run(ssh, f"cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"    PM2 start: {out.strip()}", flush=True)
run(ssh, "pm2 save 2>/dev/null || true")

time.sleep(4)
out, _ = run(ssh, "pm2 status")
print(f"[PM2]\n{out}", flush=True)

# Test
out, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{OUR_PORT}/cw_dwq 2>/dev/null || echo 'FAIL'")
print(f"[Local test] HTTP {out.strip()}", flush=True)

# ==================== 4. Fix Nginx - Add /cw_dwq blocks ====================
print(f"\n[4] Adding /cw_dwq routing to ridge-guardian.conf...", flush=True)

sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    conf = f.read().decode('utf-8')
sftp.close()

# Check if already has /cw_dwq
if '/cw_dwq' in conf:
    print("    /cw_dwq already in config, checking...", flush=True)
else:
    print("    Adding /cw_dwq blocks...", flush=True)

# Remove any old cw_dwq blocks we may have added before
lines = conf.split('\n')
cleaned = []
skip_until_brace = False
for line in lines:
    if '# ====== 定位器' in line or '# 定位器' in line:
        skip_until_brace = True
        continue
    if skip_until_brace:
        if line.strip() == '}':
            skip_until_brace = False
        continue
    cleaned.append(line)
conf = '\n'.join(cleaned)

# Now add the /cw_dwq blocks RIGHT BEFORE the catch-all `location /` block
# This is critical - must be before `location /` so it takes priority
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

# Find the catch-all `location /` block in the SSL server block
# and insert our blocks before it
idx = conf.find('\n    location / {\n')
if idx > 0:
    conf = conf[:idx] + '\n' + cw_dwq_block + conf[idx+1:]
    print("    [OK] Inserted /cw_dwq blocks before catch-all location /", flush=True)
else:
    # Fallback: insert before last }
    idx = conf.rfind('}')
    if idx > 0:
        conf = conf[:idx] + cw_dwq_block + '\n}' + conf[idx+1:]
        print("    [OK] Inserted before last }", flush=True)

# Write back
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
    f.write(conf.encode('utf-8'))
sftp.close()

# Verify the insertion
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    verify = f.read().decode('utf-8')
sftp.close()
has_cwdwq = '/cw_dwq' in verify
print(f"    Config has /cw_dwq: {has_cwdwq}", flush=True)

# Test and reload
out, _ = run(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test] {out.strip()}", flush=True)

if "successful" in out:
    run(ssh, "sudo systemctl reload nginx")
    print("[+] Nginx reloaded!", flush=True)
else:
    print("[-] Nginx config error! Restoring backup...", flush=True)
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
print("\n========== Verification ==========", flush=True)
time.sleep(2)

tests = [
    (f"Node.js :{OUR_PORT}/cw_dwq", f"curl -sk -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{OUR_PORT}/cw_dwq"),
    ("Nginx /cw_dwq", "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq"),
    ("Main site /", "curl -sk -o /dev/null -w '%{http_code}' https://localhost/"),
]

for name, cmd in tests:
    try:
        o, _ = run(ssh, cmd)
        code = o.strip()
        tag = "OK" if code == "200" else f"HTTP {code}"
    except:
        tag = "ERR"
    print(f"  [{tag}] {name}", flush=True)

# Show the relevant part of the config
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    full = f.read().decode('utf-8')
sftp.close()

# Show lines around /cw_dwq
for i, line in enumerate(full.split('\n'), 1):
    if 'cw_dwq' in line or 'location /' in line:
        print(f"  L{i}: {line}", flush=True)

print(f"\n定位器: https://zouyuhang.online/cw_dwq", flush=True)
print("Done!", flush=True)
ssh.close()
