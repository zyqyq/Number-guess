<template>
  <div class="admin-page">
    <!-- 来源校验中 -->
    <div v-if="checking" class="admin-gate">
      <div class="gate-card">
        <div class="gate-spinner"></div>
        <p class="gate-text">正在校验访问来源…</p>
      </div>
    </div>

    <!-- 非本机 / 口令错误 -->
    <div v-else-if="denied" class="admin-gate">
      <div class="gate-card">
        <div class="gate-icon">⛔</div>
        <h2 class="gate-title">拒绝访问</h2>
        <p class="gate-text">{{ deniedReason || '管理后台仅允许在本机访问。' }}</p>
        <ul class="gate-hint">
          <li>请在服务器本机打开 <code>http://localhost:8000/admin</code></li>
          <li>当前来源：<code>{{ currentOrigin }}</code></li>
          <li>本地访问默认仅限回环地址（127.0.0.1 / ::1），可在 <code>config.json</code> 关闭该限制</li>
          <li>IP 黑名单中的来源一律拒绝，优先级高于仅本机开关</li>
        </ul>
        <div class="gate-actions">
          <button class="ghost-btn" @click="checkAccess">重新检测</button>
          <button class="ghost-btn" @click="goHome">返回游戏首页</button>
        </div>
      </div>
    </div>

    <!-- 管理控制台 -->
    <template v-else>
      <header class="admin-header">
        <div class="brand">
          <div class="brand-mark">盾</div>
          <div class="brand-text">
            <h1 class="brand-title">系统管理后台</h1>
            <p class="brand-sub">猜数字桌游 · 本机运维控制台</p>
          </div>
        </div>

        <div class="header-right">
          <span
            class="local-pill"
            :class="snapshot?.security.localOnly === false ? 'pill-open' : ''"
            :title="snapshot?.security.localOnly === false ? '配置文件中已关闭仅本机限制，请注意安全' : '管理接口仅对本机回环地址开放'"
          >
            {{ snapshot?.security.localOnly === false ? '仅本机：关' : '仅限本机' }}
          </span>
          <span class="conn-pill" :class="connected ? 'on' : 'off'">
            <span class="conn-dot"></span>
            {{ connected ? '已连接' : '重连中…' }}
          </span>
          <span class="server-clock mono">{{ fmtTime(snapshot?.serverTime) }}</span>
          <button class="ghost-btn" @click="goHome">退出后台</button>
        </div>
      </header>

      <nav class="admin-tabs">
        <button class="tab" :class="{ active: tab === 'terminals' }" @click="tab = 'terminals'">
          连入终端<span class="tab-count">{{ snapshot?.terminals.length ?? 0 }}</span>
        </button>
        <button class="tab" :class="{ active: tab === 'rooms' }" @click="tab = 'rooms'">
          房间管理<span class="tab-count">{{ snapshot?.rooms.length ?? 0 }}</span>
        </button>
        <button class="tab" :class="{ active: tab === 'security' }" @click="tab = 'security'">
          安全设置<span class="tab-count">{{ securityCount }}</span>
        </button>
        <button class="tab" :class="{ active: tab === 'system' }" @click="tab = 'system'">
          系统管理
        </button>
      </nav>

      <main class="admin-content">
        <p v-if="!snapshot" class="loading-tip">正在载入管理数据…</p>
        <template v-else>
          <AdminTerminals
            v-if="tab === 'terminals'"
            :terminals="snapshot.terminals"
            :server-time="snapshot.serverTime"
            @kick="handleKick"
          />
          <AdminRooms v-else-if="tab === 'rooms'" :rooms="snapshot.rooms" @action="handleRoomAction" />
          <AdminSecurity
            v-else-if="tab === 'security'"
            :security="snapshot.security"
            @add-ip="(ip: string) => send({ cmd: 'AdminAddIp', ip })"
            @remove-ip="(ip: string) => send({ cmd: 'AdminRemoveIp', ip })"
            @add-word="(word: string) => send({ cmd: 'AdminAddWord', word })"
            @remove-word="(word: string) => send({ cmd: 'AdminRemoveWord', word })"
            @reload-config="handleReloadConfig"
          />
          <AdminSystem
            v-else
            :system="snapshot.system"
            :events="snapshot.events"
            :rooms="snapshot.rooms"
            :server-time="snapshot.serverTime"
          />
        </template>
      </main>

      <transition name="toast">
        <div v-if="notice" class="admin-toast">{{ notice }}</div>
      </transition>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import AdminTerminals from '@/components/AdminTerminals.vue';
