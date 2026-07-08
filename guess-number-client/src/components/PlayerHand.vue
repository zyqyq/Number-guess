<template>
  <div class="player-hand">
    <h3>{{ player.playerName }} {{ isMe ? '(你)' : '' }}</h3>
    <div class="cards">
      <div 
        v-for="card in displayCards" 
        :key="card.id"
        class="card"
        :class="[getColorClass(card.color), { 'hidden-number': hideNumbers }]"
      >
        <div class="card-content">
          <span v-if="!hideNumbers" class="card-number">{{ card.number }}</span>
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

const props = defineProps<{
  player: Player;
  isMe?: boolean;
}>();

// 如果是自己，隐藏数字；否则显示完整数字
const hideNumbers = props.isMe;

// 对于自己的手牌，数字已经由 store 的 myHand 计算属性处理为 null
const displayCards = props.player.hand;

// 获取颜色对应的 CSS 类
const getColorClass = (color: Color) => {
  const colorMap: Record<Color, string> = {
    '红': 'card-red',
    '蓝': 'card-blue',
    '绿': 'card-green',
    '橙': 'card-orange',
    '粉': 'card-pink'
  };
  return colorMap[color];
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

.player-hand h3 {
  margin: 0 0 12px 0;
  font-size: 16px;
  color: #333;
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

/* 颜色底色 */
.card-red {
  background-color: #ef5350;
}

.card-blue {
  background-color: #42a5f5;
}

.card-green {
  background-color: #66bb6a;
}

.card-orange {
  background-color: #ffa726;
}

.card-pink {
  background-color: #ec407a;
}

.card.hidden-number {
  /* 自己的手牌：只显示颜色底色，不显示数字 */
}

.card-content {
  text-align: center;
}

.card-number {
  display: block;
  font-size: 24px;
  font-weight: bold;
  color: white;
  text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.3);
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
