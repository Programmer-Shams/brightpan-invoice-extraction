"""Generates the sample invoices for this project and their ground-truth JSON.
All vendors, addresses and numbers are test data. Re-run to regenerate: python scripts/make_samples.py"""
import json, random, os, io
from decimal import Decimal, ROUND_HALF_UP
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw
import subprocess, numpy as np

random.seed(42)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S, T = os.path.join(ROOT, "samples"), os.path.join(ROOT, "truth")
BUYER = ["Brightpan Kitchen Supply", "1450 Harmon Ave", "Columbus, OH 43223", "accounts@brightpan.example"]
D = lambda x: Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

VENDORS = {
 "ferro": ("Ferro Metalworks Inc.", ["88 Foundry Rd", "Youngstown, OH 44502"]),
 "pacpack": ("Pacific Packaging Co.", ["2100 Harbor Way", "Oakland, CA 94607"]),
 "lakeline": ("Lakeline Freight LLC", ["7 Terminal Dr", "Toledo, OH 43605"]),
 "brightsteel": ("BrightSteel Components", ["400 Mill St", "Pittsburgh, PA 15222"]),
 "northcoat": ("NorthCoat Finishes", ["55 Kiln Ave", "Erie, PA 16501"]),
 "maple": ("Maple Leaf Ceramics Ltd.", ["310 Rue Dufferin", "Montreal, QC H2X 1Y2"]),
 "pixelpro": ("PixelPro Studio", ["19 Market St, Suite 4", "Columbus, OH 43215"]),
 "officehub": ("OfficeHub Supplies", ["900 Commerce Pkwy", "Dublin, OH 43017"]),
}

def items(spec):
    out = []
    for desc, q, p in spec:
        out.append({"description": desc, "quantity": q, "unit_price": float(D(p)), "amount": float(D(Decimal(str(q)) * D(p)))})
    return out

