/**
 * 语音通话引擎（WebRTC Mesh，单例）。
 *
 * 设计要点：
 * - 单例而非 composable：玩家在大厅 ↔ 游戏页之间跳转时组件会卸载重建，
 *   单例可以让语音通话不中断；UI 只读它的响应式状态。
 * - 信令全部走房间 WebSocket（VoiceJoin / VoiceSignal / …），
 *   服务端只维护成员表，媒体流点对点直连，不经过服务器转发。
 * - iceServers 留空：局域网 / Tailscale 内网下 host candidate 足以连通，
 *   同时避免把内网 IP 泄露给公网 STUN 服务器。
 * - 房主禁麦由服务端记录并推送 Event_VoiceHostMuted，客户端禁用麦克风轨道。
 */

import { ref, computed, watch } from 'vue';
import { wsService } from '@/services/websocket';
import { useGameStore } from '@/stores/game';
import type { VoiceMember, VoiceSignalData } from '@/types/game';

const SPEAK_THRESHOLD = 0.02; // RMS 阈值，超过视为正在说话
const SPEAK_INTERVAL = 200;   // 说话检测间隔（ms）

class VoiceChatService {
  // ---------------- 响应式状态（供 UI 绑定） ----------------
  inCall = ref(false);
  selfMuted = ref(false);
  hostMuted = ref(false);
  selfSpeaking = ref(false);
  errorMsg = ref('');
  notice = ref('');
  members = ref<VoiceMember[]>([]);
  peerStates = ref<Record<string, RTCPeerConnectionState>>({});
  mics = ref<MediaDeviceInfo[]>([]);
  outputs = ref<MediaDeviceInfo[]>([]);
  selectedMic = ref('');
  selectedOutput = ref('');
  volume = ref(1);

  /** 浏览器是否处于安全上下文（HTTPS / localhost），否则无法调用麦克风 */
  secureContext = computed(() => typeof window !== 'undefined' && window.isSecureContext);

  // ---------------- 内部状态 ----------------
  private playerId = '';
  private playerName = '';
  private isHost = false;
  private localStream: MediaStream | null = null;
  private audioCtx: AudioContext | null = null;
  private speakTimer: number | null = null;
  private noticeTimer: number | null = null;
  private dataBuffer = new Uint8Array(0);
  private peers = new Map<string, RTCPeerConnection>();
  private remoteAudios = new Map<string, HTMLAudioElement>();
  private remoteAnalysers = new Map<string, AnalyserNode>();
  private localAnalyser: AnalyserNode | null = null;
  private pendingCandidates = new Map<string, RTCIceCandidateInit[]>();
  private remoteSelfMuted = new Set<string>();
  private remoteSpeaking = new Map<string, boolean>();
  private initialized = false;

  // ---------------- 身份与初始化 ----------------

  /** ChatPanel 挂载时调用：登记当前玩家身份（大厅与游戏页各自调用） */
  setIdentity(playerId: string, playerName: string, isHost: boolean) {
    this.playerId = playerId;
    this.playerName = playerName;
    this.isHost = isHost;
    this.syncMembers();
  }

  /** 注册 WebSocket 回调（只做一次） */
  init() {
    if (this.initialized) return;
    this.initialized = true;
    wsService.setVoiceEventCallback((event, payload) => this.handleVoiceEvent(event, payload));
    // 断线重连后重新登记成员身份，双方重建连接
    wsService.setReopenedCallback(() => {
      if (this.inCall.value) {
        wsService.send({ cmd: 'VoiceJoin' });
      }
    });
    // 服务端快照里的语音成员表变化时同步 UI（别人加入/离开/禁麦）
    watch(
      () => useGameStore().gameState?.voice,
      () => this.syncMembers(),
      { deep: true }
    );
    if (navigator.mediaDevices?.addEventListener) {
      navigator.mediaDevices.addEventListener('devicechange', () => this.refreshDevices());
    }
  }

