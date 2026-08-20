const AUDIO_CONSTRAINTS = {
  sampleRate: 48000,
  channelCount: 1,
  noiseSuppression: true,
  autoGainControl: true,
};

function isEchoAllUnsupported(err) {
  return (
    (err?.name === 'OverconstrainedError' &&
      (!err.constraint || err.constraint === 'echoCancellation')) ||
    (err?.name === 'TypeError' && /echoCancellation|constraint/i.test(err?.message || ''))
  );
}

export async function acquireVoiceStream() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { ...AUDIO_CONSTRAINTS, echoCancellation: { exact: 'all' } },
    });
  } catch (err) {
    if (!isEchoAllUnsupported(err)) throw err;
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { ...AUDIO_CONSTRAINTS, echoCancellation: true },
    });
    return { stream, aecAll: false };
  }

  if (stream.getAudioTracks()[0]?.getSettings?.().echoCancellation === 'all') {
    return { stream, aecAll: true };
  }

  stream.getTracks().forEach((track) => track.stop());
  stream = await navigator.mediaDevices.getUserMedia({
    audio: { ...AUDIO_CONSTRAINTS, echoCancellation: true },
  });
  return { stream, aecAll: false };
}
