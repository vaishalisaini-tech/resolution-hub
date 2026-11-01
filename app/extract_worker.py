"""Bounded subprocess document extraction. Not a full OS sandbox."""
import sys,os,json,io,base64,zipfile,tempfile,subprocess
from pathlib import Path
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup
from .content import plain_html
LIMIT=20*1024*1024

def extract(data,name,depth=0):
    if depth>3:raise ValueError('Nested attachment depth exceeded')
    ext=Path(name).suffix.lower();out={'html':'','children':[],'warnings':[],'mime':'application/octet-stream'}
    if ext in ['.txt','.md','.log','.csv','.json']:
        out['html']=plain_html(data.decode('utf-8-sig'));out['mime']='text/plain'
    elif ext=='.eml':
        msg=BytesParser(policy=policy.default).parsebytes(data)
        part=msg.get_body(preferencelist=('html','plain'))
        body=part.get_content() if part else ''
        if not isinstance(body,str):body=''
        if not part or part.get_content_type()!='text/html':body=plain_html(body)
        header='\n'.join(k+': '+str(msg.get(k,'')) for k in ['Subject','From','To','Date'])
        out['html']=plain_html(header)+body;out['mime']='message/rfc822'
        parts=list(msg.walk())
        if len(parts)>100:raise ValueError('Too many MIME parts')
        for p in parts:
            if p.is_multipart() or p is part:continue
            filename=p.get_filename();cid=str(p.get('Content-ID','')).strip('<>')
            if not filename and not cid:continue
            payload=p.get_payload(decode=True)
            if payload is None:continue
            filename=filename or ('inline'+('.png' if p.get_content_type()=='image/png' else '.jpg' if p.get_content_type()=='image/jpeg' else '.bin'))
            out['children'].append(child(payload,filename,cid,depth))
    elif ext=='.msg':
        import extract_msg
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'mail.msg';p.write_bytes(data)
            with extract_msg.Message(str(p)) as msg:
                html=msg.htmlBody
                if isinstance(html,bytes):html=html.decode('utf-8',errors='replace')
                out['html']=plain_html('Subject: '+str(msg.subject or '')+'\nFrom: '+str(msg.sender or '')+'\nTo: '+str(msg.to or '')+'\nDate: '+str(msg.date or ''))+(html or plain_html(msg.body or ''))
                for a in list(msg.attachments)[:30]:
                    try:
                        payload=a.data
                        if not isinstance(payload,bytes):out['warnings'].append('Embedded MSG attachment could not be decoded');continue
                        out['children'].append(child(payload,a.longFilename or a.shortFilename or 'attachment.bin',str(getattr(a,'cid','') or '').strip('<>'),depth))
                    except Exception:out['warnings'].append('An MSG attachment could not be extracted')
        out['mime']='application/vnd.ms-outlook'
    elif ext=='.pdf':
        if not data.startswith(b'%PDF-'):raise ValueError('Not a PDF')
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data))
        if reader.is_encrypted:raise ValueError('Encrypted PDF unsupported')
        if len(reader.pages)>100:raise ValueError('PDF page limit: 100')
        out['html']=''.join('<h3>Page '+str(i+1)+'</h3>'+plain_html(p.extract_text() or '') for i,p in enumerate(reader.pages));out['mime']='application/pdf'
        out['warnings'].append('PDF layout and embedded images are not fully reproduced; scanned PDFs require separate OCR preprocessing.')
    elif ext=='.docx':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(x.file_size for x in z.infolist())>LIMIT:raise ValueError('Expanded DOCX too large')
            if 'word/document.xml' not in z.namelist():raise ValueError('Not a DOCX')
            for path in [n for n in z.namelist() if n.startswith('word/media/')][:20]:out['children'].append(child(z.read(path),Path(path).name,'',depth))
        from docx import Document
        doc=Document(io.BytesIO(data));out['html']=''.join(plain_html(p.text) for p in doc.paragraphs)
        for t in doc.tables:out['html']+='<table>'+''.join('<tr>'+''.join('<td>'+plain_html(c.text)+'</td>' for c in r.cells)+'</tr>' for r in t.rows)+'</table>'
        out['mime']='application/vnd.openxmlformats-officedocument.wordprocessingml.document';out['warnings'].append('DOCX images are attachments; original positioning is not guaranteed.')
    elif ext in ['.png','.jpg','.jpeg','.webp']:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS=16000000
        im=Image.open(io.BytesIO(data));im.load()
        if im.width*im.height>16000000:raise ValueError('Image pixel limit exceeded')
        im.thumbnail((2400,2400));buffer=io.BytesIO();im.convert('RGB').save(buffer,format='PNG')
        out['normalized']=base64.b64encode(buffer.getvalue()).decode();out['mime']='image/png'
        if os.getenv('OCR_ENABLED')=='true':
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'image.png';p.write_bytes(buffer.getvalue())
                try:
                    r=subprocess.run(['tesseract',str(p),'stdout'],capture_output=True,timeout=15,check=True);out['html']=plain_html(r.stdout.decode(errors='replace'))
                except Exception:out['warnings'].append('OCR unavailable or failed; image retained without extracted text.')
        else:out['warnings'].append('OCR disabled; image text is not extracted. Vision requires an approved capable model.')
    else:raise ValueError('Unsupported attachment format: '+ext)
    if len(out['html'])>400000:raise ValueError('Extracted content too large')
    return out

def child(data,name,cid,depth):
    if len(data)>LIMIT:raise ValueError('Attachment too large')
    try:result=extract(data,name,depth+1)
    except Exception as e:result={'html':'','children':[],'warnings':['Attachment not extracted: '+str(e)[:200]],'mime':'application/octet-stream'}
    return {'name':Path(name.replace('\\','/')).name[:180],'cid':cid,'data':base64.b64encode(data).decode(),'result':result}
if __name__=='__main__':
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(25,25));resource.setrlimit(resource.RLIMIT_AS,(1024*1024*1024,1024*1024*1024))
        except (ImportError,ValueError):pass
        data=Path(sys.argv[1]).read_bytes();result=extract(data,sys.argv[2]);encoded=json.dumps(result)
        if len(encoded)>40*1024*1024:raise ValueError('Extraction result too large')
        Path(sys.argv[3]).write_text(encoded)
    except Exception as e:
        Path(sys.argv[3]).write_text(json.dumps({'error':str(e)[:300]}));sys.exit(1)
