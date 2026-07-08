<template>
  <div class="game-room">
    <!-- 顶部信息栏 -->
    <header class="game-header">
      <h1>猜数字游戏</h1>
      <div class="room-info">
        <span>房间号：{{ roomId }}</span>
        <span>轮次：{{ gameState?.roundNumber || 0 }}</span>
        <button class="exit-btn" @click="exitRoom">🚪 退出</button>
      </div>
    </header>

    <!-- 主游戏区 -->
    <main class="game-main">
      <!-- 左侧：牌区和玩家手牌 -->
      <div class="left-panel">
        <!-- 公共牌区 -->
        <section class="public-section">
          <PublicCards 
            :publicCards="displayedPublicCards"
            :clickable="isMyTurn && normalizedSubPhase === 'ACTION_PHASE'"
            @select="handlePublicCardSelect"
          />
        </section>

        <!-- 其他玩家手牌（合并到单框） -->
        <section class="other-players-section">
          <div class="other-players-container">
            <div
              v-for="player in orderedOtherPlayers"
              :key="player.playerId"
              class="other-player-row"
            >
              <div class="opl-name-wrap" :class="{ 'active-turn': gameState?.currentTurnPlayerId === player.playerId }">
                <span class="opl-name">{{ player.playerName }}</span>
                <span v-if="gameState?.currentTurnPlayerId === player.playerId" class="opl-turn-icon">⚡</span>
              </div>
              <div class="cards">
                <div
                  v-for="card in player.hand"
                  :key="card.id"
                  class="card card-base"
                  :class="getColorClass(card.color)"
                  :style="{ backgroundColor: getColorValue(card.color) }"
                >
                  <div class="card-content">
                    <span class="card-number">{{ card.number }}</span>
                    <div class="point-dots">
                      <span v-for="dot in getPointFromNumber(card.number)" :key="dot" class="point-dot"></span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 自己的手牌 -->
        <section class="my-hand-section">
          <PlayerHand
            v-if="currentPlayer"
            :player="currentPlayer"
            :isMe="true"
            :selectedNumbers="guessForm"
            :pointJudgeMode="pointJudgeMode"
            @commit-number="handleHandNumberCommit"
            @point-judge-select="handlePointJudgeSelect"
          />
          <div v-if="pointJudgeMode" class="point-judge-hint">
            👆 点击一张手牌选择目标颜色进行点数判定
          </div>
        </section>

      </div>

      <!-- 右侧：操作栏 -->
      <aside class="right-panel">
        <div class="deck-area">
          <div class="deck-stack">牌堆</div>
          <div class="deck-count">剩余：{{ totalDeckRemaining }}</div>
        </div>
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
            v-if="normalizedGamePhase === 'WAITING'"
            class="btn btn-primary"
            @click="handleStartGame"
          >
            开始游戏
          </button>

          <!-- 选色抽牌阶段 -->
          <div v-if="normalizedSubPhase === 'DRAW_PHASE' && isMyTurn" class="draw-phase">
            <p>请选择要抽取的颜色：</p>
            <div class="color-card-buttons">
              <button
                v-for="count in colorCounts"
                :key="count.color"
                class="color-card-button"
                :disabled="count.count === 0"
                @click="handleSelectColor(count.color)"
              >
                <span class="color-card-count">剩余 {{ count.count }}</span>
              </button>
            </div>
          </div>

          <!-- 判定阶段 -->
          <div v-if="normalizedSubPhase === 'ACTION_PHASE' && isMyTurn" class="action-phase">
            <p v-if="!selectedPublicCard">请先选择一张公共牌</p>
            <template v-else>
              <p class="selected-label">已选择公牌</p>
              <div
                class="selected-card-visual card-mini"
                :class="getColorClass(selectedPublicCard.color)"
                :style="{ backgroundColor: getColorValue(selectedPublicCard.color) }"
              >
                <span class="card-number-small">{{ selectedPublicCard.number }}</span>
                <div class="point-dots">
                  <span v-for="dot in getPointFromNumber(selectedPublicCard.number)" :key="dot" class="point-dot"></span>
                </div>
              </div>
              <div class="judge-buttons">
                <button
                  class="btn btn-secondary"
                  @click="handleJudgeByPosition"
                >
                  位置判定
                </button>
                <button
                  class="btn btn-secondary"
                  @click="startPointJudge"
                >
                  点数判定
                </button>
              </div>
            </template>
          </div>



          <!-- 房主跳过按钮 -->
          <button 
            v-if="isHost && normalizedSubPhase === 'ACTION_PHASE'"
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

        <!-- 个人线索区 -->
        <div v-if="currentPlayer?.clues?.length" class="my-clues-section">
          <h3>🧩 线索</h3>
          <div class="my-clue-list">
            <div
              v-for="clue in currentPlayer.clues.slice().reverse()"
              :key="clue.id"
              class="my-clue-card"
            >
              <div class="my-clue-text">
                <span v-if="clue.type === 'point'" class="clue-html">
                  <span :style="{ color: getColorValue(clue.targetColor!), fontWeight: 700 }">{{ clue.targetColor }}牌</span>
                  {{ (clue as any).result ? '是' : '不是' }}
                  {{ getPointFromNumber(clue.publicCardNumber!) }}点
                </span>
                <span v-else-if="clue.type === 'position'" class="clue-html">
                  数字 {{ clue.publicCardNumber }} 在
                  <span :style="{ color: getColorValue(getColorFromNumber(clue.publicCardNumber!)), fontWeight: 700 }">{{ getColorFromNumber(clue.publicCardNumber!) }}</span>
                  和
                  <span :style="{ color: getColorValue(neighborColor(clue.publicCardNumber!)), fontWeight: 700 }">{{ neighborColor(clue.publicCardNumber!) }}</span>
                  之间
                </span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 备选区表格（跨两列） -->
      <section class="candidate-section">
        <CandidateTable
          :selectedNumbers="guessForm"
          @select-number="handleCandidateSelect"
        />
      </section>
    </main>

    <!-- 猜测弹窗（直接用手牌区已填的数字） -->
    <div v-if="showGuessModal" class="modal-overlay" @click.self="showGuessModal = false">
      <div class="modal">
        <h2>提交你的猜测</h2>
        <p>你的手牌区已填的数字将作为猜测结果提交</p>
        <div class="guess-preview">
          <span v-for="color in colorsForGuess" :key="color" class="guess-preview-item" :style="{ background: getColorValue(color) }">
            <span class="gp-color">{{ color }}</span>
            <span class="gp-number">{{ guessForm[color] ?? '?' }}</span>
          </span>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showGuessModal = false">取消</button>
          <button class="btn btn-primary" :disabled="!allGuessesFilled" @click="handleSubmitGuess">提交</button>
        </div>
      </div>
    </div>

    <!-- 猜测结果全局弹窗 -->
    <div v-if="guessResult" class="modal-overlay">
      <div class="modal result-modal">
        <h2>{{ guessResult.correct ? '🎉 猜对了！' : '❌ 猜错了' }}</h2>
        <p class="result-subtitle">{{ guessResult.playerName }} 的猜测：</p>
        <div class="guess-preview">
          <span v-for="(g, gi) in guessResult.guesses" :key="gi" class="guess-preview-item">
            {{ g }}
          </span>
        </div>
        <p v-if="guessResult.correct" class="result-correct">游戏结束！{{ guessResult.playerName }} 获胜！</p>
        <p v-else class="result-wrong">正确答案已公开。等待下一位玩家操作。</p>
        <div v-if="guessResult.correct" class="result-actions">
          <template v-if="isHost">
            <button class="btn btn-primary" @click="handleResetGame">🔄 重置游戏</button>
            <button class="btn btn-danger" :disabled="dissolveCountdown <= 0" @click="handleDissolveRoom">
              解散房间{{ dissolveCountdown > 0 ? '…' + dissolveCountdown + 's' : '' }}
            </button>
          </template>
          <template v-else>
            <button class="btn btn-secondary" :disabled="dissolveCountdown <= 0" @click="exitRoom">
              退出房间{{ dissolveCountdown > 0 ? '…' + dissolveCountdown + 's' : '' }}
            </button>
          </template>
        </div>
        <button v-if="!guessResult.correct" class="btn btn-secondary" @click="guessResult = null">关闭</button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useGameStore } from '@/stores/game';
