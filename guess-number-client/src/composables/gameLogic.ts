import { computed } from 'vue';
import { useGameStore } from '@/stores/game';
import type { Card, Color } from '@/types/game';

/**
 * 获取自己的手牌（数字已隐藏）
 * 返回的牌中 number 字段为 null，用于渲染时显示 "?"
 */
export function useMyHand() {
  const gameStore = useGameStore();
  
  // 直接使用 store 中的 myHand 计算属性
  return {
    myHand: gameStore.myHand,
    hasHand: computed(() => gameStore.myHand.length > 0)
  };
}

/**
 * 获取其他玩家的手牌（完整数字可见）
 */
export function useOtherPlayers() {
  const gameStore = useGameStore();
  
  return {
    otherPlayers: gameStore.otherPlayers,
    playerCount: computed(() => gameStore.otherPlayers.length)
  };
}

/**
 * 根据线索推导候选范围
 */
export function useDeduction() {
  const gameStore = useGameStore();
  
  /**
   * 获取某颜色手牌的候选数字范围
   * @param color 手牌颜色
   * @returns 可能的数字列表
   */
  const getCandidatesForColor = (color: Color): number[] => {
    const player = gameStore.currentPlayer;
    if (!player) return [];
    
    const card = player.hand.find(c => c.color === color);
    if (!card) return [];
    
    // 如果已有线索，根据线索过滤
    const clues = player.clues.filter(clue => {
      if (clue.type === 'point') {
        return clue.targetColor === color;
      }
      return false;
    });
    
    // 简化版：暂时返回所有可能数字（1-12 点）
    // TODO: 实现完整的线索推导逻辑
    const allNumbers = Array.from({ length: 12 }, (_, i) => i + 1);
    
    return allNumbers;
  };
  
  /**
   * 检查某个数字是否已被排除（出现在公牌或弃牌中）
   * @param number 数字
   * @returns 是否已出现
   */
  const isNumberRevealed = (number: number): boolean => {
    const state = gameStore.gameState;
    if (!state) return false;
    
    // 检查公牌区
    const publicNumbers = state.publicCards.map(c => c.number);
    if (publicNumbers.includes(number)) return true;
    
    // TODO: 检查弃牌堆（需要后端在快照中包含弃牌信息）
    
    return false;
  };

  /**
   * 获取所有已出现的数字集合（用于备选区灰显）
   * 返回格式："颜色 - 数字" 的集合
   * 标灰条件：所有当前玩家可见的牌，包括：
   *   - 公牌区当前显示的牌
   *   - 曾出现在公牌区并被判定弃置的牌（usedCardNumbers）
   *   - 其他玩家的手牌数字（已公开）
   */
  const revealedNumbers = computed(() => {
    const state = gameStore.gameState;
    if (!state) return new Set<string>();
    
    const revealed = new Set<string>();
    
    // 公牌区的数字
    for (const card of state.publicCards) {
      revealed.add(`${card.color}-${card.number}`);
    }
    
    // 曾出现在公牌区并被判定弃置的牌（usedCardNumbers）
    if (state.usedCardNumbers) {
      for (const item of state.usedCardNumbers) {
        revealed.add(`${item.color}-${item.number}`);
      }
    }
    
    // 其他玩家的手牌数字（当前操作玩家可见，备选区标灰）
    const currentPlayerId = gameStore.myPlayerId;
    for (const playerId in state.players) {
      if (playerId === currentPlayerId) continue; // 跳过自己的牌
      const player = state.players[playerId];
      if (player.hand) {
        for (const card of player.hand) {
          revealed.add(`${card.color}-${card.number}`);
        }
      }
    }
    
    return revealed;
  });
  
  return {
    getCandidatesForColor,
    isNumberRevealed,
    revealedNumbers
  };
}

/**
 * 备选区表格辅助函数
 */
export function useTableFilter() {
  const deduction = useDeduction();
  
  /**
   * 判断某个数字格子是否应该灰显
   * @param number 数字
   * @param isManuallyBlocked 用户是否手动搁置
   * @returns 灰显原因：'revealed' | 'blocked' | null
   */
  const getGrayReason = (number: number, isManuallyBlocked: boolean): 'revealed' | 'blocked' | null => {
    if (deduction.isNumberRevealed(number)) {
      return 'revealed';
    }
    if (isManuallyBlocked) {
      return 'blocked';
    }
    return null;
  };
  
  return {
    getGrayReason
  };
}
