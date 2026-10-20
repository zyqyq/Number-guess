#!/bin/bash

# =============================================================================
# 生成本地自签名证书（HTTPS）
# 用途：浏览器只有在安全上下文（HTTPS 或 localhost）才允许调用 getUserMedia，
#       语音通话因此需要 HTTPS。局域网部署用自签证书即可，无需购买域名证书。
# 用法：./scripts/gen-cert.sh          # 已存在则提示手动确认后覆盖
# 输出：certs/server.crt（证书） + certs/server.key（私钥） + certs/server.cnf
# 提示：换了网络环境（本机 IP 变化）后重新执行一次即可，客户端需重新信任证书。
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

CERT_DIR="$PROJECT_ROOT/certs"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"
CNF_FILE="$CERT_DIR/server.cnf"

echo "=========================================="
echo "  生成 HTTPS 自签名证书"
echo "=========================================="

mkdir -p "$CERT_DIR"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "⚠️  证书已存在：$CERT_FILE"
    read -r -p "是否重新生成？[y/N] " answer
    case "$answer" in
        y|Y|yes|YES) echo "继续生成..." ;;
        *) echo "已取消"; exit 0 ;;
    esac
fi

# ---------------- 收集需要写入 SAN 的地址 ----------------
DNS_NAMES=("localhost")
IP_LIST=("127.0.0.1" "::1")

# 本机当前所有 IPv4（排除回环与链路本地）
while IFS= read -r ip; do
    [ -n "$ip" ] && IP_LIST+=("$ip")
done < <(ifconfig 2>/dev/null | grep -oE 'inet [0-9.]+' | awk '{print $2}' \
    | grep -vE '^127\.|^169\.254\.' | sort -u)

# 常见内网 / Tailscale 网段兜底：当前没启用、之后可能启用
for ip in 192.168.1.1 192.168.2.1 192.168.2.2 192.168.31.1 10.0.0.1; do
    found=0
    for exist in "${IP_LIST[@]}"; do
        [ "$exist" = "$ip" ] && found=1 && break
    done
    [ "$found" -eq 0 ] && IP_LIST+=("$ip")
done

# ---------------- 生成 openssl 配置 ----------------
{
    echo "[req]"
    echo "distinguished_name = req_distinguished_name"
    echo "x509_extensions = v3_req"
    echo "prompt = no"
    echo ""
    echo "[req_distinguished_name]"
    echo "CN = guess-number.local"
    echo "O = Guess Number Game"
    echo ""
    echo "[v3_req]"
    echo "subjectAltName = @alt_names"
    echo "keyUsage = digitalSignature, keyEncipherment"
    echo "extendedKeyUsage = serverAuth"
    echo ""
    echo "[alt_names]"
    idx=1
    for name in "${DNS_NAMES[@]}"; do
        echo "DNS.$idx = $name"
        idx=$((idx + 1))
    done
    idx=1
    for ip in "${IP_LIST[@]}"; do
        echo "IP.$idx = $ip"
        idx=$((idx + 1))
    done
} > "$CNF_FILE"

echo "📝 SAN 地址："
grep -E '^(DNS|IP)\.' "$CNF_FILE" | sed 's/^/    /'

# ---------------- 生成证书（RSA 2048，825 天） ----------------
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -days 825 \
    -config "$CNF_FILE" >/dev/null 2>&1

chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo ""
echo "✅ 证书已生成："
echo "    证书：$CERT_FILE"
echo "    私钥：$KEY_FILE"
echo "    有效期：825 天"
echo ""
echo "🚀 启动 HTTPS 服务："
echo "    cd $PROJECT_ROOT && ./venv/bin/python -m uvicorn backend.main:app \\"
echo "        --host 0.0.0.0 --port 8000 \\"
echo "        --ssl-certfile certs/server.crt --ssl-keyfile certs/server.key"
echo ""
echo "💡 客户端首次访问会提示证书不受信任，选择「高级 → 继续访问」即可；"
echo "   局域网内每台设备只需确认一次。"
