import paramiko, sys, os, zipfile, io

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Upload zip
print("[*] Uploading zip...", flush=True)
zip_path = r"C:\Users\zyh\Desktop\fix_cw_dwq_v2.zip"
with open(zip_path, 'rb') as f:
    zip_data = f.read()

zf = zipfile.ZipFile(io.BytesIO(zip_data), 'r')
print(f"    Zip contents: {zf.namelist()}", flush=True)

sftp = ssh.open_sftp()
for fn in zf.namelist():
    data = zf.read(fn)
    rp = f"/opt/location-server/{fn}"
    rd = os.path.dirname(rp)
    if rd and rd != '/opt/location-server':
        try: sftp.stat(rd)
        except: run(ssh, f"sudo mkdir -p {rd}")
    with sftp.open(rp, 'wb') as rf: rf.write(data)
    run(ssh, f"sudo chown root:root {rp}")
    print(f"    [OK] {fn}", flush=True)

sftp.close()
zf.close()
print("[+] Upload complete!", flush=True)

# Verify public files
out, _ = run(ssh, "ls -la /opt/location-server/public/")
print(f"\n[public/]\n{out}")

out, _ = run(ssh, "head -3 /opt/location-server/public/index.html")
print(f"[index.html]\n{out}")

# Restart service
print("\n[*] Restarting service...", flush=True)
run(ssh, "pm2 stop location-server 2>/dev/null; pm2 delete location-server 2>/dev/null; true")
out, _ = run(ssh, "cd /opt/location-server && pm2 start server.js --name 'location-server' 2>&1")
print(f"    {out.strip()}", flush=True)
run(ssh, "pm2 save 2>/dev/null || true")

import time; time.sleep(4)

out, _ = run(ssh, "pm2 status")
print(f"[PM2]\n{out}", flush=True)

# Test
out, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3002/cw_dwq/ 2>/dev/null || echo FAIL")
print(f"\n[Test /cw_dwq/] HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -s http://127.0.0.1:3002/cw_dwq/ | head -5")
print(f"[Body]\n{out[:200]}", flush=True)

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/cw_dwq/ 2>/dev/null || echo FAIL")
print(f"[Nginx /cw_dwq] HTTP {out.strip()}", flush=True)

out, _ = run(ssh, "curl -sk -o /dev/null -w '%{http_code}' https://localhost/ 2>/dev/null || echo FAIL")
print(f"[Main site /] HTTP {out.strip()}", flush=True)

print(f"\n定位器: https://zouyuhang.online/cw_dwq", flush=True)
print("Done!", flush=True)
ssh.close()
