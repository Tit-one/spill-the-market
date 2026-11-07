"""Portable report formats. Imported/user text is always escaped in HTML."""
from __future__ import annotations

import csv
import html
import io
import json


def export_report(report: dict, format: str) -> tuple[str, str, str]:
    if format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2), "application/json", "report.json"
    scenarios = report.get("scenarios", [])
    columns = ["plan_id", "name", "is_baseline", "price_cents", "mean_revenue_cents", "mean_units",
               "mean_spend_cents", "mean_cac_cents", "mean_paid_cac_cents"]
    if format == "csv":
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for scenario in scenarios:
            safe = {key: scenario.get(key) for key in columns}
            for key, value in safe.items():
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
                    safe[key] = "'" + value
            writer.writerow(safe)
        return "\ufeff" + output.getvalue(), "text/csv", "report.csv"
    product = report.get("product", {})
    title = product.get("name", "Spill the Market") if isinstance(product, dict) else str(product)
    currency = product.get("currency", "EUR") if isinstance(product, dict) else "EUR"
    def money(value):
        return "—" if value is None else f"{float(value) / 100:,.2f} {currency}"
    rows = [[str(s.get("name", "")), str(s.get("mean_units", 0)), money(s.get("mean_revenue_cents", 0)),
             money(s.get("mean_spend_cents", 0)), money(s.get("mean_cac_cents"))] for s in scenarios]
    assumptions = report.get("assumptions", [])
    if format == "md":
        def clean(value):
            return str(value).replace("|", "\\|").replace("\n", " ")
        text = f"# {clean(title)} — synthetic launch experiment\n\n"
        text += "Simulation variability is conditional on model assumptions; it does not validate market demand.\n\n"
        text += "| Strategy | Units | Virtual revenue | Media cost | Blended CAC |\n|---|---:|---:|---:|---:|\n"
        text += "\n".join("| " + " | ".join(clean(x) for x in row) + " |" for row in rows)
        text += "\n\n## Assumptions\n\n" + "\n".join("- " + clean(x) for x in assumptions)
        return text, "text/markdown", "report.md"
    if format != "html":
        raise ValueError("format must be json, csv, md or html")
    def esc(value):
        return html.escape(str(value), quote=True)
    table = "".join("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in row) + "</tr>" for row in rows)
    daily = next((s.get("daily", []) for s in scenarios if not s.get("is_baseline")), [])
    points = []
    if daily:
        maximum = max(float(row.get("cumulative_revenue_cents", 0)) for row in daily) or 1
        points = [f"{20 + i * 660 / max(1, len(daily)-1):.2f},{180 - 160 * float(row.get('cumulative_revenue_cents', 0)) / maximum:.2f}"
                  for i, row in enumerate(daily)]
    chart = f'<svg viewBox="0 0 700 200" role="img" aria-label="Cumulative virtual revenue"><polyline fill="none" stroke="#2455f5" stroke-width="3" points="{" ".join(points)}"/></svg>'
    body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — Spill the Market</title><style>body{{font:16px system-ui,sans-serif;color:#14213d;margin:40px auto;padding:0 24px;max-width:1100px;line-height:1.6}}h1{{font-size:36px}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #dfe5ef;padding:12px;text-align:left}}aside{{background:#eef3ff;padding:18px}}svg{{max-width:100%}}li{{margin:8px 0}}</style>
<p>Spill the Market / synthetic experiment</p><h1>{esc(title)}</h1><aside>Simulated revenue and purchase intentions are hypotheses, not observed sales. Dispersion measures simulation variability.</aside>
<p>{esc(report.get('winner_reason', ''))}</p>{chart}<table><thead><tr><th>Strategy</th><th>Units</th><th>Virtual revenue</th><th>Media cost</th><th>Blended CAC</th></tr></thead><tbody>{table}</tbody></table>
<h2>Assumptions and limitations</h2><ul>{''.join('<li>'+esc(x)+'</li>' for x in assumptions)}</ul>
<p>Population: {esc(report.get('population',''))}; days: {esc(report.get('rounds',''))}; seed: {esc(report.get('seed',''))}.</p></html>"""
    return body, "text/html", "report.html"