import { wsService } from '@/services/websocket';
import PublicCards from '@/components/PublicCards.vue';
import PlayerHand from '@/components/PlayerHand.vue';
import CandidateTable from '@/components/CandidateTable.vue';
import type { Color, Card, ClientCommand } from '@/types/game';
import { getColorClass, getColorValue, getPointFromNumber, getColorFromNumber } from '@/utils/game';

const gameStore = useGameStore();
const route = useRoute();
const router = useRouter();

const roomId = computed(() => String(route.query.roomId || gameStore.gameState?.roomId || 'ROOM001'));
const playerName = computed(() => String(route.query.playerName || 'Player'));
const playerId = computed(() => `${roomId.value}_${playerName.value}`);
const isHost = computed(() => route.query.isHost === 'true');

// 选中的公共牌
const selectedPublicCard = ref<Card | null>(null);

// 猜测弹窗
const showGuessModal = ref(false);
const guessForm = ref<Record<Color, number | null>>({
  红: null,
  蓝: null,
  绿: null,
  橙: null,
  粉: null
});

// 全局猜测结果弹窗
const guessResult = ref<{
  correct: boolean;
  guesses: number[];
  correctNumbers?: number[];
  playerName: string;
  gameOverInfo?: any;
} | null>(null);
const dissolveCountdown = ref(60);
let dissolveTimer: ReturnType<typeof setInterval> | null = null;