import AdminRooms from '@/components/AdminRooms.vue';
import AdminSystem from '@/components/AdminSystem.vue';
import AdminSecurity from '@/components/AdminSecurity.vue';
import type { AdminAccessInfo, AdminSnapshot } from '@/types/admin';
import { getClientId } from '@/services/presence';
import { fmtTime } from '@/utils/admin';

type TabKey = 'terminals' | 'rooms' | 'security' | 'system';

const router = useRouter();

const checking = ref(true);
const denied = ref(false);
const deniedReason = ref('');
const auth = ref<AdminAccessInfo | null>(null);
const snapshot = ref<AdminSnapshot | null>(null);
const tab = ref<TabKey>('terminals');
const connected = ref(false);
const notice = ref('');
const currentOrigin = `${window.location.origin}/admin`;

const securityCount = computed(() => {
  const s = snapshot.value?.security;
  return (s?.ipBlacklist.length ?? 0) + (s?.bannedWords.length ?? 0);
});

let socket: WebSocket | null = null;
let retryTimer: number | undefined;
let noticeTimer: number | undefined;
let disposed = false;

const showNotice = (text: string) => {
  notice.value = text;
  if (noticeTimer !== undefined) window.clearTimeout(noticeTimer);
  noticeTimer = window.setTimeout(() => {
    notice.value = '';
  }, 2600);
};

const goHome = () => {
  disposeSocket();
  router.push('/');
};

const disposeSocket = () => {
  if (retryTimer !== undefined) {
    window.clearTimeout(retryTimer);
    retryTimer = undefined;
  }
  if (socket) {
    socket.onclose = null;
    socket.close(1000, 'leave_admin');
    socket = null;
  }
  connected.value = false;
};

