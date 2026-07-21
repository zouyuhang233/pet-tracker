import paramiko, sys, os, zipfile, io, time

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"
OUR_PORT = 3002

def run(ssh, cmd, timeout=30):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

print("[*] Connecting...", flush=True)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
print("[+] Connected!", flush=True)

# ---- Step 1: Upload files ----
print("[*] Uploading files...", flush=True)
zip_path = r"C:\Users\zyh\Desktop\fix_cw_dwq.zip"
with open(zip_path, 'rb') as f:
    zip_data = f.read()

zf = zipfile.ZipFile(io.BytesIO(zip_data), 'r')
sftp = ssh.open_sftp()
run(ssh, "sudo mkdir -p /opt/location-server/public && sudo chown root:root /opt/location-server")
for fn in zf.namelist():
    data = zf.read(fn)
    rp = f"/opt/location-server/{fn}"
    rd = os.path.dirname(rp)
    if rd and rd != '/opt/location-server':
        try: sftp.stat(rd)
        except: run(ssh, f"sudo mkdir -p {rd}")
    with sftp.open(rp, 'wb') as rf: rf.write(data)
    run(ssh, f"sudo chown root:root {rp}")
sftp.close(); zf.close()
print("[+] Files uploaded!", flush=True)

# ---- Step 2: Set port & install deps (background) ----
sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'r') as f:
    js = f.read().decode('utf-8')
sftp.close()
js = js.replace('const WEB_PORT = 3000;', f'const WEB_PORT = {OUR_PORT};')
sftp = ssh.open_sftp()
with sftp.open('/opt/location-server/server.js', 'w') as f:
    f.write(js.encode('utf-8'))
sftp.close()
print(f"[+] Port set to {OUR_PORT}", flush=True)

# npm install in background
run(ssh, "cd /opt/location-server && nohup npm install --production --prefer-offline > /tmp/npm.log 2>&1 &")
print("[*] npm install running in background...", flush=True)

# ---- Step 3: Start Node service immediately (might fail if deps not ready) ----
run(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")
run(ssh, f"cd /opt/location-server && pm2 start server.js --name 'location-server'")
run(ssh, "pm2 save")
time.sleep(3)

out, _ = run(ssh, "pm2 status")
print(f"[PM2]\n{out}", flush=True)

out, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{OUR_PORT}/cw_dwq 2>/dev/null || echo 'FAIL'")
print(f"[Local test] HTTP {out.strip()}", flush=True)

# ---- Step 4: Fix Nginx ----
print("[*] Fixing Nginx...", flush=True)
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    conf = f.read().decode('utf-8')
sftp.close()

# Remove old cw_dwq blocks if any
if '/cw_dwq' in conf:
    lines = conf.split('\n')
    new_lines, skip = [], False
    for line in lines:
        if '# ====== 定位器' in line or '# 定位器' in line:
            skip = True; continue
        if skip and line.strip().startswith('#'): continue
        if skip and 'location /cw_dwq' in line: continue
        if skip and 'proxy_pass' in line and 'cw_dwq' not in line: skip = False
        if skip and line.strip() == '}': skip = False; continue
        new_lines.append(line)
    conf = '\n'.join(new_lines)

# Insert /cw_dwq before last }
block = f"""
    # ====== 定位器 /cw_dwq ======
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

idx = conf.rfind('}')
if idx > 0:
    conf = conf[:idx] + block + '\n}' + conf[idx+1:]
else:
    conf += block

sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
    f.write(conf.encode('utf-8'))
sftp.close()

out, _ = run(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test] {out}", flush=True)

if "successful" in out:
    run(ssh, "sudo systemctl reload nginx")
    print("[+] Nginx reloaded!", flush=True)
else:
    print("[-] Nginx error! Restoring backup...", flush=True)
    for ext in ['.bak', '.bak-deploy', '.bak2']:
        ok, _ = run(ssh, f"sudo test -f /etc/nginx/conf.d/ridge-guardian.conf{ext} && echo YES || echo NO")
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
            print(f"[+] Restored from {ext}", flush=True)
            break

# ---- Step 5: Final check ----
print("\n========== Result ==========", flush=True)
time.sleep(2)

for name, cmd in [
    (f"Node :{OUR_PORT}", f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{OUR_PORT}/cw_dwq"),
    ("Nginx /cw_dwq", "curl -s -o /dev/null -w '%{http_code}' http://localhost/cw_dwq"),
    ("HTTPS /cw_dwq", "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq"),
    ("Main site /", "curl -sk -o /dev/null -w '%{http_code}' https://localhost/"),
]:
    try:
        o, _ = run(ssh, cmd)
        code = o.strip()
        tag = "OK" if code == "200" else f"HTTP {code}"
    except:
        tag = "ERR"
    print(f"  [{tag}] {name}", flush=True)

out, _ = run(ssh, "pm2 status")
print(f"\n[PM2]\n{out}", flush=True)

print(f"\n定位器: https://zouyuhang.online/cw_dwq", flush=True)
print("Done!", flush=True)
ssh.close()
