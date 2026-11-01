import re,html
from bs4 import BeautifulSoup,Comment
ALLOWED={'p','br','b','strong','i','em','u','s','ul','ol','li','table','thead','tbody','tr','td','th','blockquote','div','span','pre','code','h1','h2','h3','h4','a','img','hr'}
BLOCKED={'script','style','iframe','object','embed','svg','math','form','input','button','textarea','select','link','meta','base','template','noscript'}
STYLE=re.compile(r'^(?:#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,20}|\d{1,3}(?:px|pt|%)|left|right|center|bold|normal|italic|underline|collapse|solid)$')
def clean(raw):
    soup=BeautifulSoup(raw[:500000],'html.parser')
    for x in soup.find_all(string=lambda t:isinstance(t,Comment)):x.extract()
    for tag in list(soup.find_all(True)):
        if tag.name is None:continue
        if tag.name in BLOCKED:tag.decompose();continue
        if tag.name not in ALLOWED:tag.unwrap();continue
        attrs={}
        if tag.name=='img':
            src=tag.get('src','')
            if not re.fullmatch(r'/api/assets/[a-f0-9-]{36}/image',src):tag.decompose();continue
            attrs={'src':src,'alt':str(tag.get('alt','Inline image'))[:200]}
        if tag.name=='a':
            href=tag.get('href','')
            if re.match(r'^https?://',href,re.I):attrs={'href':href,'rel':'noopener noreferrer','target':'_blank'}
        for key in ['colspan','rowspan']:
            if str(tag.get(key,'')).isdigit() and 1<=int(tag[key])<=20:attrs[key]=str(tag[key])
        styles=[]
        for part in str(tag.get('style','')).split(';'):
            if ':' not in part:continue
            key,value=map(str.strip,part.split(':',1))
            if key in ['color','background-color','font-weight','font-style','text-align','text-decoration','font-size','border-collapse'] and STYLE.fullmatch(value):styles.append(key+':'+value)
        if styles:attrs['style']=';'.join(styles)
        tag.attrs=attrs
    return str(soup)
def text(raw):return BeautifulSoup(raw,'html.parser').get_text('\n',strip=True)
def plain_html(value):return '<p>'+html.escape(value).replace('\n','<br>')+'</p>'
def image_ids(raw):return set(re.findall(r'/api/assets/([a-f0-9-]{36})/image',raw))
def split_pairs(raw,source):
    value=text(raw)
    # Heading-based extraction is deterministic; no missing solution is invented.
    blocks=re.split(r'\n\s*-{3,}\s*\n|(?=^\s*(?:Issue|Problem)\s*\d*\s*:)',value,flags=re.M|re.I)
    blocks=[b.strip() for b in blocks if b.strip()]
    if len(blocks)>1 and not re.match(r'^(?:Issue|Problem)\s*\d*\s*:',blocks[0],re.I) and re.match(r'^(?:Issue|Problem)\s*\d*\s*:',blocks[1],re.I):
        prefix=blocks.pop(0);blocks[0]=prefix+'\n'+blocks[0]
    pairs=[]
    for b in blocks[:30]:
        m=re.search(r'^\s*(?:Resolution|Solution|Fix)\s*:\s*',b,re.M|re.I)
        issue=b[:m.start()] if m else b;resolution=b[m.end():].strip() if m else ''
        issue=re.sub(r'^\s*(?:Issue|Problem)\s*\d*\s*:\s*','',issue,flags=re.I).strip()
        pairs.append({'issue_html':plain_html(issue),'resolution_html':plain_html(resolution),'source':source,'warnings':[] if m else ['No explicitly labelled resolution found; save unresolved or review manually.'],'method':'heading-based','confirmed':False})
    if len(pairs)==1:
        # Preserve full sanitized email formatting in the issue when no labelled split exists.
        if not pairs[0]['resolution_html'] or not text(pairs[0]['resolution_html']):pairs[0]['issue_html']=raw
    return pairs
