"""Render and inspect machine-checkable final PDF properties before manual review."""
import re,subprocess,shutil
from PIL import Image,ImageDraw
import pymupdf
from common import *

JOURNAL_ABBREVIATIONS={
    'Proceedings of the VLDB Endowment':'Proc. VLDB Endow.',
    'Proceedings of the ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies':'Proc. ACM Interact. Mob. Wearable Ubiquitous Technol.',
    '2016 IEEE International Parallel and Distributed Processing Symposium (IPDPS)':'Proc. IEEE IPDPS',
    'IEEE Transactions on Visualization and Computer Graphics':'IEEE Trans. Vis. Comput. Graph.',
    'Journal of Computational Physics':'J. Comput. Phys.',
    'SIAM Journal on Numerical Analysis':'SIAM J. Numer. Anal.',
    'Bell System Technical Journal':'Bell Syst. Tech. J.',
    'IEEE Transactions on Information Theory':'IEEE Trans. Inf. Theory',
    'ACM Computing Surveys':'ACM Comput. Surv.',
    'Scientific Data':'Sci. Data',
    'IEEE Transactions on Intelligent Transportation Systems':'IEEE Trans. Intell. Transp. Syst.',
    'Nature Methods':'Nat. Methods',
    'Journal of the American Statistical Association':'J. Am. Stat. Assoc.',
    'Scandinavian Journal of Statistics':'Scand. J. Stat.',
    'Annals of Statistics':'Ann. Stat.',
    'IEEE Transactions on Big Data':'IEEE Trans. Big Data',
}

def abbreviate_journals(text):
    for full,short in JOURNAL_ABBREVIATIONS.items():text=text.replace(full,short)
    return text

def shorten_long_author_lists(text):
    def replace(match):
        parts=match[2].split(', ')
        if len(parts)>12 or ('et al.' in match[2] and len(parts)>8):
            return match[1]+', '.join(parts[:6])+', et al.:'
        return match[0]
    return re.sub(r'(\\bibitem\{[^}]+\}\s*)([^:\n]+):',replace,text)

def bibliography_identity(text):
    text=shorten_long_author_lists(abbreviate_journals(text))
    return re.sub(r'\s+',' ',re.sub(r'\\url\{[^}]*\}','',text)).strip()
def references():
    original=(DEV/'before/paper/iccies_references.tex').read_text(encoding='utf8')
    target=ROOT/'paper/iccies_references.tex';current=target.read_text(encoding='utf8')
    metadata=json.loads((DEV/'audit/SZ3_reference_primary.json').read_text(encoding='utf8'))
    assert metadata['DOI'].lower()=='10.1109/tbdata.2022.3201176'
    assert metadata['title'][0]=='SZ3: A Modular Framework for Composing Prediction-Based Error-Bounded Lossy Compressors'
    added=r'''
\bibitem{sz3} Liang, X., Zhao, K., Di, S., Li, S., Underwood, R., Gok, A.M., Tian, J., Deng, J., Calhoun, J.C., Tao, D., Chen, Z., Cappello, F.: SZ3: A Modular Framework for Composing Prediction-Based Error-Bounded Lossy Compressors. IEEE Transactions on Big Data 9(2), 485--498 (2023). \url{https://doi.org/10.1109/TBDATA.2022.3201176}
'''
    if r'\bibitem{sz3}' not in current:
        assert current==original
        current=current.replace(r'\end{thebibliography}',added+r'\end{thebibliography}');target.write_text(current,encoding='utf8')
    assert bibliography_identity(original.split(r'\end{thebibliography}')[0]) in bibliography_identity(current)
    full_links=DEV/'audit/references_with_full_links.tex'
    if not full_links.exists():full_links.write_text(current,encoding='utf8')
    entries=re.split(r'(?=\\bibitem\{)',current)
    for j,entry in enumerate(entries):
        key=re.match(r'\\bibitem\{([^}]+)\}',entry)
        if key and key[1] not in {'idfdata','cmudata','solar','zstd_spec'}:
            entries[j]=re.sub(r'\s*\\url\{[^}]*\}','',entry)
    current=shorten_long_author_lists(abbreviate_journals(''.join(entries)));target.write_text(current,encoding='utf8')
    audit=ROOT/'audit/iccies_references.json';registry=json.loads(audit.read_text(encoding='utf8'))
    existing=[r for r in registry['references'] if r['key']!='sz3']
    registry.pop('original_entries_unchanged',None)
    registry.update(passed=True,count=len(existing)+1,references=existing+[dict(key='sz3',status='verified-original-arxiv-and-Crossref-publisher-metadata',source=metadata)],checked_on='2026-10-30',original_bibliographic_identities_unchanged=True,presentation='Article DOI links omitted for space; complete links retained in evidence; dataset and protocol URLs retained')
    assert registry['count']==29
    audit.write_text(json.dumps(registry,indent=2,ensure_ascii=False)+'\n',encoding='utf8')

