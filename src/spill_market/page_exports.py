"""Escaped, portable page-analysis evidence exports."""
import base64
import csv
import html
import io
import json
import re


def export_page_audit(audit: dict, assets_dir, format: str):
    report = audit["report"]
    if format == "json":
        value = {"audit_id": audit["id"], "snapshots": audit["snapshots"], "report": report}
        return json.dumps(value, ensure_ascii=False, indent=2), "application/json", "page-audit.json"
    reviews = report.get("reviews", [])
    if format == "csv":
        stream = io.StringIO(newline="")
        fields = ["persona_id", "age", "variant_id", "snapshot_id", "viewport", "step", "mode",
                  "understanding", "questions", "frictions", "trust", "intention_before", "intention_after", "intended_action"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for review in reviews:
            row = {key: review.get(key) for key in fields}
            for key, value in row.items():
                if isinstance(value, list):
                    value = "; ".join(map(str, value))
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    value = "'" + value
                row[key] = value
            writer.writerow(row)
        return "\ufeff" + stream.getvalue(), "text/csv", "page-audit.csv"
    if format == "md":
        def clean(value):
            return html.escape(str(value)).replace("|", "\\|").replace("\n", " ")
        text = "# Product-page analysis\n\nSynthetic comprehension hypotheses; not measured buyer behavior.\n\n"
        for observation in report.get("observations", []):
            text += f"## {clean(observation['snapshot_id'])}\n\n{clean(observation['summary'])}\n\n"
        text += "| Persona | Age | Page | Section | Understanding | Questions | Intention |\n|---|---:|---|---|---|---|---|\n"
        for r in reviews:
            text += "| " + " | ".join(clean(r.get(k)) for k in
                ("persona_id", "age", "variant_id", "snapshot_id", "understanding", "questions", "intention_after")) + " |\n"
        text += "\n## Limitations\n\n" + "\n".join("- " + clean(v) for v in report.get("limitations", []))
        return text, "text/markdown", "page-audit.md"
    if format != "html":
        raise ValueError("format must be json, csv, html or md")
    def esc(value):
        return html.escape(str(value))
    sections = []
    for snapshot in audit["snapshots"]:
        identifier = snapshot["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            continue
        image = assets_dir / f"{identifier}.jpg"
        data = base64.b64encode(image.read_bytes()).decode() if image.is_file() else ""
        observation = next((o for o in report.get("observations", []) if o["snapshot_id"] == identifier), {})
        sections.append(f'<section><h2>{esc(identifier)}</h2><img alt="Local page capture" '
                        f'src="data:image/jpeg;base64,{data}"><p>{esc(observation.get("summary", ""))}</p></section>')
    rows = "".join("<tr>" + "".join(f"<td>{esc(r.get(key, ''))}</td>" for key in
                   ("persona_id", "age", "variant_id", "snapshot_id", "mode", "understanding", "questions",
                    "frictions", "intention_before", "intention_after")) + "</tr>" for r in reviews)
    limitations = "".join(f"<li>{esc(v)}</li>" for v in report.get("limitations", []))
    text = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Page analysis</title>'
    text += '<style>body{font:16px system-ui;max-width:1400px;margin:2rem auto;padding:1rem}img{max-width:100%;max-height:650px}td,th{border:1px solid #aaa;padding:.5rem;vertical-align:top}table{border-collapse:collapse}section{margin:2rem 0}</style>'
    text += '<h1>Product-page analysis</h1><p>Synthetic comprehension hypotheses, not measured conversions.</p>'
    text += "".join(sections) + "<table><thead><tr>" + "".join(f"<th>{x}</th>" for x in
        ("Persona", "Age", "Page", "Section", "Mode", "Understanding", "Questions", "Friction", "Before", "After"))
    text += "</tr></thead><tbody>" + rows + "</tbody></table><h2>Limitations</h2><ul>" + limitations + "</ul></html>"
    return text, "text/html", "page-audit.html"
