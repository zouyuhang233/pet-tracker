import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Read current config
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    conf = f.read().decode('utf-8')
sftp.close()

print("=== Current config (searching for cw_dwq and location /) ===")
for i, line in enumerate(conf.split('\n'), 1):
    if 'cw_dwq' in line or (line.strip().startswith('location /') and 'location /cw_dwq' not in line):
        print(f"  L{i:3d}: {line}")

# Check: is /cw_dwq BEFORE the catch-all location /?
lines = conf.split('\n')
cwdwq_line = None
catchall_line = None
for i, line in enumerate(lines):
    if '/cw_dwq/' in line and 'location' in line and cwdwq_line is None:
        cwdwq_line = i
    if line.strip() == 'location / {' and catchall_line is None:
        catchall_line = i

print(f"\ncw_dwq location at line: {cwdwq_line}")
print(f"catch-all location / at line: {catchall_line}")

if cwdwq_line and catchall_line and cwdwq_line > catchall_line:
    print("PROBLEM: /cw_dwq is AFTER catch-all location / ! Need to move it before.")
elif cwdwq_line and catchall_line and cwdwq_line < catchall_line:
    print("OK: /cw_dwq is before catch-all. But still showing main site...")
    print("Maybe the proxy_pass target is wrong or service is down.")
else:
    print("PROBLEM: /cw_dwq block not found or catch-all not found!")

# Check if the service is actually running and responding
out, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3002/cw_dwq/ 2>/dev/null || echo FAIL")
print(f"\nLocal service test: HTTP {out.strip()}")

out, _ = run(ssh, "curl -s http://127.0.0.1:3002/cw_dwq/ | head -3")
print(f"Local body: {out.strip()[:100]}")

# Check PM2
out, _ = run(ssh, "pm2 status")
print(f"\n{out}")

# ==================== FIX: Rewrite the entire config properly ====================
print("\n=== Rewriting config with /cw_dwq in correct position ===")

# Parse the existing config to extract the SSL server block content
# We need to inject /cw_dwq blocks BEFORE location /

# Strategy: find the SSL server block, and rebuild it with /cw_dwq before location /
conf_lines = conf.split('\n')

# Find the start of the 443 SSL server block
ssl_start = None
for i, line in enumerate(conf_lines):
    if 'listen 443 ssl' in line and 'server_name' in conf_lines[i+1]:
        ssl_start = i
        break

if ssl_start is None:
    print("ERROR: Can't find SSL server block!")
    sys.exit(1)

# Find the end of the SSL server block (last } before next server block or end)
ssl_end = None
for i in range(ssl_start + 1, len(conf_lines)):
    if conf_lines[i].strip() == '}' and (i+1 >= len(conf_lines) or conf_lines[i+1].strip().startswith('server') or conf_lines[i+1].strip().startswith('#')):
        # Check if there are more content after this }
        # We want the LAST } of the server block
        ssl_end = i

# Actually, let's just find the last } in the file that closes the SSL server
# The SSL server block ends with a } that has no indentation (top level)
for i in range(len(conf_lines) - 1, ssl_start, -1):
    if conf_lines[i].strip() == '}':
        ssl_end = i
        break

print(f"SSL server block: lines {ssl_start} to {ssl_end}")

# Extract the SSL block content
ssl_content = conf_lines[ssl_start:ssl_end+1]

# Find the catch-all location / block within the SSL block
catchall_in_ssl = None
for i in range(ssl_start, ssl_end):
    if conf_lines[i].strip() == 'location / {':
        catchall_in_ssl = i
        break

print(f"Catch-all location / at line {catchall_in_ssl}")

# Build new SSL block with /cw_dwq inserted before location /
cwdwq_block = [
    "",
    "    # ====== 定位器 /cw_dwq ======",
    "    location /cw_dwq/ {",
    "        proxy_pass http://127.0.0.1:3002/cw_dwq/;",
    "        proxy_http_version 1.1;",
    "        proxy_set_header Host $host;",
    "        proxy_set_header X-Real-IP $remote_addr;",
    "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
    "        proxy_set_header X-Forwarded-Proto $scheme;",
    "        proxy_set_header Upgrade $http_upgrade;",
    "        proxy_set_header Connection \"upgrade\";",
    "        proxy_cache_bypass $http_upgrade;",
    "        proxy_redirect http://127.0.0.1:3002/ /cw_dwq/;",
    "    }",
    "    location /cw_dwq/ws {",
    "        proxy_pass http://127.0.0.1:8081/;",
    "        proxy_http_version 1.1;",
    "        proxy_set_header Host $host;",
    "        proxy_set_header X-Real-IP $remote_addr;",
    "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
    "        proxy_set_header X-Forwarded-Proto $scheme;",
    "        proxy_set_header Upgrade $http_upgrade;",
    "        proxy_set_header Connection \"Upgrade\";",
    "        proxy_read_timeout 3600s;",
    "        proxy_send_timeout 3600s;",
    "    }",
]

# Remove any existing /cw_dwq blocks from the SSL content
new_ssl_content = []
skip = False
for line in ssl_content:
    if '# ====== 定位器' in line or '# 定位器' in line:
        skip = True; continue
    if skip:
        if line.strip() == '}': skip = False; continue
        if 'location /cw_dwq' in line: continue
        if 'proxy_pass' in line and 'cw_dwq' in line: continue
        if 'proxy_set_header' in line: continue
        if 'proxy_http_version' in line: continue
        if 'proxy_cache_bypass' in line: continue
        if 'proxy_redirect' in line: continue
        if 'proxy_read_timeout' in line: continue
        if 'proxy_send_timeout' in line: continue
        if line.strip() == '': continue
    new_ssl_content.append(line)

# Insert /cw_dwq blocks before location /
if catchall_in_ssl:
    idx = catchall_in_ssl - ssl_start
    new_ssl_content = new_ssl_content[:idx] + cwdwq_block + new_ssl_content[idx:]

# Rebuild the full config
new_conf = conf_lines[:ssl_start] + new_ssl_content + conf_lines[ssl_end+1:]

new_conf_str = '\n'.join(new_conf)
print(f"\nNew config length: {len(new_conf_str)} chars (was {len(conf)})")

# Verify /cw_dwq is before location /
for i, line in enumerate(new_conf.split('\n'), 1):
    if '/cw_dwq/' in line and 'location' in line:
        print(f"  cw_dwq at L{i}: {line.strip()}")
    if line.strip() == 'location / {':
        print(f"  catch-all at L{i}: {line.strip()}")

# Write the new config
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'w') as f:
    f.write(new_conf_str.encode('utf-8'))
sftp.close()
print("\n[OK] Config written")

# Test and reload
out, _ = run(ssh, "sudo nginx -t 2>&1")
print(f"[Nginx test] {out.strip()}")

if "successful" in out:
    run(ssh, "sudo systemctl reload nginx")
    print("[+] Nginx reloaded!")
else:
    print("[-] Nginx config error!")

# ==================== Verify ====================
import time; time.sleep(2)

print("\n=== Verification ===")

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq/ 2>/dev/null || echo FAIL")
print(f"Nginx /cw_dwq -> HTTP {out.strip()}")

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/ 2>/dev/null || echo FAIL")
print(f"Main site / -> HTTP {out.strip()}")

out, _ = run(ssh, "curl -s http://127.0.0.1:3002/cw_dwq/ | head -3")
print(f"Local service: {out.strip()[:80]}")

print(f"\n定位器: https://zouyuhang.online/cw_dwq")
ssh.close()
