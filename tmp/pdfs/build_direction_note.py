from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
import pdfplumber

ROOT = Path('/home/puffedrice/Documents/food-app')
OUT = ROOT / 'output/pdf/nutrition-buddy-direction-note.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont('DV', '/usr/share/fonts/TTF/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DV-Bold', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'))
pdfmetrics.registerFontFamily('DV', normal='DV', bold='DV-Bold', italic='DV', boldItalic='DV-Bold')
W, H = A4
M = 40
CW = W - M * 2
INK = HexColor('#203B3A')
MUTED = HexColor('#596C6A')
TEAL = HexColor('#16736A')
PAPER = HexColor('#FBFAF6')
PALE = HexColor('#EAF3ED')
LILAC = HexColor('#EEEAF6')
SAND = HexColor('#F3EDDE')
LINE = HexColor('#D9E1DB')
c = canvas.Canvas(str(OUT), pagesize=A4)
c.setTitle('Bangla Nutrition Buddy - product direction note')
c.setAuthor('Internal product planning')

def text(s, x, top, width, size=10, leading=14.5, color=INK, bold=False):
    style = ParagraphStyle('p', fontName='DV-Bold' if bold else 'DV', fontSize=size,
                           leading=leading, textColor=color, spaceAfter=0)
    p = Paragraph(s, style)
    _, h = p.wrap(width, 1000)
    p.drawOn(c, x, top-h)
    return top-h

def base(page, tagline):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    text('WORKING NOTE / INTERNAL / OCT 2026', M, H-31, CW, 8, 11, TEAL, True)
    c.setStrokeColor(LINE)
    c.line(M, 39, W-M, 39)
    text(tagline, M, 29, CW-30, 7.5, 10, MUTED)
    text(str(page) + ' / 3', W-M-29, 29, 29, 7.5, 10, MUTED)

def card(x, top, width, height, title, items, fill=PALE, size=10):
    c.setFillColor(fill)
    c.roundRect(x, top-height, width, height, 12, fill=1, stroke=0)
    y = text(title, x+16, top-16, width-32, 12, 16, INK, True) - 11
    for item in items:
        y = text(item, x+16, y, width-32, size, 14.3) - 10
    assert y >= top-height+4, (title, y, top-height)
    return y

def arrow(x1, y, x2):
    c.setStrokeColor(TEAL)
    c.setLineWidth(1.3)
    c.line(x1, y, x2, y)
    c.line(x2-4, y+3, x2, y)
    c.line(x2-4, y-3, x2, y)

base(1, 'Direction, not a specification. Keep the first version focused.')
y = text('Bangla nutrition buddy', M, H-64, CW, 27, 33, INK, True)
y = text('Everyday help. A useful history for the doctor.', M, y-10, CW, 13, 18, TEAL, True)
y = text('Help people make realistic food choices using local meals, budget, preferences and self-reported conditions. Over time, turn their meal logs into a history they can share at a consultation.', M, y-14, CW, 10.5, 15.5)

top = y-25
gap = 16
nw = (CW-gap*3)/4
labels = [('<b>Log a meal</b>', 'Text, voice or photo'),
          ('<b>Get useful help</b>', 'Caution, swap or portion idea'),
          ('<b>Build a history</b>', 'Patterns across logged meals'),
          ('<b>Share at a visit</b>', 'Doctor reviews with patient')]
for i, (label, desc) in enumerate(labels):
    x = M+i*(nw+gap)
    c.setFillColor(PALE if i != 3 else LILAC)
    c.roundRect(x, top-100, nw, 100, 9, fill=1, stroke=0)
    text('0'+str(i+1), x+11, top-10, nw-22, 8, 10, TEAL, True)
    yy=text(label, x+11, top-29, nw-22, 10, 14)
    text(desc, x+11, yy-7, nw-22, 8.5, 12, MUTED)
    if i<3: arrow(x+nw+3, top-51, x+nw+gap-3)
text('Later: an explicitly approved doctor plan can guide daily suggestions.', M, top-112, CW, 8.5, 12, MUTED)

