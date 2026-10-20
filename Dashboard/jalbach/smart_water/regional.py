"""Automatic public reservoir reports; never used as neighbourhood consumption."""
from html.parser import HTMLParser
import re
import pandas as pd
import requests
from .live import LiveError,utc_now

PUBLIC_SOURCES={
    'Mumbai':'https://mumbaiwaterlevel.com/',
    'Thane':'https://mumbaiwaterlevel.com/thane-water-levels',
    'Kalyan–Dombivli':'https://mumbaiwaterlevel.com/kalyan-dombivli-water-levels',
    'Bhiwandi':'https://mumbaiwaterlevel.com/bhiwandi-water-levels',
    'Ulhasnagar':'https://mumbaiwaterlevel.com/ulhasnagar-water-levels',
    'Ambarnath':'https://mumbaiwaterlevel.com/ambarnath-water-levels',
    'Badlapur':'https://mumbaiwaterlevel.com/badlapur-water-levels',
}

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__();self.hidden=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,value):
        if not self.hidden and value.strip():self.parts.append(value.strip())


def parse_report(html,city,now=None):
    now=utc_now() if now is None else pd.Timestamp(now)
    parser=VisibleText();parser.feed(html)
    text=' '.join(parser.parts)
    # Read the observation/report date, NEVER the SEO title containing "Today".
    match=re.search(r'(?:Report as of|Data as of)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',text)
    if not match:raise LiveError('Public report has no verifiable observation date. No current reading is inferred.')
    date=pd.to_datetime(match[1],dayfirst=True).tz_localize('Asia/Kolkata')
    if date>now:raise LiveError('Public report contains a future date.')
    if city=='Mumbai':
        values=re.search(r'Stored\s+([\d,]+)\s+ML.*?Capacity\s+([\d,]+)\s+ML',text)
    else:
        values=re.search(r'Stored\s+([\d,]+)\s*/\s*([\d,]+)\s+ML',text)
    if not values:raise LiveError('Public report layout changed or storage figures are missing. Values were not guessed.')
    stored,capacity=[float(v.replace(',','')) for v in values.groups()]
    if capacity<=0 or not 0<=stored<=capacity*1.05:
        raise LiveError('Public report storage failed range checks.')
    return {'city':city,'reported_at':date.isoformat(),'fetched_at':now.isoformat(),
            'stored_ml':stored,'capacity_ml':capacity,'percent_full':100*stored/capacity,
            'stale':now-date>pd.Timedelta(days=2),'source_url':PUBLIC_SOURCES[city],
            'provenance':'Independent community republication; attributed by publisher to BMC / Maharashtra WRD. Not independently reconciled with the official bulletin.'}


def fetch_report(city,now=None):
    if city not in PUBLIC_SOURCES:raise LiveError('Unsupported regional source.')
    try:
        response=requests.get(PUBLIC_SOURCES[city],timeout=(5,15))
        response.raise_for_status()
        return parse_report(response.text,city,now)
    except requests.RequestException as exc:
        raise LiveError('Public report could not be reached. No live figures are available from this attempt.') from exc
