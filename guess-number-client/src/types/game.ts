// 游戏核心数据类型定义

export type Color = '红' | '蓝' | '绿' | '橙' | '粉';

export interface Card {
  id: string;
  color: Color;
  number: number;
  isSelected?: boolean;
}

export interface PositionResult {
  position: number;       // 0=最左, 1-4=之间, 5=最右
  leftColor: Color | null;
  rightColor: Color | null;
}

export interface Clue {
  id: string;
  type: 'position' | 'point';
  publicCardId: string;
  publicCardNumber?: number;
  targetColor?: Color;
  result: PositionResult | boolean; // position: {position,leftColor,rightColor}, point: true/false
  timestamp: number;
}

export interface Player {
  playerId: string;
  playerName: string;
  isAlive: boolean;
  isOnline: boolean;
  hand: Card[]; // 包含真实数字
  clues: Clue[];
}

export interface DeckRemainingCount {
  红: number;
  蓝: number;
  绿: number;
  橙: number;
  粉: number;
}

export type GamePhase = 'WAITING' | 'PLAYING' | 'GAME_OVER';
export type SubPhase = 'DRAW_PHASE' | 'ACTION_PHASE' | 'JUDGE_RESULT' | 'PAUSED';

export interface PendingJudgement {
  selectedPublicCardId: string;
  judgeType: 'position' | 'point';
  targetColor?: Color;
  result?: PositionResult | boolean;
}

export interface GameOverInfo {
  winnerId: string | null; // null = 平局
  winnerName: string | null;
  correctGuess?: number[];
  reason: 'correct_guess' | 'deck_exhausted';
}

export interface GameState {
  roomId: string;
  hostId?: string;
  gamePhase: GamePhase;
  subPhase: SubPhase | null;
  roundNumber: number;
  currentTurnPlayerId: string | null;
  turnOrder?: string[];
  deckRemainingCount: DeckRemainingCount;
  publicCards: Card[];
  players: Record<string, Player>;
  pendingJudgement: PendingJudgement | null;
  gameOverInfo: GameOverInfo | null;
  seed?: string;
  usedCardNumbers?: Array<{ color: Color; number: number }>;
}

export interface FullStateSnapshot extends GameState {
  // 与 GameState 相同，用于类型明确
}

// WebSocket 客户端指令
export type ClientCommand = 
  | { cmd: 'JoinRoom'; roomId: string; playerName: string }
  | { cmd: 'Reconnect'; roomId: string; playerId: string; accessToken?: string }
  | { cmd: 'StartGame' }
  | { cmd: 'SelectColorToDraw'; color: Color }
  | { cmd: 'SelectPublicCard'; publicCardId: string }
  | { cmd: 'DeselectPublicCard' }
  | { cmd: 'JudgeByPosition'; publicCardId: string }
  | { cmd: 'JudgeByPoint'; publicCardId: string; targetColor: Color }
  | { cmd: 'SkipTurn' }
  | { cmd: 'SubmitGuess'; guesses: number[] }
  | { cmd: 'ResetGame' }
  | { cmd: 'DissolveRoom' }
  | { cmd: 'KickPlayer'; playerId: string };

// WebSocket 服务端事件
export type ServerEvent =
  | { event: 'Event_StateUpdate'; payload: GameState }
  | { event: 'Event_SyncFullState'; payload: FullStateSnapshot }
  | { event: 'Event_GuessResult'; payload: { correct: boolean; correctNumbers?: number[] } }
  | { event: 'Event_PlayerDisconnected'; payload: { playerId: string; isCurrentTurnPlayer: boolean; paused: boolean } }
  | { event: 'Event_GameOver'; payload: GameOverInfo };