top2=top-149
col=(CW-16)/2
card(M, top2, col, 238, 'For the person', [
    '<b>Easy logging:</b> repeat meals, local names, Bangla/Banglish and familiar portions.',
    '<b>Relevant help:</b> use reported conditions to flag food considerations. For diabetes + a likely sweet, explain the concern and ask about portion.',
    '<b>Practical choices:</b> work with what is affordable, available and cooked at home.',
    '<b>Memory:</b> remember preferences and corrections; let the user edit or forget them.'
], PALE, 9.5)
card(M+col+16, top2, col, 238, 'For the doctor', [
    '<b>Quick summary:</b> frequent foods, food groups, reported portions and meal timing.',
    '<b>Useful context:</b> conditions, allergies, budget and household constraints.',
    '<b>Inspect the evidence:</b> open supporting entries, photos and assumptions.',
    '<b>See the gaps:</b> show logging coverage and uncertainty. Keep doctor notes separate from AI observations.'
], LILAC, 9.5)

bt=top2-254
card(M, bt, CW, 130, 'History should be honest, not overconfident', [
    '<b>Example:</b> "18 of the last 30 days have entries. Sweetened tea appears on 11 logged days; sugar quantity is often unknown."',
    'Missing entries are not skipped meals. A photo is not proof the food was eaten. The doctor makes the assessment.'
], SAND, 9.5)
c.showPage()

base(2, 'More detail and source links: product-feasibility-review.md')
y=text('What to keep in mind', M, H-66, CW, 25, 31, INK, True)
y=text('A small, trustworthy loop first. Add complexity when it earns its place.', M, y-11, CW, 10.5, 15.5, MUTED)
top=y-23
card(M, top, col, 198, 'AI + reviewed rules', [
    'AI understands meals and explains options. Reviewed rules and food data drive cautions and calculations.',
    'Photos miss oil, sugar and weight. Confirm important details; label estimates.',
    'Avoid blanket food bans. Reports of treating low blood sugar need a different, reviewed response.'
], PALE, 9.5)
card(M+col+16, top, col, 198, 'Learn the right things', [
    'Dish and portion corrections update the record. Taste, price and availability update preferences.',
    '"I ate it anyway" is context, not proof of safety. Overrides must not remove health rules.',
    'Start with editable memory and ranking. Park reinforcement learning.'
], LILAC, 9.5)
top2=top-213
card(M, top2, col, 180, 'Local data is real work', [
    'Curate local names, recipe variants, household portions and nutrient data. Unknown is not zero.',
    'Support saved recipes, shared cooking, low-cost phones and patchy internet.',
    'Keep correctable meal records, separate from chat.'
], SAND, 9.5)
card(M+col+16, top2, col, 180, 'Sharing must be deliberate', [
    'Doctor logs in; patient gives an ID/QR and approves access. An ID alone unlocks nothing.',
    'Allow expiry and revocation; show access history. Plan caregiver permissions.',
    'Review privacy, hosting and medical claims locally before launch.'
], PALE, 9.5)
top3=top2-188
card(M, top3, CW, 126, 'Build now / park for later', [
    '<b>Now:</b> one adult cohort, easy logs, reviewed food cautions, preference memory and a shareable 7/30-day history.',
    '<b>Later:</b> all-age pathways, wearables, restaurant estimates and hospital integrations. Do not promise deficiency prediction or exact photo nutrition.'
], LILAC, 9.5)
top4=top3-140
text('Questions for our next planning session', M, top4, CW, 12, 16, INK, True)
q='Who is first? Which conditions? Who reviews advice? Who pays? Will people keep logging, and will doctors use the history?'
yy=text(q, M, top4-25, CW, 10, 14.5)
yy=text('<b>Feasibility:</b> a focused pilot is realistic. Test logging effort, doctor usefulness, accuracy and cost before expanding.', M, yy-12, CW, 10, 14.5, TEAL)
assert yy > 53, yy
c.showPage()

base(3, 'Suggested starting stack. Validate providers, Bangla quality and hosting before committing.')
y=text('How we could build it', M, H-66, CW, 25, 31, INK, True)
y=text('One web app, one modular backend, one database. Keep the first build simple.', M, y-10, CW, 10, 14, MUTED)

stack_top=y-18
stack_rows=[
    ('App + doctor view', 'Next.js / React + TypeScript; PWA for phone-friendly access.'),
    ('Backend', 'Python FastAPI + Pydantic: APIs, validation, calculations, rules.'),
    ('Data', 'PostgreSQL: meals, recipes, profiles, preferences, consent, audit.'),
    ('Photos + AI', 'Private S3-compatible storage; hosted vision + Bangla speech APIs.'),
    ('Access + jobs', 'Managed OIDC login; API checks. Redis + Celery when jobs need it.'),
]
row_h=25
c.setFillColor(PALE)
c.roundRect(M, stack_top-len(stack_rows)*row_h-12, CW, len(stack_rows)*row_h+12, 10, fill=1, stroke=0)
for i,(label,desc) in enumerate(stack_rows):
    rt=stack_top-8-i*row_h
    text(label,M+12,rt,102,8.8,12,INK,True)
    bot=text(desc,M+120,rt,CW-133,8.5,11.5)
    assert bot>=rt-row_h+1, (label,bot,rt)

