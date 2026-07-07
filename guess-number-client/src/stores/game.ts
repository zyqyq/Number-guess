import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { GameState, Player, Card, Color } from '@/types/game';

export const useGameStore = defineStore('game', () => {
  // 当前玩家 ID（用于前端过滤自己的手牌）
  const myPlayerId = ref<string | null>(null);
  
  // 完整游戏状态（从后端接收的全量数据）
  const gameState = ref<GameState | null>(null);

  // 计算属性：当前玩家对象
  const currentPlayer = computed(() => {
    if (!gameState.value || !myPlayerId.value) return null;
    return gameState.value.players[myPlayerId.value] || null;
  });

  // 计算属性：其他玩家列表
  const otherPlayers = computed(() => {
    if (!gameState.value || !myPlayerId.value) return [];
    return Object.values(gameState.value.players).filter(p => p.playerId !== myPlayerId.value);
  });

  // 计算属性：我的手牌（数字已隐藏）
  const myHand = computed(() => {
    if (!currentPlayer.value) return [];
    // 前端过滤：将自己的手牌数字隐藏为 null
    return currentPlayer.value.hand.map(card => ({
      ...card,
      number: null as unknown as number // 显示为 ?
    }));
  });

  // 计算属性：是否是当前回合
  const isMyTurn = computed(() => {
    return gameState.value?.currentTurnPlayerId === myPlayerId.value;
  });

  // 计算属性：游戏是否结束
  const isGameOver = computed(() => {
    return gameState.value?.gamePhase === 'GAME_OVER';
  });

  // 设置当前玩家 ID
  const setMyPlayerId = (playerId: string) => {
    myPlayerId.value = playerId;
  };

  // 更新游戏状态（从 WebSocket 接收）
  const updateGameState = (state: GameState) => {
    gameState.value = state;
  };

  return {
    myPlayerId,
    gameState,
    currentPlayer,
    otherPlayers,
    myHand,
    isMyTurn,
    isGameOver,
    setMyPlayerId,
    updateGameState
  };
});
