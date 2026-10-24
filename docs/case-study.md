# Case study: invoices and receipts to clean accounts-payable data

## The problem

Brightpan Kitchen Supply (the store in this portfolio project) gets supplier invoices and receipts by email
and by upload. Some are PDFs, some are scans, some are phone photos taken at a loading dock. Someone in accounts
payable typed every one into a spreadsheet: vendor, invoice number, dates, every line, the totals. That is slow,
and it lets two expensive mistakes through: an invoice whose total doesn't match its own lines, and the same invoice
paid twice.

## What was built

A system that reads each document as it arrives and only asks a person about the doubtful ones.

- **Two ways in.** Drag a file into the web app, or email it to the AP address. Both land in the same queue within
  seconds.
- **Reads any format.** Digital PDFs, scans and phone photos, including a two-page invoice and Canadian-dollar
  bills. Every line item is captured, with a confidence score per field.
- **Checks the math, never fixes it.** The line items must add up to the subtotal, and subtotal − discount + tax +
  shipping must equal the printed total, to the cent. If a vendor's total is wrong, the system keeps what is printed
  and flags it.
- **Catches duplicates.** An invoice number already received from the same vendor is stopped, even when it is
  resent as a photo.
- **Never invents.** A receipt with no due date gets no due date. A Canadian invoice stays in CAD.
- **Files the clean ones, routes the rest.** Clean documents become a row in the Google Sheet AP register.
  Doubtful ones go to a review queue in the web app and to Slack, with the reason in plain words ("printed total is
  over by USD 50.00"). Approving one files it.

## How it was tested

Before the system existed, a test harness was built and run against an empty stub, so every number is measured
from the same baseline. It uploads 20 test documents (10 digital PDFs, a two-page invoice, 4 scans, 3 phone photos,
2 receipts) to the running system, waits for each to finish and compares every field with an answer key. Two errors
were planted on purpose: an invoice whose printed total is $50 too high, and a duplicate of an earlier invoice
resent as a phone photo. Every mismatch was then reviewed by hand.

## Results

Measured on the full run of 20 documents (`eval/results.csv`):

| Measure | Result |
| --- | --- |
| Header fields correct (vendor, number, dates, currency, PO, subtotal, tax, shipping, total) | 200 of 200 |
| Line items fully correct (description, quantity, unit price, amount) | 79 of 80 |
| Planted errors caught (wrong total, duplicate) | 2 of 2, each with the right reason |
| Clean documents wrongly sent to review | 0 of 18 |
| Invented values (made-up due dates, USD on Canadian bills) | 0 |
| Time per document, upload to finished | 7.6 s median, 21.5 s slowest |
| AI cost per document | $0.025 |
| Email intake | 3 emailed documents (a scan, a photo, a receipt) read and filed |

The one line-item miss is a store receipt that prints the product name cut short ("Bubble wrap roll 12in x 17");
the system recorded exactly what was printed. These results describe a 20-document test set in three invoice
layouts; real supplier paperwork is more varied, which is what the review queue is for.

## How it works

Python and FastAPI receive each file and answer at once. A background worker takes documents from a Postgres
(Supabase) queue, sends the PDF text or page images to Claude with a strict output schema, then runs the checks in
plain code. n8n watches the Gmail inbox and writes to Google Sheets and Slack. The web app is Next.js with shadcn/ui.
The worker retries rate limits, outages and network errors, resends any register row or Slack message that didn't
go out, and an independent code review of the whole system was run and its findings fixed before release.

## What it means for an AP team

Typing goes away for the documents that pass, and the team's attention goes to the few that don't, each one
arriving with the reason it was stopped. A wrong total or a double-billed invoice is caught before it is paid, not
found at month end.