flow_top=stack_top-len(stack_rows)*row_h-32
text('A meal goes through this flow',M,flow_top,CW,11.5,16,INK,True)
node_top=flow_top-25
node_h=43
node_gap=10
steps=[
    ('1  CAPTURE', 'Next.js sends text, voice or a photo through the authenticated API.'),
    ('2  UNDERSTAND', 'FastAPI calls hosted AI / speech tools to draft food and portion candidates.'),
    ('3  CONFIRM', 'Patient corrects important details. Considering food and eating it are separate.'),
    ('4  ASSESS', 'Python calculates estimates; reviewed rules + saved preferences shape options.'),
    ('5  RESPOND + SAVE', 'AI explains in Bangla; validate output. Save the reported meal + assumptions.'),
]
for i,(title,desc) in enumerate(steps):
    nt=node_top-i*(node_h+node_gap)
    c.setFillColor(LILAC if i in (1,4) else PALE)
    c.roundRect(M,nt-node_h,CW,node_h,8,fill=1,stroke=0)
    text(title,M+12,nt-7,CW-24,8.5,11,TEAL,True)
    b=text(desc,M+12,nt-22,CW-24,8.5,11.5)
    assert b>=nt-node_h+4, (title,b,nt-node_h)
    if i<4:
        ax=W/2
        a_top=nt-node_h-1
        a_bot=a_top-node_gap+2
        c.setStrokeColor(TEAL)
        c.setLineWidth(1)
        c.line(ax,a_top,ax,a_bot)
        c.line(ax-3,a_bot+3,ax,a_bot)
        c.line(ax+3,a_bot+3,ax,a_bot)
bottom=node_top-4*(node_h+node_gap)-node_h
text('Corrections update records; preferences improve ranking. Health rules stay reviewed.',M,bottom-8,CW,8.3,11.5,MUTED)

dt=bottom-34
text('At the doctor visit',M,dt,CW,11.5,16,INK,True)
dt-=25
dw=(CW-3*gap)/4
dsteps=[('ID / QR', 'Doctor signs in; patient identifies record.'),
        ('Patient approval', 'API checks clinician, scope and expiry.'),
        ('History summary', 'SQL computes patterns + logging gaps.'),
        ('Doctor review', 'Inspect entries, add notes; access is logged.')]
for i,(title,desc) in enumerate(dsteps):
    xx=M+i*(dw+gap)
    c.setFillColor(SAND)
    c.roundRect(xx,dt-69,dw,69,8,fill=1,stroke=0)
    yy=text(title,xx+9,dt-9,dw-18,8.5,11,INK,True)
    yy=text(desc,xx+9,yy-6,dw-18,8,11,MUTED)
    assert yy>=dt-69+4,(title,yy,dt-69)
    if i<3: arrow(xx+dw+3,dt-35,xx+dw+gap-3)

ops_top=dt-82
yy=text('<b>Run it:</b> Docker on managed hosting; encrypted backups, error monitoring and versioned rules/model checks. Send minimum necessary data to AI; select hosting after privacy review.',M,ops_top,CW,8.5,12)
refs_top=yy-7
yy=text('Stack references: <link href="https://nextjs.org/docs/app/guides/progressive-web-apps" color="#16736A">Next.js PWA</link> / <link href="https://fastapi.tiangolo.com/features/" color="#16736A">FastAPI</link> / <link href="https://www.postgresql.org/docs/17/ddl-rowsecurity.html" color="#16736A">PostgreSQL access policies</link>',M,refs_top,CW,7.5,10,MUTED)
assert yy>48,yy
c.save()

with pdfplumber.open(OUT) as pdf:
    assert len(pdf.pages)==3
    full='\n'.join(p.extract_text() or '' for p in pdf.pages)
    assert 'Bangla nutrition buddy' in full
    assert 'Questions for our next planning session' in full
    assert 'How we could build it' in full
    print(f'Created {OUT}; pages={len(pdf.pages)}; words={len(full.split())}')
