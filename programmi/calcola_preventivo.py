#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sorzolupo2 - calcolo del preventivo del parcheggio
Parcheggio Trieste - via Milano 2 - Trieste

Uso:
    python3 calcola_preventivo.py dati.json [risultato.json]

Stampa il preventivo come testo (tabelle Markdown) e, se indicato,
salva il risultato completo in risultato.json.

Formato di dati.json
--------------------
{
  "cliente": "Esempio Srl",
  "email": "info@esempio.it",
  "data_preventivo": "21/11/2026",
  "aliquota_iva": 22,             (facoltativo, 22)
  "prezzi_iva_inclusa": true,     (facoltativo, true: le tariffe delle conferme sono IVA inclusa)
  "righe": [
    {
      "veicolo": "Mario Rossi",             ospite/conducente o descrizione del veicolo
      "targa": "AB123CD",                   facoltativo
      "modello": "",                        facoltativo
      "categoria": "grande",                codice di CATEGORIE (sotto)
      "arrivo": "26-11-2026 13:00",         gg-mm-aaaa hh:mm, come Jotform (va bene anche gg/mm/aaaa)
      "partenza": "28-11-2026 17:00",
      "tariffa": 35.00,                     euro al giorno della conferma; per "forfait" l'importo totale
      "tipo": "giornaliera",                giornaliera (default) | forfait
      "tariffa_diurna": null,               facoltativo: sostituisce quella del tariffario
      "intestatario": "Esempio Srl",        facoltativo: a chi va la fattura (default: il cliente)
      "fonte": "conferma Gmail 20/11/2026 14:34",
      "annullata": false,
      "note": ""
    }
  ]
}

Regole di Marco (21/11/2026)
- Le tariffe delle conferme sono IVA 22% inclusa: imponibile = totale / 1,22
  arrotondato al centesimo, IVA = totale - imponibile.
- Giorni = solo le notti: data di partenza meno data di arrivo, qualunque sia
  l'ora di uscita (anche dopo il check-out delle 12).
- Sosta in giornata: tariffa diurna del tariffario (fino a 8 ore con uscita
  entro le 20:00: 20 euro vetture, 10 euro moto). Se la sosta supera le 8 ore,
  finisce dopo le 20 o la categoria non ha tariffa diurna: 1 giorno alla
  tariffa giornaliera, segnalato tra le cose da verificare.
- Ogni intestatario ha il suo riepilogo (una fattura): l'IVA si calcola sul
  totale della fattura; l'eventuale centesimo di differenza tra le righe va
  sulla riga piu' grande, cosi' le righe tornano con il totale.
- Split payment (art. 17-ter DPR 633/1972): il cliente paga al parcheggio
  l'imponibile e versa l'IVA direttamente all'Erario.
