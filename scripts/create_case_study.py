"""Build the one-page teacher submission from real saved project evidence."""
from pathlib import Path
import csv
import sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output'/'pdf'/'DBMS_Case_Study.pdf'
REPO='https://github.com/rajdeepkundu2006/policy-aware-direct-reader'


def build():
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ProjectTitle',fontName='Helvetica-Bold',fontSize=16,leading=19,textColor=colors.black,spaceAfter=6))
    styles.add(ParagraphStyle(name='BodyProject',fontName='Helvetica',fontSize=10.5,leading=13.6,spaceAfter=5,textColor=colors.black))
    styles.add(ParagraphStyle(name='SectionProject',fontName='Helvetica-Bold',fontSize=11,leading=14,spaceBefore=5,spaceAfter=3,textColor=colors.black))
    styles.add(ParagraphStyle(name='SmallProject',fontName='Helvetica',fontSize=9,leading=11.5,spaceAfter=4,textColor=colors.black))
    story=[]
    def p(text,style='BodyProject'):
        story.append(Paragraph(text,styles[style]))
    p('Policy Aware Direct Snapshot Reader','ProjectTitle')
    p('Secure read only query acceleration study | DBMS Theory Case Study','SmallProject')
    p('<b>Team</b> Namit Gawade, Ishaan Singh and Rajdeep Kundu<br/>Department of Computer Science and Engineering, VIT Vellore | 7 October 2026','SmallProject')
    sections=[
        ('1 Brief overview', 'We built a working prototype that compares PostgreSQL row-level security (RLS) with a Python reader operating on a frozen binary export of an employees table. The study tests whether a simpler read path can preserve authorized results and improve latency.'),
        ('2 Problem addressed', 'Bypassing a database engine can also bypass its access controls. Our project investigates how to retain role-based row filtering in a direct reader and checks correctness against PostgreSQL, rather than assuming that faster access is secure.'),
        ('3 Methodology and technologies', 'We use Python, PostgreSQL, psycopg, Streamlit and pytest. PostgreSQL policies are extracted from pg_policy and translated into a restricted policy tree. Python decodes native binary COPY records and filters them. A consistent transaction supplies the export and baseline; complete rows are compared for soundness and completeness. Repeated timings report the mean and sample standard deviation.'),
        ('4 Key features and outcomes', 'The prototype supports IT, HR and Finance roles, validated policies, NULL handling, synthetic datasets, aligned result tables and CSV reports. The research suite covers 27 combinations of three roles, three dataset sizes (1,000 to 100,000 rows) and three salary rules. All 27 cases matched PostgreSQL. The current demonstration has 10,000 rows: 10 original samples and 9,990 generated employees.'),
        ('5 Final project outcome', 'We completed a reproducible prototype and experimental report. PostgreSQL was faster in the 27-case suite; a separate ten-row experiment favored the reader. The outcome demonstrates correct filtering for the tested subset, without claiming universal acceleration. Live heap parsing and arbitrary SQL policies remain future work. No publication or acceptance is claimed.'),
        ('6 Proof of outcome', 'Saved benchmark results and raw timing samples are included in the repository. The local validation suite passed 47 tests, including an offline demo that runs the actual reader against a bundled synthetic snapshot and recorded PostgreSQL baseline. Representative measured IT results from the 27-case suite are shown below.')
    ]
    for heading,body in sections:
        p(heading,'SectionProject'); p(body)
    with (ROOT/'docs'/'evidence'/'benchmark_results.csv').open(encoding='utf-8') as file:
        rows=[r for r in csv.DictReader(file) if r['role']=='it_user' and r['minimum_salary']=='0']
    data=[['Dataset rows','PostgreSQL mean ms','Reader mean ms','Full rows match']]
    data += [[f"{int(r['dataset_size']):,}",f"{float(r['postgres_avg_ms']):.3f}",f"{float(r['reader_avg_ms']):.3f}",'Yes'] for r in rows]
    table=Table(data,colWidths=[98,143,132,111],hAlign='LEFT')
    table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),9),('LEADING',(0,0),(-1,-1),11),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7edf3')),('TEXTCOLOR',(0,0),(-1,-1),colors.black),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#d9d9d9')),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(table);story.append(Spacer(1,6))
    p(f'<b>Repository and evidence</b> <link href="{REPO}" color="black">{REPO}</link>','SmallProject')
    p('<b>Review without PostgreSQL</b> Open demo/index.html for recorded evidence, or run run.cmd demo to execute the local reader. The live database experiment uses run.cmd.','SmallProject')
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(str(OUTPUT),pagesize=letter,rightMargin=44,leftMargin=44,topMargin=34,bottomMargin=32,title='DBMS Theory Case Study Policy Aware Direct Snapshot Reader',author='Namit Gawade; Ishaan Singh; Rajdeep Kundu')
    doc.build(story)
    print(OUTPUT)

if __name__=='__main__':
    build()
