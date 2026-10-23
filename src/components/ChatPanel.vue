<template>
  <section class="rail-card chat-panel">
    <!-- 页签与在线数 -->
    <header class="chat-head">
      <div class="chat-tabs">
        <button class="chat-tab" :class="{ active: tab === 'chat' }" @click="tab = 'chat'">
          💬 聊天
          <span v-if="chatUnread > 0" class="tab-badge">{{ chatUnread > 99 ? '99+' : chatUnread }}</span>
        </button>
        <button class="chat-tab" :class="{ active: tab === 'voice' }" @click="tab = 'voice'">
          🎙️ 语音
          <span v-if="voiceChat.members.value.length > 0" class="tab-badge live">
            {{ voiceChat.members.value.length }}
          </span>
        </button>
      </div>
      <span class="online-count">{{ onlineCount }} 人在线</span>
    </header>

    <!-- ============ 文字聊天 ============ -->
    <div v-show="tab === 'chat'" class="chat-body">
      <div ref="listEl" class="msg-list">
        <div
          v-for="m in messages"
          :key="m.id"
          class="msg-row"
          :class="{
            system: m.system,
            mine: !m.system && m.from === playerId,
            other: !m.system && m.from !== playerId,
          }"
        >
          <span v-if="m.system" class="sys-text">{{ m.text }}</span>
          <template v-else>
            <div class="msg-head">
              <span class="msg-name">{{ m.from === playerId ? '我' : m.fromName }}</span>
              <span class="msg-time">{{ fmtTime(m.ts) }}</span>
            </div>
            <div class="bubble">
              <span class="msg-text">{{ m.text }}</span>
            </div>
          </template>
        </div>
      </div>
      <div class="msg-input">
        <input
          v-model="draft"
          type="text"
          maxlength="300"
          placeholder="说点什么…"
          @keydown.enter.prevent="send"
        />
        <button type="button" :disabled="!draft.trim()" @click="send">发送</button>
      </div>
      <transition name="toast">
        <div v-if="rejectTip" class="reject-tip">{{ rejectTip }}</div>
      </transition>
    </div>

    <!-- ============ 语音通话 ============ -->
    <div v-show="tab === 'voice'" class="voice-body">
      <div v-if="!voiceChat.secureContext.value" class="voice-warn">
        语音通话需要 HTTPS 安全上下文，当前为 HTTP 访问，浏览器已禁用麦克风。
        请改用 <b>https://</b> 地址打开（自签证书选择「继续访问」即可）。
      </div>

      <div class="voice-actions">
        <button v-if="!voiceChat.inCall.value" class="voice-join" :disabled="!voiceChat.secureContext.value" @click="voiceChat.joinCall()">
          🎙️ 加入通话
        </button>
        <button v-else class="voice-leave" @click="voiceChat.leaveCall()">📴 离开通话</button>
        <button
          v-if="voiceChat.inCall.value"
          class="voice-mute"
          :class="{ muted: voiceChat.selfMuted.value || voiceChat.hostMuted.value }"
          @click="voiceChat.toggleSelfMute()"
        >
          {{ voiceChat.selfMuted.value || voiceChat.hostMuted.value ? '🔇 已静音' : '🎤 麦克风开' }}
        </button>
      </div>

      <transition name="toast">
        <div v-if="voiceChat.notice.value" class="voice-notice">{{ voiceChat.notice.value }}</div>
      </transition>
      <div v-if="voiceChat.errorMsg.value" class="voice-error">{{ voiceChat.errorMsg.value }}</div>

      <!-- 成员列表 -->
      <div class="voice-members">
        <div class="voice-sub">通话成员（{{ voiceChat.members.value.length }}）</div>
        <div v-if="voiceChat.members.value.length === 0" class="voice-empty">还没有人加入通话</div>
        <div
          v-for="m in voiceChat.members.value"
          :key="m.playerId"
          class="voice-member"
          :class="{ speaking: m.speaking }"
        >
          <span class="vm-name">
            {{ m.playerId === playerId ? '我' : m.playerName }}
            <span v-if="m.playerId === roomHostId" class="vm-flag">👑</span>
          </span>
          <span class="vm-tags">
            <span v-if="m.hostMuted" class="vm-tag ban">禁麦</span>
            <span v-else-if="m.selfMuted" class="vm-tag mute">静音</span>
            <span v-if="m.playerId !== playerId" class="vm-tag" :class="m.connected ? 'ok' : 'wait'">
              {{ m.connected ? '已连接' : '连接中' }}
            </span>
            <button
              v-if="isHost && m.playerId !== playerId"
              class="vm-kick"
              title="移出通话"
              @click="voiceChat.hostKick(m.playerId)"
            >✕</button>
          </span>
        </div>
      </div>

      <!-- 房主控制 -->
      <div v-if="isHost && voiceChat.members.value.length > 0" class="voice-host">
        <button class="host-btn" @click="voiceChat.hostMuteAll(true)">🚫 全体禁麦</button>
        <button class="host-btn" @click="voiceChat.hostMuteAll(false)">🔊 解除禁麦</button>
        <button class="host-btn danger" @click="voiceChat.hostCloseCall()">⛔ 关闭通话</button>
      </div>

      <!-- 设备与音量 -->
      <div class="voice-settings">
        <div class="voice-sub">设置</div>
        <label class="voice-field">
          <span>麦克风</span>
          <select :value="voiceChat.selectedMic.value" @change="onMicChange">
            <option v-for="d in voiceChat.mics.value" :key="d.deviceId" :value="d.deviceId">
              {{ d.label || '默认麦克风' }}
            </option>
            <option v-if="voiceChat.mics.value.length === 0" value="">默认麦克风</option>
          </select>
        </label>
        <label class="voice-field">
          <span>输出设备</span>
          <select :value="voiceChat.selectedOutput.value" @change="onOutputChange">
            <option v-for="d in voiceChat.outputs.value" :key="d.deviceId" :value="d.deviceId">
              {{ d.label || '默认输出' }}
            </option>
            <option v-if="voiceChat.outputs.value.length === 0" value="">默认输出</option>
          </select>
        </label>
        <label class="voice-field">
          <span>音量 {{ Math.round(voiceChat.volume.value * 100) }}%</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            :value="voiceChat.volume.value"
            @input="onVolumeChange"
          />
        </label>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue';
