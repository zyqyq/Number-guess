<template>
  <div class="public-cards">
    <transition-group name="draw" tag="div" class="public-cards-inner">
      <div 
        v-for="card in publicCards" 
        :key="card.id"
        class="public-card card-base"
      :class="[getColorClass(card.color), { 
        'selected': card.isSelected,
        'clickable': clickable 
      }]"
      :style="{ backgroundColor: getColorValue(card.color) }"
      @click="handleCardClick(card)"
    >
      <div class="card-content">
        <span class="card-number">{{ card.number }}</span>
        <div class="point-dots">
          <span 
            v-for="dot in getPointCount(card.number)" 
            :key="dot" 
            class="point-dot"
          ></span>
        </div>
      </div>
      </div>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import type { Card, Color } from '@/types/game';
import { getColorClass, getColorValue, getPointFromNumber } from '@/utils/game';

const props = defineProps<{
  publicCards: Card[];
  clickable?: boolean;
}>();

const emit = defineEmits<{
  (e: 'select', card: Card): void;
}>();

/**
 * 获取点数（1-12）
 */
const getPointCount = (num: number): number => {
  return getPointFromNumber(num);
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
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.card-number {
  display: block;
  font-size: 32px;
  font-weight: bold;
  color: white;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
}

/* 点数图标容器 */
.point-dots {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 3px;
}

/* 单个点数图标（小圆点） */
.point-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.9);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

/* 抽牌入场动画 */
.draw-enter-from {
  transform: translateY(-30px) scale(0.9);
  opacity: 0;
}
.draw-enter-active {
  transition: all 360ms cubic-bezier(.2,.8,.2,1);
}
.draw-enter-to {
  transform: translateY(0) scale(1);
  opacity: 1;
}
</style>
