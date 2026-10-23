<template>
  <div class="lobby-page">
    <div class="lobby-wrap">
      <div class="lobby-container">
      <!-- 房间号展示：复制房间号 / 复制分享链接 / 隐身状态 -->
      <div class="room-header">
        <h1>
          房间号：<span class="room-id">{{ roomId }}</span>
          <span v-if="isSpectator" class="spectate-badge" title="你正在旁观，不会影响牌局">👁 旁观中</span>
          <span v-if="isPrivate" class="private-badge" title="隐身房间不出现在首页房间列表">🔒 隐身中</span>
        </h1>
        <div class="room-header-actions">
          <button class="copy-btn" @click="copyRoomId" title="复制房间号">📋</button>
          <button class="copy-btn" @click="copyShareLink" title="复制分享链接（对方打开即自动填入房间号）">🔗</button>
        </div>
      </div>
      
      <!-- 旁观者提示：大厅就是「等待界面」，只读，不能替房主开局 -->
      <div v-if="isSpectator" class="spectate-banner">
        <span class="sb-icon">👁</span>
        <span class="sb-text">
          旁观模式 · 正在等待房主开始游戏
          <small>牌局开始后自动切到观战界面；旁观不占玩家名额</small>
        </span>
      </div>

      <!-- 玩家列表 -->
      <div class="players-section">
        <h2>玩家列表 ({{ players.length }}/4)</h2>
        <div class="player-list">
          <div 
            v-for="(player, index) in players" 
            :key="player.playerId"
            class="player-item"
            :class="{ 'bot-item': player.isBot }"
          >
            <span class="player-name">
              {{ player.playerName }}
              <span v-if="player.isHost" class="host-badge">👑</span>
              <span v-if="player.isBot" class="bot-badge">🤖 机器人</span>
            </span>
            <button
              v-if="player.isBot && isHost"
              class="bot-remove-btn"
              @click="handleRemoveBot(player.playerId)"
            >
              移除
            </button>
            <span v-else class="ready-indicator">✅ 已就绪</span>
          </div>
          
          <!-- 空位占位 -->
          <div 
            v-for="i in (4 - players.length)" 
            :key="'empty-' + i"
            class="player-item empty"
          >
            <span class="empty-slot">等待玩家加入...</span>
          </div>
        </div>
      </div>

      <!-- 旁观者列表：房主可就地禁言 / 踢出 -->
      <div v-if="spectators.length" class="spectators-section">
        <h2>旁观者 ({{ spectators.length }})</h2>
        <div class="spectator-list">
          <div v-for="s in spectators" :key="s.playerId" class="spectator-item">
            <span class="spectator-name">
              👁 {{ s.playerName }}
              <span v-if="s.muted" class="muted-badge">已禁言</span>
            </span>
            <div v-if="isHost" class="spectator-actions">
              <button class="mini-btn" type="button" @click="toggleSpectatorMute(s)">
                {{ s.muted ? '解除禁言' : '禁言' }}
              </button>
              <button class="mini-btn danger" type="button" @click="kickSpectator(s.playerId)">踢出</button>
            </div>
            <span v-else class="spectator-hint">旁观中</span>
          </div>
        </div>
      </div>

      <!-- 房主操作区（旁观者不显示） -->
      <div v-if="isHost && !isSpectator" class="host-actions">
        <button 
          class="start-btn"
          :disabled="players.length < 4"
          @click="handleStartGame"
        >
          {{ players.length < 4 ? `还需 ${4 - players.length} 名玩家（可添加机器人）` : '🎮 开始游戏' }}
        </button>
        <!-- 机器人 / 房间隐身：同一行，各占一半宽度 -->
        <div class="host-action-row">
          <button 
            class="bot-add-btn"
            :disabled="players.length >= 4"
            @click="handleAddBot"
          >
            {{ players.length >= 4 ? '房间已满 4/4' : '🤖 添加机器人' }}
          </button>
          <div class="privacy-wrap">
            <button
              class="privacy-btn"
              :class="{ active: isPrivate }"
              :aria-pressed="isPrivate"
              @click="togglePrivacy"
            >
              {{ isPrivate ? '🔓 解除房间隐身' : '🔒 房间隐身' }}
            </button>
            <!-- 说明文字仅在鼠标悬停 / 键盘聚焦时浮出 -->
            <span class="privacy-tip" role="tooltip">
              {{ isPrivate ? '当前已隐身，不在首页房间列表显示' : '开启后不在首页房间列表显示' }}
            </span>
          </div>
        </div>
        <button class="dismiss-btn" @click="handleDismissRoom">解散房间</button>
      </div>
      
      <!-- 非房主提示 -->
      <div v-else class="non-host-message">
        <p>{{ isSpectator ? '等待房主开始游戏…（旁观中，不占玩家名额）' : '等待房主开始游戏...' }}</p>
        <button class="leave-btn" @click="handleLeaveRoom">
          {{ isSpectator ? '退出旁观' : '退出房间' }}
        </button>
      </div>
      
      <!-- 反馈信息 -->
      <div v-if="feedbackMsg" class="feedback" :class="feedbackType">
        {{ feedbackMsg }}
      </div>
      </div>

      <!-- 右侧：聊天室（等待阶段也能文字聊天 / 语音） -->
      <aside class="lobby-chat">
        <ChatPanel
          :roomId="roomId"
          :playerId="isSpectator ? spectatorId : currentPlayerId"
          :playerName="isSpectator ? (spectatorName || playerName) : playerName"
          :isHost="isHost && !isSpectator"
          :players="chatPlayers"
        />
      </aside>
    </div>

    <!-- 游戏中旁观申请（房主审批） -->
    <SpectatorAskModal :ask="pendingAsk" @respond="respondSpectator" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { wsService } from '@/services/websocket';
