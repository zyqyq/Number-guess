<template>
  <div class="player-hand">
      <div class="my-hand-grid">
        <div
          v-for="card in displayCards"
          :key="card.id"
          class="card card-base my-card"
          :class="[getColorClass(card.color), {
            selected: hasSelection(card.color),
            'point-judge-target': pointJudgeMode
          }]"
          :style="{ backgroundColor: getColorValue(card.color) }"
          @click="pointJudgeMode && handlePointJudgeClick(card.color)"
        >
          <div class="card-content my-card-content">
            <span class="my-card-color">{{ card.color }}</span>
            <input
              class="my-card-input"
              type="number"
              min="1"
              max="60"
              inputmode="numeric"
              v-model="draftValues[card.color]"
              @keydown.enter.prevent="commitCard(card.color)"
              @blur="commitCard(card.color)"
              @click.stop
            />
          </div>
        </div>
      </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue';
import type { Player, Color } from '@/types/game';
import { getColorClass, getColorValue, getPointFromNumber } from '@/utils/game';

const props = defineProps<{
  player: Player;
  isMe?: boolean;
  isActive?: boolean;
  selectedNumbers?: Partial<Record<Color, number | null>>;
  pointJudgeMode?: boolean;
}>();

const emit = defineEmits<{
  commitNumber: [color: Color, number: number];
  pointJudgeSelect: [color: Color];
}>();

const displayCards = computed(() => 
  [...props.player.hand].sort((a, b) => a.number - b.number)
);
const isActiveTurn = computed(() => !!props.isActive);

const draftValues = reactive<Record<Color, string>>({
  红: '',
  蓝: '',
  绿: '',
  橙: '',
  粉: ''
});

const hasSelection = (color: Color) => {
  return props.selectedNumbers?.[color] != null;
};

watch(
  () => props.selectedNumbers,
  () => {
    for (const card of displayCards.value) {
      const selected = props.selectedNumbers?.[card.color];
      if (selected != null) {
        draftValues[card.color] = String(selected);
      }
    }
  },
  { deep: true, immediate: true }
);

const commitCard = (color: Color) => {
  const value = Number(draftValues[color]);
  if (!Number.isInteger(value) || value < 1 || value > 60) {
    return;
  }
  emit('commitNumber', color, value);
};

const getPointCount = (num: number): number => {
  return getPointFromNumber(num);
};

const handlePointJudgeClick = (color: Color) => {
  emit('pointJudgeSelect', color);
};
</script>

<style scoped>
.player-hand {
  margin: 0px 0;
  padding: 0px;
  border: 1px solid #ffffff;
  border-radius: 12px;
  background: #ffffff;
}

.eliminated-badge {
  font-size: 12px;
  color: #999;
  background: #e0e0e0;
  padding: 2px 8px;
  border-radius: 999px;
}

.my-hand-grid {
  display: flex;
  gap: 12px;
  justify-content: center;
  align-items: center;
}

/* 我的手牌与公共牌同尺寸 */
.my-hand-grid .card {
  width: 80px;
  height: 120px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.card:hover {
  transform: translateY(-2px);
}

.card.selected {
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9) inset, 0 0 16px rgba(255, 255, 255, 0.45);
}

.card.point-judge-target {
  cursor: pointer;
  animation: pulse-point-judge 1s ease-in-out infinite;
}

@keyframes pulse-point-judge {
  0%, 100% {
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.7) inset, 0 0 0 3px rgba(255, 235, 59, 0.8);
    transform: scale(1);
  }
  50% {
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.7) inset, 0 0 0 5px rgba(255, 235, 59, 1), 0 0 20px rgba(255, 235, 59, 0.4);
    transform: scale(1.05);
  }
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
  font-weight: 800;
  color: white;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
}

.point-dots {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 2px;
  max-width: 44px;
}

.point-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.9);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.my-card-content {
  width: 100%;
  padding: 10px 8px;
}

.my-card-color {
  font-size: 13px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.95);
}

.my-card-input {
  width: 100%;
  margin-top: 6px;
  border: none;
  outline: none;
  background: rgba(255, 255, 255, 0.18);
  color: white;
  text-align: center;
  font-size: 24px;
  font-weight: 800;
  border-radius: 8px;
  padding: 6px 4px;
  box-sizing: border-box;
  -moz-appearance: textfield;
  appearance: textfield;
}

.my-card-input::-webkit-inner-spin-button,
.my-card-input::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.my-card-input::placeholder {
  color: rgba(255, 255, 255, 0.75);
}

.clues {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px dashed #ccc;
}

.clues h4 {
  margin: 0 0 8px;
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
