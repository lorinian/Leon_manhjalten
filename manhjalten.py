"""
MÅNHJÄLTEN
==========
Ett 3D-spel där du springer runt på månen och jagar aliens
som försöker gömma sig bakom sina rymdskepp.
Skjut tillräckligt många gånger på ett skepp så sprängs det!

Styrning:
    W A S D      springa
    Shift        spurta
    Mellanslag   skjuta
    E            hoppa (låg gravitation!)
    Piltangenter vända och titta upp/ner
    Esc          paus

Musen används inte i spelet, så du kan alltid flytta fönstret.
    R            spela igen (när spelet är slut)

Starta:  .venv/bin/python manhjalten.py
"""

import math
import os
import random
import struct
import wave
from pathlib import Path

# I WSL (Linux i Windows) måste vi be om grafikkortet, annars blir spelet jättesegt
if os.path.exists('/usr/lib/wsl/lib') and 'GALLIUM_DRIVER' not in os.environ:
    os.environ['GALLIUM_DRIVER'] = 'd3d12'

from panda3d.core import TransparencyAttrib
from PIL import Image, ImageDraw, ImageFilter
from ursina import (Audio, DirectionalLight, Entity, Mesh, Shader, Text, Texture, Ursina, Vec2, Vec3,
                    camera, color, curve, destroy, held_keys, invoke, lerp, time, window)
from ursina.shaders import unlit_shader

MAPP = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Inställningar – testa att ändra dem!
# ---------------------------------------------------------------------------
BANANS_RADIE = 105        # hur långt ut man får springa
GRAVITATION = 5.0         # månen har låg gravitation
HOPPKRAFT = 6.5
GA_FART = 8.0
SPURT_FART = 13.0
ALIEN_FART = 6.0
ALIEN_PANIK_FART = 9.5
SKOTT_FART = 90.0
SKJUT_PAUS = 0.16         # sekunder mellan skotten
SIKTHJALP = 12            # grader: så nära siktet måste en alien vara för att skotten ska styra dit (0 = av)
VRID_FART = 120           # grader per sekund med piltangenterna (höger/vänster)
START_TID = 60            # sekunder man alltid får varje våg
TID_PER_ALIEN = 10        # extra sekunder för varje alien i vågen
TITT_FART = 60            # grader per sekund med piltangenterna (upp/ner)
SKEPP_ANTAL = 8           # så många rymdskepp finns på månen i början av varje våg
SKEPP_LIV = 20            # så många skott tål ett rymdskepp innan det exploderar

# Färger – mörkt och neon
NEON = color.rgb(0.0, 0.95, 1.0)
DRAKT_SVART = color.rgb(0.07, 0.075, 0.09)
DRAKT_GRA = color.rgb(0.18, 0.19, 0.22)
ALIEN_GRON = color.rgb(0.25, 0.75, 0.2)
ALIEN_GLOD = color.rgb(0.55, 1.0, 0.2)
ALIEN_LILA = color.rgb(0.9, 0.2, 1.0)
SKEPP_METALL = color.rgb(0.32, 0.33, 0.37)


app = Ursina(title='Månhjälten', borderless=False, development_mode=False, size=(1280, 720))
window.color = color.black
window.fps_counter.enabled = False
window.exit_button.visible = False
camera.fov = 75
camera.clip_plane_far = 2000
Texture.default_filtering = 'mipmap'


# ---------------------------------------------------------------------------
# En egen ljus-shader: mörka skuggor, kantljus och lite dimma långt bort
# ---------------------------------------------------------------------------
LJUS_STRUCT = '''
uniform struct {
    vec4 position; vec3 color; vec3 attenuation; vec3 spotDirection;
    float spotCosCutoff; float spotExponent;
    sampler2DShadow shadowMap; mat4 shadowViewMatrix;
} p3d_LightSource[1];
'''

man_shader = Shader(language=Shader.GLSL, name='man_shader', vertex='''#version 150
''' + LJUS_STRUCT + '''
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat3 p3d_NormalMatrix;
in vec4 vertex;
in vec3 normal;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;
uniform vec2 texture_scale;
uniform vec2 texture_offset;
out vec2 texcoords;
out vec4 vertex_color;
out vec3 view_pos;
out vec3 view_normal;
out vec4 shadow_coord;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * vertex;
    view_pos = vec3(p3d_ModelViewMatrix * vertex);
    view_normal = normalize(p3d_NormalMatrix * normal);
    shadow_coord = p3d_LightSource[0].shadowViewMatrix * vec4(view_pos, 1.0);
    texcoords = p3d_MultiTexCoord0 * texture_scale + texture_offset;
    vertex_color = p3d_Color;
}
''', fragment='''#version 150
''' + LJUS_STRUCT + '''
uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
uniform vec3 ambient;
uniform vec3 rim_color;
uniform vec4 fog_color;
uniform float fog_density;
uniform float shadow_bias;
uniform float specular;
in vec2 texcoords;
in vec4 vertex_color;
in vec3 view_pos;
in vec3 view_normal;
in vec4 shadow_coord;
out vec4 fragment_color;
void main() {
    vec4 base = texture(p3d_Texture0, texcoords) * p3d_ColorScale * vertex_color;
    vec3 N = normalize(view_normal);
    vec3 V = normalize(-view_pos);
    if (dot(N, V) < 0.0) N = -N;
    vec3 L = normalize(p3d_LightSource[0].position.xyz);

    vec4 c = shadow_coord;
    c.z -= shadow_bias * c.w;
    float shadow = textureProj(p3d_LightSource[0].shadowMap, c);

    vec3 sun = p3d_LightSource[0].color;
    float diff = max(dot(N, L), 0.0) * shadow;
    vec3 H = normalize(L + V);
    float spec = pow(max(dot(N, H), 0.0), 48.0) * shadow * specular;
    float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);

    vec3 col = base.rgb * (ambient + sun * diff) + sun * spec + rim_color * rim;
    float dist = length(view_pos);
    float f = 1.0 - exp(-pow(dist * fog_density, 2.0));
    col = mix(col, fog_color.rgb, clamp(f, 0.0, 1.0));
    fragment_color = vec4(col, base.a);
}
''', default_input={
    'texture_scale': Vec2(1, 1),
    'texture_offset': Vec2(0, 0),
    'ambient': Vec3(0.10, 0.11, 0.16),
    'rim_color': Vec3(0.05, 0.10, 0.18),
    'fog_color': color.rgba(0.01, 0.012, 0.025, 1),
    'fog_density': 0.0065,
    'shadow_bias': 0.0015,
    'specular': 0.25,
})
Entity.default_shader = man_shader


def glodande(model, farg, **kw):
    """En del som lyser själv (påverkas inte av ljus och skuggor)."""
    return Entity(model=model, color=farg, shader=unlit_shader, **kw)


class Grupp(Entity):
    """
    Många små delar som slås ihop till två modeller: en belyst och en lysande.
    Det gör att datorn bara behöver rita två saker istället för femtio,
    så spelet går mycket snabbare.
    """
    def __init__(self, **kw):
        super().__init__(**kw)
        self.lit = Entity(parent=self)
        self.glod = Entity(parent=self, shader=unlit_shader)

    def del_av(self, model, farg, glod=False, **kw):
        return Entity(parent=self.glod if glod else self.lit, model=model, color=farg, **kw)

    def sla_ihop(self):
        if self.lit.children:
            self.lit.combine(include_normals=True)
        if self.glod.children:
            self.glod.combine()
            self.glod.shader = unlit_shader
            self.glod.setTransparency(TransparencyAttrib.M_alpha)
        return self


