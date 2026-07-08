<template>
  <div class="public-cards">
    <div 
      v-for="card in publicCards" 
      :key="card.id"
      class="public-card"
      :class="[getColorClass(card.color), { 
        'selected': card.isSelected,
        'clickable': clickable 
      }]"
      @click="handleCardClick(card)"
    >
      <div class="card-content">
        <span class="card-number">{{ card.number }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Card, Color } from '@/types/game';

const props = defineProps<{
  publicCards: Card[];
  clickable?: boolean;
}>();

const emit = defineEmits<{
  (e: 'select', card: Card): void;
}>();

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

const handleCardClick = (card: Card) => {
  if (props.clickable) {
    emit('select', card);
  }
};
</script>

<style scoped>
.public-cards {
  display: flex;
  gap: 12px;
  padding: 16px;
  justify-content: center;
}

.public-card {
  width: 80px;
  height: 120px;
  border: 2px solid #ccc;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: default;
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

.public-card.clickable {
  cursor: pointer;
}

.public-card.clickable:hover {
  transform: translateY(-5px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.public-card.selected {
  border-color: #4CAF50;
  box-shadow: 0 0 15px rgba(76, 175, 80, 0.5);
  transform: translateY(-5px);
}

.card-content {
  text-align: center;
}

.card-number {
  display: block;
  font-size: 32px;
  font-weight: bold;
  color: white;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
}
</style>