"""

import json
import sys
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")

# codice: (descrizione, descrizione breve, tariffa diurna del tariffario o None)
CATEGORIE = {
    "maxi_furgone":   ("Maxi furgone (> 2 m)", "Maxi furgone", None),
    "furgone":        ("Furgone (< 2 m)", "Furgone", None),
    "furgone_h":      ("Furgone (altezza da verificare)", "Furgone (h?)", None),
    "elevato_valore": ("Vettura di elevato valore", "Elevato valore", None),
    "elettrica":      ("Vettura elettrica", "Elettrica", Decimal("20.00")),
    "grande":         ("Vettura grande (> 4,60 m)", "Grande", Decimal("20.00")),
    "medio_piccola":  ("Vettura medio-piccola (< 4,60 m)", "Medio-piccola", Decimal("20.00")),
    "auto":           ("Vettura (misura non indicata)", "Auto", Decimal("20.00")),
    "moto":           ("Motociclo", "Moto", Decimal("10.00")),
    "ebike":          ("E-bike", "E-bike", None),
    "bici":           ("Bicicletta", "Bici", None),
}

FORMATI_DATA = ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M",
                "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")


def soldi(x):
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def euro(d):
    if d is None:
        return "-"
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


def leggi_data(testo):
    """Restituisce (datetime, ha_ora) oppure (None, False)."""
    if not testo:
        return None, False
    testo = str(testo).strip()
    for f in FORMATI_DATA:
        try:
            return datetime.strptime(testo, f), ("%H" in f)
        except ValueError:
            continue
    return None, False


def gg_mm(dt, ha_ora):
    if dt is None:
        return "?"
    return dt.strftime("%d/%m %H:%M") if ha_ora else dt.strftime("%d/%m")


def calcola_riga(r):
    cat = r.get("categoria", "")
    desc, breve, diurna_tariffario = CATEGORIE.get(cat, (cat or "?", cat or "?", None))
    avvisi = []
    arr, arr_ora = leggi_data(r.get("arrivo"))
    dep, dep_ora = leggi_data(r.get("partenza"))
    tipo = (r.get("tipo") or "giornaliera").lower()
    tariffa = soldi(r["tariffa"]) if r.get("tariffa") not in (None, "") else None
    out = {
        "veicolo": r.get("veicolo", ""), "targa": r.get("targa", ""),
        "modello": r.get("modello", ""), "categoria": desc, "categoria_breve": breve,
        "periodo": f"{gg_mm(arr, arr_ora)} → {gg_mm(dep, dep_ora)}",
        "intestatario": r.get("intestatario"), "fonte": r.get("fonte", ""),
        "note": r.get("note", ""), "annullata": bool(r.get("annullata")),
        "giorni": None, "tipo_applicato": tipo, "tariffa_applicata": tariffa,
        "totale": None, "imponibile": None, "iva": None, "avvisi": avvisi,
    }
    if cat not in CATEGORIE:
        avvisi.append(f"Categoria «{cat}» non riconosciuta")
    if cat == "furgone_h":
        avvisi.append("Furgone senza altezza: maxi se oltre 2 m")
    if tariffa is None:
        avvisi.append("Tariffa non confermata in e-mail")
    if arr is None or dep is None:
        avvisi.append("Verificare le date di arrivo e partenza")
        return out
    notti = (dep.date() - arr.date()).days
    if notti < 0:
        avvisi.append("Partenza prima dell'arrivo: verificare")
        return out
    if tipo == "forfait":
        out["giorni"] = notti
        out["totale"] = tariffa
        return out
    if notti == 0:
        diurna = soldi(r["tariffa_diurna"]) if r.get("tariffa_diurna") not in (None, "") else diurna_tariffario
        ore = (dep - arr).total_seconds() / 3600
        if diurna is not None and arr_ora and dep_ora and ore <= 8 and dep.time() <= time(20, 0):
            out["giorni"] = 0
            out["tipo_applicato"] = "diurna"
            out["tariffa_applicata"] = diurna
            out["totale"] = diurna
            return out
        if diurna is None:
            motivo = "tariffa diurna non prevista per questa categoria"
        elif not (arr_ora and dep_ora):
            motivo = "orari mancanti"
        else:
            motivo = "oltre 8 ore o uscita dopo le 20"
        avvisi.append(f"Sosta in giornata ({motivo}): conteggiato 1 giorno")
        out["giorni"] = 1
        out["totale"] = tariffa
        return out
    out["giorni"] = notti
    out["totale"] = (tariffa * notti).quantize(CENT) if tariffa is not None else None
    return out


def scorpora(totale, aliq):
    imponibile = (totale / (1 + aliq)).quantize(CENT, rounding=ROUND_HALF_UP)
    return imponibile, totale - imponibile


def calcola(dati):
    aliq = Decimal(str(dati.get("aliquota_iva", 22))) / 100
    iva_inclusa = dati.get("prezzi_iva_inclusa", True)
    cliente = dati.get("cliente", "")
    righe = [calcola_riga(r) for r in dati.get("righe", [])]
    for r in righe:
        if not r["intestatario"]:
            r["intestatario"] = cliente

    fatture = []
    for nome in dict.fromkeys(r["intestatario"] for r in righe):
        valide = [r for r in righe if r["intestatario"] == nome
                  and not r["annullata"] and r["totale"] is not None]
        if not valide:
            continue
        base = sum((r["totale"] for r in valide), Decimal("0"))
        if iva_inclusa:
            totale = base
            imponibile, iva = scorpora(totale, aliq)
            for r in valide:
                r["imponibile"], r["iva"] = scorpora(r["totale"], aliq)
            diff = imponibile - sum(r["imponibile"] for r in valide)
            if diff:
                grande = max(valide, key=lambda x: x["totale"])
                grande["imponibile"] += diff
                grande["iva"] -= diff
        else:
            imponibile = base
            iva = (imponibile * aliq).quantize(CENT, rounding=ROUND_HALF_UP)
            totale = imponibile + iva
            for r in valide:
                r["imponibile"] = r["totale"]
                r["iva"] = (r["totale"] * aliq).quantize(CENT, rounding=ROUND_HALF_UP)
            diff = iva - sum(r["iva"] for r in valide)
            if diff:
                max(valide, key=lambda x: x["totale"])["iva"] += diff
        # controllo: l'IVA non deve scostarsi piu' di 1 centesimo da imponibile x aliquota
        assert abs(iva - imponibile * aliq) <= CENT, (nome, imponibile, iva)
        assert sum(r["imponibile"] for r in valide) == imponibile, nome
        assert sum(r["iva"] for r in valide) == iva, nome
        fatture.append({
            "intestatario": nome, "veicoli": len(valide),
            "totale": totale, "imponibile": imponibile, "iva": iva,
            "split_da_incassare": imponibile, "split_iva_all_erario": iva,
        })

    # riepilogo per categoria e tariffa applicata
    gruppi = {}
    for r in righe:
        if r["annullata"] or r["totale"] is None:
            continue
        chiave = (r["categoria"], r["tipo_applicato"], r["tariffa_applicata"])
        g = gruppi.setdefault(chiave, {"categoria": r["categoria"], "tipo": r["tipo_applicato"],
                                       "tariffa": r["tariffa_applicata"], "veicoli": 0,
                                       "giorni": 0, "totale": Decimal("0")})
        g["veicoli"] += 1
        g["giorni"] += r["giorni"] or 0
        g["totale"] += r["totale"]

    return {
        "cliente": cliente, "email": dati.get("email", ""),
        "data_preventivo": dati.get("data_preventivo", datetime.now().strftime("%d/%m/%Y")),
        "aliquota_iva": dati.get("aliquota_iva", 22), "prezzi_iva_inclusa": iva_inclusa,
        "righe": righe, "per_tariffa": list(gruppi.values()), "fatture": fatture,
        "totale": sum((f["totale"] for f in fatture), Decimal("0")),
        "imponibile": sum((f["imponibile"] for f in fatture), Decimal("0")),
        "iva": sum((f["iva"] for f in fatture), Decimal("0")),
    }


def tariffa_testo(r_or_g):
    tipo = r_or_g.get("tipo_applicato", r_or_g.get("tipo"))
    t = r_or_g.get("tariffa_applicata", r_or_g.get("tariffa"))
    if t is None:
        return "da confermare"
    if tipo == "forfait":
        return f"{euro(t)} forfait"
    if tipo == "diurna":
        return f"{euro(t)} diurna"
    return f"{euro(t)}/giorno"


def stampa(ris):
    aliq = ris["aliquota_iva"]
    nota_iva = f"IVA {aliq}% inclusa" if ris["prezzi_iva_inclusa"] else f"IVA {aliq}% esclusa"
    piu_fatture = len({r["intestatario"] for r in ris["righe"]}) > 1
    righe_txt = [
        f"# Preventivo · {ris['cliente']}",
        f"{ris['email']} · {ris['data_preventivo']} · Parcheggio Trieste, via Milano 2, Trieste · tariffe {nota_iva}",
        "",
        "## Veicoli",
        "| # | Veicolo | Categoria | Periodo | Giorni | Tariffa | Totale |" + (" Fattura a |" if piu_fatture else ""),
        "|---|---|---|---|---|---|---|" + ("---|" if piu_fatture else ""),
    ]
    for i, r in enumerate(ris["righe"], 1):
        nome = r["veicolo"] + (f" ({r['targa']})" if r["targa"] else "")
        totale = euro(r["totale"])
        if r["annullata"]:
            nome = "ANNULLATA · " + nome
            totale = f"~~{totale}~~ escluso" if r["totale"] is not None else "escluso"
        giorni = "-" if r["giorni"] is None else ("in giornata" if r["tipo_applicato"] == "diurna" else str(r["giorni"]))
        righe_txt.append(f"| {i} | {nome} | {r['categoria_breve']} | {r['periodo']} | {giorni} | "
                         f"{tariffa_testo(r)} | {totale} |" + (f" {r['intestatario']} |" if piu_fatture else ""))
    righe_txt += ["", "## Per tariffa applicata",
                  "| Categoria | Veicoli | Giorni | Tariffa | Totale |", "|---|---|---|---|---|"]
    for g in ris["per_tariffa"]:
        giorni = "in giornata" if g["tipo"] == "diurna" else str(g["giorni"])
        righe_txt.append(f"| {g['categoria']} | {g['veicoli']} | {giorni} | {tariffa_testo(g)} | {euro(g['totale'])} |")
    for f in ris["fatture"]:
        righe_txt += [
            "", f"## Fattura a {f['intestatario']} ({f['veicoli']} {'veicolo' if f['veicoli'] == 1 else 'veicoli'})",
            f"- Totale IVA inclusa: {euro(f['totale'])}",
            f"- Imponibile: {euro(f['imponibile'])}",
            f"- IVA {aliq}%: {euro(f['iva'])}",
            f"- Fattura normale: il cliente paga {euro(f['totale'])}",
            f"- Split payment: il cliente paga al parcheggio {euro(f['split_da_incassare'])} "
            f"e versa {euro(f['split_iva_all_erario'])} di IVA all'Erario",
        ]
    if len(ris["fatture"]) > 1:
        righe_txt += ["", f"**Totale preventivo: {euro(ris['totale'])}** "
                          f"(imponibile {euro(ris['imponibile'])} + IVA {euro(ris['iva'])})"]
    avvisi = [(i, a) for i, r in enumerate(ris["righe"], 1) for a in r["avvisi"]]
    if avvisi:
        righe_txt += ["", "## Da verificare"] + [f"- riga {i}: {a}" for i, a in avvisi]
    fonti = [(i, r["fonte"]) for i, r in enumerate(ris["righe"], 1) if r["fonte"]]
    if fonti:
        righe_txt += ["", "## Fonti"] + [f"- riga {i}: {f}" for i, f in fonti]
    print("\n".join(righe_txt))


def in_json(o):
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(type(o))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as fh:
        risultato = calcola(json.load(fh))
    stampa(risultato)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as fh:
            json.dump(risultato, fh, ensure_ascii=False, indent=2, default=in_json)