# ---------------------------------------------------------------------------
# Ljud – vi tillverkar egna små ljudeffekter med matematik
# ---------------------------------------------------------------------------
def skapa_ljud():
    mapp = MAPP / 'ljud'
    mapp.mkdir(exist_ok=True)
    rate = 22050

    def spara(namn, prover):
        fil = mapp / f'{namn}.wav'
        if fil.exists():
            return
        with wave.open(str(fil), 'w') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, s)) * 30000)) for s in prover))

    def svep(tid, f0, f1, brus=0.0, form='fyrkant', volym=0.5):
        prover, fas = [], 0.0
        n = int(rate * tid)
        for i in range(n):
            t = i / n
            fas += (f0 + (f1 - f0) * t) / rate
            if form == 'fyrkant':
                v = 1.0 if (fas % 1) < 0.5 else -1.0
            else:
                v = math.sin(fas * math.tau)
            v = v * (1 - brus) + random.uniform(-1, 1) * brus
            prover.append(v * volym * (1 - t) ** 2)
        return prover

    spara('laser', svep(0.17, 1700, 260, brus=0.05, volym=0.35))
    spara('traff', [a + b for a, b in zip(svep(0.35, 250, 1300, form='sinus', volym=0.6),
                                          svep(0.35, 80, 40, brus=0.9, volym=0.5))])
    spara('hopp', svep(0.25, 180, 520, form='sinus', volym=0.4))
    melodi = []
    for ton in (523, 659, 784, 1047):
        melodi += svep(0.13, ton, ton, volym=0.25)
    spara('vag', melodi)
    spara('pip', svep(0.12, 900, 1400, form='sinus', volym=0.25))
    spara('boom', [a + b for a, b in zip(svep(1.2, 90, 25, brus=0.85, volym=0.9),
                                         svep(1.2, 60, 30, form='sinus', volym=0.6))])
    spara('klonk', svep(0.08, 420, 180, brus=0.4, volym=0.3))


skapa_ljud()


class Ljud:
    """Håller några kopior av varje ljud så att de kan spelas samtidigt."""
    def __init__(self, namn, antal=4, volym=1.0):
        self.kopior = [Audio(MAPP / 'ljud' / f'{namn}.wav', autoplay=False, auto_destroy=False, volume=volym)
                       for _ in range(antal)]
        self.i = 0

    def spela(self, tonhojd=1.0):
        a = self.kopior[self.i]
        self.i = (self.i + 1) % len(self.kopior)
        a.pitch = tonhojd
        a.play()


ljud_laser = Ljud('laser', 6, 0.6)
ljud_traff = Ljud('traff', 4, 0.8)
ljud_hopp = Ljud('hopp', 2, 0.6)
ljud_vag = Ljud('vag', 1, 0.7)
ljud_pip = Ljud('pip', 3, 0.5)
ljud_boom = Ljud('boom', 2, 1.0)
ljud_klonk = Ljud('klonk', 4, 0.5)


# ---------------------------------------------------------------------------
# Texturer gjorda med kod
# ---------------------------------------------------------------------------
def somlost_brus(storlek, grov, styrka):
    """Brus som går att lägga kant i kant utan skarvar."""
    liten = Image.effect_noise((grov, grov), styrka).convert('L')
    stor = Image.new('L', (grov * 3, grov * 3))
    for x in range(3):
        for y in range(3):
            stor.paste(liten, (x * grov, y * grov))
    stor = stor.resize((storlek * 3, storlek * 3), Image.BICUBIC)
    return stor.crop((storlek, storlek, storlek * 2, storlek * 2))


def mantextur():
    s = 512
    bild = somlost_brus(s, 16, 60)
    bild = Image.blend(bild, somlost_brus(s, 64, 50), 0.5)
    bild = Image.blend(bild, Image.effect_noise((s, s), 45).convert('L'), 0.3)
    rita = ImageDraw.Draw(bild)
    for _ in range(70):
        x, y = random.randrange(s), random.randrange(s)
        r = random.choice([2, 3, 4, 6, 9, 14])
        for dx in (-s, 0, s):
            for dy in (-s, 0, s):
                rita.ellipse((x + dx - r, y + dy - r, x + dx + r, y + dy + r), fill=95)
                rita.ellipse((x + dx - r * .75, y + dy - r * .75 + r * .2,
                              x + dx + r * .75, y + dy + r * .75 + r * .2), fill=75)
    bild = bild.filter(ImageFilter.GaussianBlur(0.8))
    rgb = Image.merge('RGB', (bild, bild, bild.point(lambda v: min(255, int(v * 1.06)))))
    return Texture(rgb)


def jordtextur():
    s = 256
    bild = Image.new('RGB', (s, s), (20, 60, 150))
    land = somlost_brus(s, 8, 90)
    moln = somlost_brus(s, 16, 90)
    px, lp, mp = bild.load(), land.load(), moln.load()
    for x in range(s):
        for y in range(s):
            if lp[x, y] > 150:
                px[x, y] = (40, 110, 50) if lp[x, y] < 185 else (130, 120, 70)
            if mp[x, y] > 165:
                px[x, y] = (230, 235, 245)
    return Texture(bild)


# ---------------------------------------------------------------------------
# Rymden: stjärnor, jorden och ljuset från solen
# ---------------------------------------------------------------------------
himmel = Entity()
for antal, tjocklek, ljushet in ((1400, 1.5, 0.55), (300, 2.5, 0.85), (60, 3.5, 1.0)):
    punkter, farger = [], []
    for _ in range(antal):
        v = Vec3(random.gauss(0, 1), abs(random.gauss(0, 1)) * 0.9 + 0.02, random.gauss(0, 1)).normalized()
        punkter.append(v * 900)
        t = random.random()
        farger.append(color.rgb(ljushet * (0.8 + 0.2 * t), ljushet * 0.9, ljushet * (1.0 - 0.15 * t)))
    Entity(parent=himmel, model=Mesh(vertices=punkter, colors=farger, mode='point', thickness=tjocklek),
           shader=unlit_shader)

JORD_RIKTNING = Vec3(-0.55, 0.42, 0.72).normalized()
jorden = Entity(parent=himmel, model='sphere', texture=jordtextur(), scale=110,
                position=JORD_RIKTNING * 800, rotation=(20, 40, 15), shader=unlit_shader)
Entity(parent=jorden, model='sphere', scale=1.08, color=color.rgba(0.3, 0.6, 1.0, 0.22), shader=unlit_shader)
# Jordens skuggsida (så att den ser ut som en skära)
Entity(parent=himmel, model='sphere', scale=112, color=color.rgba(0, 0, 0, 0.88), shader=unlit_shader,
       position=JORD_RIKTNING * 800 + Vec3(-35, -10, -5))
himmel.hide(0b0001)   # stjärnor och jorden ska inte kasta skuggor

sol = DirectionalLight(shadow_map_resolution=Vec2(1024, 1024), color=color.rgb(1.35, 1.3, 1.25))
sol.look_at(Vec3(0.6, -0.45, 0.65))


# ---------------------------------------------------------------------------
# Månens yta: mark, kratrar, stenar och berg vid horisonten
# ---------------------------------------------------------------------------
MANTEXTUR = mantextur()
mark = Entity(model='plane', scale=(700, 1, 700), texture=MANTEXTUR, texture_scale=(45, 45),
              color=color.rgb(0.62, 0.62, 0.66))
mark.set_shader_input('specular', 0.0)

kratrar = []      # (x, z, radie, kanthöjd)
krater_grupp = Entity()
sten_grupp = Entity()


