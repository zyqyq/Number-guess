<template>
  <div class="game-room" :class="{ 'is-spectator': isSpectator }">
    <!-- 顶部信息栏 -->
    <header class="game-header">
      <h1>猜数字游戏</h1>
      <div class="room-info">
        <span>房间号：{{ roomId }}</span>
        <span v-if="isSpectator" class="spectator-chip" title="你正在旁观，不会影响牌局">👁 旁观中</span>
        <span v-if="gameState?.isPrivate" class="private-chip" title="隐身房间不出现在首页房间列表">🔒 隐身</span>
        <span>轮次：{{ gameState?.roundNumber || 0 }}</span>
        <button class="share-btn" type="button" title="复制分享链接" @click="copyShareLink">🔗 分享</button>
        <button v-if="isHost && (normalizedGamePhase === 'PLAYING' || normalizedGamePhase === 'GAME_OVER')" class="reset-btn" @click="handleResetGame">🔄 重置</button>
        <button class="exit-btn" @click="exitRoom">🚪 {{ isSpectator ? '退出旁观' : '退出' }}</button>
      </div>
    </header>

    <!-- 旁观模式通栏提示 + 视角切换器 -->
    <div v-if="isSpectator" class="spectator-banner">
      <span class="sb-icon">👁</span>
      <span class="sb-text">
        旁观模式 · 正代入 <b>{{ spectateViewName || '（等待）' }}</b> 的视角：手牌与线索与 TA 完全一致，所有操作按钮已禁用
      </span>
      <span v-if="spectateOptions.length" class="sb-views">
        <span class="sb-views-label">切换视角</span>
        <button
          v-for="opt in spectateOptions"
          :key="opt.playerId"
          type="button"
          class="sb-view-btn"
          :class="{ active: opt.playerId === spectateViewId }"
          @click="setSpectateView(opt.playerId)"
        >
          {{ opt.playerName }}
        </button>
      </span>
    </div>

    <!-- 旁观者操作提示（只读拦截 / 禁言 / 视角切换等） -->
    <transition name="share-fade">
      <div v-if="spectatorNotice" class="spectator-notice">{{ spectatorNotice }}</div>
    </transition>

    <!-- 分享链接复制结果提示 -->
    <transition name="share-fade">
      <div v-if="shareTip" class="share-toast">{{ shareTip }}</div>
    </transition>

    <!-- 主游戏区：中间保持原有布局与宽度，左右两侧空白区各挂一栏 -->
    <main class="game-layout">
      <!-- 左侧空白区：个人线索栏（原在右侧操作面板内） -->
      <aside class="side-rail rail-left">
        <div v-if="currentPlayer?.clues?.length" class="rail-card clue-card">
          <h3 class="rail-title">🧩 线索</h3>
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
                  <template v-if="posResult(clue) as any">
                  <template v-if="posResult(clue)?.leftColor && posResult(clue)?.rightColor">
                  数字 {{ clue.publicCardNumber }}
                    在
                    <span :style="{ color: getColorValue(posResult(clue)?.leftColor!), fontWeight: 700 }">{{ posResult(clue)?.leftColor }}</span>
                    和
                    <span :style="{ color: getColorValue(posResult(clue)?.rightColor!), fontWeight: 700 }">{{ posResult(clue)?.rightColor }}</span>
                    之间
                  </template>
                  <template v-else-if="!posResult(clue)?.leftColor && posResult(clue)?.rightColor">
                  数字 {{ clue.publicCardNumber }}
                    比
                    <span :style="{ color: getColorValue(posResult(clue)?.rightColor!), fontWeight: 700 }">{{ posResult(clue)?.rightColor }}</span>
                    还小
                  </template>
                  <template v-else-if="posResult(clue)?.leftColor && !posResult(clue)?.rightColor">
                  数字 {{ clue.publicCardNumber }}
                    比
                    <span :style="{ color: getColorValue(posResult(clue)?.leftColor!), fontWeight: 700 }">{{ posResult(clue)?.leftColor }}</span>
                    还大
                  </template>
                  </template>
                </span>
              </div>
            </div>
          </div>
        </div>
        <section v-else class="rail-card clue-card">
          <h3 class="rail-title">🧩 线索</h3>
          <p class="rail-empty">还没有线索<br />完成一次判定后显示</p>
        </section>
      </aside>

      <div class="game-main">
        <!-- 左侧：牌区和玩家手牌 -->
        <div class="left-panel">
          <!-- 公共牌区 -->
          <section class="public-section">
            <PublicCards 
              :publicCards="displayedPublicCards"
              :clickable="isMyTurn && normalizedSubPhase === 'ACTION_PHASE'"
              :attract="isMyTurn && normalizedSubPhase === 'ACTION_PHASE' && !selectedPublicCard"
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
                  <span v-if="player.isBot" class="opl-bot-badge">🤖</span>
                  <span v-if="gameState?.currentTurnPlayerId === player.playerId" class="opl-turn-icon">⚡</span>
                </div>
                <div class="cards">
                  <div
                    v-for="card in [...player.hand].sort((a, b) => a.number - b.number)"
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
        <aside class="right-panel" :class="{ 'is-my-turn': isMyActiveTurn }">
          <div class="turn-indicator" :class="isMyActiveTurn ? 'is-mine' : 'is-other'">
            <div v-if="isMyActiveTurn" class="my-turn">
              <span class="pulse-dot"></span>
              <span class="my-turn-main">轮到你了！</span>
              <span class="my-turn-sub">{{ myTurnHint }}</span>
            </div>
            <div v-else class="other-turn">
              <template v-if="normalizedGamePhase === 'GAME_OVER'">本局已结束</template>
              <template v-else-if="normalizedGamePhase === 'WAITING'">等待房主开始游戏</template>
              <template v-else-if="normalizedSubPhase === 'PAUSED'">⏸ 当前玩家已断线，牌局暂停</template>
              <template v-else-if="isBotTurn">🤖 {{ getCurrentPlayerName }} 正在思考…</template>
              <template v-else>等待 {{ getCurrentPlayerName }} 操作…</template>
            </div>
          </div>

          <!-- 回合步骤条：抽牌 → 选牌 → 判定，两个阶段共用同一条，随阶段推进 -->
          <div
            v-if="isMyActiveTurn && (normalizedSubPhase === 'DRAW_PHASE' || normalizedSubPhase === 'ACTION_PHASE')"
            class="step-bar"
          >
            <div class="step" :class="stepClass(1)">
              <span class="step-index">{{ currentStep > 1 ? '✓' : '1' }}</span>
              <span class="step-label">抽牌</span>
            </div>
            <span class="step-arrow">→</span>
            <div class="step" :class="stepClass(2)">
              <span class="step-index">{{ currentStep > 2 ? '✓' : '2' }}</span>
              <span class="step-label">选牌</span>
            </div>
            <span class="step-arrow">→</span>
            <div class="step" :class="stepClass(3)">
              <span class="step-index">3</span>
              <span class="step-label">判定</span>
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
            <div v-if="normalizedSubPhase === 'DRAW_PHASE' && isMyActiveTurn" class="draw-phase">
              <div class="color-card-buttons">
                <button
                  v-for="count in colorCounts"
                  :key="count.color"
                  class="color-card-button"
                  :disabled="count.count === 0"
                  @click="handleSelectColor(count.color)"
                >
                  <span class="color-card-name">{{ count.color }}</span>
                  <span class="color-card-count">{{ count.count }}</span>
                </button>
              </div>
            </div>

            <!-- 判定阶段 -->
            <div v-if="normalizedSubPhase === 'ACTION_PHASE' && isMyActiveTurn" class="action-phase">
              <template v-if="selectedPublicCard">
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
              </template>
              <div class="judge-buttons">
                <button
                  class="btn btn-secondary"
                  :disabled="!selectedPublicCard"
                  @click="handleJudgeByPosition"
                >
                  位置判定
                </button>
                <button
                  class="btn btn-secondary"
                  :class="{ 'is-picking': pointJudgeMode }"
                  :disabled="!selectedPublicCard"
                  @click="startPointJudge"
                >
                  {{ pointJudgeMode ? '点一张手牌' : '点数判定' }}
                </button>
              </div>
            </div>

            <!-- 提交猜测按钮 -->
            <button
              v-if="normalizedGamePhase === 'PLAYING' || normalizedGamePhase === 'WAITING'"
              class="btn btn-danger"
              @click="showGuessModal = true"
            >
              提交猜测
            </button>

            <!-- 房主跳过按钮 -->
            <button 
              v-if="isHost && normalizedSubPhase === 'ACTION_PHASE' && normalizedGamePhase === 'PLAYING'"
              class="btn btn-warning"
              @click="handleSkipTurn"
            >
              跳过本轮
            </button>
          </div>

          <!-- 旁观者：盖住整个操作区（pointer-events 全挡，服务端另有兜底拦截） -->
          <div v-if="isSpectator" class="spectator-lock">
            <span class="sl-icon">👁</span>
            <span class="sl-text">旁观中，不可操作牌局</span>
            <span class="sl-sub">想亲自玩？点右上角「退出旁观」回首页开房或加入</span>
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

        <!-- 备选区表格（跨两列） -->
        <section class="candidate-section">
          <CandidateTable
            :selectedNumbers="guessForm"
            :revealedCards="revealedCards"
            @select-number="handleCandidateSelect"
          />
        </section>
      </div>

      <!-- 右侧空白区：聊天室（文字 + 语音通话） -->
      <aside class="side-rail rail-right">
        <ChatPanel
          :roomId="roomId"
          :playerId="spectatorId || playerId"
          :playerName="spectatorName || playerName"
          :isHost="isHost"
          :players="chatMembers"
        />
      </aside>
    </main>

    <!-- 猜测弹窗（直接用手牌区已填的数字） -->
    <div v-if="showGuessModal" class="modal-overlay" @click.self="showGuessModal = false">
      <div class="modal">
        <h2>提交你的猜测</h2>
        <p>你的手牌区已填的数字将作为猜测结果提交</p>
        <div class="guess-preview">
          <span v-for="item in sortedGuessPreview" :key="item.color" class="guess-preview-item" :style="{ background: getColorValue(item.color) }">
            <span class="gp-color">{{ item.color }}</span>
            <span class="gp-number">{{ item.number ?? '?' }}</span>
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
        <template v-if="showGuesses || guessResult.correct">
          <h2>{{ guessResult.correct ? '🎉 猜对了！' : '❌ 猜错了' }}</h2>
          <p class="result-subtitle">{{ guessResult.playerName }} 的猜测：</p>
          <div v-if="showGuesses" class="guess-preview">
            <span v-for="g in sortedGuesses" :key="g" class="guess-preview-item" :style="{ background: getColorValue(getColorFromNumber(g)) }">
              <span class="gp-number">{{ g }}</span>
            </span>
          </div>
          <p v-if="guessResult.correct" class="result-correct">游戏结束！{{ guessResult.playerName }} 获胜！</p>
          <template v-else>
            <p class="result-wrong">正确答案：</p>
            <div class="guess-preview">
              <span v-for="n in sortedCorrectNumbers" :key="n" class="guess-preview-item" :style="{ background: getColorValue(getColorFromNumber(n)) }">
                <span class="gp-number">{{ n }}</span>
              </span>
            </div>
            <p class="result-hint">点击「关闭」以继续游戏</p>
            <div style="height:8px"></div>
          </template>
        </template>
        <template v-else>
          <h2>❌ 猜错了</h2>
          <p class="result-subtitle">{{ guessResult.playerName }} 猜错了</p>
          <p class="result-hint">点击「关闭」以继续游戏</p>
          <div style="height:8px"></div>
        </template>
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
        <button v-if="!guessResult.correct" class="btn btn-secondary" @click="handleCloseWrongGuess">关闭</button>
      </div>
    </div>

    <!-- 观战审批等待（仅旁观者，牌局进行中才会出现） -->
    <div v-if="spectatorWaiting" class="spectate-waiting">
      <div class="sw-card">
        <div class="sw-spinner"></div>
        <p class="sw-title">正在等待房主批准旁观…</p>
        <p class="sw-sub">牌局正在进行，房主同意后即可进入（60 秒无响应自动取消）</p>
        <button class="sw-cancel" type="button" @click="exitRoom">取消并返回首页</button>
      </div>
    </div>

    <!-- 房主：游戏中收到的旁观申请 -->
    <SpectatorAskModal :ask="pendingAsk" @respond="respondSpectator" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useGameStore } from '@/stores/game';
