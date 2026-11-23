#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF A4 del profilo dei Sorzolupo, a partire dal testo Markdown.

Uso:
    python3 crea_pdf_profilo.py sorzolupi-profilo-completo.md uscita.pdf

Riconosce un Markdown semplice: titolo (#), sottotitolo (il primo paragrafo dopo il
titolo), sezioni (## e ###), elenchi puntati (- ) e numerati (1. ), tabelle (| … |),
grassetto (**testo**) e testo tecnico (`testo`).
"""

import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Body", FONT_DIR + "DejaVuSansCondensed.ttf"))
pdfmetrics.registerFont(TTFont("BodyBold", FONT_DIR + "DejaVuSansCondensed-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", FONT_DIR + "DejaVuSansMono.ttf"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyBold",
                              italic="Body", boldItalic="BodyBold")

SIZE = 11.5
LARGHEZZA = A4[0] - 36 * mm
ST = {
    "title": ParagraphStyle("title", fontName="BodyBold", fontSize=24, leading=29, spaceAfter=4),
    "subtitle": ParagraphStyle("subtitle", fontName="Body", fontSize=12, leading=16,
                               textColor=colors.HexColor("#333333"), spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="BodyBold", fontSize=17, leading=21, spaceBefore=14,
                         spaceAfter=6, textColor=colors.HexColor("#1F3A5F")),
    "h3": ParagraphStyle("h3", fontName="BodyBold", fontSize=13.5, leading=17, spaceBefore=10,
                         spaceAfter=4),
    "p": ParagraphStyle("p", fontName="Body", fontSize=SIZE, leading=SIZE * 1.35, spaceAfter=5),
    "li": ParagraphStyle("li", fontName="Body", fontSize=SIZE, leading=SIZE * 1.35),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=SIZE - 1, leading=(SIZE - 1) * 1.25),
    "cellh": ParagraphStyle("cellh", fontName="BodyBold", fontSize=SIZE - 1, leading=(SIZE - 1) * 1.25),
}


def inline(t):
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r'<font name="Mono" size="%.1f">\1</font>' % (SIZE - 1.5), t)
    return t


def tabella(righe):
    celle = [[c.strip() for c in r.strip().strip("|").split("|")] for r in righe
             if not re.match(r"^\|\s*-", r.strip())]
    n = len(celle[0])
    # larghezze: mai meno della parola più lunga di ogni colonna (le parole non si spezzano),
    # poi lo spazio che resta va alle colonne con più testo
    pad = 2 * 4 + 3

    def larg(t, bold=False):
        return pdfmetrics.stringWidth(re.sub(r"\*\*|`", "", t), "BodyBold" if bold else "Body", SIZE - 1)
    minimo, naturale = [], []
    for c in range(n):
        parole = [(p, i == 0) for i, r in enumerate(celle) for p in re.sub(r"\*\*|`", "", r[c]).split()]
        minimo.append(max([larg(p, b) for p, b in parole] or [10]) + pad)
        naturale.append(max(larg(r[c], i == 0) for i, r in enumerate(celle)) + pad)
    if sum(naturale) <= LARGHEZZA:
        widths = [w * LARGHEZZA / sum(naturale) for w in naturale]
    elif sum(minimo) >= LARGHEZZA:
        widths = [w * LARGHEZZA / sum(minimo) for w in minimo]
    else:
        extra = [nat - mn for nat, mn in zip(naturale, minimo)]
        resto = LARGHEZZA - sum(minimo)
        widths = [mn + resto * e / sum(extra) for mn, e in zip(minimo, extra)]
    data = [[Paragraph(inline(v), ST["cellh"] if i == 0 else ST["cell"]) for v in r]
            for i, r in enumerate(celle)]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8A8A8A")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE3EC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def elenco(voci, numerato):
    items = [ListItem(Paragraph(inline(v), ST["li"]), leftIndent=14) for v in voci]
    if numerato:
        return ListFlowable(items, bulletType="1", bulletFormat="%s.", bulletFontName="BodyBold",
                            bulletFontSize=SIZE, leftIndent=16, spaceBefore=2, spaceAfter=6)
    return ListFlowable(items, bulletType="bullet", start="•", bulletFontName="Body",
                        bulletFontSize=SIZE, leftIndent=14, spaceBefore=2, spaceAfter=6)


def leggi(md):
    righe = md.splitlines()
    story, i = [], 0
    titolo = ""
    sottotitolo_atteso = False
    in_attesa = []  # intestazioni da tenere insieme al blocco che segue
    while i < len(righe):
        r = righe[i]
        s = r.strip()
        blocco = None
        if not s:
            i += 1
            continue
        if s.startswith("# "):
            titolo = s[2:]
            story.append(Paragraph(inline(titolo), ST["title"]))
            sottotitolo_atteso = True
            i += 1
            continue
        if s.startswith("## ") or s.startswith("### "):
            stile = ST["h2"] if s.startswith("## ") else ST["h3"]
            testo = s[3:] if s.startswith("## ") else s[4:]
            in_attesa.append(Paragraph(inline(testo), stile))
            i += 1
            continue
        if s.startswith("|"):
            gruppo = []
            while i < len(righe) and righe[i].strip().startswith("|"):
                gruppo.append(righe[i])
                i += 1
            blocco = tabella(gruppo)
        elif re.match(r"^- ", s) or re.match(r"^\d+\. ", s):
            numerato = bool(re.match(r"^\d+\. ", s))
            voci = []
            while i < len(righe):
                t = righe[i].strip()
                if numerato and re.match(r"^\d+\. ", t):
                    voci.append(re.sub(r"^\d+\. ", "", t))
                elif not numerato and t.startswith("- "):
                    voci.append(t[2:])
                else:
                    break
                i += 1
            blocco = elenco(voci, numerato)
        else:
            testo = [s]
            i += 1
            while i < len(righe) and righe[i].strip() and not re.match(r"^(#|\||- |\d+\. )", righe[i].strip()):
                testo.append(righe[i].strip())
                i += 1
            stile = ST["subtitle"] if sottotitolo_atteso else ST["p"]
            blocco = Paragraph(inline(" ".join(testo)), stile)
        sottotitolo_atteso = False
        if in_attesa:
            story.append(KeepTogether(in_attesa + [blocco]))
            in_attesa = []
        else:
            story.append(blocco)
    story += in_attesa
    return titolo, story


class ConPagine(rl_canvas.Canvas):
    """Canvas che scrive «pagina N di M» in fondo a ogni foglio."""
    titolo = ""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._pagine = []

    def showPage(self):
        self._pagine.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        tot = len(self._pagine)
        for stato in self._pagine:
            self.__dict__.update(stato)
            self.setFont("Body", 8.5)
            self.setFillColor(colors.HexColor("#555555"))
            self.drawString(18 * mm, 10 * mm, self.titolo)
            self.drawRightString(A4[0] - 18 * mm, 10 * mm, f"pagina {self._pageNumber} di {tot}")
            super().showPage()
        super().save()


def main(md_path, out):
    with open(md_path, encoding="utf-8") as fh:
        titolo, story = leggi(fh.read())
    ConPagine.titolo = re.sub(r"\*\*|`", "", titolo) + " · profilo completo e regole"
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=titolo,
                            author="Parcheggio Trieste", creator="Sorzolupi")
    doc.build(story, canvasmaker=ConPagine)
    print("PDF creato:", out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
