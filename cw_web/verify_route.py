import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Test 1: Local service (bypass Nginx)
out, _ = run(ssh, "curl -s http://127.0.0.1:3002/cw_dwq/ | head -5")
print("=== Local :3002/cw_dwq ===")
print(out)

# Test 2: Through Nginx
out, _ = run(ssh, "curl -sk https://localhost/cw_dwq/ | head -10")
print("=== Nginx /cw_dwq ===")
print(out)

# Test 3: Check what the main site returns
out, _ = run(ssh, "curl -sk https://localhost/ | head -5")
print("=== Nginx / (main site) ===")
print(out)

# Test 4: Check response headers to see which server handles it
out, _ = run(ssh, "curl -sk -I https://localhost/cw_dwq/ 2>/dev/null | head -10")
print("=== Nginx /cw_dwq headers ===")
print(out)

# Test 5: Maybe there's a cache issue - check Nginx config one more time
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    lines = f.read().decode('utf-8').split('\n')
sftp.close()

print("\n=== Config lines 220-250 ===")
for i in range(219, min(250, len(lines))):
    print(f"  L{i+1}: {lines[i]}")

# Check if there's another config file that might override
out, _ = run(ssh, "sudo nginx -T 2>/dev/null | grep -n 'server_name.*zouyuhang' | head -10")
print(f"\n=== All server blocks for zouyuhang ===")
print(out)

out, _ = run(ssh, "sudo nginx -T 2>/dev/null | grep -n 'location /cw_dwq' | head -10")
print(f"\n=== All /cw_dwq locations ===")
print(out)

out, _ = run(ssh, "sudo nginx -T 2>/dev/null | grep -n 'location / {' | head -10")
print(f"\n=== All catch-all location / ===")
print(out)

ssh.close()