def krater_profil(d, h):
    """Höjden i en krater på avståndet d (0 = mitten, 1 = kanten)."""
    if d < 1.0:
        return 0.03 + (h - 0.03) * d ** 3
    if d < 1.6:
        return h * (1 - (d - 1) / 0.6) ** 2
    return 0.0


def bygg_krater(x, z, r, h):
    varv, ringar = 28, 14
    verts, tris, uvs, normaler = [], [], [], []
    for i in range(ringar + 1):
        d = 1.6 * i / ringar
        # Lutningen i den här ringen bestämmer åt vilket håll ytan pekar
        lutning = (krater_profil(d + 0.01, h) - krater_profil(max(0, d - 0.01), h)) / ((0.01 + min(d, 0.01)) * r)
        for j in range(varv):
            a = math.tau * j / varv
            verts.append(Vec3(math.cos(a) * d * r, krater_profil(d, h), math.sin(a) * d * r))
            uvs.append(Vec2((x + math.cos(a) * d * r) / 15, (z + math.sin(a) * d * r) / 15))
            normaler.append(Vec3(-math.cos(a) * lutning, 1, -math.sin(a) * lutning).normalized())
    for i in range(ringar):
        for j in range(varv):
            a = i * varv + j
            b = i * varv + (j + 1) % varv
            c, e = a + varv, b + varv
            tris += [a, c, b, b, c, e]
    m = Mesh(vertices=verts, triangles=tris, uvs=uvs, normals=normaler)
    Entity(parent=krater_grupp, model=m, position=(x, 0, z), color=color.rgb(0.55, 0.55, 0.6))
    kratrar.append((x, z, r, h))


def markhojd(x, z):
    hojd = 0.0
    for kx, kz, r, h in kratrar:
        dx, dz = x - kx, z - kz
        if abs(dx) < r * 1.6 and abs(dz) < r * 1.6:
            hojd = max(hojd, krater_profil(math.sqrt(dx * dx + dz * dz) / r, h))
    return hojd


# Berg långt borta
for i in range(40):
    a = math.tau * i / 40 + random.uniform(-0.05, 0.05)
    avst = random.uniform(230, 320)
    Entity(parent=sten_grupp, model='icosphere', color=color.rgb(0.22, 0.22, 0.25),
           position=(math.cos(a) * avst, -random.uniform(4, 12), math.sin(a) * avst),
           scale=(random.uniform(60, 120), random.uniform(25, 60), random.uniform(50, 90)),
           rotation=(0, random.uniform(0, 360), 0))


# ---------------------------------------------------------------------------
# Rymdskepp – aliensen gömmer sig bakom dessa
# ---------------------------------------------------------------------------
class Rymdskepp(Grupp):
    def __init__(self, pos, kraschat=False):
        super().__init__(position=pos)
        self.radie = 5.4
        self.kraschat = kraschat
        self.liv = SKEPP_LIV
        self.blink = 0.0
        self.fas = random.uniform(0, 10)
        # Ett kraschat skepp ligger lägre och lutar
        for g in (self.lit, self.glod):
            g.y = 1.2 if kraschat else 2.6
            if kraschat:
                g.rotation = (random.uniform(-14, 14), 0, random.uniform(10, 18))
        if kraschat:
            self.lit.rotation = self.glod.rotation

        self.del_av('sphere', SKEPP_METALL, scale=(11, 1.9, 11))
        self.del_av('sphere', color.rgb(0.2, 0.21, 0.24), scale=(8.5, 2.4, 8.5), y=0.25)
        # Glasbubbla på toppen
        self.del_av('sphere', color.rgba(0.6, 0.15, 0.9, 0.55), glod=True, scale=(3.8, 3.0, 3.8), y=1.2)
        self.del_av('sphere', color.rgb(0.35, 0.05, 0.5), glod=True, scale=1.4, y=1.0)
        # Lysande ring under
        self.del_av('sphere', color.rgba(1, 0.25, 0.1, 0.7) if kraschat else color.rgba(0.2, 1.0, 0.4, 0.7),
                    glod=True, scale=(4, 0.6, 4), y=-0.75)
        # Lampor runt kanten
        for i in range(12):
            a = math.tau * i / 12
            self.del_av('sphere', ALIEN_GLOD if i % 2 else ALIEN_LILA, glod=True, scale=0.4,
                        position=(math.cos(a) * 5.4, 0, math.sin(a) * 5.4))
        if not kraschat:
            # Landningsben
            for i in range(3):
                a = math.tau * i / 3 + 0.5
                ben = Entity(parent=self.lit, position=(math.cos(a) * 3.6, -1.4, math.sin(a) * 3.6),
                             rotation=(0, -math.degrees(a), 0))
                Entity(parent=ben, model='cube', color=color.rgb(0.15, 0.15, 0.17), scale=(0.3, 2.6, 0.3), rotation=(0, 0, -20))
                Entity(parent=ben, model='cube', color=color.rgb(0.15, 0.15, 0.17), scale=(1.0, 0.15, 1.0), position=(0.45, -1.2, 0))
        else:
            # Lite skrot runt ett kraschat skepp
            for _ in range(6):
                a = random.uniform(0, math.tau)
                d = random.uniform(5.5, 8)
                Entity(parent=sten_grupp, model='cube', color=SKEPP_METALL,
                       scale=(random.uniform(.4, 1.5), .15, random.uniform(.4, 1.2)),
                       position=pos + Vec3(math.cos(a) * d, 0.1, math.sin(a) * d),
                       rotation=(random.uniform(-20, 20), random.uniform(0, 360), random.uniform(-20, 20)))
        self.sla_ihop()

        # Livmätare som syns ovanför skeppet när det har blivit träffat
        self.matare = Entity(parent=self, y=6.2, billboard=True, enabled=False)
        glodande('quad', color.rgba(0, 0, 0, 0.6), parent=self.matare, scale=(4.2, 0.45))
        self.matare_fyll = glodande('quad', ALIEN_GLOD, parent=self.matare, origin=(-0.5, 0),
                                    x=-2, scale=(4, 0.3))
        self.matare_fyll.setDepthOffset(1)   # ritas framför den svarta bakgrunden

    def traffas(self):
        """Ett skott träffade skeppet. Returnerar True om skeppet gick sönder."""
        self.liv -= 1
        self.blink = 0.08
        skada = 1 - self.liv / SKEPP_LIV
        # Ju mer skadat, desto mörkare och rödare blir skeppet
        self.lit.color = color.rgb(1 - skada * 0.45, 1 - skada * 0.7, 1 - skada * 0.75)
        self.matare.enabled = True
        self.matare_fyll.scale_x = 4 * max(0, self.liv) / SKEPP_LIV
        self.matare_fyll.color = color.rgb(0.55 + 0.45 * skada, 1 - 0.8 * skada, 0.2 - 0.1 * skada)
        return self.liv <= 0

    def update(self):
        # Lamporna pulserar (och kraschade eller skadade skepp blinkar trasigt)
        self.fas += time.dt
        self.blink -= time.dt
        skada = 1 - self.liv / SKEPP_LIV
        p = 0.75 + 0.25 * math.sin(self.fas * 3)
        if (self.kraschat or skada > 0.4) and random.random() < 0.06 + skada * 0.2:
            p = 0.3
        if self.blink > 0:
            p = 1.8
        self.glod.color = color.rgb(p, p, p)


