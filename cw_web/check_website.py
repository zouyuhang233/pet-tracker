#!/usr/bin/env python3
"""Check website content via HTTP."""
import urllib.request
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Check via Nginx HTTPS
url = "https://zouyuhang.online/cw_dwq/"
print(f"[检查] 访问 {url}")
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html',
})

try:
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        content = resp.read().decode('utf-8', errors='replace')
        print(f"[HTTP] 状态码: {resp.status}")
        print(f"[HTTP] 内容长度: {len(content)} 字节")
        # Check for key elements
        checks = [
            ('宠爱有家', '品牌名称'),
            ('实时追踪', '仪表盘标题'),
            ('服务项目', '服务区块'),
            ('专家团队', '团队区块'),
            ('紧急联系', '紧急联系'),
            ('预约就诊', '预约表单'),
            ('🐾', '爪印图标'),
            ('stepCount', '步数元素'),
            ('leaflet', '地图库'),
        ]
        for keyword, desc in checks:
            found = keyword in content
            print(f"  {'✓' if found else '✗'} {desc} ({keyword})")
except Exception as e:
    print(f"[错误] {e}")
