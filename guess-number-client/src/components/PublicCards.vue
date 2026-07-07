<template>
  <div class="public-cards">
    <div 
      v-for="card in publicCards" 
      :key="card.id"
      class="public-card"
      :class="{ 
        'selected': card.isSelected,
        'clickable': clickable 
      }"
      @click="handleCardClick(card)"
    >
      <div class="card-content">
        <span class="card-color">{{ card.color }}</span>
        <span class="card-number">{{ card.number }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Card } from '@/types/game';

const props = defineProps<{
  publicCards: Card[];
  clickable?: boolean;
}>();

const emit = defineEmits<{
  (e: 'select', card: Card): void;
}>();

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
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: default;
  transition: all 0.2s ease;
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

.card-color {
  display: block;
  font-size: 14px;
  font-weight: bold;
  margin-bottom: 4px;
}

.card-number {
  display: block;
  font-size: 24px;
  font-weight: bold;
}
</style>
