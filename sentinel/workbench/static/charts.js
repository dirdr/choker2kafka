export function drawChart(canvas, samples, key, color, fixedMax) {
  if (!canvas) return;
  const width = canvas.clientWidth || 420;
  const height = 75;
  const scale = window.devicePixelRatio || 1;
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.scale(scale, scale);
  const values = samples.filter((sample) => Number.isFinite(sample[key]));
  const max =
    fixedMax || Math.max(1, ...values.map((sample) => sample[key])) * 1.2;
  ctx.strokeStyle = "#343942";
  ctx.lineWidth = 0.5;
  for (const y of [8, height / 2, height - 8]) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  ctx.font = "9px monospace";
  ctx.fillStyle = "#9ba3af";
  ctx.fillText(String(Math.round(max)), 2, 8);
  ctx.fillText("0", 2, height - 1);
  if (values.length < 2) {
    ctx.fillText("Collecting live samples…", 35, height / 2 - 6);
    return;
  }
  const first = samples[0].at;
  const span = Math.max(5000, samples.at(-1).at - first);
  ctx.beginPath();
  let continuing = false;
  for (const sample of samples) {
    if (!Number.isFinite(sample[key])) {
      continuing = false;
      continue;
    }
    const x = 30 + ((sample.at - first) / span) * (width - 34);
    const y = height - 8 - (sample[key] / max) * (height - 18);
    if (continuing) ctx.lineTo(x, y);
    else ctx.moveTo(x, y);
    continuing = true;
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.7;
  ctx.stroke();
}
