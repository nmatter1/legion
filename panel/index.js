const canvas = document.getElementById("map");
const ctx = canvas.getContext("2d");

const tileSize = 32;
const gridSize = 1;
const tileset = new Image();
tileset.src = "tileset.png";

let offsetX = 0, offsetY = 0;
let isDragging = false;
let lastX, lastY;
const mapData = [
  [1, 1, 1, 1, 1],
  [1, 0, 0, 0, 1],
  [1, 0, 2, 0, 1],
  [1, 0, 0, 0, 1],
  [1, 1, 1, 1, 1]
];
tileset.onload = () => drawGrid();
// Handle mouse drag for panning
canvas.addEventListener("mousedown", (e) => {
    isDragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
});

canvas.addEventListener("mousemove", (e) => {
    if (isDragging) {
        offsetX += e.clientX - lastX;
        offsetY += e.clientY - lastY;
        lastX = e.clientX;
        lastY = e.clientY;
        drawGrid();
    }
});

canvas.addEventListener("mouseup", () => isDragging = false);
canvas.addEventListener("mouseleave", () => isDragging = false);

function drawGrid() {
   ctx.clearRect(0, 0, canvas.width, canvas.height)
   // tileset, sx, sy, sWidth, sHeight, dx, dy, dWidth, dHeight
   for (let i = 0; i < 16; i++) {
      const col = 1
      const row = 3
      const gap = 4
      const sx = 0 + gap * col + tileSize * col
      const sy = 40 + gap * row + tileSize * row
      const dx = offsetX + tileSize 
      const dy = offsetY + tileSize
      ctx.drawImage(tileset, sx, sy, tileSize, tileSize, dx, dy, tileSize, tileSize);
   }
}
