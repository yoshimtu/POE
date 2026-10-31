from exile.model import Plugin,Mark
from exile.valuation import summarize
from exile.prices import format_price


class Pricing(Plugin):
    id, name, category = "pricing", "Items & stash", "Economy"
    description = "Ground, inventory and stash prices, stash search, item assessment and movable net-worth summaries."
    defaults = dict(archetype='General',ground_prices=True,inventory_prices=True,badge_font=10,
                    inventory_summary=True,tab_summary=True,summary_closed=False,inventory_rare_ratings=True,
                    summary_anchor='Top centre',summary_x=700,summary_y=26,summary_width=330,summary_font=11,summary_opacity=85,
                    summary_locked=False,summary_positions={},summary_sizes={},assessment_sizes={},stash_overlay=True,
                    stash_query='',stash_scope='Both',stash_prices=True,stash_names=False,
                    rare_enabled=True,rare_mode='Always on',rare_hotkey='Alt+F',rare_feedback=True,assessment_detail='Simple')
    fields = {"archetype": ("Build preference (General = automatic)", "choice",
                            ["General", "Attack", "Spell", "Damage over time", "Energy shield", "Minion", "Mana", "Attribute stacking", "Item find"])}
    fields.update(ground_prices=('Ground item prices','bool'),inventory_prices=('Inventory item prices','bool'),
        inventory_rare_ratings=('Show estimated rare ratings in inventory (*)','bool'),
        badge_font=('Price text size (pixels)','int',7,14),inventory_summary=('Inventory net worth and top 3','bool'),
        tab_summary=('Open stash / guild tab net worth and top 3','bool'),
        summary_anchor=('Default summary position','choice',['Top centre','Custom']),
        summary_x=('Summary left (custom pixels)','int',0,7680),summary_y=('Summary top (pixels)','int',0,4320),
        summary_width=('Summary width (pixels)','int',260,520),summary_font=('Summary text size (pixels)','int',10,16),
        summary_opacity=('Summary background opacity %','int',20,100))
    fields['summary_locked']=('Lock summary positions (click through)','bool')
    fields.update(rare_enabled=('Assess hovered rare items','bool'),
        rare_mode=('Rare assessment display','choice',['Always on','Hotkey only']),
        rare_hotkey=('Detailed breakdown shortcut','string'),rare_feedback=('Show rating feedback buttons','bool'),
        assessment_detail=('Assessment display','choice',['Simple','Detailed']))
    fields.update(stash_overlay=('Show stash overlay','bool'),
        stash_query=('Highlight name, base, tab or mod containing','string'),
        stash_scope=('Stash overlay scope','choice',['Both','Personal','Guild']),
        stash_prices=('Show stash prices','bool'),stash_names=('Show full item names (larger labels)','bool'))
    settings_groups={'Ground & inventory':['ground_prices','inventory_prices','inventory_rare_ratings','badge_font'],
        'Stash':['stash_overlay','stash_prices','stash_names','stash_scope','stash_query'],
        'Net worth':['inventory_summary','tab_summary','summary_locked','summary_anchor','summary_x','summary_y','summary_width','summary_font','summary_opacity'],
        'Assessment':['rare_enabled','rare_mode','rare_hotkey','rare_feedback','assessment_detail','archetype']}

    def migrate_settings(self,saved):
        settings=dict(saved.get(self.id,{}).get('settings',{}))
        legacy=saved.get('stash',{}).get('settings',{})
        for old,new in (('query','stash_query'),('scope','stash_scope'),('prices','stash_prices'),('names','stash_names')):
            if new not in settings and old in legacy:settings[new]=legacy[old]
        return settings

    def stash_marks(self,snapshot):
        if not self.settings['stash_overlay']:return []
        query=self.settings['stash_query'].casefold().strip()
        scope=self.settings['stash_scope'].lower();result=[]
        for item in snapshot.stash[:10000]:
            if scope!='both'and item.get('scope')!=scope:continue
            searchable=' '.join(str(item.get(k,''))for k in ('name','base','tab'))+' '+' '.join(item.get('mods',[]))
            if query and query not in searchable.casefold():continue
            if not item.get('screen')or not item.get('visible'):continue
            rect=item.get('rect');price=item.get('chaos_estimate')
            text=item.get('price_label')or(format_price(price,getattr(snapshot,'divine_chaos',None))if isinstance(price,(int,float))else'')
            if rect and not self.settings['stash_names']:
                if query:result.append(Mark('slot',*rect[:2],color='#a2cbb2',points=[rect[2:]]))
                if self.settings['stash_prices']and text:
                    text=text.replace(' (variants)','*').replace(' (check rolls)','*').replace(' stack','')
                    result.append(Mark('price',*rect[:2],text,'#a2cbb2',points=[rect[2:]]))
            elif self.settings['stash_names']:
                name=item.get('name','Item')
                if self.settings['stash_prices']:name+=' · '+(text or'price unknown')
                result.append(Mark('label',*item['screen'],name,'#a2cbb2',18))
        return result

    def tick(self,snapshot,ctx):
        if snapshot.source not in ('live','preview'):return []
        if snapshot.source=='live'and(not snapshot.fresh()or not snapshot.in_game or snapshot.loading):return []
        result=self.stash_marks(snapshot)
        for enabled,items in ((self.settings['ground_prices'],snapshot.ground_items),
                              (self.settings['inventory_prices']and any(p['scope']=='inventory'for p in snapshot.item_panels),snapshot.inventory)):
            if not enabled:continue
            for item in items:
                rect=item.get('rect');text=item.get('price_label')
                if item.get('visible')and rect and text:
                    result.append(Mark('item_price',*rect[:2],text,'#e2c990',points=[rect[2:]],
                        payload=dict(font=self.settings['badge_font'])))
        if self.settings['inventory_rare_ratings'] and any(p['scope']=='inventory' for p in snapshot.item_panels):
            for item in snapshot.inventory:
                if not item.get('visible') or not item.get('rect') or item.get('price_label'):continue
                score=item.get('inventory_rating')
                if score is not None:
                    rect=item['rect'];result.append(Mark('item_price',*rect[:2],f'{score:g}','#dfc274',points=[rect[2:]],payload=dict(font=self.settings['badge_font'])))
        panels=snapshot.item_panels;sections=[]
        if self.settings['inventory_summary']and any(p['scope']=='inventory'for p in panels):
            summary=summarize(snapshot.inventory,getattr(snapshot,'divine_chaos',None))
            if not snapshot.inventory_loaded:summary.update(total_label='Loading',top=[],unknown=0)
            sections.append(dict(scope='inventory',title='Inventory',**summary))
        if self.settings['tab_summary']:
            for panel in panels:
                scope=panel['scope']
                if scope not in ('personal','guild'):continue
                active={(i.get('tab_index'),i.get('tab'))for i in snapshot.stash if i.get('scope')==scope and i.get('visible')}
                if len(active)==1:
                    index,name=next(iter(active))
                    items=[i for i in snapshot.stash if i.get('scope')==scope and i.get('tab_index')==index]
                    sections.append(dict(scope=scope,title=('Guild'if scope=='guild'else'Stash')+' · '+str(name),
                                         **summarize(items,getattr(snapshot,'divine_chaos',None))))
                else:
                    sections.append(dict(scope=scope,title='Guild tab'if scope=='guild'else'Stash tab',
                        total_label='Reading tab',top=[],unknown=0,priced=0))
        if sections:
            width=self.settings['summary_width'];viewport=snapshot.viewport
            x=max(4,(viewport[0]-width)/2)if self.settings['summary_anchor']=='Top centre'else self.settings['summary_x']
            x=max(0,min(x,viewport[0]-width));y=self.settings['summary_y']
            result.append(Mark('wealth_panel',x,y,payload=dict(sections=sections,settings=dict(self.settings))))
        return result


def create_plugin():
    return Pricing()
