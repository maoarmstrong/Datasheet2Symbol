"""Synthetic fixtures only; deliberately not a cloud accuracy benchmark."""
import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from backend.models import Pin

root=Path(__file__).resolve().parents[1]/'fixtures'; root.mkdir(exist_ok=True)
samples={
 'power':('DEMO-PWR','QFN-8+EP', [('1','VIN','Power','Power','electrical'),('2','VIN','Power','Power','electrical'),('3','EN','Input','Control','electrical'),('4','NC','Passive','Reserved','NC'),('5','OUT','Power','Power','electrical'),('6','GND','Power','Ground','electrical'),('7','GND','Power','Ground','electrical'),('8','FB','Input','Control','electrical'),('9','EP','Power','Ground','exposed_pad')]),
 'digital':('DEMO-DIG','TSSOP-6',[('01','VDD','Power','Power','electrical'),('02','PA0','Bidirectional','GPIO','electrical'),('03','PA1','Bidirectional','GPIO','electrical'),('04','nRESET','Input','Control','electrical'),('05','DNC','Passive','Reserved','DNC'),('06','GND','Power','Ground','electrical')]),
 'connector':('DEMO-CONN','Receptacle-X',[('A1','GND','Passive','Ground','electrical'),('A2','TX+','Passive','Channel','electrical'),('B12','TX-','Passive','Channel','electrical'),('SH1','SHIELD','Passive','Shield','shield'),('MP1','LOCATOR','Unknown','Mechanical','mechanical')]),
 'multipage':('DEMO-CROSS','QFN-12',[(str(i),name,typ,group,'electrical') for i,name,typ,group in [(1,'VDD','Power','Power'),(2,'VDD','Power','Power'),(3,'GND','Power','Ground'),(4,'nCS','Input','Control'),(5,'nRESET','Input','Control'),(6,'CLK','Input','Clock'),(7,'AIN+','Input','Analog'),(8,'AIN-','Input','Analog'),(9,'OUT+','Output','Analog'),(10,'OUT-','Output','Analog'),(11,'PA0','Bidirectional','GPIO'),(12,'GND','Power','Ground')]])
}
for key,(name,package,values) in samples.items():
 pins=[];doc=fitz.open()
 for page_index in range(2):
  page=doc.new_page(width=595,height=842)
  page.draw_rect(fitz.Rect(35,35,560,100),color=(.15,.4,.32),fill=(.92,.96,.93))
  page.insert_text((50,61),'SYNTHETIC DEMO - NOT A REAL DATASHEET',fontsize=15)
  page.insert_text((50,83),f'{name} / {package} / File page {page_index+1}',fontsize=12)
  page.insert_text((50,135),'PIN TABLE - selected package only',fontsize=14)
  page.insert_text((50,160),'Number    Original name       Type             Kind',fontsize=11,fontname='cour')
  subset=list(enumerate(values))[:(len(values)+1)//2] if page_index==0 else list(enumerate(values))[(len(values)+1)//2:]
  for row,(i,(number,pname,typ,group,kind)) in enumerate(subset):
   page.insert_text((50,195+row*30),f'{number:<9} {pname:<18} {typ:<16} {kind}',fontname='cour',fontsize=10)
   evidence={'page':page_index+1,'printed_page':str(10+page_index),'kind':'table','quote':f'{number}: {pname} ({kind}) — synthetic fixture'}
   pin=Pin(number=number,original_name=pname,symbol_name=pname,electrical_type=typ,group='',part='B' if group in ['Power','Ground','Shield'] else 'A',position='Left' if typ!='Output' else 'Right',kind=kind,fact='explicit',observation='Mating face view; do not mirror' if key=='connector' else '',evidence=[evidence]).model_dump()
   if key=='multipage' and number=='4': pin['evidence'].append({'page':2,'printed_page':'11','kind':'footnote','quote':'nCS is active low. Synthetic footnote.'})
   pins.append(pin)
   pin['table_row']={'page':page_index+1,'name':pname,'selected_column':package,'columns':{package:[number]}}
  notes=['This document and all pin assignments are fictional test fixtures.','Printed page labels intentionally differ from PDF file page numbers.']
  if key=='connector': notes+=['Drawing observation: MATING FACE VIEW. Do not mirror.','MP1 is a mechanical locating feature, not an electrical contact.']
  if key=='digital': notes+=['Alternative package (not selected): WLCSP-6 uses A1,A2,B1,B2,C1,C2.']
  if key=='multipage': notes+=['nCS / nRESET are active-low. Table continues across pages.']
  for n,note in enumerate(notes): page.insert_text((50,570+n*24),note,fontsize=10)
  page.insert_text((50,795),f'SYNTHETIC / printed page {10+page_index}',fontsize=10)
 target={'model':name,'package':package,'pin_count':sum(x[4]!='mechanical' for x in values),'fact':'explicit','observation':'Synthetic benchmark only','evidence':[{'page':1,'printed_page':'10','kind':'description','quote':'Synthetic model and package'}]}
 (root/f'{key}.json').write_text(json.dumps({'name':name,'target':target,'pins':pins},ensure_ascii=False,indent=2),encoding='utf-8')
 doc.save(root/f'{key}.pdf')
 doc[0].get_pixmap(matrix=fitz.Matrix(1,1)).save(root/f'{key}-preview.png')
 doc.close()
print('Generated four explicitly synthetic test fixtures.')
