/** End-to-end voice AEC behavior using the real browser modules. */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it, beforeEach, afterEach } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");

const toDataUrl = (source, tag) =>
  `data:text/javascript;base64,${Buffer.from(`${source}\n//# sourceURL=${tag}`, "utf8").toString("base64")}`;

const stripImports = (source) => source.replace(/^import[^\n]*\n/gm, "");

class FakePlayback {
  constructor() {
    this.isPlaying = false;
    this.queueLength = 0;
    this.rms = 0;
    this.aecActive = false;
    this._onPlaybackEnd = null;
    this._onCaption = null;
  }

  set onPlaybackEnd(fn) {
    this._onPlaybackEnd = fn;
  }

  set onCaption(fn) {
    this._onCaption = fn;
  }

  stop() {
    this.isPlaying = false;
    this.queueLength = 0;
  }

  destroy() {
    this.stop();
    this.destroyed = true;
  }

  setVolume() {}

  enqueue() {}
}

class FakeAudioContext {
  constructor() {
    this.state = "running";
    this.sampleRate = 48000;
    this.destination = {};
    this.audioWorklet = { addModule: async () => {} };
  }

  createMediaStreamSource(stream) {
    globalThis.__aecAudioSources.push(stream);
    return { connect() {}, disconnect() {} };
  }

  createGain() {
    return { gain: { value: 0 }, connect() {}, disconnect() {} };
  }

  close() {
    this.state = "closed";
    return Promise.resolve();
  }
}

class FakeAudioWorkletNode {
  constructor() {
    this.port = { onmessage: null };
  }

  connect() {}

  disconnect() {}
}

class FakeWebSocket {
  static OPEN = 1;

  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
    globalThis.__aecSockets.push(this);
    queueMicrotask(() => {
      this.readyState = FakeWebSocket.OPEN;
      this.onopen?.();
    });
  }

  send(value) {
    this.sent.push(value);
  }

  close() {
    this.readyState = 3;
    this.onclose?.({ code: 1000 });
  }
}

function makeStream(settings) {
  const track = {
    stopped: false,
    getSettings: () => settings,
    stop() {
      this.stopped = true;
    },
  };
  return {
    active: true,
    track,
    getAudioTracks: () => [track],
    getTracks: () => [track],
  };
}

function installBrowserStubs() {
  globalThis.__aecSockets = [];
  globalThis.__aecAudioSources = [];
  globalThis.__aecVadOptions = [];
  globalThis.__aecStreamEvents = [];
  globalThis.__aecGetUserMedia = null;

  globalThis.location = { protocol: "http:", host: "localhost" };
  // The real module resolves its worklet relative to import.meta.url. A data
  // URL has no relative path, but the AudioWorklet stub never reads it.
  globalThis.URL = class FakeURL {};
  globalThis.WebSocket = FakeWebSocket;
  globalThis.AudioContext = FakeAudioContext;
  globalThis.AudioWorkletNode = FakeAudioWorkletNode;
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: (...args) => globalThis.__aecGetUserMedia(...args),
      },
    },
  });
  globalThis.document = {
    createElement: () => ({ onload: null, onerror: null }),
    head: {
      appendChild(element) {
        queueMicrotask(() => element.onload?.());
      },
    },
  };
  globalThis.window = {
    vad: {
      MicVAD: {
        async new(options) {
          globalThis.__aecVadOptions.push(options);
          const stream = await options.getStream();
          globalThis.__aecStreamEvents.push(["getStream", stream]);
          await options.pauseStream(stream);
          globalThis.__aecStreamEvents.push(["pauseStream", stream]);
          const resumed = await options.resumeStream(stream);
          globalThis.__aecStreamEvents.push(["resumeStream", resumed]);
          return {
            start() {},
            pause() {},
            destroy() {
              this.destroyed = true;
            },
          };
        },
      },
    },
  };
}

installBrowserStubs();

const vadSource = stripImports(
  readFileSync(resolve(ROOT, "server/static/modules/voice-vad.js"), "utf8"),
);
const vadUrl = toDataUrl(vadSource, "voice-vad-e2e");
const micSource = stripImports(
  readFileSync(resolve(ROOT, "server/static/modules/voice-mic.js"), "utf8"),
);
const micUrl = toDataUrl(micSource, "voice-mic-e2e");
const voiceSource = stripImports(
  readFileSync(resolve(ROOT, "server/static/modules/voice.js"), "utf8"),
);
const voiceUrl = toDataUrl(
  `import { VoiceVAD } from "${vadUrl}";
import { acquireVoiceStream } from "${micUrl}";
const basePath = "";
const VoicePlayback = globalThis.__VoicePlayback;
${voiceSource}`,
  "voice-aec-e2e",
);

globalThis.__VoicePlayback = FakePlayback;
const { VoiceManager } = await import(voiceUrl);
const { VoiceVAD } = await import(vadUrl);