import { wsService } from '@/services/websocket';
import { getClientId } from '@/services/presence';
import PublicCards from '@/components/PublicCards.vue';
import PlayerHand from '@/components/PlayerHand.vue';
import CandidateTable from '@/components/CandidateTable.vue';
import ChatPanel from '@/components/ChatPanel.vue';
import SpectatorAskModal from '@/components/SpectatorAskModal.vue';
import type { Color, Card, ClientCommand } from '@/types/game';
import { getColorClass, getColorValue, getPointFromNumber, getColorFromNumber } from '@/utils/game';
import { useDeduction } from '@/composables/gameLogic';

const gameStore = useGameStore();
const route = useRoute();
const router = useRouter();

const roomId = computed(() => String(route.query.roomId || gameStore.gameState?.roomId || 'ROOM001'));
const playerName = computed(() => String(route.query.playerName || 'Player'));
const playerId = computed(() => `${roomId.value}_${playerName.value}`);
// 房主身份以服务端 hostId 为准（手动填房号加入的第一人也是房主）
const isHost = computed(() => !!gameState.value?.hostId && gameState.value.hostId === playerId.value);

// ---------------------------------------------------------------- 旁观者
// 旁观者复用参赛者界面（D1 视角代入）：把 store 的 myPlayerId 指向「代入的玩家」，
// 手牌问号、线索、回合提示自然与真身一致；写操作由服务端统一拦截。
const isSpectator = computed(() => String(route.query.spectate || '') === '1');
// 从大厅等待界面跳过来时连接是复用的，身份只在 store 里，这里先认领回来
const spectatorId = ref(isSpectator.value ? gameStore.spectatorId : '');
const spectatorName = ref(isSpectator.value ? gameStore.spectatorName : '');
const spectateViewId = ref(isSpectator.value ? gameStore.spectatorView : '');
const spectatorWaiting = ref(false);
const spectatorMuted = ref(false);
const spectatorNotice = ref('');
// 房主在游戏页收到的旁观申请（游戏期审批只可能落在游戏页）
const pendingAsk = ref<{ playerId: string; playerName: string } | null>(null);
let spectatorNoticeTimer: number | undefined;
const showSpectatorNotice = (text: string, ms = 2800) => {
  spectatorNotice.value = text;
  if (spectatorNoticeTimer !== undefined) window.clearTimeout(spectatorNoticeTimer);
  spectatorNoticeTimer = window.setTimeout(() => {
    spectatorNotice.value = '';
  }, ms);
};

