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

# ==================== Step 1: Diagnosis ====================
print("\n========== Step 1: Diagnosis ==========")

out, _ = ssh_exec(ssh, "cat /etc/nginx/conf.d/ridge-guardian.conf 2>/dev/null || echo 'NOT FOUND'")
print(f"[ridge-guardian.conf]\n{out[:3000]}")

out, _ = ssh_exec(ssh, "ls -la /etc/nginx/conf.d/")
print(f"[conf.d listing]\n{out}")

out, _ = ssh_exec(ssh, "pm2 status")
print(f"[PM2]\n{out}")

out, _ = ssh_exec(ssh, "sudo ss -tlnp | grep -E ':(80|443|3000|3001|8080)'")
print(f"[Ports]\n{out}")

# ==================== Step 2: Deploy files ====================
print("\n========== Step 2: Deploying files ==========")

zip_path = r"C:\Users\zyh\Desktop\fix_cw_dwq.zip"
with open(zip_path, 'rb') as f:
    zip_data = f.read()
print(f"[+] Read zip: {len(zip_data)} bytes")

# Extract zip contents using BytesIO (keep buffer open)
zip_buffer = io.BytesIO(zip_data)
zf = zipfile.ZipFile(zip_buffer, 'r')
file_list = zf.namelist()
print(f"[+] Files to upload: {file_list}")

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
print("[+] All files uploaded!")

# ==================== Step 3: Modify server.js port ====================
print("\n========== Step 3: Configuring Node.js on port 3001 ==========")

# Read server.js and change port from 3000 to 3001
sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'r') as f:
    server_js = f.read().decode('utf-8')
sftp.close()

# Change WEB_PORT from 3000 to 3001 (since ridge-guardian uses 3000)
server_js = server_js.replace('const WEB_PORT = 3000;', 'const WEB_PORT = 3001;')
print("[+] Changed WEB_PORT to 3001")

# Write back
sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'w') as f:
    f.write(server_js.encode('utf-8'))
sftp.close()

# Install dependencies
print("[*] Installing npm dependencies...")
out, _ = ssh_exec(ssh, "cd /opt/location-server && npm install --production 2>&1", timeout=120)
print(f"[npm install]\n{out[-500:]}")