  // ---------------- 本地媒体流 ----------------

  private async ensureLocalStream(force = false): Promise<MediaStream | null> {
    if (localStreamExists(this.localStream) && !force) return this.localStream;
    if (!navigator.mediaDevices?.getUserMedia) {
      this.errorMsg.value = '当前浏览器不支持麦克风采集';
      return null;
    }
    try {
      const audio: boolean | MediaTrackConstraints = this.selectedMic.value
        ? { deviceId: { exact: this.selectedMic.value }, echoCancellation: true, noiseSuppression: true }
        : { echoCancellation: true, noiseSuppression: true };
      const stream = await navigator.mediaDevices.getUserMedia({ audio, video: false });
      if (force && this.localStream) {
        // 换设备：旧轨道全部停止
        this.localStream.getTracks().forEach((t) => t.stop());
      }
      this.localStream = stream;
      this.applySelfMuteToTracks();
      this.setupLocalAnalyser(stream);
      this.refreshDevices();
      return stream;
    } catch (err: any) {
      const name = err?.name || '';
      if (name === 'NotAllowedError') {
        this.errorMsg.value = '麦克风权限被拒绝，请在浏览器地址栏放行后重试';
      } else if (name === 'NotFoundError') {
        this.errorMsg.value = '未检测到可用的麦克风设备';
      } else {
        this.errorMsg.value = '无法打开麦克风：' + (err?.message || name || '未知错误');
      }
      return null;
    }
  }

  private applySelfMuteToTracks() {
    const enabled = !(this.selfMuted.value || this.hostMuted.value);
    this.localStream?.getAudioTracks().forEach((t) => (t.enabled = enabled));
  }

  private setupLocalAnalyser(stream: MediaStream) {
    try {
      if (!this.audioCtx) {
        this.audioCtx = new AudioContext();
        this.dataBuffer = new Uint8Array(this.audioCtx.sampleRate / 10);
      }
      if (this.audioCtx.state === 'suspended') void this.audioCtx.resume();
      const source = this.audioCtx.createMediaStreamSource(stream);
      const analyser = this.audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      this.localAnalyser = analyser;
      this.startSpeakLoop();
    } catch (err) {
      console.warn('[voice] 本地音频分析初始化失败', err);
    }
  }

  private startSpeakLoop() {
    if (this.speakTimer !== null) return;
    this.speakTimer = window.setInterval(() => this.tick(), SPEAK_INTERVAL);
  }

  private stopSpeakLoop() {
    if (this.speakTimer !== null) {
      clearInterval(this.speakTimer);
      this.speakTimer = null;
    }
  }

  private tick() {
    if (!this.audioCtx) return;
    const flags = new Map<string, boolean>();
    const measure = (key: string, analyser: AnalyserNode | null) => {
      if (!analyser) return;
      if (this.dataBuffer.length !== analyser.fftSize) {
        this.dataBuffer = new Uint8Array(analyser.fftSize);
      }
      analyser.getByteTimeDomainData(this.dataBuffer);
      let sum = 0;
      for (let i = 0; i < this.dataBuffer.length; i++) {
        const v = (this.dataBuffer[i] - 128) / 128;
        sum += v * v;
      }
      flags.set(key, Math.sqrt(sum / this.dataBuffer.length) > SPEAK_THRESHOLD);
    };
    measure('self', this.localAnalyser);
    for (const [pid, analyser] of this.remoteAnalysers) measure(pid, analyser);
    this.selfSpeaking.value = flags.get('self') || false;
    this.remoteSpeaking = flags;
    this.syncMembers();
  }

  // ---------------- 加入 / 退出 ----------------

