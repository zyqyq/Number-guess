<template>
  <div class="player-hand">
    <div v-if="!isMe" class="player-row">
      <div class="player-header">
        <span class="player-label" :class="{ 'active-turn': isActiveTurn }">
          {{ player.playerName }}
          <span v-if="isActiveTurn" class="turn-indicator">⚡</span>
        </span>
        <span v-if="!player.isAlive" class="eliminated-badge">💀 已出局</span>
      </div>

      <div class="cards other-cards">
        <div
          v-for="card in displayCards"
          :key="card.id"
          class="card card-base"
          :class="getColorClass(card.color)"
          :style="{ backgroundColor: getColorValue(card.color) }"
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
      </div>
    </div>

    <div v-else class="my-hand-grid">
      <div
        v-for="card in displayCards"
        :key="card.id"
        class="card card-base my-card"
        :class="[getColorClass(card.color), { selected: hasSelection(card.color) }]"
        :style="{ backgroundColor: getColorValue(card.color) }"
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
          />
        </div>
      </div>
    </div>

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
import { computed, reactive, watch } from 'vue';
import type { Player, Color } from '@/types/game';
import { getColorClass, getColorValue, getPointFromNumber } from '@/utils/game';

const props = defineProps<{
  player: Player;
  isMe?: boolean;
  isActive?: boolean;
  selectedNumbers?: Partial<Record<Color, number | null>>;
}>();

const emit = defineEmits<{
  commitNumber: [color: Color, number: number];
}>();

const displayCards = computed(() => props.player.hand);
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
</script>

<style scoped>
.player-hand {
  margin: 16px 0;
  padding: 16px;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  background: #fafafa;
}

.player-row {
  display: flex;
  align-items: center;
  gap: 22px;
  justify-content: center;
  flex-wrap: wrap;
}

.player-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.player-label {
  background: rgba(0, 0, 0, 0.72);
  color: white;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.player-label.active-turn {
  animation: breathe 1.5s ease-in-out infinite;
}

@keyframes breathe {
  0%,
  100% {
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
  0%,
  100% {
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
  border-radius: 999px;
}

.cards,
.my-hand-grid {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
}

.card {
  width: 66px;
  height: 96px;
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
