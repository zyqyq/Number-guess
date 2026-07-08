<template>
  <div class="candidate-table">
    <table>
      <thead>
        <tr>
          <th>颜色</th>
          <th v-for="num in 12" :key="num">{{ num }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="color in colors" :key="color">
          <td class="color-cell" :class="getColorClass(color)">{{ color }}</td>
          <td 
            v-for="num in 12" 
            :key="`${color}-${num}`"
            class="number-cell"
            :class="getCellClass(color, num)"
            @click.left="handleLeftClick(color, num)"
            @contextmenu.prevent="handleRightClick(color, num)"
            @touchstart="handleTouchStart(color, num, $event)"
            @touchend="handleTouchEnd"
          >
            {{ num }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { Color } from '@/types/game';
import { useTableFilter, useDeduction } from '@/composables/gameLogic';

const colors: Color[] = ['红', '蓝', '绿', '橙', '粉'];

// 手动搁置的数字（颜色 -> 数字集合）
const manuallyBlocked = ref<Map<Color, Set<number>>>(new Map());

const { getGrayReason } = useTableFilter();
const { revealedNumbers } = useDeduction();

// 获取颜色对应的 CSS 类
const getColorClass = (color: Color) => {
  const colorMap: Record<Color, string> = {
    '红': 'color-red',
    '蓝': 'color-blue',
    '绿': 'color-green',
    '橙': 'color-orange',
    '粉': 'color-pink'
  };
  return colorMap[color];
};

/**
 * 获取单元格的 CSS 类
 */
const getCellClass = (color: Color, num: number) => {
  const isManuallyBlocked = manuallyBlocked.value.get(color)?.has(num) || false;
  const reason = getGrayReason(num, isManuallyBlocked);
  return {
    'revealed': reason === 'revealed',
    'blocked': reason === 'blocked'
  };
};

/**
 * 左键点击：提交猜测（触发事件）
 */
const emit = defineEmits<{
  selectNumber: [color: Color, num: number];
}>();

const handleLeftClick = (color: Color, num: number) => {
  // 已出现的数字不能选择
  if (revealedNumbers.value.has(`${color}-${num}`)) {
    return;
  }
  emit('selectNumber', color, num);
};

/**
 * 右键点击：搁置/取消搁置
 */
const handleRightClick = (color: Color, num: number) => {
  if (!manuallyBlocked.value.has(color)) {
    manuallyBlocked.value.set(color, new Set());
  }
  const blockedSet = manuallyBlocked.value.get(color)!;
  
  if (blockedSet.has(num)) {
    blockedSet.delete(num);
  } else {
    blockedSet.add(num);
  }
};

// 触摸支持：长按搁置
let longPressTimer: number | null = null;
const handleTouchStart = (color: Color, num: number, event: TouchEvent) => {
  longPressTimer = window.setTimeout(() => {
    handleRightClick(color, num);
    // 触感反馈
    if (navigator.vibrate) {
      navigator.vibrate(50);
    }
    longPressTimer = null;
  }, 300);
};

const handleTouchEnd = () => {
  if (longPressTimer) {
    clearTimeout(longPressTimer);
    longPressTimer = null;
  }
};
</script>

<style scoped>
.candidate-table {
  overflow-x: auto;
}

table {
  border-collapse: collapse;
  width: 100%;
  font-size: 14px;
}

th, td {
  border: 1px solid #ddd;
  padding: 8px;
  text-align: center;
  min-width: 30px;
}

th {
  background-color: #f5f5f5;
  font-weight: bold;
}

.color-cell {
  font-weight: bold;
  min-width: 50px;
}

/* 颜色底色 */
.color-red {
  background-color: #ef5350;
  color: white;
}

.color-blue {
  background-color: #42a5f5;
  color: white;
}

.color-green {
  background-color: #66bb6a;
  color: white;
}

.color-orange {
  background-color: #ffa726;
  color: white;
}

.color-pink {
  background-color: #ec407a;
  color: white;
}

.number-cell {
  cursor: pointer;
  transition: all 0.2s ease;
}

.number-cell:hover {
  background-color: #e3f2fd;
}

/* 已出现的数字 - 系统自动灰显 */
.number-cell.revealed {
  background-color: #e0e0e0;
  color: #999;
  cursor: not-allowed;
}

/* 用户手动搁置的数字 */
.number-cell.blocked {
  background-color: #ffcdd2;
  color: #c62828;
}
</style>