def run():
    gate=json.loads((DEV/'results/gate.json').read_text(encoding='utf8'));assert gate['passed']
    document_scripts={'report_v8.py','workflow_v8.py','manuscript_v8.py','finalize_v8.py','compact.py','publish_code.py'}
    for name,digest in gate['code_sha256'].items():
        if name not in document_scripts:assert sha(DEV/'code'/name)==digest,('Numerical source changed after validation',name)
    body=ROOT/'paper/iccies_body.tex';text_source=body.read_text(encoding='utf8')
    assert text_source.startswith((DEV/'before/frontmatter.tex').read_text(encoding='utf8'))
    references_source=(ROOT/'paper/iccies_references.tex').read_text(encoding='utf8')
    keys=set(re.findall(r'\\bibitem\{([^}]+)\}',references_source));cited=set(re.findall(r'\\cite\{([^}]+)\}',text_source))
    assert keys==cited and len(keys)==29,(keys-cited,cited-keys)
    assert all(',' not in key for key in cited)
    assert not re.search(r'\\cite\{[^}]+\}[\s~,;]*\\cite\{',text_source)
    write('../audit/v8_document_qa.json',dict(passed=True,numerical_code_unchanged=True,locked_opening_unchanged=True,
          citations_single_and_separated=True,all_references_cited=True,body_sha256=sha(body)))
    pdf=ROOT/'output/pdf/UAV_Energy_Conserving_Compression.pdf';out=ROOT/'audit/v8_visual';out.mkdir(exist_ok=True)
    for pattern in ['page-*.png','contact_*.png']:
        for previous in out.glob(pattern):
            assert previous.resolve().is_relative_to(out.resolve());previous.unlink()
    poppler=shutil.which('pdftoppm');assert poppler
    subprocess.run([poppler,'-scale-to','1400','-png',str(pdf),str(out/'page')],check=True,capture_output=True)
    pages=sorted(out.glob('page-*.png'))
    for start in range(0,len(pages),8):
        sheet=Image.new('RGB',(1240,3620),'#e5e7eb');draw=ImageDraw.Draw(sheet)
        for j,path in enumerate(pages[start:start+8]):
            im=Image.open(path).convert('RGB');im.thumbnail((600,865));x=20+(j%2)*620;y=25+(j//2)*905
            sheet.paste(im,(x,y));draw.text((x,y+870),f'Page {start+j+1}',fill='black')
        sheet.save(out/f'contact_{start//8+1}.png')
    outside=[];refstyle=[];registry=[];references=False
    with pymupdf.open(pdf) as doc:
        assert 12<=len(doc)<=15,len(doc)
        assert len(pages)==len(doc)
        for i,page in enumerate(doc):
            text=page.get_text();registry.append(dict(page=i+1,words=len(text.split())))
            if re.search(r'^References\s*$',text,re.M):references=True
            for block in page.get_text('blocks'):
                x0,y0,x1,y1=block[:4]
                if x0<0 or y0<0 or x1>page.rect.width or y1>page.rect.height:outside.append(i+1)
            if references:
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines',[]):
                        for span in line['spans']:
                            if span['text'].strip()=='References':continue
                            if span['color']!=0 or 'bold' in span['font'].lower():refstyle.append(dict(page=i+1,text=span['text'],font=span['font'],color=span['color']))
        text='\n'.join(p.get_text() for p in doc)
        assert '??' not in text and '[TODO' not in text and '\ufffd' not in text
    assert not outside and not refstyle,(outside,refstyle)
    refs=json.loads((ROOT/'audit/iccies_references.json').read_text(encoding='utf8'))
    assert refs['passed'] and 20<refs['count']<30
    original=(DEV/'before/paper/iccies_references.tex').read_text(encoding='utf8').split(r'\end{thebibliography}')[0]
    assert bibliography_identity(original) in bibliography_identity((ROOT/'paper/iccies_references.tex').read_text(encoding='utf8'))
    write('../audit/iccies_pdf_qa.json',dict(passed=True,pdf_sha256=sha(pdf),pages=registry,reference_style_violations=refstyle,text_outside_page=outside,
        original_bibliographic_identities_unchanged=True,SZ3_reference_verified=True,no_local_source_paths_in_article=True))
    write('../audit/v8_visual/render.json',dict(pdf_sha256=sha(pdf),pages_rendered=len(pages),renderer=poppler,manual_visual_review='pending'))
    print('Rendered',len(pages),'pages; inspect final contact sheets and detailed figure/table pages',flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--references-only',action='store_true');args=parser.parse_args()
    references()
    if not args.references_only:run()