DOCS = [
 # id, vendor, inv_no, date, due, currency, po, items, tax_rate, shipping, discount, template, variant, notes, override_total
 ("INV01","ferro","FM-10421","2026-09-02","2026-10-02","USD","PO-5501",[("12-inch carbon steel skillet blank",200,9.40),("10-inch carbon steel skillet blank",150,7.85)],0.0,145.00,0,"A","digital","",None),
 ("INV02","pacpack","PP-88310","2026-09-05","2026-10-05","USD","PO-5502",[("Retail box, skillet, printed 4-color",500,0.62),("Molded pulp insert",500,0.21),("Shipping carton 18x14x6",120,1.10)],0.0,0,0,"B","digital","",None),
 ("INV03","lakeline","LF-2026-0915","2026-09-15","2026-09-30","USD",None,[("LTL freight Youngstown-Columbus, 6 pallets",1,612.00),("Liftgate service",1,75.00),("Fuel surcharge",1,48.84)],0.0,0,0,"C","digital","Net 15",None),
 ("INV04","brightsteel","BSC-7781","2026-09-08","2026-10-08","USD","PO-5503",[("Stainless rivet set (pack of 1,000)",8,64.50),("Handle assembly, Pro line",400,3.95)],0.0575,60.00,0,"A","digital","Ohio sales tax 5.75%",None),
 ("INV05","northcoat","NC-40912","2026-09-10","2026-10-10","USD","PO-5504",[("Nonstick coating, 20 L drum",4,486.00),("Primer, 5 L",6,72.40)],0.0,0,0,"B","digital","",None),
 ("INV06","maple","MLC-2290","2026-09-12","2026-10-27","CAD","PO-5505",[("Ceramic spoon rest, glazed",300,3.20),("Ceramic utensil crock",150,8.75)],0.05,95.00,0,"C","digital","Canadian dollars; GST 5%",None),
 ("INV07","pixelpro","PXS-118","2026-09-18","2026-10-18","USD",None,[("Product photography, half day",2,450.00),("Image retouching per image",40,6.00)],0.0,0,90.00,"A","digital","Includes a discount line",None),
 ("INV08","officehub","OH-552201","2026-09-20","2026-10-20","USD",None,[("Thermal shipping labels 4x6 (roll)",30,12.99),("Packing tape 2-inch (6-pack)",20,14.49),("Printer toner, black",2,89.00)],0.0725,0,0,"B","digital","Sales tax 7.25%",None),
 ("INV09","ferro","FM-10498","2026-09-22","2026-10-22","USD","PO-5510",[("Cast iron skillet blank 12-inch",300,11.20),("Cast iron skillet blank 10-inch",250,9.10),("Pattern tooling fee",1,350.00),("Pallet charge",9,18.00)] + [(f"Sample casting lot {i}",1,25.00) for i in range(1,41)],0.0,220.00,0,"A","multipage","Line items continue on page 2",None),
 ("INV10","pacpack","PP-88377","2026-09-25","2026-10-25","USD","PO-5511",[("Retail box, knife set, printed",300,0.95),("Foam insert, knife set",300,0.40)],0.0,35.00,0,"B","digital","Printed total is wrong on purpose (vendor error)",None),
 ("INV11","lakeline","LF-2026-0928","2026-09-28","2026-10-13","USD",None,[("LTL freight Pittsburgh-Columbus, 3 pallets",1,398.00),("Fuel surcharge",1,31.84)],0.0,0,0,"C","scan","Scanned, slight rotation",None),
 ("INV12","brightsteel","BSC-7802","2026-09-29","2026-10-29","USD","PO-5512",[("Lid knob, stainless",600,0.88),("Lid rim, 10-inch",300,2.40)],0.0575,40.00,0,"A","scan","Scanned, low contrast",None),
 ("INV13","northcoat","NC-40955","2026-10-01","2026-10-31","USD","PO-5513",[("Nonstick coating, 20 L drum",2,486.00)],0.0,55.00,0,"B","scan","Scanned",None),
 ("INV14","officehub","OH-552288","2026-10-02","2026-11-01","USD",None,[("Copy paper, case",5,42.00),("Shipping scale",1,129.00)],0.0725,0,0,"C","scan","Scanned, noisy",None),
 ("INV15","pixelpro","PXS-131","2026-10-03","2026-11-02","USD",None,[("Short product video, 30 s",3,380.00)],0.0,0,0,"A","photo","Phone photo, perspective and shadow",None),
 ("INV16","ferro","FM-10421","2026-10-04","2026-11-03","USD","PO-5501",[("12-inch carbon steel skillet blank",200,9.40),("10-inch carbon steel skillet blank",150,7.85)],0.0,145.00,0,"A","photo","Duplicate of INV01 (same vendor and invoice number), resent as a phone photo",None),
 ("INV17","maple","MLC-2301","2026-10-05","2026-11-19","CAD","PO-5514",[("Ceramic spoon rest, glazed",200,3.20)],0.05,95.00,0,"C","photo","Phone photo, Canadian dollars",None),
 ("INV18","brightsteel","BSC-7815","2026-10-07","2026-11-06","USD","PO-5515",[("Handle assembly, Pro line",250,3.95)],0.0,30.00,0,"B","digital","Tax-exempt (resale certificate on file)",None),
 ("RCPT01","officehub","R-0098812","2026-10-08",None,"USD",None,[("Bubble wrap roll 12in x 175ft",2,24.99),("Box cutter",3,6.49)],0.0725,0,0,"R","receipt","Store receipt, narrow format",None),
 ("RCPT02","lakeline","R-LF-5521","2026-10-09",None,"USD",None,[("Pallet jack rental, 1 day",1,65.00)],0.0,0,0,"R","receipt","Receipt photo",None),
]

def totals(it, tax_rate, shipping, discount):
    sub = sum(D(x["amount"]) for x in it)
    taxable = sub - D(discount)
    tax = D(taxable * Decimal(str(tax_rate)))
    total = taxable + tax + D(shipping)
    return sub, tax, total

