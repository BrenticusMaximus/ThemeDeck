// Logarithmic bands give bass, mids and treble useful space in a small display.
export const spectrumHeights = (data: Uint8Array, sampleRate: number, fftSize: number, count: number): number[] => {
  const lowHz = 40;
  const highHz = Math.min(16000, sampleRate / 2);
  const hzPerBin = sampleRate / fftSize;
  return Array.from({ length: count }, (_, i) => {
    const start = Math.max(1, Math.floor(lowHz * Math.pow(highHz / lowHz, i / count) / hzPerBin));
    const end = Math.min(data.length, Math.max(start + 1, Math.ceil(lowHz * Math.pow(highHz / lowHz, (i + 1) / count) / hzPerBin)));
    let sum = 0;
    for (let bin = start; bin < end; bin += 1) sum += Math.pow(data[bin] / 255, 2);
    const level = end > start ? Math.sqrt(sum / (end - start)) : 0;
    return 0.08 + Math.min(1, level) * 0.92;
  });
};

// Fast attack follows notes; slower release keeps motion readable without a CSS delay.
export const smoothHeights = (previous: number[], target: number[], elapsedMs: number): number[] =>
  target.map((value, i) => {
    const old = previous[i] ?? 0.08;
    const timeConstant = value > old ? 35 : 150;
    return old + (value - old) * (1 - Math.exp(-elapsedMs / timeConstant));
  });
