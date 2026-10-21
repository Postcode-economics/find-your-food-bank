# Parse 'Monday, Wednesday and Thursday, 9:30am–8pm; Tuesday to Friday 10am to 6pm' -> {'Mon':'09:30 - 20:00',...}. Returns None if anything is ambiguous.
import re
D=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];K=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
def t24(h,m,ap):
  h=int(h);m=int(m or 0)
  if ap=='pm' and h<12:h+=12
  if ap=='am' and h==12:h=0
  return f"{h:02d}:{m:02d}"
TR=re.compile(r'(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|noon)?\s*(?:–|-|to|until)\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|noon)',re.I)
def parse(s):
  s=s.lower().replace('12 noon','12pm').replace('noon','pm').replace('midday','12pm').replace('mondays','monday').replace('tuesdays','tuesday').replace('wednesdays','wednesday').replace('thursdays','thursday').replace('fridays','friday').replace('saturdays','saturday').replace('sundays','sunday')
  s=re.sub(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday),? closed','',s)
  out={}
  for part in re.split(r';|\n|(?:(?<=am|pm)|(?<=\)))[ ,]+(?=(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))',s):
    m=TR.search(part)
    if not m: continue
    a1=m.group(3) or m.group(6)
    if a1=='pm' and m.group(6)=='pm' and int(m.group(1))>int(m.group(4)) and int(m.group(1))!=12: a1='am'
    span=f"{t24(m.group(1),m.group(2),a1)} - {t24(m.group(4),m.group(5),m.group(6))}"
    dp=part[:m.start()]
    days=set()
    for r in re.finditer(r'(\w+day)\s*(?:to|–|-)\s*(\w+day)',dp):
      if r.group(1) in D and r.group(2) in D:
        i,j=D.index(r.group(1)),D.index(r.group(2));days|=set(range(i,j+1)) if i<=j else set()
    for d in D:
      if d in dp: days.add(D.index(d))
    if not days: return None
    for i in days:
      if K[i] in out: return None
      out[K[i]]=span
  return out or None
