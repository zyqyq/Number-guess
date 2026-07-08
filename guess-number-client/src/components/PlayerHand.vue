<template>
  <div class="player-hand">
    <div class="player-header">
      <span class="player-label" :class="{ 'active-turn': isActiveTurn }">
        {{ isMe ? '你' : player.playerName }}
        <span v-if="isActiveTurn" class="turn-indicator">⚡</span>
      </span>
      <span v-if="!player.isAlive" class="eliminated-badge">💀 已出局</span>
    </div>
    <div class="cards">
      <div 
        v-for="card in displayCards" 
        :key="card.id"
        class="card card-base"
        :class="[getColorClass(card.color), { 'hidden-number': hideNumbers }]"
        :style="{ backgroundColor: getColorValue(card.color) }"
      >
        <div class="card-content">
          <span v-if="!hideNumbers" class="card-number">{{ card.number }}</span>
          <div v-if="!hideNumbers" class="point-dots">
            <span 
              v-for="dot in getPointCount(card.number)" 
              :key="dot" 
              class="point-dot"
            ></span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 线索区域 -->
    <div class="clues" v-if="player.clues && player.clues.length > 0">
      <h4>线索:</h4>
      <div v-for="clue in player.clues" :key="clue.id" class="clue-item">
        <span v-if="clue.type === 'position'">
          公牌 {{ clue.publicCardNumber }} 位于位置 {{ clue.result }}
        </span>
        <span v-else-if="clue.type === 'point'">
          公牌 {{ clue.publicCardNumber }} 与 {{ clue.targetColor }} 点数{{ clue.result ? '相同' : '不同' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Player, Card, Color } from '@/types/game';
import { getColorClass, getColorValue, getPointFromNumber } from '@/utils/game';

const props = defineProps<{
  player: Player;
  isMe?: boolean;
}>();

// 如果是自己，隐藏数字；否则显示完整数字
const hideNumbers = props.isMe;

// 对于自己的手牌，数字已经由 store 的 myHand 计算属性处理为 null
const displayCards = props.player.hand;

// 判断是否是当前操作玩家（通过父组件传入或从 gameStore 获取）
const isActiveTurn = false; // TODO: 从 gameStore 获取当前回合玩家 ID

/**
 * 获取点数（1-12）
 */
const getPointCount = (num: number): number => {
  if (hideNumbers || num == null) return 0;
  return getPointFromNumber(num);
};
</script>

<style scoped>
.player-hand {
  margin: 16px 0;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #fafafa;
}

.player-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.player-label {
  background: rgba(0, 0, 0, 0.7);
  color: white;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: bold;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.player-label.active-turn {
  animation: breathe 1.5s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% {
    box-shadow: 0 0 5px rgba(76, 175, 80, 0.5);
  }
  50% {
    box-shadow: 0 0 15px rgba(76, 175, 80, 0.8);
  }
}

.turn-indicator {
  font-size: 12px;
  animation: flash 1s ease-in-out infinite;
}

@keyframes flash {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.eliminated-badge {
  font-size: 12px;
  color: #999;
  background: #e0e0e0;
  padding: 2px 8px;
  border-radius: 4px;
}

.cards {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.card {
  width: 60px;
  height: 90px;
  border: 2px solid #ccc;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.card.hidden-number .card-content {
  /* 自己的手牌：只显示颜色底色，不显示数字和点数 */
}

.card-content {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.card-number {
  display: block;
  font-size: 24px;
  font-weight: bold;
  color: white;
  text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.3);
}

/* 点数图标容器 */
.point-dots {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 2px;
}

/* 单个点数图标（小圆点） */
.point-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.9);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.clues {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px dashed #ccc;
}

.clues h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #666;
}

.clue-item {
  font-size: 12px;
  color: #555;
  margin: 4px 0;
  padding: 4px 8px;
  background: #f0f0f0;
  border-radius: 4px;
}
</style>