import { getClientId } from '@/services/presence';
import { useGameStore } from '@/stores/game';
import ChatPanel from '@/components/ChatPanel.vue';
import SpectatorAskModal from '@/components/SpectatorAskModal.vue';

const router = useRouter();
const route = useRoute();
const gameStore = useGameStore();

const roomId = ref('');
const playerName = ref('');
const isHost = ref(false);
// 旁观者：牌局没开始时同样待在本页（大厅即等待界面），只读、没有房主操作
const isSpectator = computed(() => String(route.query.spectate || '') === '1');
const spectatorId = ref(gameStore.spectatorId);
const spectatorName = ref(gameStore.spectatorName);
// 房主可把房间设为隐身：隐身房间不出现在首页公开列表（拿到房间号或分享链接仍可加入）
const isPrivate = ref(false);
const players = ref<Array<{ playerId: string; playerName: string; isHost: boolean; isBot?: boolean }>>([]);
// 旁观者（房主可禁言 / 踢出）
const spectators = ref<Array<{ playerId: string; playerName: string; muted: boolean }>>([]);
// 游戏进行中收到的旁观申请（房主弹窗审批）
const pendingAsk = ref<{ playerId: string; playerName: string } | null>(null);
const feedbackMsg = ref('');
const feedbackType = ref<'success' | 'error'>('success');
const currentPlayerId = computed(() => `${roomId.value}_${playerName.value}`);

// 聊天室的在线人数与成员展示用（含旁观者，语音成员列表才不会出现裸 id）
const chatPlayers = computed(() => {
  const map: Record<string, { playerId: string; playerName: string; isBot?: boolean }> = {};
  for (const p of players.value) {
    map[p.playerId] = { playerId: p.playerId, playerName: p.playerName, isBot: p.isBot };
  }
  for (const s of spectators.value) {
    map[s.playerId] = { playerId: s.playerId, playerName: s.playerName, isBot: false };
  }
  return map;
});