const spectateOptions = computed(() => {
  const st = gameState.value;
  if (!st || !st.players) return [];
  const ids = st.turnOrder && st.turnOrder.length ? st.turnOrder : Object.keys(st.players);
  return ids.filter((id) => st.players[id]).map((id) => ({ playerId: id, playerName: st.players[id].playerName }));
});

const spectateViewName = computed(() => {
  const st = gameState.value;
  if (!st || !spectateViewId.value) return '';
  return st.players?.[spectateViewId.value]?.playerName || '';
});

const setSpectateView = (target: string) => {
  if (!isSpectator.value || !target || target === spectateViewId.value) return;
  spectateViewId.value = target;
  gameStore.setMyPlayerId(target);
  wsService.send({ cmd: 'SpectateSetView', targetPlayerId: target } as ClientCommand);
};

/** 聊天/语音的成员表：参赛者 + 旁观者（语音成员列表里要能显示旁观者昵称） */
const chatMembers = computed(() => {
  const st = gameState.value;
  const base: Record<string, { playerId: string; playerName: string; isBot?: boolean }> = {};
  for (const [pid, p] of Object.entries(st?.players || {})) {
    base[pid] = { playerId: pid, playerName: (p as any).playerName, isBot: !!(p as any).isBot };
  }
  for (const s of st?.spectators || []) {
    if (!base[s.playerId]) {
      base[s.playerId] = { playerId: s.playerId, playerName: s.playerName, isBot: false };
    }
  }
  if (spectatorId.value && !base[spectatorId.value]) {
    base[spectatorId.value] = {
      playerId: spectatorId.value,
      playerName: spectatorName.value || '旁观者',
      isBot: false,
    };
  }
  return base;
});

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
  playerId: string;
  gameOverInfo?: any;
} | null>(null);
const dissolveCountdown = ref(60);
let dissolveTimer: ReturnType<typeof setInterval> | null = null;