const colorsForGuess: Color[] = ['红', '蓝', '绿', '橙', '粉'];
const allGuessesFilled = computed(() => colorsForGuess.every(c => typeof guessForm.value[c] === 'number' && guessForm.value[c]! >= 1 && guessForm.value[c]! <= 60));

// 点数判定模式（点击手牌选择目标颜色）
const pointJudgeMode = ref(false);

// 计算属性
const gameState = computed(() => gameStore.gameState);
const currentPlayer = computed(() => gameStore.currentPlayer);
const otherPlayers = computed(() => gameStore.otherPlayers);
const orderedOtherPlayers = computed(() => {
  const state = gameState.value;
  if (!state || !state.turnOrder) return otherPlayers.value;
  const order: string[] = state.turnOrder;
  return order
    .map(pid => state.players[pid])
    .filter(p => p && p.playerId !== playerId.value);
});
const isMyTurn = computed(() => gameStore.isMyTurn);
const normalizedGamePhase = computed(() => String(gameState.value?.gamePhase || '').toUpperCase());
const normalizedSubPhase = computed(() => String(gameState.value?.subPhase || '').toUpperCase());

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

const totalDeckRemaining = computed(() => {
  if (!gameState.value || !gameState.value.deckRemainingCount) return 0;
  return Object.values(gameState.value.deckRemainingCount).reduce((s: number, v: any) => s + (Number(v) || 0), 0);
});

// 已选定的公共牌从显示中移除（不再出现）
const displayedPublicCards = computed(() => {
  const allCards = gameState.value?.publicCards || [];
  if (!selectedPublicCard.value) return allCards;
  return allCards.filter(c => c.id !== selectedPublicCard.value!.id);
});

// 退出房间
const exitRoom = () => {
  wsService.disconnect();
  router.push('/');
};

// WebSocket 事件处理
const handleStateUpdate = (state: any) => {
  console.log('[GameRoom] State updated:', state);
  // 判定完成后关闭点数判定模式（选定牌保留到用户手动取消或判定完成）
  pointJudgeMode.value = false;
};

const handleGuessResult = (result: any) => {
  console.log('[GameRoom] Guess result:', result);
  guessResult.value = result;
  showGuessModal.value = false;
  if (result.correct) {
    startDissolveCountdown();
  }
};

const startDissolveCountdown = () => {
  dissolveCountdown.value = 60;
  if (dissolveTimer) clearInterval(dissolveTimer);
  dissolveTimer = setInterval(() => {
    dissolveCountdown.value--;
    if (dissolveCountdown.value <= 0) {
      if (dissolveTimer) clearInterval(dissolveTimer);
      dissolveTimer = null;
      // 房主自动解散
      if (isHost.value) {
        sendCommand({ cmd: 'DissolveRoom' });
      }
    }
  }, 1000);
};

const handleDisconnect = (data: any) => {
  console.log('[GameRoom] Player disconnected:', data);
  if (data.isCurrentTurnPlayer && data.paused) {
    alert('当前操作玩家断线，游戏已暂停');
  }
};

