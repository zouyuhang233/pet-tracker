import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=20):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    out = sout.read().decode('utf-8', errors='replace')
    err = serr.read().decode('utf-8', errors='replace')
    return out, err

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Use --nostream to avoid infinite output
out, _ = run(ssh, "pm2 logs location-server --lines 20 --nostream 2>&1")
print("=== PM2 Logs ===")
print(out[:2000])

out, _ = run(ssh, "ls /opt/location-server/node_modules/express/package.json 2>/dev/null && echo EXPRESS_OK || echo NO_EXPRESS")
print(f"Express: {out.strip()}")

out, _ = run(ssh, "ls /opt/location-server/node_modules/ws/package.json 2>/dev/null && echo WS_OK || echo NO_WS")
print(f"WS: {out.strip()}")

out, _ = run(ssh, "cat /opt/location-server/package.json")
print(f"\n=== package.json ===\n{out}")

out, _ = run(ssh, "cd /opt/location-server && node -e \"try { require('express'); console.log('express OK') } catch(e) { console.log(e.message) }\"")
print(f"Express test: {out.strip()}")

out, _ = run(ssh, "cd /opt/location-server && node -e \"try { require('ws'); console.log('ws OK') } catch(e) { console.log(e.message) }\"")
print(f"WS test: {out.strip()}")

# Try to start and capture error
out, _ = run(ssh, "cd /opt/location-server && timeout 3 node server.js 2>&1 || true")
print(f"\n=== Direct run ===\n{out[:1000]}")

ssh.close()