const updatePlayerList = (state: any) => {
  if (state.players) {
    players.value = Object.values(state.players as any).map((p: any) => ({
      playerId: p.playerId,
      playerName: p.playerName,
      isHost: p.playerId === (state as any).hostId,
      isBot: !!p.isBot
    }));

    // 房主身份以服务端为准：手动填房号加入的第一人同样会成为房主
    if ((state as any).hostId && !isSpectator.value) {
      isHost.value = (state as any).hostId === currentPlayerId.value;
    }
    if (isSpectator.value) isHost.value = false;

    // 隐身状态同样以服务端为准（房主切换后服务端会广播 state）
    isPrivate.value = !!(state as any).isPrivate;

    // 旁观者列表（隐身旁观不会下发到这里）
    spectators.value = ((state as any).spectators || []).map((s: any) => ({
      playerId: s.playerId,
      playerName: s.playerName,
      muted: !!s.muted
    }));
    
    if (players.value.length === 4 && !isSpectator.value) {
      showFeedback('房间已满，可以开始游戏了！', 'success');
    }
  }
};

onMounted(() => {
  // 从路由参数获取信息
  roomId.value = (route.query.roomId as string) || '';
  playerName.value = (route.query.playerName as string) || '';
  isHost.value = !isSpectator.value && route.query.isHost === 'true';
  
  if (!roomId.value || !playerName.value) {
    router.push('/');
    return;
  }
  
  // 初始化玩家列表（包含自己；旁观者自己不在玩家列表里，由服务端快照接管）
  players.value = isSpectator.value
    ? []
    : [{
        playerId: 'local',
        playerName: playerName.value,
        isHost: isHost.value
      }];
  
  // 先设回调，再连 WebSocket，确保不丢失消息
  wsService.setStateUpdateCallback((state: any) => {
    console.log('[Lobby] State update:', state);
    updatePlayerList(state);
    
    // 游戏开始后跳转到游戏页面
    const phase = String((state as any).gamePhase || '').toUpperCase();
    if (phase === 'PLAYING') {
      gameStore.updateGameState(state as any);
      if (isSpectator.value) {
        // 旁观者：连接复用，保持旁观身份与代入视角
        router.push({
          path: '/game',
          query: { roomId: roomId.value, playerName: playerName.value, spectate: '1' }
        });
        return;
      }
      gameStore.setMyPlayerId(currentPlayerId.value);
      router.push({
        path: '/game',
        query: {
          roomId: roomId.value,
          playerName: playerName.value,
          isHost: String(isHost.value)
        }
      });
    }
  });
  
  // 房间被房主或管理员关闭
  wsService.setRoomClosedCallback(() => {
    alert('房间已被关闭');
    wsService.disconnect();
    router.push('/');
  });

  // 服务端拒绝接入（如保留房间号）：提示后回首页，不再自动重连
  wsService.setFatalCallback((message: string) => {
    wsService.disconnect();
    // D2：房间满员时自动转旁观，而不是把人挡回首页
    if (message.includes('房间已满')) {
      alert('房间已满员，将以旁观者身份进入（牌局进行中需房主批准）');
      router.push({
        path: '/game',
        query: { roomId: roomId.value, playerName: playerName.value, spectate: '1' }
      });
      return;
    }
    alert(message);
    router.push('/');
  });

  // 旁观相关事件：本页处理「游戏中收到的旁观申请」、本页作为旁观者时的身份与退出
  wsService.setSpectatorEventCallback((event: string, payload: any) => {
    if (event === 'Event_SpectatorAsk') {
      pendingAsk.value = { playerId: payload.playerId, playerName: payload.playerName };
      return;
    }
    if (event === 'Event_SpectateReady') {
      spectatorId.value = payload?.playerId || '';
      spectatorName.value = payload?.playerName || '';
      gameStore.setSpectator(spectatorId.value, spectatorName.value, payload?.viewId || '');
      if (payload?.viewId) gameStore.setMyPlayerId(payload.viewId);
      return;
    }
    if (event === 'Event_SpectateView' && payload?.targetPlayerId) {
      gameStore.setSpectator(spectatorId.value, spectatorName.value, payload.targetPlayerId);
      gameStore.setMyPlayerId(payload.targetPlayerId);
      return;
    }
    if (event === 'Event_SpectatorRejected') {
      alert(payload?.text || payload?.reason || '无法旁观该房间');
      wsService.disconnect();
      router.push('/');
      return;
    }
    if (event === 'Event_SpectatorLeft') {
      wsService.disconnect();
      router.push('/');
      return;
    }
  });
  wsService.setChatRejectedCallback((payload: { reason: string }) => {
    showFeedback(payload.reason, 'error');
  });

  // 如果已有连接（从 GameRoom 重置后跳转而来），直接读取当前状态
  if (wsService.getStatus() === 'open') {
    const currentState = gameStore.gameState;
    if (currentState) {
      updatePlayerList(currentState);
    }
  } else {
    // 首次进入或连接已断开，重新连接（WS 地址跟随当前访问主机，支持局域网其他设备接入）
    let wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/${roomId.value}/${playerName.value}?clientId=${getClientId()}`;
    if (isSpectator.value) {
      wsUrl += '&spectate=1';
      const adminToken = route.query.adminToken;
      if (adminToken) wsUrl += `&adminToken=${encodeURIComponent(String(adminToken))}`;
    }
    wsService.connectWithUrl(wsUrl);
  }
});

const copyRoomId = async () => {
  try {
    await navigator.clipboard.writeText(roomId.value);
    showFeedback('房间号已复制到剪贴板', 'success');
  } catch (err) {
    showFeedback('复制失败，请手动复制', 'error');
  }
};

const copyShareLink = async () => {
  const url = `${window.location.origin}/?roomId=${roomId.value}`;
  try {
    await navigator.clipboard.writeText(url);
    showFeedback('分享链接已复制，发给好友即可直接进入本房', 'success');
  } catch (err) {
    showFeedback(`复制失败，请手动复制：${url}`, 'error');
  }
};

const togglePrivacy = () => {
  wsService.send({ cmd: 'SetRoomPrivacy', private: !isPrivate.value });
};

/** 房主审批旁观申请（弹窗回调） */
const respondSpectator = (payload: { allow: boolean; allowChat: boolean; allowVoice: boolean }) => {
  const ask = pendingAsk.value;
  if (!ask) return;
  wsService.send({
    cmd: 'SpectatorRespond',
    playerId: ask.playerId,
    allow: payload.allow,
    allowChat: payload.allowChat,
    allowVoice: payload.allowVoice
  });
  showFeedback(
    payload.allow ? `已允许 ${ask.playerName} 旁观` : `已拒绝 ${ask.playerName} 的旁观申请`,
    payload.allow ? 'success' : 'error'
  );
  pendingAsk.value = null;
};

const kickSpectator = (playerId: string) => {
  wsService.send({ cmd: 'KickSpectator', playerId });
};

const toggleSpectatorMute = (s: { playerId: string; playerName: string; muted: boolean }) => {
  wsService.send({ cmd: 'MuteSpectator', playerId: s.playerId, muted: !s.muted });
};

const handleStartGame = () => {
  if (players.value.length < 4) {
    showFeedback('需要 4 名玩家才能开始游戏', 'error');
    return;
  }
  
  wsService.send({ cmd: 'StartGame' });
};

const handleAddBot = () => {
  if (players.value.length >= 4) {
    showFeedback('房间已满，无法再添加机器人', 'error');
    return;
  }
  wsService.send({ cmd: 'AddBot' });
};

const handleRemoveBot = (botId: string) => {
  wsService.send({ cmd: 'RemoveBot', playerId: botId });
};

const handleDismissRoom = () => {
  if (confirm('确定要解散房间吗？')) {
    // 必须先告诉服务端：只断开连接的话，房间对象会一直留在内存里，
    // 首页房间列表和管理后台都还能看到它；用同一个房间号重开时，
    // 服务端会认为房间还在，于是继承上一局的聊天记录（这就是那个 bug）。
    wsService.send({ cmd: 'DissolveRoom' });
    wsService.disconnect();
    router.push('/');
  }
};

const handleLeaveRoom = () => {
  // 主动退出 ≠ 断线：服务端会立刻把人从名单里移除，不再留占位等重连
  if (isSpectator.value) {
    wsService.send({ cmd: 'SpectatorLeave' });
  } else {
    wsService.send({ cmd: 'LeaveRoom' });
  }
  wsService.disconnect();
  router.push('/');
};

const showFeedback = (msg: string, type: 'success' | 'error') => {
  feedbackMsg.value = msg;
  feedbackType.value = type;
  setTimeout(() => {
    feedbackMsg.value = '';
  }, 3000);
};
</script>

<style scoped>
.lobby-page {
  position: fixed;
  inset: 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 40px 20px;
  overflow-y: auto;
  display: flex;
  align-items: flex-start;
  justify-content: center;
}

/* 大厅主体 + 右侧聊天室 */
.lobby-wrap {
  display: flex;
  align-items: stretch;
  gap: 16px;
  width: 100%;
  max-width: 1000px;
  min-height: min(720px, calc(100vh - 80px));
}

.lobby-container {
  flex: 1 1 auto;
  min-width: 0;
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

/* 右侧聊天栏：固定宽度、固定上下长度，多余消息在卡片内滚动 */
.lobby-chat {
  flex: 0 0 300px;
  width: 300px;
  height: min(720px, calc(100vh - 80px));
  max-height: min(720px, calc(100vh - 80px));
  align-self: flex-start;
  background: white;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.lobby-chat :deep(.chat-panel) {
  border-radius: 16px;
  box-shadow: none;
}

@media (max-width: 860px) {
  .lobby-page {
    align-items: flex-start;
  }

  .lobby-wrap {
    flex-direction: column;
    min-height: 0;
  }

  .lobby-chat {
    flex: 0 0 auto;
    width: 100%;
    height: 420px;
  }
}

.room-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32px;
  padding-bottom: 16px;
  border-bottom: 2px solid #e0e0e0;
}

.room-header h1 {
  font-size: 24px;
  color: #333;
  margin: 0;
}

.room-id {
  color: #667eea;
  font-weight: bold;
  font-size: 28px;
}

.copy-btn {
  background: none;
  border: 2px solid #667eea;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.copy-btn:hover {
  background: #667eea;
  color: white;
}

.room-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.private-badge {
  margin-left: 10px;
  padding: 3px 8px;
  border-radius: 999px;
  background: #fff4e5;
  color: #c2751b;
  font-size: 12px;
  font-weight: 600;
  vertical-align: middle;
}

.spectate-badge {
  margin-left: 10px;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 12px;
  font-weight: 600;
  vertical-align: middle;
}

/* 旁观者在大厅（等待界面）看到的通栏提示 */
.spectate-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  padding: 10px 14px;
  border: 1px solid #c7d2fe;
  border-radius: 10px;
  background: #eef2ff;
  color: #3730a3;
  text-align: left;
}

.spectate-banner .sb-icon {
  font-size: 18px;
  line-height: 1;
}

.spectate-banner .sb-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  font-weight: 600;
}

.spectate-banner .sb-text small {
  font-size: 11px;
  font-weight: 400;
  color: #5b62a8;
}

/* 机器人 / 房间隐身：同一行、各占一半宽度（grid 保证严格等宽） */
.host-action-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.host-action-row > * {
  min-width: 0;
}

.host-action-row .bot-add-btn,
.host-action-row .privacy-btn {
  width: 100%;
  padding: 13px 8px;
  font-size: 15px;
  white-space: nowrap;
}

/* 隐身按钮的说明文字：默认隐藏，悬停 / 聚焦时才浮出 */
.privacy-wrap {
  position: relative;
  display: flex;
}

.privacy-tip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%) translateY(4px);
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(38, 34, 58, 0.95);
  color: #fff;
  font-size: 12px;
  line-height: 1.4;
  text-align: center;
  white-space: nowrap;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s;
  z-index: 6;
}

/* 小三角 */
.privacy-tip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: rgba(38, 34, 58, 0.95);
}

/* 悬停时浮出；键盘 Tab 聚焦（focus-visible）时也浮出。
   这里刻意不用 :focus-within —— 鼠标点击按钮后按钮会留在聚焦态，
   :focus-within 会让说明文字一直挂着，直到点击别处才消失。 */
.privacy-wrap:hover .privacy-tip,
.privacy-btn:focus-visible + .privacy-tip {
  opacity: 1;
  visibility: visible;
  transform: translateX(-50%) translateY(0);
}

.privacy-btn {
  padding: 12px;
  background: #fff;
  border: 2px solid #667eea;
  color: #4a4fa2;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.privacy-btn:hover {
  background: #eef0ff;
}

.privacy-btn.active {
  background: #fff4e5;
  border-color: #e0a35a;
  color: #b4690e;
}

.players-section h2 {
  font-size: 18px;
  color: #555;
  margin-bottom: 16px;
}

.player-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 32px;
}

.player-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: #f5f5f5;
  border-radius: 8px;
}

.player-item.empty {
  background: #fafafa;
  border: 2px dashed #e0e0e0;
}

.player-name {
  font-weight: bold;
  color: #333;
  font-size: 16px;
}

.host-badge {
  margin-left: 8px;
}

.bot-badge {
  margin-left: 8px;
  font-size: 12px;
  color: #5e35b1;
  background: #ede7f6;
  border-radius: 10px;
  padding: 2px 8px;
}

.player-item.bot-item {
  background: #f6f2ff;
  border: 1px solid #e0d7f7;
}

.bot-remove-btn {
  padding: 6px 14px;
  background: #fff;
  color: #c62828;
  border: 1px solid #ef9a9a;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.bot-remove-btn:hover {
  background: #ffebee;
}

.bot-add-btn {
  padding: 14px;
  background: #fff;
  color: #5e35b1;
  border: 2px dashed #b39ddb;
  border-radius: 8px;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
}

.bot-add-btn:hover:not(:disabled) {
  background: #f6f2ff;
}

.bot-add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ready-indicator {
  color: #4CAF50;
  font-size: 14px;
}

.empty-slot {
  color: #999;
  font-style: italic;
}

.host-actions, .non-host-message {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.start-btn {
  padding: 16px;
  background: linear-gradient(45deg, #667eea, #764ba2);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 18px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
}

.start-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.start-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dismiss-btn {
  padding: 12px;
  background: #f44336;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
}

.dismiss-btn:hover {
  background: #d32f2f;
}

.non-host-message {
  text-align: center;
  padding: 24px;
  background: #f5f5f5;
  border-radius: 8px;
}

.non-host-message p {
  margin: 0 0 16px 0;
  color: #666;
  font-size: 16px;
}

.leave-btn {
  padding: 12px 24px;
  background: #9e9e9e;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
}

.leave-btn:hover {
  background: #757575;
}

.feedback {
  margin-top: 16px;
  padding: 12px;
  border-radius: 8px;
  text-align: center;
  animation: fadeIn 0.3s ease;
}

.feedback.success {
  background: #e8f5e9;
  color: #2e7d32;
}

.feedback.error {
  background: #ffebee;
  color: #c62828;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ---------------------------------------------------------- 旁观者 */
.spectators-section {
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 12px;
  background: #f6f7ff;
  border: 1px solid #e2e6f7;
}

.spectators-section h2 {
  margin: 0 0 10px;
  font-size: 15px;
  color: #4a4fa2;
}

.spectator-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.spectator-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #e6e9f6;
}

.spectator-name {
  font-size: 13px;
  color: #3c4160;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted-badge {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  background: #fff1e6;
  color: #b56a1c;
  font-size: 11px;
}

.spectator-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.mini-btn {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #cfd4ef;
  background: #fff;
  color: #4a4fa2;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.mini-btn:hover {
  border-color: #667eea;
  background: #f2f3ff;
}

.mini-btn.danger {
  border-color: #f0c9c4;
  color: #c0392b;
}

.mini-btn.danger:hover {
  border-color: #e57368;
  background: #fff4f2;
}

.spectator-hint {
  font-size: 12px;
  color: #9096ad;
  flex-shrink: 0;
}
</style>
