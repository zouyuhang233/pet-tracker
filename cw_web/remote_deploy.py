import paramiko
import sys
import os
import zipfile
import io

HOST = "8.134.127.141"
PORT = 22
USER = "root"
PASS = "123456789zyhZ"

def ssh_exec(ssh, cmd, timeout=60):
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

# ==================== Diagnosis ====================
print("\n========== Diagnosis ==========")

out, _ = ssh_exec(ssh, "ls -la /etc/nginx/sites-enabled/")
print(f"[Nginx enabled]\n{out}")

out, _ = ssh_exec(ssh, "ls -la /etc/nginx/sites-available/")
print(f"[Nginx available]\n{out}")

out, _ = ssh_exec(ssh, "sudo nginx -T 2>/dev/null | head -80")
print(f"[Nginx main config]\n{out}")

# Check existing server blocks for zouyuhang.online
out, _ = ssh_exec(ssh, "sudo grep -r 'zouyuhang' /etc/nginx/ 2>/dev/null || echo 'No zouyuhang config found'")
print(f"[zouyuhang references]\n{out}")

# Check what's running on ports
out, _ = ssh_exec(ssh, "sudo ss -tlnp | grep -E ':(80|443|3000|8080)'")
print(f"[Port listeners]\n{out}")

# ==================== Extract files using Python ====================
print("\n========== Deploying files ==========")

zip_path = r"C:\Users\zyh\Desktop\fix_cw_dwq.zip"
with open(zip_path, 'rb') as f:
    zip_data = f.read()
print(f"[+] Read zip: {len(zip_data)} bytes")

# Extract zip contents on local machine and upload each file
zip_buffer = io.BytesIO(zip_data)
with zipfile.ZipFile(zip_buffer, 'r') as zf:
    file_list = zf.namelist()
    print(f"[+] Zip contains {len(file_list)} files: {file_list[:10]}")

sftp = ssh.open_sftp()

# Create directories
ssh_exec(ssh, "sudo mkdir -p /opt/location-server/public")
ssh_exec(ssh, "sudo chown -R root:root /opt/location-server")

# Upload each file
for filename in file_list:
    file_data = zf.read(filename)
    remote_path = f"/opt/location-server/{filename}"
    
    # Create directory if needed
    remote_dir = os.path.dirname(remote_path)
    if remote_dir:
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            ssh_exec(ssh, f"sudo mkdir -p {remote_dir}")
    
    # Upload file
    with sftp.open(remote_path, 'wb') as rf:
        rf.write(file_data)
    ssh_exec(ssh, f"sudo chown root:root {remote_path}")
    print(f"  [OK] {filename}")

sftp.close()
print("[+] All files uploaded!")

# ==================== Install deps ====================
print("\n========== Installing dependencies ==========")

out, _ = ssh_exec(ssh, "cd /opt/location-server && npm install --production 2>&1", timeout=120)
print(f"[npm install]\n{out[-1000:]}")

# Check if node_modules exists
out, _ = ssh_exec(ssh, "ls -la /opt/location-server/node_modules/.package-lock.json 2>/dev/null || echo 'NO node_modules'")
print(f"[node_modules check] {out.strip()}")

# ==================== Configure PM2 ====================
print("\n========== Configuring PM2 ==========")

