<template>
  <div class="candidate-table">
    <table>
      <tbody>
        <tr v-for="(color, rowIdx) in colors" :key="color">
          <td
            v-for="col in 12"
            :key="`${color}-${col}`"
            class="number-cell"
            :class="cellClass(cardNumber(color, col))"
            :style="cellStyle(color, cardNumber(color, col))"
            @click.left="handleSelect(color, cardNumber(color, col))"
            @contextmenu.prevent="handleRightClick(color, cardNumber(color, col))"
          >
            <span class="cell-number">{{ cardNumber(color, col) }}</span>
            <div class="cell-points">
              <span
                v-for="d in getPointFromNumber(cardNumber(color, col))"
                :key="d"
                class="cell-dot"
              ></span>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { Color } from '@/types/game';
import { getColorValue, getLightColorValue, getPointFromNumber } from '@/utils/game';

const props = defineProps<{
  selectedNumbers?: Partial<Record<Color, number | null>>;
}>();

const emit = defineEmits<{
  selectNumber: [color: Color, num: number];
}>();

const colors: Color[] = ['红', '蓝', '绿', '橙', '粉'];
const manuallyBlocked = ref<Set<string>>(new Set());

/** 颜色行 R 的第 C 列 (1-based) 对应的数字： (R+1) + (C-1)*5 */
const cardNumber = (color: Color, col: number): number => {
  const idx = colors.indexOf(color);
  return (idx + 1) + (col - 1) * 5;
};

const keyOf = (color: Color, num: number) => `${color}-${num}`;

const isSelected = (color: Color, num: number) => props.selectedNumbers?.[color] === num;

const isBlocked = (color: Color, num: number) => manuallyBlocked.value.has(keyOf(color, num));

const cellClass = (num: number) => ({
  revealed: false,
});

const cellStyle = (color: Color, num: number) => {
  const key = keyOf(color, num);
  const sel = isSelected(color, num);
  const blk = isBlocked(color, num);
  if (sel) {
    return {
      backgroundColor: getColorValue(color),
      boxShadow: '0 0 0 2px rgba(255,255,255,0.75) inset, 0 0 14px rgba(255,255,255,0.4)',
      color: '#fff',
    };
  }
  if (blk) {
    return { backgroundColor: getLightColorValue(color), opacity: 0.65 };
  }
  return { backgroundColor: getColorValue(color), color: '#fff' };
};

const handleSelect = (color: Color, num: number) => {
  emit('selectNumber', color, num);
};

const handleRightClick = (color: Color, num: number) => {
  const key = keyOf(color, num);
  if (manuallyBlocked.value.has(key)) {
    manuallyBlocked.value.delete(key);
  } else {
    manuallyBlocked.value.add(key);
  }
  // trigger reactivity
  manuallyBlocked.value = new Set(manuallyBlocked.value);
};
</script>

<style scoped>
.candidate-table {
  overflow-x: auto;
}

table {
  border-collapse: collapse;
  width: 100%;
  table-layout: fixed;
  font-size: 13px;
}

th,
td {
  border: 1px solid rgba(255, 255, 255, 0.18);
  padding: 6px 2px;
  text-align: center;
  width: calc(100% / 12);
}

.col-header {
  background: #f4f4f4;
  font-weight: 700;
  color: #333;
  min-width: 54px;
  font-size: 13px;
  border: 1px solid #ddd;
}

.color-cell {
  font-weight: 700;
  color: white;
  text-align: center;
  min-width: 52px;
  padding: 8px 4px;
  font-size: 14px;
}

.number-cell {
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  user-select: none;
  vertical-align: middle;
}

.number-cell:hover {
  transform: translateY(-1px);
  filter: brightness(1.04);
}

.cell-number {
  display: block;
  font-weight: 800;
  font-size: 16px;
  line-height: 1.1;
  text-shadow: 0 1px 2px rgba(0,0,0,0.2);
}

.cell-points {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 2px;
  margin-top: 3px;
}

.cell-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.85);
  box-shadow: 0 1px 1px rgba(0,0,0,0.15);
}

.number-cell.revealed {
  background-color: #e7e7e7 !important;
  color: #999;
  cursor: not-allowed;
  opacity: 0.7;
}
</style>