# Stop old location-server if exists
ssh_exec(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")

# Start our service on port 3001
out, _ = ssh_exec(ssh, "cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"[Start] {out}")

out, _ = ssh_exec(ssh, "pm2 save 2>&1")
out, _ = ssh_exec(ssh, "pm2 startup 2>/dev/null | tail -3")

import time
time.sleep(4)

out, _ = ssh_exec(ssh, "pm2 status")
print(f"[PM2]\n{out}")

# Test on port 3001
out, _ = ssh_exec(ssh, "curl -s -o /dev/null -w '%{http_code}' http://localhost:3001/cw_dwq 2>/dev/null || echo 'FAIL'")
print(f"[Local test on 3001] HTTP {out.strip()}")

# ==================== Step 4: Modify ridge-guardian.conf ====================
print("\n========== Step 4: Adding /cw_dwq to ridge-guardian.conf ==========")

# Read the existing ridge-guardian.conf
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    ridge_conf = f.read().decode('utf-8')
sftp.close()

print(f"[Current ridge-guardian.conf]\n{ridge_conf[:2000]}")

# Check if /cw_dwq is already in the config
if '/cw_dwq' in ridge_conf:
    print("[!] /cw_dwq already exists in config, updating...")
    # Remove old cw_dwq block and re-add it
    lines = ridge_conf.split('\n')
    new_lines = []
    skip = False
    for line in lines:
        if '# ====== 定位器网站' in line or '# 定位器网站' in line:
            skip = True
            continue
        if skip and line.strip().startswith('#'):
            continue
        if skip and 'location /cw_dwq' in line:
            # Skip until we find a line that's not part of this block
            skip = False
            continue
        if skip:
            continue
        new_lines.append(line)
    ridge_conf = '\n'.join(new_lines)

# Add /cw_dwq location block to the existing config
# We add it inside the main server block
cw_dwq_block = """
    # ====== 定位器网站 /cw_dwq ======
    location /cw_dwq/ {
        proxy_pass http://localhost:3001/cw_dwq/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_cache_bypass $http_upgrade;
        proxy_redirect http://localhost:3001/ /cw_dwq/;
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
"""

# Find the last `}` of the main server block and insert before it
# Actually, let's just append the location blocks before the last closing brace
# Find the last server block closing brace
last_brace_idx = ridge_conf.rfind('}')
if last_brace_idx > 0:
    ridge_conf = ridge_conf[:last_brace_idx] + cw_dwq_block + '\n}' + ridge_conf[last_brace_idx+1:]
else:
    ridge_conf += cw_dwq_block

print(f"[+] Added /cw_dwq block to ridge-guardian.conf")

# Write back
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
    f.write(ridge_conf.encode('utf-8'))
sftp.close()

# Test and reload Nginx
out, _ = ssh_exec(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test] {out}")

if "successful" in out:
    ssh_exec(ssh, "sudo systemctl reload nginx")
    print("[+] Nginx reloaded!")
else:
    print("[-] Nginx config error! Rolling back...")
    # Restore backup
    sftp = ssh.open_sftp()
    backup_files = []
    try:
        backup_files = sftp.listdir('/etc/nginx/conf.d/')
    except:
        pass
    sftp.close()
    
    # Try to restore from backup
    for bf in ['.bak', '.bak-deploy', '.bak2']:
        backup_path = f'/etc/nginx/conf.d/ridge-guardian.conf{bf}'
        try:
            with sftp.open(backup_path, 'r') as f:
                original = f.read()
            sftp.close()
            sftp = ssh.open_sftp()
            with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
                f.write(original)
            sftp.close()
            ssh_exec(ssh, "sudo systemctl reload nginx")
            print(f"[+] Restored from {bf}")
            break
        except:
            pass

# ==================== Step 5: Firewall ====================
print("\n========== Step 5: Firewall ==========")
ssh_exec(ssh, "sudo ufw allow 80/tcp comment 'HTTP' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 443/tcp comment 'HTTPS' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 3001/tcp comment 'Web cw_dwq' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw allow 8080/tcp comment 'TCP' 2>/dev/null || true")
ssh_exec(ssh, "sudo ufw reload 2>/dev/null || true")
print("[+] Firewall done")

# ==================== Step 6: HTTPS check ====================
print("\n========== Step 6: HTTPS ==========")
out, _ = ssh_exec(ssh, "sudo ls /etc/letsencrypt/live/zouyuhang.online/ 2>/dev/null || echo 'No cert'")
print(f"[SSL cert] {out.strip()}")

# ==================== Step 7: Final Verification ====================
print("\n========== Step 7: Final Verification ==========")
time.sleep(2)

tests = [
    ("Node.js :3001", "curl -s -o /dev/null -w '%{http_code}' http://localhost:3001/cw_dwq"),
    ("Nginx /cw_dwq", "curl -s -o /dev/null -w '%{http_code}' http://localhost/cw_dwq"),
    ("Main site /", "curl -s -o /dev/null -w '%{http_code}' http://localhost/"),
]

for name, cmd in tests:
    out, _ = ssh_exec(ssh, cmd)
    code = out.strip()
    status = "OK" if code == "200" else f"CHECK (HTTP {code})"
    print(f"  [{status}] {name}")

out, _ = ssh_exec(ssh, "ls -la /etc/nginx/conf.d/")
print(f"\n[conf.d files]\n{out}")

out, _ = ssh_exec(ssh, "pm2 status")
print(f"[PM2]\n{out}")

print("\n========== COMPLETE ==========")
print("Main site:   https://zouyuhang.online/")
print("定位器网站:   https://zouyuhang.online/cw_dwq")
print("本地测试:    http://localhost:3001/cw_dwq")

ssh.close()