# ---------------------------------------------------------------------------
# Hjälten
# ---------------------------------------------------------------------------
class Hjalte(Entity):
    def __init__(self):
        super().__init__()
        self.fart_y = 0.0
        self.pa_marken = True
        self.steg = 0.0
        self.figur = Entity(parent=self)
        f = self.figur

        # Ben
        self.ben = []
        for sida in (-1, 1):
            hoft = Grupp(parent=f, position=(0.2 * sida, 0.9, 0))
            hoft.del_av('cube', DRAKT_SVART, scale=(0.27, 0.5, 0.32), y=-0.22)
            hoft.del_av('cube', DRAKT_GRA, scale=(0.24, 0.45, 0.28), y=-0.62)
            hoft.del_av('cube', DRAKT_GRA, scale=(0.22, 0.22, 0.12), position=(0, -0.43, 0.15))   # knäskydd
            hoft.del_av('cube', NEON, glod=True, scale=(0.05, 0.12, 0.02), position=(0, -0.43, 0.215))
            hoft.del_av('cube', DRAKT_SVART, scale=(0.3, 0.2, 0.45), position=(0, -0.86, 0.06))  # känga
            hoft.del_av('cube', NEON, glod=True, scale=(0.31, 0.03, 0.46), position=(0, -0.79, 0.06))
            self.ben.append(hoft.sla_ihop())

        # Kropp, ryggsäck och hjälm
        k = Grupp(parent=f)
        k.del_av('cube', DRAKT_SVART, scale=(0.72, 0.85, 0.42), y=1.3)
        k.del_av('cube', DRAKT_GRA, scale=(0.62, 0.45, 0.1), position=(0, 1.42, 0.2))      # bröstplåt
        k.del_av('cube', NEON, glod=True, scale=(0.08, 0.3, 0.02), position=(0, 1.42, 0.255))
        k.del_av('cube', NEON, glod=True, scale=(0.25, 0.03, 0.02), position=(0, 1.58, 0.255))
        k.del_av('cube', DRAKT_GRA, scale=(0.78, 0.13, 0.48), y=0.9)                       # bälte
        k.del_av('cube', NEON, glod=True, scale=(0.15, 0.08, 0.02), position=(0, 0.9, 0.245))
        k.del_av('cube', DRAKT_GRA, scale=(0.6, 0.75, 0.3), position=(0, 1.35, -0.34))     # ryggsäck
        for sida in (-1, 1):
            k.del_av('cube', DRAKT_SVART, scale=(0.16, 0.4, 0.16), position=(0.17 * sida, 1.0, -0.42))
            k.del_av('cube', NEON, glod=True, scale=(0.12, 0.05, 0.12), position=(0.17 * sida, 0.79, -0.42))
            k.del_av('cube', NEON, glod=True, scale=(0.03, 0.4, 0.02), position=(0.22 * sida, 1.4, -0.5))
            # Axelskydd
            k.del_av('sphere', DRAKT_GRA, scale=(0.36, 0.28, 0.42), position=(0.47 * sida, 1.68, 0))
            k.del_av('cube', NEON, glod=True, scale=(0.02, 0.05, 0.3), position=(0.62 * sida, 1.68, 0))
        # Hjälm med lysande visir
        k.del_av('sphere', DRAKT_SVART, scale=(0.62, 0.62, 0.66), y=2.0)
        k.del_av('sphere', color.rgb(0.0, 0.55, 0.7), glod=True, scale=(0.52, 0.24, 0.42), position=(0, 2.02, 0.15))
        k.del_av('sphere', NEON, glod=True, scale=(0.4, 0.07, 0.3), position=(0, 2.06, 0.23))
        k.del_av('cube', DRAKT_GRA, scale=(0.12, 0.22, 0.12), position=(0.31, 2.0, -0.02))
        k.del_av('cube', DRAKT_SVART, scale=(0.03, 0.45, 0.03), position=(0.31, 2.3, -0.05))
        k.sla_ihop()
        self.antennlampa = glodande('sphere', color.rgb(1, 0.15, 0.1), parent=f, scale=0.07, position=(0.31, 2.53, -0.05))
        self.jetlagor = [glodande('cube', color.rgba(0.2, 0.9, 1, 0.8), parent=f, scale=(0.1, 0.0, 0.1),
                                  position=(0.17 * s, 0.75, -0.42)) for s in (-1, 1)]

        # Vänster arm (svänger när man springer)
        self.v_arm = Grupp(parent=f, position=(-0.5, 1.62, 0))
        self.v_arm.del_av('cube', DRAKT_SVART, scale=(0.2, 0.75, 0.22), y=-0.37)
        self.v_arm.del_av('cube', NEON, glod=True, scale=(0.21, 0.04, 0.23), y=-0.55)
        self.v_arm.del_av('cube', DRAKT_GRA, scale=(0.2, 0.2, 0.22), y=-0.82)
        self.v_arm.sla_ihop()

        # Höger arm siktar med pistolen
        a = self.h_arm = Grupp(parent=f, position=(0.5, 1.62, 0))
        a.del_av('cube', DRAKT_SVART, scale=(0.2, 0.22, 0.72), z=0.33)
        a.del_av('cube', NEON, glod=True, scale=(0.21, 0.23, 0.04), z=0.5)
        a.del_av('cube', DRAKT_GRA, scale=(0.2, 0.2, 0.18), z=0.74)
        p = Vec3(0, 0.08, 0.86)   # där pistolen sitter i handen
        a.del_av('cube', color.rgb(0.1, 0.1, 0.12), scale=(0.1, 0.16, 0.42), position=p + Vec3(0, 0, 0.12))
        a.del_av('cube', color.rgb(0.1, 0.1, 0.12), scale=(0.09, 0.22, 0.1), position=p + Vec3(0, -0.14, -0.02))
        a.del_av('cube', DRAKT_GRA, scale=(0.07, 0.07, 0.25), position=p + Vec3(0, 0.03, 0.42))
        a.del_av('cube', NEON, glod=True, scale=(0.105, 0.025, 0.3), position=p + Vec3(0, 0.04, 0.13))
        a.sla_ihop()
        self.mynning = Entity(parent=a, position=p + Vec3(0, 0.03, 0.58))
        self.blixt = glodande('sphere', color.rgba(0.6, 1, 1, 0.9), parent=self.mynning, scale=0)

    def animera(self, fart, pitch):
        self.h_arm.rotation_x = pitch * 0.9
        if fart > 0.5 and self.pa_marken:
            self.steg += time.dt * fart * 1.1
            sving = math.sin(self.steg) * 38
            self.ben[0].rotation_x = sving
            self.ben[1].rotation_x = -sving
            self.v_arm.rotation_x = -sving * 0.8
            self.figur.y = abs(math.sin(self.steg)) * 0.08
        else:
            for d in (*self.ben, self.v_arm):
                d.rotation_x = lerp(d.rotation_x, 0 if self.pa_marken else -25, min(1, time.dt * 8))
            self.figur.y = lerp(self.figur.y, 0, min(1, time.dt * 8))
        # Jetlågor när man är i luften
        lagor = 0.35 + random.uniform(0, 0.15) if not self.pa_marken else 0
        for l in self.jetlagor:
            l.scale_y = lerp(l.scale_y, lagor, min(1, time.dt * 15))
            l.y = 0.75 - l.scale_y / 2
        self.antennlampa.visible = (time.time() % 1.2) < 0.6
        self.blixt.scale = max(0, self.blixt.scale_x - time.dt * 4)


