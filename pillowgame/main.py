import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageChops, ImageFilter, ImageOps
import math

# ------------------- Parâmetros ajustáveis -------------------
NUM_ERROS = 7

# detecção de cor
GREEN_THRESHOLD = 70    # valor absoluto mínimo no canal
BLUE_THRESHOLD = 70
DOMINANCE_DELTA = 30    # G - R > DOMINANCE_DELTA  OR  B - R > DOMINANCE_DELTA

# morfologia
DILATION_SIZE = 7       # MaxFilter size (ímpar). 1 = sem dilatação
EROSION_SIZE = 5        # MinFilter size (usado após dilatação para fechar - closing)
MIN_AREA = 80           # descarta regiões muito pequenas (ajuste)

MARGEM_RAIO = 12        # margem extra no raio do círculo

# Ajuste fino de posicionamento (valores pequenos)
SHIFT_X_FACTOR = 0.08
SHIFT_Y_FACTOR = 0.06

DEBUG_DRAW = False      # False: não desenha círculos automaticamente (usuário deve clicar)
# -------------------------------------------------------------

def gerar_diff():
    img1 = Image.open("source.png").convert("RGB")
    img2 = Image.open("target.png").convert("RGB")
    diff = ImageChops.difference(img1, img2)
    diff.save("diff_result.png")
    return diff

def criar_mascara_unida(diff):
    w, h = diff.size
    dpix = diff.load()

    mask_img = Image.new("L", (w, h), 0)
    m = mask_img.load()

    for x in range(w):
        for y in range(h):
            r, g, b = dpix[x, y]
            is_green = (g >= GREEN_THRESHOLD and (g - r) > DOMINANCE_DELTA)
            is_blue  = (b >= BLUE_THRESHOLD and (b - r) > DOMINANCE_DELTA)
            if is_green or is_blue:
                m[x, y] = 255
            else:
                m[x, y] = 0

    if DILATION_SIZE > 1:
        mask_img = mask_img.filter(ImageFilter.MaxFilter(DILATION_SIZE))
    if EROSION_SIZE > 1:
        mask_img = mask_img.filter(ImageFilter.MinFilter(EROSION_SIZE))

    return mask_img

def flood_fill_collect(mask_px, visited, start_x, start_y, w, h):
    stack = [(start_x, start_y)]
    visited[start_y][start_x] = True
    pixels = []
    while stack:
        x, y = stack.pop()
        pixels.append((x, y))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = x + dx
                ny = y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    if mask_px[nx, ny] > 0 and not visited[ny][nx]:
                        visited[ny][nx] = True
                        stack.append((nx, ny))
    return pixels

def detectar_regioes(diff, num=NUM_ERROS):
    w, h = diff.size
    mask_img = criar_mascara_unida(diff)
    mask_px = mask_img.load()
    visited = [[False]*w for _ in range(h)]
    regioes = []

    for y in range(h):
        for x in range(w):
            if mask_px[x, y] > 0 and not visited[y][x]:
                pixs = flood_fill_collect(mask_px, visited, x, y, w, h)
                if not pixs:
                    continue
                area = len(pixs)
                if area < MIN_AREA:
                    continue
                xs = [p[0] for p in pixs]
                ys = [p[1] for p in pixs]
                x1, x2 = min(xs), max(xs)
                y1, y2 = min(ys), max(ys)
                cx = sum(xs) / area
                cy = sum(ys) / area

                bbox_w = x2 - x1
                bbox_h = y2 - y1
                cx_adj = cx - SHIFT_X_FACTOR * bbox_w
                cy_adj = cy - SHIFT_Y_FACTOR * bbox_h

                regioes.append({
                    'pixels': pixs,
                    'centroid': (cx_adj, cy_adj),
                    'orig_centroid': (cx, cy),
                    'bbox': (x1, y1, x2, y2),
                    'area': area
                })

    regioes.sort(key=lambda r: r['area'], reverse=True)

    def centroid_distance(a, b):
        ax, ay = a['centroid']
        bx, by = b['centroid']
        return math.hypot(ax - bx, ay - by)

    while len(regioes) > num:
        min_d = None
        pair = (0, 1)
        n = len(regioes)
        for i in range(n):
            for j in range(i+1, n):
                d = centroid_distance(regioes[i], regioes[j])
                if min_d is None or d < min_d:
                    min_d = d
                    pair = (i, j)
        i, j = pair
        A = regioes[i]
        B = regioes[j]
        merged_pixels = A['pixels'] + B['pixels']
        area = len(merged_pixels)
        xs = [p[0] for p in merged_pixels]
        ys = [p[1] for p in merged_pixels]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        cx = sum(xs) / area
        cy = sum(ys) / area
        bbox_w = x2 - x1
        bbox_h = y2 - y1
        cx_adj = cx - SHIFT_X_FACTOR * bbox_w
        cy_adj = cy - SHIFT_Y_FACTOR * bbox_h
        merged = {
            'pixels': merged_pixels,
            'centroid': (cx_adj, cy_adj),
            'orig_centroid': (cx, cy),
            'bbox': (x1, y1, x2, y2),
            'area': area
        }
        regioes[i] = merged
        regioes.pop(j)
        regioes.sort(key=lambda r: r['area'], reverse=True)

    return regioes

