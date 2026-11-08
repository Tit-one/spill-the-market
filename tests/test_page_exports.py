from spill_market.page_exports import export_page_audit


def test_page_exports_escape_page_text_and_spreadsheet_formulas(tmp_path):
    review = {'persona_id':'p1','age':42,'variant_id':'A','snapshot_id':'s1','step':0,'mode':'observation',
              'understanding':'<script>alert(1)</script>','questions':['=CMD()'],'frictions':[],
              'intention_before':.2,'intention_after':.3}
    audit = {'id':'audit','snapshots':[], 'report':{'reviews':[review],'observations':[], 'limitations':[]}}
    html, _, _ = export_page_audit(audit, tmp_path, 'html')
    assert '<script>alert(1)</script>' not in html and '&lt;script&gt;' in html
    csv, _, _ = export_page_audit(audit, tmp_path, 'csv')
    assert "'=CMD()" in csv
    md, _, _ = export_page_audit(audit, tmp_path, 'md')
    assert '<script>' not in md
    content, _, _ = export_page_audit(audit, tmp_path, 'json')
    assert 'audit' in content and 'reviews' in content