  async joinCall() {
    if (!this.secureContext.value) {
      this.errorMsg.value = '语音通话需要 HTTPS 安全上下文，请使用 https:// 地址访问';
      return;
    }
    if (this.inCall.value) return;
    this.errorMsg.value = '';
    const stream = await this.ensureLocalStream();
    if (!stream) return;
    this.inCall.value = true;
    wsService.send({ cmd: 'VoiceJoin' });
    this.syncMembers();
  }

  async leaveCall(notify = true) {
    if (notify) {
      wsService.send({ cmd: 'VoiceLeave' });
    }
    for (const pid of [...this.peers.keys()]) this.closePeer(pid);
    this.stopSpeakLoop();
    this.localAnalyser = null;
    if (this.localStream) {
      this.localStream.getTracks().forEach((t) => t.stop());
      this.localStream = null;
    }
    if (this.audioCtx) {
      try {
        await this.audioCtx.close();
      } catch {
        /* 忽略 */
      }
      this.audioCtx = null;
    }
    this.inCall.value = false;
    this.selfMuted.value = false;
    this.hostMuted.value = false;
    this.remoteSelfMuted.clear();
    this.remoteSpeaking.clear();
    this.syncMembers();
  }

  // ---------------- PeerConnection 管理 ----------------

  private createPeer(pid: string, initiator: boolean) {
    if (this.peers.has(pid) || pid === this.playerId) return;
    let pc: RTCPeerConnection;
    try {
      pc = new RTCPeerConnection({ iceServers: [] });
    } catch (err) {
      console.warn('[voice] 创建 RTCPeerConnection 失败', err);
      return;
    }
    this.peers.set(pid, pc);
    this.pendingCandidates.set(pid, []);

    if (this.localStream) {
      for (const track of this.localStream.getAudioTracks()) {
        pc.addTrack(track, this.localStream);
      }
    }

    pc.onicecandidate = (event) => {
      if (event.candidate) {
        wsService.send({
          cmd: 'VoiceSignal',
          to: pid,
          data: { candidate: event.candidate.toJSON() },
        });
      }
    };

    pc.ontrack = (event) => {
      const stream = event.streams?.[0] || new MediaStream([event.track]);
      this.attachRemoteAudio(pid, stream);
    };

    pc.onconnectionstatechange = () => {
      this.peerStates.value = { ...this.peerStates.value, [pid]: pc.connectionState };
      this.syncMembers();
      if (pc.connectionState === 'failed') {
        // 连接失败：清理后由重连逻辑重建
        this.closePeer(pid);
      }
    };

    this.peerStates.value = { ...this.peerStates.value, [pid]: pc.connectionState };
    this.syncMembers();

    if (initiator) {
      void this.makeOffer(pc, pid);
    }
  }

