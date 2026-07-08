<template>
  <div class="lobby-page">
    <div class="lobby-container">
      <!-- 房间号展示 -->
      <div class="room-header">
        <h1>房间号：<span class="room-id">{{ roomId }}</span></h1>
        <button class="copy-btn" @click="copyRoomId" title="复制房间号">📋</button>
      </div>
      
      <!-- 玩家列表 -->
      <div class="players-section">
        <h2>玩家列表 ({{ players.length }}/4)</h2>
        <div class="player-list">
          <div 
            v-for="(player, index) in players" 
            :key="player.playerId"
            class="player-item"
          >
            <span class="player-name">
              {{ player.playerName }}
              <span v-if="player.isHost" class="host-badge">👑</span>
            </span>
            <span class="ready-indicator">✅ 已就绪</span>
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
      
      <!-- 房主操作区 -->
      <div v-if="isHost" class="host-actions">
        <button 
          class="start-btn"
          :disabled="players.length < 4"
          @click="handleStartGame"
        >
          {{ players.length < 4 ? '等待更多玩家加入...' : '🎮 开始游戏' }}
        </button>
        <button class="dismiss-btn" @click="handleDismissRoom">解散房间</button>
      </div>
      
      <!-- 非房主提示 -->
      <div v-else class="non-host-message">
        <p>等待房主开始游戏...</p>
        <button class="leave-btn" @click="handleLeaveRoom">退出房间</button>
      </div>
      
      <!-- 反馈信息 -->
      <div v-if="feedbackMsg" class="feedback" :class="feedbackType">
        {{ feedbackMsg }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { wsService } from '@/services/websocket';
import { useGameStore } from '@/stores/game';

const router = useRouter();
const route = useRoute();
const gameStore = useGameStore();

const roomId = ref('');
const playerName = ref('');
const isHost = ref(false);
const players = ref<Array<{ playerId: string; playerName: string; isHost: boolean }>>([]);
const feedbackMsg = ref('');
const feedbackType = ref<'success' | 'error'>('success');
const currentPlayerId = computed(() => `${roomId.value}_${playerName.value}`);

const updatePlayerList = (state: any) => {
  if (state.players) {
    players.value = Object.values(state.players as any).map((p: any) => ({
      playerId: p.playerId,
      playerName: p.playerName,
      isHost: p.playerId === (state as any).hostId
    }));
    
    if (players.value.length === 4) {
      showFeedback('房间已满，可以开始游戏了！', 'success');
    }
  }
};

onMounted(() => {
  // 从路由参数获取信息
  roomId.value = (route.query.roomId as string) || '';
  playerName.value = (route.query.playerName as string) || '';
  isHost.value = route.query.isHost === 'true';
  
  if (!roomId.value || !playerName.value) {
    router.push('/');
    return;
  }
  
  // 初始化玩家列表（包含自己）
  players.value = [{
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
  
  // 如果已有连接（从 GameRoom 重置后跳转而来），直接读取当前状态
  if (wsService.getStatus() === 'open') {
    const currentState = gameStore.gameState;
    if (currentState) {
      updatePlayerList(currentState);
    }
  } else {
    // 首次进入或连接已断开，重新连接
    const wsUrl = `ws://localhost:8000/ws/${roomId.value}/${playerName.value}`;
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

const handleStartGame = () => {
  if (players.value.length < 4) {
    showFeedback('需要 4 名玩家才能开始游戏', 'error');
    return;
  }
  
  wsService.send({ cmd: 'StartGame' });
};

const handleDismissRoom = () => {
  if (confirm('确定要解散房间吗？')) {
    wsService.disconnect();
    router.push('/');
  }
};

const handleLeaveRoom = () => {
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
}

.lobby-container {
  max-width: 600px;
  margin: 0 auto;
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
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
</style>
