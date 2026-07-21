import paramiko
import sys
import os
import zipfile
import io
import time

HOST = "8.134.127.141"
PORT = 22
USER = "root"
PASS = "123456789zyhZ"
OUR_PORT = 3002  # Different from ridge-guardian(3000), blog(3001), eda(3005)

def ssh_exec(ssh, cmd, timeout=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

print("[*] Connecting...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
    print("[+] Connected!")
except Exception as e:
    print(f"[-] Failed: {e}")
    sys.exit(1)

# ==================== Step 1: Deploy files ====================
print("\n========== Step 1: Deploying files ==========")

zip_path = r"C:\Users\zyh\Desktop\fix_cw_dwq.zip"
with open(zip_path, 'rb') as f:
    zip_data = f.read()
print(f"[+] Zip: {len(zip_data)} bytes")

zip_buffer = io.BytesIO(zip_data)
zf = zipfile.ZipFile(zip_buffer, 'r')
file_list = zf.namelist()
print(f"[+] Files: {file_list}")

sftp = ssh.open_sftp()
ssh_exec(ssh, "sudo mkdir -p /opt/location-server/public")
ssh_exec(ssh, "sudo chown -R root:root /opt/location-server")

for filename in file_list:
    file_data = zf.read(filename)
    remote_path = f"/opt/location-server/{filename}"
    remote_dir = os.path.dirname(remote_path)
    if remote_dir and remote_dir != '/opt/location-server':
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            ssh_exec(ssh, f"sudo mkdir -p {remote_dir}")
    with sftp.open(remote_path, 'wb') as rf:
        rf.write(file_data)
    ssh_exec(ssh, f"sudo chown root:root {remote_path}")
    print(f"  [OK] {filename}")

sftp.close()
zf.close()
print("[+] Files uploaded!")

# ==================== Step 2: Configure port ====================
print(f"\n========== Step 2: Configuring on port {OUR_PORT} ==========")

sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'r') as f:
    server_js = f.read().decode('utf-8')
sftp.close()

server_js = server_js.replace('const WEB_PORT = 3000;', f'const WEB_PORT = {OUR_PORT};')
print(f"[+] Set WEB_PORT = {OUR_PORT}")

sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'w') as f:
    f.write(server_js.encode('utf-8'))
sftp.close()

# ==================== Step 3: Install deps & start ====================
print("\n========== Step 3: Install deps & start service ==========")

# Run npm install in background to avoid timeout
out, _ = ssh_exec(ssh, f"cd /opt/location-server && nohup npm install --production > /tmp/npm_install.log 2>&1 & echo 'PID:'$!")
print(f"[npm] {out.strip()}")

# Wait for npm install to complete
print("[*] Waiting for npm install (up to 120s)...")
for i in range(24):
    time.sleep(5)
    out, _ = ssh_exec(ssh, "tail -5 /tmp/npm_install.log 2>/dev/null || echo 'still running'")
    print(f"  [{i*5}s] {out.strip()[:100]}")
    if 'added' in out or 'up to date' in out:
        print("[+] npm install complete!")
        break
else:
    print("[!] npm install may still be running, continuing...")

# Check node_modules
out, _ = ssh_exec(ssh, "ls /opt/location-server/node_modules/package.json 2>/dev/null && echo 'OK' || echo 'NO node_modules'")
print(f"[node_modules] {out.strip()}")

