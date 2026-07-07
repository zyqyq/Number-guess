<template>
  <div class="game-room">
    <!-- 顶部信息栏 -->
    <header class="game-header">
      <h1>猜数字游戏</h1>
      <div class="room-info">
        <span>房间号：{{ roomId }}</span>
        <span>轮次：{{ gameState?.roundNumber || 0 }}</span>
      </div>
    </header>

    <!-- 主游戏区 -->
    <main class="game-main">
      <!-- 左侧：牌区和玩家手牌 -->
      <div class="left-panel">
        <!-- 公共牌区 -->
        <section class="public-section">
          <h2>公共牌区</h2>
          <PublicCards 
            :publicCards="gameState?.publicCards || []"
            :clickable="isMyTurn && gameState?.subPhase === 'ACTION_PHASE'"
            @select="handlePublicCardSelect"
          />
        </section>

        <!-- 其他玩家手牌 -->
        <section class="other-players-section">
          <h2>其他玩家</h2>
          <PlayerHand
            v-for="player in otherPlayers"
            :key="player.playerId"
            :player="player"
            :isMe="false"
          />
        </section>

        <!-- 自己的手牌 -->
        <section class="my-hand-section">
          <h2>我的手牌</h2>
          <PlayerHand
            v-if="currentPlayer"
            :player="currentPlayer"
            :isMe="true"
          />
          
          <!-- 线索展示区 -->
          <div class="clues-summary" v-if="currentPlayer?.clues?.length">
            <h3>已获得的线索</h3>
            <div class="clue-list">
              <div 
                v-for="clue in currentPlayer.clues" 
                :key="clue.id"
                class="clue-item"
              >
                <span class="clue-type">{{ clue.type === 'position' ? '位置' : '点数' }}</span>
                <span class="clue-detail">
                  {{ formatClueDetail(clue) }}
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- 备选区表格 -->
        <section class="candidate-section">
          <h2>备选区（左键选择，右键搁置）</h2>
          <CandidateTable @select-number="handleCandidateSelect" />
        </section>
      </div>

      <!-- 右侧：操作栏 -->
      <aside class="right-panel">
        <div class="turn-indicator">
          <div v-if="isMyTurn" class="my-turn">
            <strong>轮到你了！</strong>
          </div>
          <div v-else class="other-turn">
            当前玩家：{{ getCurrentPlayerName }}
          </div>
        </div>

        <!-- 操作按钮区 -->
        <div class="action-buttons">
          <!-- 等待开始状态 -->
          <button 
            v-if="gameState?.gamePhase === 'WAITING'"
            class="btn btn-primary"
            @click="handleStartGame"
          >
            开始游戏
          </button>

          <!-- 选色抽牌阶段 -->
          <div v-if="gameState?.subPhase === 'DRAW_PHASE' && isMyTurn" class="draw-phase">
            <p>请选择要抽取的颜色：</p>
            <div class="color-buttons">
              <button
                v-for="count in colorCounts"
                :key="count.color"
                class="btn btn-color"
                :disabled="count.count === 0"
                @click="handleSelectColor(count.color)"
              >
                {{ count.color }} ({{ count.count }})
              </button>
            </div>
          </div>

          <!-- 判定阶段 -->
          <div v-if="gameState?.subPhase === 'ACTION_PHASE' && isMyTurn" class="action-phase">
            <p v-if="!selectedPublicCard">请先选择一张公共牌</p>
            <template v-else>
              <p>已选择公牌：{{ selectedPublicCard.color }} {{ selectedPublicCard.number }}</p>
              <div class="judge-buttons">
                <button 
                  class="btn btn-secondary"
                  @click="handleJudgeByPosition"
                >
                  位置判定
                </button>
                <button 
                  class="btn btn-secondary"
                  @click="handleJudgeByPoint"
                >
                  点数判定
                </button>
              </div>
            </template>
          </div>

          <!-- 提交猜测按钮（任何时候可用） -->
          <button 
            class="btn btn-danger"
            @click="showGuessModal = true"
          >
            提交猜测
          </button>

          <!-- 房主跳过按钮 -->
          <button 
            v-if="isHost && gameState?.subPhase === 'ACTION_PHASE'"
            class="btn btn-warning"
            @click="handleSkipTurn"
          >
            跳过本轮
          </button>
        </div>

        <!-- 游戏结束信息 -->
        <div v-if="gameState?.gameOverInfo" class="game-over-info">
          <h3>游戏结束</h3>
          <p v-if="gameState.gameOverInfo.winnerName">
            🎉 {{ gameState.gameOverInfo.winnerName }} 获胜！
          </p>
          <p v-else>
            🤝 平局！
          </p>
        </div>
      </aside>
    </main>

    <!-- 猜测弹窗 -->
    <div v-if="showGuessModal" class="modal-overlay" @click.self="showGuessModal = false">
      <div class="modal">
        <h2>提交你的猜测</h2>
        <p>按颜色顺序输入你 5 张牌的数字：</p>
        <div class="guess-inputs">
          <div 
            v-for="card in myHand" 
            :key="card.color"
            class="guess-input"
          >
            <label>{{ card.color }}:</label>
            <input 
              type="number" 
              v-model.number="guessForm[card.color]"
              min="1" 
              max="60"
            />
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showGuessModal = false">取消</button>
          <button class="btn btn-primary" @click="handleSubmitGuess">提交</button>
        </div>
      </div>
    </div>

    <!-- 点数判定目标颜色选择弹窗 -->
    <div v-if="showPointJudgeModal" class="modal-overlay" @click.self="showPointJudgeModal = false">
      <div class="modal">
        <h2>点数判定</h2>
        <p>选择你要比较的手牌颜色：</p>
        <div class="color-buttons">
          <button
            v-for="card in myHand"
            :key="card.color"
            class="btn btn-color"
            @click="pointJudgeTargetColor = card.color; confirmPointJudge()"
          >
            {{ card.color }}
          </button>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showPointJudgeModal = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useGameStore } from '@/stores/game';
