"""Fill the supplied report templates without rebuilding their static content."""
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import math
import re
from lxml import etree

TEMPLATES = Path(__file__).with_name('report_templates')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS = {'w': W, 's': S}


def _payload(app):
    sections = {s['sheet']: s for s in app._report_sections()}
    def table(sheet, index=0):
        return sections[sheet]['tables'][index]['rows']
    def values(rows, keys):
        return [[r.get(k, '') for k in keys] for r in rows]
    stem = 'name cdtn y1 v1 fr1 a shape k1 theta L k2 bed k3 f ho T h1 kh d50 vc ratio ys_pier'.split()
    cap = 'name cdtn y1 v1 ys_pier y2 h2 T apc v2 apc_star fr2 d50 vc2 ratio2 kw_pc cap_shape k1_pc theta Lpc k2_pc k3 ys_pc'.split()
    pile = 'name cdtn y1 v1 ys_pier y3 h3 ap S m n aproj km ksp apg y3max khpg v3 shape k1 k3 ys_pg note'.split()
    footing = 'name cdtn y1 v1 ys_pier y2 h2 h1 yf v2 ks vf apc y2_af frf d50 vc2 ratiof kw_lb k1_foot k2_pc k3 footing'.split()
    single = 'name cdtn y1 v1 fr1 a shape k1 theta L k2 bed k3 d50 vc ratio kw single z_single note'.split()
    lc, lb = table('XCB-lo coc'), table('XCB-lo be')
    pile_rows = [{**r, 'shape': 'Mũi tròn', 'k1': 1.0} for r in lc if r.get('has_piles',True) and r.get('h3',0)>0]
    out = dict(lc_stem=values(lc, stem), lc_cap=values(lc, cap), lc_pile=values(pile_rows, pile),
        lc_sum=values(lc, 'stt name cdtn ys_pier ys_pc ys_pg ys_total'.split()),
        lb_stem=values(lb, stem[:-1] + ['kw', 'ys_pier']), lb_cap=values(lb, footing),
        lb_sum=values(lb, 'stt name cdtn ys_pier footing ys_lb'.split()),
        single=values(table('Xoi cuc tru'), single),
        xc=values(table('Xói chung'), [str(i) for i in range(23)]),
        denh=values(table('Nuoc denh'), [str(i) for i in range(15)]))
    c = app._report_context
    # The sample's Vcau table describes submerged parts rather than the GUI's
    # separate projected component areas. All areas come from the actual run.
    geometry = {p['name']: p for p in app._report_piers}
    vcau = []
    for r in table('Vcau', 2):
        p = geometry.get(r['0'], {})
        num = lambda k: float(r.get(str(k), 0) or 0)
        depth = lambda width, area: area / width if width > 0 else ''
        vcau.append([r['0'], num(1), p.get('aproj', '') if num(8) else '',
            depth(num(7), num(8)), p.get('apc', '') if num(6) else '',
            depth(num(5), num(6)), p.get('a', ''), depth(num(3), num(4)),
            c['skew'], num(9), num(10)])
    out['vcau'] = vcau
    out['vcau_totals'] = [sum(r[9] for r in vcau), sum(r[10] for r in vcau)]
    out['vcau_summary'] = ['', out['vcau_totals'][1], '', out['vcau_totals'][1],
                           '', out['vcau_totals'][0], '', c['area_bridge'],
                           c['qtk'] / c['area_bridge']]
    # Same 15 columns as the original V-H/Word table, with the extra "Phía"
    # column retained. No explanatory abbreviations or additional columns.
    vh = c['vh_data']; ai = c['ai_vals']
    ppll, morphology = [], []
    cum_area = cum_q = cum_width = perimeter_sum = 0.0
    for i, p in enumerate(vh):
        cum_width += p['dl']; cum_area += p['wi']; cum_q += p['Qi']
        h53 = p['hi'] ** (5 / 3)
        ppll.append(['', p['name'], p['z'], p['hi'], p['dl'], cum_width,
            p['wi'], cum_area, h53, ai[i], c['alpha'],
            p['Qi'] / p['dl'] if p['dl'] > 0 else 0.0, p['Qi'], cum_q, p['Vi']])
        wet = c['wet_w'][i]
        dh = p['hi'] - vh[i - 1]['hi'] if i else 0.0
        per = math.hypot(wet, dh) if wet > 0 else 0.0
        perimeter_sum += per
        cos_sk = math.cos(math.radians(c['skew']))
        morphology.append([p['name'], p['z'], p['hi'], p['wi']/wet if wet > 0 else 0.0,
            p['dl']/cos_sk if cos_sk > 1e-9 else '', c['skew'], p['dl'], p['wi'], per, ''])
    out['ppll'] = ppll
    out['ppll_total'] = sum(ai)
    out['morphology'] = morphology
    out['morphology_total'] = ['', '', '', '', '', '', cum_width, cum_area, perimeter_sum, '']
    out['summary'] = values(table('Tong hop'), 'name cdtn left main right ys_local y_tot z_scour'.split())
    return out