# ---------------------------------------------------------------------------
# Aliens – alla använder samma färdiga modell (det går snabbare)
# ---------------------------------------------------------------------------
alien_mall = Grupp()
alien_mall.del_av('sphere', ALIEN_GRON, scale=(0.75, 0.95, 0.7), y=0.75)
alien_mall.del_av('sphere', ALIEN_GLOD, glod=True, scale=(0.4, 0.5, 0.2), position=(0, 0.72, 0.27))
alien_mall.del_av('sphere', ALIEN_GRON, scale=(0.85, 0.7, 0.75), y=1.45)
for sida in (-1, 1):
    alien_mall.del_av('sphere', color.rgb(0.02, 0.02, 0.03), scale=(0.25, 0.32, 0.12),
                      position=(0.17 * sida, 1.48, 0.32), rotation=(0, 0, 25 * sida))
    alien_mall.del_av('sphere', ALIEN_LILA, glod=True, scale=0.06, position=(0.15 * sida, 1.53, 0.38))
    alien_mall.del_av('cube', ALIEN_GRON, scale=(0.04, 0.4, 0.04),
                      position=(0.18 * sida + 0.08 * sida, 1.93, 0), rotation=(0, 0, -25 * sida))
    alien_mall.del_av('sphere', ALIEN_LILA, glod=True, scale=0.13, position=(0.18 * sida + 0.18 * sida, 2.13, 0))
alien_mall.sla_ihop()
alien_mall.detachNode()   # själva mallen syns inte, bara kopiorna


class Alien(Entity):
    def __init__(self, pos):
        super().__init__(position=pos)
        self.figur = Entity(parent=self)
        alien_mall.lit.instanceTo(self.figur)
        alien_mall.glod.instanceTo(self.figur)
        k = random.uniform(0.8, 1.15)
        self.figur.color = color.rgb(k, k, k)
        self.ben = []
        for sida in (-1, 1):
            b = Entity(parent=self.figur, position=(0.18 * sida, 0.38, 0))
            Entity(parent=b, model='cube', color=ALIEN_GRON, scale=(0.13, 0.38, 0.13), y=-0.19)
            self.ben.append(b)
        self.mal = Vec3(pos)
        self.skepp = None
        self.lage = 'gom'        # 'gom' = gömmer sig, 'kika' = tittar fram
        self.timer = random.uniform(0.5, 2)
        self.byt_timer = 0
        self.kik_vinkel = 0
        self.steg = random.uniform(0, 10)


# ---------------------------------------------------------------------------
# Effekter
# ---------------------------------------------------------------------------
partiklar = []   # [entity, hastighet, livstid]


def explosion(pos, farg=ALIEN_GLOD, antal=22, storlek=1.0):
    for _ in range(antal):
        p = glodande('cube', random.choice([farg, ALIEN_LILA, color.white]),
                     scale=random.uniform(0.08, 0.22), position=pos,
                     rotation=(random.uniform(0, 360), random.uniform(0, 360), 0))
        v = Vec3(random.uniform(-1, 1), random.uniform(0.2, 1.5), random.uniform(-1, 1)) * random.uniform(3, 9) * storlek
        partiklar.append([p, v, random.uniform(0.6, 1.2)])
    ring = glodande('sphere', color.rgba(0.6, 1, 0.3, 0.6), position=pos, scale=0.3)
    ring.animate_scale(4 * storlek, duration=0.3 * storlek, curve=curve.out_expo)
    ring.fade_out(duration=0.3 * storlek)
    destroy(ring, delay=0.35 * storlek)


def damm(pos):
    for _ in range(8):
        p = glodande('sphere', color.rgba(0.6, 0.6, 0.65, 0.6), scale=random.uniform(0.1, 0.25),
                     position=pos + Vec3(random.uniform(-.3, .3), 0.1, random.uniform(-.3, .3)))
        partiklar.append([p, Vec3(random.uniform(-1.5, 1.5), random.uniform(0.5, 2), random.uniform(-1.5, 1.5)), 0.7])


def uppdatera_partiklar():
    for p in partiklar[:]:
        e, v, liv = p
        p[2] -= time.dt
        v.y -= GRAVITATION * time.dt
        e.position += v * time.dt
        e.rotation_y += 400 * time.dt
        e.scale *= max(0, 1 - time.dt * 1.5)
        if p[2] <= 0 or e.y < -0.5:
            destroy(e)
            partiklar.remove(p)


# ---------------------------------------------------------------------------
# HUD (skärmtexter, sikte och radar)
# ---------------------------------------------------------------------------
Text.default_font = 'VeraMono.ttf'


def UI(**kw):
    """Saker på skärmen ska inte påverkas av solljuset."""
    return Entity(shader=unlit_shader, **kw)


hud = UI(parent=camera.ui)
sikte = UI(parent=hud)
for x, y, sx, sy in ((0.018, 0, 0.012, 0.002), (-0.018, 0, 0.012, 0.002),
                     (0, 0.018, 0.002, 0.012), (0, -0.018, 0.002, 0.012)):
    UI(parent=sikte, model='quad', color=NEON, position=(x, y), scale=(sx, sy))
UI(parent=sikte, model='circle', color=NEON, scale=0.004)

poang_text = Text(parent=hud, text='', position=(-0.86, 0.47), scale=1.4, color=NEON)
info_text = Text(parent=hud, text='', position=(-0.86, 0.42), scale=1.0, color=color.rgb(0.7, 0.8, 0.85))
tid_text = Text(parent=hud, text='', position=(0, 0.47), origin=(0, 0), scale=1.8, color=color.white)
meny_bakgrund = UI(parent=camera.ui, model='quad', color=color.rgba(0, 0.02, 0.05, 0.75),
                   scale=(1.25, 0.62), y=0.03, z=0.5)
mitt_text = Text(parent=camera.ui, text='', origin=(0, 0), y=0.2, scale=3, color=NEON)
under_text = Text(parent=camera.ui, text='', origin=(0, 0), y=-0.02, scale=1.2, color=color.rgb(0.8, 0.85, 0.9))
traff_markor = UI(parent=hud, model='quad', color=color.rgba(1, 1, 1, 0), scale=0.05, rotation_z=45)

radar = UI(parent=hud, position=(0.70, -0.34))
RADAR_R = 0.13
UI(parent=radar, model='circle', color=color.rgba(0.0, 0.15, 0.2, 0.55), scale=RADAR_R * 2)
for r in (1.0, 0.5):
    UI(parent=radar, model=Mesh(vertices=[Vec3(math.cos(a / 40 * math.tau), math.sin(a / 40 * math.tau), 0) * RADAR_R * r
                                              for a in range(41)], mode='line', thickness=1.5),
           color=color.rgba(0, 0.9, 1, 0.5))
UI(parent=radar, model='quad', color=NEON, scale=(0.008, 0.016))
radar_prickar = []

# Mörk kant runt skärmen (vinjett)
vinjett_bild = Image.new('L', (256, 256))
vp = vinjett_bild.load()
for x in range(256):
    for y in range(256):
        d = math.sqrt(((x - 128) / 128) ** 2 + ((y - 128) / 128) ** 2)
        vp[x, y] = int(max(0, min(1, (d - 0.55) / 0.9)) ** 1.5 * 255)
svart = Image.new('L', (256, 256))
vinjett = UI(parent=camera.ui, model='quad', scale=(window.aspect_ratio * 1.02, 1.02), z=1,
                 texture=Texture(Image.merge('RGBA', (svart, svart, svart, vinjett_bild))))


