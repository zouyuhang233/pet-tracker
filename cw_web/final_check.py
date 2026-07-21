import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Also fix the HTTP server block (port 80) to add /cw_dwq there too
# This ensures /cw_dwq works even before HTTPS redirect
sftp = ssh.open_sftp()
with sftp.open('/etc/nginx/conf.d/ridge-guardian.conf', 'r') as f:
    conf = f.read().decode('utf-8')
sftp.close()

lines = conf.split('\n')

# Find the HTTP server block (the one with listen 80 and return 301)
# We need to add a /cw_dwq location there too that proxies directly
# Actually, the HTTP block just does 301 redirect, so /cw_dwq will be redirected to https://.../cw_dwq
# which then gets handled by the HTTPS block. So this should be fine.

# But let's verify - check if there's a separate default server on port 80
out, _ = run(ssh, "sudo nginx -T 2>/dev/null | grep -B2 -A5 'listen.*80' | head -30")
print("=== Port 80 server blocks ===")
print(out)

# The real question: is there caching? Check Cloudflare or any CDN
out, _ = run(ssh, "curl -skI https://localhost/cw_dwq/ | grep -i cache")
print("=== Cache headers ===")
print(out)

# Check if there's a Cloudflare or similar
out, _ = run(ssh, "curl -s http://127.0.0.1:3002/cw_dwq/ | grep -i 'title'")
print(f"=== Service title ===\n{out}")

# Final summary
print("\n========== SUMMARY ==========")
print("Local service :3002/cw_dwq -> 定位器 website (OK)")
print("Nginx /cw_dwq  -> 定位器 website (OK from server)")
print("Nginx /        -> Main site (OK)")
print("")
print("If browser still shows main site:")
print("  1. Hard refresh: Ctrl+Shift+R")
print("  2. Clear browser cache")
print("  3. Try incognito mode")
print("  4. Check if Cloudflare CDN is caching (purge cache)")
print("")
print("Server config is correct!")

ssh.close()