const handleGameOver = (data: any) => {
  console.log('[GameRoom] Game over:', data);
  if (data) {
    guessResult.value = {
      correct: true,
      guesses: data.correctGuess || [],
      playerName: data.winnerName || '',
      gameOverInfo: data,
    };
    startDissolveCountdown();
  }
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
    sendCommand({ cmd: 'DeselectPublicCard' });
  } else {
    selectedPublicCard.value = card;
    sendCommand({ cmd: 'SelectPublicCard', publicCardId: card.id });
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

const startPointJudge = () => {
  if (!selectedPublicCard.value) return;
  pointJudgeMode.value = true;
};

const handlePointJudgeSelect = (color: Color) => {
  if (!selectedPublicCard.value || !pointJudgeMode.value) return;
  sendCommand({
    cmd: 'JudgeByPoint',
    publicCardId: selectedPublicCard.value.id,
    targetColor: color
  });
  pointJudgeMode.value = false;
};

const handleSkipTurn = () => {
  sendCommand({ cmd: 'SkipTurn' });
};

const handleSubmitGuess = () => {
  const guesses: number[] = colorsForGuess.map(c => guessForm.value[c]!);
  if (guesses.some(g => typeof g !== 'number' || g < 1 || g > 60)) {
    alert('请先在备选区点击或手牌区输入完整数字');
    return;
  }
  sendCommand({ cmd: 'SubmitGuess', guesses });
  showGuessModal.value = false;
};

const handleResetGame = () => {
  sendCommand({ cmd: 'ResetGame' });
  guessResult.value = null;
  if (dissolveTimer) clearInterval(dissolveTimer);
  dissolveTimer = null;
};

const handleDissolveRoom = () => {
  sendCommand({ cmd: 'DissolveRoom' });
  guessResult.value = null;
  if (dissolveTimer) clearInterval(dissolveTimer);
  dissolveTimer = null;
};

const handleHandNumberCommit = (color: Color, number: number) => {
  guessForm.value[color] = number;
};

// 获取某个数字对应颜色的相邻颜色（用于位置线索展示）
const neighborColor = (number: number): Color => {
  const colors: Color[] = ['红', '蓝', '绿', '橙', '粉'];
  const idx = colors.indexOf(getColorFromNumber(number));
  if (number % 5 === 0) {
    // 最后一列（60,55,50...）右边没有颜色，取左边
    return colors[(idx - 1 + 5) % 5];
  }
  // 取右边的颜色
  return colors[(idx + 1) % 5];
};

// 备选区表格选择事件处理
const handleCandidateSelect = (color: Color, num: number) => {
  guessForm.value[color] = num;
  console.log(`从备选区选择：${color} ${num}`);
};

// 生命周期
onMounted(() => {
  if (!route.query.roomId || !route.query.playerName) {
    router.replace('/');
    return;
  }

  gameStore.setMyPlayerId(playerId.value);
  
  // 连接 WebSocket
  wsService.setStateUpdateCallback(handleStateUpdate);
  wsService.setGuessResultCallback(handleGuessResult);
  wsService.setDisconnectCallback(handleDisconnect);
  wsService.setGameOverCallback(handleGameOver);
  wsService.setRoomClosedCallback(() => {
    alert('房间已解散');
    exitRoom();
  });
  
  if (wsService.getStatus() !== 'open') {
    wsService.connectWithUrl(`ws://localhost:8000/ws/${roomId.value}/${playerName.value}`);
  }
});

onUnmounted(() => {
  if (dissolveTimer) clearInterval(dissolveTimer);
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
  align-items: center;
  color: #666;
}

.exit-btn {
  background: #e53935;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
}
.exit-btn:hover {
  background: #c62828;
}

.game-main {
  display: grid;
  grid-template-columns: 3fr 1fr; /* ← 3:1 分栏，修改数值即可调整比例 */
  gap: 24px;
}

/* 备选区跨两列占满全宽 */
.candidate-section {
  grid-column: 1 / -1;
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
  padding: 12px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

section + section {
  margin-top: 12px;
}

/* 三个牌区卡片居中对齐（第3张牌对齐） */
.public-section .public-cards-inner,
.my-hand-section .my-hand-grid {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: nowrap;
}

.public-section .public-cards-inner > *,
.my-hand-section .my-hand-grid .card {
  flex-shrink: 0;
}

/* 其他玩家容器 —— 合并到一个框 */
.other-players-container {
  background: #fafafa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.other-player-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.opl-name-wrap {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  width: 100px;           /* 固定宽度，避免昵称影响居中 */
  justify-content: flex-start;
}

.opl-name {
  background: rgba(0, 0, 0, 0.72);
  color: white;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
  display: inline-block;
}

.opl-name-wrap.active-turn .opl-name {
  animation: breathe 1.5s ease-in-out infinite;
}

.opl-turn-icon {
  font-size: 11px;
  flex-shrink: 0;
}

.other-player-row .cards {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex: 1;
}

.other-player-row .cards .card {
  width: 56px;
  height: 76px;
  border: 2px solid rgba(255,255,255,0.3);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.other-player-row .cards .card .card-number {
  font-size: 18px;
}

.other-player-row .cards .card .point-dot {
  width: 4px;
  height: 4px;
}

.turn-indicator {
  margin-bottom: 20px;
  padding: 12px;
  border-radius: 6px;
  text-align: center;
}

.deck-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.deck-stack {
  width: 84px;
  height: 110px;
  border-radius: 8px;
  background: linear-gradient(180deg,#333,#111);
  color: white;
  display:flex;
  align-items:center;
  justify-content:center;
  font-weight:700;
  box-shadow: 0 8px 18px rgba(0,0,0,0.25);
}
.deck-count { color: #444; font-weight:600; }

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

.color-card-buttons {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.color-card-button {
  border: none;
  border-radius: 14px;
  padding: 18px 14px;
  color: white;
  cursor: pointer;
  text-align: center;
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.14);
}

.color-card-button:hover:not(:disabled) {
  transform: translateY(-2px);
  filter: brightness(1.05);
}

.color-card-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

.color-card-count {
  font-size: 18px;
  font-weight: 800;
  opacity: 0.95;
}

.color-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.color-card-button:nth-child(1) { background: linear-gradient(135deg, #ef5350, #d32f2f); }
.color-card-button:nth-child(2) { background: linear-gradient(135deg, #42a5f5, #1e88e5); }
.color-card-button:nth-child(3) { background: linear-gradient(135deg, #66bb6a, #43a047); }
.color-card-button:nth-child(4) { background: linear-gradient(135deg, #ffa726, #fb8c00); }
.color-card-button:nth-child(5) { background: linear-gradient(135deg, #ec407a, #d81b60); }

.judge-buttons {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.draw-phase, .action-phase {
  background: white;
  padding: 16px;
  border-radius: 6px;
  margin-bottom: 12px;
}

.selected-label {
  text-align: center;
  font-weight: 600;
  margin-bottom: 10px;
  color: #555;
}

.selected-card-visual {
  margin: 0 auto 8px;
}

.card-mini {
  width: 80px;
  height: 120px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  box-shadow: 0 4px 10px rgba(0,0,0,0.2);
}

.card-number-small {
  font-size: 32px;
  font-weight: 800;
  color: white;
  text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}

.card-mini .point-dots {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 3px;
}

.card-mini .point-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.85);
}

.point-judge-hint {
  margin-top: 8px;
  padding: 10px;
  background: #fff8e1;
  border: 1px solid #ffe082;
  border-radius: 6px;
  font-size: 13px;
  text-align: center;
  color: #f57f17;
  animation: pulse-hint 1.5s ease-in-out infinite;
}

@keyframes pulse-hint {
  0%,100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.game-over-info {
  margin-top: 16px;
  padding: 12px;
  background: #fff3e0;
  border-radius: 6px;
  text-align: center;
}

.game-over-info h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
  color: #e65100;
}

/* 右侧栏个人线索卡片 */
.my-clues-section {
  margin-top: 16px;
  background: white;
  padding: 12px;
  border-radius: 6px;
}

.my-clues-section h3 {
  margin: 0 0 12px 0;
  font-size: 16px;
  color: #333;
}

.my-clue-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.my-clue-card {
  padding: 10px 12px;
  background: #f0f4ff;
  border-left: 3px solid #42a5f5;
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.6;
}

.my-clue-card:first-child {
  font-size: 15px;
  font-weight: 600;
  background: #e3f2fd;
  border-left-color: #1976d2;
}

.clue-html {
  font-size: inherit;
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

/* 猜测预览 */
.guess-preview {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin: 12px 0;
  flex-wrap: wrap;
}

.guess-preview-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  color: white;
  font-weight: 700;
  min-width: 50px;
}

.gp-color { font-size: 11px; opacity: 0.85; }
.gp-number { font-size: 22px; }

.result-modal h2 { text-align: center; }
.result-subtitle { text-align: center; color: #666; }
.result-correct { text-align: center; color: #2e7d32; font-weight: 700; }
.result-wrong { text-align: center; color: #c62828; }
.result-actions { display: flex; gap: 12px; justify-content: center; margin-top: 16px; }
</style>