const colorsForGuess: Color[] = ['红', '蓝', '绿', '橙', '粉'];
const allGuessesFilled = computed(() => colorsForGuess.every(c => typeof guessForm.value[c] === 'number' && guessForm.value[c]! >= 1 && guessForm.value[c]! <= 60));

const sortedGuessPreview = computed(() => {
  const items = colorsForGuess.map(c => ({ color: c, number: guessForm.value[c] }));
  return items.sort((a, b) => (a.number ?? 999) - (b.number ?? 999));
});

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
// 真正「该我操作」：牌局进行中且当前回合是自己（等待/结束阶段不算）
const isMyActiveTurn = computed(() => isMyTurn.value && normalizedGamePhase.value === 'PLAYING');

const getCurrentPlayerName = computed(() => {
  if (!gameState.value?.currentTurnPlayerId) return '';
  const player = gameState.value.players[gameState.value.currentTurnPlayerId];
  return player?.playerName || '';
});

const isBotTurn = computed(() => {
  const pid = gameState.value?.currentTurnPlayerId;
  if (!pid) return false;
  return !!gameState.value?.players?.[pid]?.isBot;
});

// 当前进行到第几步：1 抽牌 / 2 选牌 / 3 判定；0 表示当前不在行动阶段
const currentStep = computed(() => {
  if (!isMyActiveTurn.value) return 0;
  const sub = normalizedSubPhase.value;
  if (sub === 'DRAW_PHASE') return 1;
  if (sub === 'ACTION_PHASE') return selectedPublicCard.value ? 3 : 2;
  return 0;
});

const stepClass = (n: number) => ({
  'step-active': currentStep.value === n,
  'step-done': currentStep.value > n,
});