async function waitFor(predicate) {
  for (let i = 0; i < 50; i += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.fail("timed out waiting for voice state");
}

async function connectedVadManager(streams) {
  let calls = 0;
  globalThis.__aecGetUserMedia = async () => {
    const stream = streams[calls++];
    if (stream instanceof Error) throw stream;
    return stream;
  };
  const manager = new VoiceManager();
  await manager.connect("alice");
  manager.setMode("vad");
  await waitFor(() => manager._vad && globalThis.__aecVadOptions.length > 0);
  return {
    manager,
    socket: globalThis.__aecSockets.at(-1),
    options: globalThis.__aecVadOptions.at(-1),
  };
}

afterEach(() => {
  delete globalThis.__aecGetUserMedia;
  delete globalThis.__aecSockets;
  delete globalThis.__aecAudioSources;
  delete globalThis.__aecVadOptions;
  delete globalThis.__aecStreamEvents;
});

describe("voice AEC integration", () => {
  beforeEach(() => {
    globalThis.__aecSockets = [];
    globalThis.__aecAudioSources = [];
    globalThis.__aecVadOptions = [];
    globalThis.__aecStreamEvents = [];
  });

  it("shares one delayed MicVAD creation across concurrent starts", async () => {
    const originalNew = window.vad.MicVAD.new;
    let release;
    let resolveCalled;
    let newCalls = 0;
    const creationStarted = new Promise((resolve) => {
      resolveCalled = resolve;
    });
    const creationGate = new Promise((resolve) => {
      release = resolve;
    });
    const fakeVad = {
      async start() {},
      pause() {},
      destroy() {},
    };

    window.vad.MicVAD.new = async () => {
      newCalls += 1;
      resolveCalled();
      await creationGate;
      return fakeVad;
    };

    const vad = new VoiceVAD();
    try {
      const first = vad.start();
      const second = vad.start();
      await creationStarted;
      assert.equal(newCalls, 1);

      release();
      assert.deepEqual(await Promise.all([first, second]), [true, true]);
      assert.equal(newCalls, 1);
    } finally {
      vad.destroy();
      window.vad.MicVAD.new = originalNew;
    }
  });

  it("shares one AEC stream, interrupts TTS, starts recording, and stops its track", async () => {
    const stream = makeStream({ echoCancellation: "all" });
    const { manager, socket, options } = await connectedVadManager([stream]);

    assert.equal(manager._aecAll, true);
    manager._playback.aecActive = true;
    assert.equal(globalThis.__aecStreamEvents[0][0], "getStream");
    assert.strictEqual(globalThis.__aecStreamEvents[0][1], stream);
    assert.deepEqual(
      globalThis.__aecStreamEvents.map(([name, value]) => [name, value]),
      [
        ["getStream", stream],
        ["pauseStream", stream],
        ["resumeStream", stream],
      ],
    );
    assert.strictEqual(await options.getStream(), stream);

    manager._handleMessage({ data: JSON.stringify({ type: "tts_start" }) });
    options.onSpeechStart();
    await waitFor(() => manager.isRecording);

    assert.deepEqual(
      socket.sent.map((value) => JSON.parse(value)),
      [{ type: "config", vad_mode: "vad" }],
    );
    assert.strictEqual(globalThis.__aecAudioSources[0], stream);

    options.onSpeechRealStart();
    assert.deepEqual(
      socket.sent.map((value) => JSON.parse(value)),
      [
        { type: "config", vad_mode: "vad" },
        { type: "interrupt" },
      ],
    );

    manager.disconnect();
    assert.equal(stream.track.stopped, true);
  });

  it("keeps the first TTS half-duplex until playback AEC is ready", async () => {
    const stream = makeStream({ echoCancellation: "all" });
    const { manager, socket, options } = await connectedVadManager([stream]);

    assert.equal(manager._aecAll, true);
    manager._playback.aecActive = false;
    manager._handleMessage({ data: JSON.stringify({ type: "tts_start" }) });
    options.onSpeechStart();
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(manager.isRecording, false);
    assert.equal(globalThis.__aecAudioSources.length, 0);
    assert.deepEqual(
      socket.sent.map((value) => JSON.parse(value)),
      [{ type: "config", vad_mode: "vad" }],
    );

    manager._playback.aecActive = true;
    options.onSpeechStart();
    await waitFor(() => manager.isRecording);
    assert.deepEqual(
      socket.sent.map((value) => JSON.parse(value)),
      [{ type: "config", vad_mode: "vad" }],
    );

    options.onSpeechRealStart();
    assert.deepEqual(
      socket.sent.map((value) => JSON.parse(value)),
      [
        { type: "config", vad_mode: "vad" },
        { type: "interrupt" },
      ],
    );

    manager.disconnect();
    assert.equal(stream.track.stopped, true);
  });

  it("ignores VAD speech during TTS when echoCancellation=all is unavailable", async () => {
    const unsupported = Object.assign(new Error("AEC mode unsupported"), {
      name: "OverconstrainedError",
      constraint: "echoCancellation",
    });
    const stream = makeStream({ echoCancellation: true });
    const { manager, socket, options } = await connectedVadManager([unsupported, stream]);

    assert.equal(manager._aecAll, false);
    manager._handleMessage({ data: JSON.stringify({ type: "tts_start" }) });
    options.onSpeechStart();
    options.onSpeechRealStart();
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(manager.isRecording, false);
    assert.equal(globalThis.__aecAudioSources.length, 0);
    assert.deepEqual(
      socket.sent.map((value) => JSON.parse(value)),
      [{ type: "config", vad_mode: "vad" }],
    );
    manager.disconnect();
    assert.equal(stream.track.stopped, true);
  });
});