import { useMyHand, useOtherPlayers } from '@/composables/gameLogic';
import { wsService } from '@/services/websocket';
import PublicCards from '@/components/PublicCards.vue';
import PlayerHand from '@/components/PlayerHand.vue';
import CandidateTable from '@/components/CandidateTable.vue';
import type { Color, Card, ClientCommand } from '@/types/game';

const gameStore = useGameStore();
const { myHand } = useMyHand();
const { otherPlayers } = useOtherPlayers();

// 房间 ID 和玩家 ID（实际应从路由或登录获取）
const roomId = ref('ROOM001');
const playerId = ref('P1');
const isHost = ref(true);

// 选中的公共牌
const selectedPublicCard = ref<Card | null>(null);

// 猜测弹窗
const showGuessModal = ref(false);
const guessForm = ref<Record<Color, number>>({
  红: 0,
  蓝: 0,
  绿: 0,
  橙: 0,
  粉: 0
});

// 点数判定目标颜色选择
const showPointJudgeModal = ref(false);
const pointJudgeTargetColor = ref<Color>('红');

// 计算属性
const gameState = computed(() => gameStore.gameState);
const currentPlayer = computed(() => gameStore.currentPlayer);
const isMyTurn = computed(() => gameStore.isMyTurn);

const getCurrentPlayerName = computed(() => {
  if (!gameState.value?.currentTurnPlayerId) return '';
  const player = gameState.value.players[gameState.value.currentTurnPlayerId];
  return player?.playerName || '';
});

const colorCounts = computed(() => {
  const counts = [
    { color: '红' as Color, count: gameState.value?.deckRemainingCount.红 || 0 },
    { color: '蓝' as Color, count: gameState.value?.deckRemainingCount.蓝 || 0 },
    { color: '绿' as Color, count: gameState.value?.deckRemainingCount.绿 || 0 },
    { color: '橙' as Color, count: gameState.value?.deckRemainingCount.橙 || 0 },
    { color: '粉' as Color, count: gameState.value?.deckRemainingCount.粉 || 0 }
  ];
  return counts;
});

// WebSocket 事件处理
const handleStateUpdate = (state: any) => {
  console.log('[GameRoom] State updated:', state);
  // 状态更新后重置选中的牌
  selectedPublicCard.value = null;
};

