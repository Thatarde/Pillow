import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageChops, ImageFilter
import math

# Configurações
NUM_ERROS = 7
GREEN_THRESHOLD = 70
BLUE_THRESHOLD = 70
DOMINANCE_DELTA = 30
DILATION_SIZE = 7
EROSION_SIZE = 5
MIN_AREA = 80
MARGEM_RAIO = 12
SHIFT_X_FACTOR = 0.08
SHIFT_Y_FACTOR = 0.06
DEBUG_DRAW = False

def gerar_diff():
    img1 = Image.open("source.png").convert("RGB")
    img2 = Image.open("target.png").convert("RGB")
    diff = ImageChops.difference(img1, img2)
    diff.save("diff_result.png")
    return diff

def criar_mascara(diff):
    w, h = diff.size
    mask_img = Image.new("L", (w, h))
    m = mask_img.load()
    dpix = diff.load()
    
    for x in range(w):
        for y in range(h):
            r, g, b = dpix[x, y]
            is_green = (g >= GREEN_THRESHOLD and (g - r) > DOMINANCE_DELTA)
            is_blue = (b >= BLUE_THRESHOLD and (b - r) > DOMINANCE_DELTA)
            m[x, y] = 255 if is_green or is_blue else 0

    if DILATION_SIZE > 1:
        mask_img = mask_img.filter(ImageFilter.MaxFilter(DILATION_SIZE))
    if EROSION_SIZE > 1:
        mask_img = mask_img.filter(ImageFilter.MinFilter(EROSION_SIZE))

    return mask_img

def flood_fill(mask_px, visited, start_x, start_y, w, h):
    stack = [(start_x, start_y)]
    visited[start_y][start_x] = True
    pixels = []
    
    while stack:
        x, y = stack.pop()
        pixels.append((x, y))
        for dx, dy in [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and mask_px[nx, ny] > 0 and not visited[ny][nx]:
                visited[ny][nx] = True
                stack.append((nx, ny))
    return pixels

def detectar_regioes(diff):
    w, h = diff.size
    mask_img = criar_mascara(diff)
    mask_px = mask_img.load()
    visited = [[False] * w for _ in range(h)]
    regioes = []

    for y in range(h):
        for x in range(w):
            if mask_px[x, y] > 0 and not visited[y][x]:
                pixs = flood_fill(mask_px, visited, x, y, w, h)
                if len(pixs) < MIN_AREA:
                    continue
                    
                xs = [p[0] for p in pixs]
                ys = [p[1] for p in pixs]
                x1, x2 = min(xs), max(xs)
                y1, y2 = min(ys), max(ys)
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)

                bbox_w = x2 - x1
                bbox_h = y2 - y1
                cx_adj = cx - SHIFT_X_FACTOR * bbox_w
                cy_adj = cy - SHIFT_Y_FACTOR * bbox_h

                regioes.append({
                    'centroid': (cx_adj, cy_adj),
                    'bbox': (x1, y1, x2, y2),
                    'area': len(pixs)
                })

    regioes.sort(key=lambda r: r['area'], reverse=True)

    # Manter apenas NUM_ERROS regiões, mesclando as mais próximas
    while len(regioes) > NUM_ERROS:
        min_d = float('inf')
        pair = (0, 1)
        
        for i in range(len(regioes)):
            for j in range(i + 1, len(regioes)):
                ax, ay = regioes[i]['centroid']
                bx, by = regioes[j]['centroid']
                d = math.hypot(ax - bx, ay - by)
                if d < min_d:
                    min_d = d
                    pair = (i, j)
                    
        i, j = pair
        A, B = regioes[i], regioes[j]
        
        # Mesclar regiões
        x1 = min(A['bbox'][0], B['bbox'][0])
        y1 = min(A['bbox'][1], B['bbox'][1])
        x2 = max(A['bbox'][2], B['bbox'][2])
        y2 = max(A['bbox'][3], B['bbox'][3])
        
        cx = (A['centroid'][0] + B['centroid'][0]) / 2
        cy = (A['centroid'][1] + B['centroid'][1]) / 2
        bbox_w = x2 - x1
        bbox_h = y2 - y1
        
        cx_adj = cx - SHIFT_X_FACTOR * bbox_w
        cy_adj = cy - SHIFT_Y_FACTOR * bbox_h

        regioes[i] = {
            'centroid': (cx_adj, cy_adj),
            'bbox': (x1, y1, x2, y2),
            'area': A['area'] + B['area']
        }
        regioes.pop(j)

    return regioes

class Jogo7Erros:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Jogo dos 7 Erros")
        self.root.geometry("1315x500")

        self.img_left = Image.open("source.png")
        self.img_right = Image.open("target.png")
        
        self._setup_ui()
        self._setup_game()
        
        self.root.mainloop()

    def _setup_ui(self):
        self.tk_left = ImageTk.PhotoImage(self.img_left)
        self.tk_right = ImageTk.PhotoImage(self.img_right)

        self.canvas_left = tk.Canvas(self.root, width=self.img_left.width, height=self.img_left.height)
        self.canvas_left.grid(row=0, column=0, padx=10, pady=10)
        self.canvas_left.create_image(0, 0, anchor="nw", image=self.tk_left)

        self.canvas_right = tk.Canvas(self.root, width=self.img_right.width, height=self.img_right.height)
        self.canvas_right.grid(row=0, column=1, padx=10, pady=10)
        self.canvas_right.create_image(0, 0, anchor="nw", image=self.tk_right)

        self.canvas_left.bind("<Button-1>", self.clique)
        self.canvas_right.bind("<Button-1>", self.clique)

        frame = tk.Frame(self.root)
        frame.grid(row=1, column=0, columnspan=2, pady=8)
        tk.Button(frame, text="Revelar diferenças", command=self.revelar).grid(row=0, column=0, padx=8)
        tk.Button(frame, text="Reiniciar", command=self.reiniciar).grid(row=0, column=1, padx=8)

    def _setup_game(self):
        diff = gerar_diff()
        regioes = detectar_regioes(diff)

        # Criar círculos nas posições originais detectadas
        self.circulos = []
        for r in regioes:
            x1, y1, x2, y2 = r['bbox']
            cx, cy = r['centroid']
            raio = max(x2 - x1, y2 - y1) / 2 + MARGEM_RAIO
            self.circulos.append((int(cx), int(cy), int(raio)))

        self.acertos = []

        if DEBUG_DRAW:
            for cx, cy, r in self.circulos:
                self.canvas_left.create_oval(cx-r, cy-r, cx+r, cy+r, outline="yellow", width=2)
                self.canvas_right.create_oval(cx-r, cy-r, cx+r, cy+r, outline="yellow", width=2)

    def clique(self, event):
        x, y = event.x, event.y
        for i, (cx, cy, r) in enumerate(self.circulos):
            if i in self.acertos:
                continue
            if (x - cx)**2 + (y - cy)**2 <= r**2:
                self.acertos.append(i)
                self.canvas_left.create_oval(cx-r, cy-r, cx+r, cy+r, outline="red", width=3)
                self.canvas_right.create_oval(cx-r, cy-r, cx+r, cy+r, outline="red", width=3)
                if len(self.acertos) == NUM_ERROS:
                    messagebox.showinfo("Parabéns!", "Você encontrou todos os 7 erros!")
                return

    def revelar(self):
        Image.open("diff_result.png").show()

    def reiniciar(self):
        self.root.destroy()
        Jogo7Erros()

if __name__ == "__main__":
    Jogo7Erros()