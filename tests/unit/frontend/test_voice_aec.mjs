import { afterEach, beforeEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const voiceSource = await readFile(
  new URL('../../../server/static/modules/voice.js', import.meta.url),
  'utf8',
);

const playbackStub = `
class VoicePlayback {
  constructor() {
    this.isPlaying = false;
    this.queueLength = 0;
    this.rms = 0;
  }
  destroy() {}
  stop() { this.isPlaying = false; this.queueLength = 0; }
  enqueue() {}
  setVolume() {}
}`;

const vadStub = `
class VoiceVAD {
  constructor(options) { this.options = options; }
  async start() { return true; }
  stop() {}
  destroy() {}
}`;

const moduleSource = voiceSource
  .replace("import { VoicePlayback } from './voice-playback.js';", playbackStub)
  .replace("import { VoiceVAD } from './voice-vad.js';", vadStub)
  .replace("import { basePath } from '/shared/base-path.js';", "const basePath = '';")
  .replace("new URL('./voice-worklet.js', import.meta.url)", "'voice-worklet.js'");

const { VoiceManager } = await import(
  `data:text/javascript;base64,${Buffer.from(moduleSource).toString('base64')}`,
);

class FakeTrack {
  constructor(settings = {}) {
    this.settings = settings;
    this.stopped = false;
  }

  getSettings() {
    return this.settings;
  }

  stop() {
    this.stopped = true;
  }
}

class FakeStream {
  constructor(settings = {}) {
    this.track = new FakeTrack(settings);
  }

  get active() {
    return !this.track.stopped;
  }

  getTracks() {
    return [this.track];
  }

  getAudioTracks() {
    return [this.track];
  }
}

class FakeAudioContext {
  static instances = [];

  constructor() {
    this.sampleRate = 48000;
    this.closed = false;
    this.sources = [];
    this.audioWorklet = { addModule: async () => {} };
    FakeAudioContext.instances.push(this);
  }

  createMediaStreamSource(stream) {
    this.sources.push(stream);
    return { connect() {} };
  }

  createGain() {
    return { gain: { value: 1 }, connect() {} };
  }

  close() {
    this.closed = true;
  }
}

class FakeAudioWorkletNode {
  constructor() {
    this.port = { onmessage: null };
  }

  connect() {}
  disconnect() {}
}

const originalGlobals = new Map();
const managers = [];

function setGlobal(name, value) {
  if (!originalGlobals.has(name)) {
    originalGlobals.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
  }
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value,
  });
}

function newManager() {
  const manager = new VoiceManager();
  manager._connected = true;
  manager._ws = {
    readyState: 1,
    sent: [],
    send(message) { this.sent.push(message); },
    close() {},
  };
  managers.push(manager);
  return manager;
}

beforeEach(() => {
  FakeAudioContext.instances = [];
  setGlobal('AudioContext', FakeAudioContext);
  setGlobal('AudioWorkletNode', FakeAudioWorkletNode);
  setGlobal('WebSocket', { OPEN: 1 });
  setGlobal('navigator', { mediaDevices: { getUserMedia: async () => new FakeStream() } });
});

afterEach(() => {
  for (const manager of managers.splice(0)) manager.disconnect();
  for (const [name, descriptor] of originalGlobals) {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete globalThis[name];
  }
  originalGlobals.clear();
});

describe('VoiceManager native AEC', () => {
  it('accepts exact all only when getSettings confirms all', async () => {
    const stream = new FakeStream({ echoCancellation: 'all' });
    const calls = [];
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      calls.push(constraints);
      return stream;
    };
    const manager = newManager();

    assert.equal(await manager._ensureMediaStream(), stream);
    assert.equal(manager._aecAll, true);
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0].audio.echoCancellation, { exact: 'all' });
  });

  it('falls back to boolean AEC for OverconstrainedError, but does not retry permission errors', async () => {
    const fallbackStream = new FakeStream({ echoCancellation: true });
    const calls = [];
    let attempt = 0;
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      calls.push(constraints);
      attempt += 1;
      if (attempt === 1) {
        const error = new Error('all unsupported');
        error.name = 'OverconstrainedError';
        error.constraint = 'echoCancellation';
        throw error;
      }
      return fallbackStream;
    };
    const manager = newManager();

    assert.equal(await manager._ensureMediaStream(), fallbackStream);
    assert.equal(manager._aecAll, false);
    assert.equal(calls.length, 2);
    assert.equal(calls[1].audio.echoCancellation, true);

    const permissionManager = newManager();
    let permissionCalls = 0;
    const permissionError = new Error('permission denied');
    permissionError.name = 'NotAllowedError';
    navigator.mediaDevices.getUserMedia = async () => {
      permissionCalls += 1;
      throw permissionError;
    };
    await assert.rejects(permissionManager._ensureMediaStream(), { name: 'NotAllowedError' });
    assert.equal(permissionCalls, 1);
  });

  it('passes one cached stream to both VAD and AudioWorklet recording', async () => {
    const stream = new FakeStream({ echoCancellation: 'all' });
    navigator.mediaDevices.getUserMedia = async () => stream;
    const manager = newManager();

    manager._mode = 'vad';
    await manager._startVAD();
    assert.equal(await manager._vad.options.getStream(), stream);
    assert.equal(await manager._vad.options.resumeStream(), stream);
    await manager.startRecording();
    assert.equal(FakeAudioContext.instances.at(-1).sources[0], stream);
  });

  it('allows barge-in with all AEC and keeps fallback mode half-duplex', async () => {
    const allStream = new FakeStream({ echoCancellation: 'all' });
    navigator.mediaDevices.getUserMedia = async () => allStream;
    const allManager = newManager();
    allManager._mode = 'vad';
    await allManager._startVAD();
    allManager._ttsPlaying = true;
    allManager._vad.options.onSpeechStart();
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(allManager._ws.sent, [JSON.stringify({ type: 'interrupt' })]);
    assert.equal(allManager.isRecording, true);

    const fallbackStream = new FakeStream({ echoCancellation: true });
    navigator.mediaDevices.getUserMedia = async () => fallbackStream;
    const fallbackManager = newManager();
    fallbackManager._mode = 'vad';
    await fallbackManager._startVAD();
    fallbackManager._ttsPlaying = true;
    fallbackManager._vad.options.onSpeechStart();
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(fallbackManager._ws.sent, []);
    assert.equal(fallbackManager.isRecording, false);
  });

  it('releases the microphone track when push-to-talk recording ends', async () => {
    const stream = new FakeStream({ echoCancellation: 'all' });
    navigator.mediaDevices.getUserMedia = async () => stream;
    const manager = newManager();

    await manager.startRecording();
    assert.equal(manager.isRecording, true);
    manager.stopRecording();
    assert.equal(stream.track.stopped, true);
    assert.equal(manager._mediaStream, null);
    assert.deepEqual(manager._ws.sent, [JSON.stringify({ type: 'speech_end' })]);
  });
});
