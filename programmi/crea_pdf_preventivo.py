#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sorzolupo2 - PDF del preventivo (A4 verticale, tabella leggibile da stampare o mandare)
Parcheggio Trieste - via Milano 2 - Trieste

Uso:
    python3 crea_pdf_preventivo.py dati.json uscita.pdf

dati.json e' lo stesso file di calcola_preventivo.py (che deve stare nella stessa
cartella: i conti si fanno con quel programma), con in piu' due campi facoltativi:
  "oggetto": "Parcheggio dal 19 al 22 novembre 2026"
  "nota": "testo libero in fondo al preventivo"

Nel PDF:
- tabella dei veicoli: veicolo, tipo, dal, al, giorni, euro al giorno, totale;
- le prenotazioni annullate non compaiono; una riga senza prezzo confermato
  compare con "da confermare" e non entra nel totale;
- riepilogo con totale IVA inclusa, imponibile e IVA per ogni intestatario;
- nota sulla scissione dei pagamenti (split payment, art. 17-ter DPR 633/1972).
"""

import json
import os
import sys
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calcola_preventivo import calcola, euro  # noqa: E402

FORNITORE = ["Parcheggio Trieste", "via Milano 2 · Trieste",
             "+39 339 2574801 · www.parcheggiotrieste.com"]

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Body", FONT_DIR + "DejaVuSansCondensed.ttf"))
pdfmetrics.registerFont(TTFont("BodyBold", FONT_DIR + "DejaVuSansCondensed-Bold.ttf"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyBold",
                              italic="Body", boldItalic="BodyBold")

SIZE = 13
ST = {
    "norm": ParagraphStyle("norm", fontName="Body", fontSize=SIZE, leading=SIZE * 1.3),
    "small": ParagraphStyle("small", fontName="Body", fontSize=SIZE - 1.5, leading=(SIZE - 1.5) * 1.3,
                            textColor=colors.HexColor("#333333")),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=SIZE, leading=SIZE * 1.2),
    "cell_c": ParagraphStyle("cell_c", fontName="Body", fontSize=SIZE, leading=SIZE * 1.2,
                             alignment=TA_CENTER),
    "cell_r": ParagraphStyle("cell_r", fontName="Body", fontSize=SIZE, leading=SIZE * 1.2,
                             alignment=TA_RIGHT),
    "head": ParagraphStyle("head", fontName="BodyBold", fontSize=SIZE, leading=SIZE * 1.2),
    "head_c": ParagraphStyle("head_c", fontName="BodyBold", fontSize=SIZE, leading=SIZE * 1.2,
                             alignment=TA_CENTER),
    "head_r": ParagraphStyle("head_r", fontName="BodyBold", fontSize=SIZE, leading=SIZE * 1.2,
                             alignment=TA_RIGHT),
    "firm": ParagraphStyle("firm", fontName="BodyBold", fontSize=17, leading=21),
    "title": ParagraphStyle("title", fontName="BodyBold", fontSize=22, leading=26, alignment=TA_RIGHT),
    "right": ParagraphStyle("right", fontName="Body", fontSize=SIZE, leading=SIZE * 1.3,
                            alignment=TA_RIGHT),
    "h2": ParagraphStyle("h2", fontName="BodyBold", fontSize=SIZE + 2, leading=(SIZE + 2) * 1.3,
                         spaceBefore=4, spaceAfter=3),
}
GRID = colors.HexColor("#6E6E6E")
HEAD_BG = colors.HexColor("#D9D9D9")
TOT_BG = colors.HexColor("#EDEDED")


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tipo_cliente(breve):
    """Descrizione del tipo per il cliente, senza le note interne (es. «(h?)»)."""
    return breve.replace(" (h?)", "")


def num(d):
    return "" if d is None else euro(d).replace(" €", "")


def data_breve(periodo):
    """«19/11 → 22/11» oppure «19/11 13:00 → 22/11 17:00» -> (dal, al)."""
    dal, _, al = periodo.partition(" → ")
    return dal, al


LARGHEZZA = A4[0] - 32 * mm   # larghezza utile tra i margini
PAD = 4                       # spazio a destra e a sinistra nelle celle (pt)


def tabella_veicoli(ris, piu_fatture):
    intest = ["#", "Veicolo", "Tipo", "Dal", "Al", "Giorni", "€/giorno", "Totale €"]
    allinea = ["c", "l", "l", "c", "c", "c", "r", "r"]
    righe = []
    giorni_tot = 0
    for r in ris["righe"]:
        if r["annullata"]:
            continue
        nome = esc(r["veicolo"]) + (f" · {esc(r['targa'])}" if r["targa"] else "")
        if piu_fatture:
            nome += f'<br/><font size="{SIZE - 2}">fattura a {esc(r["intestatario"])}</font>'
        dal, al = data_breve(r["periodo"])
        if r["tipo_applicato"] == "diurna":
            giorni, tariffa = "in giornata", f"{num(r['tariffa_applicata'])} diurna"
        elif r["tipo_applicato"] == "forfait":
            giorni, tariffa = str(r["giorni"]), "forfait"
        else:
            giorni = "-" if r["giorni"] is None else str(r["giorni"])
            tariffa = num(r["tariffa_applicata"]) if r["tariffa_applicata"] is not None else "da conf."
        totale = num(r["totale"]) if r["totale"] is not None else "da confermare"
        if r["totale"] is not None and r["giorni"]:
            giorni_tot += r["giorni"]
        righe.append([str(len(righe) + 1), nome, esc(tipo_cliente(r["categoria_breve"])),
                      dal, al, giorni, tariffa, totale])
    totali = ["", "<b>Totale</b>", "", "", "", f"<b>{giorni_tot}</b>", "", f"<b>{num(ris['totale'])}</b>"]

    # larghezze: ogni colonna quanto il testo più largo; al Veicolo resta tutto il resto
    def largo(testo, bold=False):
        pulito = testo.replace("<b>", "").replace("</b>", "")
        return pdfmetrics.stringWidth(pulito, "BodyBold" if bold else "Body", SIZE)
    widths = []
    for c in range(len(intest)):
        if c == 1:
            widths.append(0)
            continue
        w = max([largo(intest[c], True), largo(totali[c], True)] + [largo(rr[c]) for rr in righe])
        widths.append(w + 2 * PAD + 3)
    widths[1] = LARGHEZZA - sum(widths)

    stili_testa = {"c": ST["head_c"], "l": ST["head"], "r": ST["head_r"]}
    stili_cella = {"c": ST["cell_c"], "l": ST["cell"], "r": ST["cell_r"]}
    rows = [[Paragraph(h, stili_testa[a]) for h, a in zip(intest, allinea)]]
    for rr in righe + [totali]:
        rows.append([Paragraph(v, stili_cella[a]) if v else "" for v, a in zip(rr, allinea)])
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, GRID),
        ("BOX", (0, 0), (-1, -1), 1.2, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.black),
        ("BACKGROUND", (0, -1), (-1, -1), TOT_BG),
        ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.black),
        ("SPAN", (1, -1), (4, -1)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), PAD),
        ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
    ]))
    return t


def tabella_iva(f, aliq):
    rows = [[Paragraph("Totale IVA inclusa", ST["cell"]), Paragraph(f"<b>{euro(f['totale'])}</b>", ST["cell_r"])],
            [Paragraph("Imponibile", ST["cell"]), Paragraph(euro(f["imponibile"]), ST["cell_r"])],
            [Paragraph(f"IVA {aliq}%", ST["cell"]), Paragraph(euro(f["iva"]), ST["cell_r"])]]
    t = Table(rows, colWidths=[52 * mm, 32 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.0, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, GRID),
        ("BACKGROUND", (0, 0), (-1, 0), TOT_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def piede(canvas, doc):
    canvas.saveState()
    canvas.setFont("Body", 9)
    canvas.setFillColor(colors.HexColor("#444444"))
    canvas.drawString(16 * mm, 9 * mm, " · ".join(FORNITORE))
    canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"pagina {doc.page}")
    canvas.restoreState()


def main(dati_path, out):
    with open(dati_path, encoding="utf-8") as fh:
        dati = json.load(fh)
    ris = calcola(dati)
    aliq = ris["aliquota_iva"]
    piu_fatture = len(ris["fatture"]) > 1

    intest = Table([[
        [Paragraph(FORNITORE[0], ST["firm"]), Paragraph(FORNITORE[1], ST["norm"]),
         Paragraph(FORNITORE[2], ST["small"])],
        [Paragraph("PREVENTIVO", ST["title"]),
         Paragraph(f"del {esc(ris['data_preventivo'])}", ST["right"])],
    ]], colWidths=[105 * mm, 73 * mm])
    intest.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.black),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    story = [intest, Spacer(1, 7 * mm),
             Paragraph(f"<b>Cliente:</b> {esc(ris['cliente'])}"
                       + (f" · {esc(ris['email'])}" if ris["email"] else ""), ST["norm"])]
    if dati.get("oggetto"):
        story.append(Paragraph(f"<b>Oggetto:</b> {esc(dati['oggetto'])}", ST["norm"]))
    story += [Spacer(1, 4 * mm), tabella_veicoli(ris, piu_fatture), Spacer(1, 4 * mm)]

    # riepilogo per tariffa
    righe_tar = []
    for g in ris["per_tariffa"]:
        cat = {"Vettura (misura non indicata)": "Auto",
               "Furgone (altezza da verificare)": "Furgone"}.get(g["categoria"], g["categoria"])
        if g["tipo"] == "diurna":
            righe_tar.append(f"{cat}: {g['veicoli']} × tariffa diurna {euro(g['tariffa'])} = {euro(g['totale'])}")
        elif g["tipo"] == "forfait":
            righe_tar.append(f"{cat}: {g['veicoli']} a forfait = {euro(g['totale'])}")
        else:
            righe_tar.append(f"{cat}: {g['veicoli']} {'veicolo' if g['veicoli'] == 1 else 'veicoli'}, "
                             f"{g['giorni']} giorni × {euro(g['tariffa'])} = {euro(g['totale'])}")
    blocco = [Paragraph("Riepilogo", ST["h2"])] + [Paragraph(esc(t), ST["norm"]) for t in righe_tar]
    story.append(KeepTogether(blocco))
    story.append(Spacer(1, 2 * mm))

    for f in ris["fatture"]:
        titolo = f"Fattura a {esc(f['intestatario'])}" if piu_fatture else "Importi"
        split = (f"In caso di scissione dei pagamenti (split payment, art. 17-ter DPR 633/1972) "
                 f"il cliente paga al parcheggio l'imponibile di {euro(f['imponibile'])} e versa l'IVA "
                 f"di {euro(f['iva'])} direttamente all'Erario.")
        story.append(KeepTogether([Paragraph(titolo, ST["h2"]), tabella_iva(f, aliq), Spacer(1, 2 * mm),
                                   Paragraph(split, ST["small"])]))
        story.append(Spacer(1, 2 * mm))
    if piu_fatture:
        story.append(Paragraph(f"<b>Totale preventivo: {euro(ris['totale'])}</b> "
                               f"(imponibile {euro(ris['imponibile'])} + IVA {euro(ris['iva'])})", ST["norm"]))
        story.append(Spacer(1, 3 * mm))

    note = ["Tariffa giornaliera con notte inclusa: i giorni sono le notti di sosta "
            "(data di uscita meno data di arrivo).",
            f"Prezzi IVA {aliq}% inclusa." if ris["prezzi_iva_inclusa"] else f"Prezzi IVA {aliq}% esclusa."]
    if any(r["tipo_applicato"] == "diurna" for r in ris["righe"]):
        note.append("Sosta in giornata: tariffa diurna fino a 8 ore, con uscita entro le 20:00.")
    if dati.get("nota"):
        note.append(dati["nota"])
    story.append(KeepTogether([Paragraph("Note", ST["h2"])] +
                              [Paragraph("· " + esc(t), ST["small"]) for t in note]))

    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=18 * mm,
                            title=f"Preventivo {ris['cliente']}", author=FORNITORE[0],
                            creator="Sorzolupo2")
    doc.build(story, onFirstPage=piede, onLaterPages=piede)
    print(f"PDF creato: {out} · totale {euro(ris['totale'])} "
          f"(imponibile {euro(ris['imponibile'])} + IVA {euro(ris['iva'])}) · "
          f"{datetime.now():%d/%m/%Y %H:%M}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
