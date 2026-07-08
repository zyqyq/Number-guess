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
          <td class="color-cell" :class="getColorClass(color)"></td>
          <td 
            v-for="num in 12" 
            :key="`${color}-${num}`"
            class="number-cell"
            :class="getCellClass(color, num)"
            :style="getCellStyle(color, num)"
            @click.left="handleLeftClick(color, num)"
            @contextmenu.prevent="handleRightClick(color, num)"
            @touchstart="handleTouchStart(color, num, $event)"
            @touchend="handleTouchEnd"
          >
            <span class="number-text">{{ num }}</span>
            <div class="point-dots">
              <span 
                v-for="dot in getPointCount(num)" 
                :key="dot" 
                class="point-dot"
              ></span>
            </div>
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
import { getColorClass, getColorValue, getLightColorValue, getPointFromNumber } from '@/utils/game';

const colors: Color[] = ['红', '蓝', '绿', '橙', '粉'];

// 手动搁置的数字（颜色 -> 数字集合）
const manuallyBlocked = ref<Map<Color, Set<number>>>(new Map());

// 已提交的猜测（用于高光显示）
const submittedGuesses = ref<Set<string>>(new Set());

const { getGrayReason } = useTableFilter();
const { revealedNumbers } = useDeduction();

/**
 * 获取点数（1-12）
 */
const getPointCount = (num: number): number => {
  return getPointFromNumber(num);
};

/**
 * 获取单元格的 CSS 类
 */
const getCellClass = (color: Color, num: number) => {
  const isManuallyBlocked = manuallyBlocked.value.get(color)?.has(num) || false;
  const reason = getGrayReason(num, isManuallyBlocked);
  const key = `${color}-${num}`;
  const isSubmitted = submittedGuesses.value.has(key);
  
  return {
    'revealed': reason === 'revealed',
    'blocked': reason === 'blocked' && !isSubmitted,
    'submitted': isSubmitted,
    'light-blocked': reason === 'blocked' && !isSubmitted
  };
};

/**
 * 获取单元格的内联样式（用于动态底色）
 */
const getCellStyle = (color: Color, num: number) => {
  const key = `${color}-${num}`;
  const isRevealed = revealedNumbers.value.has(key);
  const isManuallyBlocked = manuallyBlocked.value.get(color)?.has(num) || false;
  const isSubmitted = submittedGuesses.value.has(key);
  
  // 已出现的牌：灰显
  if (isRevealed) {
    return { backgroundColor: '#e0e0e0' };
  }
  
  // 提交后的高光
  if (isSubmitted) {
    return { 
      boxShadow: '0 0 8px rgba(76, 175, 80, 0.6)',
      borderColor: '#4CAF50'
    };
  }
  
  // 手动搁置：浅色
  if (isManuallyBlocked) {
    return { backgroundColor: getLightColorValue(color) };
  }
  
  // 默认：该数字牌的标准底色
  return { backgroundColor: getColorValue(color) };
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
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.number-cell:hover:not(.revealed) {
  transform: scale(1.05);
}

/* 数字文本 */
.number-text {
  font-size: 16px;
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

/* 已出现的数字 - 系统自动灰显 */
.number-cell.revealed {
  background-color: #e0e0e0 !important;
  cursor: not-allowed;
  opacity: 0.6;
}

.number-cell.revealed .number-text {
  color: #999;
}

.number-cell.revealed .point-dot {
  background-color: #999;
}

/* 用户手动搁置的数字 - 浅色背景 */
.number-cell.light-blocked {
  opacity: 0.7;
}

/* 提交后的高光效果 */
.number-cell.submitted {
  box-shadow: 0 0 8px rgba(76, 175, 80, 0.6);
  border: 2px solid #4CAF50;
}
</style>
