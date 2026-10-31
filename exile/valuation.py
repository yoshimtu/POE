"""Numeric item values and stack-aware, equipment-free container summaries."""
import math

from exile.prices import format_price,format_range


def quote_key(item):
    links=item.get('links',0)
    # The provider groups 0–4 linked sockets together; 5L/6L remain distinct.
    if isinstance(links,int)and 0<=links<5:links=0
    key=item.get('name'),item.get('base'),links,item.get('corrupted')
    if item.get('art'):key=(*key,item['art'])
    if item.get('visual_identity'):key=(*key,'visual_identity',item['visual_identity'])
    return (*key,'foulborn',item['foulborn'])if item.get('foulborn')is not None else key


FOULBORN_AREAS={'monastery of the keepers','hive colony','hive fortress'}


def foulborn_area(area):
    return ' '.join(str(area).casefold().split()).removeprefix('the ') in FOULBORN_AREAS


def enrich_items(items,currencies,unique_quotes,area=''):
    divine=currencies.get('divine orb')
    for item in items:
        for field in ('chaos_estimate','value_low','value_high','price_label'):item.pop(field,None)
        quantity=item.get('quantity',1)
        if item.get('decode_error') or not isinstance(quantity,int) or quantity<=0:continue
        low=high=None;quote=None
        metadata=item.get('metadata','')
        bulk=item.get('stackable')or metadata.startswith(('Metadata/Items/Currency/','Metadata/Items/Scarabs/','Metadata/Items/DivinationCards/','Metadata/Items/MapFragments/'))
        if bulk:
            price=currencies.get(item.get('name','').casefold())
            if price is not None:low=high=price
        elif item.get('rarity')==3:
            quote=unique_quotes.get(quote_key(item))
            if quote:
                alternatives=quote.get('alternatives')
                if alternatives:
                    # This is the user's location fallback, not a decoded item flag.
                    alternatives=[candidate for candidate in alternatives
                                  if not candidate['name'].casefold().startswith('foulborn ') or item.get('foulborn')is True or (item.get('foulborn')is None and foulborn_area(area))]
                    if not alternatives:continue
                    quote=dict(quote,alternatives=alternatives)
                    low=min(candidate['low']for candidate in alternatives)
                    high=max(candidate['high']for candidate in alternatives)
                else:low,high=quote['low'],quote['high']
        if not all(isinstance(v,(int,float))and math.isfinite(v)and v>=0 for v in (low,high)):continue
        low*=quantity;high*=quantity
        item.update(value_low=low,value_high=high,chaos_estimate=low,
                    price_label=format_range(low,high,divine))
        if quote and quote.get('alternatives'):
            labels=[format_range(candidate['low']*quantity,candidate['high']*quantity,divine)
                    for candidate in quote['alternatives']]
            item['price_label']=' / '.join(dict.fromkeys(labels))


def summarize(items,divine=None):
    groups={};seen=set();unknown=priced=0;total_low=total_high=0.
    for index,item in enumerate(items):
        entity=item.get('entity')
        if entity is not None and entity in seen:continue
        if entity is not None:seen.add(entity)
        low,high=item.get('value_low'),item.get('value_high')
        if not all(isinstance(v,(int,float))and math.isfinite(v)and v>=0 for v in (low,high)):
            unknown+=1;continue
        total_low+=low;total_high+=high
        priced+=1
        # Only interchangeable stackables are merged. Two rare/unique pieces
        # with unread rolls are not claimed to be identical items.
        key=('stack',item.get('metadata'),*quote_key(item)) if item.get('stackable') else ('item',entity if entity is not None else index)
        row=groups.setdefault(key,dict(name=item.get('name')or'Item',quantity=0,stacks=0,low=0.,high=0.))
        row['quantity']+=item.get('quantity',1);row['stacks']+=1
        row['low']+=low;row['high']+=high
    rows=sorted(groups.values(),key=lambda r:(-r['low'],-r['high'],r['name']))
    for row in rows:row['price_label']=format_range(row['low'],row['high'],divine)
    total_label=''if unknown and not priced else format_range(total_low,total_high,divine)
    return dict(total_low=total_low,total_high=total_high,total_label=total_label,
                unknown=unknown,priced=priced,top=rows[:3])