def draw_doc(path, v, d, it, sub, tax, total, printed_total, tpl):
    vname, vaddr = VENDORS[v]
    c = canvas.Canvas(path, pagesize=letter); W, H = letter
    labels = {"A": ("INVOICE", "Invoice #", "Date", "Due Date", "PO #"),
              "B": ("TAX INVOICE", "Inv No.", "Issue date", "Payment due", "Your PO"),
              "C": ("Invoice", "Number", "Bill Date", "Due", "Ref")}[tpl]
    def header():
        if tpl == "B":
            c.setFont("Helvetica-Bold", 20); c.drawRightString(W-0.75*inch, H-1*inch, labels[0])
            c.setFont("Helvetica-Bold", 12); c.drawString(0.75*inch, H-1*inch, vname)
        else:
            c.setFont("Helvetica-Bold", 16); c.drawString(0.75*inch, H-0.9*inch, vname)
            c.setFont("Helvetica-Bold", 18 if tpl=="A" else 14); c.drawRightString(W-0.75*inch, H-0.9*inch, labels[0])
        c.setFont("Helvetica", 9)
        for i, line in enumerate(vaddr): c.drawString(0.75*inch, H-1.15*inch-i*12, line)
    header()
    y0 = H-1.9*inch
    c.setFont("Helvetica-Bold", 9); c.drawString(0.75*inch, y0, "Bill to")
    c.setFont("Helvetica", 9)
    for i, line in enumerate(BUYER): c.drawString(0.75*inch, y0-12-i*12, line)
    meta = [(labels[1], d["invoice_number"]), (labels[2], d["invoice_date"])]
    if d["due_date"]: meta.append((labels[3], d["due_date"]))
    if d["po_number"]: meta.append((labels[4], d["po_number"]))
    meta.append(("Currency", d["currency"]))
    for i, (k, val) in enumerate(meta):
        c.setFont("Helvetica-Bold", 9); c.drawString(4.6*inch, y0-i*13, k)
        c.setFont("Helvetica", 9); c.drawRightString(W-0.75*inch, y0-i*13, val)
    y = y0 - 1.3*inch
    cols = [0.75*inch, 4.4*inch, 5.4*inch, W-0.75*inch]
    def thead(y):
        c.setFont("Helvetica-Bold", 9)
        c.drawString(cols[0], y, "Description"); c.drawRightString(cols[1]+0.4*inch, y, "Qty")
        c.drawRightString(cols[2]+0.6*inch, y, "Unit price"); c.drawRightString(cols[3], y, "Amount")
        c.line(cols[0], y-4, cols[3], y-4)
    thead(y); y -= 18; c.setFont("Helvetica", 9); page = 1
    for x in it:
        if y < 1.6*inch:
            c.setFont("Helvetica", 8); c.drawRightString(W-0.75*inch, 0.6*inch, f"Page {page} of 2 — continued"); c.showPage(); page += 1
            c.setFont("Helvetica-Bold", 10); c.drawString(0.75*inch, H-0.8*inch, f"{vname} — {labels[1]} {d['invoice_number']} (continued)")
            y = H-1.3*inch; thead(y); y -= 18; c.setFont("Helvetica", 9)
        c.drawString(cols[0], y, x["description"]); c.drawRightString(cols[1]+0.4*inch, y, f"{x['quantity']:,}")
        c.drawRightString(cols[2]+0.6*inch, y, f"{x['unit_price']:,.2f}"); c.drawRightString(cols[3], y, f"{x['amount']:,.2f}")
        y -= 14
    c.line(4.4*inch, y+9, cols[3], y+9); y -= 8
    rows = [("Subtotal", d["subtotal"])]
    if d["discount"]: rows.append(("Discount", -d["discount"]))
    if d["tax"]: rows.append((f"Tax ({d['tax_rate']*100:g}%)", d["tax"]))
    elif d.get("tax_exempt"): rows.append(("Tax (exempt)", 0.0))
    if d["shipping"]: rows.append(("Shipping", d["shipping"]))
    rows.append((f"TOTAL {d['currency']}", printed_total))
    for k, val in rows:
        c.setFont("Helvetica-Bold" if k.startswith("TOTAL") else "Helvetica", 10 if k.startswith("TOTAL") else 9)
        c.drawString(4.6*inch, y, k); c.drawRightString(cols[3], y, f"{val:,.2f}"); y -= 14
    c.setFont("Helvetica", 8)
    terms = "Terms: Net 15" if "Net 15" in d["notes"] else ("Terms: Net 45" if d["currency"]=="CAD" else "Terms: Net 30")
    c.drawString(0.75*inch, 0.9*inch, terms + "   |   Thank you for your business.")
    if page == 2: c.drawRightString(W-0.75*inch, 0.6*inch, "Page 2 of 2")
    c.save()