def _copy_package(source, target, replacements):
    # Retain all OLE equations, drawings, relationships, styles and metadata.
    with ZipFile(source) as src, ZipFile(target, 'w', ZIP_DEFLATED) as dst:
        for entry in src.infolist():
            dst.writestr(entry, replacements.get(entry.filename, src.read(entry.filename)))


def export_word(app, target):
    from docx import Document
    from docx.table import _Row
    from docx.oxml.ns import qn
    source = TEMPLATES / 'MaubangtinhXoi.docx'
    doc = Document(source)
    tables = list(doc.tables)
    data = _payload(app)
    def set_cell(cell, value):
        texts = cell._tc.findall('.//w:t', NS)
        old = ''.join(t.text or '' for t in texts).strip()
        try:
            number = float(value)
            digits = len(old.rsplit(',', 1)[1]) if ',' in old else (len(old.rsplit('.',1)[1]) if '.' in old else 0)
            text = f'{number:.{digits}f}'.replace('.', ',')
        except (TypeError, ValueError):
            text = str(value)
        if texts:
            texts[0].text = text
            for t in texts[1:]: t.text = ''
        else:
            cell.paragraphs[0].add_run(text)
        # New project names and user-entered descriptions are Unicode.
        # Preserve the sample's typeface for its existing TCVN3 text/equations.
        if any(ord(ch) > 255 for ch in text):
            for run in cell.paragraphs[0].runs:
                run.font.name = 'Times New Roman'
    def block(table_index, start, end, rows, positions=None):
        table = tables[table_index]
        old = list(table.rows)[start:end+1]
        seed = deepcopy(old[0]._tr)
        anchor = old[-1]._tr.getnext()
        for row in old: table._tbl.remove(row._tr)
        for values in rows or [[]]:
            tr = deepcopy(seed)
            if anchor is None: table._tbl.append(tr)
            else: anchor.addprevious(tr)
            row = _Row(tr, table)
            # Remove every specimen value, including intentionally blank cells.
            seen = set()
            for cell in row.cells:
                if cell._tc not in seen:
                    set_cell(cell, ''); seen.add(cell._tc)
            for pos, value in zip(positions if positions is not None else range(len(values)), values):
                # Format numbers using the original column's number of decimals.
                cell = row.cells[pos]
                original = _Row(deepcopy(seed), table).cells[pos]
                cell._tc.replace(cell._tc.find(qn('w:p')), deepcopy(original._tc.find(qn('w:p'))))
                set_cell(cell, value)
    c = app._report_context
    set_cell(tables[0].cell(0,5), f"{c['htk']:.2f} (m)")
    set_cell(tables[1].cell(0,4), c['htk']); set_cell(tables[1].cell(0,10), c['qtk'])
    set_cell(tables[2].cell(0,5), c['htk']); set_cell(tables[2].cell(0,11), c['qtk'])
    # Update fixed summary cells before variable rows are inserted.
    for i,value in enumerate(data['vcau_summary']): set_cell(tables[0].cell(11+i,11), value)
    for pos,value in zip([11,12],data['vcau_totals']): set_cell(tables[0].cell(10,pos),value)
    set_cell(tables[2].cell(52,9),data['ppll_total']); set_cell(tables[2].cell(52,10),c['alpha'])
    block(0,4,9,data['vcau'],[0,1,2,4,6,7,8,9,10,11,12])
    # Word sample intentionally has no x0 column; keep that exact table.
    block(1,3,3,[r[:13]+[r[14]] for r in data['denh']])
    block(2,3,51,data['ppll'])
    block(3,4,4,[r[:22] for r in data['xc']],
          [0,1,2,3,4,5,7,9,10,11,12,13,16,17,18,19,21,23,25,27,29,31])
    # Bottom-to-top replacement keeps the source coordinates stable.
    block(5,15,17,data['lc_pile'],[0,2,5,8,13,18,21,24,26,30,31,34,38,41,44,46,49,52,55,59,61,64,68])
    block(5,9,11,data['lc_cap'],[0,1,4,7,10,15,20,23,25,29,33,37,40,42,45,47,50,54,57,60,62,65,67])
    block(5,3,5,data['lc_stem'],[0,3,6,9,14,19,22,27,28,32,35,39,43,46,48,51,53,56,60,63,66,69])
    block(6,2,4,data['lc_sum'],[0,1,2,4,6,7,8])
    block(8,2,2,data['lb_stem'])
    block(9,2,2,data['lb_cap'])
    block(10,3,3,data['lb_sum'],[0,1,2,3,6,9])
    xml = etree.tostring(doc.element, xml_declaration=True, encoding='UTF-8', standalone=True)
    _copy_package(source,target,{'word/document.xml':xml})


