# Månhjälten 🌙

Ett 3D-spel i Python där du är en hjälte på månen. Aliens har landat och
försöker springa iväg och gömma sig bakom sina rymdskepp. Din uppgift är att
hitta och skjuta alla innan tiden tar slut. Du har bara en pistol.

## Kom igång

Du behöver Python 3.10 eller nyare.

### Windows

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manhjalten.py
```

### Linux / WSL / macOS

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manhjalten.py
```

Tryck mellanslag i fönstret för att börja spela. Musen används inte i
spelet, så du kan alltid dra fönstret dit du vill (till exempel till en
annan skärm).

## Styrning

| Tangent          | Vad händer                       |
|------------------|----------------------------------|
| **W A S D**      | Springa                          |
| **Shift**        | Spurta                           |
| **Mellanslag**   | Skjuta (håll inne för att skjuta flera skott) |
| **E**            | Hoppa (låg gravitation!)         |
| **Piltangenter** | Vända höger/vänster och titta upp/ner |
| **Esc**          | Pausa                            |
| **R**            | Spela igen när spelet är slut    |

## Så spelar man

- Spelet är uppdelat i **vågor**. Varje ny våg har fler aliens.
- Aliens gömmer sig på andra sidan av ett rymdskepp än du. Ibland
  **kikar de fram**, och då har du chansen att träffa dem.
- Kommer du för nära får de panik och springer till ett annat skepp.
- Skotten går inte igenom rymdskeppen, men skjuter du **tillräckligt många
  gånger på ett skepp så sprängs det**. En mätare ovanför skeppet visar hur
  mycket det tål. Aliens som gömmer sig precis bakom skeppet åker med i
  smällen! När en ny våg börjar landar nya skepp.
- **Sikthjälp**: när siktet blir lila är en alien nära nog, och skotten
  styr då mot den. Sikta åt rätt håll och tryck mellanslag!
- **Radarn** nere till höger visar skeppen (grå) och aliens (gröna).
- Varje träff ger poäng. Klarar du en våg snabbt får du **tidsbonus**.
- När tiden tar slut är spelet över.

## Ändra i spelet

Överst i `manhjalten.py` finns inställningar som du kan ändra. Spara filen
och starta spelet igen för att se vad som händer.

| Inställning        | Vad den gör                                  |
|--------------------|----------------------------------------------|
| `GRAVITATION`      | Hur snabbt du faller. Prova `1.0` eller `20.0`! |
| `HOPPKRAFT`        | Hur högt du hoppar                           |
| `GA_FART`          | Hur snabbt du springer                       |
| `SPURT_FART`       | Hur snabbt du springer med Shift             |
| `ALIEN_FART`       | Hur snabbt aliens springer                   |
| `ALIEN_PANIK_FART` | Hur snabbt aliens springer när du är nära    |
| `SKOTT_FART`       | Hur snabbt skotten flyger                    |
| `SKJUT_PAUS`       | Tid mellan skotten (mindre = snabbare)       |
| `SIKTHJALP`        | Hur mycket skotten styr mot närmaste alien (`0` = av) |
| `VRID_FART`        | Hur snabbt du vänder med vänster/höger pil   |
| `TITT_FART`        | Hur snabbt du tittar upp/ner med pilarna     |
| `START_TID`        | Sekunder du alltid får på varje våg          |
| `TID_PER_ALIEN`    | Extra sekunder för varje alien i vågen       |
| `SKEPP_ANTAL`      | Hur många rymdskepp som finns på månen       |
| `SKEPP_LIV`        | Hur många skott ett rymdskepp tål            |
| `BANANS_RADIE`     | Hur långt ut på månen du får springa         |

Färgerna finns också där, till exempel `NEON` (dräktens lysande ränder) och
`ALIEN_GRON`. En färg skrivs som `color.rgb(röd, grön, blå)`, där varje
siffra går från `0.0` till `1.0`.

## Hur spelet är byggt

Allt finns i en enda fil, `manhjalten.py`:

- **Ljud**: ljudeffekterna räknas fram med matematik första gången
  spelet startar och sparas i mappen `ljud/`.
- **Texturer**: månens yta och jorden ritas med kod (biblioteket Pillow).
- **Figurerna**: hjälten, aliens och rymdskeppen är byggda av enkla former
  (kuber och klot). Klassen `Grupp` slår ihop delarna till färre modeller
  så att spelet går snabbare.
- **Shadern** `man_shader` ger ljus, skuggor, kantljus och dimma, så att
  allt får sin mörka stämning.
- **Alien-hjärnan** finns i `styr_alien`. Där bestäms var de gömmer sig,
  när de kikar fram och när de flyr.

Spelmotorn heter [Ursina](https://www.ursinaengine.org/) och bygger på Panda3D.

## Problem?

- **Spelet går segt i WSL**: spelet ber själv om grafikkortet
  (`GALLIUM_DRIVER=d3d12`), men det går ändå långsammare än direkt i
  Windows. Kör det helst i Windows om du kan.
- **Inget ljud i WSL**: WSL har ofta ingen ljudenhet. Spelet fungerar ändå.
- **Nya ljud**: vill du göra om ljuden, radera mappen `ljud/` så skapas
  de igen nästa gång spelet startar.
