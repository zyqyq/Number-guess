<template>
  <div class="candidate-table">
    <table>
      <thead>
        <tr>
          <th>颜色</th>
          <th v-for="point in points" :key="point">{{ point }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="color in colors" :key="color">
          <td class="color-cell" :class="getColorClass(color)">{{ color }}</td>
          <td
            v-for="point in points"
            :key="`${color}-${point}`"
            class="number-cell"
            :class="getCellClass(color, point)"
            :style="getCellStyle(color, point)"
            @click.left="handleSelect(color, point)"
            @contextmenu.prevent="handleRightClick(color, point)"
            @touchstart="handleTouchStart(color, point, $event)"
            @touchend="handleTouchEnd(color, point, $event)"
            @touchcancel="handleTouchCancel"
          >
            <span class="number-text">{{ getCardNumber(color, point) }}</span>
            <span class="point-label">{{ point }}点</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { Color } from '@/types/game';
import { useDeduction, useTableFilter } from '@/composables/gameLogic';
import { getColorClass, getColorValue, getLightColorValue, getStartNumberForColor } from '@/utils/game';

const props = defineProps<{
  selectedNumbers?: Partial<Record<Color, number | null>>;
}>();

const emit = defineEmits<{
  selectNumber: [color: Color, num: number];
}>();

const colors: Color[] = ['红', '蓝', '绿', '橙', '粉'];
const points = Array.from({ length: 12 }, (_, index) => index + 1);

const manuallyBlocked = ref<Map<Color, Set<number>>>(new Map());
const submittedGuesses = ref<Set<string>>(new Set());

const { getGrayReason } = useTableFilter();
const { revealedNumbers } = useDeduction();

const getCardNumber = (color: Color, point: number): number => {
  return getStartNumberForColor(color, point);
};

const getSelectedNumber = (color: Color): number | null => {
  return props.selectedNumbers?.[color] ?? null;
};

const getCellClass = (color: Color, point: number) => {
  const number = getCardNumber(color, point);
  const key = `${color}-${number}`;
  const selectedNumber = getSelectedNumber(color);
  const isManualBlocked = manuallyBlocked.value.get(color)?.has(number) || false;
  const isSubmitted = submittedGuesses.value.has(key);
  const reason = getGrayReason(number, isManualBlocked);

  return {
    revealed: reason === 'revealed',
    blocked: reason === 'blocked' && !isSubmitted,
    submitted: isSubmitted,
    selected: selectedNumber === number,
    'auto-shelved': selectedNumber !== null && selectedNumber !== number,
    'manual-shelved': isManualBlocked,
  };
};

const getCellStyle = (color: Color, point: number) => {
  const number = getCardNumber(color, point);
  const key = `${color}-${number}`;
  const selectedNumber = getSelectedNumber(color);
  const isRevealed = revealedNumbers.value.has(key);
  const isManualBlocked = manuallyBlocked.value.get(color)?.has(number) || false;
  const isSubmitted = submittedGuesses.value.has(key);

  if (isRevealed) {
    return { backgroundColor: '#e7e7e7' };
  }

  if (isSubmitted) {
    return {
      boxShadow: '0 0 0 2px rgba(76, 175, 80, 0.4) inset, 0 0 14px rgba(76, 175, 80, 0.28)',
      borderColor: '#4CAF50'
    };
  }

  if (selectedNumber === number) {
    return {
      backgroundColor: getColorValue(color),
      boxShadow: '0 0 0 3px rgba(255, 255, 255, 0.75) inset, 0 0 0 2px rgba(255, 255, 255, 0.8), 0 0 14px rgba(255, 255, 255, 0.45)'
    };
  }

  if (selectedNumber !== null || isManualBlocked) {
    return { backgroundColor: getLightColorValue(color) };
  }

  return { backgroundColor: getColorValue(color) };
};

const handleSelect = (color: Color, point: number) => {
  const number = getCardNumber(color, point);
  if (revealedNumbers.value.has(`${color}-${number}`)) {
    return;
  }
  emit('selectNumber', color, number);
};

const handleRightClick = (color: Color, point: number) => {
  const number = getCardNumber(color, point);
  if (!manuallyBlocked.value.has(color)) {
    manuallyBlocked.value.set(color, new Set());
  }
  const blockedSet = manuallyBlocked.value.get(color)!;
  if (blockedSet.has(number)) {
    blockedSet.delete(number);
  } else {
    blockedSet.add(number);
  }
};

type TouchPoint = {
  color: Color;
  point: number;
  startX: number;
  startY: number;
};

const touchPoint = ref<TouchPoint | null>(null);

const handleTouchStart = (color: Color, point: number, event: TouchEvent) => {
  const touch = event.touches[0];
  if (!touch) return;
  touchPoint.value = {
    color,
    point,
    startX: touch.clientX,
    startY: touch.clientY,
  };
};

const handleTouchEnd = (color: Color, point: number, event: TouchEvent) => {
  const start = touchPoint.value;
  const touch = event.changedTouches[0];
  touchPoint.value = null;
  if (!start || !touch) return;

  const deltaX = touch.clientX - start.startX;
  const deltaY = touch.clientY - start.startY;
  if (Math.abs(deltaX) < 30 && deltaY < -30) {
    handleSelect(color, point);
  }
};

const handleTouchCancel = () => {
  touchPoint.value = null;
};
</script>

<style scoped>
.candidate-table {
  overflow-x: auto;
}

table {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  min-width: 860px;
  font-size: 14px;
}

th,
td {
  border: 1px solid rgba(255, 255, 255, 0.14);
  padding: 10px 8px;
  text-align: center;
  min-width: 56px;
}

th {
  background: #f4f4f4;
  font-weight: 700;
  color: #333;
}

.color-cell {
  width: 72px;
  min-width: 72px;
  font-weight: 700;
  color: white;
}

.color-red {
  background-color: #ef5350;
}

.color-blue {
  background-color: #42a5f5;
}

.color-green {
  background-color: #66bb6a;
}

.color-orange {
  background-color: #ffa726;
}

.color-pink {
  background-color: #ec407a;
}

.number-cell {
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
  color: white;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  user-select: none;
}

.number-cell:hover:not(.revealed) {
  transform: translateY(-1px);
  filter: brightness(1.03);
}

.number-text {
  font-size: 18px;
  font-weight: 800;
  line-height: 1;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
}

.point-label {
  font-size: 12px;
  opacity: 0.9;
}

.number-cell.revealed {
  background-color: #e7e7e7 !important;
  color: #999;
  cursor: not-allowed;
  opacity: 0.7;
}

.number-cell.revealed .number-text,
.number-cell.revealed .point-label {
  color: #999;
  text-shadow: none;
}

.number-cell.selected {
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.85) inset, 0 0 14px rgba(255, 255, 255, 0.45);
}

.number-cell.auto-shelved,
.number-cell.manual-shelved {
  opacity: 0.72;
}

.number-cell.submitted {
  box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.6) inset, 0 0 14px rgba(76, 175, 80, 0.24);
  border-color: #4CAF50;
}
</style>
