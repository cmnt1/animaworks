/**
 * VoiceManager — Orchestrates voice chat (WebSocket + AudioWorklet + VAD + Playback).
 */
import { VoicePlayback } from './voice-playback.js';
import { VoiceVAD } from './voice-vad.js';
import { basePath } from '/shared/base-path.js';

// Hard cap on one continuous recording — matches the server's audio buffer.
const MAX_RECORD_MS = 60_000;
// Speakers keep echoing after the last sample (device latency + room tail);
// In the boolean-AEC fallback, keep VAD shut that long past playback end.
const ECHO_TAIL_MS = 1200;

export class VoiceManager {
  constructor() {
    this._ws = null;
    this._animaName = null;
    this._mode = 'ptt'; // 'ptt' or 'vad'
    this._recording = false;
    this._connected = false;
    this._startingRecording = false;
    this._pendingStop = false;
    this._audioContext = null;
    this._workletNode = null;
    this._mediaStream = null;
    this._aecAll = false;
    this._maxRecordTimer = null;
    this._playback = new VoicePlayback();
    this._playback.onPlaybackEnd = () => {
      this._lastPlaybackEndMs = performance.now();
      if (this._ttsPlaying) {
        this._ttsPlaying = false;
        this._emit('playbackEnd');
      }
    };
    this._playback.onCaption = (text) => this._emit('caption', { text });
    this._pendingCaption = null;
    this._vad = null;
    this._ttsPlaying = false;
    this._lastPlaybackEndMs = 0;
    this._listeners = {};
    this._reconnectTimer = null;
    this._reconnectAttempts = 0;
    this._maxReconnectAttempts = 5;
    this._connGen = 0; // connection generation to ignore stale WS events
  }

  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
  }

  off(event, fn) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter((f) => f !== fn);
  }

  _emit(event, data) {
    (this._listeners[event] || []).forEach((f) => f(data));
  }

  connect(animaName) {
    this.disconnect();
    this._animaName = animaName;
    const gen = ++this._connGen;

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}${basePath}/ws/voice/${encodeURIComponent(animaName)}`;

    return new Promise((resolve, reject) => {
      let settled = false;
      this._ws = new WebSocket(url);
      this._ws.binaryType = 'arraybuffer';

      this._ws.onopen = () => {
        if (gen !== this._connGen) return;
        settled = true;
        this._connected = true;
        this._reconnectAttempts = 0;
        this._emit('connected');
        resolve();
      };
      this._ws.onclose = (e) => {
        if (gen !== this._connGen) return;
        this._connected = false;
        if (!settled) {
          settled = true;
          reject(new Error('WebSocket closed before open'));
          return;
        }
        this._emit('disconnected', { code: e.code });
        this._tryReconnect();
      };
      this._ws.onerror = () => {
        if (gen !== this._connGen) return;
        this._emit('error', { message: 'WebSocket error' });
      };
      this._ws.onmessage = (e) => {
        if (gen !== this._connGen) return;
        this._handleMessage(e);
      };
    });
  }

  disconnect() {
    this._pendingStop = true;
    this._stopRecordingInternal();
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    this._connected = false;
    this._animaName = null;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this._playback.destroy();
    this._playback = new VoicePlayback();
    this._playback.onPlaybackEnd = () => {
      if (this._ttsPlaying) {
        this._ttsPlaying = false;
        this._emit('playbackEnd');
      }
    };
    this._playback.onCaption = (text) => this._emit('caption', { text });
    this._pendingCaption = null;
    if (this._vad) {
      this._vad.destroy();
      this._vad = null;
    }
    this._releaseMediaStream();
  }

  _isEchoAllUnsupported(err) {
    return (
      (err?.name === 'OverconstrainedError' &&
        (!err.constraint || err.constraint === 'echoCancellation')) ||
      (err?.name === 'TypeError' && /echoCancellation|constraint/i.test(err?.message || ''))
    );
  }

  async _acquireMediaStream() {
    const common = {
      sampleRate: 48000,
      channelCount: 1,
      noiseSuppression: true,
      autoGainControl: true,
    };
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { ...common, echoCancellation: { exact: 'all' } },
      });
    } catch (err) {
      if (!this._isEchoAllUnsupported(err)) throw err;
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { ...common, echoCancellation: true },
      });
      this._aecAll = false;
      return stream;
    }

    const track = stream.getAudioTracks()[0];
    if (track?.getSettings().echoCancellation === 'all') {
      this._aecAll = true;
      return stream;
    }

    stream.getTracks().forEach((t) => t.stop());
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { ...common, echoCancellation: true },
    });
    this._aecAll = false;
    return stream;
  }

  async _ensureMediaStream() {
    if (this._mediaStream && this._mediaStream.active !== false) return this._mediaStream;
    const generation = this._connGen;
    const stream = await this._acquireMediaStream();
    if (generation !== this._connGen || !this._connected) {
      stream.getTracks().forEach((t) => t.stop());
      throw new Error('Voice disconnected');
    }
    this._mediaStream = stream;
    return stream;
  }

  _releaseMediaStream() {
    if (this._mediaStream) {
      this._mediaStream.getTracks().forEach((t) => t.stop());
      this._mediaStream = null;
    }
    this._aecAll = false;
  }

  async startRecording() {
    if (this._recording || this._startingRecording || !this._connected) return;

    if (this._ttsPlaying) {
      this.interrupt();
    }

    this._startingRecording = true;
    this._pendingStop = false;

    try {
      const mediaStream = await this._ensureMediaStream();

      if (this._pendingStop || !this._connected) {
        if (this._mode !== 'vad') this._releaseMediaStream();
        this._startingRecording = false;
        this._pendingStop = false;
        return;
      }

      this._audioContext = new AudioContext({ sampleRate: 48000 });

      // Resolve against this module's URL so the /app/ base path and version
      // prefix are preserved (an absolute '/modules/...' 404s behind nginx).
      await this._audioContext.audioWorklet.addModule(
        new URL('./voice-worklet.js', import.meta.url),
      );

      if (this._pendingStop) {
        this._audioContext.close();
        this._audioContext = null;
        if (this._mode !== 'vad') this._releaseMediaStream();
        this._startingRecording = false;
        this._pendingStop = false;
        return;
      }

      const source = this._audioContext.createMediaStreamSource(mediaStream);
      this._workletNode = new AudioWorkletNode(this._audioContext, 'voice-pcm-processor', {
        processorOptions: { sampleRate: this._audioContext.sampleRate },
      });

      this._workletNode.port.onmessage = (e) => {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
          this._ws.send(e.data);
        }
      };

      const silentGain = this._audioContext.createGain();
      silentGain.gain.value = 0;
      source.connect(this._workletNode);
      this._workletNode.connect(silentGain);
      silentGain.connect(this._audioContext.destination);

      this._recording = true;
      this._startingRecording = false;
      // Safety net for any missed stop event: the server only keeps 60s of
      // audio anyway, so force the turn instead of streaming the mic forever.
      this._maxRecordTimer = setTimeout(() => this.stopRecording(), MAX_RECORD_MS);
      this._emit('recordingStart');
    } catch (err) {
      this._startingRecording = false;
      this._pendingStop = false;
      if (this._connected) {
        this._emit('error', { message: `Microphone error: ${err.message}` });
      }
    }
  }

  stopRecording() {
    if (this._startingRecording) {
      this._pendingStop = true;
      this._emit('recordingStop');
      return;
    }
    if (!this._recording) return;
    this._stopRecordingInternal();
    if (this._mode !== 'vad') this._releaseMediaStream();
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'speech_end' }));
    }
    this._emit('recordingStop');
  }

  /**
   * Abort a recording that a VAD misfire started (blip too short to be speech).
   * Sends neither speech_end (no turn on noise) nor interrupt (that is
   * barge-in and would kill a reply the anima is streaming) — just tells the
   * server to drop the buffered noise.
   */
  discardRecording() {
    if (this._startingRecording) {
      this._pendingStop = true;
      this._emit('recordingStop');
      return;
    }
    if (!this._recording) return;
    this._stopRecordingInternal();
    if (this._mode !== 'vad') this._releaseMediaStream();
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'discard_audio' }));
    }
    this._emit('recordingStop');
  }

  _stopRecordingInternal() {
    this._recording = false;
    if (this._maxRecordTimer) {
      clearTimeout(this._maxRecordTimer);
      this._maxRecordTimer = null;
    }
    if (this._workletNode) {
      this._workletNode.disconnect();
      this._workletNode = null;
    }
    if (this._audioContext) {
      this._audioContext.close();
      this._audioContext = null;
    }
  }

  _outputActive() {
    return (
      this._ttsPlaying ||
      this._playback.isPlaying ||
      this._playback.queueLength > 0 ||
      performance.now() - this._lastPlaybackEndMs < ECHO_TAIL_MS
    );
  }

  interrupt() {
    this._pendingCaption = null;
    this._playback.stop();
    this._ttsPlaying = false;
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'interrupt' }));
    }
    this._emit('interrupted');
  }

  setMode(mode) {
    if (mode === this._mode) {
      // After disconnect, mode stays but VAD instance is gone — restart if needed.
      if (mode === 'vad' && !this._vad) this._startVAD();
      return;
    }
    this._mode = mode;
    if (mode === 'vad') {
      this._startVAD();
    } else {
      if (this._vad) this._vad.stop();
      if (!this._recording && !this._startingRecording) this._releaseMediaStream();
    }
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'config', vad_mode: mode }));
    }
    this._emit('modeChange', { mode });
  }

  async _startVAD() {
    if (this._vad) {
      await this._vad.start();
      return;
    }
    try {
      await this._ensureMediaStream();
    } catch (err) {
      if (this._connected && this._mode === 'vad') {
        this._emit('error', { message: `Microphone error: ${err.message}` });
      }
      return;
    }
    if (this._mode !== 'vad') {
      this._releaseMediaStream();
      return;
    }
    const vad = new VoiceVAD({
      getStream: () => this._ensureMediaStream(),
      pauseStream: async () => {},
      resumeStream: () => this._ensureMediaStream(),
      onSpeechStart: () => {
        if (this._outputActive() && !this._aecAll) return;
        if (this._outputActive()) this.interrupt();
        this.startRecording();
      },
      onSpeechEnd: () => this.stopRecording(),
      onMisfire: () => this.discardRecording(),
    });
    this._vad = vad;
    await vad.start();
    if (this._vad !== vad || this._mode !== 'vad' || !this._connected) {
      vad.destroy();
      if (this._vad === vad) this._vad = null;
      this._releaseMediaStream();
    }
  }

  _handleMessage(event) {
    if (event.data instanceof ArrayBuffer) {
      // First chunk after a tts_start carries that sentence's subtitle.
      this._playback.enqueue(event.data, this._pendingCaption);
      this._pendingCaption = null;
      return;
    }
    try {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case 'transcript':
          this._emit('transcript', { text: msg.text });
          break;
        case 'transcript_partial':
          this._emit('transcriptPartial', { text: msg.text });
          break;
        case 'response_start':
          this._emit('responseStart');
          break;
        case 'response_text':
          this._emit('responseText', { text: msg.text, done: msg.done });
          break;
        case 'response_done':
          this._emit('responseDone', { emotion: msg.emotion });
          break;
        case 'emotion':
          this._emit('emotion', { emotion: msg.emotion });
          break;
        case 'tts_start':
          this._ttsPlaying = true;
          this._pendingCaption = msg.text || null;
          this._emit('ttsStart');
          break;
        case 'tts_done':
          if (this._playback.queueLength === 0 && !this._playback.isPlaying) {
            this._ttsPlaying = false;
          }
          this._emit('ttsDone');
          break;
        case 'thinking_status':
          this._emit('thinkingStatus', msg.thinking);
          break;
        case 'thinking_delta':
          this._emit('thinkingDelta', { text: msg.text });
          break;
        case 'error':
          this._emit('error', { message: msg.message });
          break;
        case 'status':
          this._emit('status', { state: msg.state });
          break;
      }
    } catch {
      // Ignore parse errors
    }
  }

  _tryReconnect() {
    if (this._reconnectAttempts >= this._maxReconnectAttempts || !this._animaName) return;
    const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts), 30000);
    this._reconnectAttempts++;
    this._reconnectTimer = setTimeout(() => this.connect(this._animaName), delay);
  }

  setVolume(v) {
    this._playback.setVolume(v);
  }

  get isConnected() {
    return this._connected;
  }
  get isRecording() {
    return this._recording;
  }
  get isTTSPlaying() {
    return this._ttsPlaying;
  }
  get mode() {
    return this._mode;
  }

  /** TTS再生時の正規化RMS(0..1)。`_playback` はdisconnectで再生成されるためgetterで都度参照。 */
  get ttsRMS() {
    return this._playback.rms;
  }
}

export const voiceManager = new VoiceManager();