def resolver_sobreposicoes(circulos, img_w, img_h, max_iter=10):
    # circulos: list of tuples (x, y, r) -> we will return adjusted list
    circ = [list(c) for c in circulos]  # mutable
    n = len(circ)
    for _ in range(max_iter):
        moved = False
        for i in range(n):
            xi, yi, ri = circ[i]
            for j in range(n):
                if i == j:
                    continue
                xj, yj, rj = circ[j]
                dx = xi - xj
                dy = yi - yj
                d = math.hypot(dx, dy)
                if d == 0:
                    # empurra levemente aleatoriamente (fixo)
                    dx = 1.0
                    dy = 0.5
                    d = math.hypot(dx, dy)
                # overlap amount (positive if overlapping)
                overlap = (ri + rj) - d
                # só agir quando há sobreposição significativa e um é bem maior
                if overlap > 10 and (ri > 1.2 * rj or rj > 1.2 * ri):
                    # determine smaller/bigger
                    if ri < rj:
                        small_idx = i
                        big_idx = j
                        sx, sy, sr = xi, yi, ri
                        bx, by, br = xj, yj, rj
                        vx = sx - bx
                        vy = sy - by
                    else:
                        small_idx = j
                        big_idx = i
                        sx, sy, sr = xj, yj, rj
                        bx, by, br = xi, yi, ri
                        vx = sx - bx
                        vy = sy - by
                    # normalize vector
                    mag = math.hypot(vx, vy)
                    if mag == 0:
                        vx, vy = 1.0, 0.0
                        mag = 1.0
                    nx = vx / mag
                    ny = vy / mag
                    # desired shift: overlap + a small margin
                    shift = overlap + 12
                    new_x = sx + nx * shift
                    new_y = sy + ny * shift
                    # clamp inside image
                    new_x = max(sr, min(img_w - sr - 1, new_x))
                    new_y = max(sr, min(img_h - sr - 1, new_y))
                    # apply
                    if ri < rj:
                        circ[small_idx][0] = int(round(new_x))
                        circ[small_idx][1] = int(round(new_y))
                    else:
                        circ[small_idx][0] = int(round(new_x))
                        circ[small_idx][1] = int(round(new_y))
                    moved = True
        if not moved:
            break
    # return as list of tuples
    return [tuple(map(int, c)) for c in circ]

class Jogo7Erros:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Jogo dos 7 Erros")
        self.root.geometry("1315x500")
        self.root.resizable(True, True)

        self.img_left = Image.open("source.png")
        self.img_right = Image.open("target.png")
        self.tk_left = ImageTk.PhotoImage(self.img_left)
        self.tk_right = ImageTk.PhotoImage(self.img_right)

        self.canvas_left = tk.Canvas(self.root, width=self.img_left.width, height=self.img_left.height)
        self.canvas_left.grid(row=0, column=0, padx=10, pady=10)
        self.canvas_left.create_image(0,0,anchor="nw", image=self.tk_left)

        self.canvas_right = tk.Canvas(self.root, width=self.img_right.width, height=self.img_right.height)
        self.canvas_right.grid(row=0, column=1, padx=10, pady=10)
        self.canvas_right.create_image(0,0,anchor="nw", image=self.tk_right)

        self.canvas_left.bind("<Button-1>", self.clique)
        self.canvas_right.bind("<Button-1>", self.clique)

        frame = tk.Frame(self.root)
        frame.grid(row=1, column=0, columnspan=2, pady=8)
        tk.Button(frame, text="Revelar diferenças", command=self.revelar).grid(row=0, column=0, padx=8)
        tk.Button(frame, text="Reiniciar", command=self.reiniciar).grid(row=0, column=1, padx=8)

        diff = gerar_diff()
        regioes = detectar_regioes(diff, num=NUM_ERROS)

        # cria a lista inicial de circulos (cx, cy, raio)
        temp_circulos = []
        for r in regioes:
            x1, y1, x2, y2 = r['bbox']
            cx, cy = r['centroid']
            raio = max((x2 - x1), (y2 - y1)) / 2.0 + MARGEM_RAIO
            temp_circulos.append((int(round(cx)), int(round(cy)), int(math.ceil(raio))))

        # resolve sobreposições movendo círculos pequenos para fora dos grandes
        w_img, h_img = self.img_left.width, self.img_left.height
        self.circulos = resolver_sobreposicoes(temp_circulos, w_img, h_img)

        self.acertos = []

        if DEBUG_DRAW:
            for (cx, cy, r) in self.circulos:
                self.canvas_left.create_oval(cx-r, cy-r, cx+r, cy+r, outline="yellow", width=2)
                self.canvas_right.create_oval(cx-r, cy-r, cx+r, cy+r, outline="yellow", width=2)

        self.root.mainloop()

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