def draw_receipt(path, v, d, it, printed_total):
    vname, vaddr = VENDORS[v]
    img = Image.new("L", (420, 640 + 22*len(it)), 248); g = ImageDraw.Draw(img)
    yy = 20
    for line in [vname.upper(), *vaddr, "", f"Receipt {d['invoice_number']}", f"Date {d['invoice_date']}", "-"*38]:
        g.text((20, yy), line, fill=20); yy += 20
    for x in it:
        g.text((20, yy), f"{x['quantity']} x {x['description'][:26]}", fill=20); yy += 18
        g.text((260, yy), f"{x['amount']:>10.2f}", fill=20); yy += 20
    g.text((20, yy), "-"*38, fill=20); yy += 20
    for k, val in [("SUBTOTAL", d["subtotal"]), ("TAX", d["tax"]), ("TOTAL USD", printed_total)]:
        g.text((20, yy), k, fill=20); g.text((260, yy), f"{val:>10.2f}", fill=20); yy += 20
    g.text((20, yy+10), "PAID - CARD ****", fill=20)
    img = img.resize((img.width*2, img.height*2))
    return img

def degrade(img, kind):
    img = img.convert("L")
    if kind == "scan":
        img = img.rotate(random.uniform(-1.6, 1.6), expand=True, fillcolor=255)
        img = ImageEnhance.Contrast(img).enhance(random.uniform(0.65, 0.8))
        arr = np.array(img).astype(np.int16) + np.random.normal(0, 9, np.array(img).shape).astype(np.int16)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    else:
        w, h = img.size
        img = img.transform((w, h), Image.PERSPECTIVE, (1, 0.04, -40, 0.01, 1.02, -20, 0.00002, 0.00004), fillcolor=200)
        grad = Image.linear_gradient("L").resize((w, h)).point(lambda p: 255 - p//3)
        img = Image.composite(img, Image.new("L", (w, h), 120), grad).filter(ImageFilter.GaussianBlur(1.0))
        img = img.rotate(random.uniform(-4, 4), expand=True, fillcolor=90)
    return img

manifest = []
for (did, v, no, date, due, cur, po, spec, tr, ship, disc, tpl, variant, notes, _) in DOCS:
    it = items(spec)
    sub, tax, total = totals(it, tr, ship, disc)
    d = {"document_id": did, "vendor_name": VENDORS[v][0], "invoice_number": no, "invoice_date": date, "due_date": due,
         "currency": cur, "po_number": po, "line_items": it, "subtotal": float(sub), "discount": float(D(disc)),
         "tax_rate": tr, "tax": float(tax), "shipping": float(D(ship)), "total": float(total), "notes": notes,
         "tax_exempt": "exempt" in notes}
    printed_total = float(total)
    expected_flags = []
    if did == "INV10":
        printed_total = float(total + D(50))
        expected_flags.append("totals_mismatch")
    if did == "INV16": expected_flags.append("duplicate_invoice")
    d["computed_total"] = d["total"]
    d["total"] = printed_total  # the extractor reports what is printed; validation compares with computed_total
    d["expected_flags"] = expected_flags
    d["expected_route"] = "review" if expected_flags else "auto"
    if variant == "receipt":
        img = draw_receipt(None, v, d, it, printed_total)
        ext = "png" if did == "RCPT01" else "jpg"
        if ext == "jpg": img = degrade(img, "photo")
        fname = f"{did}.{ext}"; img.save(os.path.join(S, fname), quality=85)
    else:
        pdf = os.path.join(S, f"{did}.pdf") if variant in ("digital", "multipage") else os.path.join("/tmp", f"{did}.pdf")
        draw_doc(pdf, v, d, it, sub, tax, total, printed_total, tpl)
        if variant in ("digital", "multipage"):
            fname = f"{did}.pdf"
        else:
            subprocess.run(["pdftoppm", "-r", "150", "-png", "-singlefile", pdf, f"/tmp/{did}"], check=True)
            img = degrade(Image.open(f"/tmp/{did}.png"), "scan" if variant == "scan" else "photo")
            if variant == "scan":
                fname = f"{did}.pdf"; img.convert("RGB").save(os.path.join(S, fname), "PDF", resolution=150)
            else:
                fname = f"{did}.jpg"; img.convert("RGB").save(os.path.join(S, fname), quality=82)
    d["file"] = fname; d["format"] = variant
    for k in ("notes",): pass
    json.dump(d, open(os.path.join(T, f"{did}.json"), "w"), indent=2)
    manifest.append({"document_id": did, "file": fname, "format": variant, "vendor": VENDORS[v][0], "currency": cur,
                     "total": d["total"], "computed_total": d["computed_total"], "expected_route": d["expected_route"], "expected_flags": ";".join(expected_flags), "notes": notes})
import csv
with open(os.path.join(ROOT, "truth", "manifest.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=manifest[0].keys()); w.writeheader(); w.writerows(manifest)
print(len(manifest), "documents")