# Stop old instance
ssh_exec(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")

# Start
out, _ = ssh_exec(ssh, f"cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"[Start] {out}")

out, _ = ssh_exec(ssh, "pm2 save 2>/dev/null || true")

time.sleep(4)

out, _ = ssh_exec(ssh, "pm2 status")
print(f"[PM2]\n{out}")

# Test
out, _ = ssh_exec(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{OUR_PORT}/cw_dwq 2>/dev/null || echo 'FAIL'")
print(f"[Local test] HTTP {out.strip()}")

# ==================== Step 4: Fix Nginx ====================
print(f"\n========== Step 4: Adding /cw_dwq to ridge-guardian.conf ==========")

# Read existing config
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    ridge_conf = f.read().decode('utf-8')
sftp.close()

# Show current config
print(f"[Current config]\n{ridge_conf[:2000]}")

# Check if /cw_dwq already exists
if '/cw_dwq' in ridge_conf:
    print("[!] /cw_dwq already exists, removing old entries...")
    lines = ridge_conf.split('\n')
    new_lines = []
    skip_cwdwq = False
    for line in lines:
        if '# ====== 定位器' in line or '# 定位器' in line:
            skip_cwdwq = True
            continue
        if skip_cwdwq and line.strip().startswith('#'):
            continue
        if skip_cwdwq and ('location /cw_dwq' in line or 'proxy_pass' in line):
            continue
        if skip_cwdwq and line.strip() == '}':
            skip_cwdwq = False
            continue
        new_lines.append(line)
    ridge_conf = '\n'.join(new_lines)

# Build the /cw_dwq location blocks
cw_dwq_blocks = f"""
    # ====== 定位器网站 /cw_dwq ======
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

# Insert before the last } of the SSL server block
# Find the last } of the main server block (443 ssl)
last_ssl_brace = ridge_conf.rfind('}')
if last_ssl_brace > 0:
    ridge_conf = ridge_conf[:last_ssl_brace] + cw_dwq_blocks + '\n}' + ridge_conf[last_ssl_brace+1:]
else:
    ridge_conf += cw_dwq_blocks

print(f"[+] Added /cw_dwq blocks")

# Write back
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
    f.write(ridge_conf.encode('utf-8'))
sftp.close()

# Test and reload
out, _ = ssh_exec(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test] {out}")

if "successful" in out:
    ssh_exec(ssh, "sudo systemctl reload nginx")
    print("[+] Nginx reloaded!")
else:
    print("[-] Nginx error! Restoring backup...")
    # Try restoring from .bak
    for ext in ['.bak', '.bak-deploy', '.bak2', '.disabled']:
        backup = f'/etc/nginx/conf.d/ridge-guardian.conf{ext}'
        out_check, _ = ssh_exec(ssh, f"sudo test -f {backup} && echo 'EXISTS' || echo 'NO'")
        if 'EXISTS' in out_check:
            sftp = ssh.open_sftp()
            with sftp.open(backup, 'r') as f:
                original = f.read()
            sftp.close()
            sftp = ssh.open_sftp()
            with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
                f.write(original)
            sftp.close()
            ssh_exec(ssh, "sudo nginx -t && sudo systemctl reload nginx")
            print(f"[+] Restored from {ext}")
            break

# ==================== Step 5: Verify ====================
print("\n========== Step 5: Verification ==========")
time.sleep(2)

tests = [
    (f"Node.js :{OUR_PORT}", f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{OUR_PORT}/cw_dwq"),
    ("Nginx /cw_dwq", "curl -s -o /dev/null -w '%{http_code}' http://localhost/cw_dwq"),
    ("Nginx HTTPS /cw_dwq", "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq"),
    ("Main site /", "curl -sk -o /dev/null -w '%{http_code}' https://localhost/"),
]

for name, cmd in tests:
    try:
        out, _ = ssh_exec(ssh, cmd)
        code = out.strip()
        status = "OK" if code == "200" else f"HTTP {code}"
    except:
        status = "ERROR"
    print(f"  [{status}] {name}")

out, _ = ssh_exec(ssh, "pm2 status")
print(f"\n[PM2]\n{out}")

print("\n========== DONE ==========")
print(f"Main site:  https://zouyuhang.online/")
print(f"定位器:      https://zouyuhang.online/cw_dwq")
print(f"本地测试:    http://localhost:{OUR_PORT}/cw_dwq")

ssh.close()