const handleGuessResult = (result: any) => {
  console.log('[GameRoom] Guess result:', result);
  alert(result.correct ? '🎉 恭喜你猜对了！获胜！' : `❌ 猜错了！正确答案是：${JSON.stringify(result.correctNumbers)}`);
  showGuessModal.value = false;
};

const handleDisconnect = (data: any) => {
  console.log('[GameRoom] Player disconnected:', data);
  if (data.isCurrentTurnPlayer && data.paused) {
    alert('当前操作玩家断线，游戏已暂停');
  }
};

const handleGameOver = (data: any) => {
  console.log('[GameRoom] Game over:', data);
};

// 方法
const sendCommand = (cmd: ClientCommand) => {
  wsService.send(cmd);
};

const handleStartGame = () => {
  sendCommand({ cmd: 'StartGame' });
};

const handlePublicCardSelect = (card: Card) => {
  if (selectedPublicCard.value?.id === card.id) {
    selectedPublicCard.value = null;
  } else {
    selectedPublicCard.value = card;
  }
};

const handleSelectColor = (color: Color) => {
  sendCommand({ 
    cmd: 'SelectColorToDraw', 
    color 
  });
};

const handleJudgeByPosition = () => {
  if (!selectedPublicCard.value) return;
  sendCommand({
    cmd: 'JudgeByPosition',
    publicCardId: selectedPublicCard.value.id
  });
};

const handleJudgeByPoint = () => {
  if (!selectedPublicCard.value) return;
  pointJudgeTargetColor.value = '红';
  showPointJudgeModal.value = true;
};

const confirmPointJudge = () => {
  if (!selectedPublicCard.value) return;
  sendCommand({
    cmd: 'JudgeByPoint',
    publicCardId: selectedPublicCard.value.id,
    targetColor: pointJudgeTargetColor.value
  });
  showPointJudgeModal.value = false;
};

const handleSkipTurn = () => {
  sendCommand({ cmd: 'SkipTurn' });
};

const handleSubmitGuess = () => {
  // 验证输入
  const guesses = [
    guessForm.value.红,
    guessForm.value.蓝,
    guessForm.value.绿,
    guessForm.value.橙,
    guessForm.value.粉
  ];
  
  if (guesses.some(g => g < 1 || g > 60)) {
    alert('请输入 1-60 之间的数字');
    return;
  }
  
  sendCommand({
    cmd: 'SubmitGuess',
    guesses: guesses
  });
};

const formatClueDetail = (clue: any) => {
  if (clue.type === 'position') {
    return `公牌 ${clue.publicCardNumber} 位于位置 ${clue.result}`;
  } else if (clue.type === 'point') {
    return `公牌 ${clue.publicCardNumber} 与 ${clue.targetColor} 点数${clue.result ? '相同' : '不同'}`;
  }
  return '';
};

// 备选区表格选择事件处理
const handleCandidateSelect = (color: Color, num: number) => {
  // 将选择的数字填入猜测表单
  guessForm.value[color] = num;
  console.log(`从备选区选择：${color} ${num}`);
};