def export_excel(app, target):
    """Patch worksheet XML; preserve all original shapes, equations and styles."""
    import posixpath
    from openpyxl.utils.cell import get_column_letter, column_index_from_string
    source = TEMPLATES / 'MauTTXoiCau.xlsx'
    data = _payload(app); context = app._report_context
    with ZipFile(source) as package:
        parts = {n:package.read(n) for n in package.namelist()}
    workbook = etree.fromstring(parts['xl/workbook.xml'])
    rels = etree.fromstring(parts['xl/_rels/workbook.xml.rels'])
    paths = {r.get('Id'):posixpath.normpath('xl/'+r.get('Target')) for r in rels}
    styles = etree.fromstring(parts['xl/styles.xml'])
    fonts, xfs = styles.find('s:fonts',NS), styles.find('s:cellXfs',NS)
    unicode_styles = {}
    def unicode_style(style_id):
        if style_id not in unicode_styles:
            xf = deepcopy(xfs[int(style_id)])
            font = deepcopy(fonts[int(xf.get('fontId','0'))])
            name = font.find('s:name',NS)
            if name is not None: name.set('val','Times New Roman')
            fonts.append(font); fonts.set('count',str(len(fonts)))
            xf.set('fontId',str(len(fonts)-1)); xfs.append(xf); xfs.set('count',str(len(xfs)))
            unicode_styles[style_id]=str(len(xfs)-1)
        return unicode_styles[style_id]
    def set_value(cell,value):
        for child in list(cell): cell.remove(child)
        cell.attrib.pop('t',None)
        if value == '' or value is None: return
        try:
            number = float(value)
            if not math.isfinite(number): raise ValueError('Non-finite report value')
            etree.SubElement(cell,'{%s}v'%S).text=repr(number)
        except (TypeError,ValueError):
            cell.set('t','inlineStr')
            node=etree.SubElement(etree.SubElement(cell,'{%s}is'%S),'{%s}t'%S)
            node.text=str(value);node.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
            if any(ord(ch)>255 for ch in str(value)):
                cell.set('s',unicode_style(cell.get('s','0')))
    def cell_at(root,address):
        sd=root.find('s:sheetData',NS); r=int(re.search(r'\d+',address).group())
        row=sd.find(f"s:row[@r='{r}']",NS)
        if row is None:
            row=etree.Element('{%s}row'%S,r=str(r));sd.append(row)
        cell=row.find(f"s:c[@r='{address}']",NS)
        if cell is None:
            cell=etree.Element('{%s}c'%S,r=address)
            if len(row):cell.set('s',row[0].get('s','0'))
            row.append(cell)
        return cell
    shared = etree.fromstring(parts['xl/sharedStrings.xml'])
    def replace_caption_number(root, address, old, new):
        cell = cell_at(root, address)
        if cell.get('t') != 's': return
        value = cell.find('s:v', NS)
        if value is None: return
        item = deepcopy(shared[int(value.text)])
        for text in item.findall('.//s:t', NS):
            if text.text: text.text = text.text.replace(old, new)
        shared.append(item); value.text = str(len(shared)-1)
    blocks = {
        'Vcau':[(9,14,data['vcau'])],
        'denh':[(7,7,data['denh'])],
        'V-H':[(8,54,data['ppll'])],
        'V-H (Htb)':[(7,36,data['ppll'])],
        'hinh thai':[(6,54,data['morphology'])],
        'HTB lu':[(7,36,data['morphology'])],
        'xoi chung':[(9,9,data['xc'])],
        'XBC-lo coc':[(32,34,data['lc_stem']), (39,41,data['lc_cap']),
                       (46,48,data['lc_pile']), (53,55,data['lc_sum'])],
        'XCB-Lo Be':[(22,23,data['lb_stem']), (28,29,data['lb_cap']), (34,35,data['lb_sum'])],
        'xoi cuc  tru':[(23,23,data['single'])],
        'TH xoi':[(5,10,data['summary'])]}
    # Summary tables use merged physical columns; keep those exact spans.
    columns = {('XBC-lo coc',53):[1,3,5,7,9,10,11],
               ('XCB-Lo Be',34):[1,3,5,6,10,13]}
    headers = {'Vcau':{'D3':context['htk']},
        'denh':{'E3':context['htk'],'K3':context['qtk']},
        'hinh thai':{'C2':context['htk'],'B5':context['htk'],'F5':context['skew']},
        'HTB lu':{'C3':context['htk'],'B6':context['htk'],'F6':context['skew']},
        'V-H':{'F3':context['htk'],'L3':context['qtk'],'C7':context['htk'],'D7':0},
        'V-H (Htb)':{'F2':context['htk'],'L2':context['qtk'],'C6':context['htk'],'D6':0},
        'xoi chung':{'D3':context['htk']},
        'XBC-lo coc':{'H28':context['htk'],'L28':context['qtk']},
        'XCB-Lo Be':{'H18':context['htk'],'L18':context['qtk']},
        'xoi cuc  tru':{'I18':context['htk']}}
    summaries={'Vcau':{'J17':data['vcau_totals'][0],'K17':data['vcau_totals'][1],
                       **{f'J{20+i}':v for i,v in enumerate(data['vcau_summary'])}},
        'V-H':{'J55':data['ppll_total'],'K55':context['alpha']},
        'V-H (Htb)':{'J37':data['ppll_total'],'K37':context['alpha']},
        'hinh thai':{'G55':data['morphology_total'][6],'H55':context['area'],
                     'I55':data['morphology_total'][8], 'E56':context['qtk']/context['area'],
                     'E57':context['qtk']},
        'HTB lu':{'G37':data['morphology_total'][6],'H37':context['area'],
                  'I37':data['morphology_total'][8]}}
    sheet_maps={}
    for sheet in workbook.find('s:sheets',NS):
        name=sheet.get('name');path=paths[sheet.get('{%s}id'%R)]
        if name not in blocks:continue
        root=etree.fromstring(parts[path]);sd=root.find('s:sheetData',NS)
        if name == 'HTB lu':
            replace_caption_number(root, 'A2', '2.47', f"{context['htk']:.2f}")
        for address,value in {**headers.get(name,{}),**summaries.get(name,{})}.items():
            set_value(cell_at(root,address),value)
        ranges=blocks[name]
        def map_row(r, ranges=ranges):
            delta=0
            for start,end,rows in ranges:
                size=max(1,len(rows))
                if r>end:delta+=size-(end-start+1)
                elif r>=start:return start+delta+min(r-start,size-1)
            return r+delta
        def ref(value):
            return re.sub(r'(\$?[A-Z]{1,3}\$?)(\d+)',lambda m:m[1]+str(map_row(int(m[2]))),value)
        # Clone source data-row formatting; clear every specimen value first.
        seeds={start:deepcopy(sd.find(f"s:row[@r='{start}']",NS)) for start,_,_ in ranges}
        for row in list(sd):
            r=int(row.get('r'))
            if any(start<=r<=end for start,end,_ in ranges):sd.remove(row);continue
            row.set('r',str(map_row(r)))
            for cell in row:
                if cell.get('r'):cell.set('r',ref(cell.get('r')))
                f=cell.find('s:f',NS)
                if f is not None and f.text and '!' not in f.text:f.text=ref(f.text)
        for start,end,rows in ranges:
            seed=seeds[start]
            for offset,values in enumerate(rows or [[]]):
                r=map_row(start)+offset;row=deepcopy(seed);row.set('r',str(r))
                for cell in row:
                    if cell.get('r'):cell.set('r',re.sub(r'\d+',str(r),cell.get('r')))
                    set_value(cell,'')
                positions=columns.get((name,start),range(len(values)))
                for col,value in zip(positions,values):
                    address=get_column_letter(col+1)+str(r)
                    cell=row.find(f"s:c[@r='{address}']",NS)
                    if cell is None:cell=etree.SubElement(row,'{%s}c'%S,r=address)
                    set_value(cell,value)
                row[:]=sorted(row,key=lambda c:column_index_from_string(re.sub(r'\d+','',c.get('r','A1'))))
                sd.append(row)
        sd[:]=sorted(sd,key=lambda row:int(row.get('r')))
        for node in root.iter():
            if node is sd or node.tag in ('{%s}c'%S,'{%s}row'%S):continue
            for attribute in ('ref','sqref'):
                if node.get(attribute):node.set(attribute,ref(node.get(attribute)))
        # Replicate merged cells belonging to repeated summary rows.
        merged=root.find('s:mergeCells',NS)
        if merged is not None:
            seen=set(); remove=[]
            for node in merged:
                if node.get('ref') in seen:remove.append(node)
                seen.add(node.get('ref'))
            for node in remove:merged.remove(node)
            for start,end,rows in ranges:
                seed_refs=[n.get('ref') for n in merged if re.fullmatch(r'[A-Z]+'+str(map_row(start))+r':[A-Z]+'+str(map_row(start)),n.get('ref',''))]
                for offset in range(1,max(1,len(rows))):
                    for seed_ref in seed_refs:
                        new_ref=re.sub(r'\d+',str(map_row(start)+offset),seed_ref)
                        if new_ref not in seen:etree.SubElement(merged,'{%s}mergeCell'%S,ref=new_ref);seen.add(new_ref)
            merged.set('count',str(len(merged)))
        sheet_maps[name]=map_row
        parts[path]=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
        # Move original comments/shapes with the expanded worksheet rows.
        relpath=posixpath.join(posixpath.dirname(path),'_rels',posixpath.basename(path)+'.rels')
        if relpath in parts:
            sr=etree.fromstring(parts[relpath])
            for relation in sr:
                child=posixpath.normpath(posixpath.join(posixpath.dirname(path),relation.get('Target')))
                if child not in parts:continue
                if '/drawings/' in child and child.endswith('.xml'):
                    draw=etree.fromstring(parts[child])
                    for node in draw.iter():
                        if etree.QName(node).localname=='row' and node.text and node.text.isdigit():node.text=str(map_row(int(node.text)+1)-1)
                    parts[child]=etree.tostring(draw,xml_declaration=True,encoding='UTF-8',standalone=True)
    # Print areas/titles follow inserted rows while their original columns remain.
    for defined in workbook.findall('s:definedNames/s:definedName',NS):
        if not defined.text:continue
        for name,mapper in sheet_maps.items():
            if defined.text.startswith("'"+name+"'!") or defined.text.startswith(name+'!'):
                defined.text=re.sub(r'(\$?[A-Z]{1,3}\$?)(\d+)',lambda m:m[1]+str(mapper(int(m[2]))),defined.text)
                break
    # Cached report results are authoritative; avoid recalculating template formulas.
    calc=workbook.find('s:calcPr',NS)
    if calc is not None:calc.set('calcMode','manual');calc.set('fullCalcOnLoad','0');calc.set('forceFullCalc','0')
    parts['xl/workbook.xml']=etree.tostring(workbook,xml_declaration=True,encoding='UTF-8',standalone=True)
    parts['xl/styles.xml']=etree.tostring(styles,xml_declaration=True,encoding='UTF-8',standalone=True)
    shared.set('uniqueCount', str(len(shared)))
    parts['xl/sharedStrings.xml']=etree.tostring(shared,xml_declaration=True,encoding='UTF-8',standalone=True)
    _copy_package(source,target,parts)