# Stop and remove old instance
ssh_exec(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")

# Start new instance
out, _ = ssh_exec(ssh, "cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"[Start] {out}")

out, _ = ssh_exec(ssh, "pm2 save 2>&1")
print(f"[Save] {out}")

out, _ = ssh_exec(ssh, "pm2 startup 2>/dev/null | tail -3")
print(f"[Startup] {out}")

import time
time.sleep(4)

out, _ = ssh_exec(ssh, "pm2 status")
print(f"[PM2 status]\n{out}")

# Quick test
out, _ = ssh_exec(ssh, "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/cw_dwq 2>/dev/null || echo 'FAIL'")
print(f"[Local test] HTTP {out.strip()}")

# ==================== Fix Nginx ====================
print("\n========== Configuring Nginx ==========")

# Check the MAIN nginx.conf to understand the setup
out, _ = ssh_exec(ssh, "cat /etc/nginx/nginx.conf")
print(f"[nginx.conf]\n{out}")

# Check if there's a conf.d directory
out, _ = ssh_exec(ssh, "ls -la /etc/nginx/conf.d/ 2>/dev/null || echo 'no conf.d'")
print(f"[conf.d] {out}")

# Check sites-available more carefully
out, _ = ssh_exec(ssh, "ls -la /etc/nginx/sites-available/")
print(f"[Sites available]\n{out}")

# Check ALL nginx configs for server blocks
out, _ = ssh_exec(ssh, "sudo grep -l 'server {' /etc/nginx/sites-available/* 2>/dev/null; sudo grep -l 'server {' /etc/nginx/conf.d/* 2>/dev/null; echo '---done---'")
print(f"[Configs with server blocks]\n{out}")

# ==================== Write Nginx config ====================
print("\n========== Writing Nginx config ==========")

# The key insight: we need to add /cw_dwq routing to the EXISTING server block
# that handles zouyuhang.online, or create a new dedicated config

# First, let's find what's handling port 80
out, _ = ssh_exec(ssh, "sudo nginx -T 2>/dev/null | grep -A 20 'server {' | head -60")
print(f"[Current server blocks]\n{out}")

# Write our location-server config
sftp = ssh.open_sftp()
nginx_config = """server {
    listen 80;
    listen [::]:80;
    server_name zouyuhang.online www.zouyuhang.online _;

    # 定位器网站 - /cw_dwq 子目录
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

with sftp.open('/etc/nginx/sites-available/location-server', 'w') as f:
    f.write(nginx_config)
sftp.close()

# Enable it
out, _ = ssh_exec(ssh, "sudo ln -sf /etc/nginx/sites-available/location-server /etc/nginx/sites-enabled/location-server")
print(f"[Enable site] {out.strip()}")

# Test and reload
out, _ = ssh_exec(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test] {out}")

if "successful" in out:
    ssh_exec(ssh, "sudo systemctl reload nginx")
    print("[+] Nginx reloaded!")
else:
    print("[-] Nginx config error!")

# ==================== Firewall ====================
print("\n========== Firewall ==========")
ssh_exec(ssh, "sudo ufw allow 80/tcp comment 'HTTP' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 443/tcp comment 'HTTPS' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 3000/tcp comment 'Web' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 8080/tcp comment 'TCP' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw reload 2>/dev/null || true")
print("[+] Firewall done")

# ==================== HTTPS ====================
print("\n========== HTTPS ==========")
out, _ = ssh_exec(ssh, "sudo certbot --nginx -d zouyuhang.online -d www.zouyuhang.online --non-interactive --agree-tos --email zouyuhang@example.com 2>&1", timeout=60)
print(f"[Certbot] {out[:500]}")

# ==================== Final verification ====================
print("\n========== Final Verification ==========")
time.sleep(2)

tests = [
    ("Node.js local", "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/cw_dwq"),
    ("Nginx proxy", "curl -s -o /dev/null -w '%{http_code}' http://localhost/cw_dwq"),
]

for name, cmd in tests:
    out, _ = ssh_exec(ssh, cmd)
    code = out.strip()
    status = "OK" if code == "200" else f"FAIL (HTTP {code})"
    print(f"  [{status}] {name}")

out, _ = ssh_exec(ssh, "ls -la /etc/nginx/sites-enabled/")
print(f"\n[Enabled sites]\n{out}")

out, _ = ssh_exec(ssh, "pm2 status")
print(f"[PM2]\n{out}")

print("\n========== COMPLETE ==========")
print("URL: https://zouyuhang.online/cw_dwq")

ssh.close()