  private async makeOffer(pc: RTCPeerConnection, pid: string) {
    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsService.send({
        cmd: 'VoiceSignal',
        to: pid,
        data: { description: { type: offer.type, sdp: offer.sdp } },
      });
    } catch (err) {
      console.warn('[voice] createOffer 失败', err);
    }
  }

  private closePeer(pid: string) {
    const pc = this.peers.get(pid);
    if (pc) {
      pc.onicecandidate = null;
      pc.ontrack = null;
      pc.onconnectionstatechange = null;
      try {
        pc.close();
      } catch {
        /* 忽略 */
      }
      this.peers.delete(pid);
    }
    this.pendingCandidates.delete(pid);
    const audio = this.remoteAudios.get(pid);
    if (audio) {
      audio.srcObject = null;
      this.remoteAudios.delete(pid);
    }
    this.remoteAnalysers.delete(pid);
    const next = { ...this.peerStates.value };
    delete next[pid];
    this.peerStates.value = next;
    this.remoteSelfMuted.delete(pid);
    this.syncMembers();
  }

  private attachRemoteAudio(pid: string, stream: MediaStream) {
    let audio = this.remoteAudios.get(pid);
    if (!audio) {
      audio = new Audio();
      audio.autoplay = true;
      this.remoteAudios.set(pid, audio);
    }
    audio.srcObject = stream;
    audio.volume = this.volume.value;
    void this.applyOutputDevice(audio);
    audio.play().catch(() => {
      /* 自动播放被拦截时保持元素就绪，用户交互后再播 */
    });
    // 远程说话检测（只做分析，不占用输出通路）
    try {
      if (!this.audioCtx) this.audioCtx = new AudioContext();
      const source = this.audioCtx.createMediaStreamSource(stream);
      const analyser = this.audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      this.remoteAnalysers.set(pid, analyser);
      this.startSpeakLoop();
    } catch (err) {
      console.warn('[voice] 远程音频分析初始化失败', err);
    }
  }

  // ---------------- 信令处理 ----------------

  private handleVoiceEvent(event: string, payload: any) {
    switch (event) {
      case 'Event_VoicePeers':
        // 我（新成员）拿到既有成员列表，主动向每人发 offer
        for (const pid of payload?.peers || []) {
          this.createPeer(pid, true);
        }
        break;

      case 'Event_VoicePeerJoined':
        // 有人加入：等对方 offer。若这是刷新重连的旧 PeerConnection，先拆掉
        if (payload?.playerId && payload.playerId !== this.playerId) {
          if (this.peers.has(payload.playerId)) {
            this.closePeer(payload.playerId);
          }
        }
        break;

      case 'Event_VoicePeerLeft':
        if (payload?.playerId) this.closePeer(payload.playerId);
        break;

      case 'Event_VoiceSignal':
        if (payload?.from) void this.handleSignal(payload.from, payload.data || {});
        break;

      case 'Event_VoiceMuteState':
        if (payload?.muted) {
          this.remoteSelfMuted.add(payload.playerId);
        } else {
          this.remoteSelfMuted.delete(payload.playerId);
        }
        this.syncMembers();
        break;

      case 'Event_VoiceHostMuted':
        this.hostMuted.value = !!payload?.muted;
        this.applySelfMuteToTracks();
        this.showNotice(
          this.hostMuted.value ? '你已被房主禁麦' : '房主已解除禁麦'
        );
        this.syncMembers();
        break;

      case 'Event_VoiceKicked':
        this.showNotice(`你已被${payload?.by || '房主'}移出语音通话`);
        void this.leaveCall(false);
        break;

      case 'Event_VoiceClosed':
        this.showNotice(payload?.by ? `${payload.by}关闭了语音通话` : '语音通话已结束');
        void this.leaveCall(false);
        break;

      default:
        break;
    }
  }

  private async handleSignal(from: string, data: VoiceSignalData) {
    if (!this.inCall.value) return;
    let pc = this.peers.get(from);
    if (!pc) {
      // 对方先到了（极端竞态）：被动等 offer
      this.createPeer(from, false);
      pc = this.peers.get(from);
    }
    if (!pc) return;

    try {
      if (data.description) {
        const description = new RTCSessionDescription(data.description);
        await pc.setRemoteDescription(description);
        const queued = this.pendingCandidates.get(from) || [];
        this.pendingCandidates.set(from, []);
        for (const candidate of queued) {
          try {
            await pc.addIceCandidate(new RTCIceCandidate(candidate));
          } catch {
            /* 忽略过期候选 */
          }
        }
        if (description.type === 'offer') {
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          wsService.send({
            cmd: 'VoiceSignal',
            to: from,
            data: { description: { type: answer.type, sdp: answer.sdp } },
          });
        }
      } else if (data.candidate) {
        if (pc.remoteDescription) {
          await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
        } else {
          const queue = this.pendingCandidates.get(from) || [];
          queue.push(data.candidate);
          this.pendingCandidates.set(from, queue);
        }
      }
    } catch (err) {
      console.warn('[voice] 信令处理失败', err);
    }
  }

  // ---------------- 静音 / 设备 / 音量 ----------------

  toggleSelfMute() {
    this.selfMuted.value = !this.selfMuted.value;
    this.applySelfMuteToTracks();
    wsService.send({ cmd: 'VoiceSetMute', muted: this.selfMuted.value });
    this.syncMembers();
  }

  hostMuteAll(muted: boolean) {
    if (!this.isHost) return;
    wsService.send({ cmd: 'VoiceMuteAll', muted });
  }

  hostCloseCall() {
    if (!this.isHost) return;
    wsService.send({ cmd: 'VoiceClose' });
  }

  hostKick(playerId: string) {
    if (!this.isHost) return;
    wsService.send({ cmd: 'VoiceKick', playerId });
  }

  async changeMic(deviceId: string) {
    this.selectedMic.value = deviceId;
    if (!this.inCall.value) return;
    const stream = await this.ensureLocalStream(true);
    if (!stream) return;
    const newTrack = stream.getAudioTracks()[0];
    for (const pc of this.peers.values()) {
      for (const sender of pc.getSenders()) {
        if (sender.track && sender.track.kind === 'audio' && newTrack) {
          try {
            await sender.replaceTrack(newTrack);
          } catch {
            /* 忽略 */
          }
        }
      }
    }
  }

  async changeOutput(deviceId: string) {
    this.selectedOutput.value = deviceId;
    for (const audio of this.remoteAudios.values()) {
      await this.applyOutputDevice(audio);
    }
  }

  private async applyOutputDevice(audio: HTMLAudioElement) {
    if (!this.selectedOutput.value) return;
    if (typeof (audio as any).setSinkId !== 'function') return; // Safari 不支持
    try {
      await (audio as any).setSinkId(this.selectedOutput.value);
    } catch {
      /* 设备不可用时保持默认输出 */
    }
  }

  setVolume(value: number) {
    this.volume.value = Math.min(1, Math.max(0, value));
    for (const audio of this.remoteAudios.values()) {
      audio.volume = this.volume.value;
    }
  }

  async refreshDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      this.mics.value = devices.filter((d) => d.kind === 'audioinput');
      this.outputs.value = devices.filter((d) => d.kind === 'audiooutput');
      // 默认选中系统第一项
      if (!this.selectedMic.value && this.mics.value.length > 0) {
        this.selectedMic.value = this.mics.value[0].deviceId;
      }
      if (!this.selectedOutput.value && this.outputs.value.length > 0) {
        this.selectedOutput.value = this.outputs.value[0].deviceId;
      }
    } catch {
      /* 忽略 */
    }
  }

  // ---------------- 状态合成 ----------------

  /** 依据服务端 voice 成员表 + 本地连接状态合成 UI 列表 */
  syncMembers() {
    const store = useGameStore();
    const state = store.gameState;
    const participants = state?.voice?.participants || [];
    const hostMutedList = state?.voice?.hostMuted || [];
    this.members.value = participants.map((pid) => {
      const player = state?.players?.[pid];
      return {
        playerId: pid,
        playerName: player?.playerName || pid,
        isBot: !!player?.isBot,
        hostMuted: hostMutedList.includes(pid),
        selfMuted: pid === this.playerId ? this.selfMuted.value : this.remoteSelfMuted.has(pid),
        speaking: pid === this.playerId ? this.selfSpeaking.value : !!this.remoteSpeaking.get(pid),
        connected: pid === this.playerId ? this.inCall.value : this.peerStates.value[pid] === 'connected',
      };
    });
  }

  showNotice(text: string) {
    this.notice.value = text;
    if (this.noticeTimer !== null) clearTimeout(this.noticeTimer);
    this.noticeTimer = window.setTimeout(() => {
      this.notice.value = '';
    }, 4000);
  }
}

function localStreamExists(stream: MediaStream | null): boolean {
  return !!stream && stream.getAudioTracks().some((t) => t.readyState === 'live');
}

export const voiceChat = new VoiceChatService();