import { wsService } from '@/services/websocket';
import { voiceChat } from '@/services/voice';
import { useGameStore } from '@/stores/game';
import type { ChatMessage } from '@/types/game';

const props = defineProps<{
  roomId: string;
  playerId: string;
  playerName: string;
  isHost: boolean;
  players: Record<string, { playerId: string; playerName: string; isBot?: boolean }>;
}>();

const gameStore = useGameStore();
const tab = ref<'chat' | 'voice'>('chat');
const draft = ref('');
const messages = ref<ChatMessage[]>([]);
const chatUnread = ref(0);
const rejectTip = ref('');
const listEl = ref<HTMLElement | null>(null);
let rejectTimer: ReturnType<typeof setTimeout> | null = null;

const onlineCount = computed(() => Object.keys(props.players || {}).length);
const roomHostId = computed(() => gameStore.gameState?.hostId || '');

const fmtTime = (ts: number) => {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const scrollToBottom = async () => {
  await nextTick();
  const el = listEl.value;
  if (el) el.scrollTop = el.scrollHeight;
};

const showReject = (text: string) => {
  rejectTip.value = text;
  if (rejectTimer) clearTimeout(rejectTimer);
  rejectTimer = setTimeout(() => {
    rejectTip.value = '';
  }, 3000);
};

const send = () => {
  const text = draft.value.trim();
  if (!text) return;
  wsService.send({ cmd: 'SendChat', text });
  draft.value = '';
};

const onMicChange = (e: Event) => {
  void voiceChat.changeMic((e.target as HTMLSelectElement).value);
};
const onOutputChange = (e: Event) => {
  void voiceChat.changeOutput((e.target as HTMLSelectElement).value);
};
const onVolumeChange = (e: Event) => {
  voiceChat.setVolume(Number((e.target as HTMLInputElement).value));
};

onMounted(() => {
  voiceChat.init();
  voiceChat.setIdentity(props.playerId, props.playerName, props.isHost);
  void voiceChat.refreshDevices();

  // 历史消息来自状态快照，之后按事件追加
  const history = gameStore.gameState?.chat;
  if (history && history.length > 0) {
    messages.value = history.slice(-100);
    void scrollToBottom();
  }

  wsService.setChatCallback((message) => {
    messages.value.push(message);
    if (messages.value.length > 200) {
      messages.value.splice(0, messages.value.length - 200);
    }
    if (tab.value === 'chat') {
      void scrollToBottom();
    } else {
      chatUnread.value += 1;
    }
  });

  wsService.setChatRejectedCallback((payload) => {
    showReject(payload.reason || '发送失败');
  });
});

// 切回聊天页签时清零未读并滚到底部
watch(tab, (value) => {
  if (value === 'chat') {
    chatUnread.value = 0;
    void scrollToBottom();
  }
});

// 身份（尤其房主标志）可能晚于挂载才从服务端状态到达，持续同步给语音引擎
watch(
  () => [props.playerId, props.playerName, props.isHost],
  () => {
    voiceChat.setIdentity(props.playerId, props.playerName, props.isHost);
  }
);

// 服务端快照里的语音成员表变化时刷新成员列表（兜底，与引擎内部监听等价）
watch(
  () => gameStore.gameState?.voice,
  () => voiceChat.syncMembers(),
  { deep: true }
);

// 新消息到达且正处于聊天页签时保持贴底
watch(
  () => messages.value.length,
  () => {
    if (tab.value === 'chat') void scrollToBottom();
  }
);

// 快照里带来新历史（晚加入 / 重连）时合并去重
watch(
  () => gameStore.gameState?.chat,
  (history) => {
    if (!history || history.length === 0) return;
    const existing = new Set(messages.value.map((m) => m.id));
    const fresh = history.filter((m) => !existing.has(m.id));
    if (fresh.length === 0) return;
    messages.value.push(...fresh);
    if (messages.value.length > 200) {
      messages.value.splice(0, messages.value.length - 200);
    }
    if (tab.value === 'chat') void scrollToBottom();
  },
  { deep: true }
);

onBeforeUnmount(() => {
  wsService.setChatCallback(() => {});
  wsService.setChatRejectedCallback(() => {});
  if (rejectTimer) clearTimeout(rejectTimer);
  // 不断开语音通话：单例引擎跨页面保活，大厅 ↔ 游戏页跳转不中断
});
</script>

<style scoped>
.chat-panel {
  /* 卡片本身是固定尺寸的容器：头尾不动，中间消息区在卡片内滚动，
     消息再多也只让 .msg-list 出现滚动条，不会把整张卡片撑高 */
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  max-height: 100%;
  padding: 0;
  overflow: hidden;
}

/* ---------- 头部页签 ---------- */
.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid #eef1f5;
  flex-shrink: 0;
}