// 生命周期
onMounted(() => {
  // 设置当前玩家 ID
  gameStore.setMyPlayerId(playerId.value);
  
  // 连接 WebSocket
  wsService.setStateUpdateCallback(handleStateUpdate);
  wsService.setGuessResultCallback(handleGuessResult);
  wsService.setDisconnectCallback(handleDisconnect);
  wsService.setGameOverCallback(handleGameOver);
  
  // 尝试连接（开发环境可注释，使用模拟数据）
  // wsService.connect(roomId.value);
  
  // 模拟加载游戏状态（实际应从 WebSocket 接收）
  gameStore.updateGameState({
    roomId: roomId.value,
    gamePhase: 'PLAYING',
    subPhase: 'DRAW_PHASE',
    roundNumber: 1,
    currentTurnPlayerId: 'P1',
    deckRemainingCount: { 红: 11, 蓝: 12, 绿: 12, 橙: 12, 粉: 12 },
    publicCards: [
      { id: 'pub_1', color: '红', number: 6, isSelected: false },
      { id: 'pub_2', color: '蓝', number: 12, isSelected: false },
      { id: 'pub_3', color: '绿', number: 18, isSelected: false },
      { id: 'pub_4', color: '橙', number: 24, isSelected: false },
      { id: 'pub_5', color: '粉', number: 30, isSelected: false }
    ],
    players: {
      'P1': {
        playerId: 'P1',
        playerName: 'Alice',
        isAlive: true,
        isOnline: true,
        hand: [
          { id: 'h1_1', color: '红', number: 11 },
          { id: 'h1_2', color: '蓝', number: 17 },
          { id: 'h1_3', color: '绿', number: 23 },
          { id: 'h1_4', color: '橙', number: 29 },
          { id: 'h1_5', color: '粉', number: 35 }
        ],
        clues: []
      },
      'P2': {
        playerId: 'P2',
        playerName: 'Bob',
        isAlive: true,
        isOnline: true,
        hand: [
          { id: 'h2_1', color: '红', number: 1 },
          { id: 'h2_2', color: '蓝', number: 7 },
          { id: 'h2_3', color: '绿', number: 13 },
          { id: 'h2_4', color: '橙', number: 19 },
          { id: 'h2_5', color: '粉', number: 25 }
        ],
        clues: []
      }
    },
    pendingJudgement: null,
    gameOverInfo: null
  });
});

onUnmounted(() => {
  wsService.disconnect();
});
</script>

<style scoped>
.game-room {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.game-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 2px solid #e0e0e0;
}

.game-header h1 {
  margin: 0;
  font-size: 24px;
  color: #333;
}

.room-info {
  display: flex;
  gap: 20px;
  color: #666;
}

.game-main {
  display: grid;
  grid-template-columns: 3fr 1fr;
  gap: 24px;
}

.left-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.right-panel {
  background: #f5f5f5;
  padding: 20px;
  border-radius: 8px;
  height: fit-content;
}

section {
  background: white;
  padding: 16px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

section h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
  color: #333;
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 8px;
}

.turn-indicator {
  margin-bottom: 20px;
  padding: 12px;
  border-radius: 6px;
  text-align: center;
}

.my-turn {
  background: #e8f5e9;
  color: #2e7d32;
  font-size: 18px;
}

.other-turn {
  background: #e3f2fd;
  color: #1976d2;
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #4CAF50;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #45a049;
}

.btn-secondary {
  background: #2196F3;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #1976d2;
}

.btn-danger {
  background: #f44336;
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: #d32f2f;
}

.btn-warning {
  background: #ff9800;
  color: white;
}

.btn-warning:hover:not(:disabled) {
  background: #f57c00;
}

.btn-color {
  background: #9c27b0;
  color: white;
  margin: 4px;
}

.btn-color:hover:not(:disabled) {
  background: #7b1fa2;
}

.color-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.judge-buttons {
  display: flex;
  gap: 12px;
}

.draw-phase, .action-phase {
  background: white;
  padding: 16px;
  border-radius: 6px;
  margin-bottom: 12px;
}

.game-over-info {
  margin-top: 20px;
  padding: 16px;
  background: #fff3e0;
  border-radius: 6px;
  text-align: center;
}

.game-over-info h3 {
  margin: 0 0 12px 0;
  color: #e65100;
}

/* 线索展示 */
.clues-summary {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 2px solid #e0e0e0;
}

.clues-summary h3 {
  margin: 0 0 12px 0;
  font-size: 16px;
  color: #555;
}

.clue-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.clue-item {
  display: flex;
  gap: 12px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 14px;
}

.clue-type {
  font-weight: bold;
  color: #1976d2;
  min-width: 40px;
}

.clue-detail {
  color: #333;
}

/* 猜测弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  padding: 24px;
  border-radius: 8px;
  max-width: 500px;
  width: 90%;
}

.modal h2 {
  margin: 0 0 16px 0;
  color: #333;
}

.guess-inputs {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 16px 0;
}

.guess-input {
  display: flex;
  align-items: center;
  gap: 12px;
}

.guess-input label {
  min-width: 40px;
  font-weight: bold;
}

.guess-input input {
  flex: 1;
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 16px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}
</style>