const myTurnHint = computed(() => {
  const sub = normalizedSubPhase.value;
  if (sub === 'DRAW_PHASE') return '先选一种颜色抽牌';
  if (sub === 'ACTION_PHASE') {
    return selectedPublicCard.value ? '已选公牌，请选择判定方式' : '请先在左侧点选一张公牌';
  }
  if (sub === 'JUDGE_RESULT') return '判定结算中…';
  return '';
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

// 直接展示后端返回的公共牌（后端已根据 selectedPublicCardId 过滤）
const displayedPublicCards = computed(() => gameState.value?.publicCards || []);

// 备选区自动标灰
const deduction = useDeduction();
const revealedCards = computed(() => deduction.revealedNumbers.value);

// 猜测结果弹窗中是否显示猜测者本人的数字（只有本人可见；旁观者按代入视角算）
const showGuesses = computed(() => {
  const me = isSpectator.value ? spectateViewId.value : playerId.value;
  return guessResult.value?.playerId === me;
});

// 猜测数字按从小到大排序
const sortedGuesses = computed(() => {
  if (!guessResult.value?.guesses) return [];
  return [...guessResult.value.guesses].sort((a, b) => a - b);
});

const sortedCorrectNumbers = computed(() => {
  if (!guessResult.value?.correctNumbers) return [];
  return [...guessResult.value.correctNumbers].sort((a, b) => a - b);
});

// 退出房间
// 分享本房：房间号夹在 URL 里，对方打开首页即自动预填
const shareTip = ref('');
let shareTipTimer: number | undefined;
const showShareTip = (text: string) => {
  shareTip.value = text;
  if (shareTipTimer !== undefined) window.clearTimeout(shareTipTimer);
  shareTipTimer = window.setTimeout(() => {
    shareTip.value = '';
  }, 3000);
};
const copyShareLink = async () => {
  const url = `${window.location.origin}/?roomId=${roomId.value}`;
  try {
    await navigator.clipboard.writeText(url);
    showShareTip('分享链接已复制，发给好友即可进入本房');
  } catch (err) {
    showShareTip(`复制失败，请手动复制：${url}`);
  }
};

/** 主动离开：先告诉服务端（不告诉的话会被当成「断线」，位置一直挂着等重连） */
const exitRoom = () => {
  const leaveCmd: ClientCommand = isSpectator.value
    ? { cmd: 'SpectatorLeave' }
    : { cmd: 'LeaveRoom' };
  wsService.send(leaveCmd);
  wsService.disconnect();
  router.push('/');
};

/** 服务端已经把房间/人清掉了（解散、被踢、审批被拒），不必再发指令 */
const exitRoomQuiet = () => {
  wsService.disconnect();
  router.push('/');
};

// WebSocket 事件处理
const handleStateUpdate = (state: any) => {
  console.log('[GameRoom] State updated:', state);
  // 判定完成后关闭点数判定模式（选定牌保留到用户手动取消或判定完成）
  pointJudgeMode.value = false;
  // 旁观者：代入的玩家中途退出时，跟服务端一起回退到仍在座的第一位玩家
  if (isSpectator.value) {
    const players = state?.players || {};
    if (spectateViewId.value && !players[spectateViewId.value]) {
      const order: string[] = state?.turnOrder || [];
      const fallback = order.find((id) => players[id]) || Object.keys(players)[0];
      if (fallback) {
        spectateViewId.value = fallback;
        gameStore.setMyPlayerId(fallback);
      }
    }
  }
  // 新回合开始（抽牌阶段）时清空选牌
  const sp = String(state?.subPhase || '').toUpperCase();
  if (sp === 'DRAW_PHASE') {
    selectedPublicCard.value = null;
  }
  // 重置到等待界面时清空所有本地状态并跳转回大厅
  const gp = String(state?.gamePhase || '').toUpperCase();
  if (gp === 'WAITING') {
    guessResult.value = null;
    guessForm.value = { 红: null, 蓝: null, 绿: null, 橙: null, 粉: null };
    selectedPublicCard.value = null;
    pointJudgeMode.value = false;
    if (dissolveTimer) clearInterval(dissolveTimer);
    dissolveTimer = null;
    // 牌局还没开始：所有人先回等待界面。旁观者同样进大厅的等待视图（只读、
    // 没有房主操作），不留在游戏主界面。连接不断开，直接复用。
    if (isSpectator.value) {
      router.replace({
        path: '/lobby',
        query: { roomId: roomId.value, playerName: playerName.value, spectate: '1' }
      });
      return;
    }
    // 不断开 WebSocket，直接跳转 Lobby 复用连接
    router.push({
      path: '/lobby',
      query: {
        roomId: roomId.value,
        playerName: playerName.value,
        isHost: String(isHost.value)
      }
    });
    return;
  }
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
      playerId: data.winnerId || '',
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
  pointJudgeMode.value = !pointJudgeMode.value;
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
  guessForm.value = { 红: null, 蓝: null, 绿: null, 橙: null, 粉: null };
  selectedPublicCard.value = null;
  pointJudgeMode.value = false;
  if (dissolveTimer) clearInterval(dissolveTimer);
  dissolveTimer = null;
};

const handleDissolveRoom = () => {
  sendCommand({ cmd: 'DissolveRoom' });
  guessResult.value = null;
  if (dissolveTimer) clearInterval(dissolveTimer);
  dissolveTimer = null;
};

const handleCloseWrongGuess = () => {
  if (guessResult.value?.correctNumbers && guessResult.value.playerId === playerId.value) {
    // 仅猜测者本人：关闭弹窗后将正确答案填入牌区
    const correctNumbers: number[] = guessResult.value.correctNumbers;
    colorsForGuess.forEach((c, i) => {
      guessForm.value[c] = correctNumbers[i];
    });
  }
  guessResult.value = null;
};

const handleHandNumberCommit = (color: Color, number: number) => {
  guessForm.value[color] = number;
};

/** 获取位置线索的详细结果（类型安全） */
const posResult = (clue: { type: string; result: any }) => {
  if (clue.type === 'position' && clue.result && typeof clue.result !== 'boolean') {
    return clue.result as { position: number; leftColor: Color | null; rightColor: Color | null };
  }
  return null;
};

// 备选区表格选择事件处理
const handleCandidateSelect = (color: Color, num: number) => {
  guessForm.value[color] = num;
  console.log(`从备选区选择：${color} ${num}`);
};

/** 旁观者相关事件（审批 / 视角 / 禁言 / 只读拦截） */
const handleSpectatorEvent = (event: string, payload: any) => {
  if (event === 'Event_SpectateReady') {
    spectatorWaiting.value = false;
    spectatorMuted.value = !!payload?.muted;
    spectatorId.value = payload?.playerId || '';
    spectatorName.value = payload?.playerName || '';
    const view = payload?.viewId || '';
    if (view) {
      spectateViewId.value = view;
      gameStore.setMyPlayerId(view);
    }
    // 身份存进 store：跳到大厅的等待界面时连接是复用的，
    // Event_SpectateReady 不会再发一次，得靠 store 带过去
    gameStore.setSpectator(spectatorId.value, spectatorName.value, view);
    showSpectatorNotice(
      payload?.hidden ? '已以管理员身份隐身旁观（其他玩家看不到你）' : '已进入旁观模式',
      3200
    );
    return;
  }
  if (event === 'Event_SpectatorWaiting') {
    spectatorWaiting.value = true;
    return;
  }
  if (event === 'Event_SpectatorAsk') {
    pendingAsk.value = { playerId: payload?.playerId, playerName: payload?.playerName };
    return;
  }
  if (event === 'Event_SpectatorRejected') {
    spectatorWaiting.value = false;
    if (payload?.reason === 'kicked') {
      alert(payload?.text || '你已被房主移出旁观');
    } else {
      alert(payload?.text || payload?.reason || '无法旁观该房间');
    }
    exitRoomQuiet();
    return;
  }
  if (event === 'Event_SpectateView') {
    if (payload?.targetPlayerId) {
      spectateViewId.value = payload.targetPlayerId;
      gameStore.setMyPlayerId(payload.targetPlayerId);
      showSpectatorNotice(`已切换到 ${payload.targetName || '该玩家'} 的视角`, 2000);
    }
    return;
  }
  if (event === 'Event_SpectatorMuted') {
    spectatorMuted.value = !!payload?.muted;
    showSpectatorNotice(payload?.muted ? '你已被房主禁言，暂时不能发言' : '房主已解除你的禁言');
    return;
  }
  if (event === 'Event_SpectatorLeft') {
    exitRoomQuiet();
    return;
  }
  if (event === 'Event_ActionRejected') {
    showSpectatorNotice(payload?.reason || '该操作不可用', 2000);
  }
};

/** 房主在游戏页审批旁观申请 */
const respondSpectator = (payload: { allow: boolean; allowChat: boolean; allowVoice: boolean }) => {
  const ask = pendingAsk.value;
  if (!ask) return;
  wsService.send({
    cmd: 'SpectatorRespond',
    playerId: ask.playerId,
    allow: payload.allow,
    allowChat: payload.allowChat,
    allowVoice: payload.allowVoice
  } as ClientCommand);
  showSpectatorNotice(
    payload.allow ? `已允许 ${ask.playerName} 旁观` : `已拒绝 ${ask.playerName} 的旁观申请`,
    2600
  );
  pendingAsk.value = null;
};

// 生命周期
onMounted(() => {
  if (!route.query.roomId || !route.query.playerName) {
    router.replace('/');
    return;
  }

  // 参赛者先认领自己；旁观者要等 Event_SpectateReady 带回「代入视角」后再设置 myPlayerId
  if (!isSpectator.value) gameStore.setMyPlayerId(playerId.value);

  // 连接 WebSocket
  wsService.setStateUpdateCallback(handleStateUpdate);
  wsService.setGuessResultCallback(handleGuessResult);
  wsService.setDisconnectCallback(handleDisconnect);
  wsService.setGameOverCallback(handleGameOver);
  wsService.setSpectatorEventCallback(handleSpectatorEvent);
  wsService.setChatRejectedCallback((payload) => showSpectatorNotice(payload.reason, 2600));
  wsService.setRoomClosedCallback(() => {
    alert('房间已解散');
    exitRoomQuiet();
  });
  wsService.setFatalCallback((message: string) => {
    alert(message);
    exitRoomQuiet();
  });

  if (wsService.getStatus() !== 'open') {
    // WS 地址跟随当前访问主机，支持局域网其他设备接入
    let wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/${roomId.value}/${playerName.value}?clientId=${getClientId()}`;
    if (isSpectator.value) {
      wsUrl += '&spectate=1';
      const adminToken = route.query.adminToken;
      if (adminToken) wsUrl += `&adminToken=${encodeURIComponent(String(adminToken))}`;
    }
    wsService.connectWithUrl(wsUrl);
  }
});

onUnmounted(() => {
  if (dissolveTimer) clearInterval(dissolveTimer);
  if (spectatorNoticeTimer !== undefined) window.clearTimeout(spectatorNoticeTimer);
});
</script>

<style scoped>
.game-room {
  /* 全宽：中间游戏区保持原有宽度并居中，左右空白区各挂一栏 */
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f2f4f8;
}

.game-header {
  /* 标题栏横向铺满整屏 */
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 28px;
  background: #ffffff;
  border-bottom: 1px solid #e3e7ee;
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.05);
  position: sticky;
  top: 0;
  z-index: 20;
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

.reset-btn {
  background: #ff8f00;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
}
.reset-btn:hover {
  background: #e65100;
}

.share-btn {
  background: #fff;
  border: 1px solid #c7cbe6;
  color: #4a4fa2;
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.share-btn:hover {
  background: #eef0ff;
  border-color: #667eea;
}

.private-chip {
  padding: 3px 8px;
  border-radius: 999px;
  background: #fff4e5;
  color: #c2751b;
  font-size: 12px;
  font-weight: 600;
}

.share-toast {
  position: fixed;
  left: 50%;
  bottom: 32px;
  transform: translateX(-50%);
  z-index: 60;
  padding: 10px 18px;
  border-radius: 10px;
  background: rgba(30, 30, 46, 0.92);
  color: #fff;
  font-size: 13px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
}

.share-fade-enter-active,
.share-fade-leave-active {
  transition: opacity 0.25s ease;
}

.share-fade-enter-from,
.share-fade-leave-to {
  opacity: 0;
}

/* 三栏：左空白（线索） | 中间原有游戏区 | 右空白（预留聊天室）
   两侧等宽、中间固定上限 1400px，保证原有元素仍在屏幕正中 */
.game-layout {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(0, 1200px) minmax(180px, 1fr);
  gap: 20px;
  padding: 12px 20px 16px;
  align-items: stretch;
}

.side-rail {
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: calc(100vh - 96px);
}

.rail-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 12px;
  text-align: left;
}

.clue-card {
  flex: 1 1 auto;
  min-height: 0;
}

.rail-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 700;
  color: #37474f;
  flex-shrink: 0;
}

.rail-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
  font-size: 12px;
  line-height: 1.8;
  color: #9aa7b4;
  text-align: center;
}

/* 线索栏的空态靠上，避免高栏里文字飘在正中 */
.clue-card .rail-empty {
  align-items: flex-start;
  padding-top: 4px;
}

.chat-card {
  flex: 1 1 auto;
  min-height: 0;
}

/* 中间游戏区：沿用原有 3:1 分栏 */
.game-main {
  display: grid;
  grid-template-columns: 3fr 1fr; /* ← 3:1 分栏，修改数值即可调整比例 */
  gap: 24px;
  align-items: stretch;
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

/* 右侧操作区：撑满行高，与左侧三块（公牌 / 其他玩家 / 我的手牌）上下齐平 */
.right-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: white;
  padding: 12px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

section {
  background: white;
  padding: 12px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

section + section {
  margin-top: 0px;
}

/* 三个牌区卡片居中对齐（第3张牌对齐） */
.public-section .public-cards-inner,
.my-hand-section .my-hand-grid {
  display: flex;
  justify-content: center;
  gap: 6px;
  flex-wrap: nowrap;
}

.public-section .public-cards-inner > *,
.my-hand-section .my-hand-grid .card {
  flex-shrink: 0;
}

/* 其他玩家容器 —— 合并到一个框 */
.other-players-container {
  background: #ffffff;
  border: 1px solid #ffffff;
  border-radius: 8px;
  padding: 0px 0px;
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

.opl-bot-badge {
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
  margin-bottom: 12px;
  padding: 10px;
  border-radius: 6px;
  text-align: center;
  flex-shrink: 0;
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
  flex-direction: row;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
}

.color-card-button {
  position: relative;
  border: none;
  border-radius: 6px;
  padding: 12px 24px;
  color: white;
  cursor: pointer;
  text-align: center;
  font-size: 14px;
  font-weight: bold;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.16);
  width: 100%;
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
  margin-top: 0;
}

.draw-phase, .action-phase {
  background: transparent;
  padding: 0;
  margin-bottom: 0;
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

/* 左侧栏个人线索卡片（窄列适配，超出可滚动） */
.my-clue-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
}

.my-clue-card {
  padding: 8px 10px;
  background: #f0f4ff;
  border-left: 3px solid #42a5f5;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.my-clue-card:first-child {
  font-size: 13px;
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
  color: rgb(0, 0, 0);
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

/* ===== 轮次视觉指引 ===== */

/* 右侧操作栏：轮到本人时整栏高亮 */
.right-panel {
  position: relative;
  border: 2px solid transparent;
  transition: border-color .3s ease, box-shadow .3s ease, transform .3s ease;
}

.right-panel.is-my-turn {
  border-color: #ff9800;
  animation: panel-glow 2.2s ease-in-out infinite;
}

@keyframes panel-glow {
  0%, 100% { box-shadow: 0 0 0 3px rgba(255, 152, 0, .12), 0 6px 18px rgba(255, 152, 0, .28); }
  50%      { box-shadow: 0 0 0 7px rgba(255, 152, 0, .22), 0 10px 26px rgba(255, 152, 0, .42); }
}

@keyframes pulse-ring {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%      { transform: scale(1.6); opacity: .55; }
}

/* 回合横幅 */
.turn-indicator.is-mine {
  background: linear-gradient(135deg, #ff9800, #f57c00);
  color: #fff;
  box-shadow: 0 6px 18px rgba(255, 152, 0, .35);
}

.turn-indicator.is-mine .my-turn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  background: transparent;
  color: #fff;
}

.my-turn-main {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 1px;
}

.my-turn-main::after {
  content: '';
  display: block;
  margin: 4px auto 0;
  width: 68%;
  height: 2px;
  border-radius: 2px;
  background: rgba(255, 255, 255, .75);
}

.my-turn-sub {
  font-size: 12px;
  font-weight: 600;
  opacity: .95;
}

.turn-indicator.is-mine .pulse-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
  animation: pulse-ring 1.4s ease-in-out infinite;
}

.turn-indicator.is-other {
  background: #e3f2fd;
  color: #1976d2;
}

.turn-indicator.is-other .other-turn {
  background: transparent;
  font-size: 13px;
  font-weight: 600;
}

/* 步骤条 */
.step-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: nowrap;
  gap: 3px;
  margin-bottom: 10px;
  padding: 8px 6px;
  border-radius: 8px;
  background: #f5f8fc;
  flex-shrink: 0;
}

.step {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 7px;
  border-radius: 999px;
  background: #f1f3f5;
  color: #90a4ae;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all .25s ease;
}

.step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #cfd8dc;
  color: #fff;
  font-size: 10px;
  flex-shrink: 0;
}

.step-label {
  white-space: nowrap;
}

.step.step-active {
  background: #fff3e0;
  color: #e65100;
  box-shadow: 0 0 0 2px rgba(255, 152, 0, .35);
}

.step.step-active .step-index {
  background: #fb8c00;
}

.step.step-done {
  background: #e8f5e9;
  color: #2e7d32;
}

.step.step-done .step-index {
  background: #43a047;
}

.step-arrow {
  color: #b0bec5;
  font-size: 12px;
}

/* 抽牌按钮：颜色名居中，剩余张数做成右上角标（省上下高度） */
.color-card-buttons {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.color-card-name {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 1px;
}

.color-card-button .color-card-count {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.92);
  color: #263238;
  font-size: 11px;
  font-weight: 800;
  line-height: 18px;
  text-align: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.22);
  opacity: 1;
}

.color-card-button:disabled .color-card-count {
  background: rgba(255, 255, 255, 0.6);
  color: #78909c;
}

/* 点数判定进行中 */
.btn.is-picking {
  background: #ff9800;
  box-shadow: 0 0 0 3px rgba(255, 152, 0, .35);
}

/* 尊重系统「减少动态效果」设置 */
/* 屏幕不足以容纳「1400 中间区 + 两侧栏」时退化为单列，线索与聊天栏顺次下移
   （1600px 以下中间区已窄于原始设计宽度，故在此断点收起两侧栏） */
@media (max-width: 1600px) {
  .game-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }

  .game-main {
    order: -1;
  }

  .side-rail {
    max-height: none;
  }

  /* 聊天栏退化成整宽后仍然要有固定上下长度：消息多了在卡片内滚动，
     否则整张卡片会被内容顶长、把页面越拉越高 */
  .rail-right {
    height: 520px;
    max-height: 520px;
  }

  .rail-card {
    min-height: 72px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .right-panel.is-my-turn,
  .turn-indicator.is-mine .pulse-dot {
    animation: none;
  }
}

/* ---------------------------------------------------------- 旁观者 */
.spectator-chip {
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4a4fa2;
  font-size: 12px;
  font-weight: 700;
}

.spectator-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 9px 28px;
  background: linear-gradient(90deg, #eef2ff, #f7f2ff);
  border-bottom: 1px solid #dfe3f5;
  color: #4a4fa2;
  font-size: 13px;
}
.sb-icon { font-size: 16px; }
.sb-text b { color: #2f3380; }
.sb-views { margin-left: auto; display: flex; align-items: center; gap: 6px; }
.sb-views-label { font-size: 12px; color: #7a7fb5; }
.sb-view-btn {
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid #c9cdf0;
  background: #fff;
  color: #4a4fa2;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.sb-view-btn:hover { border-color: #667eea; }
.sb-view-btn.active { background: #667eea; border-color: #667eea; color: #fff; font-weight: 700; }

.spectator-notice {
  position: fixed;
  left: 50%;
  top: 96px;
  transform: translateX(-50%);
  z-index: 70;
  padding: 9px 16px;
  border-radius: 10px;
  background: rgba(74, 79, 162, 0.95);
  color: #fff;
  font-size: 13px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
}

/* 旁观者：整个操作区禁用交互（服务端另有 Event_ActionRejected 兜底） */
.game-room.is-spectator .action-buttons {
  pointer-events: none;
  opacity: 0.45;
  filter: grayscale(0.3);
}

.spectator-lock {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px dashed #b9c0ea;
  border-radius: 10px;
  background: #f5f6ff;
  color: #4a4fa2;
}
.sl-icon { font-size: 18px; }
.sl-text { font-size: 13px; font-weight: 700; }
.sl-sub { font-size: 12px; color: #7a7fb5; }

/* 观战审批等待遮罩 */
.spectate-waiting {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(20, 22, 40, 0.55);
}
.sw-card {
  width: min(420px, 88vw);
  padding: 28px 26px;
  border-radius: 16px;
  background: #fff;
  text-align: center;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.28);
}
.sw-spinner {
  width: 34px;
  height: 34px;
  margin: 0 auto 14px;
  border: 3px solid #e3e6f7;
  border-top-color: #667eea;
  border-radius: 50%;
  animation: sw-spin 0.9s linear infinite;
}
@keyframes sw-spin {
  to { transform: rotate(360deg); }
}
.sw-title { margin: 0 0 6px; font-size: 16px; color: #2f3380; font-weight: 700; }
.sw-sub { margin: 0 0 18px; font-size: 13px; color: #7a7fb5; line-height: 1.6; }
.sw-cancel {
  padding: 9px 20px;
  border-radius: 8px;
  border: 1px solid #cfd4ef;
  background: #fff;
  color: #4a4fa2;
  font-size: 13px;
  cursor: pointer;
}
.sw-cancel:hover { border-color: #667eea; }
</style>