.chat-tabs {
  display: flex;
  gap: 4px;
}

.chat-tab {
  position: relative;
  border: none;
  background: transparent;
  padding: 4px 8px;
  font-size: 12px;
  color: #64748b;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
}

.chat-tab.active {
  background: #e8eefc;
  color: #1d4ed8;
  font-weight: 700;
}

.tab-badge {
  display: inline-block;
  min-width: 15px;
  margin-left: 3px;
  padding: 0 3px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  font-size: 10px;
  line-height: 15px;
  text-align: center;
}

.tab-badge.live {
  background: #22c55e;
}

.online-count {
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
}

/* ---------- 聊天主体 ---------- */
.chat-body {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.msg-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 8px 4px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg-row {
  display: flex;
  flex-direction: column;
  max-width: 100%;
}

.msg-row.system {
  text-align: center;
  align-items: center;
}

/* 自己的发言靠右，其他人的发言靠左（微信/QQ 式对齐） */
.msg-row.mine {
  align-items: flex-end;
}

.msg-row.other {
  align-items: flex-start;
}

.sys-text {
  font-size: 11px;
  color: #94a3b8;
}

/* 名称与时间在气泡之外，不上底色 */
.msg-head {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 0 2px 2px;
  font-size: 10px;
  line-height: 1.4;
  color: #94a3b8;
  background: transparent;
  max-width: 100%;
}

.msg-name {
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-time {
  flex-shrink: 0;
}

.bubble {
  max-width: 80%;
  padding: 5px 8px;
  border-radius: 8px;
  background: #f1f5f9;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
  text-align: left;
}

/* 气泡朝发送侧收角，贴近微信/QQ 观感 */
.msg-row.other .bubble {
  border-top-left-radius: 2px;
}

.msg-row.mine .bubble {
  background: #dbeafe;
  border-top-right-radius: 2px;
}

.msg-text {
  display: block;
  text-align: left;
}

.msg-input {
  display: flex;
  gap: 6px;
  padding: 8px;
  border-top: 1px solid #eef1f5;
  flex-shrink: 0;
}

.msg-input input {
  flex: 1;
  min-width: 0;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 12px;
  outline: none;
}

.msg-input input:focus {
  border-color: #93c5fd;
}

.msg-input button {
  border: none;
  background: #2563eb;
  color: #fff;
  border-radius: 6px;
  padding: 0 10px;
  font-size: 12px;
  cursor: pointer;
}

.msg-input button:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.reject-tip {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 52px;
  padding: 5px 8px;
  border-radius: 6px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 11px;
  text-align: center;
}

/* ---------- 语音主体 ---------- */
.voice-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.voice-warn {
  padding: 7px 8px;
  border-radius: 6px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #92400e;
  font-size: 11px;
  line-height: 1.6;
}

.voice-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.voice-actions button {
  flex: 1 1 auto;
  border: none;
  border-radius: 6px;
  padding: 7px 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.voice-join {
  background: #16a34a;
  color: #fff;
}

.voice-join:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.voice-leave {
  background: #ef4444;
  color: #fff;
}

.voice-mute {
  background: #e2e8f0;
  color: #334155;
}

.voice-mute.muted {
  background: #fee2e2;
  color: #b91c1c;
}

.voice-notice {
  padding: 5px 8px;
  border-radius: 6px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
  font-size: 11px;
}

.voice-error {
  padding: 5px 8px;
  border-radius: 6px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 11px;
}

.voice-sub {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}

.voice-empty {
  font-size: 11px;
  color: #94a3b8;
}

.voice-members {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.voice-member {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 4px 6px;
  border-radius: 6px;
  background: #f8fafc;
  border: 1px solid transparent;
  font-size: 12px;
}

.voice-member.speaking {
  border-color: #22c55e;
  background: #f0fdf4;
}

.vm-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vm-flag {
  margin-left: 2px;
}

.vm-tags {
  display: flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
}

.vm-tag {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #e2e8f0;
  color: #475569;
}

.vm-tag.ban {
  background: #fee2e2;
  color: #b91c1c;
}

.vm-tag.mute {
  background: #fef3c7;
  color: #92400e;
}

.vm-tag.ok {
  background: #dcfce7;
  color: #15803d;
}

.vm-tag.wait {
  background: #e0e7ff;
  color: #3730a3;
}

.vm-kick {
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  font-size: 11px;
  padding: 0 2px;
}

.vm-kick:hover {
  color: #ef4444;
}

.voice-host {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.host-btn {
  flex: 1 1 auto;
  border: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 6px;
  padding: 5px 4px;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.host-btn.danger {
  border-color: #fecaca;
  color: #b91c1c;
}

.voice-settings {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-top: 4px;
  border-top: 1px solid #eef1f5;
}

.voice-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: #475569;
}

.voice-field select {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 11px;
  background: #fff;
  max-width: 100%;
}

.voice-field input[type='range'] {
  width: 100%;
}

/* ---------- 动画 ---------- */
.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
}
</style>