const connectAdminSocket = () => {
  if (disposed || !auth.value) return;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/ws/admin?clientId=${getClientId()}`;

  socket = new WebSocket(url);

  socket.onopen = () => {
    connected.value = true;
    // 首帧即口令校验（服务端要求先收到 AdminAuth 才推数据）
    socket?.send(
      JSON.stringify({ cmd: 'AdminAuth', user: auth.value?.adminUser, room: auth.value?.adminRoom })
    );
  };

  socket.onmessage = (event) => {
    let data: any;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (data.event === 'Event_AdminSnapshot') {
      snapshot.value = data.payload as AdminSnapshot;
    } else if (data.event === 'Event_AdminDenied') {
      denied.value = true;
      deniedReason.value = data.payload?.reason || '管理口令校验失败';
      disposeSocket();
    }
  };

  socket.onclose = () => {
    connected.value = false;
    socket = null;
    if (!disposed && !denied.value) {
      retryTimer = window.setTimeout(connectAdminSocket, 3000);
    }
  };
};

const checkAccess = async () => {
  checking.value = true;
  denied.value = false;
  deniedReason.value = '';
  disposeSocket();
  snapshot.value = null;

  try {
    const res = await fetch('/api/admin/access', { cache: 'no-store' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      denied.value = true;
      deniedReason.value = body?.message || '管理后台仅允许在本机访问。';
      return;
    }
    auth.value = (await res.json()) as AdminAccessInfo;
    connectAdminSocket();
  } catch {
    denied.value = true;
    deniedReason.value = '无法连接到后端服务，请确认服务已启动。';
  } finally {
    checking.value = false;
  }
};

const send = (payload: Record<string, unknown>) => {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    showNotice('管理通道未连接，操作未发送');
    return;
  }
  socket.send(JSON.stringify(payload));
};

const handleKick = (payload: { clientId: string; nickname: string }) => {
  send({ cmd: 'AdminKickTerminal', clientId: payload.clientId });
  showNotice(`已发送断开指令：${payload.nickname || payload.clientId.slice(0, 8)}`);
};

const handleRoomAction = (payload: { cmd: string; roomId: string; playerId?: string }) => {
  send(payload);
  const labels: Record<string, string> = {
    AdminResetRoom: `已重置房间 ${payload.roomId}`,
    AdminCloseRoom: `已关闭房间 ${payload.roomId}`,
    AdminKickPlayer: `已将该玩家移出房间 ${payload.roomId}`,
  };
  showNotice(labels[payload.cmd] || '指令已发送');
};

const handleReloadConfig = () => {
  send({ cmd: 'AdminReloadConfig' });
  showNotice('已从 config.json 重载配置');
};

onMounted(() => {
  checkAccess();
});

onBeforeUnmount(() => {
  disposed = true;
  disposeSocket();
  if (noticeTimer !== undefined) window.clearTimeout(noticeTimer);
});
</script>

<style scoped>
.admin-page {
  --admin-bg: #eef1f6;
  --admin-text: #1e293b;
  --admin-muted: #64748b;
  --admin-border: #e2e8f0;
  --admin-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 20px rgba(15, 23, 42, 0.04);
  min-height: 100vh;
  background: var(--admin-bg);
  color: var(--admin-text);
  text-align: left;
  font-size: 13px;
}

/* ---------- 校验 / 拒绝 ---------- */
.admin-gate {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  box-sizing: border-box;
}

.gate-card {
  width: 100%;
  max-width: 520px;
  padding: 36px 40px;
  text-align: center;
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(15, 23, 42, 0.1);
}

.gate-icon {
  font-size: 34px;
  line-height: 1;
  margin-bottom: 12px;
}

.gate-title {
  margin: 0 0 10px;
  font-size: 20px;
  font-weight: 600;
  color: #dc2626;
}

.gate-text {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--admin-muted);
}

.gate-hint {
  margin: 0 0 22px;
  padding: 14px 16px;
  text-align: left;
  font-size: 12px;
  line-height: 2;
  color: var(--admin-muted);
  background: #f8fafc;
  border-radius: 10px;
  list-style: none;
}

.gate-hint code {
  padding: 1px 6px;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12px;
  color: #0f172a;
  background: #eef2f7;
  border-radius: 4px;
}

.gate-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.gate-spinner {
  width: 26px;
  height: 26px;
  margin: 0 auto 14px;
  border: 3px solid #e2e8f0;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* ---------- 顶栏 ---------- */
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  height: 62px;
  /* 左右留白与下方内容容器（max-width 1440 + 24 内边距）对齐 */
  padding: 0 max(24px, calc((100vw - 1440px) / 2 + 24px));
  background: #fff;
  border-bottom: 1px solid var(--admin-border);
  position: sticky;
  top: 0;
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  font-size: 15px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.32);
}

.brand-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--admin-text);
}

.brand-sub {
  margin: 0;
  font-size: 11px;
  color: var(--admin-muted);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.local-pill {
  padding: 4px 10px;
  font-size: 11px;
  color: #92400e;
  background: #fef3c7;
  border-radius: 999px;
}

.local-pill.pill-open {
  color: #b91c1c;
  background: #fee2e2;
}

.conn-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 11px;
  border-radius: 999px;
}

.conn-pill.on {
  color: #15803d;
  background: #dcfce7;
}

.conn-pill.off {
  color: #b45309;
  background: #fef3c7;
}

.conn-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.server-clock {
  font-size: 12px;
  color: var(--admin-muted);
}

.mono {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

/* ---------- 标签页 ---------- */
.admin-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 24px 0;
  max-width: 1440px;
  margin: 0 auto;
  box-sizing: border-box;
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 18px;
  font-size: 13px;
  color: var(--admin-muted);
  background: transparent;
  border: none;
  border-radius: 9px 9px 0 0;
  cursor: pointer;
  transition: all 0.15s ease;
}

.tab:hover {
  color: var(--admin-text);
  background: rgba(255, 255, 255, 0.7);
}

.tab.active {
  color: #3730a3;
  font-weight: 600;
  background: #fff;
  box-shadow: 0 -1px 0 var(--admin-border), 1px 0 0 var(--admin-border), -1px 0 0 var(--admin-border);
}

.tab-count {
  padding: 0 6px;
  font-size: 11px;
  font-weight: 500;
  color: #475569;
  background: #eef2f7;
  border-radius: 999px;
  line-height: 17px;
}

.tab.active .tab-count {
  color: #fff;
  background: #6366f1;
}

.admin-content {
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 24px 40px;
  box-sizing: border-box;
}

.loading-tip {
  margin: 0;
  padding: 60px 0;
  text-align: center;
  color: var(--admin-muted);
}

.ghost-btn {
  padding: 7px 14px;
  font-size: 12px;
  color: #334155;
  background: #fff;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ghost-btn:hover {
  border-color: #94a3b8;
  background: #f8fafc;
}

.admin-toast {
  position: fixed;
  left: 50%;
  bottom: 32px;
  transform: translateX(-50%);
  padding: 10px 20px;
  font-size: 12px;
  color: #fff;
  background: rgba(15, 23, 42, 0.9);
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25);
  z-index: 50;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 8px);
}
</style>
