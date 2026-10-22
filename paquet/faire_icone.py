"""Dessine l'icône de Root : fond sombre, lueur verte, l'oreillette pixel.
Reprend l'identité de l'app (vert #3f9d84, le sceau de la fenêtre)."""
import sys
from PIL import Image, ImageDraw, ImageFilter

N = 1024
OREILLETTE = [
    "................", "...oooo....L....", "..owwhho....L...", ".ouuwwwwo.L..L..",
    ".ouuwwLLo..L..L.", ".owwwwLLo..L..L.", "..owwwwso.L..L..", "...owwwso...L...",
    "....owso........", "....owso........", "....owso........", "....owso........",
    "....owso........", "....owso........", ".....oo.........", "................",
]
TEINTES = {"o": (138,138,150), "w": (216,216,222), "h": (255,255,255),
           "s": (174,174,184), "u": (62,62,72), "L": (111,212,182)}

def squircle(taille, rayon):
    m = Image.new("L", (taille, taille), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, taille-1, taille-1], radius=rayon, fill=255)
    return m

img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
# fond : dégradé sombre vertical
fond = Image.new("RGBA", (N, N))
for y in range(N):
    t = y / N
    r = int(16 + 6*t); g = int(26 + 10*(1-t)); b = int(22 + 8*(1-t))
    for x in range(0, N, 1):
        pass
    fond.paste((r, g, b, 255), [0, y, N, y+1])
# lueur verte en haut
glow = Image.new("RGBA", (N, N), (0, 0, 0, 0))
dg = ImageDraw.Draw(glow)
dg.ellipse([N*0.12, -N*0.25, N*0.88, N*0.55], fill=(63, 157, 132, 150))
glow = glow.filter(ImageFilter.GaussianBlur(120))
fond = Image.alpha_composite(fond, glow)

# l'oreillette, centrée, ~58% de l'icône
p = int(N * 0.58 / 16)
ox = (N - p*16) // 2
oy = (N - p*16) // 2
oreille = Image.new("RGBA", (N, N), (0, 0, 0, 0))
do = ImageDraw.Draw(oreille)
for yy in range(16):
    for xx in range(16):
        c = TEINTES.get(OREILLETTE[yy][xx])
        if c:
            x0 = ox + xx*p; y0 = oy + yy*p
            do.rectangle([x0, y0, x0+p-1, y0+p-1], fill=c + (255,))
# halo vert derrière l'oreillette
halo = oreille.filter(ImageFilter.GaussianBlur(26))
fond = Image.alpha_composite(fond, halo)
fond = Image.alpha_composite(fond, oreille)

# masque squircle façon macOS
masque = squircle(N, int(N*0.225))
img.paste(fond, (0, 0), masque)
# liseré clair subtil
bord = Image.new("RGBA", (N, N), (0, 0, 0, 0))
db = ImageDraw.Draw(bord)
db.rounded_rectangle([3, 3, N-4, N-4], radius=int(N*0.225)-3, outline=(255, 255, 255, 40), width=4)
img = Image.alpha_composite(img, Image.composite(bord, Image.new("RGBA",(N,N),(0,0,0,0)), masque))

img.save(sys.argv[1])
print("icône écrite:", sys.argv[1])
