// 游戏工具函数

import type { Color } from '@/types/game';

/**
 * 根据数字计算点数 (1-3)
 * 点数按列循环分布：第1列1点、第2列2点、第3列3点、第4列1点、第5列2点……
 * 即只有 1、2、3 三种点数可能
 * 公式：((number - 1) / 5 的列号 % 3) + 1
 */
export function getPointFromNumber(number: number): number {
  return (Math.floor((number - 1) / 5) % 3) + 1;
}

/**
 * 根据点数和颜色获取该颜色的起始数字
 * 红：1, 6, 11, 16... (每 5 个循环)
 * 蓝：2, 7, 12, 17...
 * 绿：3, 8, 13, 18...
 * 橙：4, 9, 14, 19...
 * 粉：5, 10, 15, 20...
 */
export function getStartNumberForColor(color: Color, point: number): number {
  const colorOffset: Record<Color, number> = {
    '红': 1,
    '蓝': 2,
    '绿': 3,
    '橙': 4,
    '粉': 5
  };
  const baseOffset = colorOffset[color];
  // 每个点数的间隔是 5（因为有 5 种颜色）
  return baseOffset + (point - 1) * 5;
}

/**
 * 根据点数反推可能的数字范围
 * 点数 1: 1-5
 * 点数 2: 6-10
 * ...
 * 点数 12: 56-60
 */
export function getNumbersForPoint(point: number): number[] {
  if (point < 1 || point > 12) return [];
  const start = (point - 1) * 5 + 1;
  const end = point * 5;
  return Array.from({ length: 5 }, (_, i) => start + i);
}

/**
 * 获取颜色对应的 CSS 类名
 */
export function getColorClass(color: Color): string {
  const colorMap: Record<Color, string> = {
    '红': 'color-red',
    '蓝': 'color-blue',
    '绿': 'color-green',
    '橙': 'color-orange',
    '粉': 'color-pink'
  };
  return colorMap[color];
}

/**
 * 获取颜色对应的标准色值（用于动态样式）
 */
export function getColorValue(color: Color): string {
  const colorMap: Record<Color, string> = {
    '红': '#ef5350',
    '蓝': '#42a5f5',
    '绿': '#66bb6a',
    '橙': '#ffa726',
    '粉': '#ec407a'
  };
  return colorMap[color];
}

/**
 * 获取颜色的浅色版本（用于搁置状态）
 */
export function getLightColorValue(color: Color): string {
  const colorMap: Record<Color, string> = {
    '红': '#ffcdd2',
    '蓝': '#bbdefb',
    '绿': '#c8e6c9',
    '橙': '#ffe0b2',
    '粉': '#f8bbd9'
  };
  return colorMap[color];
}

/**
 * 生成 60 张牌的完整牌组
 * 颜色与数字绑定循环：红 1、蓝 2、绿 3、橙 4、粉 5、红 6……
 */
export function generateFullDeck(): Array<{ color: Color; number: number }> {
  const deck: Array<{ color: Color; number: number }> = [];
  const colors: Color[] = ['红', '蓝', '绿', '橙', '粉'];
  
  for (let i = 1; i <= 60; i++) {
    const colorIndex = (i - 1) % 5;
    deck.push({
      color: colors[colorIndex],
      number: i
    });
  }
  
  return deck;
}

/**
 * 根据数字获取对应的颜色（按照牌组规律）
 */
export function getColorFromNumber(number: number): Color {
  const colors: Color[] = ['红', '蓝', '绿', '橙', '粉'];
  const colorIndex = (number - 1) % 5;
  return colors[colorIndex];
}

/**
 * 验证房间号格式（4 位字母/数字）
 */
export function isValidRoomId(roomId: string): boolean {
  // 仅允许 4 位数字房间号
  return /^\d{4}$/.test(roomId);
}

/**
 * 验证昵称格式（2-8 个字符，仅允许中文、英文、数字）
 */
export function isValidPlayerName(name: string): boolean {
  // 最小长度放宽到 1，最大 8
  return /^[\u4e00-\u9fa5A-Za-z0-9]{1,8}$/.test(name);
}