# ---------------------------------------------------------------------------
# Spelet
# ---------------------------------------------------------------------------
class Spel:
    def __init__(self):
        self.lage = 'meny'
        self.yaw = 0.0
        self.pitch = 8.0
        self.skak = 0.0
        self.skjut_timer = 0.0
        self.skott = []          # [entity, riktning, livstid]
        self.aliens = []
        self.skepp = []
        self.vag = 0
        self.poang = 0
        self.traffar = 0
        self.skjutna = 0
        self.tid_kvar = 0.0
        self.paus_timer = 0.0

        self.bygg_varlden()
        self.hjalte = Hjalte()
        self.kamera_fot = Entity()
        self.kamera_arm = Entity(parent=self.kamera_fot)
        camera.parent = self.kamera_arm
        camera.position = (1.2, 0.5, -6.5)
        camera.rotation = (0, 0, 0)
        self.visa_meny()

    def bygg_varlden(self):
        self.fyll_pa_skepp(Vec3(0, 0, 0))
        # Kratrar som inte ligger under skeppen
        forsok = 0
        while len(kratrar) < 22 and forsok < 500:
            forsok += 1
            r = random.uniform(3, 11)
            x, z = random.uniform(-110, 110), random.uniform(-110, 110)
            if Vec3(x, 0, z).length() < r * 1.6 + 6:
                continue
            if any((Vec3(x, 0, z) - s.position).length() < r * 1.6 + 7 for s in self.skepp):
                continue
            if any(math.hypot(x - kx, z - kz) < (r + kr) * 1.6 for kx, kz, kr, _ in kratrar):
                continue
            bygg_krater(x, z, r, random.uniform(0.5, 1.0) * r * 0.13)
        krater_grupp.combine(include_normals=True)
        krater_grupp.texture = MANTEXTUR
        krater_grupp.set_shader_input('specular', 0.0)
        # Stenar
        for _ in range(140):
            x, z = random.uniform(-140, 140), random.uniform(-140, 140)
            s = random.uniform(0.15, 0.9) * random.choice([1, 1, 1, 2.2])
            g = random.uniform(0.28, 0.4)
            Entity(parent=sten_grupp, model='icosphere', color=color.rgb(g, g, g),
                   position=(x, markhojd(x, z) + s * 0.1, z), scale=(s, s * random.uniform(0.4, 0.8), s * 1.2),
                   rotation=(random.uniform(-20, 20), random.uniform(0, 360), random.uniform(-20, 20)))
        sten_grupp.combine(include_normals=True)
        sten_grupp.set_shader_input('specular', 0.05)
        # Skuggorna räknas ut i en ruta runt hjälten (flyttas med när man springer)
        self.skuggzon = Entity(model='cube', scale=(110, 30, 110), visible=False)
        sol.update_bounds(self.skuggzon)

    def fyll_pa_skepp(self, hjalte_pos, landa=False):
        """Ställer ut nya rymdskepp tills det finns SKEPP_ANTAL stycken."""
        forsok = 0
        while len(self.skepp) < SKEPP_ANTAL and forsok < 2000:
            forsok += 1
            a, d = random.uniform(0, math.tau), random.uniform(18, 85)
            p = Vec3(math.cos(a) * d, 0, math.sin(a) * d)
            if any((p - Vec3(s.x, 0, s.z)).length() < 24 for s in self.skepp):
                continue
            if (p - Vec3(hjalte_pos.x, 0, hjalte_pos.z)).length() < 20:
                continue
            if any(math.hypot(p.x - kx, p.z - kz) < kr + 7 for kx, kz, kr, _ in kratrar):
                continue
            skepp = Rymdskepp(p, kraschat=random.random() < 0.33)
            if landa:
                # Nya skepp kommer flygande från himlen
                skepp.y = 45
                skepp.animate_y(0, duration=random.uniform(1.5, 2.5), curve=curve.out_cubic)
            self.skepp.append(skepp)

    # ---------------- lägen ----------------
    def visa_text(self, rubrik, text='', bakgrund=False):
        mitt_text.text = rubrik
        under_text.text = text
        under_text.y = -0.02 if bakgrund else 0.12
        meny_bakgrund.visible = bakgrund

    def visa_meny(self):
        self.lage = 'meny'
        hud.visible = False
        self.visa_text('MÅNHJÄLTEN',
                       'Aliens har landat på månen och gömmer sig bakom sina rymdskepp!\n'
                       'Skjut alla innan tiden tar slut.\n\n'
                       'WASD springa   Shift spurta   E hoppa\n'
                       'Piltangenter vända   Mellanslag skjuta   Esc paus\n\n'
                       'Tryck mellanslag för att börja', bakgrund=True)

    def starta(self):
        for a in self.aliens:
            destroy(a)
        self.aliens.clear()
        self.poang = self.traffar = self.skjutna = 0
        self.vag = 0
        self.paus_timer = 0
        self.hjalte.position = Vec3(0, 0, 0)
        self.yaw = 0
        # Skadade skepp byts ut mot nya hela
        for s in [s for s in self.skepp if s.liv < SKEPP_LIV]:
            self.skepp.remove(s)
            destroy(s)
        self.fyll_pa_skepp(self.hjalte.position)
        self.lage = 'spel'
        hud.visible = True
        self.ny_vag()

    def ny_vag(self):
        self.vag += 1
        antal = 3 + self.vag * 2
        self.tid_kvar = START_TID + antal * TID_PER_ALIEN
        self.fyll_pa_skepp(self.hjalte.position, landa=True)
        for _ in range(antal):
            for _ in range(50):
                s = random.choice(self.skepp)
                a = random.uniform(0, math.tau)
                p = Vec3(s.x, 0, s.z) + Vec3(math.cos(a), 0, math.sin(a)) * (s.radie + 2)
                if (p - self.hjalte.position).length() > 25:
                    break
            alien = Alien(p)
            alien.skepp = s
            self.aliens.append(alien)
        rubrik = f'VÅG {self.vag}'
        self.visa_text(rubrik, f'{antal} aliens gömmer sig...')
        ljud_vag.spela()
        invoke(self.rensa_text, rubrik, delay=2.5)

    def rensa_text(self, om_text):
        if mitt_text.text == om_text and self.lage == 'spel':
            self.visa_text('')

    def slut(self):
        self.lage = 'slut'
        traffsakerhet = int(100 * self.traffar / self.skjutna) if self.skjutna else 0
        self.visa_text('TIDEN ÄR SLUT',
                       f'Du klarade {self.vag - 1} vågor och fick {self.poang} poäng\n'
                       f'Träffsäkerhet: {traffsakerhet}%\n\n'
                       'Tryck R för att spela igen', bakgrund=True)

    # ---------------- inmatning ----------------
    def tangent(self, key):
        if self.lage == 'meny' and key == 'space':
            self.starta()
        elif self.lage == 'slut' and key == 'r':
            self.starta()
        elif self.lage == 'spel' and key == 'escape':
            self.lage = 'paus'
            self.visa_text('PAUS', 'Tryck mellanslag för att fortsätta', bakgrund=True)
        elif self.lage == 'paus' and key in ('space', 'escape'):
            self.lage = 'spel'
            self.visa_text('')
        elif self.lage == 'spel' and key == 'e' and self.hjalte.pa_marken:
            self.hjalte.fart_y = HOPPKRAFT
            self.hjalte.pa_marken = False
            ljud_hopp.spela()
            damm(self.hjalte.position)

    # ---------------- varje bildruta ----------------
    def uppdatera(self):
        uppdatera_partiklar()
        himmel.position = camera.world_position
        if self.lage == 'meny':
            # Kameran åker långsamt runt hjälten på menyn
            self.yaw += time.dt * 8
            self.pitch = 10
            self.flytta_kamera()
            self.hjalte.animera(0, 0)
            return
        if self.lage != 'spel':
            return

        self.styr_hjalten()
        self.uppdatera_skott()
        for alien in self.aliens:
            self.styr_alien(alien)
        self.flytta_kamera()
        self.uppdatera_hud()

        if self.paus_timer > 0:
            # Mellan två vågor
            self.paus_timer -= time.dt
            if self.paus_timer <= 0:
                self.ny_vag()
            return
        self.tid_kvar -= time.dt
        if self.tid_kvar <= 0:
            self.tid_kvar = 0
            self.slut()
        elif not self.aliens:
            self.paus_timer = 3
            bonus = int(self.tid_kvar) * 10
            self.poang += bonus
            self.visa_text(f'VÅG {self.vag} KLAR!', f'Tidsbonus: +{bonus}')
            ljud_vag.spela(1.25)

    def riktningar(self):
        y = math.radians(self.yaw)
        return Vec3(math.sin(y), 0, math.cos(y)), Vec3(math.cos(y), 0, -math.sin(y))

    def styr_hjalten(self):
        h = self.hjalte
        # Piltangenterna: vänster/höger vänder, upp/ner tittar upp och ner
        self.yaw += (held_keys['right arrow'] - held_keys['left arrow']) * VRID_FART * time.dt
        self.pitch += (held_keys['down arrow'] - held_keys['up arrow']) * TITT_FART * time.dt
        self.pitch = max(-35, min(45, self.pitch))
        fram, hoger = self.riktningar()
        rikt = fram * (held_keys['w'] - held_keys['s']) + hoger * (held_keys['d'] - held_keys['a'])
        fart = SPURT_FART if held_keys['shift'] else GA_FART
        if rikt.length() > 0:
            rikt = rikt.normalized() * fart
        h.position += rikt * time.dt
        h.rotation_y = self.yaw

        # Hopp och låg gravitation
        golv = markhojd(h.x, h.z)
        h.fart_y -= GRAVITATION * time.dt
        h.y += h.fart_y * time.dt
        if h.y <= golv:
            if not h.pa_marken and h.fart_y < -3:
                damm(h.position)
            h.y = golv
            h.fart_y = 0
            h.pa_marken = True
        elif h.y > golv + 0.2:
            h.pa_marken = False

        self.puttas_ut(h, 0.6)
        h.animera(rikt.length(), self.pitch)

        self.skjut_timer -= time.dt
        if held_keys['space'] and self.skjut_timer <= 0:
            self.skjut()

    def puttas_ut(self, e, radie):
        """Hindrar någon från att springa rakt igenom ett rymdskepp."""
        for s in self.skepp:
            d = Vec3(e.x - s.x, 0, e.z - s.z)
            minst = s.radie + radie
            if 0.001 < d.length() < minst and e.y < 4:
                e.position += d.normalized() * (minst - d.length())
        avst = Vec3(e.x, 0, e.z).length()
        if avst > BANANS_RADIE:
            e.x *= BANANS_RADIE / avst
            e.z *= BANANS_RADIE / avst

    def skjut(self):
        self.skjut_timer = SKJUT_PAUS
        self.skjutna += 1
        start = self.hjalte.mynning.world_position
        # Sikta mot det som är mitt på skärmen
        kam = camera.world_position
        kfram = camera.forward
        siktpunkt = kam + kfram * 120
        if kfram.y < -0.01:
            t = -kam.y / kfram.y
            if t < 120:
                siktpunkt = kam + kfram * t
        mal = self.hitta_mal()
        if mal:
            siktpunkt = mal.position + Vec3(0, 1.0, 0)
        rikt = (siktpunkt - start).normalized()
        bolt = glodande('cube', NEON, scale=(0.07, 0.07, 1.1), position=start)
        Entity(parent=bolt, model='cube', color=color.rgba(0.3, 1, 1, 0.3), shader=unlit_shader, scale=(3.5, 3.5, 1.2))
        bolt.look_at(start + rikt)
        self.skott.append([bolt, rikt, 1.4])
        self.hjalte.blixt.scale = 0.45
        self.skak = max(self.skak, 0.06)
        ljud_laser.spela(random.uniform(0.92, 1.08))

    def fri_sikt(self, fran, till):
        """Står något rymdskepp i vägen mellan två punkter?"""
        d = Vec3(till.x - fran.x, 0, till.z - fran.z)
        langd2 = d.x * d.x + d.z * d.z
        for sk in self.skepp:
            t = ((sk.x - fran.x) * d.x + (sk.z - fran.z) * d.z) / max(langd2, 0.001)
            t = max(0, min(1, t))
            nx, nz = fran.x + d.x * t - sk.x, fran.z + d.z * t - sk.z
            if nx * nx + nz * nz < (sk.radie * 0.9) ** 2:
                return False
        return True

    def hitta_mal(self):
        """Sikthjälp: den alien som är närmast mitten av siktet (och inte gömd bakom ett skepp)."""
        kam = camera.world_position
        kfram = Vec3(camera.forward.x, 0, camera.forward.z).normalized()
        basta, basta_vinkel = None, SIKTHJALP
        for alien in self.aliens:
            till = Vec3(alien.x - kam.x, 0, alien.z - kam.z)
            avst = till.length()
            if avst < 1 or avst > 110:
                continue
            vinkel = math.degrees(math.acos(max(-1, min(1, till.dot(kfram) / avst))))
            if vinkel < basta_vinkel and self.fri_sikt(kam, alien.position):
                basta, basta_vinkel = alien, vinkel
        return basta

    def uppdatera_skott(self):
        for s in self.skott[:]:
            bolt, rikt, liv = s
            s[2] -= time.dt
            steg = SKOTT_FART * time.dt
            traffad = None
            delsteg = max(1, int(steg / 0.4))
            for _ in range(delsteg):
                bolt.position += rikt * (steg / delsteg)
                p = bolt.position
                for alien in self.aliens:
                    d = p - (alien.position + Vec3(0, 1.0, 0))
                    if abs(d.y) < 1.1 and d.x * d.x + d.z * d.z < 0.55 ** 2:
                        traffad = alien
                        break
                if traffad:
                    break
                traffat_skepp = next((sk for sk in self.skepp
                                      if (p.x - sk.x) ** 2 + (p.z - sk.z) ** 2 < sk.radie ** 2 and p.y < 4.2), None)
                if traffat_skepp:
                    s[2] = 0
                    explosion(p, farg=color.orange, antal=6)
                    ljud_klonk.spela(random.uniform(0.85, 1.15))
                    if traffat_skepp.traffas():
                        self.sprang_skepp(traffat_skepp)
                    break
                if p.y < markhojd(p.x, p.z):
                    s[2] = 0
                    explosion(p, farg=NEON, antal=5)
                    break
            if traffad:
                self.traff(traffad)
                s[2] = 0
            if s[2] <= 0:
                destroy(bolt)
                self.skott.remove(s)

    def traff(self, alien):
        explosion(alien.position + Vec3(0, 1, 0))
        ljud_traff.spela(random.uniform(0.9, 1.15))
        self.aliens.remove(alien)
        destroy(alien)
        self.traffar += 1
        self.poang += 100 * self.vag
        self.skak = 0.25
        traff_markor.color = color.rgba(1, 1, 1, 1)
        traff_markor.scale = 0.08
        traff_markor.animate_scale(0.03, duration=0.25)
        traff_markor.animate_color(color.rgba(1, 1, 1, 0), duration=0.3)

    def sprang_skepp(self, skepp):
        mitt = Vec3(skepp.x, 2.5, skepp.z)
        self.skepp.remove(skepp)
        destroy(skepp)
        for _ in range(4):
            explosion(mitt + Vec3(random.uniform(-3, 3), random.uniform(-1, 2), random.uniform(-3, 3)),
                      farg=random.choice([color.orange, ALIEN_LILA, color.yellow]), antal=25, storlek=2.2)
        ljud_boom.spela(random.uniform(0.9, 1.1))
        self.skak = 0.7
        self.poang += 50 * self.vag
        # Aliens som gömde sig precis bakom skeppet åker med i smällen!
        for alien in self.aliens[:]:
            if (Vec3(alien.x, 0, alien.z) - Vec3(mitt.x, 0, mitt.z)).length() < skepp.radie + 3.5:
                self.traff(alien)

    # ---------------- alien-hjärna ----------------
    def gomstalle(self, skepp, vinkel=0.0):
        """Platsen bakom ett skepp sett från hjälten (vinkel vrider runt skeppet)."""
        bort = Vec3(skepp.x - self.hjalte.x, 0, skepp.z - self.hjalte.z)
        if bort.length() < 0.01:
            bort = Vec3(1, 0, 0)
        bort = bort.normalized()
        c, s = math.cos(vinkel), math.sin(vinkel)
        bort = Vec3(bort.x * c - bort.z * s, 0, bort.x * s + bort.z * c)
        return Vec3(skepp.x, 0, skepp.z) + bort * (skepp.radie + 1.4)

    def valj_skepp(self, alien):
        """Hitta ett nytt skepp som ligger långt från hjälten men inte för långt bort."""
        basta = alien.skepp if alien.skepp in self.skepp else None
        basta_poang = -1e9
        for s in self.skepp:
            if s is alien.skepp:
                continue
            p = ((s.position - self.hjalte.position).length()
                 - (s.position - alien.position).length() * 0.8
                 + random.uniform(0, 12))
            if p > basta_poang:
                basta, basta_poang = s, p
        alien.skepp = basta

    def styr_alien(self, alien):
        h = self.hjalte
        till_hjalte = Vec3(h.x - alien.x, 0, h.z - alien.z)
        avst = till_hjalte.length()
        alien.byt_timer -= time.dt
        alien.timer -= time.dt

        # Skeppet har sprängts: hitta ett nytt att gömma sig bakom
        if alien.skepp not in self.skepp:
            self.valj_skepp(alien)
            alien.lage = 'gom'

        # Hjälten kommer för nära: spring till ett annat skepp!
        if avst < 9 and alien.byt_timer <= 0:
            self.valj_skepp(alien)
            alien.byt_timer = 3
            alien.lage = 'gom'
            if random.random() < 0.5:
                ljud_pip.spela(random.uniform(1.2, 1.6))

        if alien.skepp is None:
            # Inga skepp kvar – bara att springa därifrån!
            bort = -till_hjalte / avst if avst > 0.1 else Vec3(1, 0, 0)
            alien.mal = alien.position + bort * 6
        elif alien.lage == 'gom':
            alien.mal = self.gomstalle(alien.skepp)
            # Ibland blir de nyfikna och kikar fram...
            if alien.timer <= 0 and (alien.mal - alien.position).length() < 1.5 and avst > 14:
                alien.lage = 'kika'
                alien.kik_vinkel = random.choice([-1, 1]) * random.uniform(0.9, 1.4)
                alien.timer = random.uniform(1.0, 2.2)
        else:
            alien.mal = self.gomstalle(alien.skepp, alien.kik_vinkel)
            if alien.timer <= 0:
                alien.lage = 'gom'
                alien.timer = random.uniform(2, 5)

        rikt = Vec3(alien.mal.x - alien.x, 0, alien.mal.z - alien.z)
        langd = rikt.length()
        fart = ALIEN_PANIK_FART if avst < 14 else ALIEN_FART
        if langd > 0.3:
            rikt = rikt / langd
            # Styr runt skeppen istället för att fastna i dem
            for s in self.skepp:
                ut = Vec3(alien.x - s.x, 0, alien.z - s.z)
                d = ut.length()
                if d < s.radie + 2.5 and rikt.dot(ut) < 0:
                    sida = Vec3(-ut.z, 0, ut.x) / d
                    if sida.dot(rikt) < 0:
                        sida = -sida
                    rikt = (rikt + sida * 1.5).normalized()
            alien.position += rikt * min(fart * time.dt, langd)
            mal_vinkel = math.degrees(math.atan2(rikt.x, rikt.z))
            alien.rotation_y = lerp_vinkel(alien.rotation_y, mal_vinkel, time.dt * 10)
            alien.steg += time.dt * fart * 2
            sving = math.sin(alien.steg) * 40
            alien.ben[0].rotation_x = sving
            alien.ben[1].rotation_x = -sving
            alien.figur.y = abs(math.sin(alien.steg)) * 0.25
        else:
            # Står still och tittar efter hjälten
            mal_vinkel = math.degrees(math.atan2(till_hjalte.x, till_hjalte.z))
            alien.rotation_y = lerp_vinkel(alien.rotation_y, mal_vinkel, time.dt * 5)
            alien.steg += time.dt * 3
            alien.figur.y = abs(math.sin(alien.steg)) * 0.05
        self.puttas_ut(alien, 0.5)
        alien.y = markhojd(alien.x, alien.z)

    # ---------------- kamera och HUD ----------------
    def flytta_kamera(self):
        h = self.hjalte
        mal = h.position + Vec3(0, 1.75, 0)
        self.kamera_fot.position = lerp(self.kamera_fot.position, mal, min(1, time.dt * 14))
        self.kamera_fot.rotation_y = self.yaw
        self.kamera_arm.rotation_x = self.pitch
        self.skak = max(0, self.skak - time.dt * 1.5)
        if (Vec3(h.x, 0, h.z) - self.skuggzon.position).length() > 6:
            self.skuggzon.position = Vec3(round(h.x / 6) * 6, 0, round(h.z / 6) * 6)
            sol.update_bounds(self.skuggzon)
        camera.position = Vec3(1.2 + random.uniform(-1, 1) * self.skak * 0.5,
                               0.5 + random.uniform(-1, 1) * self.skak * 0.5, -6.5)

    def uppdatera_hud(self):
        poang_text.text = f'POÄNG {self.poang}'
        # Siktet blir lila när skotten kommer att styra mot en alien
        siktfarg = ALIEN_LILA if self.hitta_mal() else NEON
        for del_ in sikte.children:
            del_.color = siktfarg
        sikte.scale = 1.4 if siktfarg is ALIEN_LILA else 1
        info_text.text = f'VÅG {self.vag}    ALIENS KVAR {len(self.aliens)}'
        sek = int(math.ceil(self.tid_kvar))
        tid_text.text = f'{sek // 60}:{sek % 60:02d}'
        blinka = self.tid_kvar < 10 and (self.tid_kvar % 0.5) < 0.25
        tid_text.color = color.rgb(1, 0.25, 0.2) if blinka else color.white

        # Radarn: grå = skepp, grön = aliens
        saker = [(s, color.rgba(0.6, 0.6, 0.7, 0.8), 0.022) for s in self.skepp] + \
                [(a, ALIEN_GLOD, 0.012) for a in self.aliens]
        while len(radar_prickar) < len(saker):
            radar_prickar.append(UI(parent=radar, model='circle', z=-0.1))
        fram, hoger = self.riktningar()
        for i, prick in enumerate(radar_prickar):
            if i >= len(saker):
                prick.visible = False
                continue
            e, farg, storlek = saker[i]
            rel = Vec3(e.x - self.hjalte.x, 0, e.z - self.hjalte.z)
            p = Vec2(rel.dot(hoger), rel.dot(fram)) * (RADAR_R / 60)
            if p.length() > RADAR_R:
                p = p.normalized() * RADAR_R
            prick.visible = True
            prick.position = (p.x, p.y)
            prick.color = farg
            prick.scale = storlek


def lerp_vinkel(a, b, t):
    skillnad = (b - a + 180) % 360 - 180
    return a + skillnad * min(1, t)


spel = Spel()


def update():
    spel.uppdatera()


def input(key):
    spel.tangent(key)


app.run()
