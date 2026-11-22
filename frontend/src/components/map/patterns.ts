/** Small raster patterns drawn on a canvas (no external sprite server). */
export function hatchImage(color: string, bg = "rgba(0,0,0,0)", size = 12, width = 2): ImageData {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d")!;
  g.fillStyle = bg;
  g.fillRect(0, 0, size, size);
  g.strokeStyle = color;
  g.lineWidth = width;
  g.beginPath();
  for (let o = -size; o <= size; o += size / 2) {
    g.moveTo(o, size);
    g.lineTo(o + size, 0);
  }
  g.stroke();
  return g.getImageData(0, 0, size, size);
}

export function squareIcon(fill: string, stroke: string, size = 18): ImageData {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d")!;
  g.fillStyle = fill;
  g.strokeStyle = stroke;
  g.lineWidth = 2;
  g.beginPath();
  g.rect(3, 3, size - 6, size - 6);
  g.fill();
  g.stroke();
  // roof mark: shelter
  g.fillStyle = stroke;
  g.fillRect(size / 2 - 1, 6, 2, size - 12);
  g.fillRect(6, size / 2 - 1, size - 12, 2);
  return g.getImageData(0, 0, size, size);
}
