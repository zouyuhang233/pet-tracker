import paramiko
import sys
import os

HOST = "8.134.127.141"
PORT = 22
USER = "root"
PASS = "123456789zyhZ"

def ssh_exec(ssh, cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

print("[*] Connecting to server...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
    print("[+] Connected!")
except Exception as e:
    print(f"[-] Connection failed: {e}")
    sys.exit(1)

# ==================== Step 1: Diagnose ====================
print("\n========== Step 1: Diagnosis ==========")

out, _ = ssh_exec(ssh, "ls -la /etc/nginx/sites-enabled/ 2>/dev/null")
print(f"[Nginx enabled sites]\n{out}")

out, _ = ssh_exec(ssh, "ls -la /etc/nginx/sites-available/ 2>/dev/null")
print(f"[Nginx available sites]\n{out}")

out, _ = ssh_exec(ssh, "cat /etc/nginx/sites-available/default 2>/dev/null || echo 'NO default config'")
print(f"[Default config]\n{out[:2000]}")

out, _ = ssh_exec(ssh, "cat /etc/nginx/sites-available/location-server 2>/dev/null || echo 'NO location-server config'")
print(f"[Location-server config]\n{out[:2000]}")

out, _ = ssh_exec(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test]\n{out}")

out, _ = ssh_exec(ssh, "pm2 status 2>/dev/null || echo 'PM2 not running'")
print(f"[PM2 status]\n{out}")

out, _ = ssh_exec(ssh, "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/cw_dwq 2>/dev/null || echo 'FAILED'")
print(f"[Local service test] HTTP {out}")

out, _ = ssh_exec(ssh, "curl -s -o /dev/null -w '%{http_code}' http://localhost/cw_dwq 2>/dev/null || echo 'FAILED'")
print(f"[Nginx proxy test] HTTP {out}")

# ==================== Step 2: Deploy files ====================
print("\n========== Step 2: Deploy files ==========")

# Read the fix package
zip_path = r"C:\Users\zyh\Desktop\fix_cw_dwq.zip"
if not os.path.exists(zip_path):
    print(f"[-] Fix package not found: {zip_path}")
    sys.exit(1)

with open(zip_path, 'rb') as f:
    zip_data = f.read()
print(f"[+] Read fix package: {len(zip_data)} bytes")

# Upload via SFTP
sftp = ssh.open_sftp()
try:
    sftp.stat('/opt/location-server')
except FileNotFoundError:
    print("[*] Creating /opt/location-server")
    ssh_exec(ssh, "sudo mkdir -p /opt/location-server && sudo chown -R root:root /opt/location-server")

# Upload zip
remote_zip = '/tmp/fix_cw_dwq.zip'
print(f"[*] Uploading to {remote_zip}...")
with sftp.open(remote_zip, 'wb') as rf:
    rf.write(zip_data)
print("[+] Upload complete!")

# Unzip on server
out, _ = ssh_exec(ssh, f"sudo unzip -o {remote_zip} -d /opt/location-server/ 2>&1")
print(f"[Unzip output]\n{out[:500]}")

sftp.close()

# ==================== Step 3: Install deps & start service ====================
print("\n========== Step 3: Start Node.js service ==========")

out, _ = ssh_exec(ssh, "which node || echo 'NO NODE'")
print(f"[Node.js] {out.strip()}")

if 'NO NODE' in out:
    print("[*] Installing Node.js...")
    ssh_exec(ssh, "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -", timeout=60)
    ssh_exec(ssh, "sudo apt-get install -y nodejs", timeout=120)
    out, _ = ssh_exec(ssh, "node --version")
    print(f"[+] Node.js installed: {out.strip()}")

out, _ = ssh_exec(ssh, "which pm2 || echo 'NO PM2'")
if 'NO PM2' in out:
    print("[*] Installing PM2...")
    ssh_exec(ssh, "sudo npm install -g pm2", timeout=60)

# Stop old processes
ssh_exec(ssh, "cd /opt/location-server && pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")

# Install dependencies
print("[*] Installing npm dependencies...")
out, _ = ssh_exec(ssh, "cd /opt/location-server && npm install --production 2>&1", timeout=60)
print(f"[npm install]\n{out[:500]}")

# Start service
ssh_exec(ssh, "cd /opt/location-server && pm2 start server.js --name 'location-server'")
ssh_exec(ssh, "pm2 save")
ssh_exec(ssh, "pm2 startup 2>/dev/null || true")

import time
time.sleep(3)

out, _ = ssh_exec(ssh, "pm2 status")
print(f"[PM2 status]\n{out}")

out, _ = ssh_exec(ssh, "pm2 logs location-server --lines 20 2>&1")
print(f"[PM2 logs]\n{out[:1000]}")

# ==================== Step 4: Fix Nginx ====================
print("\n========== Step 4: Fix Nginx configuration ==========")

# Disable default site
out, _ = ssh_exec(ssh, "sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null; echo 'done'")
print(f"[*] Disabled default site: {out.strip()}")

# Write new Nginx config
nginx_conf = """server {
    listen 80;
    listen [::]:80;
    server_name zouyuhang.online www.zouyuhang.online _;

    # 定位器网站 - /cw_dwq 子目录反向代理
    location /cw_dwq/ {
        proxy_pass http://localhost:3000/cw_dwq/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_cache_bypass $http_upgrade;
        proxy_redirect http://localhost:3000/ /cw_dwq/;
    }

    # WebSocket 反代
    location /cw_dwq/ws {
        proxy_pass http://localhost:8081/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
"""

# Write config using SFTP
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/sites-available/location-server', 'w') as f:
    f.write(nginx_conf)
sftp.close()
print("[+] Nginx config written")

# Enable site
out, _ = ssh_exec(ssh, "sudo ln -sf /etc/nginx/sites-available/location-server /etc/nginx/sites-enabled/location-server")
print(f"[+] Site enabled: {out.strip()}")

# Test and reload
out, _ = ssh_exec(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test] {out}")

if "successful" in out:
    ssh_exec(ssh, "sudo systemctl reload nginx")
    print("[+] Nginx reloaded!")
else:
    print("[-] Nginx config has errors!")

# ==================== Step 5: Firewall ====================
print("\n========== Step 5: Firewall ==========")
ssh_exec(ssh, "sudo ufw allow 80/tcp comment 'HTTP' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 443/tcp comment 'HTTPS' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 3000/tcp comment 'Web' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 8080/tcp comment 'TCP' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 22/tcp comment 'SSH' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw reload 2>/dev/null || true")
print("[+] Firewall configured")

# ==================== Step 6: HTTPS ====================
print("\n========== Step 6: HTTPS ==========")
out, _ = ssh_exec(ssh, "sudo certbot --nginx -d zouyuhang.online -d www.zouyuhang.online --non-interactive --agree-tos --email zouyuhang@example.com 2>&1", timeout=60)
print(f"[Certbot] {out[:500]}")

# ==================== Step 7: Verify ====================
print("\n========== Step 7: Verification ==========")

time.sleep(2)

tests = [
    ("Local Node.js", "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/cw_dwq"),
    ("Nginx proxy", "curl -s -o /dev/null -w '%{http_code}' http://localhost/cw_dwq"),
]

for name, cmd in tests:
    out, _ = ssh_exec(ssh, cmd)
    code = out.strip()
    status = "OK" if code == "200" else f"FAIL (HTTP {code})"
    print(f"  [{status}] {name}")

# Final check - list enabled sites
out, _ = ssh_exec(ssh, "ls -la /etc/nginx/sites-enabled/")
print(f"\n[Final Nginx sites-enabled]\n{out}")

out, _ = ssh_exec(ssh, "pm2 status")
print(f"[Final PM2]\n{out}")

# ==================== Done ====================
print("\n========== DONE ==========")
print("Visit: https://zouyuhang.online/cw_dwq")

ssh.close()
